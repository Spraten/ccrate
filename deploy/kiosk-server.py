#!/usr/bin/env python3
"""Loopback Homebox companion with browser-owned badge sessions."""
import base64, io, json, os, pathlib, signal, stat, sys, tempfile, threading, time, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from uuid import UUID as NativeUUID
FIXTURE_PROCESS=os.environ.get('WORKSHOP_FIXTURE_PROCESS')=='1'
def fixture_process_root():
    if not FIXTURE_PROCESS:return None
    raw=pathlib.Path(os.environ.get('WORKSHOP_ROOT',''))
    token=os.environ.get('WORKSHOP_FIXTURE_TOKEN','')
    ready=pathlib.Path(os.environ.get('WORKSHOP_FIXTURE_READY_FILE',''))
    try:
        if '..' in raw.parts or raw.is_symlink():raise ValueError()
        root=raw.resolve(strict=True)
        if raw.absolute()!=root:raise ValueError()
        marker=root/'.fixture-process-token'
        marker_stat=marker.lstat()
        if (not root.is_relative_to(pathlib.Path(tempfile.gettempdir()).resolve())
                or root.stat().st_uid!=os.getuid() or (root.stat().st_mode&0o777)!=0o700
                or not stat.S_ISREG(marker_stat.st_mode) or marker_stat.st_nlink!=1
                or marker_stat.st_uid!=os.getuid() or (marker_stat.st_mode&0o777)!=0o600
                or len(token)<32 or marker.read_text()!=token):raise ValueError()
        if os.environ.get('WORKSHOP_BIND_HOST')!='127.0.0.1' or int(os.environ.get('WORKSHOP_COMPANION_PORT','-1'))!=0:raise ValueError()
        base=urlsplit(os.environ.get('WORKSHOP_NATIVE_BASE',''))
        if base.scheme!='http' or base.hostname!='127.0.0.1' or not base.port or not 32768<=base.port<=60999:raise ValueError()
        if any(key.startswith('HBOX_') for key in os.environ):raise ValueError()
        if ('..' in ready.parts or not ready.is_absolute() or not ready.resolve(strict=False).is_relative_to(root)):raise ValueError()
        return root,ready
    except (OSError,ValueError,TypeError) as exc:
        raise RuntimeError('Fixture process refused before imports: owned temporary root, token, loopback and ephemeral ports are required') from exc
_fixture_context=fixture_process_root()
if _fixture_context:
    import types
    _fixture_blocked_names={'printer','printing','label_output','hardware','gpio'}
    def _fixture_is_physical_module(_name):
        return any(_part in _fixture_blocked_names for _part in _name.split('.'))
    if any(_fixture_is_physical_module(_name) for _name in sys.modules):
        raise RuntimeError('Fixture process refused cached physical modules before constructors')
    def _fixture_physical_refusal(*_args,**_kwargs):
        raise RuntimeError('Physical outputs are disabled in fixture-process mode')
    for _name in ('hardware','labels','printer','printing','label_output','gpio'):
        _module=types.ModuleType(_name)
        _module.__getattr__=lambda _attribute: _fixture_physical_refusal
        sys.modules[_name]=_module
CODE_ROOT_ENV=os.environ.get('WORKSHOP_CODE_ROOT')
CODE_ROOT=pathlib.Path(CODE_ROOT_ENV or pathlib.Path(__file__).resolve().parents[1]).resolve()
if _fixture_context:
    _ui_root=pathlib.Path(os.environ.get('HOMEBOX_UI_ROOT','')).resolve(strict=True)
    if not _ui_root.is_relative_to(CODE_ROOT):raise RuntimeError('Fixture process refused a static root outside its selected package')
ROOT=pathlib.Path(os.environ.get('WORKSHOP_ROOT','/home/user/Desktop/inventory-system')).resolve()
LABEL_ASSET_ROOT=pathlib.Path(os.environ.get('WORKSHOP_LABEL_ASSET_ROOT',CODE_ROOT/'work/label-ui-build')).resolve()
sys.path.insert(0,str(CODE_ROOT/'kiosk'))
sys.path.insert(0,str(ROOT/'program-files/runtime/hardware/python'))
sys.path.insert(0,str(CODE_ROOT/'ops'))
from ledger import Ledger, UNIDENTIFIED_ACTOR
from badges import Badges
from sessions import Sessions
from scan_codes import normalize, resolve_equipment
from decode_codes import decode_frame
from PIL import Image
import zxingcpp, qrcode
from urllib.parse import urlsplit, parse_qs
from homebox import Homebox
from checkout import confirm_checkout, checkout_availability, checkout_status_actor, checkout_cart_context
from checkout_cart import CheckoutCart
from returns import confirm_return, recover, RETURN_STATES
from maps import list_map,save_room,save_object,remove_object
from native_jobs import NativeJobs
from categories import create_category,recover_category
from code_registration import register_code,recover_code
from stock import browse as browse_stock,invalidate as invalidate_stock
from reviews import submit_review,recover_review
from kits import manifest as kit_manifest,save as save_kit
from system_status import status as system_status,start_backup
from hardware import reconnect as reconnect_hardware,camera_status
from desktop_api import ApiError, handle as desktop_handle, once, operation_status, recovery_rows, post_action, request_row, history as desktop_history
from accounts import create_account, get_profile, update_profile, creation_input, profile_input
from labels import preview as label_preview,print_label,print_badge,recover_print,probe as printer_probe,paper as labels_paper
from problems import submit_problem,recover_problem
from item_notes import submit_note, recover_note
from web_item_actions import WebItemActions
from setup_native import submit, recover_creation
from imports import Imports
from label_layouts import LabelLayouts
from network_access import same_origin, trusted_native_origins
from workshop import Workshop,move_location,submit_shelf_order,recover_shelf_order
from workshop_views import build_view,resolve_workshop_code
from shelf_checks import (ShelfChecks, CheckAccessDenied, shelf_check_action,
                          terminal_check_context)
TERMINAL_SHELF_CHECK_ROUTES={'list','get','resolve','request','start','observe','notes','refresh','finish','cancel'}
from products import catalog,lookup
from ledger import Conflict
from conditions import STATES, condition, checkout_blocker, set_condition
BASE=os.environ.get('WORKSHOP_NATIVE_BASE','http://127.0.0.1:17745')
lock=threading.Lock()
ops_path=ROOT/'work/ops'
ops_path.mkdir(exist_ok=True,mode=0o700)
os.chmod(ops_path,0o700)
ledger=Ledger(ops_path/'ledger.db')
checkout_cart=CheckoutCart(ledger)
shelf_checks=ShelfChecks(ledger)
badges=Badges(ledger)
native_jobs=NativeJobs(ledger)
imports=Imports(ops_path/'imports.db')
label_layouts=LabelLayouts(ops_path/'label-layouts.db',asset_root=LABEL_ASSET_ROOT)
workshop=Workshop(ops_path/'workshop.db')
sessions=Sessions()
web_item_actions=WebItemActions()

class _SessionBoundNativeClient:
    """Prevent a badge switch from racing the standalone maintenance POST."""
    def __init__(self, client, valid):
        self._client, self._valid = client, valid
    def __getattr__(self, name):
        return getattr(self._client, name)
    def call(self, path, *args, **kwargs):
        method = kwargs.get('method', args[0] if args and isinstance(args[0], str) else 'GET')
        if str(method).upper() == 'POST' and not self._valid():
            raise Conflict('Badge session changed before the note was written; inspect Recovery')
        return self._client.call(path, *args, **kwargs)

