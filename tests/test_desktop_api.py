"""Isolated desktop auth, tenancy, provenance and uncertain-operation checks."""
import copy
import gc
import io
import json
import pathlib
import tempfile
import threading
import unittest
import urllib.error
from email.message import Message
from unittest.mock import patch
from uuid import uuid4

import desktop_api as api
from badges import Badges
from homebox import Homebox, session_cookie
from ledger import Ledger, Conflict
from native_jobs import NativeJobs
from item_notes import submit_note
from sessions import Sessions
from workshop import Workshop


def ident():
    return str(uuid4())


class Request:
    def __init__(self, path, method='GET', data=None, headers=None):
        self.path, self.command = '/workshop-api/'+path, method
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

    def entity(self, key):
        if key not in self.owner.entities or self.tenant != self.owner.group:
            raise urllib.error.HTTPError('native', 403, 'forbidden', {}, None)
        return copy.deepcopy(self.owner.entities[key])

    def entities(self, locations=False):
        return [copy.deepcopy(entity) for entity in self.owner.entities.values()
                if entity['entityType']['isLocation'] == locations] if self.tenant == self.owner.group else []

    def call(self, path, method='GET', data=None):
        self.owner.native_calls.append((self.token, self.tenant, path, method, copy.deepcopy(data)))
        if self.token not in self.owner.users:
            raise urllib.error.HTTPError('native', 401, 'expired', {}, None)
        if path == '/api/v1/users/self':
            return {'item': copy.deepcopy(self.owner.users[self.token])}
        if path == '/api/v1/groups':
            return {'id': self.tenant, 'name': 'Workshop' if self.tenant == self.owner.group else 'Other collection'}
        if path == '/api/v1/groups/members/administration':
            return {'canManage': True}
        if path == '/api/v1/groups/members':
            if method == 'POST':
                return {'id': data['requestKey'], 'name': data['name']}
            return [{'id': self.owner.manager, 'name': 'Workshop Admin', 'email': 'fixture@example.invalid'},
                    {'id': self.owner.borrower, 'name': 'Borrower', 'email': 'borrower@example.invalid'}]
        if path == '/api/v1/groups/invitations':
            if method == 'POST':
                invitation = {'id': ident(), 'token': 'private-invitation-token', **data}
                self.owner.invitations.append(invitation)
                if self.owner.fail_invite:
                    raise OSError('Injected lost response')
                return copy.deepcopy(invitation)
            return copy.deepcopy(self.owner.invitations)
        if path == '/api/v1/entity-types':
            return [{'id': self.owner.kind, 'isLocation': False, 'name': 'Equipment'}]
        if path.startswith('/api/v1/entities/') and path.endswith('/maintenance'):
            entity_id = path.split('/')[-2]
            self.entity(entity_id)
            if method == 'GET' and self.owner.fail_maintenance:
                raise OSError('Injected native maintenance read failure')
            entries = self.owner.maintenance.setdefault(entity_id, [])
            if method == 'POST':
                row = {'id': ident(), **copy.deepcopy(data)}
                entries.append(row)
                return {'item': copy.deepcopy(row)}
            return copy.deepcopy(entries)
        if path.startswith('/api/v1/entities/'):
            key = path.rsplit('/', 1)[1]
            entity = self.entity(key)
            if method == 'PATCH':
                self.owner.entities[key]['parent'] = {'id': data['parentId']}
                if self.owner.fail_patch:
                    raise OSError('Injected lost response after native write')
            if method == 'PUT':
                self.owner.entities[key] = dict(copy.deepcopy(data), parent={'id': data['parentId']})
            return self.entity(key)
        raise AssertionError('Unexpected native request: '+path)


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = pathlib.Path(self.temp.name)
        self.group, self.other_group, self.manager, self.borrower, self.asset, self.shelf, self.other_shelf, self.kind = [ident() for _ in range(8)]
        self.other_asset = ident()
        self.users = {
            'alpha': {'id': self.manager, 'name': 'Workshop Admin', 'email': 'fixture@example.invalid', 'defaultGroupId': self.group, 'groupIds': [self.group, self.other_group]},
            'member': {'id': self.borrower, 'name': 'Workshop Admin', 'email': 'member@example.invalid', 'defaultGroupId': self.group, 'groupIds': [self.group]},
        }
        self.entities = {
            self.asset: {'id': self.asset, 'name': 'Fixture drill', 'assetId': '001-001', 'quantity': 1, 'archived': False,
                         'entityType': {'id': self.kind, 'isLocation': False}, 'parent': {'id': self.shelf, 'name': 'Shelf'},
                         'fields': [{'name': 'Equipment condition', 'type': 'text', 'textValue': 'Ready'}], 'tags': []},
            self.other_asset: {'id': self.other_asset, 'name': 'Fixture lamp', 'assetId': '001-002', 'quantity': 1, 'archived': False,
                               'entityType': {'id': self.kind, 'isLocation': False}, 'parent': {'id': self.shelf, 'name': 'Shelf'},
                               'fields': [{'name': 'Equipment condition', 'type': 'text', 'textValue': 'Ready'}], 'tags': []},
            self.shelf: {'id': self.shelf, 'name': 'Shelf', 'archived': False, 'quantity': 0, 'entityType': {'id': self.kind, 'isLocation': True}, 'fields': []},
            self.other_shelf: {'id': self.other_shelf, 'name': 'Other shelf', 'archived': False, 'quantity': 0, 'entityType': {'id': self.kind, 'isLocation': True}, 'fields': []},
        }
        self.maintenance = {self.asset: []}
        self.fail_maintenance = False
        self.ledger = Ledger(self.root/'work/ops/ledger.db'); self.badges = Badges(self.ledger)
        self.sessions = Sessions(); self.jobs = NativeJobs(self.ledger)
        self.workshop = Workshop(self.root/'work/ops/workshop.db')
        (self.root/'work/ops/desktop-managers.json').write_text(json.dumps({'managers': [{'user_id': self.manager, 'group_id': self.group}]}))
        self.native_calls = []; self.invitations = []; self.fail_invite = self.fail_patch = False
        def factory(cookie, base=None):
            self.assertEqual(base, 'http://127.0.0.1:17747')
            token = cookie.split('hb.auth.token=', 1)[1].split(';', 1)[0]
            return Native(self, token)
        self.deps = {'root': self.root, 'lock': threading.Lock(), 'ledger': self.ledger, 'badges': self.badges,
                     'native_jobs': self.jobs, 'workshop': self.workshop, 'imports': None, 'sessions': self.sessions,
                     'homebox_factory': factory, 'native_base': 'http://127.0.0.1:17747'}
        self.identity = self.request('context').result['identity']

    def tearDown(self):
        gc.collect()  # Existing Workshop SQLite contexts close when collected.
        self.temp.cleanup()

    def request(self, path, data=None, headers=None, method=None):
        request = Request(path, method or ('GET' if data is None else 'POST'), data,
                          {'X-Workshop-Identity': getattr(self, 'identity', ''), **(headers or {})})
        self.assertTrue(api.handle(request, self.deps))
        return request

    def checkout(self):
        operation = self.ledger.begin(self.group, self.borrower, 'check_out', [self.asset], ident())
        self.ledger.complete(operation['id']); return operation

    def test_management_checkout_confirms_once_and_consumes_its_saved_cart(self):
        saved = self.request('checkout-cart', {'items': [self.asset], 'revision': 0, 'request_key': ident()})
        self.assertEqual(saved.status, 200)
        key = ident()
        data = {'request_key': key, 'assets': [self.asset], 'verified': [self.asset], 'kit_versions': {},
                'cart_revision': saved.result['revision'], 'cart_items': [self.asset], 'original_items': [self.asset]}
        first = self.request('checkout', data)
        replay = self.request('checkout', data)
        self.assertEqual(first.status, 200)
        self.assertEqual(first.result['status'], 'completed')
        self.assertEqual(first.result['id'], replay.result['id'])
        self.assertEqual(self.request('checkout-cart').result, {'revision': 2, 'items': []})
        self.assertEqual(len(self.ledger.custody(self.group)), 1)

    def test_regular_member_can_checkout_for_themselves(self):
        headers = {'Cookie': 'hb.auth.token=member; hb.auth.remember=true'}
        member = self.request('context', headers=headers).result
        headers['X-Workshop-Identity'] = member['identity']
        saved = self.request('checkout-cart', {'items': [self.asset], 'revision': 0, 'request_key': ident()}, headers)
        key = ident()
        result = self.request('checkout', {'request_key': key, 'assets': [self.asset], 'verified': [self.asset],
                                           'kit_versions': {}, 'cart_revision': saved.result['revision'],
                                           'cart_items': [self.asset]}, headers)
        self.assertEqual(result.status, 200)
        self.assertEqual(self.ledger.detail(self.group, result.result['id'])['actor_id'], self.borrower)
        self.assertEqual(self.ledger.custody(self.group)[0]['actor_id'], self.borrower)

    def test_stale_saved_cart_rejects_new_checkout_before_creating_operation(self):
        saved = self.request('checkout-cart', {'items': [self.asset], 'revision': 0, 'request_key': ident()})
        edited = self.request('checkout-cart', {'items': [], 'revision': saved.result['revision'], 'request_key': ident()})
        self.assertEqual(edited.status, 200)
        key = ident()
        stale = self.request('checkout', {'request_key': key, 'assets': [self.asset], 'verified': [self.asset],
                                          'kit_versions': {}, 'cart_revision': saved.result['revision'],
                                          'cart_items': [self.asset]})
        self.assertEqual(stale.status, 409)
        self.assertIsNone(self.ledger.request(self.group, key))
        self.assertEqual(self.ledger.custody(self.group), [])

    def test_hardware_reconnect_is_bound_to_a_current_manager_and_cannot_print(self):
        with patch('hardware.reconnect', return_value={'connected': True, 'steps': []}) as reconnect:
            self.assertEqual(self.request('hardware/reconnect', {'device': 'printer'}).status, 200)
            reconnect.assert_called_once_with('printer')
            reconnect.reset_mock()
            member = self.request('context', headers={'Cookie': 'hb.auth.token=member; hb.auth.remember=true'}).result
            denied = self.request('hardware/reconnect', {'device': 'printer'}, headers={'Cookie': 'hb.auth.token=member; hb.auth.remember=true', 'X-Workshop-Identity': member['identity']})
            self.assertEqual(denied.status, 403)
            self.assertEqual(self.request('hardware/reconnect', {'device': 'camera'}, headers={'X-Workshop-Identity': 'stale'}).status, 409)
            reconnect.assert_not_called()
        self.assertFalse(self.jobs.unresolved(self.group))

    def test_hardware_status_is_manager_only_and_returns_device_probes(self):
        printer = {'device': 'printer', 'connected': True, 'reason': 'ready', 'message': 'ready', 'steps': []}
        camera = {'device': 'camera', 'connected': False, 'reason': 'disconnected', 'message': 'missing', 'steps': ['connect it']}
        with patch('hardware.reconnect', return_value=printer) as reconnect, patch('hardware.camera_status', return_value=camera) as camera_status:
            response = self.request('hardware/status')
            self.assertEqual(response.status, 200)
            self.assertEqual(response.result, {'printer': printer, 'camera': camera})
            reconnect.assert_called_once_with('printer')
            camera_status.assert_called_once_with()
            reconnect.reset_mock(); camera_status.reset_mock()
            member = self.request('context', headers={'Cookie': 'hb.auth.token=member; hb.auth.remember=true'}).result
            denied = self.request('hardware/status', headers={'Cookie': 'hb.auth.token=member; hb.auth.remember=true', 'X-Workshop-Identity': member['identity']})
            self.assertEqual(denied.status, 403)
            reconnect.assert_not_called()
            camera_status.assert_not_called()

    def test_native_cookie_context_has_no_credentials_or_token(self):
        result = self.request('context').result
        self.assertTrue(result['manager']); self.assertEqual(result['user']['id'], self.manager)
        self.assertEqual(result['group']['id'], self.group)
        self.assertNotIn('alpha', json.dumps(result)); self.assertNotIn('password', json.dumps(result))
        self.assertTrue(all(call[0] == 'alpha' for call in self.native_calls))

    def test_local_backup_rejection_does_not_create_request_or_recovery_state(self):
        with patch.dict('os.environ', {'WORKSHOP_LOCAL_TEST': '1', 'WORKSHOP_ROOT': str(self.root)}):
            response = self.request('backup/start', {'request_key': ident()})
        self.assertEqual(response.status, 400)
        with self.ledger.connection() as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertNotIn('desktop_requests', tables)
        self.assertEqual(self.request('recovery').result, [])
        self.assertFalse((self.root/'work/backup-status.json').exists())

    def test_missing_expired_and_fake_session_cookie_do_not_authenticate(self):
        for cookie in (None, 'hb.auth.session=true', 'hb.auth.token=expired; hb.auth.remember=true'):
            self.assertEqual(self.request('equipment', headers={'Cookie': cookie}).status, 401)

    def test_member_with_admin_display_name_cannot_write_or_view_badges(self):
        headers = {'Cookie': 'hb.auth.token=member; hb.auth.remember=true'}
        context = self.request('context', headers=headers).result
        self.assertFalse(context['manager'])
        headers['X-Workshop-Identity'] = context['identity']
        self.assertEqual(self.request('equipment', headers=headers).status, 200)
        self.assertEqual(self.request('badges', headers=headers).status, 403)
        self.assertEqual(self.request('badges/issue', {'user_id': self.borrower, 'request_key': ident()}, headers).status, 403)
        self.assertEqual(self.badges.list(self.group), [])

    def test_checkout_cart_uses_signed_in_actor_and_rejects_stale_or_changed_replays(self):
        headers = {'Cookie': 'hb.auth.token=member; hb.auth.remember=true'}
        context = self.request('context', headers=headers).result
        headers['X-Workshop-Identity'] = context['identity']
        key = ident()
        payload = {'actor_id': self.manager, 'items': [self.asset], 'revision': 0, 'request_key': key}

        first = self.request('checkout-cart', payload, headers)

        self.assertEqual(first.status, 200)
        self.assertEqual(first.result, {'revision': 1, 'items': [self.asset]})
        self.assertEqual(self.request('checkout-cart', headers=headers).result, first.result)
        self.assertEqual(self.request('checkout-cart').result, {'revision': 0, 'items': []})
        self.assertEqual(self.request('checkout-cart', payload, headers).result, first.result)
        changed = self.request('checkout-cart', dict(payload, items=[self.other_asset]), headers)
        stale = self.request('checkout-cart', {'items': [self.other_asset], 'revision': 0, 'request_key': ident()}, headers)
        self.assertEqual(changed.status, 409)
        self.assertEqual(stale.status, 409)
        self.assertEqual(self.request('checkout-cart', headers=headers).result, first.result)
        self.assertEqual(self.ledger.custody(self.group), [])

    def test_checkout_availability_reports_unresolved_operations_for_desktop_cart(self):
        operation = self.ledger.begin(self.group, self.manager, 'check_out', [self.asset], ident())
        response = self.request('checkout-availability?ids='+self.asset)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.result, [{'id': self.asset, 'name': 'Fixture drill',
                                            'reason': 'Checkout operation requires recovery (pending)'}])

    def test_checkout_cart_cannot_select_another_collection(self):
        headers = {'Cookie': 'hb.auth.token=member; hb.auth.remember=true', 'X-Workshop-Group': self.other_group}
        self.assertEqual(self.request('checkout-cart', headers=headers).status, 403)

    def test_checkout_status_is_hidden_from_another_member(self):
        operation = self.ledger.begin(self.group, self.manager, 'check_out', [self.asset, self.other_asset], ident())
        self.ledger.complete(operation['id'])
        request_key = operation['request_key']
        owned = self.request('operation/status', {'request_key': request_key})
        self.assertEqual(owned.result, {'id': operation['id'], 'status': 'completed', 'action': 'check_out', 'count': 2})
        member = self.request('context', headers={'Cookie': 'hb.auth.token=member; hb.auth.remember=true'}).result
        headers = {'Cookie': 'hb.auth.token=member; hb.auth.remember=true', 'X-Workshop-Identity': member['identity']}

        response = self.request('operation/status', {'request_key': request_key}, headers)

        self.assertEqual(response.status, 200)
        self.assertEqual(response.result, {'status': 'not_started'})

    def test_collection_selection_is_member_scoped_and_manager_permission_scoped(self):
        self.assertEqual(self.request('context', headers={'X-Workshop-Group': ident()}).status, 403)
        ctx = self.request('context', headers={'X-Workshop-Group': self.other_group}).result
        self.assertEqual(ctx['group']['id'], self.other_group); self.assertFalse(ctx['manager'])
        self.assertNotEqual(ctx['identity'], self.identity)
        self.assertEqual(self.request('equipment', headers={'X-Workshop-Group': self.other_group}).result, [])

    def test_corrupt_manager_config_fails_closed(self):
        (self.root/'work/ops/desktop-managers.json').write_text('{broken')
        self.assertFalse(self.request('context').result['manager'])
        self.assertEqual(self.request('badges/issue', {'user_id': self.borrower, 'request_key': ident()}).status, 403)

    def test_management_grant_and_revoke_use_native_membership(self):
        cookie = {'Cookie': 'hb.auth.token=member; hb.auth.remember=true'}
        self.assertFalse(self.request('context', headers=cookie).result['manager'])
        data = {'user_id': self.borrower, 'enabled': True, 'request_key': ident()}
        self.assertEqual(self.request('permissions/set', data).status, 200)
        self.assertTrue(self.request('context', headers=cookie).result['manager'])
        self.assertTrue(next(m for m in self.request('people').result if m['id'] == self.borrower)['workshop_manager'])
        self.assertEqual(self.request('permissions/set', {'user_id': self.borrower, 'enabled': False, 'request_key': ident()}).status, 200)
        self.assertFalse(self.request('context', headers=cookie).result['manager'])
        self.assertEqual(self.request('permissions/set', {'user_id': ident(), 'enabled': True, 'request_key': ident()}).status, 400)
        self.assertEqual(self.request('permissions/set', {'user_id': self.manager, 'enabled': False, 'request_key': ident()}).status, 400)

    def test_workshop_admin_management_access_is_protected(self):
        path = self.root/'work/ops/desktop-managers.json'
        path.write_text(json.dumps({'owner_id': self.borrower, 'managers': [{'user_id': self.manager, 'group_id': self.group}]}))
        people = self.request('people').result
        self.assertTrue(next(member for member in people if member['id'] == self.borrower)['protected_owner'])
        self.assertFalse(next(member for member in people if member['id'] == self.manager)['protected_owner'])
        self.assertEqual(self.request('permissions/set', {'user_id': self.borrower, 'enabled': False, 'request_key': ident()}).status, 400)

    def test_csrf_bad_binding_account_drift_and_malformed_body_rejected(self):
        data = {'user_id': self.borrower, 'request_key': ident()}
        for headers, status in (({'Origin': 'https://evil.invalid'}, 403), ({'Origin': None}, 403),
                                ({'X-Workshop-Identity': 'old'}, 409), ({'Cookie': 'hb.auth.token=member; hb.auth.remember=true'}, 409),
                                ({'Content-Type': 'text/plain'}, 415), ({'Content-Length': '1000001'}, 413)):
            self.assertEqual(self.request('badges/issue', data, headers).status, status)
        self.assertEqual(self.badges.list(self.group), [])

    def test_entity_and_history_foreign_record_do_not_disclose_companion_data(self):
        self.assertEqual(self.request('entity?id='+ident()).status, 403)
        self.assertEqual(self.request('history?entity='+ident()).status, 403)

    @patch('desktop_api.badge_qr', return_value='data:image/png;base64,fixture')
    def test_badge_issue_retry_once_and_no_secret_in_journal(self, qr):
        data = {'user_id': self.borrower, 'request_key': ident()}
        first = self.request('badges/issue', data); second = self.request('badges/issue', data)
        self.assertEqual(first.status, 200); self.assertEqual(second.status, 200)
        self.assertEqual(first.result['id'], second.result['id']); self.assertIsNone(second.result['code'])
        self.assertEqual(len(self.badges.list(self.group)), 1)
        with self.ledger.connection() as db:
            persisted = '\n'.join(str(tuple(row)) for row in db.execute('SELECT * FROM desktop_requests'))
        self.assertNotIn(first.result['code'], persisted)
        changed = dict(data, user_id=self.manager)
        self.assertEqual(self.request('badges/issue', changed).status, 409)

    @patch('desktop_api.badge_qr', side_effect=OSError('Injected after issuance'))
    def test_unknown_badge_result_refuses_retry_and_exposes_recovery(self, qr):
        data = {'user_id': self.borrower, 'request_key': ident()}
        self.assertEqual(self.request('badges/issue', data).status, 503)
        self.assertEqual(self.request('badges/issue', data).status, 409)
        self.assertEqual(len(self.badges.list(self.group)), 1)
        self.assertEqual(self.request('operation/status', {'request_key': data['request_key']}).result['status'], 'review')
        recovery = self.request('recovery').result
        self.assertTrue(recovery[0]['desktop_job'])
        self.assertEqual(recovery[0]['intent'], {'user_id': self.borrower})
        self.assertTrue(recovery[0]['created_at'])
        payload = {'id': recovery[0]['id'], 'desktop_job': True, 'outcome': 'complete'}
        self.assertEqual(self.request('recovery/resolve', payload).status, 400)
        self.assertEqual(self.request('recovery/resolve', dict(payload, inspected=True)).status, 200)
        self.assertEqual(self.request('recovery').result, [])

    def test_request_journal_migrates_older_schema_and_preserves_safe_recovery_context(self):
        with self.ledger.connection() as db:
            db.execute('''CREATE TABLE desktop_requests(id TEXT PRIMARY KEY,group_id TEXT NOT NULL,
                actor_id TEXT NOT NULL,kind TEXT NOT NULL,request_key TEXT NOT NULL,digest TEXT NOT NULL,
                status TEXT NOT NULL,result TEXT,created_at TEXT NOT NULL,UNIQUE(group_id,request_key))''')
        api.journal_schema(self.ledger)
        with self.ledger.connection() as db:
            columns = {row['name'] for row in db.execute('PRAGMA table_info(desktop_requests)')}
        self.assertIn('intent', columns)
        data = {'filename': 'Fixture.csv', 'source': 'Fixture assets', 'csv': 'Private,CSV\nsecret,data',
                'code': 'private badge code', 'cookie': 'private cookie', 'request_key': ident()}
        self.assertEqual(api.safe_intent('imports/upload', data), {'filename': 'Fixture.csv', 'source': 'Fixture assets'})
        self.assertEqual(api.safe_intent('badges/issue', dict(data, user_id=self.borrower)), {'user_id': self.borrower})

    def test_logout_or_manager_removal_prevents_queued_write(self):
        del self.users['alpha']
        self.assertEqual(self.request('badges/issue', {'user_id': self.borrower, 'request_key': ident()}).status, 401)
        self.assertEqual(self.badges.list(self.group), [])

    def test_badge_revoke_ends_all_owner_sessions_and_preserves_other_person(self):
        badge = self.badges.issue(self.group, self.borrower, [self.borrower])
        own1, own2, other = [self.sessions.get(ident()) for _ in range(3)]
        own1.start(self.borrower); own2.start(self.borrower); other.start(self.manager)
        request = self.request('badges/revoke', {'id': badge['id'], 'request_key': ident()})
        self.assertEqual(request.status, 200)
        self.assertIsNone(own1.current()); self.assertIsNone(own2.current()); self.assertEqual(other.current(), self.manager)
        foreign = self.badges.issue(self.other_group, self.borrower, [self.borrower])
        self.assertEqual(self.request('badges/revoke', {'id': foreign['id'], 'request_key': ident()}).status, 404)

    def test_invitation_is_group_scoped_secret_once_no_automatic_retry(self):
        data = {'uses': 1, 'request_key': ident()}
        first = self.request('invitation/create', data); second = self.request('invitation/create', data)
        self.assertEqual(first.status, 200); self.assertIn('/?token=', first.result['join_url'])
        self.assertNotIn('token', second.result); self.assertEqual(len(self.invitations), 1)
        self.assertNotIn('token', self.request('invitations').result[0])
        self.fail_invite = True; other = {'request_key': ident()}
        self.assertEqual(self.request('invitation/create', other).status, 503)
        self.assertEqual(self.request('invitation/create', other).status, 409)
        self.assertEqual(len(self.invitations), 2)

    def test_admin_return_attributes_note_to_operator_and_preserves_borrower_durably(self):
        checkout = self.checkout(); before = copy.deepcopy(self.entities[self.asset])
        data = {'request_key': ident(), 'targets': [{'entity_id': self.asset, 'return_note': 'Was dirty; returned clean.'}]}
        first = self.request('return', data); second = self.request('return', data)
        self.assertEqual(first.status, 200); self.assertEqual(first.result, second.result)
        detail = self.ledger.detail(self.group, first.result['id'])
        self.assertEqual(detail['actor_id'], self.manager)
        self.assertEqual(detail['context']['desktop_previous_borrowers'][0]['user_id'], self.borrower)
        self.assertEqual(detail['context']['desktop_previous_borrowers'][0]['checkout_operation_id'], checkout['id'])
        self.assertEqual(self.entities[self.asset], before)
        history = self.request('history?entity='+self.asset).result[0]
        self.assertEqual(history['return_notes'][0]['author'], 'Workshop Admin')
        self.assertEqual(history['previous_borrowers'][0]['user_id'], self.borrower)

    def test_item_history_projects_verified_note_and_marks_native_edits_or_deletion(self):
        client = Native(self, 'alpha');client.tenant = self.group
        saved = submit_note(client, self.jobs, self.group, self.manager, ident(),
                            {'entity_id': self.asset, 'note': 'Check the battery.'}, 'Workshop Admin')
        row = next(item for item in self.request('history?entity='+self.asset).result if item['id'] == saved['id'])
        self.assertEqual((row['note_state'],row['note_text'],row['note_author']),('current','Check the battery.','Workshop Admin'))
        self.assertEqual((row['time_basis'],row['confirmed_at'] is not None),('confirmation',True))
        self.maintenance[self.asset][0]['description'] = 'Changed in C-Crate.'
        edited = next(item for item in self.request('history?entity='+self.asset).result if item['id'] == saved['id'])
        self.assertEqual((edited['note_state'],edited['note_text'],edited['note_current_text_attribution']),('edited','Changed in C-Crate.','unknown'))
        self.maintenance[self.asset].clear()
        deleted = next(item for item in self.request('history?entity='+self.asset).result if item['id'] == saved['id'])
        self.assertEqual(deleted['note_state'],'unavailable')
        self.assertNotIn('note_text',deleted)
        self.assertEqual((deleted['note_author_id'], deleted['note_author']),
                         (self.manager, 'Workshop Admin'))
        self.assertEqual(deleted['note_maintenance_id'], saved['maintenance_id'])
        self.fail_maintenance = True
        unavailable = next(item for item in self.request('history?entity='+self.asset).result if item['id'] == saved['id'])
        self.assertEqual(unavailable['note_state'], 'unavailable')
        self.assertEqual((unavailable['note_author_id'], unavailable['note_author']),
                         (self.manager, 'Workshop Admin'))
        self.assertEqual(unavailable['note_maintenance_id'], saved['maintenance_id'])
        self.assertNotIn('note_text', unavailable)

    def test_unknown_return_retains_custody_previous_borrower_and_current_manager_recovery_audit(self):
        self.checkout(); self.fail_patch = True
        data = {'request_key': ident(), 'targets': [{'entity_id': self.asset, 'destination_id': self.other_shelf}]}
        result = self.request('return', data)
        self.assertEqual(result.status, 409); self.assertEqual(len(self.ledger.custody(self.group)), 1)
        operation = self.ledger.unresolved()[0]
        self.assertEqual(self.ledger.detail(self.group, operation['id'])['context']['desktop_previous_borrowers'][0]['user_id'], self.borrower)
        self.assertEqual(self.request('return', data).status, 409)
        self.fail_patch = False
        recovered = self.request('recovery/resolve', {'id': operation['id'], 'outcome': 'complete'})
        self.assertEqual(recovered.status, 200); self.assertEqual(self.ledger.custody(self.group), [])
        events = self.ledger.detail(self.group, operation['id'])['events']
        self.assertEqual(next(event for event in events if event['kind'] == 'desktop_recovery_resolved')['detail']['actor_id'], self.manager)

    def test_recovery_native_job_audits_resolver_without_replacing_original_actor(self):
        job = self.jobs.prepare(self.group, self.borrower, 'create_location', ident(), {'name': 'Fixture'})
        def cancellation(module, function, *args):
            if (module, function) == ('stock', 'invalidate'):
                return
            client, jobs, group, key, outcome = args
            jobs.cancel(group, key); return {'id': key, 'status': 'cancelled'}
        with patch('desktop_api.native_op', side_effect=cancellation):
            result = self.request('recovery/resolve', {'id': job['id'], 'native_job': True, 'outcome': 'cancel'})
        self.assertEqual(result.status, 200); self.assertEqual(self.jobs.detail(self.group, job['id'])['actor_id'], self.borrower)
        with self.ledger.connection() as db:
            row = db.execute("SELECT detail FROM native_job_events WHERE job_id=? AND kind='desktop_recovery_resolved'", (job['id'],)).fetchone()
        self.assertEqual(json.loads(row['detail'])['actor_id'], self.manager)

    def test_item_note_recovery_uses_explicit_note_handler(self):
        job = self.jobs.prepare(self.group, self.borrower, 'add_note', ident(),
                                {'entity_id': self.asset, 'note': 'Fixture note'},
                                context={'entity_id': self.asset, 'author_name': 'Borrower'})
        calls = []
        def dispatch(module, function, *args, **kwargs):
            if (module, function) == ('stock', 'invalidate'):
                return None
            calls.append((module, function))
            self.assertEqual((module, function), ('item_notes', 'recover_note'))
            client, jobs, group, job_id, outcome = args
            self.assertEqual((group, job_id, outcome), (self.group, job['id'], 'cancel'))
            jobs.cancel(group, job_id)
            return {'id': job_id, 'status': 'cancelled'}
        with patch('desktop_api.native_op', side_effect=dispatch):
            result = self.request('recovery/resolve',
                                  {'id': job['id'], 'native_job': True, 'outcome': 'cancel'})
        self.assertEqual(result.status, 200)
        self.assertEqual(result.result['status'], 'cancelled')
        self.assertEqual(calls, [('item_notes', 'recover_note')])
        self.assertEqual(self.jobs.detail(self.group, job['id'])['actor_id'], self.borrower)

    def test_print_recovery_dispatch_injects_label_service(self):
        job = self.jobs.prepare(self.group, self.borrower, 'print_label', ident(), {'entity_id': self.asset, 'review_id': ident()})
        service = object(); self.deps['label_layouts'] = service
        def dispatch(module, function, *args, **kwargs):
            if (module, function) == ('stock', 'invalidate'): return None
            self.assertEqual((module, function), ('labels', 'recover_print'))
            self.assertIs(kwargs['layouts'], service)
            return {'id': args[3], 'status': 'cancelled'}
        with patch('desktop_api.native_op', side_effect=dispatch):
            result = self.request('recovery/resolve', {'id': job['id'], 'native_job': True, 'outcome': 'cancel'})
        self.assertEqual(result.status, 200)

    def test_workshop_save_has_durable_result_and_stale_revision_conflict(self):
        data = {'request_key': ident(), 'schema_version': 2, 'revision': 0, 'document': {'version': 2, 'rooms': []}}
        first = self.request('workshop/save', data); second = self.request('workshop/save', data)
        self.assertEqual(first.status, 200); self.assertEqual(first.result['revision'], second.result['revision'])
        self.assertEqual(self.request('operation/status', {'request_key': data['request_key']}).result['status'], 'completed')
        changed = copy.deepcopy(data); changed['document']['rooms'] = [{'id': ident(), 'location_id': None, 'name': 'Changed', 'width': 12, 'height': 10, 'unit': 'ft', 'approximate': False, 'objects': []}]
        self.assertEqual(self.request('workshop/save', changed).status, 409)
        old_schema = dict(data, schema_version=1)
        self.assertEqual(self.request('workshop/save', old_schema).status, 400)
        member = self.request('context', headers={'Cookie': 'hb.auth.token=member; hb.auth.remember=true'}).result
        self.assertEqual(self.request('operation/status', {'request_key': data['request_key']},
                                      {'Cookie': 'hb.auth.token=member; hb.auth.remember=true',
                                       'X-Workshop-Identity': member['identity']}).status, 409)
        stale = dict(data, request_key=ident())
        self.assertEqual(self.request('workshop/save', stale).status, 409)
        self.assertEqual(self.request('operation/status', {'request_key': stale['request_key']}).result['status'], 'not_started')
        self.assertEqual(self.request('recovery').result, [])
        self.assertEqual(self.workshop.get(self.group)['revision'], 1)
        refreshed = dict(data, request_key=ident(), revision=self.workshop.get(self.group)['revision'])
        self.assertEqual(self.request('workshop/save', refreshed).result['revision'], 2)
        # A later revision must not prevent replay of an old completed key.
        self.assertEqual(self.request('workshop/save', data).result['revision'], 1)

    def test_invalid_layout_is_rejected_before_journaling_a_write(self):
        data = {'request_key': ident(), 'schema_version': 2, 'revision': 0, 'document': {'version': 3, 'rooms': []}}
        self.assertEqual(self.request('workshop/save', data).status, 400)
        self.assertEqual(self.request('operation/status', {'request_key': data['request_key']}).result['status'], 'not_started')
        self.assertEqual(self.request('recovery').result, [])

    def test_invalid_name_does_not_start_profile_journal(self):
        create_key, update_key = ident(), ident()
        before_members = self.request('people').result
        create = self.request('users/create', {'name': '界' * 86, 'request_key': create_key})
        update = self.request('users/update', {
            'user_id': self.borrower, 'name': '界' * 86, 'email': '', 'avatar': '',
            'notes': '', 'updatedAt': 'fixture-version', 'request_key': update_key,
        })
        self.assertEqual(create.status, 400)
        self.assertEqual(update.status, 400)
        self.assertFalse([call for call in self.native_calls if call[3] in ('POST', 'PUT')])
        self.assertIsNone(api.request_row(self.ledger, self.group, create_key))
        self.assertIsNone(api.request_row(self.ledger, self.group, update_key))
        self.assertFalse([row for row in self.request('recovery').result if row['action'] in ('users/create', 'users/update')])
        self.assertEqual(self.request('people').result, before_members)

    def test_stale_storage_move_is_not_started_and_completed_replay_survives_later_changes(self):
        self.entities[self.shelf]['updatedAt'] = 'current'
        stale = {'id': self.shelf, 'parent_id': self.other_shelf, 'updated_at': 'old', 'request_key': ident()}
        self.assertEqual(self.request('workshop/move', stale).status, 409)
        self.assertEqual(self.request('operation/status', {'request_key': stale['request_key']}).result['status'], 'not_started')
        self.assertEqual(self.request('recovery').result, [])
        fresh = dict(stale, updated_at='current', request_key=ident())
        moved = self.request('workshop/move', fresh)
        self.assertEqual(moved.status, 200); self.assertEqual(moved.result['parent_id'], self.other_shelf)
        self.entities[self.shelf]['updatedAt'] = 'changed-again'
        self.assertEqual(self.request('workshop/move', fresh).result['parent_id'], self.other_shelf)

    def test_workshop_view_and_resolve_are_read_routes_with_bound_identity(self):
        self.entities[self.shelf].update(updatedAt='v1', fields=[{'name': 'Storage kind', 'type': 'text', 'textValue': 'Shelf'}])
        path = 'workshop/view?id='+self.shelf+'&nested=0'
        view = self.request(path)
        self.assertEqual(view.status, 200)
        self.assertEqual(view.result['selection']['target_id'], self.shelf)
        self.assertEqual(self.request(path, headers={'X-Workshop-Identity': 'stale'}).status, 409)
        for nested in ('true', '2', '01', '', '0&nested=1'):
            self.assertEqual(self.request('workshop/view?id='+self.shelf+'&nested='+nested).status, 400)
        self.assertEqual(self.request('workshop/view?id='+self.shelf+'&room_id='+ident()).status, 400)
        self.assertEqual(self.request('workshop/resolve', {'code': 'unknown'}).status, 200)
        self.assertIsNone(self.request('workshop/resolve', {'code': 'unknown'}).result['entity_id'])
        member_headers = {'Cookie': 'hb.auth.token=member; hb.auth.remember=true'}
        member_context = self.request('context', headers=member_headers).result
        member_headers['X-Workshop-Identity'] = member_context['identity']
        self.assertEqual(self.request(path, headers=member_headers).status, 200)
        self.assertEqual(self.request('workshop/resolve', {'code': 'unknown'}, member_headers).status, 200)
        self.assertFalse(any(call[3] != 'GET' for call in self.native_calls))

    def test_workshop_resolver_uses_server_owned_public_native_origin(self):
        with patch.object(api, 'trusted_native_origins', return_value=('http://pi.local:19333',)) as origins:
            raw = 'https://maker.example/code-42'
            duplicate = ident()
            self.entities[self.asset]['fields'] = [{'name':'Manufacturer QR code','type':'text','textValue':raw}]
            self.entities[duplicate] = dict(self.entities[self.asset], id=duplicate, name='Backup drill',
                fields=[{'name':'Manufacturer QR code','type':'text','textValue':raw}])
            headers = {'Cookie': 'hb.auth.token=member; hb.auth.remember=true'}
            context = self.request('context', headers=headers).result
            headers['X-Workshop-Identity'] = context['identity']
            cases = [
                ('http://evil.example:19333/item/'+self.asset, None),
                ('http://pi.local:19333/item/'+ident(), None),
                (raw, None), ('LAB:U:fixture-badge', None), ('unknown-code', None),
                ('http://pi.local:19333/item/'+self.asset, self.asset),
                ('/item/'+self.asset, self.asset),
            ]
            for code, expected in cases:
                response = self.request('workshop/resolve', {'code':code}, headers)
                self.assertEqual(response.status, 200, code)
                self.assertEqual(response.result['entity_id'], expected, code)
                if code == raw:
                    self.assertEqual({row['id'] for row in response.result['candidates']}, {self.asset, duplicate})
                    self.assertEqual(len({json.dumps(row['path'], sort_keys=True) for row in response.result['candidates']}), 2)
        self.assertEqual(response.status, 200)
        self.assertFalse(context['manager'])
        origins.assert_called_with('17745')
        self.assertFalse(any(call[3] != 'GET' for call in self.native_calls))

    def test_workshop_shelf_order_actor_is_authenticated_manager_and_recovery_is_inspection_only(self):
        observed = []
        data = {'entity_id': self.shelf, 'updated_at': 'v1', 'shelf_ids': [], 'request_key': ident()}
        native_operation = api.native_op
        with patch('desktop_api.submit_shelf_order', side_effect=lambda client, jobs, group, actor, key, payload: observed.append(actor) or {'id': ident(), 'status': 'completed'}), \
             patch('desktop_api.native_op', side_effect=lambda module, function, *args, **kwargs: None if (module, function) == ('stock', 'invalidate') else native_operation(module, function, *args, **kwargs)):
            self.assertEqual(self.request('workshop/shelf-order', data).status, 200)
            self.assertEqual(observed, [self.manager])
            self.assertEqual(self.request('workshop/shelf-order', data, {'X-Workshop-Identity': 'stale'}).status, 409)
            prepared = self.jobs.prepare(self.group, self.manager, 'workshop_shelf_order', ident(), {'entity_id': self.shelf})
            row = next(row for row in api.recovery_rows({'client': api.authenticate(Request('context'), self.deps)['client'], 'group': self.group}, self.deps)
                       if row.get('id') == prepared['id'])
            self.assertIn('Inspect the native rack shelf order', row['message'])
            self.assertEqual(self.request('recovery/resolve', {'id': prepared['id'], 'native_job': True, 'outcome': 'cancel'}).status, 200)
            self.assertEqual(self.request('operation/status', {'request_key': prepared['request_key']}).result['status'], 'cancelled')
            manager_file = self.root/'work/ops/desktop-managers.json'
            manager_file.write_text(json.dumps({'managers': []}))
            self.assertEqual(self.request('workshop/shelf-order', data).status, 403)
            manager_file.write_text(json.dumps({'managers': [{'user_id': self.manager, 'group_id': self.group}]}))
            class RevokeAfterLock:
                def __enter__(inner):
                    manager_file.write_text(json.dumps({'managers': []}))
                    return inner
                def __exit__(inner, *_): return False
            self.deps['lock'] = RevokeAfterLock()
            self.assertEqual(self.request('workshop/shelf-order', data).status, 403)
        self.assertEqual(observed, [self.manager])

    def test_native_print_recovery_shows_target_time_without_secret_hash(self):
        label = self.jobs.prepare(self.group, self.manager, 'print_label', ident(), {'entity_id': self.asset})
        badge = self.badges.issue(self.group, self.borrower, [self.borrower])
        person = self.jobs.prepare(self.group, self.manager, 'print_badge', ident(), {'badge_id': badge['id'], 'code_hash': 'private-code-hash'})
        self.jobs.sent(self.group, person['id']); self.jobs.bind(self.group, person['id'], self.borrower)
        rows = self.request('recovery').result
        by_id = {row['id']: row for row in rows}
        self.assertEqual(by_id[label['id']]['native_assets'][0]['name'], 'Fixture drill')
        self.assertEqual(by_id[label['id']]['native_assets'][0]['assetId'], '001-001')
        self.assertEqual(by_id[person['id']]['native_assets'][0]['name'], 'Badge for Borrower')
        self.assertTrue(all(row['created_at'] for row in rows))
        self.assertEqual(by_id[person['id']]['intent'], {'badge_id': badge['id']})
        self.assertNotIn('private-code-hash', json.dumps(rows))
        self.assertNotIn('code_hash', json.dumps(rows))

    def test_members_loans_use_completion_time_and_primary_photo(self):
        operation = self.checkout()
        image, thumbnail = ident(), ident()
        self.entities[self.asset]['attachments'] = [
            {'id': ident(), 'type': 'photo', 'primary': False},
            {'id': image, 'type': 'photo', 'primary': True, 'thumbnail': {'id': thumbnail}},
        ]
        detail = self.ledger.detail(self.group, operation['id'])
        completion = next(event['created_at'] for event in detail['events'] if event['kind'] == 'completed')
        result = self.request('loans')
        self.assertEqual(result.status, 200)
        self.assertEqual(result.result[0]['actor_id'], self.borrower)
        self.assertEqual(result.result[0]['checked_out_at'], completion)
        self.assertEqual(result.result[0]['imageId'], image)
        self.assertEqual(result.result[0]['thumbnailId'], thumbnail)
        self.entities.pop(self.asset)
        unavailable = self.request('loans').result[0]
        self.assertTrue(unavailable['unavailable'])
        self.assertEqual(unavailable['checked_out_at'], completion)
        self.assertNotIn('imageId', unavailable)

    def test_reprint_dispatch_does_not_send_a_badge_secret_to_the_browser(self):
        badge = self.badges.issue(self.group, self.borrower, [self.borrower])
        data = {'badge_id': badge['id'], 'request_key': ident()}
        with patch('desktop_api.native_op', return_value={'status': 'completed'}) as operation:
            result = self.request('badges/reprint', data)
        self.assertEqual(result.status, 200)
        self.assertEqual(operation.call_args.args[:2], ('labels', 'reprint_badge'))
        self.assertNotIn(badge['code'], json.dumps(result.result))
        member = {'Cookie': 'hb.auth.token=member; hb.auth.remember=true'}
        member['X-Workshop-Identity'] = self.request('context', headers=member).result['identity']
        self.assertEqual(self.request('badges/reprint', data, member).status, 403)

    @patch('desktop_api.badge_qr', return_value='fixture-qr')
    def test_badge_replacement_is_durable_and_revokes_the_old_session(self, qr):
        old = self.badges.issue(self.group, self.borrower, [self.borrower])
        session = self.sessions.get(ident()); session.start(self.borrower)
        data = {'badge_id': old['id'], 'request_key': ident()}
        first = self.request('badges/replace', data); replay = self.request('badges/replace', data)
        self.assertEqual(first.status, 200)
        self.assertEqual(replay.result['id'], first.result['id'])
        self.assertEqual(replay.result['code'], None)
        self.assertIsNone(session.current())
        self.assertIsNone(self.badges.resolve(self.group, old['code'], [self.borrower]))
        self.assertEqual(len(self.badges.list(self.group)), 2)
        self.assertEqual(self.badges.print_code(self.group, first.result['id'], [self.borrower]), first.result['code'])
        with self.ledger.connection() as db:
            rows = [dict(row) for row in db.execute('SELECT * FROM desktop_requests')]
        self.assertNotIn(first.result['code'], json.dumps(rows))
        self.assertEqual(api.safe_intent('badges/replace', data), {'badge_id': old['id']})

    def test_write_dispatch_uses_current_native_client_and_actual_manager(self):
        with patch('desktop_api.native_op', return_value={'status': 'completed'}) as operation:
            result = self.request('labels/print', {'entity_id': self.asset, 'request_key': ident()})
        self.assertEqual(result.status, 200)
        args = operation.call_args.args
        self.assertEqual(args[0:2], ('labels', 'print_label'))
        self.assertEqual(args[2].token, 'alpha'); self.assertEqual(args[4:6], (self.group, self.manager))

    def test_label_routes_derive_tenant_actor_and_keep_save_out_of_native_journal(self):
        class LabelService:
            def __init__(self):self.calls=[]
            def list(self,group):self.calls.append(('list',group));return [{'id':'starter:supvan:left'}]
            def save(self,group,actor,data):self.calls.append(('save',group,actor,data));return {'id':'saved','revision':1}
            def save_result(self,group,actor,key):self.calls.append(('result',group,actor,key));return {'id':'saved','revision':1}
            def preview(self,client,group,actor,data,deadline=None):self.calls.append(('preview',group,actor,data,deadline));return {'image':'fixture'}
        service=LabelService();self.deps['label_layouts']=service
        self.assertEqual(self.request('labels/templates').result[0]['id'],'starter:supvan:left')
        request_key=ident();saved=self.request('labels/templates/save',{'name':'My label','request_key':request_key})
        self.assertEqual(saved.result['id'],'saved')
        self.assertEqual(self.request('labels/templates/result',{'request_key':request_key}).result['revision'],1)
        entities=[self.asset,ident()]
        preview=self.request('labels/preview',{'mode':'item','entity_ids':entities,'template_id':'starter:supvan:left','template_revision':0})
        self.assertEqual(preview.status,200)
        self.assertEqual([c[0] for c in service.calls],['list','save','result','preview'])
        self.assertEqual(service.calls[1][1:3],(self.group,self.manager))
        self.assertEqual(service.calls[-1][1:3],(self.group,self.manager))
        with self.ledger.connection() as db:self.assertEqual(db.execute('SELECT count(*) FROM native_jobs').fetchone()[0],0)
        member=self.request('context',headers={'Cookie':'hb.auth.token=member; hb.auth.remember=true'}).result
        self.assertEqual(self.request('labels/templates',headers={'Cookie':'hb.auth.token=member; hb.auth.remember=true','X-Workshop-Identity':member['identity']}).status,403)

    def test_legacy_location_preview_uses_the_scoped_review_store(self):
        service=object();self.deps['label_layouts']=service
        with patch('desktop_api.native_op',return_value={'review_id':ident(),'image':'fixture'}) as operation:
            response=self.request('labels/preview',{'entity_id':self.shelf})
        self.assertEqual(response.status,200)
        self.assertEqual(operation.call_args.args[:2],('labels','preview'))
        self.assertEqual(operation.call_args.args[3],self.shelf)
        self.assertIs(operation.call_args.kwargs['layouts'],service)
        self.assertEqual(operation.call_args.kwargs['group'],self.group)
        self.assertEqual(operation.call_args.kwargs['actor'],self.manager)

    def test_legacy_location_print_requires_the_review_id(self):
        self.deps['label_layouts']=object()
        with patch('desktop_api.native_op') as operation:
            response=self.request('labels/print',{'entity_id':self.shelf,'request_key':ident()})
        self.assertEqual(response.status,400)
        operation.assert_not_called()

    def test_label_print_dispatch_passes_only_review_identity_to_service(self):
        self.deps['label_layouts']=object()
        review_id=ident()
        with patch('desktop_api.native_op',return_value={'id':ident(),'status':'completed'}) as operation:
            request=self.request('labels/print',{'entity_id':self.asset,'review_id':review_id,'request_key':ident()})
        self.assertEqual(request.status,200)
        self.assertEqual(operation.call_args.args[:2],('labels','print_label'))
        self.assertEqual(operation.call_args.args[4:6],(self.group,self.manager))
        self.assertEqual(operation.call_args.kwargs['review_id'],review_id)

    def test_import_job_uses_current_manager_without_replacing_batch_uploader(self):
        owner = self
        batch = {'id': ident(), 'actor': self.borrower, 'items': []}
        create_key = ident()
        class FixtureImports:
            def create(self, client, jobs, group, data):
                owner.assertEqual(client.token, 'alpha')
                job = jobs.prepare(group, batch['actor'], 'create_asset', create_key, {'name': 'Fixture'})
                return {'id': batch['id'], 'job_id': job['id']}
        self.deps['imports'] = FixtureImports()
        result = self.request('imports/create', {'id': batch['id'], 'index': 0})
        self.assertEqual(result.status, 200)
        self.assertEqual(self.jobs.detail(self.group, result.result['job_id'])['actor_id'], self.manager)
        self.assertEqual(batch['actor'], self.borrower)

    def test_import_label_uses_current_manager_and_layout_service(self):
        owner=self;batch_id=ident();layout_service=object()
        class FixtureImports:
            def label(self,client,jobs,group,data,*,actor=None,layouts=None):
                owner.assertEqual(client.token,'alpha');owner.assertEqual(group,owner.group)
                owner.assertEqual((actor,layouts),(owner.manager,layout_service))
                return {'id':batch_id,'uploader':owner.borrower,'label_status':'printed'}
        self.deps['imports']=FixtureImports();self.deps['label_layouts']=layout_service
        result=self.request('imports/label',{'id':batch_id,'index':0,'review_id':ident()})
        self.assertEqual(result.status,200);self.assertEqual(result.result['uploader'],self.borrower)

    def test_namespace_and_unknown_methods_never_fall_through_to_kiosk(self):
        request = Request('context'); request.path = '/api/session'
        self.assertFalse(api.handle(request, self.deps))
        self.assertEqual(self.request('context', method='DELETE').status, 405)
        self.assertEqual(self.request('unknown').status, 404)


