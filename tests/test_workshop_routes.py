"""Terminal workshop routes loaded without running kiosk-server startup code."""
import ast
import io
import json
import os
import pathlib
import tempfile
import threading
import types
import urllib.error
import urllib.request
import unittest
from contextlib import contextmanager
from email.message import Message
from unittest.mock import patch
from uuid import uuid4

from ledger import Ledger
from native_jobs import NativeJobs
from workshop import Workshop
from shelf_checks import ShelfChecks
from ledger import Conflict
import desktop_api


def uid():
    return str(uuid4())


class ResponseBase:
    def send_response(self, status): self.status = status
    def send_header(self, name, value): self.sent_headers[name] = value
    def end_headers(self): pass
    def send_error(self, status): self.status = status


class NativeFixture:
    def __init__(self, owner):
        self.owner, self.tenant, self.base, self.token = owner, None, 'http://127.0.0.1:17745', 'fixture-token'

    def call(self, path, method='GET', data=None):
        if path == '/api/v1/users/self': return {'item': {'id': self.owner.admin, 'defaultGroupId': self.owner.group}}
        if path.startswith('/api/v1/entities/') and method == 'PUT':
            key = path.rsplit('/', 1)[1]
            self.owner.nodes[key] = dict(data, parent=self.owner.nodes[key].get('parent'))
            self.owner.put_count += 1
            if self.owner.fail_after_put: raise OSError('Simulated lost response after native update')
            return {'item': self.owner.nodes[key]}
        raise AssertionError('Unexpected native call: '+path)

    def entity(self, key):
        if key not in self.owner.nodes:
            raise urllib.error.HTTPError('fixture', 403, 'foreign entity', {}, None)
        return dict(self.owner.nodes[key])
    def entities(self, locations=False):
        return [dict(row) for row in self.owner.nodes.values() if row['entityType']['isLocation'] is locations]


class SessionFixture:
    instance = 'fixture-session'
    def __init__(self, actor): self.actor = actor
    def current(self, activity=False): return self.actor


class WorkshopRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.handler_source = None
        self.group, self.admin, self.member, self.rack, self.shelf, self.tool, kind = [uid() for _ in range(7)]
        self.photo = uid()
        self.nodes = {
            self.rack: {'id': self.rack, 'name': 'Rack', 'updatedAt': 'rack-v1', 'entityType': {'id': kind, 'isLocation': True, 'name': 'Location'}, 'parent': None, 'archived': False, 'fields': [{'name':'Storage kind','type':'text','textValue':'Rack'}], 'attachments': [{'id':self.photo,'title':'Rack photo','type':'photo','primary':True,'url':'/private/photo'}]},
            self.shelf: {'id': self.shelf, 'name': 'Shelf', 'updatedAt': 'shelf-v1', 'entityType': {'id': kind, 'isLocation': True, 'name': 'Location'}, 'parent': {'id': self.rack}, 'archived': False, 'fields': [{'name':'Storage kind','type':'text','textValue':'Shelf'}], 'attachments': []},
            self.tool: {'id': self.tool, 'name': 'Drill', 'updatedAt': 'tool-v1', 'entityType': {'id': kind, 'isLocation': False, 'name': 'Equipment'}, 'parent': {'id': self.shelf}, 'archived': False, 'fields': [], 'attachments': []},
        }
        self.put_count = 0
        self.fail_after_put = False
        self.file_requests = []
        self.native = NativeFixture(self)
        self.ledger = Ledger(self.root/'work/ops/ledger.db')
        self.jobs = NativeJobs(self.ledger)
        self.shelf_checks = ShelfChecks(self.ledger)
        self.workshop = Workshop(self.root/'work/ops/workshop.db')
        self.module = self._load_handler()

    def tearDown(self): self.temp.cleanup()

    def _load_handler(self):
        source = self.handler_source or pathlib.Path(__file__).resolve().parents[1]/'deploy/kiosk-server.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        handler = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Handler')
        namespace = {
            '__name__': 'isolated_kiosk_handler', 'BaseHTTPRequestHandler': ResponseBase,
            'ROOT': self.root, 'desktop_handle': lambda *_: False, 'sessions': type('Sessions', (), {'get': lambda _s, _c: SessionFixture(self.member)})(),
            'same_origin': lambda *_: True, 'OPEN_ADMIN': True, 'lock': threading.Lock(),
            'Homebox': lambda *_: self.native, 'workshop': self.workshop, 'ledger': self.ledger,
            'shelf_checks': self.shelf_checks,
            'native_jobs': self.jobs, 'badges': None, 'imports': None, 'label_layouts': None,
            'LABEL_ASSET_ROOT': self.root, 'session': SessionFixture(self.member),
            'ApiError': desktop_api.ApiError,
            'os': os,
            'urlsplit': __import__('urllib.parse', fromlist=['urlsplit']).urlsplit,
            'parse_qs': __import__('urllib.parse', fromlist=['parse_qs']).parse_qs,
            'NativeUUID': __import__('uuid').UUID,
            'urllib': types.SimpleNamespace(request=types.SimpleNamespace(
                Request=lambda url, headers=None: types.SimpleNamespace(full_url=url, headers=headers),
                HTTPRedirectHandler=urllib.request.HTTPRedirectHandler,
                build_opener=lambda *_: types.SimpleNamespace(open=self._open_attachment)),
                error=urllib.error),
            'json': json, 'io': io, 'threading': threading,
            'native_context': lambda: (self.group, []),
            'invalidate_stock': lambda: None, 'Conflict': Conflict,
            'submit_shelf_order': __import__('workshop').submit_shelf_order,
            'recover_shelf_order': __import__('workshop').recover_shelf_order,
            'recover_print': lambda *_args, **_kwargs: None,
            'resolve_workshop_code': __import__('workshop_views').resolve_workshop_code,
            'trusted_native_origins': lambda port: ('http://pi.local:19333',) if str(port) == '19333' else (),
            'PUBLIC_NATIVE_PORT': '19333',
            'build_view': __import__('workshop_views').build_view,
            'operation_status': __import__('desktop_api').operation_status,
            'once': __import__('desktop_api').once,
            'request_row': __import__('desktop_api').request_row,
            'recovery_rows': __import__('desktop_api').recovery_rows,
            'post_action': __import__('desktop_api').post_action,
        }
        exec(compile(ast.Module(body=[handler], type_ignores=[]), str(source), 'exec'), namespace)
        return namespace

    def request(self, path, method='GET', data=None, headers=None):
        handler = self.module['Handler'].__new__(self.module['Handler'])
        handler.path, handler.command = path, method
        handler.client_address = ('127.0.0.1', 1)
        handler.sent_headers = {}
        handler.headers = Message()
        body = json.dumps(data or {}).encode()
        handler.rfile = io.BytesIO(body)
        handler.wfile = io.BytesIO()
        handler.headers['Host'] = '127.0.0.1:17749'
        for name, value in (headers or {}).items(): handler.headers[name] = value
        if method == 'POST':
            handler.headers['Origin'] = 'http://127.0.0.1:17749'
            handler.headers['Content-Length'] = str(len(body))
        getattr(handler, 'do_'+method)()
        self.last_handler = handler
        if hasattr(handler, 'result'): return handler.status, handler.result
        try: return handler.status, json.loads(handler.wfile.getvalue())
        except (ValueError, TypeError): return handler.status, None

    def workshop_headers(self, group=None, actor=None):
        return {'X-Workshop-Group': group or self.group,
                'X-Workshop-Actor': actor or self.admin}

    def test_workshop_context_is_returned_as_canonical_service_provenance(self):
        status, value = self.request('/workshop/get', 'POST', {})
        self.assertEqual(status, 200)
        self.assertEqual(value['workshop_context'], {'group_id': self.group, 'actor_id': self.admin})
        self.assertEqual(set(value['workshop_context']), {'group_id', 'actor_id'})

    def test_save_context_is_checked_before_any_plan_or_journal_write(self):
        request = {'schema_version': 2, 'revision': 0, 'request_key': uid(),
                   'document': {'version': 2, 'rooms': []}}
        status, _ = self.request('/workshop/save', 'POST', request)
        self.assertEqual(status, 409)
        self.assertEqual(self.workshop.get(self.group)['revision'], 0)
        self.assertIsNone(self.ledger.request(self.group, request['request_key']))
        self.assertIsNone(self.workshop.save_binding(self.group, request['request_key']))
        self.assertEqual(self.request('/workshop/save', 'POST', request,
                                      {'X-Workshop-Group': self.group})[0], 409)
        self.assertEqual(self.request('/workshop/save', 'POST', request,
                                      {'X-Workshop-Group': 'bad', 'X-Workshop-Actor': self.admin})[0], 409)

    def test_same_revision_collection_or_actor_change_rejects_original_context_before_writes(self):
        request = {'schema_version': 2, 'revision': 0, 'request_key': uid(),
                   'document': {'version': 2, 'rooms': []}}
        headers = self.workshop_headers()
        self.assertEqual(self.request('/workshop/save', 'POST', request, headers)[0], 200)
        self.group = uid()
        status, _ = self.request('/workshop/save', 'POST', request, headers)
        self.assertEqual(status, 409)
        self.assertEqual(self.workshop.get(self.group)['revision'], 0)
        self.assertIsNone(self.ledger.request(self.group, request['request_key']))
        self.assertIsNone(self.workshop.save_binding(self.group, request['request_key']))
        self.group = headers['X-Workshop-Group']
        self.admin = uid()
        status, _ = self.request('/workshop/save', 'POST', dict(request, request_key=uid()), headers)
        self.assertEqual(status, 409)
        self.assertEqual(self.workshop.get(self.group)['revision'], 1)

    def test_workshop_status_requires_original_context_before_reconciliation(self):
        request = {'schema_version': 2, 'revision': 0, 'request_key': uid(),
                   'document': {'version': 2, 'rooms': []}}
        headers = self.workshop_headers()
        original = self.ledger.transaction
        calls = [0]
        @contextmanager
        def fail_completion(*args, **kwargs):
            calls[0] += 1
            if calls[0] == 4: raise OSError('injected generic journal completion failure')
            with original(*args, **kwargs) as db: yield db
        self.ledger.transaction = fail_completion
        self.assertEqual(self.request('/workshop/save', 'POST', request, headers)[0], 503)
        self.ledger.transaction = original
        with self.ledger.connection() as db:
            before = db.execute('SELECT status FROM desktop_requests WHERE group_id=? AND request_key=?',
                (self.group, request['request_key'])).fetchone()[0]
        self.group = uid()
        status, _ = self.request('/operation/status', 'POST', {'request_key': request['request_key']}, headers)
        self.assertEqual(status, 409)
        self.assertEqual(self.workshop.get(headers['X-Workshop-Group'])['revision'], 1)
        with self.ledger.connection() as db:
            row = db.execute('SELECT status FROM desktop_requests WHERE group_id=? AND request_key=?',
                (headers['X-Workshop-Group'], request['request_key'])).fetchone()
        self.assertEqual(row[0], before)

    def test_unscoped_non_workshop_status_family_stays_supported(self):
        key = uid()
        op = self.ledger.begin(self.group, self.member, 'check_out', [self.tool], key)
        status, value = self.request('/operation/status', 'POST', {'request_key': key})
        self.assertEqual(status, 200)
        self.assertEqual(value['action'], 'check_out')
        self.assertEqual(value['id'], op['id'])

    def _open_attachment(self, request, timeout):
        self.file_requests.append(request)
        class Headers:
            def get_content_type(self): return 'image/jpeg'
        class Response:
            headers = Headers()
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self, _): return b'fixture-image'
        return Response()

    def test_read_route_parity_and_order_recovery_dispatch(self):
        status, view = self.request('/workshop/view', 'POST', {'entity_id': self.rack, 'include_nested': False})
        self.assertEqual(status, 200)
        self.assertEqual(view['selection']['target_id'], self.rack)
        self.assertEqual([photo['id'] for photo in view['photos']], [self.photo])
        self.assertNotIn('/private/photo', json.dumps(view))
        desktop_view = desktop_api.get_action('workshop/view', {'id': [self.rack], 'nested': ['0']},
            {'client': self.native, 'group': self.group, 'manager': True},
            {'workshop': self.workshop, 'ledger': self.ledger})
        self.assertEqual(desktop_view['selection'], view['selection'])
        self.assertEqual(self.request('/workshop/view', 'POST', {'entity_id': self.rack, 'include_nested': 'false'})[0], 400)
        self.assertEqual(self.request('/workshop/view', 'POST', {'entity_id': self.rack})[0], 400)
        self.assertEqual(self.request('/workshop/view', 'POST', {'entity_id': self.rack, 'include_nested': False, 'room_id': uid()})[0], 400)
        status, resolved = self.request('/workshop/resolve', 'POST', {'code': 'unrecognized'})
        self.assertEqual(status, 200)
        self.assertIsNone(resolved['entity_id'])

    def test_terminal_room_save_and_status_use_service_actor_and_admin_gate(self):
        request = {'schema_version': 2, 'revision': 0, 'request_key': uid(),
                   'document': {'version': 2, 'rooms': []}}
        headers = self.workshop_headers()
        status, saved = self.request('/workshop/save', 'POST', request, headers)
        self.assertEqual(status, 200, saved)
        self.assertEqual(saved['revision'], 1)
        status, receipt = self.request('/operation/status', 'POST', {'request_key': request['request_key']}, headers)
        self.assertEqual(status, 200)
        self.assertEqual(receipt, {'status': 'completed', 'action': 'workshop/save', 'result': saved,
                                   'workshop_context': {'group_id': self.group, 'actor_id': self.admin}})
        changed={'schema_version':2,'revision':1,'request_key':request['request_key'],
                 'document':{'version':2,'rooms':[{'id':uid(),'location_id':None,'name':'Changed','width':12,'height':10,
                 'unit':'ft','approximate':False,'objects':[]}]}}
        self.assertEqual(self.request('/workshop/save','POST',changed,headers)[0],409)
        self.assertEqual(self.workshop.get(self.group)['revision'],1)
        self.module['OPEN_ADMIN'] = False
        denied=dict(request,request_key=uid(),revision=1)
        status, _ = self.request('/workshop/save', 'POST', denied, headers)
        self.assertEqual(status, 403)
        self.assertEqual(self.request('/operation/status','POST',{'request_key':denied['request_key']})[1]['status'],'not_started')

    def test_terminal_room_save_recovers_postcommit_journal_failure_without_status_first(self):
        request={'schema_version':2,'revision':0,'request_key':uid(),'document':{'version':2,'rooms':[]}}
        original=self.ledger.transaction;calls=[0]
        @contextmanager
        def fail_completion(*args,**kwargs):
            calls[0]+=1
            if calls[0]==4:raise OSError('injected generic journal completion failure')
            with original(*args,**kwargs) as db:yield db
        self.ledger.transaction=fail_completion
        headers=self.workshop_headers()
        status,_=self.request('/workshop/save','POST',request,headers)
        self.ledger.transaction=original
        self.assertEqual(status,503)
        self.assertEqual(self.workshop.get(self.group)['revision'],1)
        status,saved=self.request('/workshop/save','POST',request,headers)
        self.assertEqual(status,200);self.assertEqual(saved['revision'],1)
        status,receipt=self.request('/operation/status','POST',{'request_key':request['request_key']},headers)
        self.assertEqual(status,200);self.assertEqual(receipt['status'],'completed')

    def test_terminal_room_save_keeps_pre_receipt_uncertainty_in_review(self):
        request={'schema_version':2,'revision':0,'request_key':uid(),'document':{'version':2,'rooms':[]}}
        original=self.workshop.save;calls=[0]
        def fail_before_receipt(*args,**kwargs):
            calls[0]+=1;raise OSError('injected failure before receipt')
        self.workshop.save=fail_before_receipt
        headers=self.workshop_headers()
        status,_=self.request('/workshop/save','POST',request,headers)
        self.workshop.save=original
        self.assertEqual(status,503)
        status,review=self.request('/operation/status','POST',{'request_key':request['request_key']},headers)
        self.assertEqual(status,200);self.assertEqual(review['status'],'review')
        status,_=self.request('/workshop/save','POST',request,headers)
        self.assertEqual(status,409);self.assertEqual(calls,[1])
        self.assertEqual(self.workshop.get(self.group)['revision'],0)

    def test_resolve_public_native_qr_origin_uses_server_trust_boundary(self):
        self.native.base = 'http://127.0.0.1:17747'
        self.module['trusted_native_origins'] = lambda port: ('http://pi.local:19333',)
        self.module['PUBLIC_NATIVE_PORT'] = 19333
        status, resolved = self.request('/workshop/resolve', 'POST', {'code': 'http://pi.local:19333/item/'+self.tool})
        self.assertEqual(status, 200)
        self.assertEqual(resolved['entity_id'], self.tool)

    @patch.dict(os.environ, {'WORKSHOP_PORT': '19333'})
    def test_resolve_foreign_ambiguity_badge_unknown_and_parity(self):
        self.native.base = 'http://127.0.0.1:17747'
        self.native.workshop_code_origins = ('http://pi.local:19333',)
        self.module['OPEN_ADMIN'] = False
        status, member_view = self.request('/workshop/view', 'POST',
                                           {'entity_id':self.rack,'include_nested':False})
        self.assertEqual(status, 200)
        self.assertEqual(member_view['selection']['target_id'], self.rack)
        self.assertFalse(self.module['OPEN_ADMIN'])
        missing_code = 'http://pi.local:19333/item/'+uid()
        status, missing = self.request('/workshop/resolve', 'POST', {'code':missing_code})
        self.assertEqual(status, 200)
        self.assertIsNone(missing['entity_id'])
        self.assertEqual(missing['kind'], 'entity')
        self.assertEqual(missing['message'], 'Native entity is unavailable in this tenant.')
        raw = 'https://maker.example/code-42'
        extra = uid()
        self.nodes[extra] = dict(self.nodes[self.tool], id=extra, name='Backup drill', parent={'id': self.rack},
            fields=[{'name':'Manufacturer QR code','type':'text','textValue':raw}])
        self.nodes[self.tool]['fields'] = [{'name':'Manufacturer QR code','type':'text','textValue':raw}]
        cases = [
            ('http://evil.example:19333/item/'+self.tool, None),
            ('http://pi.local:19333/item/'+uid(), None),
            (raw, None),
            ('LAB:U:fixture-badge', None),
            ('unrecognized', None),
            ('http://pi.local:19333/item/'+self.tool, self.tool),
            ('/item/'+self.tool, self.tool),
        ]
        for code, expected in cases:
            with self.subTest(code=code):
                status, result = self.request('/workshop/resolve', 'POST', {'code':code})
                self.assertEqual(status, 200)
                desktop = desktop_api.post_action('workshop/resolve', {'code':code},
                    {'client':self.native,'group':self.group,'actor':self.member,'manager':False},
                    {'ledger':self.ledger,'native_jobs':self.jobs,'badges':None}, {})
                self.assertEqual(result, desktop)
                self.assertEqual(result['entity_id'], expected)
                if code == raw:
                    self.assertEqual({row['id'] for row in result['candidates']}, {self.tool, extra})
                    self.assertEqual(len({json.dumps(row['path'], sort_keys=True) for row in result['candidates']}), 2)
        self.assertEqual(self.put_count, 0)
        self.module['OPEN_ADMIN'] = True

        order = {'entity_id': self.rack, 'updated_at': 'rack-v1', 'shelf_ids': [self.shelf], 'request_key': uid()}
        self.fail_after_put = True
        status, result = self.request('/workshop/shelf-order', 'POST', order)
        self.assertEqual(status, 503)
        job = self.jobs.unresolved(self.group)[0]
        self.assertEqual(self.jobs.detail(self.group, job['id'])['actor_id'], self.admin)
        self.assertNotEqual(self.admin, self.member)
        self.assertEqual(self.put_count, 1)
        self.module['native_context'] = lambda: (self.group, [])
        status_row = self.request('/operation/status', 'POST', {'request_key': order['request_key']})[1]
        self.assertEqual((status_row['id'], status_row['status']), (job['id'], 'review'))
        self.fail_after_put = False
        self.assertEqual(self.request('/recovery/resolve', 'POST', {'id': job['id'], 'native_job': True, 'outcome': 'complete'})[0], 200)
        self.assertEqual(self.put_count, 1)

        class RevokeAfterLock:
            def __enter__(inner): self.module['OPEN_ADMIN'] = False; return inner
            def __exit__(inner, *_): self.module['OPEN_ADMIN'] = True; return False
        self.module['lock'] = RevokeAfterLock()
        denied_order = dict(order, request_key=uid())
        self.assertEqual(self.request('/workshop/shelf-order', 'POST', denied_order)[0], 403)
        prepared = self.jobs.prepare(self.group, self.admin, 'workshop_shelf_order', uid(), {'entity_id': self.rack})
        self.assertEqual(self.request('/recovery/resolve', 'POST', {'id': prepared['id'], 'native_job': True, 'outcome': 'cancel'})[0], 403)
        self.assertEqual(self.put_count, 1)

    def test_file_route_keeps_entity_attachment_ownership_and_safe_headers(self):
        foreign = uid()
        other_photo = uid()
        self.nodes[self.shelf]['attachments'] = [{'id': other_photo, 'type': 'photo'}]
        status, body = self.request('/api/file?entity='+self.rack+'&attachment='+self.photo)
        self.assertEqual(status, 200)
        self.assertEqual(self.last_handler.sent_headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(self.last_handler.sent_headers['Cache-Control'], 'no-store')
        self.assertEqual(self.file_requests[-1].full_url.rsplit('/', 1)[-1], self.photo)
        for query in ('entity='+self.rack+'&attachment='+other_photo, 'entity='+foreign+'&attachment='+self.photo):
            status, body = self.request('/api/file?'+query)
            self.assertEqual(status, 404)


if __name__ == '__main__': unittest.main()