def confirm_terminal_note(client, jobs, session, data):
    required = {'request_key', 'input', 'session_generation', 'session_instance'}
    if not isinstance(data, dict) or set(data) != required:
        raise ValueError('Item note request is incomplete')
    if not isinstance(data['input'], dict) or set(data['input']) != {'entity_id', 'note'}:
        raise ValueError('Item note input must contain only equipment and note')
    actor, generation = session.snapshot()
    instance = session.instance
    if not actor:
        raise Conflict('Scan a group-member badge before adding an item note')
    if data['session_generation'] != generation or data['session_instance'] != instance:
        raise Conflict('Badge session changed; review the item note again')

    native = client.call('/api/v1/users/self')['item']
    group = native['defaultGroupId']
    client.tenant = group
    members = client.call('/api/v1/groups/members')
    member = next((row for row in members if row.get('id') == actor), None)
    if not member or not isinstance(member.get('name'), str) or not member['name'].strip():
        raise Conflict('Badge holder is no longer a named collection member')
    entity_id = data['input']['entity_id']
    entity = client.entity(entity_id)
    if (entity.get('id') != entity_id or entity.get('archived')
            or (entity.get('entityType') or {}).get('isLocation')
            or isinstance(entity.get('quantity'), bool)
            or entity.get('quantity') != 1):
        raise ValueError('Choose active, individually tracked equipment')

    def valid_owner():
        try:
            return (session.current(activity=True) == actor
                    and session.snapshot() == (actor, generation)
                    and session.instance == instance)
        except Exception:
            return False

    if not valid_owner():
        raise Conflict('Badge session changed; review the item note again')
    bound = _SessionBoundNativeClient(client, valid_owner)
    result = submit_note(bound, jobs, group, actor, data['request_key'], data['input'], member['name'])
    if result.get('status') != 'completed':
        return result
    ended = False
    if valid_owner():
        try:
            session.end(generation)
            ended = session.snapshot() != (actor, generation)
        except Exception:
            # The native note is already verified. Cleanup failure must not turn it into a retry.
            ended = False
    return dict(result, note_saved=True, session_ended=ended)

# Manager operations use authenticated /workshop-api requests, even on loopback.
OPEN_ADMIN=False
def label_context(deadline,actor=None):
    import time
    remaining=max(.001,deadline-time.monotonic())
    client=Homebox(ROOT,timeout=remaining,login_timeout=remaining,deadline=deadline)
    native=client.call('/api/v1/users/self')['item'];group=native['defaultGroupId'];client.tenant=group
    collection=client.call('/api/v1/groups');collection=collection.get('item',collection)
    if collection.get('id')!=group:raise Conflict('Native service did not confirm the active collection')
    actor=actor or native['id']
    members={row['id'] for row in client.call('/api/v1/groups/members')}
    if actor not in members:raise Conflict('Current badge holder is no longer a collection member')
    return client,native,group,actor
def terminal_assets():
    selected=CODE_ROOT/'work/kiosk-ui-current'
    return selected if selected.is_dir() else CODE_ROOT/'kiosk'
def inventory(locations=False):
    # Native service credentials stay on the Pi. Tokens never reach the browser or logs.
    account=json.loads((ROOT/'work/baseline/test-account.json').read_text())
    req=urllib.request.Request(BASE+'/api/v1/users/login',data=json.dumps({'username':account['email'],'password':account['password']}).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=8) as response:token=json.load(response)['token'].removeprefix('Bearer ')
    items=[]
    page=1
    while True:
        req=urllib.request.Request(BASE+f'/api/v1/entities?page={page}&pageSize=100&includeArchived=true&isLocation={str(locations).lower()}',headers={'Authorization':'Bearer '+token})
        with urllib.request.urlopen(req,timeout=8) as response:data=json.load(response)
        items.extend(data['items'])
        if len(items)>=data['total'] or not data['items']:break
        page+=1
    return items
def native_context():
    account=json.loads((ROOT/'work/baseline/test-account.json').read_text())
    req=urllib.request.Request(BASE+'/api/v1/users/login',data=json.dumps({'username':account['email'],'password':account['password']}).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=8) as response:token=json.load(response)['token'].removeprefix('Bearer ')
    def get(path):
        req=urllib.request.Request(BASE+path,headers={'Authorization':'Bearer '+token})
        with urllib.request.urlopen(req,timeout=8) as response:return json.load(response)
    actor=get('/api/v1/users/self')['item']
    members=get('/api/v1/groups/members')
    return actor['defaultGroupId'],members

def camera_state():
    return camera_status()

