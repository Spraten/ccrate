"""Authenticated Desktop Shelf Checks API tests."""
import io
import json
import pathlib
import tempfile
import threading
import unittest
from email.message import Message
from uuid import uuid4

import desktop_api as api
from badges import Badges
from ledger import Ledger
from native_jobs import NativeJobs
from shelf_checks import ShelfChecks
from sessions import Sessions
from workshop import Workshop


def ident():
    return str(uuid4())


class Request:
    def __init__(self, path, method='GET', data=None, headers=None):
        self.path, self.command = '/workshop-api/' + path, method
        self.headers = Message()
        values = {'Host': 'pi.local:17745', 'Cookie': 'hb.auth.token=alpha; hb.auth.remember=true'}
        values.update(headers or {})
        body = json.dumps(data or {}).encode()
        if method == 'POST':
            values.setdefault('Origin', 'http://pi.local:17745')
            values.setdefault('Content-Type', 'application/json')
            values.setdefault('Content-Length', str(len(body)))
        for name, value in values.items():
            if value is not None:
                self.headers[name] = value
        self.rfile = io.BytesIO(body)
        self.status = self.result = None

    def reply_json(self, status, result):
        self.status, self.result = status, result


class Native:
    def __init__(self, owner, token):
        self.owner, self.token, self.tenant = owner, token, None
        self.writes = []

    def call(self, path, method='GET', data=None):
        if method != 'GET':
            self.writes.append((path, method, data))
        if path == '/api/v1/users/self':
            if self.token not in self.owner.users:
                raise ValueError('expired token')
            return {'item': self.owner.users[self.token]}
        if path == '/api/v1/groups':
            return {'id': self.tenant, 'name': 'Workshop'}
        if path == '/api/v1/groups/members':
            return [{'id': self.owner.manager, 'name': 'Manager'},
                    {'id': self.owner.manager2, 'name': 'Second manager'}]
        raise AssertionError(path)

    def entities(self, locations=False):
        return [dict(row) for row in self.owner.entities.values()
                if row['entityType']['isLocation'] is locations and self.tenant == self.owner.group]

    def entity(self, entity_id):
        if self.tenant != self.owner.group or entity_id not in self.owner.entities:
            raise ValueError('entity unavailable')
        return dict(self.owner.entities[entity_id])


class ShelfCheckApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.group, self.other_group, self.manager, self.member, self.manager2 = [ident() for _ in range(5)]
        self.shelf, self.asset, self.kind = [ident() for _ in range(3)]
        self.users = {
            'alpha': {'id': self.manager, 'name': 'Manager', 'email': 'manager@example.invalid',
                      'defaultGroupId': self.group, 'groupIds': [self.group, self.other_group]},
            'member': {'id': self.member, 'name': 'Member', 'email': 'member@example.invalid',
                       'defaultGroupId': self.group, 'groupIds': [self.group]},
            'manager2': {'id': self.manager2, 'name': 'Second manager', 'email': 'manager2@example.invalid',
                         'defaultGroupId': self.group, 'groupIds': [self.group]},
        }
        self.entities = {
            self.shelf: {'id': self.shelf, 'name': 'Shelf', 'archived': False, 'quantity': 0,
                         'entityType': {'id': self.kind, 'isLocation': True}, 'parent': None},
            self.asset: {'id': self.asset, 'name': 'Drill', 'assetId': '001-001', 'quantity': 1,
                         'archived': False, 'entityType': {'id': self.kind, 'isLocation': False},
                         'parent': {'id': self.shelf}, 'fields': [], 'tags': []},
        }
        self.native_clients = []
        def factory(cookie, base=None):
            token = cookie.split('hb.auth.token=', 1)[1].split(';', 1)[0]
            client = Native(self, token); self.native_clients.append(client); return client
        ops = self.root / 'work/ops'
        ops.mkdir(parents=True)
        (ops / 'desktop-managers.json').write_text(json.dumps({'managers': [
            {'user_id': self.manager, 'group_id': self.group},
            {'user_id': self.manager2, 'group_id': self.group}]}))
        self.ledger = Ledger(ops / 'ledger.db')
        self.deps = {'root': self.root, 'lock': threading.Lock(), 'ledger': self.ledger,
                     'badges': Badges(self.ledger), 'native_jobs': NativeJobs(self.ledger),
                     'workshop': Workshop(ops / 'workshop.db'), 'imports': None,
                     'sessions': Sessions(), 'homebox_factory': factory,
                     'native_base': 'http://127.0.0.1:17745'}
        self.checks = ShelfChecks(self.ledger)
        self.deps['shelf_checks'] = self.checks
        self.identity = self.request('context').result['identity']

    def request(self, path, data=None, *, method=None, headers=None):
        req = Request(path, method or ('GET' if data is None else 'POST'), data,
                      {'X-Workshop-Identity': getattr(self, 'identity', ''), **(headers or {})})
        self.assertTrue(api.handle(req, self.deps))
        return req

    def desktop(self, path, data=None, *, method=None, headers=None):
        return self.request('workshop/checks/' + path, data, method=method, headers=headers)

    def test_nonmanager_private_check_list(self):
        req = Request('workshop/checks/list', headers={'Cookie': 'hb.auth.token=member; hb.auth.remember=true'})
        api.handle(req, self.deps)
        self.assertEqual(req.status, 403)

    def test_same_collection_manager_can_read_service_owned_check_but_not_write_it(self):
        started = self.desktop('start', {'location_id': self.shelf, 'request_key': ident()})
        self.assertEqual(started.status, 200, started.result)
        cookie = {'Cookie': 'hb.auth.token=manager2; hb.auth.remember=true'}
        context = self.request('context', headers=cookie).result
        headers = {**cookie, 'X-Workshop-Identity': context['identity']}
        history = self.desktop('list', headers=headers)
        self.assertEqual(history.status, 200, history.result)
        self.assertEqual([row['id'] for row in history.result], [started.result['id']])
        self.assertFalse(history.result[0]['can_edit'])
        detail = self.desktop('get?id='+started.result['id'], headers=headers)
        self.assertEqual(detail.status, 200, detail.result)
        self.assertEqual(detail.result['group_id'], self.group)
        self.assertEqual(detail.result['actor_id'], self.manager)
        self.assertFalse(detail.result['can_edit'])
        denied = self.desktop('notes', {'id': started.result['id'], 'revision': 0,
                                        'notes': 'must not change', 'request_key': ident()}, headers=headers)
        self.assertEqual(denied.status, 403)
        self.assertEqual(self.desktop('get?id='+started.result['id'], headers={
            'Cookie': 'hb.auth.token=member; hb.auth.remember=true',
            'X-Workshop-Identity': self.request('context', headers={
                'Cookie': 'hb.auth.token=member; hb.auth.remember=true'}).result['identity']}).status, 403)

    def test_terminal_and_desktop_adapters_share_scope_and_revision(self):
        from shelf_checks import shelf_check_action, terminal_check_context

        started = self.desktop('start', {'location_id': self.shelf, 'request_key': ident()})
        self.assertEqual(started.status, 200, started.result)
        client = Native(self, 'alpha')
        ctx = terminal_check_context(client, open_admin=True)
        rows = shelf_check_action(self.checks, client, ctx, 'list', {})
        self.assertEqual([row['id'] for row in rows], [started.result['id']])
        desktop_detail = self.desktop('get?id='+started.result['id']).result
        terminal_detail = shelf_check_action(self.checks, client, ctx, 'get', {'id': started.result['id']})
        self.assertEqual(terminal_detail['revision'], desktop_detail['revision'])
        updated = self.desktop('notes', {'id': started.result['id'], 'revision': 0,
                                         'notes': 'counted', 'request_key': ident()})
        self.assertEqual(updated.status, 200)
        terminal_detail = shelf_check_action(self.checks, client, ctx, 'get', {'id': started.result['id']})
        self.assertEqual(terminal_detail['revision'], updated.result['revision'])
        self.assertEqual(terminal_detail['groups'], updated.result['groups'])
        self.assertEqual(client.writes, [])

    def test_terminal_context_requires_open_admin_and_uses_service_identity(self):
        from shelf_checks import terminal_check_context

        class Client:
            tenant = None
            def call(inner, path):
                if path == '/api/v1/users/self':
                    return {'item': {'id': self.manager, 'defaultGroupId': self.group,
                                     'groupIds': [self.group]}}
                if path == '/api/v1/groups': return {'id': inner.tenant}
                if path == '/api/v1/groups/members': return [{'id': self.manager}]
                raise AssertionError(path)

        client = Client()
        self.assertEqual(terminal_check_context(client, open_admin=True),
                         {'actor': self.manager, 'group': self.group, 'manager': True})
        self.assertEqual(client.tenant, self.group)
        with self.assertRaises(PermissionError):
            terminal_check_context(client, open_admin=False)

    def test_context_revocation_and_cross_actor_replay(self):
        member_cookie = {'Cookie': 'hb.auth.token=member; hb.auth.remember=true'}
        member_ctx = self.request('context', headers=member_cookie).result
        self.assertEqual(self.desktop('list', headers={**member_cookie, 'X-Workshop-Identity': member_ctx['identity']}).status, 403)
        self.assertEqual(self.desktop('get?id='+ident(), headers={**member_cookie, 'X-Workshop-Identity': member_ctx['identity']}).status, 403)
        self.assertEqual(self.desktop('list', headers={'X-Workshop-Group': self.other_group}).status, 403)
        self.assertEqual(self.desktop('list', headers={'X-Workshop-Identity': 'stale'}).status, 409)
        self.assertEqual(self.desktop('list', headers={'X-Workshop-Actor': self.manager}).status, 400)
        start_key = ident()
        started = self.desktop('start', {'location_id': self.shelf, 'request_key': start_key})
        self.assertEqual(started.status, 200, started.result)
        self.assertEqual(self.request('operation/status', {'request_key': start_key},
                                      headers={**member_cookie, 'X-Workshop-Identity': member_ctx['identity']}).status, 403)
        manager_file = self.root / 'work/ops/desktop-managers.json'
        class RevokingLock:
            def __enter__(inner):
                manager_file.write_text(json.dumps({'managers': []}))
                return inner
            def __exit__(inner, *args): return False
        self.deps['lock'] = RevokingLock()
        queued = self.desktop('notes', {'id': started.result['id'], 'revision': 0,
                                        'notes': 'stale manager', 'request_key': ident()})
        self.assertEqual(queued.status, 403)
        self.deps['lock'] = threading.Lock()
        manager_file.write_text(json.dumps({'managers': [
            {'user_id': self.manager, 'group_id': self.group}]}))
        manager_file.write_text(json.dumps({'managers': [
            {'user_id': self.manager, 'group_id': self.group},
            {'user_id': self.member, 'group_id': self.group}]}))
        second_manager = self.request('context', headers=member_cookie).result
        replay = self.desktop('request', {'request_key': start_key},
                              headers={**member_cookie, 'X-Workshop-Identity': second_manager['identity']})
        self.assertEqual(replay.status, 403)
        self.assertNotIn(started.result['id'], json.dumps(replay.result))
        replay_write = self.desktop('start', {'location_id': self.shelf, 'request_key': start_key},
                                    headers={**member_cookie, 'X-Workshop-Identity': second_manager['identity']})
        self.assertEqual(replay_write.status, 409)

    def test_terminal_http_dispatch_returns_stale_revision_conflict(self):
        import contextlib
        import os
        import runpy
        import sys
        import types
        from unittest.mock import patch

        # The server module initializes operational paths at import, so redirect
        # its root first and stub optional scanner modules that this route never uses.
        server_root = self.root / 'terminal-server'
        (server_root / 'work/ops').mkdir(parents=True)
        old_env = {name: os.environ.get(name) for name in ('WORKSHOP_ROOT', 'WORKSHOP_CODE_ROOT')}
        os.environ['WORKSHOP_ROOT'] = str(server_root)
        os.environ['WORKSHOP_CODE_ROOT'] = str(pathlib.Path(__file__).resolve().parents[1])
        modules_before = set(sys.modules)
        sys_path_before = list(sys.path)
        optional_modules = {name: sys.modules.get(name) for name in ('qrcode', 'zxingcpp')}
        sys.modules['qrcode'] = types.ModuleType('qrcode')
        sys.modules['zxingcpp'] = types.ModuleType('zxingcpp')
        try:
            with contextlib.redirect_stdout(io.StringIO()), patch(
                    'http.server.ThreadingHTTPServer',
                    lambda *args, **kwargs: types.SimpleNamespace(serve_forever=lambda: None)):
                server = runpy.run_path(str(pathlib.Path(__file__).resolve().parents[1] / 'deploy/kiosk-server.py'),
                                        run_name='shelf_checks_terminal_test')
        finally:
            for name, module in optional_modules.items():
                if module is None: sys.modules.pop(name, None)
                else: sys.modules[name] = module
            sys.path[:] = sys_path_before
            for name, value in old_env.items():
                if value is None: os.environ.pop(name, None)
                else: os.environ[name] = value
            for name in set(sys.modules) - modules_before:
                sys.modules.pop(name, None)
        self.assertEqual(sys.path, sys_path_before)
        server_globals = server['Handler'].do_POST.__globals__
        server_globals['shelf_checks'] = self.checks
        server_globals['Homebox'] = lambda root: Native(self, 'alpha')
        server_globals['OPEN_ADMIN'] = True

        class Handler(server_globals['Handler']):
            def __init__(inner, path, data):
                body = json.dumps(data).encode()
                inner.path = path
                inner._owned_session = object()
                inner.headers = Message()
                inner.headers['Host'] = '127.0.0.1:17749'
                inner.headers['Origin'] = 'http://127.0.0.1:17749'
                inner.headers['Content-Type'] = 'application/json'
                inner.headers['Content-Length'] = str(len(body))
                inner.rfile = io.BytesIO(body)
                inner.status = inner.result = None
            def reply_json(inner, status, result): inner.status, inner.result = status, result
            def send_error(inner, status, *args, **kwargs): inner.status, inner.result = status, None

        start = Handler('/workshop/checks/start', {'location_id': self.shelf, 'request_key': ident()})
        start.do_POST()
        self.assertEqual(start.status, 200, start.result)
        stale = Handler('/workshop/checks/notes', {'id': start.result['id'], 'revision': 99,
                                                    'notes': 'stale', 'request_key': ident()})
        stale.do_POST()
        self.assertEqual(stale.status, 409, stale.result)

    def test_route_parity_and_conflicts(self):
        key = ident()
        start = self.desktop('start', {'location_id': self.shelf, 'include_nested': False, 'request_key': key})
        self.assertEqual(start.status, 200, start.result)
        check_id = start.result['id']
        listing = self.desktop('list')
        self.assertEqual(listing.status, 200)
        self.assertEqual([row['id'] for row in listing.result], [check_id])
        detail = self.desktop('get?id='+check_id)
        self.assertEqual(detail.status, 200)
        self.assertEqual(detail.result['revision'], 0)
        stale = self.desktop('notes', {'id': check_id, 'revision': 3, 'notes': 'x', 'request_key': ident()})
        self.assertEqual(stale.status, 409)
        invalid = self.desktop('start', {'location_id': 'bad', 'request_key': ident()})
        self.assertEqual(invalid.status, 400)
        malformed = self.desktop('start', {'location_id': self.shelf, 'include_nested': 'false', 'request_key': ident()})
        self.assertEqual(malformed.status, 400)
        malformed_tally = self.desktop('observe', {'id': check_id, 'revision': 0, 'entity_id': self.asset,
                                                    'method': 'visual', 'observed_quantity': -1,
                                                    'request_key': ident()})
        self.assertEqual(malformed_tally.status, 400)
        result = self.desktop('request', {'request_key': key})
        self.assertEqual(result.status, 200)
        self.assertEqual(result.result['result']['id'], check_id)
        self.assertTrue(all(not client.writes for client in self.native_clients))
