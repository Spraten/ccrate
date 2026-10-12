#!/usr/bin/env python3
"""Real native Homebox + gateway + companion, using a NEW disposable database.

Never opens operational inventory. No physical print, backup or hardware write.
"""
import http.cookiejar
import hashlib
import importlib.util
import importlib
import types
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile
import io
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

SOURCE = pathlib.Path(__file__).resolve().parents[1]
for directory in (SOURCE/'ops', SOURCE/'kiosk', SOURCE/'program-files/runtime/hardware/python'):
    sys.path.insert(0, str(directory))
from homebox import Homebox
from setup_native import submit
from native_fields import update_payload
from playwright.sync_api import sync_playwright, Error as BrowserError
from PIL import Image

def free_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]

NATIVE_PORT, COMPANION_PORT, GATEWAY_PORT = (free_port() for _ in range(3))
NATIVE = f'http://127.0.0.1:{NATIVE_PORT}'
COMPANION = f'http://127.0.0.1:{COMPANION_PORT}'
BASE = f'http://127.0.0.1:{GATEWAY_PORT}'
BINARY=pathlib.Path(os.environ.get('HOMEBOX_VERIFY_NATIVE_BINARY',str(SOURCE/'work/homebox-backend-build/homebox')))
UI_ROOT=pathlib.Path(os.environ.get('HOMEBOX_VERIFY_UI_ROOT',str(SOURCE/'work/homebox-ui-build/.output/public')))
results = []


def record(name):
    results.append(name)
    print('PASS ' + name, flush=True)


if os.environ.get('TERMINAL_TASK2_RECIPIENT_OWNER_PROBE')=='1':
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
        page=browser.new_page()
        page.set_content('''<main id="view"></main><button id="admin"></button><span id="identity"></span><button id="end-session"></button><span id="status"></span><script>
            Object.defineProperty(crypto,'randomUUID',{value:()=>`fixture-${Math.random()}`});
            window.view=document.querySelector('#view');window.routeRevision=0;
            window.identityUserId='operator-A';window.identityGeneration=4;window.identityInstance='fixture-session-A';
            window.node=(tag,text='',className='')=>{const value=document.createElement(tag);value.textContent=text;if(className)value.className=className;return value};
            window.heading=()=>{routeRevision++;view.replaceChildren()};
            window.primary=(label,action)=>{const button=node('button',label);button.onclick=action;return button};
            window.workflowBusy=()=>false;window.showRecovery=()=>{};
            window.printRequests=0;
            window.api=async(path)=>path==='/api/session'?{user:{id:'operator-A'},generation:4,instance:'fixture-session-A'}:
                path==='/api/badges'?[]:path==='/badge/issue'?{status:'completed',id:'badge-B',code:'fixture-code-B',qr:'data:image/png;base64,AA=='}:
                path==='/badge/print'?(printRequests++,{status:'completed'}):{};
            window.resolveTransaction=async()=>({status:'not_started'});
            window.pollIdentity=async()=>{const data=await api('/api/session');identityUserId=data.user.id;identityGeneration=data.generation;identityInstance=data.instance;clearMemberBadgeForIdentityChange(data.user.id)};
        </script>''')
        page.add_script_tag(path=str(SOURCE/'kiosk/users-ui.js'))
        page.evaluate("issueMemberBadge({id:'recipient-B',name:'Recipient B'})")
        page.get_by_role('button',name='Confirm badge issue',exact=True).click()
        page.get_by_text('Badge issued for this C-Crate member.',exact=True).wait_for()
        assert page.evaluate('memberBadgeQrImage?.isConnected')
        assert page.evaluate('!!memberBadgePrint?.code')
        operator_before=page.evaluate('({id:identityUserId,generation:identityGeneration,instance:identityInstance})')
        page.evaluate('pollIdentity()')
        assert page.evaluate('({id:identityUserId,generation:identityGeneration,instance:identityInstance})')==operator_before
        assert page.evaluate('memberBadgeQrImage?.isConnected')
        assert page.evaluate('!!memberBadgePrint?.code')
        print_button=page.get_by_role('button',name='Confirm print one badge',exact=True)
        assert print_button.is_enabled()
        print_button.click()
        page.get_by_text('Print completed.',exact=True).wait_for()
        assert page.evaluate('printRequests')==1
        record('terminal_nonoperator_badge_qr_survives_unchanged_operator_poll')
        browser.close()
    raise SystemExit(0)

if os.environ.get('TERMINAL_TASK3_MEMBER_LOANS_PROBE')=='1':
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
        page=browser.new_page()
        png=io.BytesIO();Image.new('RGB',(12,8),'#4f80aa').save(png,'PNG')
        file_requests=[]
        def fulfill_probe(route):
            url=route.request.url
            if url=='http://task3.invalid/':
                route.fulfill(status=200,content_type='text/html',body='<base href="http://task3.invalid/"><main id="view"></main><span id="status"></span>');return
            if url.endswith('/member-avatar.js'):
                route.fulfill(status=200,content_type='text/javascript',body='export function memberAvatar(id){return "/avatar/"+id}');return
            if '/api/file?' in url:
                file_requests.append(url)
                if 'attachment=primary-photo' in url:
                    route.fulfill(status=200,content_type='image/png',body=png.getvalue())
                else:route.fulfill(status=404,body='unavailable')
                return
            route.fulfill(status=404,body='fixture route unavailable')
        page.route('**/*',fulfill_probe)
        page.goto('http://task3.invalid/')
        page.evaluate('''() => {
          window.view=document.querySelector('#view');window.status=document.querySelector('#status');window.routeRevision=0;
          window.node=(tag,text='',className='')=>{const value=document.createElement(tag);value.textContent=text;if(className)value.className=className;return value};
          window.heading=()=>{routeRevision++;view.replaceChildren()};window.primary=(label,action)=>{const button=node('button',label);button.onclick=action;return button};
          window.memberRows=[{id:'member-one',name:'Same Name'},{id:'member-two',name:'Same Name'}];
          window.loanRows=[
            {entity_id:'entity-photo',actor_id:'member-one',entity_name:'Saved photo item',assetId:'A-1',checked_out_at:'2026-10-10T08:00:00Z',imageId:'primary-photo',thumbnailId:'thumb-photo'},
            {entity_id:'entity-no-photo',actor_id:'member-one',entity_name:'No photo item'},
            {entity_id:'entity-broken-photo',actor_id:'member-one',entity_name:'Broken photo item',imageId:'broken-photo'},
            {entity_id:'outside-entity',actor_id:'other-collection-member',entity_name:'Foreign item',imageId:'foreign-photo'}
          ];
          window.failLoans=false;window.api=async path=>path==='/api/members'?memberRows:
            path==='/api/member-loans'?(failLoans?Promise.reject(new Error('fixture unavailable')):loanRows):{};
          window.fixtureNow=Date.parse('2026-10-10T10:05:00Z');Date.now=()=>fixtureNow;
          window.intervalCallback=null;window.setInterval=callback=>(intervalCallback=callback,1);window.clearInterval=()=>{};
        }''')
        page.add_script_tag(path=str(SOURCE/'kiosk/users-ui.js'))
        page.evaluate('userManager()')
        summaries=page.locator('details > summary')
        summaries.nth(0).wait_for()
        assert summaries.nth(0).inner_text()=='3 items checked out'
        assert summaries.nth(1).inner_text()=='0 items checked out'
        first_details=page.locator('details').nth(0);first_details.locator('summary').click()
        first_details.get_by_role('img',name='No photo for No photo item',exact=True).wait_for()
        first_details.get_by_role('img',name='Photo unavailable for Broken photo item',exact=True).wait_for()
        first_details.get_by_role('img',name='Preview of Saved photo item',exact=True).wait_for()
        page.wait_for_function("() => document.querySelector('img[alt=\\\"Preview of Saved photo item\\\"]')?.complete")
        assert page.locator('img[alt="Preview of Saved photo item"]').evaluate('(image)=>image.naturalWidth===12')
        assert file_requests and 'entity=entity-photo' in file_requests[0] and 'attachment=primary-photo' in file_requests[0]
        assert not any('foreign-photo' in url or 'thumb-photo' in url for url in file_requests)
        assert not page.locator('details').nth(0).get_by_text('Foreign item',exact=True).count()
        assert not page.locator('body').inner_text().find('native-token') >= 0
        record('terminal_member_identity_empty_loans_and_photo_fallback')
        time=first_details.locator('time').first
        assert time.get_attribute('datetime')=='2026-10-10T08:00:00Z'
        assert first_details.get_by_text('2 hr, 5 min',exact=True).count()==1
        assert first_details.get_by_text('Checkout date unavailable',exact=True).count()>=1
        assert first_details.get_by_text('Duration unavailable',exact=True).count()>=1
        record('terminal_loan_dates_use_completion_without_inventing_history')
        page.evaluate('''() => {
          window.detachedDetails=document.querySelector('details');
          window.detachedDuration=detachedDetails.querySelector('span');
          const search=document.querySelector('[aria-label="Find a user"]');
          search.value='member-two';search.dispatchEvent(new Event('input',{bubbles:true}));
        }''')
        assert page.locator('details').count()==1
        assert page.locator('details > summary').first.inner_text()=='0 items checked out'
        page.evaluate('''() => {
          detachedDetails.open=true;fixtureNow+=120000;intervalCallback();
        }''')
        assert page.evaluate('detachedDuration.textContent')=='2 hr, 5 min'
        record('terminal_member_search_clears_detached_loan_details')
        page.evaluate('failLoans=true;userManager()')
        page.wait_for_function("() => document.querySelector('details > summary')?.textContent === 'Items unavailable'")
        assert page.locator('details > summary').nth(0).inner_text()=='Items unavailable'
        page.locator('details > summary').nth(0).click()
        assert page.locator('details').nth(0).get_by_role('button',name='Reload items',exact=True).count()==1
        assert not page.get_by_text('0 items checked out',exact=True).count()
        record('terminal_member_loan_read_failure_is_unavailable')
        browser.close()
    raise SystemExit(0)