class CookieAdapterTests(unittest.TestCase):
    def test_cookie_auth_never_reads_service_account_and_filters_other_cookies(self):
        with patch('pathlib.Path.read_text', side_effect=AssertionError('Must not read credentials')):
            client = Homebox.from_cookie('hb.auth.token=alpha; hb.auth.remember=true; unrelated=private')
        self.assertIsNone(client.token); self.assertNotIn('unrelated', client.cookie)
        with self.assertRaises(ValueError):
            session_cookie('hb.auth.session=true')
        with self.assertRaises(ValueError):
            session_cookie('hb.auth.token=alpha\r\nX-Extra: value; hb.auth.remember=true')

    def test_cookie_and_selected_tenant_sent_without_bearer_service_identity(self):
        client = Homebox.from_cookie('hb.auth.token=alpha; hb.auth.remember=true'); client.tenant = ident()
        captured = []
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return b'{"item":{}}'
        class Opener:
            def open(self, request, timeout=None):
                captured.append(request); return Response()
        client.opener = Opener(); client.call('/api/v1/users/self')
        self.assertEqual(captured[0].get_header('Cookie'), client.cookie)
        self.assertEqual(captured[0].get_header('X-tenant'), client.tenant)
        self.assertIsNone(captured[0].get_header('Authorization'))
        with self.assertRaises(ValueError):
            client.call('https://other.invalid/api/v1/users/self')


if __name__ == '__main__':
    unittest.main()
