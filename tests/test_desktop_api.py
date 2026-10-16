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
 =”ΩÌ¢Gß≤⁄Óù∆≠yﬁasset, duplicate})
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
