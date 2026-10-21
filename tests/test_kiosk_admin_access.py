"""Exercise companion authorization without startup, hardware, or network access."""
import ast
import json
import pathlib
import time
import types
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import desktop_api
import test_desktop_api as fixtures
from checkout import confirm_checkout
from ledger import Conflict
from network_access import same_origin
from returns import confirm_return
from shelf_checks import CheckAccessDenied, terminal_check_context


class Request(fixtures.Request):
    def __init__(self, fixture, path, data=None, cookie=None):
        super().__init__('', 'GET' if data is None else 'POST', data, {
            'Cookie': cookie, 'Host': '127.0.0.1:17749', 'Origin': 'http://127.0.0.1:17749',
            'X-Workshop-Identity': fixture.identity,
        })
        self.path = path
        self.session = fixture.sessions.get('legacy')

    def send_error(self, status):
        self.reply_json(status, {})


class KioskAdminAccessTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.DesktopTests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        source = pathlib.Path(__file__).resolve().parents[1]/'deploy/kiosk-server.py'
        tree = ast.parse(source.read_text())
        selected = [node for node in tree.body if (
            isinstance(node, ast.ClassDef) and node.name == 'Handler'
        ) or (
            isinstance(node, ast.FunctionDef) and node.name == 'label_context'
        ) or (
            isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == 'OPEN_ADMIN'
                for target in node.targets)
        )]
        self.ns = dict(self.fixture.deps, ROOT=self.fixture.root,
            LABEL_ASSET_ROOT=self.fixture.root, BaseHTTPRequestHandler=BaseHTTPRequestHandler,
            desktop_handle=lambda request, deps: desktop_api.handle(request, dict(deps,
                homebox_factory=self.fixture.deps['homebox_factory'],
                native_base=self.fixture.deps['native_base'])),
            json=json, time=time, urlsplit=urlsplit,
            parse_qs=parse_qs, NativeUUID=UUID, same_origin=same_origin,
            ApiError=desktop_api.ApiError, Conflict=Conflict, CheckAccessDenied=CheckAccessDenied,
            terminal_check_context=terminal_check_context,
            post_action=desktop_api.post_action, operation_status=desktop_api.operation_status,
            confirm_checkout=confirm_checkout, confirm_return=confirm_return,
            urllib=urllib, recovery_rows=desktop_api.recovery_rows,
            native_context=lambda: (self.fixture.group, list(self.fixture.users.values())),
            get_profile=lambda _client, user: {'id': user}, system_status=lambda: {},
            invalidate_stock=lambda: None, reconnect_hardware=lambda *_: {'status': 'completed'},
            start_backup=lambda *_: {'status': 'started'},
            checkout_cart=None, shelf_checks=None, web_item_actions=None, label_layouts=None)
        self.ns['label_layouts'] = types.SimpleNamespace(
            reconcile_reviews=lambda *_: None, list=lambda *_: [])
        self.ns['TERMINAL_SHELF_CHECK_ROUTES'] = {'list', 'get', 'start'}
        self.ns['Homebox'] = self.native
        exec(compile(ast.Module(body=selected, type_ignores=[]), str(source), 'exec'), self.ns)

    def native(self, *_args, **_kwargs):
        client = fixtures.Native(self.fixture, 'alpha')
        client.tenant = self.fixture.group
        return client

    def request(self, path, data=None, cookie=None):
        request = Request(self.fixture, path, data, cookie)
        getattr(self.ns['Handler'], 'do_'+request.command)(request)
        return request

    def test_direct_manager_mutations_reject_anonymous_members_and_managers(self):
        # Restoring open admin access lets these requests reach service credentials.
        def unavailable(*_args, **_kwargs):
            raise OSError('Native service is unavailable in this access test')
        self.ns['Homebox'] = unavailable
        routes = (
            '/badge/issue', '/badge/revoke', '/badge/reprint', '/badge/replace', '/badge/print',
            '/condition', '/imports/upload', '/imports/map', '/imports/save', '/imports/create',
            '/imports/label', '/imports/get', '/imports/list', '/hardware/reconnect',
            '/workshop/save', '/workshop/move', '/workshop/shelf-order',
            '/label/preview', '/label/print', '/label/templates/save', '/label/templates/result',
            '/label/paper', '/equipment/code', '/categories/create', '/maintenance/complete',
            '/kit/save', '/backup/start', '/accounts/create', '/accounts/update',
            '/locations/create', '/catalog/create', '/map/room', '/map/object', '/map/remove',
            '/recovery/resolve',
            '/workshop/checks/start',
        )
        for cookie in (None, 'hb.auth.token=member; hb.auth.remember=true',
                       'hb.auth.token=alpha; hb.auth.remember=true'):
            for path in routes:
                with self.subTest(path=path, cookie=cookie):
                    self.assertEqual(self.request(path, {}, cookie).status, 403)

    def test_direct_manager_reads_reject_anonymous_and_signed_in_members(self):
        for cookie in (None, 'hb.auth.token=member; hb.auth.remember=true'):
            for path in ('/api/system', '/api/recovery', '/api/member-loans',
                         '/api/user-profile?id='+self.fixture.borrower,
                         '/api/badges', '/label/equipment', '/label/templates'):
                with self.subTest(path=path, cookie=cookie):
                    self.assertEqual(self.request(path, cookie=cookie).status, 403)

    def test_direct_shelf_check_reads_deny_before_loading_service_credentials(self):
        def unavailable(*_args, **_kwargs):
            raise OSError('Native service is unavailable in this access test')
        self.ns['Homebox'] = unavailable
        for path in ('/workshop/checks/list', '/workshop/checks/get'):
            with self.subTest(path=path):
                self.assertEqual(self.request(path).status, 403)

    def test_direct_badge_revocation_cannot_change_badge_or_member_session(self):
        fixture = self.fixture
        badge = fixture.badges.issue(fixture.group, fixture.borrower, [fixture.borrower])
        session = fixture.sessions.get('legacy')
        session.start(fixture.borrower)
        response = self.request('/badge/revoke', {'id': badge['id'], 'request_key': fixtures.ident()},
                                'hb.auth.token=member; hb.auth.remember=true')
        self.assertEqual(response.status, 403)
        self.assertEqual(fixture.badges.resolve(fixture.group, badge['code'], [fixture.borrower]), fixture.borrower)
        self.assertEqual(session.current(), fixture.borrower)

    def test_badge_member_checkout_and_return_still_use_transaction_handlers(self):
        fixture = self.fixture
        session = fixture.sessions.get('legacy')
        generation = session.start(fixture.borrower)
        session.record_scan(fixture.asset)
        context = {'session_generation': generation, 'session_instance': session.instance}
        checked_out = self.request('/checkout/confirm', dict(context,
            assets=[fixture.asset], request_key=fixtures.ident()))
        self.assertEqual(checked_out.status, 200, checked_out.result)
        self.assertEqual(fixture.ledger.custody(fixture.group)[0]['actor_id'], fixture.borrower)
        returned = self.request('/return/confirm', dict(context,
            targets=[{'entity_id': fixture.asset}], request_key=fixtures.ident()))
        self.assertEqual(returned.status, 200, returned.result)
        self.assertEqual(fixture.ledger.custody(fixture.group), [])

    def test_authenticated_manager_can_revoke_badge_through_workshop_api(self):
        fixture = self.fixture
        badge = fixture.badges.issue(fixture.group, fixture.borrower, [fixture.borrower])
        response = self.request('/workshop-api/badges/revoke',
            {'id': badge['id'], 'request_key': fixtures.ident()},
            'hb.auth.token=alpha; hb.auth.remember=true')
        self.assertEqual(response.status, 200, response.result)
        self.assertEqual(response.result['status'], 'completed')
        self.assertIsNone(fixture.badges.resolve(fixture.group, badge['code'], [fixture.borrower]))


if __name__ == '__main__':
    unittest.main()