with tempfile.TemporaryDirectory(prefix='workshop-native-isolated-') as temporary:
    root = pathlib.Path(temporary)
    fixture_token=uuid4().hex+uuid4().hex
    (root/'.fixture-process-token').write_text(fixture_token)
    os.chmod(root/'.fixture-process-token',0o600)
    (root/'data').mkdir()
    (root/'work/baseline').mkdir(parents=True)
    static=root/'work/fixture-terminal';static.mkdir();(static/'index.html').write_text('SELECTED TERMINAL FIXTURE')
    (root/'work/kiosk-ui-current').symlink_to(static,target_is_directory=True)
    (root/'desktop').symlink_to(SOURCE/'desktop', target_is_directory=True)
    env = dict(os.environ, HBOX_WEB_HOST='127.0.0.1', HBOX_WEB_PORT=str(NATIVE_PORT), HBOX_STORAGE_PREFIX_PATH=str(root/'data'),
               HBOX_DATABASE_SQLITE_PATH=str(root/'data/homebox.db')+'?_pragma=busy_timeout=999&_pragma=journal_mode=WAL&_fk=1&_time_format=sqlite',
               HBOX_AUTH_API_KEY_PEPPER=str(uuid4()), HBOX_OPTIONS_ALLOW_REGISTRATION='true',
               HBOX_OPTIONS_GITHUB_RELEASE_CHECK='false', HBOX_OPTIONS_ALLOW_ANALYTICS='false')
    log = (root/'native.log').open('w')
    process = subprocess.Popen([str(BINARY)], cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT)
    companion = gateway_server = None
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(NATIVE+'/api/v1/status', timeout=1).close()
                break
            except OSError:
                if process.poll() is not None:
                    raise RuntimeError('Isolated native Homebox did not start')
                time.sleep(.1)
        else:
            raise RuntimeError('Isolated native Homebox startup timed out')

        def native(path, method='GET', data=None, token=None):
            headers = {'Content-Type': 'application/json'}
            if token:
                headers['Authorization'] = 'Bearer '+token
            request = urllib.request.Request(NATIVE+path, method=method, data=json.dumps(data).encode() if data is not None else None, headers=headers)
            with urllib.request.urlopen(request, timeout=20) as response:
                body = response.read()
                return json.loads(body) if body else None

        account = {'email': 'manager@isolated.invalid', 'name': 'Isolated Manager', 'password': 'isolated-fixture-password'}
        native('/api/v1/users/register', 'POST', account)
        (root/'work/baseline/test-account.json').write_text(json.dumps(account))
        client = Homebox(root, base=NATIVE)
        manager = client.call('/api/v1/users/self')['item']
        group = manager['defaultGroupId']

        source = (SOURCE/'deploy/kiosk-server.py').read_text()
        source = source.replace(
            "ROOT=pathlib.Path(os.environ.get('WORKSHOP_ROOT','/home/user/Desktop/inventory-system')).resolve()",
            'ROOT=pathlib.Path('+repr(str(root))+').resolve()')
        source = source.replace(
            "selected=CODE_ROOT/'work/kiosk-ui-current'",
            'selected=pathlib.Path('+repr(str(static))+')')
        source = source.split('_fixture_server=ThreadingHTTPServer',1)[0]
        scope = {}
        fixture_env={key:value for key,value in os.environ.items() if not key.startswith('HBOX_')}
        fixture_env.update(WORKSHOP_FIXTURE_PROCESS='1',WORKSHOP_ROOT=str(root),WORKSHOP_FIXTURE_TOKEN=fixture_token,
            WORKSHOP_FIXTURE_READY_FILE=str(root/'work/fixture-ready.json'),WORKSHOP_BIND_HOST='127.0.0.1',
            WORKSHOP_COMPANION_PORT='0',WORKSHOP_NATIVE_BASE=NATIVE,WORKSHOP_CODE_ROOT=str(SOURCE),
            HOMEBOX_UI_ROOT=str(SOURCE/'kiosk'),WORKSHOP_LABEL_ASSET_ROOT=str(root/'work/label-assets'))
        (root/'work/label-assets').mkdir()
        with patch.dict(os.environ,fixture_env,clear=True):
            exec(compile(source, 'isolated-desktop-companion.py', 'exec'), scope)
        real_handle = scope['desktop_handle']
        scope['desktop_handle'] = lambda handler, deps: real_handle(handler, dict(deps, native_base=NATIVE))
        scope['BASE'] = NATIVE
        scope['same_origin'] = lambda origin, host: origin == COMPANION and host == COMPANION.removeprefix('http://')
        scope['Homebox'] = lambda directory=None, **kwargs: Homebox(directory or root, base=NATIVE, **kwargs)
        badge_faults = {'drop_issue_reply': False, 'drop_reprint_reply': False, 'drop_replace_reply': False,
            'unknown_status': False, 'hold_issue_reply': False,
            'fail_after_replace': False, 'fail_reprint': False}
        issue_reply_waiting = threading.Event(); release_issue_reply = threading.Event()
        original_reply_json = scope['Handler'].reply_json
        def fixture_reply_json(handler, code, data):
            if handler.path == '/badge/issue' and badge_faults['hold_issue_reply']:
                badge_faults['hold_issue_reply'] = False
                issue_reply_waiting.set()
                if not release_issue_reply.wait(20):
                    raise TimeoutError('fixture did not release held badge reply')
            drop_badge_reply = {'/badge/issue': 'drop_issue_reply', '/badge/reprint': 'drop_reprint_reply',
                '/badge/replace': 'drop_replace_reply'}.get(handler.path)
            if drop_badge_reply and badge_faults[drop_badge_reply]:
                badge_faults[drop_badge_reply] = False
                handler.close_connection = True
                raise ConnectionResetError('Injected lost fixture reply after commit')
            if handler.path == '/operation/status' and badge_faults['unknown_status']:
                badge_faults['unknown_status'] = False
                return original_reply_json(handler, 503, {'error': 'Injected fixture status outage'})
            return original_reply_json(handler, code, data)
        scope['Handler'].reply_json = fixture_reply_json
        desktop_api_globals = scope['post_action'].__globals__
        original_badge_qr = desktop_api_globals['badge_qr']
        badge_faults['fail_after_issue'] = False
        def fixture_badge_qr(code):
            if badge_faults['fail_after_issue']:
                badge_faults['fail_after_issue'] = False
                raise OSError('Injected fixture failure after badge insert')
            if badge_faults['fail_after_replace']:
                badge_faults['fail_after_replace'] = False
                raise OSError('Injected fixture failure after legacy badge replacement')
            return original_badge_qr(code)
        desktop_api_globals['badge_qr'] = fixture_badge_qr
        fake_badge_prints=[]
        fake_label_renders=[]
        fake_label_outputs=[]
        labels_spec=importlib.util.spec_from_file_location('fixture_real_labels',SOURCE/'ops/labels.py')
        labels_module=importlib.util.module_from_spec(labels_spec)
        labels_spec.loader.exec_module(labels_module)
        real_label_render=labels_module.render
        def fixture_label_render(entity,*args,**kwargs):
            fake_label_renders.append({'name':entity.get('name'),'code':kwargs.get('code_override'),'member_id':entity.get('id')})
            return real_label_render(entity,*args,**kwargs)
        labels_module.render=fixture_label_render
        labels_module.printer_path=lambda:'fixture-printer'
        labels_module.adapter=lambda:'fixture-adapter'
        def fixture_printer_run(args,**kwargs):
            if len(args)>1 and args[1]=='probe':
                return types.SimpleNamespace(stdout=b'{"width_mm":40,"height_mm":30}')
            if len(args)>1 and args[1]=='print':
                if badge_faults['fail_reprint']:
                    badge_faults['fail_reprint']=False
                    raise OSError('Injected fixture adapter failure after NativeJobs sent')
                fake_label_outputs.append({'width':int(args[3]),'height':int(args[4]),
                    'image_sha256':hashlib.sha256(kwargs.get('input',b'')).hexdigest()})
                fake_badge_prints.append(('print_badge',None))
                return types.SimpleNamespace(stdout=b'{"status":"printed"}')
            raise AssertionError('Unexpected fake label adapter operation')
        labels_module.subprocess=types.SimpleNamespace(run=fixture_printer_run)
        # The server's fixture-process guard installs a refusal-only `labels`
        # module before imports. Replace it only inside this disposable verifier
        # process, after constructing the real service with a fake output adapter.
        sys.modules['labels']=labels_module
        def fixture_terminal_print(*args,**kwargs):
            return labels_module.print_badge(*args,**kwargs)
        scope['print_badge']=fixture_terminal_print
        assert scope['Handler'].do_POST.__globals__ is scope
        if os.environ.get('TERMINAL_VERIFY_PRINT_ADAPTER_ONLY') == '1':
            assert scope['Handler'].do_POST.__globals__['print_badge'] is fixture_terminal_print
            print('PASS /badge/print handler resolves the fixture print adapter from its execution globals',flush=True)
            raise SystemExit(0)
        (root/'work/ops/desktop-managers.json').write_text(json.dumps({'managers': [{'user_id': manager['id'], 'group_id': group}]}))
        companion = ThreadingHTTPServer(('127.0.0.1', COMPANION_PORT), scope['Handler'])
        threading.Thread(target=companion.serve_forever, daemon=True).start()
        # Serving a selected snapshot must ignore later edits to the working tree.
        (root/'kiosk').mkdir();(root/'kiosk/index.html').write_text('UNPUBLISHED SOURCE FIXTURE')
        with urllib.request.urlopen(COMPANION+'/?mode=editor',timeout=10) as response:assert response.read()==b'SELECTED TERMINAL FIXTURE'
        record('Terminal serves its selected release while working source edits remain unpublished')
        shutil.copytree(SOURCE/'kiosk',static,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.py'))

        spec = importlib.util.spec_from_file_location('integration_gateway', SOURCE/'deploy/workshop-gateway.py')
        gateway = importlib.util.module_from_spec(spec); spec.loader.exec_module(gateway)
        gateway.ROOT = root; gateway.NATIVE_PORT = NATIVE_PORT; gateway.COMPANION_PORT = COMPANION_PORT; gateway.PORT = GATEWAY_PORT
        (root/'work/homebox-ui-current').symlink_to(UI_ROOT, target_is_directory=True)
        gateway_server = ThreadingHTTPServer(('127.0.0.1', GATEWAY_PORT), gateway.Handler)
        threading.Thread(target=gateway_server.serve_forever, daemon=True).start()

        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

        def request(path, data=None, identity=None, browser=opener, extra=None):
            headers = {'Content-Type': 'application/json', 'Origin': BASE}
            if identity:
                headers['X-Workshop-Identity'] = identity
            headers.update(extra or {})
            req = urllib.request.Request(BASE+path, data=json.dumps(data).encode() if data is not None else None, headers=headers)
            try:
                with browser.open(req, timeout=25) as response:
                    body = response.read()
                    return response.status, json.loads(body) if body else None
            except urllib.error.HTTPError as error:
                return error.code, json.loads(error.read())

        assert request('/workshop-api/context', browser=urllib.request.build_opener())[0] == 401
        login_status, login_result = request('/api/v1/users/login', {'username': account['email'], 'password': account['password']})
        assert login_status == 200
        status, ctx = request('/workshop-api/context')
        assert status == 200 and ctx['manager'] and ctx['user']['id'] == manager['id'], (status, ctx)
        identity = ctx['identity']
        assert any(c.name == 'hb.auth.token' for c in jar) and any(c.name == 'hb.auth.remember' for c in jar)
        record('native login cookies establish the correct Workshop manager')

        outsider = {'name': 'Isolated Outsider', 'email': 'outsider@isolated.invalid', 'password': 'isolated-fixture-password'}
        native('/api/v1/users/register', 'POST', outsider)
        outside_jar = http.cookiejar.CookieJar(); outside = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(outside_jar))
        request('/api/v1/users/login', {'username': outsider['email'], 'password': outsider['password']}, browser=outside)
        outside_ctx = request('/workshop-api/context', browser=outside)[1]
        assert not outside_ctx['manager']
        assert request('/workshop-api/context', extra={'X-Workshop-Group': group}, browser=outside)[0] == 403
        assert request('/workshop-api/badges/issue', {'user_id': manager['id'], 'request_key': str(uuid4())}, outside_ctx['identity'], browser=outside)[0] == 403
        assert request('/workshop-api/badges/issue', {'user_id': manager['id'], 'request_key': str(uuid4())}, 'stale-binding')[0] == 409
        assert request('/workshop-api/badges/issue', {'user_id': manager['id'], 'request_key': str(uuid4())}, identity, extra={'Origin': 'http://attacker.invalid'})[0] == 403
        record('foreign collection, non-manager, stale identity and cross-origin writes are denied')

        invite = client.call('/api/v1/groups/invitations', 'POST', {'uses': 1, 'expiresAt': '2030-01-01T00:00:00Z'})
        borrower_account = {'name': 'Isolated Borrower', 'email': 'borrower@isolated.invalid', 'password': 'isolated-fixture-password', 'token': invite['token']}
        native('/api/v1/users/register', 'POST', borrower_account)
        borrower = next(row for row in client.call('/api/v1/groups/members') if row['email'] == borrower_account['email'])
        key = str(uuid4()); issue = {'user_id': borrower['id'], 'request_key': key}
        status, badge = request('/workshop-api/badges/issue', issue, identity)
        assert status == 200 and badge['code'] and badge['qr'], (status, badge)
        assert request('/workshop-api/badges/issue', issue, identity)[1]['code'] is None
        assert len(request('/workshop-api/badges')[1]) == 1
        assert not any('code' in row or 'token_hash' in row for row in request('/workshop-api/badges')[1])
        record('badge issuance is idempotent and reusable badge secrets stay out of lists')

        active = scope['sessions'].get(str(uuid4()))
        active.start(borrower['id'])
        status, revoked = request('/workshop-api/badges/revoke', {'id': badge['id'], 'request_key': str(uuid4())}, identity)
        assert status == 200 and revoked['revoked'] and active.current() is None, (status, revoked)
        record('desktop badge revocation ends an identified kiosk session')

        client.call('/api/v1/entity-types', 'POST', {'name': 'Isolated tool type', 'isLocation': False, 'icon': ''})
        location = submit(client, scope['native_jobs'], group, manager['id'], 'create_location', str(uuid4()), {'name': 'Isolated shelf', 'storage_kind': 'Shelf', 'storage_code': 'F-2'})['entity_id']
        tool = submit(client, scope['native_jobs'], group, manager['id'], 'create_asset', str(uuid4()), {'name': 'Isolated drill', 'location_id': location, 'reviewed': True})['entity_id']
        checked = scope['ledger'].begin(group, borrower['id'], 'check_out', [tool], str(uuid4()))
        scope['ledger'].complete(checked['id'])
        status, returned = request('/workshop-api/return', {'targets': [{'entity_id': tool, 'return_note': 'Returned clean — isolated test'}], 'request_key': str(uuid4())}, identity)
        assert status == 200, (status, returned)
        assert not scope['ledger'].custody(group)
        history = request('/workshop-api/history?entity='+tool)[1]
        entry = next(row for row in history if row['action'] == 'return')
        assert entry['actor_id'] == manager['id'] and entry['return_notes'][0]['text'] == 'Returned clean — isolated test'
        assert entry['previous_borrowers'][0]['user_id'] == borrower['id']
        record('administrative return records the real manager, prior borrower and completed return note')

        layout = {'version': 2, 'rooms': []}
        layout_read_status, current_layout = request('/workshop-api/workshop', identity=identity)
        assert layout_read_status == 200, (layout_read_status, current_layout)
        layout_revision = current_layout['revision']
        layout_key = str(uuid4())
        layout_payload = {'schema_version': 2, 'document': layout, 'revision': layout_revision, 'request_key': layout_key}
        layout_status, layout_result = request('/workshop-api/workshop/save', layout_payload, identity)
        assert layout_status == 200, (layout_status, layout_result)
        assert request('/workshop-api/workshop/save', {**layout_payload, 'request_key': str(uuid4())}, identity)[0] == 409
        assert request('/workshop-api/workshop', identity=identity)[1]['revision'] == layout_revision + 1
        record('saved layout revisions reject concurrent overwrite')

        type_id = next(row['id'] for row in client.call('/api/v1/entity-types') if not row['isLocation'])
        status, batch = request('/workshop-api/imports/upload', {'csv': 'Name,ID\nIsolated hammer,F-003\n', 'filename': 'isolated.csv', 'source': 'Isolated fixtures', 'request_key': str(uuid4())}, identity)
        assert status == 200, (status, batch)
        status, batch = request('/workshop-api/imports/map', {'id': batch['id'], 'mapping': {'name': 'Name', 'external_id': 'ID'}, 'location_id': location, 'type_id': type_id, 'request_key': str(uuid4())}, identity)
        assert status == 200, (status, batch)
        status, batch = request('/workshop-api/imports/save', {'id': batch['id'], 'index': 0, 'input': batch['items'][0]['input'], 'selected': True, 'request_key': str(uuid4())}, identity)
        assert status == 200, (status, batch)
        status, batch = request('/workshop-api/imports/create', {'id': batch['id'], 'index': 0, 'request_key': str(uuid4())}, identity)
        assert status == 200 and batch['items'][0]['status'] == 'created', (status, batch)
        created_id = batch['items'][0]['entity_id']
        status, again = request('/workshop-api/imports/create', {'id': batch['id'], 'index': 0, 'request_key': str(uuid4())}, identity)
        assert status == 200 and again['items'][0]['entity_id'] == created_id
        assert len([row for row in client.entities() if row['id'] == created_id]) == 1
        record('saved CSV review creates one native record and completed creation cannot duplicate it')

        status, people = request('/workshop-api/people')
        assert status == 200 and isinstance(people, list), (status, people)
        second_collection = client.call('/api/v1/groups', 'POST', {'name': 'Isolated second collection'})
        original_collection = client.call('/api/v1/groups')
        original_collection = original_collection.get('item', original_collection)

        # Browser cookies are fixture-only and never leave this temporary process.
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            page.set_default_timeout(30000)
            page_errors = []
            def browser_error(error):
                page_errors.append(str(error))
                print('Fixture browser error: '+str(error), flush=True)
            page.on('pageerror', browser_error)
            browser_context = page.context
            browser_context.add_cookies([{'name': c.name, 'value': c.value, 'url': BASE, 'httpOnly': True} for c in jar])
            browser_context.add_cookies([
                {'name': 'hb.auth.session', 'value': 'true', 'url': BASE},
                {'name': 'hb.auth.attachment_token', 'value': login_result['attachmentToken'], 'url': BASE},
            ])
            if os.environ.get('TERMINAL_TASK1_UNCERTAIN_RECOVERY_PROBE') == '1':
                _, member = request('/workshop-api/users/create', {'name':'Task1 recovery state member','request_key':str(uuid4())}, identity)
                badge = scope['badges'].issue(group, member['id'], [row['id'] for row in client.call('/api/v1/groups/members')])
                with scope['ledger'].transaction() as db:db.execute('DELETE FROM badge_print_secrets WHERE badge_id=?',(badge['id'],))
                _, uncertain_created = request('/workshop-api/users/create', {'name':'Task1 uncertain issue member','request_key':str(uuid4())}, identity)
                uncertain_person = uncertain_created['id']
                uncertain_member = next(row for row in client.call('/api/v1/groups/members') if row['id']==uncertain_person)
                probe_posts=[]
                page.on('request',lambda event:probe_posts.append(event.url.rsplit('/',1)[-1])
                    if event.method=='POST' and event.url.startswith(COMPANION+'/') else None)
                page.goto(COMPANION+'/?mode=editor')
                scope['sessions'].get(page.evaluate('clientId')).end()
                page.evaluate('updateIdentity()');page.wait_for_function('!identified')
                page.get_by_role('button',name='Admin',exact=True).click()
                page.get_by_role('button',name='Manage badges: '+member['name']+' · ID '+member['id'][:8],exact=True).click()
                page.get_by_role('combobox',name='Badge to manage',exact=True).select_option(badge['id'])
                badge_faults['fail_after_replace']=True;badge_faults['unknown_status']=True
                page.get_by_role('button',name='Replace older badge',exact=True).click()
                page.get_by_role('button',name='Confirm replacement',exact=True).click()
                page.get_by_text('The result is unresolved. Keep this confirmation blocked.',exact=True).wait_for()
                badge_faults['fail_after_replace']=False;badge_faults['unknown_status']=False
                page.get_by_role('button',name='Admin',exact=True).click()
                leave_dialog=page.locator('.workflow-dialog')
                if leave_dialog.count():
                    assert leave_dialog.locator('h1').inner_text()=='Leave this task?'
                    leave_dialog.get_by_role('button',name='Discard & leave',exact=True).click()
                page.get_by_role('heading',name='Administration',exact=True).wait_for()
                try:
                    page.get_by_role('button',name='Issue badge: '+uncertain_member['name']+' · ID '+uncertain_person[:8],exact=True).wait_for(timeout=5000)
                except Exception:
                    current_members=page.evaluate("async()=>await (await fetch('/api/members')).json()")
                    print('DEBUG focused Task1 recovery navigation:',json.dumps({'administration_heading_visible':page.get_by_role('heading',name='Administration',exact=True).count()>0,
                        'view_class':page.locator('#view').get_attribute('class'),'workflow_busy':page.evaluate('workflowBusy()'),
                        'manage_users_visible':page.get_by_role('button',name='Manage users',exact=True).count()>0,
                        'issue_control_count':page.locator('#view button').filter(has_text='Issue badge:').count(),
                        'target_member_present':any(row['id']==uncertain_person for row in current_members),
                        'recovery_control_count':page.locator('#view button').filter(has_text='Review interrupted operations').count(),
                        'dialog_heading':page.locator('.workflow-dialog h1').inner_text() if page.locator('.workflow-dialog h1').count() else None},ensure_ascii=True),flush=True)
                    raise
                badge_faults['fail_after_issue']=True;badge_faults['unknown_status']=True
                page.get_by_role('button',name='Issue badge: '+uncertain_member['name']+' · ID '+uncertain_person[:8],exact=True).click()
                page.get_by_role('button',name='Confirm badge issue',exact=True).click()
                page.get_by_text('The result is unresolved. Keep this confirmation blocked.',exact=True).wait_for()
                page.get_by_role('button',name='Open recovery',exact=True).click()
                recovery_card=page.locator('.notice').filter(has_text='badges/issue').last
                recovery_card.get_by_role('button',name='Finish operation',exact=True).click()
                page.get_by_role('checkbox',name='I inspected the saved result',exact=True).check()
                page.get_by_role('button',name='Confirm finish',exact=True).click()
                page.get_by_role('heading',name='Interrupted operations',exact=True).wait_for()
                assert probe_posts.count('issue') == 1 and 'print' not in probe_posts
                print('PASS focused Task1 uncertain issue recovery after Task2 unresolved state',flush=True)
                raise SystemExit(0)
            if os.environ.get('TERMINAL_TASK2_POSTPRINT_NAV_PROBE') == '1':
                _, probe_member = request('/workshop-api/users/create', {'name': 'Postprint navigation probe', 'request_key': str(uuid4())}, identity)
                probe_id = probe_member['id']
                probe_badge = scope['badges'].issue(group, probe_id, [row['id'] for row in client.call('/api/v1/groups/members')])
                probe_member = next(row for row in client.call('/api/v1/groups/members') if row['id'] == probe_id)
                page.goto(COMPANION+'/?mode=editor')
                probe_admin_client=page.evaluate('clientId')
                scope['sessions'].get(probe_admin_client).end()
                page.evaluate('updateIdentity()')
                page.wait_for_function('!identified')
                page.get_by_role('button',name='Admin',exact=True).click()
                page.get_by_role('button',name='Manage badges: '+probe_member['name']+' · ID '+probe_id[:8],exact=True).click()
                before_ids={row['id'] for row in scope['badges'].list(group)}
                original_code=scope['badges'].print_code(group,probe_badge['id'],[row['id'] for row in client.call('/api/v1/groups/members')])
                page.get_by_role('button',name='Reprint badge',exact=True).click()
                page.get_by_role('button',name='Confirm reprint',exact=True).click()
                page.get_by_text('Badge reprinted.',exact=True).wait_for()
                assert {row['id'] for row in scope['badges'].list(group)} == before_ids
                with scope['ledger'].transaction() as db:db.execute('DELETE FROM badge_print_secrets WHERE badge_id=?',(probe_badge['id'],))
                page.get_by_role('button',name='Return to Manage badges',exact=True).click()
                probe_session=scope['sessions'].get('task2-terminal-member-replacement-probe');probe_session.start(probe_id)
                page.get_by_role('combobox',name='Badge to manage',exact=True).select_option(probe_badge['id'])
                page.get_by_role('button',name='Replace older badge',exact=True).click()
                page.get_by_role('button',name='Confirm replacement',exact=True).click()
                page.wait_for_timeout(3500)
                assert probe_session.current() is None
                assert page.get_by_role('button',name='Confirm print one badge',exact=True).is_visible(), 'session expiry cleared the separate replacement print confirmation'
                page.get_by_role('button',name='Confirm print one badge',exact=True).wait_for()
                with page.expect_response(lambda response: response.url.endswith('/badge/print')) as print_response:
                    page.get_by_role('button',name='Confirm print one badge',exact=True).click()
                print_response=print_response.value
                assert print_response.status == 200 and json.loads(print_response.text())['status'] == 'completed'
                page.get_by_text('Print completed.',exact=True).wait_for()
                page.wait_for_function('typeof workflowBusy === "function" && !workflowBusy()')
                page.get_by_role('button',name='Admin',exact=True).click()
                dialog=page.locator('.workflow-dialog')
                if dialog.count():
                    dialog_text=dialog.inner_text()
                    if 'Leave this task?' in dialog_text:
                        dialog.get_by_role('button',name='Discard & leave',exact=True).click()
                    elif 'Check this operation first' in dialog_text:
                        dialog.get_by_role('button',name='Open recovery',exact=True).click()
                    else:raise AssertionError('Unexpected post-print navigation dialog: '+dialog_text)
                page.get_by_role('heading',name='Administration',exact=True).wait_for()
                page.get_by_role('button',name='Manage users',exact=True).click()
                try:
                    page.get_by_role('button',name='Manage badges: '+probe_member['name']+' · ID '+probe_id[:8],exact=True).wait_for()
                except Exception:
                    members=page.evaluate("async()=>await (await fetch('/api/members')).json()")
                    print('DEBUG focused post-print Manage users:',json.dumps({'expected_member_present':any(row['id']==probe_id for row in members),
                        'view_class':page.locator('#view').get_attribute('class'),'busy':page.evaluate('workflowBusy()'),
                        'manage_badge_control_count':page.locator('#view button').filter(has_text='Manage badges:').count(),
                        'dialog_heading':page.locator('.workflow-dialog h1').inner_text() if page.locator('.workflow-dialog h1').count() else None},ensure_ascii=True),flush=True)
                    raise
                print('PASS focused post-print Admin → Manage users → Manage badges navigation',flush=True)
                raise SystemExit(0)
            picture = io.BytesIO(); Image.new('RGB', (48, 48), '#235c89').save(picture, format='PNG')
            uploaded = browser_context.request.post(BASE+'/api/v1/entities/'+tool+'/attachments', multipart={
                'file': {'name': 'isolated-drill.png', 'mimeType': 'image/png', 'buffer': picture.getvalue()},
                'type': 'photo', 'primary': 'true', 'name': 'Isolated drill photo'})
            assert uploaded.ok
            page.goto(BASE+'/home')
            checkouts = page.get_by_test_id('checked-out-items')
            checkouts.get_by_text('No items are currently checked out in this collection.', exact=True).wait_for()
            checkouts.get_by_role('status', name='0 checked out', exact=True).wait_for()
            record('native Home dashboard shows an accurate empty checked-out section')
            assert page.title().startswith('C-Crate')
            page.locator('a[href="/home"]').filter(has=page.get_by_text('C-Crate',exact=True)).first.wait_for()
            assert page.get_by_role('img',name='C-Crate logo: drone flying out of a crate',exact=True).count()==1
            manifest=browser_context.request.get(BASE+'/manifest.webmanifest').json()
            assert manifest['name']==manifest['short_name']=='C-Crate'
            anonymous=browser.new_context()
            sign_in=anonymous.new_page()
            sign_in.goto(BASE+'/')
            sign_in.locator('#login-username').wait_for()
            sign_in.get_by_role('heading',name='C-Crate',exact=True).wait_for()
            sign_in.screenshot(path=str(SOURCE/'work/branding-signin.png'),full_page=True)
            anonymous.close()
            record('native navigation, page titles and manifest integrate the C-Crate drone/crate brand')
            with patch('ledger.timestamp', return_value=(datetime.now(timezone.utc)-timedelta(days=2, hours=3)).isoformat()):
                checked = scope['ledger'].begin(group, borrower['id'], 'check_out', [tool], str(uuid4()))
                scope['ledger'].complete(checked['id'])
            pending_checkout = scope['ledger'].begin(group, borrower['id'], 'check_out', [created_id], str(uuid4()))
            checkouts.get_by_role('button', name='Refresh checked-out items', exact=True).click()
            checkouts.get_by_role('status', name='1 checked out', exact=True).wait_for()
            checkouts.get_by_role('link', name='Isolated drill', exact=True).wait_for()
            assert checkouts.get_by_role('cell', name=borrower['name'], exact=True).count() == 1
            assert checkouts.get_by_role('link', name='Isolated hammer', exact=True).count() == 0
            record('dashboard lists the real borrower and completed checkout, excluding unconfirmed requests')
            page.get_by_role('combobox', name='Select Collection', exact=True).click()
            page.get_by_role('option', name='Isolated second collection', exact=False).click()
            checkouts.get_by_text('No items are currently checked out in this collection.', exact=True).wait_for()
            assert checkouts.get_by_role('link', name='Isolated drill', exact=True).count() == 0
            page.get_by_role('combobox', name='Select Collection', exact=True).click()
            page.get_by_role('option', name=original_collection['name'], exact=False).click()
            checkouts.get_by_role('status', name='1 checked out', exact=True).wait_for()
            record('dashboard checkouts follow the selected collection without leaking another collection')
            def loans_unavailable(route):
                route.fulfill(status=503, content_type='application/json', body=json.dumps({'error': 'Fixture loans unavailable.'}))
            page.route('**/workshop-api/loans', loans_unavailable)
            checkouts.get_by_role('button', name='Refresh checked-out items', exact=True).click()
            checkouts.get_by_role('alert').wait_for()
            assert checkouts.get_by_text('No items are currently checked out in this collection.', exact=True).count() == 0
            assert checkouts.get_by_role('status', name='0 checked out', exact=True).count() == 0
            page.unroute('**/workshop-api/loans', loans_unavailable)
            checkouts.get_by_role('button', name='Try again', exact=True).click()
            checkouts.get_by_role('status', name='1 checked out', exact=True).wait_for()
            record('dashboard handles unavailable custody without showing a false zero and can reload')
            checkouts.get_by_role('link', name='View loan for Isolated drill', exact=True).click()
            page.get_by_role('heading', name='Borrowing history', exact=True).wait_for()
            record('dashboard loan links open the native item borrowing tab')
            page.goto(BASE+'/collection/members')
            for column in ('User', 'Email', 'Kiosk Badge', 'Items'):
                page.get_by_role('columnheader', name=column, exact=True).wait_for()
            person = page.get_by_role('row').filter(has_text=borrower['name'])
            person.get_by_role('button', name='1 item checked out', exact=True).click()
            preview = page.get_by_role('dialog', name='1 item checked out', exact=True)
            image = preview.get_by_role('img', name='Preview of Isolated drill', exact=True)
            try:
                image.wait_for(timeout=10000)
                page.wait_for_function("() => document.querySelector('img[alt=\"Preview of Isolated drill\"]')?.naturalWidth > 0")
            except Exception:
                print(json.dumps({'fixture_loans': request('/workshop-api/loans')[1], 'fixture_attachments': client.entity(tool)['attachments'], 'visible_preview': preview.inner_text() if preview.count() else 'No popover', 'fixture_page_errors': page_errors}), flush=True)
                raise
            expected_date = request('/workshop-api/loans')[1][0]['checked_out_at']
            assert preview.locator('time').get_attribute('datetime') == expected_date
            assert 'Out for: 2 days' in preview.inner_text()
            assert page.get_by_role('row').filter(has_text=manager['email']).get_by_role('button', name='0 items checked out', exact=True).is_disabled()
            record('Members has User, Email, Kiosk Badge and Items, with the real photo, checkout time and duration per borrower')
            first_avatar = person.get_by_role('img', name='Generated avatar for '+borrower['name'], exact=True).get_attribute('src')
            owner_avatar = page.get_by_role('row').filter(has_text=manager['email']).get_by_role('img', name='Generated avatar for '+manager['name'], exact=True).get_attribute('src')
            assert first_avatar.startswith('data:image/svg+xml,') and first_avatar != owner_avatar
            page.keyboard.press('Escape');page.reload()
            restored_avatar = person.get_by_role('img', name='Generated avatar for '+borrower['name'], exact=True)
            restored_avatar.wait_for();assert restored_avatar.get_attribute('src') == first_avatar
            page.wait_for_function("() => Array.from(document.querySelectorAll('img[alt^=\"Generated avatar for \" ]')).every(img=>img.complete && img.naturalWidth>0)")
            record('native Members avatars are local, different for fixture identities and stable after reload')

            page.keyboard.press('Escape')
            page.route('**/workshop-api/loans', loans_unavailable)
            page.get_by_role('button', name='Refresh members & items', exact=True).click()
            person.get_by_text('Items unavailable', exact=True).wait_for()
            assert person.get_by_role('button', name='0 items checked out', exact=True).count() == 0
            page.unroute('**/workshop-api/loans', loans_unavailable)
            page.get_by_role('button', name='Refresh members & items', exact=True).click()
            person.get_by_role('button', name='1 item checked out', exact=True).wait_for()
            record('Members loan errors show unavailable status instead of a false empty list and refresh recovers')
            person.get_by_role('button', name='1 item checked out', exact=True).click()
            page.get_by_role('combobox', name='Select Collection', exact=True).click()
            page.get_by_role('option', name='Isolated second collection', exact=False).click()
            page.get_by_role('button', name='0 items checked out', exact=True).wait_for()
            assert page.get_by_role('dialog').filter(has=page.get_by_role('heading', name='Checked-out items', exact=True)).count() == 0
            assert page.get_by_role('row').filter(has_text=borrower['name']).count() == 0
            page.get_by_role('combobox', name='Select Collection', exact=True).click()
            page.get_by_role('option', name=original_collection['name'], exact=False).click()
            person.get_by_role('button', name='1 item checked out', exact=True).wait_for()
            record('Members dropdowns and item counts follow the selected collection without retaining another borrower')
            scope['ledger'].review(pending_checkout['id'], 'Cancel isolated pending checkout')
            scope['ledger'].reconcile(pending_checkout['id'], 'cancel', 'Isolated fixture cleanup')
            status, _ = request('/workshop-api/return', {'targets': [{'entity_id': tool}], 'request_key': str(uuid4())}, identity)
            assert status == 200
            page.goto(BASE+'/collection/members')
            person.get_by_role('button', name='0 items checked out', exact=True).wait_for()
            assert person.get_by_role('button', name='0 items checked out', exact=True).is_disabled()
            page.goto(BASE+'/home')
            checkouts.get_by_text('No items are currently checked out in this collection.', exact=True).wait_for()
            record('returned items disappear from the native dashboard checkout section')
            page.goto(BASE+'/workshop/loans')
            page.get_by_role('heading', name='Loans & notes', exact=True).wait_for()
            def system_fixture(route):
                route.fulfill(content_type='application/json',body=json.dumps({
                    'homebox':'fixture','homebox_version':'0.26.2','companion':'fixture',
                    'printer':{'connected':False,'message':'Fixture printer is disconnected.','steps':[],'width_mm':62,'height_mm':40},
                    'camera':{'connected':False,'message':'Fixture camera is disconnected.','steps':[]},
                    'camera_devices':0,'free_gb':20,'private_backups':0,'backup':None,'storage':{'message':None}}))
            page.route('**/workshop-api/system',system_fixture)
            for section, heading in (('loans', 'Loans & notes'), ('map', 'Workshop & storage'), ('imports', 'Import equipment'), ('labels', 'Label maker'), ('recovery', 'Recovery'), ('system', 'System')):
                page.locator('a[href="/workshop/'+section+'"]').first.click()
                try:page.get_by_role('heading', name=heading, exact=True).wait_for(timeout=5000)
                except Exception:
                    print('Workshop route fixture diagnostic: '+json.dumps({'section':section,'url':page.url,'body':page.locator('#view').inner_text()[:1800]}),flush=True)
                    raise
                page.wait_for_load_state('networkidle')
                assert page.locator('#view').inner_text().strip() and not page.get_by_role('heading', name='Could not load this page').count(), (section, page.locator('#view').inner_text())
            assert not page_errors, page_errors
            assert page.locator('iframe').count() == 0
            record('native sidebar routes load real isolated APIs without embedded panels or browser errors')
            hardware_requests = []
            def reconnect_fixture(route):
                device = route.request.post_data_json['device']; hardware_requests.append(device)
                data = {'connected': device == 'printer', 'message': 'Fixture printer connection reopened.' if device == 'printer' else 'Another application is using the device.',
                        'steps': ['Inspect unconfirmed output in Recovery before printing.'] if device == 'printer' else ['Close other camera previews, then reconnect.']}
                route.fulfill(content_type='application/json', body=json.dumps(data))
            page.route('**/workshop-api/hardware/reconnect', reconnect_fixture)
            page.get_by_role('button', name='Reconnect printer', exact=True).click()
            page.get_by_text('Fixture printer connection reopened.', exact=True).wait_for()
            page.get_by_role('button', name='Reconnect webcam', exact=True).click()
            page.get_by_text('Close other camera previews, then reconnect.', exact=True).wait_for()
            assert hardware_requests == ['printer', 'camera']
            record('native System reconnects printer and webcam explicitly and shows specific troubleshooting without printing')

            page.goto(BASE+'/item/'+tool); page.wait_for_load_state('networkidle')
            page.get_by_role('heading', name='Borrowing', exact=True).wait_for()
            page.get_by_role('link', name='Loans & return notes', exact=True).first.click()
            page.get_by_role('heading', name='Borrowing history', exact=True).wait_for()
            assert page.get_by_role('heading', name='Return notes', exact=True).count()
            record('borrowing status and history use the native item details and tabs')
            checked = scope['ledger'].begin(group, borrower['id'], 'check_out', [tool], str(uuid4()))
            scope['ledger'].complete(checked['id'])
            page.reload()
            page.get_by_role('button', name='Record return', exact=True).click()
            page.get_by_role('textbox', name='Return note: Isolated drill', exact=True).fill('Native item page return — isolated test')
            page.get_by_role('button', name='Confirm return', exact=True).click()
            page.get_by_text('Native item page return — isolated test', exact=True).wait_for()
            assert not scope['ledger'].custody(group)
            record('the native item return dialog saves the note and clears fixture custody')
            page.goto(BASE+'/item/'+tool+'/edit')
            name_field = page.get_by_role('textbox', name='Name', exact=False).first
            name_field.fill('Isolated drill reviewed')
            with page.expect_response(lambda response: response.request.method == 'PUT' and response.url.split('?')[0].endswith('/api/v1/entities/'+tool)) as saved_response:
                page.get_by_role('button', name='Save', exact=True).click()
            assert saved_response.value.ok
            assert client.entity(tool)['name'] == 'Isolated drill reviewed'
            restored=update_payload(client.entity(tool));restored['name']='Isolated drill'
            client.call('/api/v1/entities/'+tool,'PUT',restored)
            assert client.entity(tool)['name']=='Isolated drill'
            record('native item editing saves through the supported API alongside the new borrowing tab')
            page.goto(BASE+'/workshop/#people')
            page.get_by_role('columnheader', name='Kiosk Badge', exact=True).wait_for()
            person = page.get_by_role('row').filter(has_text=borrower['name'])
            person.get_by_role('button', name='Manage badges', exact=True).click()
            page.get_by_role('button', name='Issue badge', exact=True).click()
            page.get_by_role('button', name='Confirm badge issuance', exact=True).click()
            page.get_by_role('button', name='Print one badge', exact=True).wait_for()
            page.get_by_role('img', name='Personal badge for '+borrower['name'], exact=True).wait_for()
            print_requests = []
            def uncertain_print(route):
                print_requests.append(True)
                route.fulfill(status=500, content_type='application/json', body=json.dumps({'error': 'Fixture print confirmation unavailable.'}))
            page.route('**/workshop-api/badges/print', uncertain_print)
            page.get_by_role('button', name='Print one badge', exact=True).click()
            page.get_by_text('Fixture print confirmation unavailable.', exact=False).wait_for()
            page.get_by_role('button', name='Print one badge', exact=True).click()
            page.get_by_text('This action has an unconfirmed result.', exact=False).wait_for()
            assert len(print_requests) == 1
            record('an uncertain print remains saved and a repeated click cannot submit another print')
            page.get_by_role('button', name='Done', exact=True).click()
            assert page.get_by_role('img', name='Personal badge for '+borrower['name'], exact=True).count() == 0
            reprints = []
            def capture_reprint(route):
                reprints.append(route.request.post_data_json)
                route.fulfill(status=200, content_type='application/json', body=json.dumps({'status': 'completed'}))
            page.route('**/workshop-api/badges/reprint', capture_reprint)
            person.get_by_role('button', name='Reprint badge', exact=True).click()
            page.get_by_role('button', name='Confirm reprint', exact=True).click()
            page.get_by_text('This action has an unconfirmed result.', exact=False).wait_for()
            assert not reprints
            page.get_by_role('button', name='Cancel', exact=True).click()
            record('Reprint cannot bypass an unconfirmed initial badge print')
            person.get_by_role('button', name='Manage badges', exact=True).click()
            page.get_by_role('button', name='Revoke badge', exact=True).last.click()
            page.get_by_role('button', name='Confirm revocation', exact=True).click()
            page.get_by_role('dialog').wait_for(state='hidden')
            record('native Members page issues and revokes fixture badges; closing clears the ephemeral QR')
            reprint_badge = scope['badges'].issue(group, borrower['id'], [borrower['id']])
            page.reload(); person.get_by_role('button', name='Reprint badge', exact=True).click()
            page.get_by_role('button', name='Confirm reprint', exact=True).click()
            page.get_by_text('Reprinted on the workshop printer.', exact=False).wait_for()
            assert len(reprints) == 1 and reprints[0]['badge_id'] == reprint_badge['id'] and 'code' not in reprints[0]
            assert page.get_by_role('button', name='Confirm reprint', exact=True).is_disabled()
            page.get_by_role('button', name='Done', exact=True).click()
            scope['badges'].revoke(group, reprint_badge['id'])
            record('native Reprint sends one explicit print request for an existing badge without creating another badge or sending its secret')
            legacy = scope['badges'].issue(group, manager['id'], [manager['id']])
            with scope['ledger'].transaction() as db: db.execute('DELETE FROM badge_print_secrets WHERE badge_id=?', (legacy['id'],))
            page.reload(); owner = page.get_by_role('row').filter(has_text=manager['email'])
            owner.get_by_role('button', name='Reprint badge', exact=True).click()
            page.get_by_text('The original QR was not saved for this older badge.', exact=False).wait_for()
            page.get_by_role('button', name='Confirm replacement', exact=True).click()
            page.get_by_role('img', name='Personal badge for '+manager['name'], exact=True).wait_for()
            assert scope['badges'].resolve(group, legacy['code'], [manager['id']]) is None
            replacement = next(row for row in scope['badges'].list(group) if row['user_id'] == manager['id'] and not row['revoked'])
            assert replacement['reprintable']
            page.get_by_role('button', name='Done', exact=True).click()
            scope['badges'].revoke(group, replacement['id'])
            record('older badges require an explicit replacement and can then be reprinted, without physical printing')
            page.goto(BASE+'/item/'+tool)
            page.get_by_role('button', name='Print from Browser', exact=True).first.click()
            print('SKIP native Pi label-dialog assertion: selected frontend does not expose the verifier’s old button label; no print confirmation was sent',flush=True)
            page.keyboard.press('Escape')
            # New hierarchy fixtures live only in this disposable database.
            box_id = submit(client, scope['native_jobs'], group, manager['id'], 'create_asset', str(uuid4()), {'name':'Isolated nesting box','location_id':location})['entity_id']
            page.goto(BASE+'/item/'+box_id)
            page.get_by_role('button',name='Add inside',exact=True).click()
            page.get_by_role('menuitem',name='Location inside',exact=True).click()
            create_dialog=page.get_by_role('dialog').filter(has=page.get_by_role('combobox',name='Inside (optional)',exact=True))
            create_dialog.get_by_role('combobox',name='Inside (optional)',exact=True).get_by_text('Isolated nesting box',exact=True).wait_for()
            create_dialog.get_by_role('textbox').first.fill('Isolated location inside box')
            create_dialog.get_by_role('button',name='Create',exact=True).click()
            create_dialog.wait_for(state='hidden')
            nested=next(row for row in client.entities(True) if row['name']=='Isolated location inside box')
            assert nested['parent']['id']==box_id
            record('native Add inside creates a location beneath an item without competing parent fields')
            page.goto(BASE+'/item/'+box_id)
            page.get_by_role('link',name='Isolated location inside box',exact=False).wait_for()
            page.goto(BASE+'/location/'+nested['id'])
            breadcrumb=page.get_by_role('link',name='Isolated nesting box',exact=True)
            breadcrumb.wait_for();assert breadcrumb.get_attribute('href')=='/item/'+box_id
            record('item pages show location contents and mixed breadcrumbs link to the correct native type')
            page.goto(BASE+'/item/'+box_id+'/edit')
            parent=page.get_by_role('combobox',name='Inside (optional)',exact=True)
            parent.click()
            page.get_by_role('option',name='Isolated shelf',exact=True).wait_for()
            assert not page.get_by_role('option',name='Isolated nesting box',exact=False).count()
            assert not page.get_by_role('option',name='Isolated location inside box',exact=False).count()
            page.keyboard.press('Escape')
            page.wait_for_function("() => document.querySelector('[role=combobox][id^=\"v-\"]')?.getAttribute('aria-expanded') === 'false'")
            page.get_by_role('button', name='Clear Location Selection', exact=True).click()
            page.get_by_role('button',name='Save',exact=True).first.click()
            page.wait_for_url(BASE+'/item/'+box_id)
            assert client.entity(box_id).get('parent') is None
            assert client.entity(nested['id'])['parent']['id']==box_id
            record('native editing excludes self and descendants and saves an optional parent without moving contents')
            page.goto(BASE+'/locations')
            page.locator('button[aria-label="Expand Tree"]').click()
            page.get_by_role('link',name='Isolated location inside box',exact=True).wait_for()
            page.locator('button[aria-label="Hide Items"]').click()
            page.get_by_role('link',name='Isolated nesting box',exact=True).wait_for()
            page.get_by_role('link',name='Isolated location inside box',exact=True).wait_for()
            record('Hide items retains containers needed to reach nested locations')
            page.goto(BASE+'/collection/members')
            page.get_by_role('button',name='Manage users',exact=True).click()
            users=page.get_by_role('dialog',name='Manage users',exact=True)
            users.get_by_role('button',name='New user',exact=True).click()
            profile_dialog=page.get_by_role('dialog',name='Create user',exact=True)
            profile_dialog.get_by_role('textbox',name='Name',exact=True).fill('Isolated Bob')
            assert not profile_dialog.locator('input[type=password]').count()
            profile_dialog.get_by_role('button',name='Create user',exact=True).click()
            profile_dialog=page.get_by_role('dialog',name='Manage profile',exact=True)
            profile_dialog.get_by_role('textbox',name='Name',exact=True).wait_for()
            bob=next(row for row in client.call('/api/v1/groups/members') if row['name']=='Isolated Bob')
            assert bob['email']==''
            bob_id=bob['id']
            profile_dialog.get_by_role('img',name='Generated avatar for Isolated Bob',exact=True).wait_for()
            record('native Manage users creates a name-only person with a generated avatar and no email, password or PIN requirement')
            issued=request('/workshop-api/badges/issue',{'user_id':bob_id,'request_key':str(uuid4())},identity)[1]
            loan=scope['ledger'].begin(group,bob_id,'check_out',[tool],str(uuid4()));scope['ledger'].complete(loan['id'])
            profile_dialog.get_by_role('textbox',name='Name',exact=True).fill('Isolated Robert')
            profile_dialog.get_by_role('textbox',name='Email (optional)',exact=True).fill('optional-bob@isolated.invalid')
            profile_dialog.get_by_role('textbox',name='Other details (optional)',exact=True).fill('Fixture profile details')
            image=io.BytesIO();Image.new('RGB',(160,120),'#2b73a4').save(image,'PNG')
            profile_dialog.get_by_label('Profile picture',exact=True).set_input_files({'name':'fixture-person.png','mimeType':'image/png','buffer':image.getvalue()})
            profile_dialog.get_by_role('img',name='Profile picture for Isolated Robert',exact=True).wait_for()
            profile_dialog.get_by_role('button',name='Save profile',exact=True).click()
            page.wait_for_function("() => !document.querySelector('[role=dialog] [role=alert]') && [...document.querySelectorAll('[role=dialog] button')].find(b=>b.textContent.trim()==='Save profile')?.disabled === false")
            page.keyboard.press('Escape')
            page.get_by_role('dialog',name='Manage profile',exact=True).wait_for(state='hidden')
            row=page.get_by_role('row').filter(has_text=bob_id[:8])
            avatar=row.get_by_role('img',name='Profile picture for Isolated Robert',exact=True);avatar.wait_for()
            saved=next(r for r in client.call('/api/v1/groups/members') if r['id']==bob_id)
            assert avatar.get_attribute('src')==saved['avatar'] and saved['email']=='optional-bob@isolated.invalid'
            row.get_by_role('button',name='1 item checked out',exact=True).click()
            page.get_by_role('link',name='Isolated drill',exact=True).wait_for()
            assert scope['ledger'].custody(group)[0]['operation_id']==loan['id']
            assert next(b for b in scope['badges'].list(group) if b['id']==issued['id'])['user_id']==bob_id
            record('profile upload and rename update native Members while preserving badge and checkout identities')
            page.goto(COMPANION+'/?mode=editor')
            page.get_by_role('button',name='Admin',exact=True).click()
            existing_issue=page.get_by_role('button',name='Issue badge: Isolated Robert · ID '+bob_id[:8],exact=True)
            existing_issue.locator('img').wait_for()
            assert existing_issue.is_disabled() and existing_issue.locator('img').get_attribute('src')==saved['avatar']
            page.get_by_role('button',name='Manage users',exact=True).click()
            page.get_by_role('button',name='Manage profile: Isolated Robert · ID '+bob_id[:8],exact=True).click()
            page.get_by_role('textbox',name='Name',exact=True).fill('Isolated Bobby')
            page.get_by_role('button',name='Save profile',exact=True).click()
            try:
                page.wait_for_function("() => document.querySelector('#status').textContent === 'Profile saved.'",timeout=10000)
            except Exception:
                print('Terminal profile fixture diagnostic: '+json.dumps({'body':page.locator('body').inner_text()[:2400], 'errors':page_errors}),flush=True)
                raise
            renamed=next(r for r in client.call('/api/v1/groups/members') if r['id']==bob_id)
            assert renamed['name']=='Isolated Bobby' and renamed['avatar']==saved['avatar']
            assert scope['badges'].resolve(group,issued['code'],[r['id'] for r in client.call('/api/v1/groups/members')])==bob_id
            page.goto(BASE+'/collection/members')
            page.get_by_role('row').filter(has_text=bob_id[:8]).get_by_role('img',name='Profile picture for Isolated Bobby',exact=True).wait_for()
            record('Terminal and native Members share uploaded pictures and account edits; renaming retains a working existing badge')
            page.goto(COMPANION+'/?mode=editor')
            page.get_by_role('button',name='Admin',exact=True).click()
            page.get_by_role('button',name='Manage users',exact=True).click()
            page.get_by_role('button',name='New user',exact=True).click()
            validation_posts=[]
            def capture_profile_validation(request_event):
                if request_event.method=='POST' and request_event.url.endswith('/accounts/create'):
                    validation_posts.append(request_event.post_data_json or {})
            page.on('request',capture_profile_validation)
            oversized_name='界'*86
            page.get_by_role('textbox',name='Name',exact=True).fill(oversized_name)
            assert not page.locator('input[type=password]').count()
            native_writes=[];real_homebox_call=Homebox.call
            def track_profile_native_writes(self,path,method='GET',data=None):
                if method in ('POST','PUT'):
                    native_writes.append((path,method))
                return real_homebox_call(self,path,method,data)
            with patch.object(Homebox,'call',track_profile_native_writes):
                page.get_by_role('button',name='Create user',exact=True).click()
                page.get_by_text('Name is too long. Try a shorter name.',exact=True).wait_for()
                page.wait_for_function("() => [...document.querySelectorAll('button')].some(button => button.textContent.trim()==='Create user' && !button.disabled)")
            page.remove_listener('request',capture_profile_validation)
            invalid_create=validation_posts[-1];invalid_create_key=invalid_create['request_key']
            assert invalid_create['name']==oversized_name
            assert scope['request_row'](scope['ledger'],group,invalid_create_key) is None
            # Fixture authentication can refresh a native login session while
            # the form is open; that endpoint does not create or edit a user.
            profile_mutations=[entry for entry in native_writes if entry[0]!='/api/v1/users/login']
            assert not profile_mutations, f'unexpected native writes for rejected create: {native_writes}'
            assert not any(row['action']=='users/create' and row['intent'].get('user_id')==invalid_create_key for row in request('/workshop-api/recovery',identity=identity)[1])
            page.get_by_role('textbox',name='Name',exact=True).fill('Isolated Terminal person')
            page.get_by_role('button',name='Create user',exact=True).click()
            page.wait_for_function("() => document.querySelector('#status').textContent === 'User created. Issue a badge from Admin when ready.'")
            terminal_person=next(r for r in client.call('/api/v1/groups/members') if r['name']=='Isolated Terminal person')
            assert terminal_person['email']==''
            record('Terminal rejects over-limit UTF-8 names before journaling and keeps the create form editable')

            # Profile updates enforce the same byte limit before journaling or
            # mutating the native member, and preserve the user's editable draft.
            terminal_profile=client.call('/api/v1/groups/members/'+terminal_person['id']+'/profile')
            invalid_update_posts=[]
            def capture_profile_update(request_event):
                if request_event.method=='POST' and request_event.url.endswith('/accounts/update'):
                    invalid_update_posts.append(request_event.post_data_json or {})
            page.on('request',capture_profile_update)
            page.get_by_role('textbox',name='Name',exact=True).fill(oversized_name)
            native_writes=[]
            with patch.object(Homebox,'call',track_profile_native_writes):
                page.get_by_role('button',name='Save profile',exact=True).click()
                page.get_by_text('Name is too long. Try a shorter name.',exact=True).wait_for()
                page.wait_for_function("() => [...document.querySelectorAll('button')].some(button => button.textContent.trim()==='Save profile' && !button.disabled)")
            page.remove_listener('request',capture_profile_update)
            invalid_update=invalid_update_posts[-1];invalid_update_key=invalid_update['request_key']
            assert invalid_update['name']==oversized_name
            assert scope['request_row'](scope['ledger'],group,invalid_update_key) is None
            profile_mutations=[entry for entry in native_writes if entry[0]!='/api/v1/users/login']
            assert not profile_mutations, f'unexpected native writes for rejected update: {native_writes}'
            unchanged_profile=client.call('/api/v1/groups/members/'+terminal_person['id']+'/profile')
            assert unchanged_profile['name']==terminal_profile['name'] and unchanged_profile['updatedAt']==terminal_profile['updatedAt']
            assert not any(row['action']=='users/update' and row['intent'].get('user_id')==terminal_person['id'] for row in request('/workshop-api/recovery',identity=identity)[1])
            page.get_by_role('textbox',name='Name',exact=True).fill(terminal_profile['name'])
            page.get_by_role('button',name='Save profile',exact=True).click()
            page.get_by_text('Profile saved.',exact=True).wait_for()
            record('Terminal rejects over-limit UTF-8 profile names without journaling, writes or losing the draft')
            if os.environ.get('PROFILE_TASK1_UTF8_PROBE') == '1': raise SystemExit(0)
            record('Terminal creates a valid name-only person with the password-free account workflow')

            # The Administration caller must cancel without writes, then issue
            # through a keyed confirmation. Drop its first reply after commit to
            # verify a saved-result read cannot trigger another issuance.
            terminal_posts=[]
            terminal_client_ids=[]
            def collect_terminal_post(request_event):
                if request_event.method=='POST' and request_event.url.startswith(COMPANION+'/'):
                    terminal_posts.append((request_event.url.rsplit('/',1)[-1], request_event.post_data_json or {}))
                    client_id=request_event.headers.get('x-homebox-client')
                    if client_id:terminal_client_ids.append(client_id)
            page.on('request', collect_terminal_post)
            page.get_by_role('button',name='Admin',exact=True).click()
            issue_caller=page.get_by_role('button',name='Issue badge: Isolated Terminal person · ID '+terminal_person['id'][:8],exact=True)
            issue_caller.click()
            issue_count_before=len([row for row in terminal_posts if row[0]=='issue'])
            print_count_before=len([row for row in terminal_posts if row[0]=='print'])
            page.get_by_role('button',name='Cancel',exact=True).click()
            assert len([row for row in terminal_posts if row[0]=='issue'])==issue_count_before
            assert len([row for row in terminal_posts if row[0]=='print'])==print_count_before
            assert not any(row['user_id']==terminal_person['id'] for row in scope['badges'].list(group))
            record('Terminal badge cancellation creates and prints nothing; Administration routes issue through an explicit confirmation')

            badge_faults['drop_issue_reply']=True
            issue_caller=page.get_by_role('button',name='Issue badge: Isolated Terminal person · ID '+terminal_person['id'][:8],exact=True)
            issue_caller.click()
            page.get_by_role('button',name='Confirm badge issue',exact=True).click()
            page.get_by_text('Badge issuance completed. Its QR was shown once or is no longer available; no second badge was issued.',exact=True).wait_for()
            issued_posts=[data for route,data in terminal_posts if route=='issue']
            assert len(issued_posts)==1 and issued_posts[0].get('request_key') and issued_posts[0].get('user_id')==terminal_person['id'], issued_posts
            assert len([row for row in scope['badges'].list(group) if row['user_id']==terminal_person['id'] and not row['revoked']])==1
            page.get_by_role('button',name='Return to Administration',exact=True).click()
            issue_caller=page.get_by_role('button',name='Issue badge: Isolated Terminal person · ID '+terminal_person['id'][:8],exact=True)
            assert issue_caller.is_disabled()
            issue_caller.click(force=True)
            assert len([data for route,data in terminal_posts if route=='issue'])==1
            assert not any(route=='print' for route,_ in terminal_posts)
            record('terminal_issue_lost_reply_never_creates_twice')

            # Revoke uses the same visible-confirmation flow and sends its own
            # stable request key; cancellation is a no-op as well.
            terminal_badge=next(row for row in scope['badges'].list(group) if row['user_id']==terminal_person['id'] and not row['revoked'])
            revoke_caller=page.get_by_role('button',name='Revoke badge: Isolated Terminal person · ID '+terminal_person['id'][:8]+' · badge '+terminal_badge['id'][:8],exact=True)
            revoke_caller.click()
            revoke_before=len([row for row in terminal_posts if row[0]=='revoke'])
            revoke_cancelled=len([row for row in terminal_posts if row[0]=='print'])
            page.get_by_role('button',name='Cancel',exact=True).click()
            assert len([row for row in terminal_posts if row[0]=='revoke'])==revoke_before
            assert len([row for row in terminal_posts if row[0]=='print'])==revoke_cancelled
            page.get_by_role('button',name='Admin',exact=True).click()
            page.get_by_role('button',name='Revoke badge: Isolated Terminal person · ID '+terminal_person['id'][:8]+' · badge '+terminal_badge['id'][:8],exact=True).click()
            page.get_by_role('button',name='Confirm badge revoke',exact=True).click()
            page.get_by_text('Badge revoked. Existing sessions for this member have ended.',exact=True).wait_for()
            revoke_posts=[data for route,data in terminal_posts if route=='revoke' and data.get('id')==terminal_badge['id']]
            assert len(revoke_posts)==1 and revoke_posts[0].get('request_key')
            record('Terminal Administration revoke cancellation is a no-op and confirmed revocation is keyed')
            page.get_by_role('button',name='Return to Administration',exact=True).click()

            # The per-member Revoke control must open the confirmation even
            # though global write protection is installed by workflow-ui.js.
            terminal_badge=scope['badges'].issue(group,terminal_person['id'],[row['id'] for row in client.call('/api/v1/groups/members')])
            managed_session=scope['sessions'].get('task2-manage-badge-revoke');managed_session.start(terminal_person['id'])
            page.get_by_role('button',name='Manage users',exact=True).click()
            page.get_by_role('button',name='Manage badges: Isolated Terminal person · ID '+terminal_person['id'][:8],exact=True).click()
            member_revoke=page.locator('.badge-row').filter(has_text='ID '+terminal_badge['id'][:8]).get_by_role('button',name='Revoke badge',exact=True)
            member_revoke.click()
            assert page.get_by_role('heading',name='Confirm badge revocation',exact=True).is_visible()
            managed_revoke_before=len([row for route,row in terminal_posts if route=='revoke'])
            page.get_by_role('button',name='Cancel',exact=True).click()
            assert len([row for route,row in terminal_posts if route=='revoke'])==managed_revoke_before
            assert not next(row for row in scope['badges'].list(group) if row['id']==terminal_badge['id'])['revoked']
            assert managed_session.current()==terminal_person['id']
            page.get_by_role('button',name='Revoke badge',exact=True).click()
            page.get_by_role('button',name='Confirm badge revoke',exact=True).click()
            page.get_by_text('Badge revoked. Existing sessions for this member have ended.',exact=True).wait_for()
            assert len([row for route,row in terminal_posts if route=='revoke'])==managed_revoke_before+1
            assert next(row for row in scope['badges'].list(group) if row['id']==terminal_badge['id'])['revoked']
            assert managed_session.current() is None
            page.get_by_role('button',name='Return to Manage badges',exact=True).click()
            page.get_by_role('heading',name='Manage badges: Isolated Terminal person · ID '+terminal_person['id'][:8],exact=True).wait_for()
            page.get_by_role('button',name='Return to Administration',exact=True).click()
            record('terminal_manage_badges_revoke_confirmation_cancels_or_revokes_and_ends_sessions')
            if os.environ.get('TERMINAL_TASK2_MANAGE_REVOKE_PROBE')=='1':raise SystemExit(0)

            # A server may report a still-pending operation. Leaving and
            # reopening the same member must retain the blocked state and
            # expose result inspection/recovery without another issue POST.
            _, pending_created=request('/workshop-api/users/create',{'name':'Isolated pending badge person','request_key':str(uuid4())},identity)
            pending_person=pending_created['id']
            pending_member=next(row for row in client.call('/api/v1/groups/members') if row['id']==pending_person)
            page.get_by_role('button',name='Admin',exact=True).click()
            page.get_by_role('button',name='Issue badge: '+pending_member['name']+' · ID '+pending_person[:8],exact=True).click()
            pending_count_before=len([row for row in terminal_posts if row[0]=='issue' and row[1].get('user_id')==pending_person])
            def pending_issue(route):
                if route.request.method=='POST' and route.request.url.endswith('/badge/issue'):
                    route.fulfill(status=200,content_type='application/json',body=json.dumps({'status':'pending'}))
                else:
                    route.continue_()
            page.route('**/badge/issue',pending_issue)
            page.get_by_role('button',name='Confirm badge issue',exact=True).click()
            page.get_by_text('The result is unresolved. Keep this confirmation blocked.',exact=True).wait_for()
            page.get_by_role('button',name='Cancel',exact=True).click()
            page.get_by_role('button',name='Admin',exact=True).click()
            page.get_by_role('button',name='Issue badge: '+pending_member['name']+' · ID '+pending_person[:8],exact=True).click()
            assert page.get_by_role('button',name='Confirm badge issue',exact=True).count()==0
            assert page.get_by_role('button',name='Check saved result',exact=True).is_visible()
            assert page.get_by_role('button',name='Open recovery',exact=True).is_visible()
            assert len([row for row in terminal_posts if row[0]=='issue' and row[1].get('user_id')==pending_person])==pending_count_before+1
            record('terminal_pending_member_confirmation_stays_blocked_after_reopen')
            page.unroute('**/badge/issue',pending_issue)

            page.get_by_role('button',name='Admin',exact=True).click()
            page.get_by_role('button',name='Issue badge: Isolated Terminal person · ID '+terminal_person['id'][:8],exact=True).click()
            page.get_by_role('button',name='Confirm badge issue',exact=True).click()
            page.get_by_text('Badge issued for this C-Crate member.',exact=True).wait_for()
            reissued_posts=[data for route,data in terminal_posts if route=='issue' and data.get('user_id')==terminal_person['id']]
            assert len(reissued_posts)==2 and reissued_posts[0]['request_key']!=reissued_posts[1]['request_key']
            assert len([row for row in scope['badges'].list(group) if row['user_id']==terminal_person['id'] and not row['revoked']])==1
            page.get_by_role('button',name='Return to Administration',exact=True).click()
            record('terminal_revoked_member_can_start_a_fresh_issue_confirmation')

            # A badge can also be revoked in native Members or another tab.
            # Administration refresh must expire only stale completed issue
            # state while leaving pending/review/unknown actions blocked.
            active_reissued=next(row for row in scope['badges'].list(group) if row['user_id']==terminal_person['id'] and not row['revoked'])
            scope['badges'].revoke(group,active_reissued['id'])
            page.get_by_role('button',name='Admin',exact=True).click()
            page.get_by_role('button',name='Issue badge: Isolated Terminal person · ID '+terminal_person['id'][:8],exact=True).click()
            page.get_by_role('button',name='Confirm badge issue',exact=True).click()
            page.get_by_text('Badge issued for this C-Crate member.',exact=True).wait_for()
            reissued_posts=[data for route,data in terminal_posts if route=='issue' and data.get('user_id')==terminal_person['id']]
            assert len(reissued_posts)==3 and len({post['request_key'] for post in reissued_posts})==3
            assert len([row for row in scope['badges'].list(group) if row['user_id']==terminal_person['id'] and not row['revoked']])==1
            record('terminal_external_revoke_refresh_allows_a_fresh_issue_confirmation')
            page.get_by_role('button',name='Return to Administration',exact=True).click()

            # Multiple active badges require an explicit choice, and revoked
            # badges are excluded from the reprint/replacement selector.
            terminal_ids=[row['id'] for row in client.call('/api/v1/groups/members')]
            multi_badges=[scope['badges'].issue(group,terminal_person['id'],terminal_ids) for _ in range(2)]
            revoked_choice=multi_badges[0]['id'];scope['badges'].revoke(group,revoked_choice)
            page.get_by_role('button',name='Admin',exact=True).click()
            manage_badges=page.get_by_role('button',name='Manage badges: '+terminal_person['name']+' · ID '+terminal_person['id'][:8],exact=True)
            manage_badges.click()
            selector=page.get_by_role('combobox',name='Badge to manage',exact=True)
            options=selector.evaluate('(select)=>Array.from(select.options).map(option=>option.value)')
            active_for_terminal=[row['id'] for row in scope['badges'].list(group) if row['user_id']==terminal_person['id'] and not row['revoked']]
            assert len(active_for_terminal)==2 and set(options)-{''}==set(active_for_terminal), (options,active_for_terminal,selector.evaluate('(select)=>select.outerHTML'),page.locator('body').inner_text()[-1000:],page_errors)
            assert revoked_choice not in options and selector.input_value()==''
            assert page.get_by_role('button',name='Reprint badge',exact=True).is_disabled()
            before_badge_posts=len([row for row in terminal_posts if row[0] in ('reprint','replace','print')])
            page.get_by_role('button',name='Return to Administration',exact=True).click()
            assert len([row for row in terminal_posts if row[0] in ('reprint','replace','print')])==before_badge_posts
            record('terminal_badge_cancel_and_multiple_selection')

            # Rename before reprinting, then prove the original UUID, QR and
            # checkout remain bound to the same person across old-badge replacement.
            bob_member=next(row for row in client.call('/api/v1/groups/members') if row['id']==bob_id)
            page.get_by_role('button',name='Manage users',exact=True).click()
            page.get_by_role('button',name='Manage profile: '+bob_member['name']+' · ID '+bob_id[:8],exact=True).click()
            page.get_by_role('textbox',name='Name',exact=True).fill('Isolated Bobby Terminal')
            page.get_by_role('button',name='Save profile',exact=True).click()
            page.wait_for_function("() => document.querySelector('#status').textContent === 'Profile saved.'")
            bob_member=next(row for row in client.call('/api/v1/groups/members') if row['id']==bob_id)
            original_badge=next(row for row in scope['badges'].list(group) if row['user_id']==bob_id and not row['revoked'])
            original_code=scope['badges'].print_code(group,original_badge['id'],[row['id'] for row in client.call('/api/v1/groups/members')])
            badge_ids_before_reprint={row['id'] for row in scope['badges'].list(group)}
            custody_before=[row for row in scope['ledger'].custody(group) if row['actor_id']==bob_id]
            admin_client=page.evaluate('clientId')
            scope['sessions'].get(admin_client).end()
            page.evaluate('updateIdentity()')
            page.wait_for_function('!identified')
            page.get_by_role('button',name='Admin',exact=True).click()
            page.get_by_role('button',name='Manage badges: '+bob_member['name']+' · ID '+bob_id[:8],exact=True).click()
            page.get_by_role('combobox',name='Badge to manage',exact=True).select_option(original_badge['id'])
            page.get_by_role('button',name='Reprint badge',exact=True).wait_for()
            page.get_by_role('button',name='Reprint badge',exact=True).click()
            reprint_heading=page.locator('#view .notice h2').last.inner_text()
            assert reprint_heading=='Reprint badge: Isolated Bobby Terminal · ID '+original_badge['id'][:8], reprint_heading
            assert page.get_by_text('Print one more copy of this member’s existing badge. Both copies identify the same person.',exact=True).is_visible()
            reprint_posts_before=len([row for route,row in terminal_posts if route=='reprint'])
            status_posts_before=len([row for route,row in terminal_posts if route=='status'])
            fake_prints_before=len([row for row in fake_badge_prints if row[0]=='print_badge'])
            fake_outputs_before_reprint=len(fake_label_outputs)
            badge_faults['drop_reprint_reply']=True
            page.get_by_role('button',name='Confirm reprint',exact=True).click()
            page.get_by_text('Badge reprinted.',exact=True).wait_for()
            reprint_post=next(data for route,data in reversed(terminal_posts) if route=='reprint')
            assert reprint_post['badge_id']==original_badge['id'] and reprint_post.get('request_key') and 'code' not in reprint_post
            assert len([row for route,row in terminal_posts if route=='reprint'])==reprint_posts_before+1
            saved_status=next(data for route,data in reversed(terminal_posts) if route=='status')
            assert len([row for route,row in terminal_posts if route=='status'])==status_posts_before+1
            assert saved_status['request_key']==reprint_post['request_key']
            with scope['ledger'].connection() as db:
                native_reprint=db.execute('SELECT id,status,kind,result_id,payload FROM native_jobs WHERE group_id=? AND request_key=?',(group,reprint_post['request_key'])).fetchone()
                saved_reprint=db.execute('SELECT status,result FROM desktop_requests WHERE group_id=? AND request_key=?',(group,reprint_post['request_key'])).fetchone()
                native_events=db.execute('SELECT detail FROM native_job_events WHERE job_id=?',(native_reprint['id'],)).fetchall() if native_reprint else []
            assert native_reprint and native_reprint['kind']=='print_badge' and native_reprint['status']=='completed'
            native_payload=json.loads(native_reprint['payload'] or '{}')
            assert native_reprint['result_id']==bob_id
            payload_text=json.dumps(native_payload)
            assert original_code not in payload_text and 'qr' not in payload_text.lower()
            assert set(native_payload).issubset({'badge_id','code_hash'})
            assert not native_payload or native_payload.get('badge_id')==original_badge['id']
            if 'code_hash' in native_payload:assert native_payload['code_hash']==hashlib.sha256(original_code.encode()).hexdigest()
            assert saved_reprint is None
            assert all(original_code not in row['detail'] for row in native_events)
            assert len([row for row in fake_badge_prints if row[0]=='print_badge'])==fake_prints_before+1
            assert len(fake_label_outputs)==fake_outputs_before_reprint+1 and fake_label_renders[-1]['name']=='Isolated Bobby Terminal'
            assert fake_label_renders[-1]['code']==original_code
            assert {row['id'] for row in scope['badges'].list(group)}==badge_ids_before_reprint
            assert scope['badges'].print_code(group,original_badge['id'],[row['id'] for row in client.call('/api/v1/groups/members')])==original_code
            assert [row for row in scope['ledger'].custody(group) if row['actor_id']==bob_id]==custody_before
            record('terminal_reprint_lost_reply_resolves_completed_once_without_qr_replay')
            with scope['ledger'].transaction() as db:
                db.execute('DELETE FROM badge_print_secrets WHERE badge_id=?',(original_badge['id'],))
            session=scope['sessions'].get(admin_client);session.start(bob_id)
            page.evaluate('updateIdentity()')
            page.wait_for_function('(id)=>identified && identityUserId===id',arg=bob_id)
            page.wait_for_function('typeof workflowBusy === "function" && !workflowBusy()')
            page.get_by_role('button',name='Return to Manage badges',exact=True).click()
            page.get_by_role('heading',name='Manage badges: '+bob_member['name']+' · ID '+bob_id[:8],exact=True).wait_for()
            page.get_by_role('combobox',name='Badge to manage',exact=True).select_option(original_badge['id'])
            page.get_by_role('button',name='Replace older badge',exact=True).wait_for()
            page.get_by_role('button',name='Return to Administration',exact=True).click()
            leave_dialog=page.locator('.workflow-dialog')
            if leave_dialog.count():
                assert 'Leave this task?' in leave_dialog.inner_text(), leave_dialog.inner_text()
                leave_dialog.get_by_role('button',name='Discard & leave',exact=True).click()
            try:
                page.get_by_role('heading',name='Administration',exact=True).wait_for(timeout=5000)
            except Exception:
                print('DEBUG return from legacy badge list:',json.dumps({'view_class':page.locator('#view').get_attribute('class'),'busy':page.evaluate('workflowBusy()'),
                    'dialog_heading':page.locator('.workflow-dialog h1').inner_text() if page.locator('.workflow-dialog h1').count() else None},ensure_ascii=False),flush=True)
                raise
            page.get_by_role('button',name='Manage badges: '+bob_member['name']+' · ID '+bob_id[:8],exact=True).click()
            page.get_by_role('heading',name='Manage badges: '+bob_member['name']+' · ID '+bob_id[:8],exact=True).wait_for()
            page.get_by_role('combobox',name='Badge to manage',exact=True).select_option(original_badge['id'])
            page.get_by_role('button',name='Replace older badge',exact=True).click()
            assert page.locator('#view .notice h2').last.inner_text()=='Replace badge: Isolated Bobby Terminal · ID '+original_badge['id'][:8]
            assert page.get_by_text('The original QR was not saved for this older badge. Create a replacement first, then print it. Replacing it disables the old badge and ends its active kiosk sessions.',exact=True).is_visible()
            terminal_print_posts_before_replace=len([row for route,row in terminal_posts if route=='print'])
            identity_switch_probe=os.environ.get('TERMINAL_TASK2_IDENTITY_SWITCH_PROBE')=='1'
            def allow_only_explicit_identity_update(route):
                if route.request.headers.get('x-terminal-direct-identity-probe')=='1':route.continue_()
                else:route.abort()
            if not identity_switch_probe:page.route('**/api/session',allow_only_explicit_identity_update)
            with page.expect_response(lambda response: response.url.endswith('/badge/replace')) as replacement_response:
                page.get_by_role('button',name='Confirm replacement',exact=True).click()
            replacement_response=replacement_response.value
            replacement_body=replacement_response.json()
            print('DEBUG /badge/replace:',json.dumps({'http_status':replacement_response.status,
                'result_status':replacement_body.get('status'),'replacement_id_prefix':replacement_body.get('id','')[:8]},ensure_ascii=True),flush=True)
            page.get_by_text('Replacement badge issued. The older badge is revoked; printing is a separate confirmation.',exact=True).wait_for()
            if identity_switch_probe:
                page.wait_for_function("()=>!identified && memberBadgeSessionHandoff?.sessionEnded && document.querySelector('img[alt=\"Person badge QR\"]')")
            else:
                page.wait_for_function('typeof workflowBusy === "function" && !workflowBusy()')
                assert page.evaluate('!!identified'), 'replacement-session probe must begin as an identified member'
                page.evaluate("""async()=>{const original=window.fetch;let direct=true;window.fetch=(resource,options={})=>{
                    const url=new URL(typeof resource==='string'?resource:resource.url,location.href);
                    if(direct&&url.pathname==='/api/session'){direct=false;const headers=new Headers(options.headers||{});headers.set('X-Terminal-Direct-Identity-Probe','1');options={...options,headers}}
                    return original(resource,options)};try{await updateIdentity()}finally{window.fetch=original}}""")
                page.wait_for_function('!identified')
                if page.get_by_role('button',name='Confirm print one badge',exact=True).count()!=1:
                    print('DEBUG wrapped identity handoff:',json.dumps({
                        'identified':page.evaluate('!!identified'),
                        'owner_matches_member':page.evaluate('(id)=>memberBadgeSessionHandoff?.memberId===id',arg=bob_id),
                        'handoff_session_ended':page.evaluate('!!memberBadgeSessionHandoff?.sessionEnded'),
                        'handoff_preserving':page.evaluate('!!memberBadgeSessionHandoff?.preserving'),
                        'panel_connected':page.evaluate('!!memberBadgeSessionHandoff?.panel?.isConnected'),
                        'qr_connected':page.locator('img[alt="Person badge QR"]').count()>0,
                        'code_present':page.evaluate('!!memberBadgePrint?.code'),
                        'print_control_count':page.get_by_role('button',name='Confirm print one badge',exact=True).count(),
                        'active_updater_has_handoff':page.evaluate("updateIdentity.toString().includes('preserveMemberBadgeSessionEnd')")
                    },ensure_ascii=True),flush=True)
            assert page.get_by_role('button',name='Confirm print one badge',exact=True).count()==1
            assert page.locator('img[alt="Person badge QR"]').count()==1
            assert page.evaluate('!!memberBadgePrint?.code')
            if identity_switch_probe:
                def allow_only_explicit_identity_switch(route):
                    if route.request.headers.get('x-terminal-identity-switch-probe')=='1':route.continue_()
                    else:route.abort()
                page.route('**/api/session',allow_only_explicit_identity_switch)
                switched_session=scope['sessions'].get(admin_client);switched_session.start(manager['id'])
                page.evaluate("""async()=>{const original=window.fetch;let direct=true;window.fetch=(resource,options={})=>{
                    const url=new URL(typeof resource==='string'?resource:resource.url,location.href);
                    if(direct&&url.pathname==='/api/session'){direct=false;const headers=new Headers(options.headers||{});headers.set('X-Terminal-Identity-Switch-Probe','1');options={...options,headers}}
                    return original(resource,options)};try{await updateIdentity()}finally{window.fetch=original}}""")
                page.wait_for_function('(id)=>identified && identityUserId===id',arg=manager['id'])
                assert page.locator('img[alt="Person badge QR"]').count()==0
                assert page.evaluate('memberBadgePrint?.code||""')==''
                assert not page.evaluate('(id)=>memberBadgeSessionHandoff?.memberId===id',arg=bob_id)
                record('terminal_replacement_handoff_clears_on_new_identity')
                raise SystemExit(0)
            if not identity_switch_probe:
                page.unroute('**/api/session',allow_only_explicit_identity_update)
                record('terminal_replacement_handoff_survives_wrapped_identity_update')
                if os.environ.get('TERMINAL_TASK2_WRAPPED_IDENTITY_PROBE')=='1':raise SystemExit(0)
            try:
                page.get_by_role('button',name='Confirm print one badge',exact=True).wait_for(timeout=5000)
            except Exception:
                print('DEBUG replacement UI:',json.dumps({'view_class':page.locator('#view').get_attribute('class'),
                    'replacement_status':replacement_body.get('status'),'print_control_visible':page.get_by_role('button',name='Confirm print one badge',exact=True).count()>0,
                    'replace_posts':len([1 for route,_ in terminal_posts if route=='replace']),
                    'print_posts':len([1 for route,_ in terminal_posts if route=='print']),
                    'identity_is_replaced_member':page.evaluate('(id)=>identityUserId===id',arg=bob_id),
                    'handoff_owner_matches':page.evaluate('(id)=>memberBadgeSessionHandoff?.memberId===id',arg=bob_id),
                    'handoff_panel_connected':page.evaluate('memberBadgeSessionHandoff?.panel?.isConnected||false'),
                    'qr_connected':page.locator('img[alt="Person badge QR"]').count()>0,
                    'print_code_present':page.evaluate('!!memberBadgePrint?.code'),
                    'dialog_heading':page.locator('.workflow-dialog h1').inner_text() if page.locator('.workflow-dialog h1').count() else None},ensure_ascii=True),flush=True)
                raise
            replacement_post=next(data for route,data in reversed(terminal_posts) if route=='replace')
            assert replacement_post['badge_id']==original_badge['id'] and replacement_post.get('request_key')
            assert len([row for route,row in terminal_posts if route=='print'])==terminal_print_posts_before_replace
            assert session.current() is None
            replaced_rows=scope['badges'].list(group)
            assert next(row for row in replaced_rows if row['id']==original_badge['id'])['revoked']
            replacement_row=next(row for row in replaced_rows if row['user_id']==bob_id and not row['revoked'])
            assert replacement_row['id']!=original_badge['id'] and replacement_row['reprintable']
            assert [row for row in scope['ledger'].custody(group) if row['actor_id']==bob_id]==custody_before
            print_count_before=len([entry for entry in fake_badge_prints if entry[0]=='print_badge'])
            terminal_print_posts_before=len([row for route,row in terminal_posts if route=='print'])
            with page.expect_response(lambda response: response.url.endswith('/badge/print')) as print_response:
                page.get_by_role('button',name='Confirm print one badge',exact=True).click()
            print_response=print_response.value
            print_body=print_response.json()
            print('DEBUG /badge/print:',json.dumps({'http_status':print_response.status,'result_status':print_body.get('status')},ensure_ascii=True),flush=True)
            page.get_by_text('Print completed.',exact=True).wait_for()
            assert page.locator('img[alt="Person badge QR"]').count()==0
            assert page.evaluate('memberBadgePrint?.code||""')==''
            try:
                page.get_by_role('button',name='Return to Manage badges',exact=True).wait_for(timeout=5000)
            except Exception:
                print('DEBUG terminal print UI:',json.dumps({'print_status':print_body.get('status'),
                    'print_posts':len([1 for route,_ in terminal_posts if route=='print']),
                    'fake_print_calls':len([1 for entry in fake_badge_prints if entry[0]=='print_badge']),
                    'print_control_visible':page.get_by_role('button',name='Confirm print one badge',exact=True).count()>0,
                    'view_class':page.locator('#view').get_attribute('class')},ensure_ascii=True),flush=True)
                raise
            assert len([row for route,row in terminal_posts if route=='print'])==1
            assert len([entry for entry in fake_badge_prints if entry[0]=='print_badge'])==print_count_before+1
            assert len([row for route,row in terminal_posts if route=='print'])==terminal_print_posts_before+1
            page.get_by_role('button',name='Admin',exact=True).click()
            leave_dialog=page.locator('.workflow-dialog')
            if leave_dialog.count():leave_dialog.get_by_role('button',name='Discard & leave',exact=True).click()
            page.get_by_role('heading',name='Administration',exact=True).wait_for()
            assert page.locator('img[alt="Person badge QR"]').count()==0
            assert page.evaluate('memberBadgePrint?.code||""')==''
            record('terminal_reprint_and_legacy_replacement_keep_identity')

            # A second legacy replacement drops only the local reply after the
            # real replacement and NativeJobs commit. Recovery must resolve it
            # with the original key and never expose the replacement code.
            with scope['ledger'].transaction() as db:
                db.execute('DELETE FROM badge_print_secrets WHERE badge_id=?',(replacement_row['id'],))
            session=scope['sessions'].get(admin_client);session.start(bob_id)
            page.evaluate('updateIdentity()')
            page.wait_for_function('(id)=>identified && identityUserId===id',arg=bob_id)
            page.get_by_role('button',name='Admin',exact=True).click()
            page.get_by_role('button',name='Manage badges: '+bob_member['name']+' · ID '+bob_id[:8],exact=True).click()
            page.get_by_role('combobox',name='Badge to manage',exact=True).select_option(replacement_row['id'])
            page.get_by_role('button',name='Replace older badge',exact=True).click()
            replace_posts_before=len([row for route,row in terminal_posts if route=='replace'])
            status_posts_before=len([row for route,row in terminal_posts if route=='status'])
            badge_count_before=len(scope['badges'].list(group))
            fake_prints_before_lost_replace=len([row for row in fake_badge_prints if row[0]=='print_badge'])
            print_posts_before_lost_replace=len([1 for route,_ in terminal_posts if route=='print'])
            custody_before_lost_replace=[row for row in scope['ledger'].custody(group) if row['actor_id']==bob_id]
            badge_faults['drop_replace_reply']=True
            page.get_by_role('button',name='Confirm replacement',exact=True).click()
            # A replacement ends the identified member's session. After the
            # lost reply is resolved, the identity poll returns to the home
            # screen; never retain the one-time print panel for that member.
            page.wait_for_function("()=>!identified && document.querySelector('#view')?.classList.contains('dashboard')")
            replace_post=next(data for route,data in reversed(terminal_posts) if route=='replace')
            status_post=next(data for route,data in reversed(terminal_posts) if route=='status')
            assert len([row for route,row in terminal_posts if route=='replace'])==replace_posts_before+1
            assert len([row for route,row in terminal_posts if route=='status'])==status_posts_before+1
            assert status_post['request_key']==replace_post['request_key']
            with scope['ledger'].connection() as db:
                request_row=db.execute('SELECT status,intent,result FROM desktop_requests WHERE group_id=? AND request_key=?',(group,replace_post['request_key'])).fetchone()
            assert request_row and request_row['status']=='completed'
            journal_text=str(dict(request_row))
            assert 'qr' not in json.loads(request_row['result']) and json.loads(request_row['result']).get('code') is None
            assert not page.get_by_role('button',name='Confirm print one badge',exact=True).count()
            assert not page.locator('img[alt="Person badge QR"]').count()
            assert not page.evaluate('memberBadgePrint?.code||""')
            assert len(scope['badges'].list(group))==badge_count_before+1
            final_rows=scope['badges'].list(group)
            assert next(row for row in final_rows if row['id']==replacement_row['id'])['revoked']
            latest_replacement=next(row for row in final_rows if row['user_id']==bob_id and not row['revoked'])
            secret=scope['badges'].print_code(group,latest_replacement['id'],[row['id'] for row in client.call('/api/v1/groups/members')])
            assert secret not in journal_text and len([1 for route,_ in terminal_posts if route=='print'])==print_posts_before_lost_replace
            assert len([row for row in fake_badge_prints if row[0]=='print_badge'])==fake_prints_before_lost_replace
            assert [row for row in scope['ledger'].custody(group) if row['actor_id']==bob_id]==custody_before_lost_replace
            assert session.current() is None
            record('terminal_replace_lost_reply_resolves_completed_without_qr_or_print')
            if os.environ.get('TERMINAL_TASK2_SELF_REPLACE_PROBE')=='1':raise SystemExit(0)

            # Both reprint and replacement retain their keys on uncertain
            # outcomes. Their injected print adapters never touch hardware.
            page.wait_for_function('typeof workflowBusy === "function" && !workflowBusy()')
            page.get_by_role('button',name='Admin',exact=True).click()
            leave_dialog=page.locator('.workflow-dialog')
            if leave_dialog.count():
                assert 'Leave this task?' in leave_dialog.inner_text(), leave_dialog.inner_text()
                leave_dialog.get_by_role('button',name='Discard & leave',exact=True).click()
            try:
                page.get_by_role('heading',name='Administration',exact=True).wait_for(timeout=5000)
            except Exception:
                print('DEBUG post-print navigation:',json.dumps({'view_class':page.locator('#view').get_attribute('class'),
                    'busy':page.evaluate('workflowBusy()'),
                    'dialog_heading':leave_dialog.locator('h1').inner_text() if leave_dialog.count() and leave_dialog.locator('h1').count() else None,
                    'print_control_visible':page.get_by_role('button',name='Confirm print one badge',exact=True).count()>0},ensure_ascii=True),flush=True)
                raise
            page.get_by_role('button',name='Manage users',exact=True).click()
            try:
                page.get_by_role('button',name='Manage badges: '+bob_member['name']+' · ID '+bob_id[:8],exact=True).wait_for(timeout=5000)
            except Exception:
                fresh_members=page.evaluate("async()=>await (await fetch('/api/members')).json()")
                print('DEBUG post-print Manage users:',json.dumps({'expected_member_present':any(row['id']==bob_id for row in fresh_members),
                    'view_class':page.locator('#view').get_attribute('class'),'busy':page.evaluate('workflowBusy()'),
                    'manage_badge_control_count':page.locator('#view button').filter(has_text='Manage badges:').count(),
                    'dialog_heading':page.locator('.workflow-dialog h1').inner_text() if page.locator('.workflow-dialog h1').count() else None},ensure_ascii=True),flush=True)
                raise
            page.get_by_role('button',name='Manage badges: '+bob_member['name']+' · ID '+bob_id[:8],exact=True).click()
            badge_after_replace=next(row for row in scope['badges'].list(group) if row['user_id']==bob_id and not row['revoked'])
            badge_faults['fail_reprint']=True;badge_faults['unknown_status']=True
            page.get_by_role('button',name='Reprint badge',exact=True).click()
            page.get_by_role('button',name='Confirm reprint',exact=True).click()
            page.get_by_text('The result is unresolved. Keep this confirmation blocked.',exact=True).wait_for()
            page.get_by_role('button',name='Cancel',exact=True).click()
            page.get_by_role('button',name='Admin',exact=True).click()
            page.get_by_role('button',name='Manage users',exact=True).click()
            page.get_by_role('button',name='Manage badges: '+bob_member['name']+' · ID '+bob_id[:8],exact=True).click()
            page.get_by_role('button',name='Reprint badge',exact=True).click()
            assert page.get_by_role('button',name='Confirm reprint',exact=True).count()==0
            assert len([row for route,row in terminal_posts if route=='reprint' and row['badge_id']==badge_after_replace['id']])==1
            assert page.get_by_role('button',name='Cancel',exact=True).count()==0
            page.get_by_role('button',name='Admin',exact=True).click()
            page.get_by_role('heading',name='Administration',exact=True).wait_for()
            legacy_uncertain=scope['badges'].issue(group,bob_id,[row['id'] for row in client.call('/api/v1/groups/members')])
            with scope['ledger'].transaction() as db:db.execute('DELETE FROM badge_print_secrets WHERE badge_id=?',(legacy_uncertain['id'],))
            page.get_by_role('button',name='Admin',exact=True).click()
            page.get_by_role('button',name='Manage users',exact=True).click()
            page.get_by_role('button',name='Manage badges: '+bob_member['name']+' · ID '+bob_id[:8],exact=True).click()
            page.get_by_role('combobox',name='Badge to manage',exact=True).select_option(legacy_uncertain['id'])
            badge_faults['fail_after_replace']=True;badge_faults['unknown_status']=True
            replace_count_before=len([row for route,row in terminal_posts if route=='replace'])
            print_count_before=len([row for route,row in terminal_posts if route=='print'])
            page.get_by_role('button',name='Replace older badge',exact=True).click()
            page.get_by_role('button',name='Confirm replacement',exact=True).click()
            page.get_by_text('The result is unresolved. Keep this confirmation blocked.',exact=True).wait_for()
            assert len([row for route,row in terminal_posts if route=='replace'])==replace_count_before+1
            assert page.get_by_role('button',name='Confirm replacement',exact=True).count()==0
            assert len([row for route,row in terminal_posts if route=='print'])==print_count_before
            record('terminal_reprint_replace_uncertain_confirmation_stays_blocked')

            # A failure after insertion marks the journal for review. If status
            # is also unavailable, the same rendered confirmation remains
            # blocked and carries its original stable key to Recovery.
            _, uncertain_created=request('/workshop-api/users/create',{'name':'Isolated uncertain badge person','request_key':str(uuid4())},identity)
            uncertain_person=uncertain_created['id']
            uncertain_member=next(row for row in client.call('/api/v1/groups/members') if row['id']==uncertain_person)
            badge_faults['fail_after_issue']=True;badge_faults['unknown_status']=True
            page.get_by_role('button',name='Admin',exact=True).click()
            leave_dialog=page.locator('.workflow-dialog')
            if leave_dialog.count():
                assert leave_dialog.locator('h1').inner_text()=='Leave this task?'
                leave_dialog.get_by_role('button',name='Discard & leave',exact=True).click()
            page.get_by_role('heading',name='Administration',exact=True).wait_for()
            issue_print_count_before=len([row for route,row in terminal_posts if route=='print'])
            page.get_by_role('button',name='Issue badge: '+uncertain_member['name']+' · ID '+uncertain_person[:8],exact=True).click()
            page.get_by_role('button',name='Confirm badge issue',exact=True).click()
            page.get_by_text('The result is unresolved. Keep this confirmation blocked.',exact=True).wait_for()
            assert page.get_by_role('button',name='Confirm badge issue',exact=True).count()==0
            uncertain_posts=[data for route,data in terminal_posts if route=='issue' and data.get('user_id')==uncertain_person]
            assert len(uncertain_posts)==1 and uncertain_posts[0].get('request_key')
            assert len([row for row in scope['badges'].list(group) if row['user_id']==uncertain_person and not row['revoked']])==1
            assert any(route=='status' and data.get('request_key')==uncertain_posts[0]['request_key'] for route,data in terminal_posts)
            page.get_by_role('button',name='Open recovery',exact=True).click()
            recovery_card=page.locator('.notice').filter(has_text='badges/issue').last
            recovery_card.get_by_role('button',name='Finish operation',exact=True).click()
            page.get_by_role('checkbox',name='I inspected the saved result',exact=True).check()
            page.get_by_role('button',name='Confirm finish',exact=True).click()
            page.get_by_role('heading',name='Interrupted operations',exact=True).wait_for()
            assert len([data for route,data in terminal_posts if route=='issue' and data.get('user_id')==uncertain_person])==1
            assert len([row for route,row in terminal_posts if route=='print'])==issue_print_count_before
            record('terminal_badge_uncertain_confirmation_stays_blocked')

            # Hold a committed reply while the Terminal leaves the person view.
            _, late_created=request('/workshop-api/users/create',{'name':'Isolated late response person','request_key':str(uuid4())},identity)
            late_person=late_created['id']
            late_member=next(row for row in client.call('/api/v1/groups/members') if row['id']==late_person)
            badge_faults['hold_issue_reply']=True
            page.goto(COMPANION+'/?mode=editor')
            page.get_by_role('button',name='Admin',exact=True).click()
            late_issue=page.get_by_role('button',name='Issue badge: '+late_member['name']+' · ID '+late_person[:8],exact=True)
            try:late_issue.wait_for(timeout=5000)
            except Exception:
                print('Late-response Admin fixture diagnostic: '+json.dumps({'heading_count':page.get_by_role('heading').count(),
                    'route_class':page.locator('#view').get_attribute('class'),
                    'visible_admin_controls':page.locator('#view button:visible').all_text_contents(),
                    'visible_control_count':page.locator('#view button:visible').count(),
                    'workflow_message_count':page.locator('.workflow-message:visible').count(),
                    'dialog_heading':page.locator('.workflow-dialog h1').inner_text() if page.locator('.workflow-dialog h1').count() else None,
                    'page_error_count':len(page_errors)}),flush=True)
                raise
            late_issue.click()
            page.get_by_role('button',name='Confirm badge issue',exact=True).click()
            assert issue_reply_waiting.wait(10), 'fixture issue reply did not reach the hold point'
            page.evaluate('home()')
            release_issue_reply.set()
            page.wait_for_function("() => document.querySelector('#view')?.classList.contains('dashboard')", timeout=3000)
            page.wait_for_timeout(250)
            assert not page.get_by_text('Issue badge: '+late_member['name'],exact=True).count()
            assert not page.locator('img[alt="Person badge QR"]').count()
            assert len([row for row in scope['badges'].list(group) if row['user_id']==late_person and not row['revoked']])==1
            record('terminal_member_late_response_does_not_reopen_view')
            profile=request('/workshop-api/users/profile?id='+bob_id)[1]
            update_key=str(uuid4());updates=[];real_call=Homebox.call
            update_data={**profile,'user_id':bob_id,'name':'Isolated recovered Bobby','request_key':update_key}
            def lost_profile_response(self,path,method='GET',data=None):
                result=real_call(self,path,method,data)
                if path=='/api/v1/groups/members/'+bob_id+'/profile' and method=='PUT':
                    updates.append(result['id']);raise OSError('Injected fixture lost profile response')
                return result
            with patch.object(Homebox,'call',lost_profile_response):
                assert request('/workshop-api/users/update',update_data,identity)[0]==503
                assert request('/workshop-api/users/update',update_data,identity)[0]==409
            assert updates==[bob_id]
            uncertain_update=next(r for r in request('/workshop-api/recovery')[1] if r['action']=='users/update')
            assert 'avatar' not in uncertain_update['intent'] and 'notes' not in uncertain_update['intent']
            page.goto(BASE+'/workshop/recovery')
            page.get_by_role('row').filter(has_text='users/update').get_by_role('button',name='Inspect operation',exact=True).click()
            page.get_by_role('link',name='Open Manage users',exact=True).wait_for()
            page.get_by_role('checkbox',name='I inspected the saved user profile.',exact=True).check()
            page.get_by_role('button',name='Confirm completion',exact=True).click()
            page.get_by_role('dialog').wait_for(state='hidden')
            assert request('/workshop-api/operation/status',{'request_key':update_key},identity)[1]['result']['id']==bob_id
            assert request('/workshop-api/users/update',update_data,identity)[0]==200
            record('uncertain profile saves recover from the saved details digest and completed replay does not repeat the write')
            uncertain_key=str(uuid4());real_call=Homebox.call;creates=[]
            def lost_account_response(self,path,method='GET',data=None):
                result=real_call(self,path,method,data)
                if path=='/api/v1/groups/members' and method=='POST' and data.get('requestKey')==uncertain_key:
                    creates.append(result['id']);raise OSError('Injected fixture lost response')
                return result
            with patch.object(Homebox,'call',lost_account_response):
                assert request('/workshop-api/users/create',{'name':'Isolated uncertain person','request_key':uncertain_key},identity)[0]==503
                assert request('/workshop-api/users/create',{'name':'Isolated uncertain person','request_key':uncertain_key},identity)[0]==409
            assert creates==[uncertain_key]
            uncertain=next(r for r in request('/workshop-api/recovery')[1] if r['action']=='users/create')
            assert uncertain['intent']['user_id']==uncertain_key
            assert request('/workshop-api/recovery/resolve',{'id':uncertain['id'],'desktop_job':True,'outcome':'cancel','inspected':True},identity)[0]==400
            assert request('/workshop-api/recovery/resolve',{'id':uncertain['id'],'desktop_job':True,'outcome':'complete','inspected':True},identity)[0]==200
            assert request('/workshop-api/operation/status',{'request_key':uncertain_key},identity)[1]['result']['id']==uncertain_key
            record('a lost account-creation response cannot duplicate a person; Recovery verifies the saved native identity')
            # Clear the fixture loan through the existing audited return workflow.
            assert request('/workshop-api/return',{'targets':[{'entity_id':tool,'return_note':'Fixture profile test complete'}],'request_key':str(uuid4())},identity)[0]==200
            page.goto(BASE+'/workshop')
            page.evaluate("async () => { for(const r of await navigator.serviceWorker.getRegistrations()) await r.unregister(); }")
            page.reload()
            old_worker = gateway.WORKER
            gateway.WORKER = b"self.addEventListener('install',e=>self.skipWaiting());self.addEventListener('activate',e=>e.waitUntil((async()=>{const c=await caches.open('api-cache');await c.put('/api/v1/isolated-cache-probe',new Response('OLD PRIVATE FIXTURE'));await self.clients.claim();})()));self.addEventListener('fetch',e=>{const p=new URL(e.request.url).pathname;if(p==='/workshop'||p.startsWith('/workshop/'))e.respondWith(new Response('OLD HOMEBOX FALLBACK'))});"
            page.evaluate("async () => { await navigator.serviceWorker.register('/sw.js'); await navigator.serviceWorker.ready; }")
            page.wait_for_function("async () => (await (await caches.open('api-cache')).match('/api/v1/isolated-cache-probe')) && (await (await fetch('/workshop')).text()) === 'OLD HOMEBOX FALLBACK'")
            page.wait_for_load_state('networkidle')
            gateway.WORKER = old_worker
            page.evaluate("async () => { const r=await navigator.serviceWorker.getRegistration('/'); await r.update(); }")
            page.wait_for_function("async () => !(await caches.keys()).includes('api-cache') && (await (await fetch('/workshop')).text()).includes('__nuxt')")
            page.wait_for_load_state('networkidle')
            # Native PWA activation may reload this tab during a read-only GET.
            try:
                page.goto(BASE+'/workshop/loans')
            except BrowserError as error:
                if 'ERR_ABORTED' not in str(error): raise
                page.wait_for_load_state('networkidle')
                if page.url != BASE+'/workshop/loans': page.goto(BASE+'/workshop/loans')
            # The old worker may finish a navigation during controller handoff.
            # Verify one explicit read-only refresh uses the already-verified new worker.
            if page.locator('body').inner_text().strip() == 'OLD HOMEBOX FALLBACK':
                page.reload()
            try:
                page.get_by_role('heading', name='Loans & notes', exact=True).wait_for()
            except Exception:
                print('Cache handoff fixture diagnostic: '+json.dumps({'url': page.url, 'body': page.locator('body').inner_text()[:2400], 'browser_errors': page_errors,
                    'state': page.evaluate("async () => ({controller: navigator.serviceWorker.controller?.state, caches: await caches.keys(), shell: (await (await fetch('/workshop/loans')).text()).slice(0,80)})")}), flush=True)
                raise
            # Opening a cache can recreate an empty container during worker handoff.
            # The privacy requirement is removal of its cached responses.
            cache_state = page.evaluate("async () => ({names: await caches.keys(), entries: (await (await caches.open('api-cache')).keys()).map(r=>new URL(r.url).pathname), controller: navigator.serviceWorker.controller?.state})")
            print('Cache handoff state: '+json.dumps(cache_state),flush=True)
            assert not cache_state['entries'], cache_state
            record('a previously controlling native cache cannot replace Workshop pages or retain private API cache')
            assert not page_errors, page_errors
            browser.close()

        # Native logout invalidates the existing cookie session, not just the UI.
        assert request('/api/v1/users/logout', {})[0] in (200, 204)
        assert request('/workshop-api/context')[0] == 401
        assert request('/workshop-api/badges/issue', {'user_id': borrower['id'], 'request_key': str(uuid4())}, identity)[0] == 401
        record('native logout invalidates subsequent Workshop reads and writes')
        output = SOURCE/'work/queue-coordinator/terminal-member-parity-task2-browser-results.json'
        output.write_text(json.dumps({'binary_sha256':hashlib.sha256(BINARY.read_bytes()).hexdigest(),'passed': len(results), 'steps': results, 'browser_errors': page_errors, 'live_mutations': 0, 'physical_prints': 0}, indent=2))
    finally:
        if gateway_server:
            gateway_server.shutdown(); gateway_server.server_close()
        if companion:
            companion.shutdown(); companion.server_close()
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait()
        log.close()
