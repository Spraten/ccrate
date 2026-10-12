"""Terminal badge routes against a disposable companion root."""
import base64
import importlib
import io
import json
import os
import pathlib
import sys
import tempfile
import threading
import types
import unittest
from email.message import Message
from unittest.mock import patch
from uuid import uuid4

ROOT = pathlib.Path(__file__).resolve().parents[1]


class Request:
    def __init__(self, namespace, path, data):
        self.path, self.command = path, 'POST'
        self.headers = Message()
        raw = json.dumps(data).encode()
        for key, value in {
            'Origin': 'http://127.0.0.1:17749', 'Host': '127.0.0.1:17749',
            'Content-Length': str(len(raw)), 'Content-Type': 'application/json',
            'X-Homebox-Client': 'fixture-client',
        }.items():
            self.headers[key] = value
        self.rfile, self.wfile = io.BytesIO(raw), io.BytesIO()
        self.client_address = ('127.0.0.1', 1)
        self.sent_headers, self.status = {}, None
        self.ns = namespace

    @property
    def session(self):
        return self.ns['sessions'].get('fixture-client')

    def send_response(self, status): self.status = status
    def send_header(self, key, value): self.sent_headers[key] = value
    def end_headers(self): pass
    def send_error(self, status): self.status = status
    def reply_json(self, status, result): self.status, self.result = status, result


class GetRequest(Request):
    def __init__(self, namespace, path):
        self.path, self.command = path, 'GET'
        self.headers = Message()
        self.headers['Host'] = '127.0.0.1:17749'
        self.headers['X-Homebox-Client'] = 'fixture-client'
        self.rfile, self.wfile = io.BytesIO(), io.BytesIO()
        self.client_address = ('127.0.0.1', 1)
        self.sent_headers, self.status = {}, None
        self.ns = namespace


class TerminalMemberTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='terminal-member-fixture-')
        self.root = pathlib.Path(self.temp.name) / 'runtime'
        self.root.mkdir(mode=0o700)
        os.chmod(self.root, 0o700)
        self.token = uuid4().hex + uuid4().hex
        marker = self.root / '.fixture-process-token'
        marker.write_text(self.token)
        os.chmod(marker, 0o600)
        self.ready = self.root / 'fixture-ready.json'
        self.group, self.actor, self.member, self.outside = [str(uuid4()) for _ in range(4)]
        self.ns = self._load_server()

        owner = self
        class Client:
            tenant = None
            def __init__(client, *args, **kwargs): pass
            def call(client, path, *args, **kwargs):
                if path == '/api/v1/users/self':
                    return {'item': {'id': owner.actor, 'defaultGroupId': owner.group}}
                if path == '/api/v1/groups/members':
                    return [{'id': owner.actor, 'name': 'Fixture Admin'},
                            {'id': owner.member, 'name': 'Fixture Member'}]
                raise AssertionError('Unexpected fixture native call: '+path)
        self.ns['Homebox'] = Client
        self.ns['desktop_handle'] = lambda *_: False
        self.ns['same_origin'] = lambda origin, host: origin == 'http://'+host
        self.ns['native_context'] = lambda: (self.group, [
            {'id': self.actor, 'name': 'Fixture Admin'},
            {'id': self.member, 'name': 'Fixture Member'},
        ])
        self.ns['OPEN_ADMIN'] = True
        self.ns['lock'] = threading.RLock()
        self.ns['sessions'].get('fixture-client').start(self.member)

    def tearDown(self):
        self.temp.cleanup()

    def _load_server(self):
        source = (ROOT / 'deploy/kiosk-server.py').read_text(encoding='utf-8')
        source = source.replace(
            "ROOT=pathlib.Path(os.environ.get('WORKSHOP_ROOT','/home/user/Desktop/inventory-system')).resolve()",
            'ROOT=pathlib.Path('+repr(str(self.root))+').resolve()')
        source = source.split('_fixture_server=ThreadingHTTPServer', 1)[0]
        env = {
            'WORKSHOP_FIXTURE_PROCESS': '1', 'WORKSHOP_ROOT': str(self.root),
            'WORKSHOP_FIXTURE_TOKEN': self.token,
            'WORKSHOP_FIXTURE_READY_FILE': str(self.ready),
            'WORKSHOP_BIND_HOST': '127.0.0.1', 'WORKSHOP_COMPANION_PORT': '0',
            'WORKSHOP_NATIVE_BASE': 'http://127.0.0.1:49991',
            'WORKSHOP_CODE_ROOT': str(ROOT), 'HOMEBOX_UI_ROOT': str(ROOT/'kiosk'),
            'WORKSHOP_LABEL_ASSET_ROOT': str(self.root/'label-assets'),
        }
        (self.root/'label-assets').mkdir()
        (self.root/'work').mkdir(mode=0o700)
        fake_decoder = types.ModuleType('decode_codes')
        fake_decoder.decode_frame = lambda _frame: []
        fake_zxing = types.ModuleType('zxingcpp')
        fake_zxing.read_barcodes = lambda *_args, **_kwargs: []
        class FakeQR:
            def save(self, stream, format=None): stream.write(b'fixture-qr')
        fake_qrcode = types.ModuleType('qrcode')
        fake_qrcode.make = lambda _code: FakeQR()
        class FakeFernet:
            @staticmethod
            def generate_key(): return b'fixture-fernet-key'
            def __init__(self, _key): pass
            def encrypt(self, value): return base64.urlsafe_b64encode(value)
            def decrypt(self, value): return base64.urlsafe_b64decode(value)
        fake_cryptography = types.ModuleType('cryptography')
        fake_cryptography.__path__ = []
        fake_fernet = types.ModuleType('cryptography.fernet')
        fake_fernet.Fernet, fake_fernet.InvalidToken = FakeFernet, ValueError
        namespace = {'__name__': 'terminal_member_fixture', '__file__': str(ROOT/'deploy/kiosk-server.py')}
        blocked = {'printer', 'printing', 'label_output', 'hardware', 'gpio'}
        cached_physical = {name: module for name, module in list(sys.modules.items())
                           if any(part in blocked for part in name.split('.'))}
        for name in cached_physical:
            sys.modules.pop(name, None)
        try:
            with patch.dict(os.environ, env, clear=False), patch.dict('sys.modules', {
                'decode_codes': fake_decoder, 'zxingcpp': fake_zxing, 'qrcode': fake_qrcode,
                'cryptography': fake_cryptography, 'cryptography.fernet': fake_fernet,
            }):
                exec(compile(source, str(ROOT/'deploy/kiosk-server.py'), 'exec'), namespace)
        finally:
            sys.modules.update(cached_physical)
        self.assertEqual(namespace['ROOT'], self.root.resolve())
        self.assertTrue(namespace['FIXTURE_PROCESS'])
        return namespace

    def request(self, path, data):
        request = Request(self.ns, path, data)
        if path in ('/badge/issue', '/badge/replace'):
            with patch.dict(self.ns['post_action'].__globals__, {'badge_qr': lambda _code: 'fixture-qr'}):
                self.ns['Handler'].do_POST(request)
        else:
            self.ns['Handler'].do_POST(request)
        return request

    def get(self, path):
        request = GetRequest(self.ns, path)
        self.ns['Handler'].do_GET(request)
        return request

    def test_terminal_member_loans_reuses_native_projection(self):
        unavailable_id = str(uuid4())
        owner = self
        native_client = self.ns['Homebox']
        class LoanClient(native_client):
            def __init__(client, *args, **kwargs): client.tenant = owner.group
            def call(client, path, *args, **kwargs):
                if path == '/api/v1/users/self':
                    return {'item': {'id': owner.actor, 'defaultGroupId': owner.group}}
                if path == '/api/v1/groups/members':
                    return [{'id': owner.member, 'name': 'Fixture Member'}]
                if path == '/api/v1/entities/'+unavailable_id:
                    raise __import__('urllib.error').error.HTTPError(path, 404, 'missing', {}, None)
                if path.startswith('/api/v1/entities/'):
                    return {'item': {'id': path.rsplit('/', 1)[1], 'name': 'Fixture Tool', 'assetId': 'T-42',
                        'attachments': [{'id': 'a'*36, 'type': 'photo', 'primary': True,
                                         'thumbnail': {'id': 'b'*36}}]}}
                raise AssertionError('Unexpected fixture native call: '+path)
            def entity(client, entity_id):
                if entity_id == unavailable_id:
                    raise __import__('urllib.error').error.HTTPError(entity_id, 404, 'missing', {}, None)
                return {'id': entity_id, 'name': 'Fixture Tool', 'assetId': 'T-42',
                    'attachments': [{'id': 'a'*36, 'type': 'photo', 'primary': True,
                                     'thumbnail': {'id': 'b'*36}}]}
        self.ns['Homebox'] = LoanClient
        operation = str(uuid4())
        rows = [
            {'entity_id': str(uuid4()), 'actor_id': self.member, 'operation_id': operation, 'state': 'checked_out'},
            {'entity_id': unavailable_id, 'actor_id': self.member, 'operation_id': str(uuid4()), 'state': 'checked_out'},
            {'entity_id': str(uuid4()), 'actor_id': self.outside, 'operation_id': str(uuid4()), 'state': 'checked_out'},
        ]
        details = {operation: {'created_at': '2026-10-10T08:00:00Z', 'events': [
            {'kind': 'completed', 'created_at': '2026-10-10T08:05:00Z'}]}}
        class FixtureLedger:
            def custody(_ledger, group):
                assert group == owner.group
                return [dict(row) for row in rows if row['actor_id'] in (owner.member, owner.outside)]
            def detail(_ledger, group, operation_id): return details.get(operation_id, {'created_at': '2026-10-10T08:00:00Z', 'events': []})
        self.ns['ledger'] = FixtureLedger()
        from unittest.mock import patch
        api = self.ns['post_action'].__globals__
        expected = api['get_action']('loans', {}, {'client': LoanClient(), 'group': self.group,
            'actor': self.actor, 'manager': True, 'collection': self.group, 'user': {'id': self.actor}, 'identity': {}}, self.ns)
        with patch.dict(api, {'get_action': api['get_action']}):
            response = self.get('/api/member-loans')
        self.assertEqual(response.status, 200)
        self.assertEqual(response.result, expected)
        member_rows = [row for row in response.result if row['actor_id'] == self.member]
        self.assertEqual(len(member_rows), 2)
        available = next(row for row in member_rows if row['entity_name'] == 'Fixture Tool')
        self.assertEqual(available['checked_out_at'], '2026-10-10T08:05:00Z')
        self.assertEqual(available['imageId'], 'a'*36)
        self.assertEqual(available['thumbnailId'], 'b'*36)
        self.assertTrue(next(row for row in member_rows if row['entity_id'] == unavailable_id)['unavailable'])

    def test_terminal_member_loans_respects_setup_guard(self):
        self.ns['OPEN_ADMIN'] = False
        response = self.get('/api/member-loans')
        self.assertEqual(response.status, 403)

    def issue_payload(self, user=None, key=None):
        return {'user_id': user or self.member, 'request_key': key or str(uuid4())}

    def test_terminal_issue_is_journaled_and_secret_free(self):
        payload = self.issue_payload()
        first = self.request('/badge/issue', payload)
        replay = self.request('/badge/issue', payload)
        self.assertEqual(first.status, 200)
        self.assertEqual(replay.status, 200)
        self.assertEqual(len(self.ns['badges'].list(self.group)), 1)
        self.assertIsNone(replay.result['code'])
        row = self.ns['request_row'](self.ns['ledger'], self.group, payload['request_key'])
        self.assertEqual(row['status'], 'completed')
        self.assertNotIn(first.result['code'], str(row))
        for path in self.ns['ledger'].path.parent.glob('ledger.db*'):
            self.assertNotIn(first.result['code'].encode(), path.read_bytes())

    def test_terminal_issue_uncertain_result_refuses_repeat(self):
        payload = self.issue_payload()
        issue = self.ns['badges'].issue
        def issue_then_fail(*args):
            result = issue(*args)
            raise OSError('injected after badge row')
        with patch.object(self.ns['badges'], 'issue', side_effect=issue_then_fail):
            first = self.request('/badge/issue', payload)
        retry = self.request('/badge/issue', payload)
        self.assertEqual(first.status, 503)
        self.assertEqual(retry.status, 409)
        self.assertEqual(len(self.ns['badges'].list(self.group)), 1)
        status = self.ns['operation_status'](
            {'client': None, 'group': self.group, 'actor': self.actor, 'manager': True},
            {'ledger': self.ns['ledger'], 'native_jobs': self.ns['native_jobs']},
            {'request_key': payload['request_key']})
        self.assertEqual(status['status'], 'review')

    def test_terminal_badge_routes_preserve_membership_and_request_binding(self):
        key = str(uuid4())
        missing = self.request('/badge/issue', {'user_id': self.member})
        foreign = self.request('/badge/issue', self.issue_payload(self.outside))
        first = self.request('/badge/issue', self.issue_payload(key=key))
        changed = self.request('/badge/issue', {'user_id': self.actor, 'request_key': key})
        self.assertEqual(missing.status, 400)
        self.assertEqual(foreign.status, 400)
        self.assertEqual(first.status, 200)
        self.assertEqual(changed.status, 409)
        self.assertEqual(len(self.ns['badges'].list(self.group)), 1)
        revoke_key = str(uuid4())
        active_session = self.ns['sessions'].get('active-member-session')
        active_session.start(self.member)
        revoked = self.request('/badge/revoke', {'id': first.result['id'], 'request_key': revoke_key})
        replay = self.request('/badge/revoke', {'id': first.result['id'], 'request_key': revoke_key})
        second = self.request('/badge/issue', self.issue_payload())
        changed_revoke = self.request('/badge/revoke', {'id': second.result['id'], 'request_key': revoke_key})
        self.assertEqual(revoked.status, 200)
        self.assertTrue(revoked.result['revoked'])
        self.assertEqual(replay.status, 200)
        self.assertEqual(changed_revoke.status, 409)
        self.assertIsNone(active_session.current())

    def test_terminal_setup_guard_denies_issue_and_revoke(self):
        self.ns['OPEN_ADMIN'] = False
        issue = self.request('/badge/issue', self.issue_payload())
        revoke = self.request('/badge/revoke', {'id': str(uuid4()), 'request_key': str(uuid4())})
        self.assertEqual(issue.status, 403)
        self.assertEqual(revoke.status, 403)
        self.assertEqual(self.ns['badges'].list(self.group), [])

    def test_terminal_reprint_and_replace_dispatch_existing_helpers(self):
        badge = self.ns['badges'].issue(self.group, self.member, [self.member])
        session = self.ns['sessions'].get('fixture-client')
        session.start(self.member)
        calls = []
        def dispatch(module, function, *args, **kwargs):
            calls.append((module, function, args, kwargs))
            return {'id': 'fixture-print-job', 'status': 'completed'}
        reprint_payload = {'badge_id': badge['id'], 'request_key': str(uuid4())}
        with patch.dict(self.ns['post_action'].__globals__, {'native_op': dispatch}):
            reprinted = self.request('/badge/reprint', reprint_payload)
            replayed_reprint = self.request('/badge/reprint', reprint_payload)
        self.assertEqual(reprinted.status, 200)
        self.assertEqual(replayed_reprint.status, 200)
        self.assertEqual(len(calls), 2)
        self.assertEqual(replayed_reprint.result['status'], 'completed')
        self.assertEqual(calls[0][:2], ('labels', 'reprint_badge'))
        self.assertEqual(calls[0][2][3:], (self.group, self.actor, reprint_payload['request_key'], badge['id']))
        self.assertEqual(session.current(), self.member)

        with self.ns['ledger'].transaction() as db:
            db.execute('DELETE FROM badge_print_secrets WHERE badge_id=?', (badge['id'],))
        legacy = next(row for row in self.ns['badges'].list(self.group) if row['id'] == badge['id'])
        self.assertFalse(legacy['reprintable'])
        session.start(self.member)
        replace_payload = {'badge_id': badge['id'], 'request_key': str(uuid4())}
        replaced = self.request('/badge/replace', replace_payload)
        self.assertEqual(replaced.status, 200)
        self.assertEqual(replaced.result['user_id'], self.member)
        self.assertEqual(replaced.result['qr'], 'fixture-qr')
        self.assertIsNone(session.current())
        rows = self.ns['badges'].list(self.group)
        self.assertTrue(next(row for row in rows if row['id'] == badge['id'])['revoked'])
        replacement = next(row for row in rows if row['id'] == replaced.result['id'])
        self.assertEqual(replacement['user_id'], self.member)
        self.assertTrue(replacement['reprintable'])
        journal = self.ns['request_row'](self.ns['ledger'], self.group, replace_payload['request_key'])
        self.assertEqual(journal['status'], 'completed')
        self.assertNotIn(replaced.result['code'], str(journal))
        self.assertNotIn(replaced.result['code'], str(journal['intent']))

    def test_terminal_reprint_recovery_ack_replay_uses_one_native_journal(self):
        labels = importlib.import_module('labels')
        badge = self.ns['badges'].issue(self.group, self.member, [self.member])
        payload = {'badge_id': badge['id'], 'request_key': str(uuid4())}
        outputs = []

        class Raster:
            width, height = 320, 224
            def tobytes(self): return b'fixture-raster'

        def adapter(args, **kwargs):
            if args[1] == 'print':
                outputs.append('attempted')
                raise OSError('fixture output failed after NativeJobs sent')
            raise AssertionError('The probe adapter should be bypassed by labels.probe')

        with (patch.object(labels, 'probe', return_value={'width_mm': 40, 'height_mm': 30}),
              patch.object(labels, 'render', return_value=(Raster(), None)),
              patch.object(labels, 'printer_path', return_value='fixture-printer'),
              patch.object(labels, 'adapter', return_value='fixture-adapter'),
              patch.object(labels.subprocess, 'run', side_effect=adapter)):
            failed = self.request('/badge/reprint', payload)
            # Output failed after NativeJobs.sent, so desktop_api maps the
            # uncertain print to Conflict/409 (needs review), not bad input.
            self.assertEqual(failed.status, 409)
            job = self.ns['native_jobs'].existing(self.group, self.actor, 'print_badge',
                payload['request_key'], {'badge_id': badge['id'], 'code_hash': __import__('hashlib').sha256(
                    self.ns['badges'].print_code(self.group, badge['id'], [self.member]).encode()).hexdigest()})
            self.assertIsNotNone(job)
            self.assertEqual(job['status'], 'review')
            self.assertEqual(len(outputs), 1)
            with patch.dict('sys.modules', {'labels': labels}), patch.dict(self.ns, {'recover_print': labels.recover_print}):
                resolved = self.request('/recovery/resolve', {
                    'id': job['id'], 'native_job': True, 'outcome': 'complete',
                })
            self.assertEqual(resolved.status, 200)
            self.assertEqual(resolved.result['status'], 'completed')
            status = self.request('/operation/status', {'request_key': payload['request_key']})
            self.assertEqual(status.result['status'], 'completed')
            replay = self.request('/badge/reprint', payload)
            self.assertEqual(replay.status, 200)
            self.assertEqual(replay.result['status'], 'completed')
            self.assertEqual(len(outputs), 1)
            self.assertEqual(self.ns['native_jobs'].unresolved(self.group), [])
            self.assertIsNone(self.ns['request_row'](self.ns['ledger'], self.group, payload['request_key']))

    def test_terminal_setup_guard_denies_new_routes(self):
        self.ns['OPEN_ADMIN'] = False
        reprint = self.request('/badge/reprint', {'badge_id': str(uuid4()), 'request_key': str(uuid4())})
        replace = self.request('/badge/replace', {'badge_id': str(uuid4()), 'request_key': str(uuid4())})
        self.assertEqual(reprint.status, 403)
        self.assertEqual(replace.status, 403)
        self.assertEqual(self.ns['badges'].list(self.group), [])


if __name__ == '__main__':
    unittest.main()