class Handler(BaseHTTPRequestHandler):
    @property
    def session(self):
        from uuid import UUID
        client = self.headers.get('X-Homebox-Client', 'legacy')
        if client != 'legacy':
            client = str(UUID(client))
        if not hasattr(self,'_owned_session'):self._owned_session=sessions.get(client)
        return self._owned_session

    def reply_json(self,code,data):
        body=json.dumps(data).encode()
        self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_POST(self):
        if desktop_handle(self,{'root':ROOT,'lock':lock,'ledger':ledger,'checkout_cart':checkout_cart,'shelf_checks':shelf_checks,'badges':badges,'native_jobs':native_jobs,'imports':imports,'workshop':workshop,'sessions':sessions,'web_item_actions':web_item_actions,'label_layouts':label_layouts,'label_asset_root':LABEL_ASSET_ROOT}):return
        try:self.session
        except ValueError as error:self.reply_json(400,{'error':str(error)});return
        if self.path == '/notes/confirm' or self.path.startswith('/workshop/checks/') or self.path in ('/workshop/get','/workshop/save','/workshop/move','/workshop/view','/workshop/resolve','/workshop/shelf-order') or self.path in ('/imports/upload', '/imports/map', '/imports/save', '/imports/create', '/imports/label', '/imports/get', '/imports/list') or self.path in ('/hardware/reconnect','/scan/cancel','/operation/status','/camera/focus','/decode','/scan','/badge/issue','/badge/revoke','/badge/reprint','/badge/replace','/session/end','/session/activity','/condition','/checkout/confirm','/return/session/start','/return/confirm','/recovery/resolve','/map/room','/map/object','/map/remove','/locations/create','/catalog/create','/enroll/confirm','/problem/confirm','/label/preview','/label/print','/label/templates/save','/label/templates/result','/label/paper','/accounts/create','/accounts/update','/backup/start','/kit/save','/maintenance/complete','/categories/create','/badge/print','/equipment/code'):
            if not same_origin(self.headers.get('Origin'),self.headers.get('Host')):self.send_error(403);return
            try:size=int(self.headers.get('Content-Length','0'))
            except ValueError:self.send_error(400);return
            limit=16000 if self.path=='/notes/confirm' else 4000000 if self.path in ('/enroll/confirm','/problem/confirm') else 1000000
            if not 0<size<=limit:self.send_error(413);return
            raw=self.rfile.read(size)
            try:
                if self.path=='/decode':
                    with Image.open(io.BytesIO(raw)) as frame:
                        if frame.width>1280 or frame.height>960:self.send_error(413);return
                        detections=decode_frame(frame)
                        codes=[d['code'] for d in detections]
                        width,height=frame.size
                    self.reply_json(200,{'codes':codes,'detections':detections,'width':width,'height':height});return
                data=json.loads(raw)
                if self.path.startswith('/workshop/checks/'):
                    if not OPEN_ADMIN:self.send_error(403);return
                    if not isinstance(data,dict):raise ValueError('Shelf-check request must be an object')
                    if any(self.headers.get(name) for name in ('X-Workshop-Actor','X-Workshop-Group','X-Workshop-Manager')):
                        raise ValueError('Shelf-check identity is supplied by Workshop')
                    route=self.path.rsplit('/',1)[1]
                    if route not in TERMINAL_SHELF_CHECK_ROUTES:self.send_error(404);return
                    with lock:
                        client=Homebox(ROOT)
                        ctx=terminal_check_context(client,open_admin=OPEN_ADMIN)
                        result=shelf_check_action(shelf_checks,client,ctx,route,data)
                    self.reply_json(200,result);return
                if self.path=='/notes/confirm':
                    if not self.session.current(activity=True):self.reply_json(401,{'error':'Scan your badge first'});return
                    if not lock.acquire(timeout=2):self.reply_json(503,{'error':'Item note service is busy. Try again'});return
                    try:result=confirm_terminal_note(Homebox(ROOT),native_jobs,self.session,data)
                    finally:lock.release()
                    self.reply_json(200,result);return
                if self.path=='/imports/label':
                    deadline=time.monotonic()+20
                    if not OPEN_ADMIN:self.send_error(403);return
                    if not lock.acquire(timeout=2):self.reply_json(503,{'error':'Label service is busy. Try again'});return
                    try:
                        session_actor,generation=self.session.snapshot();instance=self.session.instance
                        if data.get('session_generation',generation)!=generation or data.get('session_instance',instance)!=instance:raise Conflict('Label session changed; review the item again')
                        valid=lambda:self.session.instance==instance and self.session.snapshot()==(session_actor,generation)
                        client,native,group,actor=label_context(deadline,session_actor)
                        result=imports.label(client,native_jobs,group,data,actor=actor,layouts=label_layouts,valid_context=valid)
                    finally:lock.release()
                    self.reply_json(200,result);return
                if self.path.startswith('/label/'):
                    deadline=time.monotonic()+20
                    if not OPEN_ADMIN:self.send_error(403);return
                    if not lock.acquire(timeout=2):self.reply_json(503,{'error':'Label service is busy. Try again'});return
                    try:
                        session_actor,generation=self.session.snapshot();instance=self.session.instance
                        if data.get('session_generation',generation)!=generation or data.get('session_instance',instance)!=instance:raise Conflict('Label session changed; review the item again')
                        valid=lambda:self.session.instance==instance and self.session.snapshot()==(session_actor,generation)
                        client,native,group,actor=label_context(deadline,session_actor)
                        suffix=self.path.removeprefix('/label/')
                        if suffix=='templates/save':
                            if deadline-time.monotonic()<4:raise TimeoutError('Label request exceeded the 20-second budget')
                            if not valid():raise Conflict('Label session changed; review the item again')
                            result=label_layouts.save(group,actor,data)
                        elif suffix=='templates/result':
                            if deadline-time.monotonic()<2:raise TimeoutError('Label request exceeded the 20-second budget')
                            result=label_layouts.save_result(group,actor,data.get('request_key'))
                        elif suffix=='preview':
                            if not data.get('mode') and data.get('entity_id'):
                                entity=client.entity(data.get('entity_id'))
                                if entity.get('isLocation') or (entity.get('entityType') or {}).get('isLocation'):result=label_preview(client,data.get('entity_id'))
                                else:raise ValueError('Choose a saved template and review the item before printing')
                            else:result=label_layouts.preview(client,group,actor,data,deadline=deadline)
                        elif suffix=='print':
                            if not data.get('review_id'):
                                entity=client.entity(data.get('entity_id'))
                                if entity.get('isLocation') or (entity.get('entityType') or {}).get('isLocation'):result=print_label(client,native_jobs,group,actor,data.get('request_key'),data.get('entity_id'))
                                else:result=print_label(client,native_jobs,group,actor,data.get('request_key'),data.get('entity_id'),layouts=label_layouts,review_id=None)
                            else:result=print_label(client,native_jobs,group,actor,data.get('request_key'),data.get('entity_id'),layouts=label_layouts,review_id=data.get('review_id'),valid_context=valid)
                        elif suffix=='paper':result=labels_paper(client,label_layouts,group,actor,data,deadline=deadline)
                        else:self.send_error(404);return
                        if suffix in ('preview','paper','templates/result') and time.monotonic()>=deadline:raise TimeoutError('Label request exceeded the 20-second budget')
                        if suffix in ('preview','paper','templates/result','templates/save') and not valid():raise Conflict('Label session changed; reload the label editor')
                        self.reply_json(200,result)
                    finally:lock.release()
                    return
                if self.path=='/hardware/reconnect':
                    if not OPEN_ADMIN:self.send_error(403);return
                    with lock:result=reconnect_hardware(data.get('device'))
                    self.reply_json(200,result);return
                if self.path=='/camera/focus':
                    import subprocess
                    camera=camera_state()
                    if not camera['supported']:raise ValueError('Pi C920 focus controls unavailable')
                    device=camera['device']
                    mode=data.get('mode')
                    if mode not in ('auto','manual'):raise ValueError('Unknown focus mode')
                    value=data.get('value',150)
                    if mode=='manual' and (type(value) is not int or value<0 or value>250 or value%5):raise ValueError('Focus must be 0 to 250 in steps of 5')
                    try:
                        subprocess.run(['v4l2-ctl','-d',device,'--set-ctrl=focus_automatic_continuous='+('1' if mode=='auto' else '0')],check=True,capture_output=True,timeout=5)
                        if mode=='manual':subprocess.run(['v4l2-ctl','-d',device,'--set-ctrl=focus_absolute='+str(value)],check=True,capture_output=True,timeout=5)
                    except (subprocess.SubprocessError,OSError):raise ValueError('Camera focus could not be changed. Reconnect the webcam and retry.')
                    self.reply_json(200,{'mode':mode,'value':value});return
                if self.path.startswith('/workshop/'):
                    if self.path not in ('/workshop/get','/workshop/view','/workshop/resolve') and not OPEN_ADMIN:self.send_error(403);return
                    with lock:
                        if self.path in ('/workshop/save','/workshop/move','/workshop/shelf-order') and not OPEN_ADMIN:self.send_error(403);return
                        client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item'];group=native['defaultGroupId']
                        client.tenant=group
                        client.workshop_code_origins=trusted_native_origins(os.environ.get('WORKSHOP_PORT','17745'))
                        if self.path=='/workshop/view':
                            entity_id=data.get('entity_id')
                            if entity_id is not None:
                                if not isinstance(entity_id,str):raise ValueError('Choose a native entity.')
                                entity_id=str(NativeUUID(entity_id))
                            nested=data.get('include_nested')
                            if type(nested) is not bool:raise ValueError('Choose whether to include nested equipment.')
                            room_id=data.get('room_id')
                            if room_id is not None:
                                if not isinstance(room_id,str):raise ValueError('Choose an available workshop room.')
                                room_id=str(NativeUUID(room_id))
                                available={row.get('id') for row in workshop.get(group).get('document',{}).get('rooms',[])}
                                if room_id not in available:raise ValueError('Choose an available workshop room.')
                            result=build_view(client,workshop.get(group),ledger.custody(group),entity_id=entity_id,include_nested=nested,room_id=room_id,can_view_loans=OPEN_ADMIN)
                        elif self.path=='/workshop/resolve':
                            if not isinstance(data.get('code'),str):raise ValueError('Enter a native equipment code.')
                            result=resolve_workshop_code(client,data['code'])
                        elif self.path=='/workshop/shelf-order':result=submit_shelf_order(client,native_jobs,group,native['id'],data.get('request_key'),data)
                        elif self.path=='/workshop/save':
                            try:
                                supplied_group=self.headers.get('X-Workshop-Group','')
                                supplied_actor=self.headers.get('X-Workshop-Actor','')
                                canonical_group=str(NativeUUID(supplied_group))
                                canonical_actor=str(NativeUUID(supplied_actor))
                            except (ValueError,TypeError,AttributeError):
                                raise Conflict('Workshop collection or service actor changed. Reload before saving.') from None
                            if supplied_group!=canonical_group or supplied_actor!=canonical_actor or canonical_group!=group or canonical_actor!=native['id']:
                                raise Conflict('Workshop collection or service actor changed. Reload before saving.')
                            if not isinstance(data,dict) or type(data.get('schema_version')) is not int or data['schema_version']!=2:
                                raise ValueError('This Workshop save is outdated. Reload before saving.')
                            prior=request_row(ledger,group,data.get('request_key'))
                            if prior is None:
                                result=workshop.replay_save(group,data,actor_id=native['id'])
                                if result is None:
                                    workshop.validate_save(client,group,data)
                                    result=once({'group':group,'actor':native['id']},globals(),'workshop/save',data,
                                                lambda:workshop.save(client,group,data,actor_id=native['id']))
                            else:
                                result=once({'group':group,'actor':native['id']},globals(),'workshop/save',data,
                                            lambda:workshop.save(client,group,data,actor_id=native['id']))
                        elif self.path=='/workshop/move':result=move_location(client,data);invalidate_stock()
                        else:
                            result=workshop.snapshot(client,group)
                            result['workshop_context']={'group_id':group,'actor_id':native['id']}
                    self.reply_json(200,result);return
                if self.path.startswith('/imports/'):
                    if not OPEN_ADMIN:self.send_error(403);return
                    with lock:
                        client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item'];group=native['defaultGroupId'];action=self.path.rsplit('/',1)[1]
                        if action=='upload':result=imports.upload(group,self.session.current() or native['id'],data)
                        elif action=='list':result=imports.list(group)
                        elif action=='map':result=imports.map(client,group,data)
                        elif action=='get':result=imports.sync(client,native_jobs,group,data)
                        elif action=='label':result=imports.label(client,native_jobs,group,data,actor=self.session.current() or native['id'],layouts=label_layouts)
                        else:result=getattr(imports,action)(client,native_jobs,group,data)
                        if action=='create':invalidate_stock()
                    self.reply_json(200,result);return
                if self.path not in ('/scan','/session/end','/session/activity','/label/preview','/backup/start'):invalidate_stock()
                if self.path=='/badge/print':
                    if not OPEN_ADMIN:self.send_error(403);return
                    with lock:
                        client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item'];result=print_badge(client,badges,native_jobs,native['defaultGroupId'],self.session.current() or native['id'],data.get('request_key'),data.get('badge_id'),data.get('code'))
                    self.reply_json(200,result);return
                if self.path=='/equipment/code':
                    if not OPEN_ADMIN:self.send_error(403);return
                    with lock:
                        client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item']
                        result=register_code(client,native_jobs,native['defaultGroupId'],self.session.current() or native['id'],data.get('request_key'),data.get('input',{}))
                    self.reply_json(200,result);return
                if self.path=='/categories/create':
                    if not OPEN_ADMIN:self.send_error(403);return
                    with lock:
                        client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item'];result=create_category(client,native_jobs,native['defaultGroupId'],self.session.current() or native['id'],data.get('request_key'),data.get('input',{}))
                    self.reply_json(200,result);return
                if self.path=='/maintenance/complete':
                    if not OPEN_ADMIN:self.send_error(403);return
                    with lock:
                        client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item'];result=submit_review(client,native_jobs,native['defaultGroupId'],self.session.current() or native['id'],data.get('request_key'),data,'complete_maintenance')
                    self.reply_json(200,result);return
                if self.path=='/kit/save':
                    if not OPEN_ADMIN:self.send_error(403);return
                    with lock:
                        client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item'];held={r['entity_id'] for r in ledger.custody(native['defaultGroupId'])}
                        if held & {data.get('entity_id'),*data.get('members',[])}:raise Conflict('Return the kit and components before changing its manifest')
                        result=save_kit(client,data.get('entity_id'),data.get('members',[]))
                    self.reply_json(200,result);return
                if self.path=='/backup/start':
                    if not OPEN_ADMIN:self.send_error(403);return
                    with lock:result=start_backup(data.get('request_key'))
                    self.reply_json(202,result);return
                if self.path in ('/accounts/create','/accounts/update'):
                    if not OPEN_ADMIN:self.send_error(403);return
                    with lock:
                        client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item'];group=native['defaultGroupId'];client.tenant=group
                        context={'actor':native['id'],'group':group}
                        if self.path=='/accounts/create':
                            creation_input(data)
                            result=once(context,globals(),'users/create',data,lambda:create_account(client,data),lambda value:{'id':value['id'],'name':value['name']})
                        else:
                            profile_input(data)
                            if request_row(ledger,group,data.get('request_key')) is None:
                                current=get_profile(client,data.get('user_id'))
                                if current['updatedAt']!=data.get('updatedAt'):raise ValueError('This profile changed. Reload it before saving')
                            result=once(context,globals(),'users/update',data,lambda:update_profile(client,data.get('user_id'),data),lambda value:{'id':value['id'],'name':value['name']})
                    self.reply_json(200,result);return
                if self.path in ('/locations/create','/catalog/create','/enroll/confirm','/problem/confirm'):
                    if self.path not in ('/enroll/confirm','/problem/confirm') and not OPEN_ADMIN:self.send_error(403);return
                    actor,generation=self.session.snapshot()
                    if self.path in ('/enroll/confirm','/problem/confirm'):
                        if not actor:self.reply_json(401,{'error':'Scan your badge first'});return
                        if data.get('session_generation')!=generation or data.get('session_instance')!=self.session.instance:raise Conflict('Badge session changed; review your selection again')
                    with lock:
                        client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item'];group=native['defaultGroupId']
                        if actor and actor not in {m['id'] for m in client.call('/api/v1/groups/members')}:raise Conflict('Badge holder is no longer a member')
                        kind={'/locations/create':'create_location','/catalog/create':'create_template','/enroll/confirm':'create_asset','/problem/confirm':'report_problem'}[self.path]
                        if self.path in ('/enroll/confirm','/problem/confirm') and self.session.snapshot()!=(actor,generation):raise Conflict('Session ended; scan your badge again')
                        result=submit_problem(client,native_jobs,group,actor,data.get('request_key'),data.get('input',{})) if kind=='report_problem' else submit(client,native_jobs,group,actor or native['id'],kind,data.get('request_key'),data.get('input',{}))
                        if self.path in ('/enroll/confirm','/problem/confirm'):self.session.end(generation)
                    self.reply_json(200,result);return
                if self.path in ('/map/room','/map/object','/map/remove'):
                    if not OPEN_ADMIN:self.send_error(403);return
                    with lock:
                        client=Homebox(ROOT)
                        if self.path=='/map/room':result=save_room(client,data.get('entity_id'),data)
                        elif self.path=='/map/object':result=save_object(client,data.get('entity_id'),data)
                        else:result=remove_object(client,data.get('entity_id'))
                    self.reply_json(200,result);return
                if self.path=='/recovery/resolve':
                    if not OPEN_ADMIN:self.send_error(403);return
                    with lock:
                        if not OPEN_ADMIN:self.send_error(403);return
                        client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item']
                        group=native['defaultGroupId']
                        if data.get('desktop_job'):
                            client.tenant=group
                            result=post_action('recovery/resolve',data,{'client':client,'group':group,'actor':native['id'],'manager':True},globals(),'http://'+self.headers.get('Host',''))
                        elif data.get('native_job'):
                            job=native_jobs.detail(group,data.get('id'))
                            handler=recover_note if job['kind']=='add_note' else recover_code if job['kind']=='register_code' else recover_category if job['kind']=='create_type' else recover_review if job['kind'] in ('review_condition','complete_maintenance') else recover_print if job['kind'] in ('print_label','print_badge') else recover_problem if job['kind']=='report_problem' else recover_shelf_order if job['kind']=='workshop_shelf_order' else recover_creation
                            result=handler(client,native_jobs,group,data.get('id'),data.get('outcome'),layouts=label_layouts) if handler is recover_print else handler(client,native_jobs,group,data.get('id'),data.get('outcome'))
                        else:result=recover(client,ledger,group,data.get('id'),data.get('outcome'))
                    self.reply_json(200,result);return
                if self.path=='/return/confirm':
                    anonymous_return=data.get('anonymous_return') is True
                    actor,generation=self.session.snapshot()
                    if data.get('session_generation')!=generation or data.get('session_instance')!=self.session.instance:raise Conflict('Return context changed; review your selection again')
                    if anonymous_return:
                        if actor or not self.session.returning(generation,self.session.instance):raise Conflict('Anonymous return context ended; start the return again')
                    elif not actor:self.reply_json(401,{'error':'Scan your badge first'});return
                    with lock:
                        client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item']
                        valid=lambda:self.session.returning(generation,self.session.instance) if anonymous_return else self.session.snapshot()==(actor,generation)
                        result=confirm_return(client,ledger,native['defaultGroupId'],None if anonymous_return else actor,data.get('targets'),data.get('request_key'),valid,self.session.scans(generation),data.get('kit_versions'),anonymous_return=anonymous_return)
                        self.session.end(generation)
                    self.reply_json(200,result);return
                if self.path=='/checkout/confirm':
                    actor,generation=self.session.snapshot()
                    if not actor:self.reply_json(401,{'error':'Scan your badge first'});return
                    if data.get('session_generation')!=generation or data.get('session_instance')!=self.session.instance:raise Conflict('Badge session changed; review your selection again')
                    with lock:
                        client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item']
                        group=native['defaultGroupId'];client.tenant=group
                        cart_context=None
                        if 'cart_revision' in data or 'cart_items' in data:
                            saved=checkout_cart.get(group,actor)
                            requested=data.get('cart_items')
                            if data.get('cart_revision')!=saved['revision'] or not isinstance(requested,list):
                                raise Conflict('Your saved checkout cart changed. Review it again.')
                            requested=[str(NativeUUID(value)) for value in requested]
                            if len(requested)>50 or len(requested)!=len(set(requested)):
                                raise Conflict('Your saved checkout cart changed. Review it again.')
                            cart_context=checkout_cart_context(saved,requested)
                        result=confirm_checkout(client,ledger,group,actor,data.get('assets',[]),data.get('request_key'),lambda:self.session.snapshot()==(actor,generation),self.session.scans(generation),data.get('kit_versions'),cart_context)
                        if cart_context is not None:
                            result['cart_consumption']=checkout_cart.consume_completed_receipt(group,actor,result['id'])
                    self.reply_json(200,result);return
                if self.path=='/condition':
                    if not OPEN_ADMIN:self.send_error(403);return
                    with lock:
                        client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item'];result=submit_review(client,native_jobs,native['defaultGroupId'],self.session.current() or native['id'],data.get('request_key'),{'entity_id':data.get('entity_id'),'state':data.get('state')});entity=client.entity(result['entity_id'])
                    self.reply_json(200,{'entity':entity,'condition':condition(entity),'blocker':checkout_blocker(entity)});return
                if self.path=='/session/activity':
                    self.reply_json(200,{'active':self.session.active(activity=True)});return
                if self.path=='/return/session/start':
                    generation=self.session.begin_anonymous_return()
                    self.reply_json(200,{'generation':generation,'instance':self.session.instance,'return_only':True});return
                if self.path=='/operation/status':
                    from ledger import uuid
                    # Wait for an in-flight writer before deciding a key made no change.
                    with lock:
                        native=Homebox(ROOT).call('/api/v1/users/self')['item']
                        group,actor=native['defaultGroupId'],native['id']
                        supplied_group=self.headers.get('X-Workshop-Group','')
                        supplied_actor=self.headers.get('X-Workshop-Actor','')
                        scoped=bool(supplied_group or supplied_actor)
                        if scoped:
                            try:
                                canonical_group=str(NativeUUID(supplied_group))
                                canonical_actor=str(NativeUUID(supplied_actor))
                            except (ValueError,TypeError,AttributeError):
                                raise Conflict('Workshop collection or service actor changed. Check the result in its original context.') from None
                            if (supplied_group!=canonical_group or supplied_actor!=canonical_actor or
                                    canonical_group!=group or canonical_actor!=native['id']):
                                raise Conflict('Workshop collection or service actor changed. Check the result in its original context.')
                        else:
                            key=uuid(data.get('request_key'))
                            prior=request_row(ledger,group,key)
                            binding=workshop.save_binding(group,key)
                            if (prior and prior.get('kind')=='workshop/save') or binding:
                                raise Conflict('This Workshop result requires its original collection and service actor context.')
                        badge_actor,generation=self.session.snapshot()
                        key=uuid(data.get('request_key'))
                        status_actor=checkout_status_actor(ledger,group,key,badge_actor,native['id'])
                        result=operation_status({'group':group,'actor':status_actor,'manager':True},globals(),data)
                        if result.get('action')=='check_out' and result.get('id'):
                            with ledger.connection() as db:
                                op=db.execute('SELECT actor_id FROM operations WHERE id=? AND group_id=?',(result['id'],group)).fetchone()
                            if not badge_actor or not op or op['actor_id']!=badge_actor:
                                result={'status':'not_started'}
                            elif result.get('status')=='completed':
                                with ledger.connection() as db:
                                    ctxrow=db.execute('SELECT payload FROM operation_context WHERE operation_id=?',(result['id'],)).fetchone()
                                if ctxrow and json.loads(ctxrow['payload']).get('checkout_cart'):
                                    result['cart_consumption']=checkout_cart.consume_completed_receipt(group,badge_actor,result['id'])
                        if scoped:result['workshop_context']={'group_id':group,'actor_id':native['id']}
                    self.reply_json(200,result);return
                if self.path=='/scan/cancel':
                    from ledger import uuid
                    self.session.cancel_scan(uuid(data.get('scan_token')))
                    self.reply_json(200,{'cancelled':True});return
                scan_context=None
                if self.path=='/scan':
                    self.session.current(activity=True)
                    scan_context=self.session.scan_context(data.get('scan_token'))
                if self.path=='/session/end':
                    if not data.get('expected_instance') or data.get('expected_instance')==self.session.instance:self.session.end(data.get('expected_generation'))
                    self.reply_json(200,{'ended':True});return
                if self.path in ('/badge/issue','/badge/revoke','/badge/reprint','/badge/replace'):
                    if not OPEN_ADMIN:self.send_error(403);return
                    with lock:
                        client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item']
                        group=native['defaultGroupId'];client.tenant=group
                        ctx={'client':client,'group':group,'actor':native['id'],'manager':True}
                        route={'/badge/issue':'badges/issue','/badge/revoke':'badges/revoke',
                            '/badge/reprint':'badges/reprint','/badge/replace':'badges/replace'}[self.path]
                        result=post_action(route,data,ctx,globals(),'')
                    self.reply_json(200,result)
                    return
                if isinstance(data.get('code'),str) and data['code'].startswith(Badges.PREFIX):
                    group,members=native_context();user=badges.resolve(group,data['code'],[m['id'] for m in members])
                    if user:
                        name=next(m['name'] for m in members if m['id']==user)
                        from ledger import uuid
                        token=uuid(data['scan_token']) if data.get('scan_token') else None
                        generation=self.session.start(user,token)
                        if generation is None:
                            self.reply_json(200,{'kind':'cancelled'});return
                        self.reply_json(200,{'kind':'user','user':{'id':user,'name':name},'generation':generation,'instance':self.session.instance})
                    else:self.reply_json(200,{'kind':'invalid','reason':'Badge unknown, revoked, or no longer a group member'})
                    return
                code=normalize(data.get('code'))
                if code['kind'] in ('asset','entity'):
                    with lock:items=inventory()+inventory(True)
                    match=next((e for e in items if ('asset_id' in code and e.get('assetId')==code['asset_id']) or ('entity_id' in code and e['id']==code['entity_id'])),None)
                    if match:
                        code['entity']=match;self.session.record_scan(match['id'],scan_context)
                    else:code={'kind':'unknown','reason':'This code is not in this C-Crate inventory'}
                if code['kind'] not in ('asset','entity','unknown'):
                    with lock:
                        client=Homebox(ROOT);items=inventory()
                        items=[client.entity(e['id']) for e in items if not e.get('archived')]
                        code=resolve_equipment(data.get('code') or '',code,items)
                    if code.get('entity'):self.session.record_scan(code['entity']['id'],scan_context)
                self.reply_json(200,code)
            except ApiError as error:self.reply_json(error.status,{'error':error.message,'reason':error.message})
            except Conflict as error:self.reply_json(409,{'error':str(error),'reason':str(error)})
            except (ValueError,TypeError,AttributeError,KeyError) as error:self.reply_json(400,{'kind':'invalid','error':str(error),'reason':str(error)})
            except CheckAccessDenied as error:self.reply_json(403,{'error':str(error),'reason':str(error)})
            except OSError as error:
                if self.path in ('/label/preview','/label/paper','/label/templates/result'):self.reply_json(503,{'error':str(error) or 'Label preview is busy. Try again'})
                else:self.reply_json(503,{'error':'C-Crate unavailable; no confirmation received','reason':'C-Crate unavailable; try again'})
            return

        if self.client_address[0] not in ('127.0.0.1','::1') or self.headers.get('X-Homebox-Client-Mode') == 'editor' or self.path != '/exit' or self.headers.get('Origin') != 'http://127.0.0.1:17749':
            self.send_error(403);return
        from kiosk_processes import kiosk_pids
        profile=str(ROOT/'work/kiosk-browser')
        targets=kiosk_pids(profile)
        if not targets:
            self.send_error(409);return
        self.send_response(200);self.send_header('Content-Length','0');self.end_headers()
        self.wfile.flush()
        def close_window():
            for pid in targets:
                try:os.kill(pid,signal.SIGTERM)
                except ProcessLookupError:pass
        timer=threading.Timer(0.3,close_window);timer.daemon=True;timer.start()
    def do_GET(self):
        if self.path in ('/', '/terminal.css', '/terminal.js', '/checkout-ui.js', '/scanner_input.js'):
            self.send_error(404); return
        if urlsplit(self.path).path in ('/touchscreen', '/touchscreen.css', '/touchscreen.js'):
            name = {'/touchscreen': 'touchscreen.html', '/touchscreen.css': 'touchscreen.css', '/touchscreen.js': 'touchscreen.js'}[urlsplit(self.path).path]
            content = (ROOT / 'kiosk' / name).read_bytes()
            mime = 'text/html; charset=utf-8' if name.endswith('.html') else ('text/css; charset=utf-8' if name.endswith('.css') else 'application/javascript; charset=utf-8')
            self.send_response(200); self.send_header('Content-Type', mime); self.send_header('Content-Length', str(len(content))); self.send_header('Cache-Control', 'no-store'); self.end_headers(); self.wfile.write(content); return
        if desktop_handle(self,{'root':ROOT,'lock':lock,'ledger':ledger,'checkout_cart':checkout_cart,'shelf_checks':shelf_checks,'badges':badges,'native_jobs':native_jobs,'imports':imports,'workshop':workshop,'sessions':sessions,'web_item_actions':web_item_actions,'label_layouts':label_layouts,'label_asset_root':LABEL_ASSET_ROOT}):return
        if urlsplit(self.path).path=='/checkout/cart':
            actor,generation=self.session.snapshot()
            if not actor:self.reply_json(401,{'error':'Scan your badge first'});return
            try:
                with lock:
                    client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item'];group=native['defaultGroupId']
                    client.tenant=group
                    members=client.call('/api/v1/groups/members')
                    if actor not in {member['id'] for member in members}:raise Conflict('Badge holder is no longer a collection member')
                    result=checkout_cart.get(group,actor)
                    if self.session.snapshot()!=(actor,generation):raise Conflict('Badge session changed; reload the checkout cart')
                self.reply_json(200,result)
            except (OSError,ValueError,Conflict) as error:self.reply_json(409,{'error':str(error)})
            return
        if urlsplit(self.path).path=='/checkout/availability':
            actor,generation=self.session.snapshot()
            if not actor:self.reply_json(401,{'error':'Scan your badge first'});return
            try:
                query=parse_qs(urlsplit(self.path).query,keep_blank_values=True)
                if set(query)!={'ids'} or len(query['ids'])!=1:raise ValueError('Choose checkout items to review')
                ids=query['ids'][0].split(',')
                with lock:
                    client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item'];group=native['defaultGroupId']
                    client.tenant=group
                    members=client.call('/api/v1/groups/members')
                    if actor not in {member['id'] for member in members}:raise Conflict('Badge holder is no longer a collection member')
                    result=checkout_availability(client,ledger,group,ids)
                    if self.session.snapshot()!=(actor,generation):raise Conflict('Badge session changed; refresh checkout availability')
                self.reply_json(200,result)
            except (ValueError,KeyError) as error:self.reply_json(400,{'error':str(error)})
            except Conflict as error:self.reply_json(409,{'error':str(error)})
            except OSError as error:self.reply_json(503,{'error':str(error) or 'C-Crate unavailable'})
            return
        terminal_path=urlsplit(self.path)
        if terminal_path.path.startswith('/workshop/checks/'):
            if not OPEN_ADMIN:self.send_error(403);return
            route=terminal_path.path.rsplit('/',1)[1]
            if route not in ('list','get'):
                self.send_error(405);return
            try:
                query=parse_qs(terminal_path.query,keep_blank_values=True)
                if any(len(values)!=1 for values in query.values()):
                    raise ValueError('Shelf-check query fields may appear only once')
                data={key:values[0] for key,values in query.items()}
                if route=='list' and 'limit' in data:
                    data['limit']=int(data['limit'])
                with lock:
                    client=Homebox(ROOT)
                    ctx=terminal_check_context(client,open_admin=OPEN_ADMIN)
                    result=shelf_check_action(shelf_checks,client,ctx,route,data)
                self.reply_json(200,result)
            except CheckAccessDenied as error:
                self.reply_json(403,{'error':str(error),'reason':str(error)})
            except (ValueError,TypeError,KeyError,AttributeError) as error:
                self.reply_json(400,{'error':str(error),'reason':str(error)})
            except OSError as error:
                self.reply_json(503,{'error':str(error) or 'C-Crate unavailable','reason':str(error)})
            return
        if self.path.startswith('/label-assets/'):
            from desktop_api import serve_label_asset
            serve_label_asset(self,ROOT,self.path[len('/label-assets/'):],LABEL_ASSET_ROOT);return
        if self.path=='/label/equipment':
            if not OPEN_ADMIN:self.send_error(403);return
            deadline=time.monotonic()+20
            if not lock.acquire(timeout=2):self.reply_json(503,{'error':'Label equipment is busy. Try again'});return
            try:
                session_actor,generation=self.session.snapshot();instance=self.session.instance
                client,native,group,actor=label_context(deadline,session_actor)
                items=[{'id':row['id'],'name':row.get('name',''),'assetId':row.get('assetId',''),'updatedAt':row.get('updatedAt'),'parent':row.get('parent')} for row in client.entities(False) if not row.get('archived') and not row.get('isLocation') and not (row.get('entityType') or {}).get('isLocation')]
                if time.monotonic()>=deadline or self.session.instance!=instance or self.session.snapshot()!=(session_actor,generation):raise Conflict('Label context changed; reload the item queue')
                self.reply_json(200,items)
            except (ValueError,KeyError,OSError,TimeoutError,Conflict) as error:self.reply_json(503,{'error':str(error) or 'Label equipment is unavailable'})
            finally:lock.release()
            return
        if self.path=='/label/templates':
            if not OPEN_ADMIN:self.send_error(403);return
            deadline=time.monotonic()+20
            if not lock.acquire(timeout=2):self.reply_json(503,{'error':'Label service is busy. Try again'});return
            try:
                session_actor,generation=self.session.snapshot();instance=self.session.instance
                client,native,group,actor=label_context(deadline,session_actor)
                label_layouts.reconcile_reviews(group,native_jobs)
                result=label_layouts.list(group)
                if time.monotonic()>=deadline or self.session.instance!=instance or self.session.snapshot()!=(session_actor,generation):raise Conflict('Label context changed; reload templates')
                self.reply_json(200,result)
            except (ValueError,OSError,TimeoutError) as error:self.reply_json(503,{'error':str(error)})
            finally:lock.release()
            return
        if self.path.startswith('/api/'):
            try:self.session
            except ValueError as error:self.reply_json(400,{'error':str(error)});return
        if self.path=='/api/camera':
            self.reply_json(200,camera_state());return
        if urlsplit(self.path).path=='/api/file':
            try:
                from ledger import uuid
                query=parse_qs(urlsplit(self.path).query);entity_id=uuid(query.get('entity',[None])[0]);attachment_id=uuid(query.get('attachment',[None])[0]);client=Homebox(ROOT);entity=client.entity(entity_id)
                attachment=next(a for a in entity.get('attachments',[]) if a['id']==attachment_id)
                request=urllib.request.Request(client.base+'/api/v1/entities/'+entity_id+'/attachments/'+attachment_id,headers={'Authorization':'Bearer '+client.token})
                class LocalRedirect(urllib.request.HTTPRedirectHandler):
                    def redirect_request(self,request,fp,code,msg,headers,newurl):
                        destination=urlsplit(newurl)
                        if destination.hostname!='127.0.0.1' or destination.port!=17745:raise ValueError('External file unavailable offline')
                        return super().redirect_request(request,fp,code,msg,headers,newurl)
                with urllib.request.build_opener(LocalRedirect()).open(request,timeout=15) as response:
                    content=response.read(10000001);mime=response.headers.get_content_type()
                if len(content)>10000000:raise ValueError('File exceeds kiosk preview limit')
                self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(content)));self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store')
                if mime not in ('image/jpeg','image/png','image/webp','image/gif'):self.send_header('Content-Disposition','attachment')
                self.end_headers();self.wfile.write(content)
            except (OSError,ValueError,StopIteration):self.reply_json(404,{'error':'Native file unavailable'})
            return
        if urlsplit(self.path).path=='/api/stock':
            try:self.reply_json(200,browse_stock(Homebox(ROOT),'refresh' in parse_qs(urlsplit(self.path).query)))
            except (OSError,ValueError):self.reply_json(503,{'error':'Native stock unavailable'})
            return
        if urlsplit(self.path).path=='/api/maintenance':
            try:
                from ledger import uuid
                entity_id=uuid(parse_qs(urlsplit(self.path).query).get('entity',[None])[0]);self.reply_json(200,Homebox(ROOT).call('/api/v1/entities/'+entity_id+'/maintenance'))
            except (OSError,ValueError):self.reply_json(503,{'error':'Native maintenance unavailable'})
            return
        if urlsplit(self.path).path=='/api/kit':
            try:
                data=kit_manifest(Homebox(ROOT),parse_qs(urlsplit(self.path).query).get('id',[None])[0]);data['verified']=list(self.session.scans(self.session.snapshot()[1]));self.reply_json(200,data)
            except (ValueError,OSError):self.reply_json(400,{'error':'Kit manifest or native equipment needs review'})
            return
        if urlsplit(self.path).path=='/api/user-profile':
            if not OPEN_ADMIN:self.send_error(403);return
            try:self.reply_json(200,get_profile(Homebox(ROOT),parse_qs(urlsplit(self.path).query).get('id',[None])[0]))
            except urllib.error.HTTPError as error:self.reply_json(error.code,{'error':'Could not read this member profile'})
            except (ValueError,OSError):self.reply_json(400,{'error':'Choose a current user and reload their profile'})
            return
        if urlsplit(self.path).path=='/api/member-loans':
            if not OPEN_ADMIN:self.send_error(403);return
            try:
                with lock:
                    client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item']
                    group=native['defaultGroupId'];client.tenant=group
                    ctx={'client':client,'group':group,'collection':group,'actor':native['id'],
                         'user':native,'manager':True,'identity':{'actor_id':native['id'],'group_id':group}}
                    from desktop_api import get_action
                    data=get_action('loans',{},ctx,globals())
                self.reply_json(200,data)
            except (OSError,ValueError,KeyError,TypeError) as error:
                self.reply_json(503,{'error':str(error) or 'Member loans unavailable'})
            return
        if self.path=='/api/system':
            if not OPEN_ADMIN:self.send_error(403);return
            self.reply_json(200,system_status());return
        if urlsplit(self.path).path in ('/api/catalog','/api/product','/api/types'):
            try:
                client=Homebox(ROOT)
                if urlsplit(self.path).path=='/api/catalog':data=catalog(client)
                elif urlsplit(self.path).path=='/api/types':data=client.call('/api/v1/entity-types')
                else:data=lookup(client,parse_qs(urlsplit(self.path).query).get('gtin',[''])[0])
                self.reply_json(200,data)
            except (ValueError,KeyError):self.reply_json(400,{'error':'Barcode or catalog data needs review'})
            except OSError:self.reply_json(503,{'error':'Native catalog unavailable'})
            return
        if urlsplit(self.path).path=='/api/map':
            try:
                entity_id=parse_qs(urlsplit(self.path).query).get('entity',[None])[0]
                self.reply_json(200,list_map(Homebox(ROOT),entity_id))
            except (ValueError,TypeError,KeyError):self.reply_json(400,{'error':'Map or location needs review'})
            except OSError:self.reply_json(503,{'error':'C-Crate map unavailable'})
            return
        if self.path=='/api/session' and self.session.current() is None:
            snapshot=self.session.snapshot()
            self.reply_json(200,{'user':None,'generation':snapshot[1],'instance':self.session.instance,'return_only':self.session.returning(snapshot[1],self.session.instance)});return
        if urlsplit(self.path).path=='/api/history':
            try:
                group,members=native_context()
                entity_id=parse_qs(urlsplit(self.path).query).get('entity',[None])[0]
                client=Homebox(ROOT);client.tenant=group
                rows=desktop_history({'client':client,'group':group},globals(),entity_id)
                labels={e['id']:e['name'] for e in client.entities()+client.entities(True)}
                labels.update({m['id']:m['name'] for m in members});labels.update({t['id']:t['name'] for t in client.call('/api/v1/templates')});labels.update({t['id']:t['name'] for t in client.call('/api/v1/entity-types')})
                for row in rows:row['asset_names']=[labels.get(key,'Deleted native record') for key in row['assets']]
                self.reply_json(200,rows)
            except (ValueError,KeyError):self.reply_json(400,{'error':'Invalid history request'})
            except OSError:self.reply_json(503,{'error':'C-Crate unavailable'})
            return
        if self.path=='/api/recovery':
            if not OPEN_ADMIN:self.send_error(403);return
            try:
                client=Homebox(ROOT);group=client.call('/api/v1/users/self')['item']['defaultGroupId'];client.tenant=group
                rows=recovery_rows({'client':client,'group':group},globals())
                self.reply_json(200,rows)
            except (OSError,ValueError,KeyError):self.reply_json(503,{'error':'Recovery data unavailable'})
            return
        if urlsplit(self.path).path=='/api/entity':
            try:
                entity_id=parse_qs(urlsplit(self.path).query).get('id',[''])[0]
                entity=Homebox(ROOT).entity(entity_id)
                self.reply_json(200,{'entity':entity,'condition':condition(entity),'states':STATES,'return_states':RETURN_STATES,'blocker':checkout_blocker(entity)} )
            except (ValueError,KeyError):self.reply_json(400,{'error':'Invalid asset'})
            except OSError:self.reply_json(503,{'error':'C-Crate unavailable'})
            return
        if urlsplit(self.path).path=='/':
            body=(terminal_assets()/'index.html').read_bytes();mime='text/html; charset=utf-8';code=200
        elif self.path in ('/caci-create.svg','/favicon.svg','/favicon.ico'):
            body=(terminal_assets()/'branding'/self.path.lstrip('/')).read_bytes();mime='image/x-icon' if self.path.endswith('.ico') else 'image/svg+xml';code=200
        elif self.path=='/terminal.css':
            body=(terminal_assets()/'terminal.css').read_bytes();mime='text/css; charset=utf-8';code=200
        elif self.path=='/terminal.js':
            body=(terminal_assets()/'terminal.js').read_bytes();mime='text/javascript; charset=utf-8';code=200
        elif self.path=='/checkout-ui.js':
            body=(terminal_assets()/'checkout-ui.js').read_bytes();mime='text/javascript; charset=utf-8';code=200
        elif self.path=='/workshop-ui.js':
            body=(terminal_assets()/'workshop-ui.js').read_bytes();mime='text/javascript; charset=utf-8';code=200
        elif self.path in ('/workflow-ui.js','/return-ui.js','/member-avatar.js','/users-ui.js','/label-editor.js','/scanner_input.js'):
            body=(terminal_assets()/self.path.lstrip('/')).read_bytes();mime='text/javascript; charset=utf-8';code=200
        elif self.path=='/import-ui.js':
            body=(terminal_assets()/'import-ui.js').read_bytes();mime='text/javascript; charset=utf-8';code=200
        elif self.path in ('/api/members','/api/badges','/api/session','/api/custody'):
            if self.path=='/api/badges' and not OPEN_ADMIN:self.send_error(403);return
            try:
                snapshot=self.session.snapshot()
                group,members=native_context()
                if self.path=='/api/members':data=[{key:m.get(key,'') for key in ('id','name','email','avatar')} for m in members]
                elif self.path=='/api/custody':
                    data=ledger.custody(group)
                    names={m['id']:m['name'] for m in members}
                    for row in data:row['borrower']=names.get(row['actor_id'],'Former C-Crate member')
                elif self.path=='/api/badges':data=badges.list(group)
                else:
                    with lock:
                        member=next((m for m in members if m['id']==snapshot[0]),None)
                        if not member:self.session.end(snapshot[1])
                    data={'user':{'id':member['id'],'name':member['name']} if member else None,'generation':snapshot[1],'instance':self.session.instance,'return_only':self.session.returning(snapshot[1],self.session.instance)}
                self.reply_json(200,data)
            except (OSError,ValueError,KeyError):self.reply_json(503,{'error':'C-Crate unavailable'})
            return
        elif self.path in ('/api/inventory','/api/locations'):
            try:
                with lock:body=json.dumps(inventory(self.path=='/api/locations')).encode()
                code=200
            except (OSError,ValueError,KeyError):body=b'{"error":"C-Crate unavailable"}';code=503
            mime='application/json'
        else:body=b'Not found';mime='text/plain';code=404
        self.send_response(code);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
    def log_message(self,*args):pass
if _fixture_context:
    _fixture_root,_fixture_ready=_fixture_context
    _fixture_host='127.0.0.1';_fixture_port=0
elif os.environ.get('WORKSHOP_LOCAL_TEST_NATIVE') == '1':
    _fixture_host='127.0.0.1';_fixture_port=17749
else:
    _fixture_host='0.0.0.0';_fixture_port=17749
_fixture_server=ThreadingHTTPServer((_fixture_host,_fixture_port),Handler)
if _fixture_context:
    _fixture_ready.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    _fixture_ready.write_text(json.dumps({'mode':'fixture-process','pid':os.getpid(),
        'host':_fixture_server.server_address[0],'port':_fixture_server.server_address[1],
        'code_root':str(CODE_ROOT),'terminal_root':str(terminal_assets()),
        'module_origins':{name:str(sys.modules[name].__file__) for name in ('workshop','ledger','desktop_api')},
        'physical_boundary':'pre-import stubs'},sort_keys=True))
else:
    print(f'Homebox companion listening on {_fixture_host}:17749',flush=True)
_fixture_server.serve_forever()
