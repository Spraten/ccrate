#!/usr/bin/env python3
"""Loopback Homebox companion with browser-owned badge sessions."""
import base64, io, json, os, pathlib, stat, sys, tempfile, threading, time, urllib.request, urllib.error
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
LABEL_ASSET_ROOT=pathlib.Path(CODE_ROOT/'label-ui' if CODE_ROOT_ENV else os.environ.get('WORKSHOP_LABEL_ASSET_ROOT',CODE_ROOT/'work/label-ui-build')).resolve()
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
from checkout import confirm_checkout, checkout_availability, checkout_status_actor
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

# Explicitly approved temporary setup mode; loopback only.
OPEN_ADMIN=True
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
        if desktop_handle(self,{'root':ROOT,'lock':lock,'ledger':ledger,'checkout_cart':checkout_cart,'shelf_checks':shelf_checks,'badges':badges,'native_jobs':native_jobs,'imports':imports,'workshop':workshop,'sessions':sessions,'label_layouts':label_layouts,'label_asset_root':LABEL_ASSET_ROOT}):return
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
                        if frame.width>1280 or frame.height>960:self.senu×Þ÷¶‰žËkºwµçI½È¥ô¤(€€€€€€€€€€€•á•ÁÐ½¹™±¥Ð…Ì•ÉÉ½ÈéÍ•±˜¹É•Á±å}©Í½¸ ÐÀä±ì•ÉÉ½ÈœéÍÑÈ¡•ÉÉ½È¥ô¤(€€€€€€€€€€€•á•ÁÐ=MÉÉ½È…Ì•ÉÉ½ÈéÍ•±˜¹É•Á±å}©Í½¸ ÔÀÌ±ì•ÉÉ½ÈœéÍÑÈ¡•ÉÉ½È¤½È€µÉ…Ñ”Õ¹…Ù…¥±…‰±”ô¤(€€€€€€€€€€€É•ÑÕÉ¸(€€€€€€€Ñ•Éµ¥¹…±}Á…Ñ õÕÉ±ÍÁ±¥Ð¡Í•±˜¹Á…Ñ ¤(€€€€€€€¥˜Ñ•Éµ¥¹…±}Á…Ñ ¹Á…Ñ ¹ÍÑ…ÉÑÍÝ¥Ñ  œ½Ý½É­Í¡½À½¡•­Ì¼œ¤è(€€€€€€€€€€€É½ÕÑ”õÑ•Éµ¥¹…±}Á…Ñ ¹Á…Ñ ¹ÉÍÁ±¥Ð œ¼œ°Ä¥lÅt(€€€€€€€€€€€¥˜É½ÕÑ”¹½Ð¥¸€ ±¥ÍÐœ°•Ðœ¤è(€€€€€€€€€€€€€€€Í•±˜¹Í•¹‘}•ÉÉ½È ÐÀÔ¤íÉ•ÑÕÉ¸(€€€€€€€€€€€ÑÉäè(€€€€€€€€€€€€€€€ÅÕ•ÉäõÁ…ÉÍ•}ÅÌ¡Ñ•Éµ¥¹…±}Á…Ñ ¹ÅÕ•Éä±­••Á}‰±…¹­}Ù…±Õ•ÌõQÉÕ”¤(€€€€€€€€€€€€€€€¥˜…¹ä¡±•¸¡Ù…±Õ•Ì¤„ôÄ™½ÈÙ…±Õ•Ì¥¸ÅÕ•Éä¹Ù…±Õ•Ì ¤¤è(€€€€€€€€€€€€€€€€€€€É…¥Í”Y…±Õ•ÉÉ½È M¡•±˜µ¡•¬ÅÕ•Éä™¥•±‘Ìµ…ä…ÁÁ•…È½¹±ä½¹”œ¤(€€€€€€€€€€€€€€€‘…Ñ„õí­•äéÙ…±Õ•ÍlÁt™½È­•ä±Ù…±Õ•Ì¥¸ÅÕ•Éä¹¥Ñ•µÌ ¥ô(€€€€€€€€€€€€€€€¥˜É½ÕÑ”ôô±¥ÍÐœ…¹€±¥µ¥Ðœ¥¸‘…Ñ„è(€€€€€€€€€€€€€€€€€€€‘…Ñ…l±¥µ¥Ðtõ¥¹Ð¡‘…Ñ…l±¥µ¥Ðt¤(€€€€€€€€€€€€€€€Ý¥Ñ ±½¬è(€€€€€€€€€€€€€€€€€€€±¥•¹Ðõ!½µ•‰½à¡I==P¤(€€€€€€€€€€€€€€€€€€€ÑàõÑ•Éµ¥¹…±}¡•­}½¹Ñ•áÐ¡±¥•¹Ð±½Á•¹}…‘µ¥¸õ=A9}5%8¤(€€€€€€€€€€€€€€€€€€€É•ÍÕ±ÐõÍ¡•±™}¡•­}…Ñ¥½¸¡Í¡•±™}¡•­Ì±±¥•¹Ð±Ñà±É½ÕÑ”±‘…Ñ„¤(€€€€€€€€€€€€€€€Í•±˜¹É•Á±å}©Í½¸ ÈÀÀ±É•ÍÕ±Ð¤(€€€€€€€€€€€•á•ÁÐ¡•­•ÍÍ•¹¥•…Ì•ÉÉ½Èè(€€€€€€€€€€€€€€€Í•±˜¹É•Á±å}©Í½¸ ÐÀÌ±ì•ÉÉ½ÈœéÍÑÈ¡•ÉÉ½È¤°É•…Í½¸œéÍÑÈ¡•ÉÉ½È¥ô¤(€€€€€€€€€€€•á•ÁÐ€¡Y…±Õ•ÉÉ½È±QåÁ•ÉÉ½È±-•åÉÉ½È±ÑÑÉ¥‰ÕÑ•ÉÉ½È¤…Ì•ÉÉ½Èè(€€€€€€€€€€€€€€€Í•±˜¹É•Á±å}©Í½¸ ÐÀÀ±ì•ÉÉ½ÈœéÍÑÈ¡•ÉÉ½È¤°É•…Í½¸œéÍÑÈ¡•ÉÉ½È¥ô¤(€€€€€€€€€€€•á•ÁÐ=MÉÉ½È…Ì•ÉÉ½Èè(€€€€€€€€€€€€€€€Í•±˜¹É•Á±å}©Í½¸ ÔÀÌ±ì•ÉÉ½ÈœéÍÑÈ¡•ÉÉ½È¤½È€µÉ…Ñ”Õ¹…Ù…¥±…‰±”œ°É•…Í½¸œéÍÑÈ¡•ÉÉ½È¥ô¤(€€€€€€€€€€€É•ÑÕÉ¸(€€€€€€€¥˜Í•±˜¹Á…Ñ ¹ÍÑ…ÉÑÍÝ¥Ñ  œ½±…‰•°µ…ÍÍ•ÑÌ¼œ¤è(€€€€€€€€€€€™É½´‘•Í­Ñ½Á}…Á¤¥µÁ½ÉÐÍ•ÉÙ•}±…‰•±}…ÍÍ•Ð(€€€€€€€€€€€Í•ÉÙ•}±…‰•±}…ÍÍ•Ð¡Í•±˜±I==P±Í•±˜¹Á…Ñ¡m±•¸ œ½±…‰•°µ…ÍÍ•ÑÌ¼œ¤ét±1	1}MMQ}I==P¤íÉ•ÑÕÉ¸(€€€€€€€¥˜Í•±˜¹Á…Ñ ôôœ½±…‰•°½•ÅÕ¥Áµ•¹Ðœè(€€€€€€€€€€€¥˜¹½Ð=A9}5%8éÍ•±˜¹Í•¹‘}•ÉÉ½È ÐÀÌ¤íÉ•ÑÕÉ¸(€€€€€€€€€€€‘•…‘±¥¹”õÑ¥µ”¹µ½¹½Ñ½¹¥Œ ¤¬ÈÀ(€€€€€€€€€€€¥˜¹½Ð±½¬¹…ÅÕ¥É”¡Ñ¥µ•½ÕÐôÈ¤éÍ•±˜¹É•Á±å}©Í½¸ ÔÀÌ±ì•ÉÉ½Èœè1…‰•°•ÅÕ¥Áµ•¹Ð¥Ì‰ÕÍä¸QÉä……¥¸ô¤íÉ•ÑÕÉ¸(€€€€€€€€€€€ÑÉäè(€€€€€€€€€€€€€€€Í•ÍÍ¥½¹}…Ñ½È±•¹•É…Ñ¥½¸õÍ•±˜¹Í•ÍÍ¥½¸¹Í¹…ÁÍ¡½Ð ¤í¥¹ÍÑ…¹”õÍ•±˜¹Í•ÍÍ¥½¸¹¥¹ÍÑ…¹”(€€€€€€€€€€€€€€€±¥•¹Ð±¹…Ñ¥Ù”±É½ÕÀ±…Ñ½Èõ±…‰•±}½¹Ñ•áÐ¡‘•…‘±¥¹”±Í•ÍÍ¥½¹}…Ñ½È¤(€€€€€€€€€€€€€€€¥Ñ•µÌõmì¥œéÉ½Ýl¥t°¹…µ”œéÉ½Ü¹•Ð ¹…µ”œ°œœ¤°…ÍÍ•Ñ%œéÉ½Ü¹•Ð …ÍÍ•Ñ%œ°œœ¤°ÕÁ‘…Ñ•‘ÐœéÉ½Ü¹•Ð ÕÁ‘…Ñ•‘Ðœ¤°Á…É•¹ÐœéÉ½Ü¹•Ð Á…É•¹Ðœ¥ô™½ÈÉ½Ü¥¸±¥•¹Ð¹•¹Ñ¥Ñ¥•Ì¡…±Í”¤¥˜¹½ÐÉ½Ü¹•Ð …É¡¥Ù•œ¤…¹¹½ÐÉ½Ü¹•Ð ¥Í1½…Ñ¥½¸œ¤…¹¹½Ð€¡É½Ü¹•Ð •¹Ñ¥ÑåQåÁ”œ¤½Èíô¤¹•Ð ¥Í1½…Ñ¥½¸œ¥t(€€€€€€€€€€€€€€€¥˜Ñ¥µ”¹µ½¹½Ñ½¹¥Œ ¤øõ‘•…‘±¥¹”½ÈÍ•±˜¹Í•ÍÍ¥½¸¹¥¹ÍÑ…¹”„õ¥¹ÍÑ…¹”½ÈÍ•±˜¹Í•ÍÍ¥½¸¹Í¹…ÁÍ¡½Ð ¤„ô¡Í•ÍÍ¥½¹}…Ñ½È±•¹•É…Ñ¥½¸¤éÉ…¥Í”½¹™±¥Ð 1…‰•°½¹Ñ•áÐ¡…¹•ìÉ•±½…Ñ¡”¥Ñ•´ÅÕ•Õ”œ¤(€€€€€€€€€€€€€€€Í•±˜¹É•Á±å}©Í½¸ ÈÀÀ±¥Ñ•µÌ¤(€€€€€€€€€€€•á•ÁÐ€¡Y…±Õ•ÉÉ½È±-•åÉÉ½È±=MÉÉ½È±Q¥µ•½ÕÑÉÉ½È±½¹™±¥Ð¤…Ì•ÉÉ½ÈéÍ•±˜¹É•Á±å}©Í½¸ ÔÀÌ±ì•ÉÉ½ÈœéÍÑÈ¡•ÉÉ½È¤½È€1…‰•°•ÅÕ¥Áµ•¹Ð¥ÌÕ¹…Ù…¥±…‰±”ô¤(€€€€€€€€€€€™¥¹…±±äé±½¬¹É•±•…Í” ¤(€€€€€€€€€€€É•ÑÕÉ¸(€€€€€€€¥˜Í•±˜¹Á…Ñ ôôœ½±…‰•°½Ñ•µÁ±…Ñ•Ìœè(€€€€€€€€€€€¥˜¹½Ð=A9}5%8éÍ•±˜¹Í•¹‘}•ÉÉ½È ÐÀÌ¤íÉ•ÑÕÉ¸(€€€€€€€€€€€‘•…‘±¥¹”õÑ¥µ”¹µ½¹½Ñ½¹¥Œ ¤¬ÈÀ(€€€€€€€€€€€¥˜¹½Ð±½¬¹…ÅÕ¥É”¡Ñ¥µ•½ÕÐôÈ¤éÍ•±˜¹É•Á±å}©Í½¸ ÔÀÌ±ì•ÉÉ½Èœè1…‰•°Í•ÉÙ¥”¥Ì‰ÕÍä¸QÉä……¥¸ô¤íÉ•ÑÕÉ¸(€€€€€€€€€€€ÑÉäè(€€€€€€€€€€€€€€€Í•ÍÍ¥½¹}…Ñ½È±•¹•É…Ñ¥½¸õÍ•±˜¹Í•ÍÍ¥½¸¹Í¹…ÁÍ¡½Ð ¤í¥¹ÍÑ…¹”õÍ•±˜¹Í•ÍÍ¥½¸¹¥¹ÍÑ…¹”(€€€€€€€€€€€€€€€±¥•¹Ð±¹…Ñ¥Ù”±É½ÕÀ±…Ñ½Èõ±…‰•±}½¹Ñ•áÐ¡‘•…‘±¥¹”±Í•ÍÍ¥½¹}…Ñ½È¤(€€€€€€€€€€€€€€€±…‰•±}±…å½ÕÑÌ¹É•½¹¥±•}É•Ù¥•ÝÌ¡É½ÕÀ±¹…Ñ¥Ù•}©½‰Ì¤(€€€€€€€€€€€€€€€É•ÍÕ±Ðõ±…‰•±}±…å½ÕÑÌ¹±¥ÍÐ¡É½ÕÀ¤(€€€€€€€€€€€€€€€¥˜Ñ¥µ”¹µ½¹½Ñ½¹¥Œ ¤øõ‘•…‘±¥¹”½ÈÍ•±˜¹Í•ÍÍ¥½¸¹¥¹ÍÑ…¹”„õ¥¹ÍÑ…¹”½ÈÍ•±˜¹Í•ÍÍ¥½¸¹Í¹…ÁÍ¡½Ð ¤„ô¡Í•ÍÍ¥½¹}…Ñ½È±•¹•É…Ñ¥½¸¤éÉ…¥Í”½¹™±¥Ð 1…‰•°½¹Ñ•áÐ¡…¹•ìÉ•±½…Ñ•µÁ±…Ñ•Ìœ¤(€€€€€€€€€€€€€€€Í•±˜¹É•Á±å}©Í½¸ ÈÀÀ±É•ÍÕ±Ð¤(€€€€€€€€€€€•á•ÁÐ€¡Y…±Õ•ÉÉ½È±=MÉÉ½È±Q¥µ•½ÕÑÉÉ½È¤…Ì•ÉÉ½ÈéÍ•±˜¹É•Á±å}©Í½¸ ÔÀÌ±ì•ÉÉ½ÈœéÍÑÈ¡•ÉÉ½È¥ô¤(€€€€€€€€€€€™¥¹…±±äé±½¬¹É•±•…Í” ¤(€€€€€€€€€€€É•ÑÕÉ¸(€€€€€€€¥˜Í•±˜¹Á…Ñ ¹ÍÑ…ÉÑÍÝ¥Ñ  œ½…Á¤¼œ¤è(€€€€€€€€€€€ÑÉäéÍ•±˜¹Í•ÍÍ¥½¸(€€€€€€€€€€€•á•ÁÐY…±Õ•ÉÉ½È…Ì•ÉÉ½ÈéÍ•±˜¹É•Á±å}©Í½¸ ÐÀÀ±ì•ÉÉ½ÈœéÍÑÈ¡•ÉÉ½È¥ô¤íÉ•ÑÕÉ¸(€€€€€€€¥˜Í•±˜¹Á…Ñ ôôœ½…Á¤½…µ•É„œè(€€€€€€€€€€€Í•±˜¹É•Á±å}©Í½¸ ÈÀÀ±…µ•É…}ÍÑ…Ñ” ¤¤íÉ•ÑÕÉ¸(€€€€€€€¥˜ÕÉ±ÍÁ±¥Ð¡Í•±˜¹Á…Ñ ¤¹Á…Ñ ôôœ½…Á¤½™¥±”œè(€€€€€€€€€€€ÑÉäè(€€€€€€€€€€€€€€€™É½´±•‘•È¥µÁ½ÉÐÕÕ¥(€€€€€€€€€€€€€€€ÅÕ•ÉäõÁ…ÉÍ•}ÅÌ¡ÕÉ±ÍÁ±¥Ð¡Í•±˜¹Á…Ñ ¤¹ÅÕ•Éä¤í•¹Ñ¥Ñå}¥õÕÕ¥¡ÅÕ•Éä¹•Ð •¹Ñ¥Ñäœ±m9½¹•t¥lÁt¤í…ÑÑ…¡µ•¹Ñ}¥õÕÕ¥¡ÅÕ•Éä¹•Ð …ÑÑ…¡µ•¹Ðœ±m9½¹•t¥lÁt¤í±¥•¹Ðõ!½µ•‰½à¡I==P¤í•¹Ñ¥Ñäõ±¥•¹Ð¹•¹Ñ¥Ñä¡•¹Ñ¥Ñå}¥¤(€€€€€€€€€€€€€€€…ÑÑ…¡µ•¹Ðõ¹•áÐ¡„™½È„¥¸•¹Ñ¥Ñä¹•Ð …ÑÑ…¡µ•¹ÑÌœ±mt¤¥˜…l¥tôõ…ÑÑ…¡µ•¹Ñ}¥¤(€€€€€€€€€€€€€€€É•ÅÕ•ÍÐõÕÉ±±¥ˆ¹É•ÅÕ•ÍÐ¹I•ÅÕ•ÍÐ¡±¥•¹Ð¹‰…Í”¬œ½…Á¤½ØÄ½•¹Ñ¥Ñ¥•Ì¼œ­•¹Ñ¥Ñå}¥¬œ½…ÑÑ…¡µ•¹ÑÌ¼œ­…ÑÑ…¡µ•¹Ñ}¥±¡•…‘•ÉÌõìÕÑ¡½É¥é…Ñ¥½¸œè	•…É•È€œ­±¥•¹Ð¹Ñ½­•¹ô¤(€€€€€€€€€€€€€€€±…ÍÌ1½…±I•‘¥É•Ð¡ÕÉ±±¥ˆ¹É•ÅÕ•ÍÐ¹!QQAI•‘¥É•Ñ!…¹‘±•È¤è(€€€€€€€€€€€€€€€€€€€‘•˜É•‘¥É•Ñ}É•ÅÕ•ÍÐ¡Í•±˜±É•ÅÕ•ÍÐ±™À±½‘”±µÍœ±¡•…‘•ÉÌ±¹•ÝÕÉ°¤è(€€€€€€€€€€€€€€€€€€€€€€€‘•ÍÑ¥¹…Ñ¥½¸õÕÉ±ÍÁ±¥Ð¡¹•ÝÕÉ°¤(€€€€€€€€€€€€€€€€€€€€€€€¥˜‘•ÍÑ¥¹…Ñ¥½¸¹¡½ÍÑ¹…µ”„ôœÄÈÜ¸À¸À¸Äœ½È‘•ÍÑ¥¹…Ñ¥½¸¹Á½ÉÐ„ôÄÜÜÐÔéÉ…¥Í”Y…±Õ•ÉÉ½È áÑ•É¹…°™¥±”Õ¹…Ù…¥±…‰±”½™™±¥¹”œ¤(€€€€€€€€€€€€€€€€€€€€€€€É•ÑÕÉ¸ÍÕÁ•È ¤¹É•‘¥É•Ñ}É•ÅÕ•ÍÐ¡É•ÅÕ•ÍÐ±™À±½‘”±µÍœ±¡•…‘•ÉÌ±¹•ÝÕÉ°¤(€€€€€€€€€€€€€€€Ý¥Ñ ÕÉ±±¥ˆ¹É•ÅÕ•ÍÐ¹‰Õ¥±‘}½Á•¹•È¡1½…±I•‘¥É•Ð ¤¤¹½Á•¸¡É•ÅÕ•ÍÐ±Ñ¥µ•½ÕÐôÄÔ¤…ÌÉ•ÍÁ½¹Í”è(€€€€€€€€€€€€€€€€€€€½¹Ñ•¹ÐõÉ•ÍÁ½¹Í”¹É•… ÄÀÀÀÀÀÀÄ¤íµ¥µ”õÉ•ÍÁ½¹Í”¹¡•…‘•ÉÌ¹•Ñ}½¹Ñ•¹Ñ}ÑåÁ” ¤(€€€€€€€€€€€€€€€¥˜±•¸¡½¹Ñ•¹Ð¤øÄÀÀÀÀÀÀÀéÉ…¥Í”Y…±Õ•ÉÉ½È ¥±”•á••‘Ì­¥½Í¬ÁÉ•Ù¥•Ü±¥µ¥Ðœ¤(€€€€€€€€€€€€€€€Í•±˜¹Í•¹‘}É•ÍÁ½¹Í” ÈÀÀ¤íÍ•±˜¹Í•¹‘}¡•…‘•È ½¹Ñ•¹ÐµQåÁ”œ±µ¥µ”¤íÍ•±˜¹Í•¹‘}¡•…‘•È ½¹Ñ•¹Ðµ1•¹Ñ œ±ÍÑÈ¡±•¸¡½¹Ñ•¹Ð¤¤¤íÍ•±˜¹Í•¹‘}¡•…‘•È `µ½¹Ñ•¹ÐµQåÁ”µ=ÁÑ¥½¹Ìœ°¹½Í¹¥™˜œ¤íÍ•±˜¹Í•¹‘}¡•…‘•È …¡”µ½¹ÑÉ½°œ°¹¼µÍÑ½É”œ¤(€€€€€€€€€€€€€€€¥˜µ¥µ”¹½Ð¥¸€ ¥µ…”½©Á•œœ°¥µ…”½Á¹œœ°¥µ…”½Ý•‰Àœ°¥µ…”½¥˜œ¤éÍ•±˜¹Í•¹‘}¡•…‘•È ½¹Ñ•¹Ðµ¥ÍÁ½Í¥Ñ¥½¸œ°…ÑÑ…¡µ•¹Ðœ¤(€€€€€€€€€€€€€€€Í•±˜¹•¹‘}¡•…‘•ÉÌ ¤íÍ•±˜¹Ý™¥±”¹ÝÉ¥Ñ”¡½¹Ñ•¹Ð¤(€€€€€€€€€€€•á•ÁÐ€¡=MÉÉ½È±Y…±Õ•ÉÉ½È±MÑ½Á%Ñ•É…Ñ¥½¸¤éÍ•±˜¹É•Á±å}©Í½¸ ÐÀÐ±ì•ÉÉ½Èœè9…Ñ¥Ù”™¥±”Õ¹…Ù…¥±…‰±”ô¤(€€€€€€€€€€€É•ÑÕÉ¸(€€€€€€€¥˜ÕÉ±ÍÁ±¥Ð¡Í•±˜¹Á…Ñ ¤¹Á…Ñ ôôœ½…Á¤½ÍÑ½¬œè(€€€€€€€€€€€ÑÉäéÍ•±˜¹É•Á±å}©Í½¸ ÈÀÀ±‰É½ÝÍ•}ÍÑ½¬¡!½µ•‰½à¡I==P¤°É•™É•Í œ¥¸Á…ÉÍ•}ÅÌ¡ÕÉ±ÍÁ±¥Ð¡Í•±˜¹Á…Ñ ¤¹ÅÕ•Éä¤¤¤(€€€€€€€€€€€•á•ÁÐ€¡=MÉÉ½È±Y…±Õ•ÉÉ½È¤éÍ•±˜¹É•Á±å}©Í½¸ ÔÀÌ±ì•ÉÉ½Èœè9…Ñ¥Ù”ÍÑ½¬Õ¹…Ù…¥±…‰±”ô¤(€€€€€€€€€€€É•ÑÕÉ¸(€€€€€€€¥˜ÕÉ±ÍÁ±¥Ð¡Í•±˜¹Á…Ñ ¤¹Á…Ñ ôôœ½…Á¤½µ…¥¹Ñ•¹…¹”œè(€€€€€€€€€€€ÑÉäè(€€€€€€€€€€€€€€€™É½´±•‘•È¥µÁ½ÉÐÕÕ¥(€€€€€€€€€€€€€€€•¹Ñ¥Ñå}¥õÕÕ¥¡Á…ÉÍ•}ÅÌ¡ÕÉ±ÍÁ±¥Ð¡Í•±˜¹Á…Ñ ¤¹ÅÕ•Éä¤¹•Ð •¹Ñ¥Ñäœ±m9½¹•t¥lÁt¤íÍ•±˜¹É•Á±å}©Í½¸ ÈÀÀ±!½µ•‰½à¡I==P¤¹…±° œ½…Á¤½ØÄ½•¹Ñ¥Ñ¥•Ì¼œ­•¹Ñ¥Ñå}¥¬œ½µ…¥¹Ñ•¹…¹”œ¤¤(€€€€€€€€€€€•á•ÁÐ€¡=MÉÉ½È±Y…±Õ•ÉÉ½È¤éÍ•±˜¹É•Á±å}©Í½¸ ÔÀÌ±ì•ÉÉ½Èœè9…Ñ¥Ù”µ…¥¹Ñ•¹…¹”Õ¹…Ù…¥±…‰±”ô¤(€€€€€€€€€€€É•ÑÕÉ¸(€€€€€€€¥˜ÕÉ±ÍÁ±¥Ð¡Í•±˜¹Á…Ñ ¤¹Á…Ñ ôôœ½…Á¤½­¥Ðœè(€€€€€€€€€€€ÑÉäè(€€€€€€€€€€€€€€€‘…Ñ„õ­¥Ñ}µ…¹¥™•ÍÐ¡!½µ•‰½à¡I==P¤±Á…ÉÍ•}ÅÌ¡ÕÉ±ÍÁ±¥Ð¡Í•±˜¹Á…Ñ ¤¹ÅÕ•Éä¤¹•Ð ¥œ±m9½¹•t¥lÁt¤í‘…Ñ…lÙ•É¥™¥•tõ±¥ÍÐ¡Í•±˜¹Í•ÍÍ¥½¸¹Í…¹Ì¡Í•±˜¹Í•ÍÍ¥½¸¹Í¹…ÁÍ¡½Ð ¥lÅt¤¤íÍ•±˜¹É•Á±å}©Í½¸ ÈÀÀ±‘…Ñ„¤(€€€€€€€€€€€•á•ÁÐ€¡Y…±Õ•ÉÉ½È±=MÉÉ½È¤éÍ•±˜¹É•Á±å}©Í½¸ ÐÀÀ±ì•ÉÉ½Èœè-¥Ðµ…¹¥™•ÍÐ½È¹…Ñ¥Ù”•ÅÕ¥Áµ•¹Ð¹••‘ÌÉ•Ù¥•Üô¤(€€€€€€€€€€€É•ÑÕÉ¸(€€€€€€€¥˜ÕÉ±ÍÁ±¥Ð¡Í•±˜¹Á…Ñ ¤¹Á…Ñ ôôœ½…Á¤½ÕÍ•ÈµÁÉ½™¥±”œè(€€€€€€€€€€€¥˜¹½Ð=A9}5%8éÍ•±˜¹Í•¹‘}•ÉÉ½È ÐÀÌ¤íÉ•ÑÕÉ¸(€€€€€€€€€€€ÑÉäéÍ•±˜¹É•Á±å}©Í½¸ ÈÀÀ±•Ñ}ÁÉ½™¥±”¡!½µ•‰½à¡I==P¤±Á…ÉÍ•}ÅÌ¡ÕÉ±ÍÁ±¥Ð¡Í•±˜¹Á…Ñ ¤¹ÅÕ•Éä¤¹•Ð ¥œ±m9½¹•t¥lÁt¤¤(€€€€€€€€€€€•á•ÁÐÕÉ±±¥ˆ¹•ÉÉ½È¹!QQAÉÉ½È…Ì•ÉÉ½ÈéÍ•±˜¹É•Á±å}©Í½¸¡•ÉÉ½È¹½‘”±ì•ÉÉ½Èœè½Õ±¹½ÐÉ•…Ñ¡¥Ìµ•µ‰•ÈÁÉ½™¥±”ô¤(€€€€€€€€€€€•á•ÁÐ€¡Y…±Õ•ÉÉ½È±=MÉÉ½È¤éÍ•±˜¹É•Á±å}©Í½¸ ÐÀÀ±ì•ÉÉ½Èœè¡½½Í”„ÕÉÉ•¹ÐÕÍ•È…¹É•±½…Ñ¡•¥ÈÁÉ½™¥±”ô¤(€€€€€€€€€€€É•ÑÕÉ¸(€€€€€€€¥˜ÕÉ±ÍÁ±¥Ð¡Í•±˜¹Á…Ñ ¤¹Á…Ñ ôôœ½…Á¤½µ•µ‰•Èµ±½…¹Ìœè(€€€€€€€€€€€¥˜¹½Ð=A9}5%8éÍ•±˜¹Í•¹‘}•ÉÉ½È ÐÀÌ¤íÉ•ÑÕÉ¸(€€€€€€€€€€€ÑÉäè(€€€€€€€€€€€€€€€Ý¥Ñ ±½¬è(€€€€€€€€€€€€€€€€€€€±¥•¹Ðõ!½µ•‰½à¡I==P¤í¹…Ñ¥Ù”õ±¥•¹Ð¹…±° œ½…Á¤½ØÄ½ÕÍ•ÉÌ½Í•±˜œ¥l¥Ñ•´t(€€€€€€€€€€€€€€€€€€€É½ÕÀõ¹…Ñ¥Ù•l‘•™…Õ±ÑÉ½ÕÁ%tí±¥•¹Ð¹Ñ•¹…¹ÐõÉ½ÕÀ(€€€€€€€€€€€€€€€€€€€Ñàõì±¥•¹Ðœé±¥•¹Ð°É½ÕÀœéÉ½ÕÀ°½±±•Ñ¥½¸œéÉ½ÕÀ°…Ñ½Èœé¹…Ñ¥Ù•l¥t°(€€€€€€€€€€€€€€€€€€€€€€€€€ÕÍ•Èœé¹…Ñ¥Ù”°µ…¹…•ÈœéQÉÕ”°¥‘•¹Ñ¥Ñäœéì…Ñ½É}¥œé¹…Ñ¥Ù•l¥t°É½ÕÁ}¥œéÉ½ÕÁõô(€€€€€€€€€€€€€€€€€€€™É½´‘•Í­Ñ½Á}…Á¤¥µÁ½ÉÐ•Ñ}…Ñ¥½¸(€€€€€€€€€€€€€€€€€€€‘…Ñ„õ•Ñ}…Ñ¥½¸ ±½…¹Ìœ±íô±Ñà±±½‰…±Ì ¤¤(€€€€€€€€€€€€€€€Í•±˜¹É•Á±å}©Í½¸ ÈÀÀ±‘…Ñ„¤(€€€€€€€€€€€•á•ÁÐ€¡=MÉÉ½È±Y…±Õ•ÉÉ½È±-•åÉÉ½È±QåÁ•ÉÉ½È¤…Ì•ÉÉ½Èè(€€€€€€€€€€€€€€€Í•±˜¹É•Á±å}©Í½¸ ÔÀÌ±ì•ÉÉ½ÈœéÍÑÈ¡•ÉÉ½È¤½È€5•µ‰•È±½…¹ÌÕ¹…Ù…¥±…‰±”ô¤(€€€€€€€€€€€É•ÑÕÉ¸(€€€€€€€¥˜Í•±˜¹Á…Ñ ôôœ½…Á¤½ÍåÍÑ•´œè(€€€€€€€€€€€¥˜¹½Ð=A9}5%8éÍ•±˜¹Í•¹‘}•ÉÉ½È ÐÀÌ¤íÉ•ÑÕÉ¸(€€€€€€€€€€€Í•±˜¹É•Á±å}©Í½¸ ÈÀÀ±ÍåÍÑ•µ}ÍÑ…ÑÕÌ ¤¤íÉ•ÑÕÉ¸(€€€€€€€¥˜ÕÉ±ÍÁ±¥Ð¡Í•±˜¹Á…Ñ ¤¹Á…Ñ ¥¸€ œ½…Á¤½…Ñ…±½œœ°œ½…Á¤½ÁÉ½‘ÕÐœ°œ½…Á¤½ÑåÁ•Ìœ¤è(€€€€€€€€€€€ÑÉäè(€€€€€€€€€€€€€€€±¥•¹Ðõ!½µ•‰½à¡I==P¤(€€€€€€€€€€€€€€€¥˜ÕÉ±ÍÁ±¥Ð¡Í•±˜¹Á…Ñ ¤¹Á…Ñ ôôœ½…Á¤½…Ñ…±½œœé‘…Ñ„õ…Ñ…±½œ¡±¥•¹Ð¤(€€€€€€€€€€€€€€€•±¥˜ÕÉ±ÍÁ±¥Ð¡Í•±˜¹Á…Ñ ¤¹Á…Ñ ôôœ½…Á¤½ÑåÁ•Ìœé‘…Ñ„õ±¥•¹Ð¹…±° œ½…Á¤½ØÄ½•¹Ñ¥ÑäµÑåÁ•Ìœ¤(€€€€€€€€€€€€€€€•±Í”é‘…Ñ„õ±½½­ÕÀ¡±¥•¹Ð±Á…ÉÍ•}ÅÌ¡ÕÉ±ÍÁ±¥Ð¡Í•±˜¹Á…Ñ ¤¹ÅÕ•Éä¤¹•Ð Ñ¥¸œ±lœt¥lÁt¤(€€€€€€€€€€€€€€€Í•±˜¹É•Á±å}©Í½¸ ÈÀÀ±‘…Ñ„¤(€€€€€€€€€€€•á•ÁÐ€¡Y…±Õ•ÉÉ½È±-•åÉÉ½È¤éÍ•±˜¹É•Á±å}©Í½¸ ÐÀÀ±ì•ÉÉ½Èœè	…É½‘”½È…Ñ…±½œ‘…Ñ„¹••‘ÌÉ•Ù¥•Üô¤(€€€€€€€€€€€•á•ÁÐ=MÉÉ½ÈéÍ•±˜¹É•Á±å}©Í½¸ ÔÀÌ±ì•ÉÉ½Èœè9…Ñ¥Ù”…Ñ…±½œÕ¹…Ù…¥±…‰±”ô¤(€€€€€€€€€€€É•ÑÕÉ¸(€€€€€€€¥˜ÕÉ±ÍÁ±¥Ð¡Í•±˜¹Á…Ñ ¤¹Á…Ñ ôôœ½…Á¤½µ…Àœè(€€€€€€€€€€€ÑÉäè(€€€€€€€€€€€€€€€•¹Ñ¥Ñå}¥õÁ…ÉÍ•}ÅÌ¡ÕÉ±ÍÁ±¥Ð¡Í•±˜¹Á…Ñ ¤¹ÅÕ•Éä¤¹•Ð •¹Ñ¥Ñäœ±m9½¹•t¥lÁt(€€€€€€€€€€€€€€€Í•±˜¹É•Á±å}©Í½¸ ÈÀÀ±±¥ÍÑ}µ…À¡!½µ•‰½à¡I==P¤±•¹Ñ¥Ñå}¥¤¤(€€€€€€€€€€€•á•ÁÐ€¡Y…±Õ•ÉÉ½È±QåÁ•ÉÉ½È±-•åÉÉ½È¤éÍ•±˜¹É•Á±å}©Í½¸ ÐÀÀ±ì•ÉÉ½Èœè5…À½È±½…Ñ¥½¸¹••‘ÌÉ•Ù¥•Üô¤(€€€€€€€€€€€•á•ÁÐ=MÉÉ½ÈéÍ•±˜¹É•Á±å}©Í½¸ ÔÀÌ±ì•ÉÉ½ÈœèµÉ…Ñ”µ…ÀÕ¹…Ù…¥±…‰±”ô¤(€€€€€€€€€€€É•ÑÕÉ¸(€€€€€€€¥˜Í•±˜¹Á…Ñ ôôœ½…Á¤½Í•ÍÍ¥½¸œ…¹Í•±˜¹Í•ÍÍ¥½¸¹ÕÉÉ•¹Ð ¤¥Ì9½¹”è(€€€€€€€€€€€Í¹…ÁÍ¡½ÐõÍ•±˜¹Í•ÍÍ¥½¸¹Í¹…ÁÍ¡½Ð ¤(€€€€€€€€€€€Í•±˜¹É•Á±å}©Í½¸ ÈÀÀ±ìÕÍ•Èœé9½¹”°•¹•É…Ñ¥½¸œéÍ¹…ÁÍ¡½ÑlÅt°¥¹ÍÑ…¹”œéÍ•±˜¹Í•ÍÍ¥½¸¹¥¹ÍÑ…¹”°É•ÑÕÉ¹}½¹±äœéÍ•±˜¹Í•ÍÍ¥½¸¹É•ÑÕÉ¹¥¹œ¡Í¹…ÁÍ¡½ÑlÅt±Í•±˜¹Í•ÍÍ¥½¸¹¥¹ÍÑ…¹”¥ô¤íÉ•ÑÕÉ¸(€€€€€€€¥˜ÕÉ±ÍÁ±¥Ð¡Í•±˜¹Á…Ñ ¤¹Á…Ñ ôôœ½…Á¤½¡¥ÍÑ½Éäœè(€€€€€€€€€€€ÑÉäè(€€€€€€€€€€€€€€€É½ÕÀ±µ•µ‰•ÉÌõ¹…Ñ¥Ù•}½¹Ñ•áÐ ¤(€€€€€€€€€€€€€€€•¹Ñ¥Ñå}¥õÁ…ÉÍ•}ÅÌ¡ÕÉ±ÍÁ±¥Ð¡Í•±˜¹Á…Ñ ¤¹ÅÕ•Éä¤¹•Ð •¹Ñ¥Ñäœ±m9½¹•t¥lÁt(€€€€€€€€€€€€€€€±¥•¹Ðõ!½µ•‰½à¡I==P¤í±¥•¹Ð¹Ñ•¹…¹ÐõÉ½ÕÀ(€€€€€€€€€€€€€€€É½ÝÌõ‘•Í­Ñ½Á}¡¥ÍÑ½Éä¡ì±¥•¹Ðœé±¥•¹Ð°É½ÕÀœéÉ½ÕÁô±±½‰…±Ì ¤±•¹Ñ¥Ñå}¥¤(€€€€€€€€€€€€€€€±…‰•±Ìõí•l¥té•l¹…µ”t™½È”¥¸±¥•¹Ð¹•¹Ñ¥Ñ¥•Ì ¤­±¥•¹Ð¹•¹Ñ¥Ñ¥•Ì¡QÉÕ”¥ô(€€€€€€€€€€€€€€€±…‰•±Ì¹ÕÁ‘…Ñ”¡íµl¥téµl¹…µ”t™½È´¥¸µ•µ‰•ÉÍô¤í±…‰•±Ì¹ÕÁ‘…Ñ”¡íÑl¥téÑl¹…µ”t™½ÈÐ¥¸±¥•¹Ð¹…±° œ½…Á¤½ØÄ½Ñ•µÁ±…Ñ•Ìœ¥ô¤í±…‰•±Ì¹ÕÁ‘…Ñ”¡íÑl¥téÑl¹…µ”t™½ÈÐ¥¸±¥•¹Ð¹…±° œ½…Á¤½ØÄ½•¹Ñ¥ÑäµÑåÁ•Ìœ¥ô¤(€€€€€€€€€€€€€€€™½ÈÉ½Ü¥¸É½ÝÌéÉ½Ýl…ÍÍ•Ñ}¹…µ•Ìtõm±…‰•±Ì¹•Ð¡­•ä°•±•Ñ•¹…Ñ¥Ù”É•½Éœ¤™½È­•ä¥¸É½Ýl…ÍÍ•ÑÌut(€€€€€€€€€€€€€€€Í•±˜¹É•Á±å}©Í½¸ ÈÀÀ±É½ÝÌ¤(€€€€€€€€€€€•á•ÁÐ€¡Y…±Õ•ÉÉ½È±-•åÉÉ½È¤éÍ•±˜¹É•Á±å}©Í½¸ ÐÀÀ±ì•ÉÉ½Èœè%¹Ù…±¥¡¥ÍÑ½ÉäÉ•ÅÕ•ÍÐô¤(€€€€€€€€€€€•á•ÁÐ=MÉÉ½ÈéÍ•±˜¹É•Á±å}©Í½¸ ÔÀÌ±ì•ÉÉ½ÈœèµÉ…Ñ”Õ¹…Ù…¥±…‰±”ô¤(€€€€€€€€€€€É•ÑÕÉ¸(€€€€€€€¥˜Í•±˜¹Á…Ñ ôôœ½…Á¤½É•½Ù•Éäœè(€€€€€€€€€€€¥˜¹½Ð=A9}5%8éÍ•±˜¹Í•¹‘}•ÉÉ½È ÐÀÌ¤íÉ•ÑÕÉ¸(€€€€€€€€€€€ÑÉäè(€€€€€€€€€€€€€€€±¥•¹Ðõ!½µ•‰½à¡I==P¤íÉ½ÕÀõ±¥•¹Ð¹…±° œ½…Á¤½ØÄ½ÕÍ•ÉÌ½Í•±˜œ¥l¥Ñ•´ul‘•™…Õ±ÑÉ½ÕÁ%tí±¥•¹Ð¹Ñ•¹…¹ÐõÉ½ÕÀ(€€€€€€€€€€€€€€€É½ÝÌõÉ•½Ù•Éå}É½ÝÌ¡ì±¥•¹Ðœé±¥•¹Ð°É½ÕÀœéÉ½ÕÁô±±½‰…±Ì ¤¤(€€€€€€€€€€€€€€€Í•±˜¹É•Á±å}©Í½¸ ÈÀÀ±É½ÝÌ¤(€€€€€€€€€€€•á•ÁÐ€¡=MÉÉ½È±Y…±Õ•ÉÉ½È±-•åÉÉ½È¤éÍ•±˜¹É•Á±å}©Í½¸ ÔÀÌ±ì•ÉÉ½ÈœèI•½Ù•Éä‘…Ñ„Õ¹…Ù…¥±…‰±”ô¤(€€€€€€€€€€€É•ÑÕÉ¸(€€€€€€€¥˜ÕÉ±ÍÁ±¥Ð¡Í•±˜¹Á…Ñ ¤¹Á…Ñ ôôœ½…Á¤½•¹Ñ¥Ñäœè(€€€€€€€€€€€ÑÉäè(€€€€€€€€€€€€€€€•¹Ñ¥Ñå}¥õÁ…ÉÍ•}ÅÌ¡ÕÉ±ÍÁ±¥Ð¡Í•±˜¹Á…Ñ ¤¹ÅÕ•Éä¤¹•Ð ¥œ±lœt¥lÁt(€€€€€€€€€€€€€€€•¹Ñ¥Ñäõ!½µ•‰½à¡I==P¤¹•¹Ñ¥Ñä¡•¹Ñ¥Ñå}¥¤(€€€€€€€€€€€€€€€Í•±˜¹É•Á±å}©Í½¸ ÈÀÀ±ì•¹Ñ¥Ñäœé•¹Ñ¥Ñä°½¹‘¥Ñ¥½¸œé½¹‘¥Ñ¥½¸¡•¹Ñ¥Ñä¤°ÍÑ…Ñ•ÌœéMQQL°É•ÑÕÉ¹}ÍÑ…Ñ•ÌœéIQUI9}MQQL°‰±½­•Èœé¡•­½ÕÑ}‰±½­•È¡•¹Ñ¥Ñä¥ô€¤(€€€€€€€€€€€•á•ÁÐ€¡Y…±Õ•ÉÉ½È±-•åÉÉ½È¤éÍ•±˜¹É•Á±å}©Í½¸ ÐÀÀ±ì•ÉÉ½Èœè%¹Ù…±¥…ÍÍ•Ðô¤(€€€€€€€€€€€•á•ÁÐ=MÉÉ½ÈéÍ•±˜¹É•Á±å}©Í½¸ ÔÀÌ±ì•ÉÉ½ÈœèµÉ…Ñ”Õ¹…Ù…¥±…‰±”ô¤(€€€€€€€€€€€É•ÑÕÉ¸(€€€€€€€¥˜Í•±˜¹Á…Ñ ¥¸€ œ½…Á¤½µ•µ‰•ÉÌœ°œ½…Á¤½‰…‘•Ìœ°œ½…Á¤½Í•ÍÍ¥½¸œ°œ½…Á¤½ÕÍÑ½‘äœ¤è(€€€€€€€€€€€ÑÉäè(€€€€€€€€€€€€€€€Í¹…ÁÍ¡½ÐõÍ•±˜¹Í•ÍÍ¥½¸¹Í¹…ÁÍ¡½Ð ¤(€€€€€€€€€€€€€€€É½ÕÀ±µ•µ‰•ÉÌõ¹…Ñ¥Ù•}½¹Ñ•áÐ ¤(€€€€€€€€€€€€€€€¥˜Í•±˜¹Á…Ñ ôôœ½…Á¤½µ•µ‰•ÉÌœé‘…Ñ„õmí­•äé´¹•Ð¡­•ä°œœ¤™½È­•ä¥¸€ ¥œ°¹…µ”œ°•µ…¥°œ°…Ù…Ñ…Èœ¥ô™½È´¥¸µ•µ‰•ÉÍt(€€€€€€€€€€€€€€€•±¥˜Í•±˜¹Á…Ñ ôôœ½…Á¤½ÕÍÑ½‘äœè(€€€€€€€€€€€€€€€€€€€‘…Ñ„õ±•‘•È¹ÕÍÑ½‘ä¡É½ÕÀ¤(€€€€€€€€€€€€€€€€€€€¹…µ•Ìõíµl¥téµl¹…µ”t™½È´¥¸µ•µ‰•ÉÍô(€€€€€€€€€€€€€€€€€€€™½ÈÉ½Ü¥¸‘…Ñ„éÉ½Ýl‰½ÉÉ½Ý•Ètõ¹…µ•Ì¹•Ð¡É½Ýl…Ñ½É}¥t°½Éµ•ÈµÉ…Ñ”µ•µ‰•Èœ¤(€€€€€€€€€€€€€€€•±¥˜Í•±˜¹Á…Ñ ôôœ½…Á¤½‰…‘•Ìœé‘…Ñ„õ‰…‘•Ì¹±¥ÍÐ¡É½ÕÀ¤¥˜=A9}5%8•±Í”mt(€€€€€€€€€€€€€€€•±Í”è(€€€€€€€€€€€€€€€€€€€Ý¥Ñ ±½¬è(€€€€€€€€€€€€€€€€€€€€€€€µ•µ‰•Èõ¹•áÐ ¡´™½È´¥¸µ•µ‰•ÉÌ¥˜µl¥tôõÍ¹…ÁÍ¡½ÑlÁt¤±9½¹”¤(€€€€€€€€€€€€€€€€€€€€€€€¥˜¹½Ðµ•µ‰•ÈéÍ•±˜¹Í•ÍÍ¥½¸¹•¹¡Í¹…ÁÍ¡½ÑlÅt¤(€€€€€€€€€€€€€€€€€€€‘…Ñ„õìÕÍ•Èœéì¥œéµ•µ‰•Él¥t°¹…µ”œéµ•µ‰•Él¹…µ”uô¥˜µ•µ‰•È•±Í”9½¹”°•¹•É…Ñ¥½¸œéÍ¹…ÁÍ¡½ÑlÅt°¥¹ÍÑ…¹”œéÍ•±˜¹Í•ÍÍ¥½¸¹¥¹ÍÑ…¹”°É•ÑÕÉ¹}½¹±äœéÍ•±˜¹Í•ÍÍ¥½¸¹É•ÑÕÉ¹¥¹œ¡Í¹…ÁÍ¡½ÑlÅt±Í•±˜¹Í•ÍÍ¥½¸¹¥¹ÍÑ…¹”¥ô(€€€€€€€€€€€€€€€Í•±˜¹É•Á±å}©Í½¸ ÈÀÀ±‘…Ñ„¤(€€€€€€€€€€€•á•ÁÐ€¡=MÉÉ½È±Y…±Õ•ÉÉ½È±-•åÉÉ½È¤éÍ•±˜¹É•Á±å}©Í½¸ ÔÀÌ±ì•ÉÉ½ÈœèµÉ…Ñ”Õ¹…Ù…¥±…‰±”ô¤(€€€€€€€€€€€É•ÑÕÉ¸(€€€€€€€•±¥˜Í•±˜¹Á…Ñ ¥¸€ œ½…Á¤½¥¹Ù•¹Ñ½Éäœ°œ½…Á¤½±½…Ñ¥½¹Ìœ¤è(€€€€€€€€€€€ÑÉäè(€€€€€€€€€€€€€€€Ý¥Ñ ±½¬é‰½‘äõ©Í½¸¹‘ÕµÁÌ¡¥¹Ù•¹Ñ½Éä¡Í•±˜¹Á…Ñ ôôœ½…Á¤½±½…Ñ¥½¹Ìœ¤¤¹•¹½‘” ¤(€€€€€€€€€€€€€€€½‘”ôÈÀÀ(€€€€€€€€€€€•á•ÁÐ€¡=MÉÉ½È±Y…±Õ•ÉÉ½È±-•åÉÉ½È¤é‰½‘äõˆì‰•ÉÉ½Èˆè‰µÉ…Ñ”Õ¹…Ù…¥±…‰±”‰ôœí½‘”ôÔÀÌ(€€€€€€€€€€€µ¥µ”ô…ÁÁ±¥…Ñ¥½¸½©Í½¸œ(€€€€€€€•±Í”é‰½‘äõˆ9½Ð™½Õ¹œíµ¥µ”ôÑ•áÐ½Á±…¥¸œí½‘”ôÐÀÐ(€€€€€€€Í•±˜¹Í•¹‘}É•ÍÁ½¹Í”¡½‘”¤íÍ•±˜¹Í•¹‘}¡•…‘•È ½¹Ñ•¹ÐµQåÁ”œ±µ¥µ”¤íÍ•±˜¹Í•¹‘}¡•…‘•È ½¹Ñ•¹Ðµ1•¹Ñ œ±ÍÑÈ¡±•¸¡‰½‘ä¤¤¤íÍ•±˜¹Í•¹‘}¡•…‘•È …¡”µ½¹ÑÉ½°œ°¹¼µÍÑ½É”œ¤íÍ•±˜¹Í•¹‘}¡•…‘•È `µ½¹Ñ•¹ÐµQåÁ”µ=ÁÑ¥½¹Ìœ°¹½Í¹¥™˜œ¤íÍ•±˜¹•¹‘}¡•…‘•ÉÌ ¤íÍ•±˜¹Ý™¥±”¹ÝÉ¥Ñ”¡‰½‘ä¤(€€€‘•˜±½}µ•ÍÍ…”¡Í•±˜°©…ÉÌ¤éÁ…ÍÌ)¥˜}™¥áÑÕÉ•}½¹Ñ•áÐè(€€€}™¥áÑÕÉ•}É½½Ð±}™¥áÑÕÉ•}É•…‘äõ}™¥áÑÕÉ•}½¹Ñ•áÐ(€€€}™¥áÑÕÉ•}¡½ÍÐôœÄÈÜ¸À¸À¸Äœí}™¥áÑÕÉ•}Á½ÉÐôÀ)•±Í”è(€€€}™¥áÑÕÉ•}¡½ÍÐôœÀ¸À¸À¸Àœí}™¥áÑÕÉ•}Á½ÉÐôÄÜÜÐä)}™¥áÑÕÉ•}Í•ÉÙ•ÈõQ¡É•…‘¥¹!QQAM•ÉÙ•È ¡}™¥áÑÕÉ•}¡½ÍÐ±}™¥áÑÕÉ•}Á½ÉÐ¤±!…¹‘±•È¤)¥˜}™¥áÑÕÉ•}½¹Ñ•áÐè(€€€}™¥áÑÕÉ•}É•…‘ä¹Á…É•¹Ð¹µ­‘¥È¡µ½‘”ôÁ¼ÜÀÀ±Á…É•¹ÑÌõQÉÕ”±•á¥ÍÑ}½¬õQÉÕ”¤(€€€}™¥áÑÕÉ•}É•…‘ä¹ÝÉ¥Ñ•}Ñ•áÐ¡©Í½¸¹‘ÕµÁÌ¡ìµ½‘”œè™¥áÑÕÉ”µÁÉ½•ÍÌœ°Á¥œé½Ì¹•ÑÁ¥ ¤°(€€€€€€€€¡½ÍÐœé}™¥áÑÕÉ•}Í•ÉÙ•È¹Í•ÉÙ•É}…‘‘É•ÍÍlÁt°Á½ÉÐœé}™¥áÑÕÉ•}Í•ÉÙ•È¹Í•ÉÙ•É}…‘‘É•ÍÍlÅt°(€€€€€€€€½‘•}É½½ÐœéÍÑÈ¡=}I==P¤°(€€€€€€€€µ½‘Õ±•}½É¥¥¹Ìœéí¹…µ”éÍÑÈ¡ÍåÌ¹µ½‘Õ±•Ím¹…µ•t¹}}™¥±•}|¤™½È¹…µ”¥¸€ Ý½É­Í¡½Àœ°±•‘•Èœ°‘•Í­Ñ½Á}…Á¤œ¥ô°(€€€€€€€€Á¡åÍ¥…±}‰½Õ¹‘…ÉäœèÁÉ”µ¥µÁ½ÉÐÍÑÕ‰Ìô±Í½ÉÑ}­•åÌõQÉÕ”¤¤)•±Í”è(€€€ÁÉ¥¹Ð !½µ•‰½à½µÁ…¹¥½¸A$±¥ÍÑ•¹¥¹œ½¸€À¸À¸À¸ÀèÄÜÜÐäœ±™±ÕÍ õQÉÕ”¤)}™¥áÑÕÉ•}Í•ÉÙ•È¹Í•ÉÙ•}™½É•Ù•È ¤(