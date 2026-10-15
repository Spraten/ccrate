#!/usr/bin/env python3
"""Prove the pinned editor and renderer load and work in offline Chromium."""
import argparse
import base64
import functools
import hashlib
import http.server
import io
import json
import pathlib
import subprocess
import threading
import time
import re
from urllib.parse import urlparse

PIN = 'eb118cc05b169c554066d823c44dc179aa3b96bb'
ASSET_PREFIX = '/workshop-api/label-assets/'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--compatibility-only', action='store_true')
    parser.add_argument('--host-fixtures-only', action='store_true', help='skip the already verified editor viewport loop but exercise bridge and native queue fixtures')
    parser.add_argument('--source-root', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    root = pathlib.Path(args.source_root).resolve()
    build = root / 'work/label-ui-build'
    manifest_path = build / 'manifest.json'
    if not manifest_path.is_file():
        raise SystemExit('FAIL: standalone editor bundle missing; run deploy/build-label-ui.py first')
    manifest = json.loads(manifest_path.read_text())
    if manifest.get('upstream_commit') != PIN:
        raise SystemExit('FAIL: bundle does not match the pinned PrintDesignPro revision')
    (build / 'compat-host.html').unlink(missing_ok=True)
    package = root / 'label-ui'

    def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

    for field, path in [
        ('dependencies_lock_sha256', package / 'pnpm-lock.yaml'),
        ('font_sha256', package / 'public/fonts/DejaVuSans.ttf'),
        ('font_license_sha256', package / 'public/fonts/DejaVu-Fonts-Copyright.txt'),
        ('upstream_license_sha256', package / 'vendor/print-design-pro/LICENSE'),
        ('patch_sha256', package / 'patches/0001-offline-fonts.patch'),
    ]:
        if manifest.get(field) != sha(path):
            raise SystemExit(f'FAIL: bundle manifest {field} does not match source')
    for relative, expected_hash in manifest.get('build_inputs', {}).items():
        if sha(package / relative) != expected_hash:
            raise SystemExit(f'FAIL: built editor source input changed: {relative}')
    actual_inputs = set(manifest.get('build_inputs', {}))
    expected_input_roots = ['package.json', 'pnpm-lock.yaml', 'vite.config.ts', 'editor.html', 'render.html', 'vendor-manifest.json', 'src', 'public', 'patches']
    expected_inputs = set()
    for item in expected_input_roots:
        path = package / item
        if path.is_file():
            expected_inputs.add(item)
        else:
            expected_inputs.update(entry.relative_to(package).as_posix() for entry in path.rglob('*') if entry.is_file())
    if actual_inputs != expected_inputs:
        raise SystemExit('FAIL: editor build input manifest is incomplete')
    source_hash = hashlib.sha256(b''.join(
        path.relative_to(package / 'vendor/print-design-pro').as_posix().encode() + b'\0' + path.read_bytes()
        for path in sorted((package / 'vendor/print-design-pro').rglob('*')) if path.is_file()
    )).hexdigest()
    if manifest.get('vendor_source_sha256') != source_hash:
        raise SystemExit('FAIL: bundle manifest vendored source hash does not match')
    actual_assets = {path.relative_to(build).as_posix() for path in build.rglob('*') if path.is_file() and path.name != 'manifest.json'}
    if actual_assets != set(manifest.get('runtime_assets', {})):
        raise SystemExit('FAIL: generated runtime asset list differs from its manifest')
    for relative, expected_hash in manifest['runtime_assets'].items():
        if sha(build / relative) != expected_hash:
            raise SystemExit(f'FAIL: generated asset hash mismatch: {relative}')
    if 'fonts.googleapis.com' in '\n'.join(p.read_text(errors='ignore') for p in build.rglob('*.js')):
        raise SystemExit('FAIL: editor bundle contains an external Google Fonts URL')

    output = pathlib.Path(args.output)
    if not output.is_absolute(): output = root / output
    output = output.resolve()
    try: output.relative_to((root / 'work').resolve())
    except ValueError: raise SystemExit('FAIL: report output must stay under source-root work/')
    output.mkdir(parents=True, exist_ok=True)
    host = output / 'compat-host.html'
    bridge_host = output / 'bridge-host.html'
    plain_http_host = output / 'plain-http-host.html'
    (output / 'label-editor.js').write_bytes((root / 'kiosk/label-editor.js').read_bytes())
    (output / 'workshop-tools.js').write_bytes((root / 'homebox-ui/overlay/lib/workshop-tools.js').read_bytes())
    bridge_host.write_text('''<!doctype html><html><body><div id="host"></div><script type="module">import {mountLabelDesigner} from "/label-editor.js";window.fixture={dirty:[],calls:0,writes:0,saved:null,touches:0};window.handle=mountLabelDesigner(document.querySelector("#host"),{src:"/workshop-api/label-assets/editor.html",context:()=>({host:'terminal',generation:7,instance:"session-a"}),dirty:value=>window.fixture.dirty.push(value),touchField:data=>{window.fixture.touches++;return Promise.resolve({field_id:data.field_id,instance_epoch:data.instance_epoch,value:'23.4'})},request:(action,data)=>{window.fixture.calls++;if(action==='labels/templates')return Promise.resolve([]);if(action==='labels/templates/save'){window.fixture.saved=data;return Promise.resolve({id:'saved-1',revision:1,document:data.document,name:data.name})}if(action==='labels/templates/result')return Promise.resolve(null);return new Promise(resolve=>window.fixture.resolve=resolve)},write:()=>{window.fixture.writes++;throw Error('physical print must be separately reviewed')}});</script></body></html>''')
    plain_http_host.write_text('''<!doctype html><html><body><div id="host"></div><div id="native"></div><script type="module">import {mountLabelDesigner} from "/label-editor.js";window.plainHttp={attempted:false,mounted:false,mountedNative:false,error:null,calls:[],dirty:[]};const options=host=>({src:'/label-assets/editor.html',context:()=>({host,generation:1,instance:'http-session-'+host}),dirty:value=>plainHttp.dirty.push(value),request:async(action,data)=>{plainHttp.calls.push({host,action,data});if(action==='labels/templates')return [];if(action==='labels/templates/save')return {id:'saved-http',revision:1,document:data.document,name:data.name};if(action==='labels/templates/result')return null;return {}},touchField:async data=>({field_id:data.field_id,instance_epoch:data.instance_epoch,value:'23.4'}),write:()=>{throw Error('unexpected physical write')}});try{window.handle=mountLabelDesigner(document.querySelector('#host'),options('terminal'));plainHttp.mounted=true;window.nativeHandle=mountLabelDesigner(document.querySelector('#native'),options('native'));plainHttp.mountedNative=true}catch(e){plainHttp.error=String(e)}finally{plainHttp.attempted=true}</script></body></html>''')
    def replace_fixture(source, old, new, label):
        if source.count(old) != 1:
            raise SystemExit(f'FAIL: expected one {label} fixture anchor')
        return source.replace(old, new)
    bridge_source = bridge_host.read_text()
    bridge_source = replace_fixture(bridge_source, "if(action==='labels/templates/save'){window.fixture.saved=data;return Promise.resolve({id:'saved-1',revision:1,document:data.document,name:data.name})}", '', 'bridge template-save request handler')
    bridge_source = replace_fixture(bridge_source, "write:()=>{window.fixture.writes++;throw Error('physical print must be separately reviewed')}", "write:(action,data)=>{window.fixture.writes++;if(action==='labels/templates/save'){window.fixture.saved=data;return Promise.resolve({id:'saved-1',revision:1,document:data.document,name:data.name})}throw Error('physical print must be separately reviewed')}", 'bridge guarded writer')
    bridge_host.write_text(bridge_source)
    plain_source = plain_http_host.read_text()
    plain_source = replace_fixture(plain_source, "calls:[],dirty:[]", "calls:[],writes:[],dirty:[]", 'plain HTTP write counter')
    plain_source = replace_fixture(plain_source, "if(action==='labels/templates/save')return {id:'saved-http',revision:1,document:data.document,name:data.name};", '', 'plain HTTP template-save request handler')
    plain_source = replace_fixture(plain_source, "write:()=>{throw Error('unexpected physical write')}", "write:(action,data)=>{plainHttp.writes.push({host,action,data});if(action==='labels/templates/save')return {id:'saved-http',revision:1,document:data.document,name:data.name};throw Error('unexpected physical write')}", 'plain HTTP guarded writer')
    plain_http_host.write_text(plain_source)
    from PIL import Image
    sheet_buffer=io.BytesIO();Image.new('RGB',(2550,3300),'white').save(sheet_buffer,format='PNG');sheet_bytes=sheet_buffer.getvalue()
    stale_sheet_buffer=io.BytesIO();Image.new('RGB',(2550,3300),(7,19,31)).save(stale_sheet_buffer,format='PNG');stale_sheet_bytes=stale_sheet_buffer.getvalue()
    sheet_image='data:image/png;base64,'+base64.b64encode(sheet_bytes).decode();sheet_hash=hashlib.sha256(sheet_bytes).hexdigest()
    native_host = output / 'native-host.html'
    native_source='''<!doctype html><html><body><main id="tools"><header><nav></nav></header><div id="view" tabindex="-1"></div><dialog id="dialog"><h2 id="dialog-title"></h2><div id="dialog-body"></div><button id="dialog-close">Close</button></dialog></main><script type="module">import {mountWorkshopTools} from "/workshop-tools.js";const ids=Array.from({length:19},(_,i)=>`00000000-0000-4000-8000-${String(i+1).padStart(12,'0')}`);window.nativeFixture={ids,calls:[],writes:[],errors:[],context:{identity:'fixture-session',manager:true,user:{id:'user-1'},group:{id:'group-1',name:'Fixture'}}};const templates=[{id:'letter-template',name:'Letter stock',profile:'letter',revision:2},{id:'letter-template-copy',name:'Letter stock copy',profile:'letter',revision:1}];const page={image:__IMAGE__,sha256:__HASH__};const workshop={context:{value:window.nativeFixture.context},refresh:async()=>window.nativeFixture.context,request:async(path,data)=>{window.nativeFixture.calls.push({path,data});if(path==='equipment')return ids.map((id,i)=>({id,name:`Fixture item ${i+1}`,assetId:`A-${i+1}`}));if(path==='locations'||path==='loans')return [];if(path==='labels/templates')return templates;if(path==='labels/preview')return {reviews:data.entity_ids.map((id,i)=>({review_id:`review-${i+1}`,profile:'letter',label_mm:[60,40],dpi:300,image:'data:image/png;base64,iVBORw0KGgo='}))};if(path==='labels/paper')return {pages:[page,page],geometry:{...data.geometry,dpi:300,columns:3,rows:6}};throw Error('Unexpected fixture request '+path)},write:async(path,data)=>{window.nativeFixture.writes.push({path,data});return {}}};window.nativeFixture.handle=mountWorkshopTools(document.querySelector('#tools'),'labels',workshop,()=>{},message=>window.nativeFixture.errors.push(message));</script></body></html>'''
    native_host.write_text(native_source.replace('__IMAGE__',json.dumps(sheet_image)).replace('__HASH__',json.dumps(sheet_hash)))
    terminal_show_label = next(line for line in (root / 'kiosk/index.html').read_text().splitlines() if line.startswith('async function showLabel(entity)'))
    terminal_host = output / 'terminal-host.html'
    terminal_host.write_text('''<!doctype html><html><body><main id="view"></main><script>window.terminalFixture={calls:[],preselected:[]};let inventory=[{id:'ordinary-1',name:'Ordinary item'}];const view=document.querySelector('#view'),status={textContent:''};function node(tag,text){const e=document.createElement(tag);if(text)e.textContent=text;return e}function heading(text){view.replaceChildren(node('h1',text))}function showLabelMaker(id){terminalFixture.preselected.push(id);return Promise.resolve()}function primary(text,fn){const b=node('button',text);b.onclick=fn;return b}function routeBack(){}function hardwarePanel(){}async function api(path,data){terminalFixture.calls.push({path,data});return path==='/label/preview'?{image:'data:image/png;base64,iVBORw0KGgo='}:{}}''' + terminal_show_label + '''\nwindow.runOrdinary=()=>showLabel({id:'ordinary-1',name:'Ordinary item'});window.runLocation=()=>{inventory=[];return showLabel({id:'location-1',name:'Storage location'})};</script></body></html>''')
    terminal_show_label_maker = (root / 'kiosk/index.html').read_text().split('async function showLabelMaker(preselectedEntityId=null){', 1)[1].split('\nasync function showLabel(entity)', 1)[0]
    terminal_actions_host = output / 'terminal-actions-host.html'
    terminal_actions_host.write_text('''<!doctype html><html><body><main id="view"></main><span id="status"></span><script>
window.terminalActions={calls:[],writes:[],paperResolve:null,delayPaper:false,errors:[],pending:0,completed:0};window.addEventListener('error',e=>terminalActions.errors.push(e.message));window.addEventListener('unhandledrejection',e=>terminalActions.errors.push(String(e.reason)));let identityGeneration=1,identityInstance='terminal-session',labelQueue=[],labelQueueContext='',labelMakerReviews=[],labelReviewOrder=[],labelMakerTemplates=[],labelDesignerHandle=null,labelMakerDirty=false,labelMakerBusy=false,labelActivityAt=0,routeRevision=0,routeStack=[],routeTitle='';
const view=document.querySelector('#view'),status=document.querySelector('#status');function node(tag,text,cls){const e=document.createElement(tag);if(text)e.textContent=text;if(cls)e.className=cls;return e}function heading(text){routeTitle=text;routeRevision++;view.replaceChildren(node('header',''));view.firstChild.className='toolbar';view.append(node('h1',text))}function primary(text,fn){const b=node('button',text);b.onclick=async(...args)=>{terminalActions.pending++;try{await fn(...args)}catch(e){terminalActions.errors.push(String(e))}finally{terminalActions.pending--;terminalActions.completed++}};return b}function captureRoute(){return null}function routeBack(){}function clearReviewed(){}function touchKeyboard(){}function workflowBusy(){return false}
async function api(path,data){terminalActions.calls.push({path,data});if(path==='/label/print'){terminalActions.writes.push({path,data});return {}}if(path==='/label/equipment')return [{id:'item-1',name:'Reviewed item',assetId:'A-1'}];if(path==='/label/templates')return [{id:'letter-1',name:'Letter',profile:'letter',revision:3}];if(path==='/label/preview')return {reviews:[{review_id:'review-1',profile:'letter',label_mm:[60,40],dpi:300,image:'data:image/png;base64,iVBORw0KGgo='}]};if(path==='/label/paper'){if(terminalActions.delayPaper)return await new Promise(resolve=>terminalActions.paperResolve=()=>resolve(terminalActions.stalePage));return terminalActions.page}throw Error('Unexpected Terminal fixture API '+path)}
''' + 'window.terminalActions.page={pages:[{image:' + json.dumps(sheet_image) + ',sha256:' + json.dumps(sheet_hash) + '}],geometry:{page_mm:[215.9,279.4],label_mm:[60,40],margin_mm:10,gap_mm:3,cut_guides:true,dpi:300,columns:2,rows:5}};window.terminalActions.stalePage={pages:[{image:' + json.dumps('data:image/png;base64,'+base64.b64encode(stale_sheet_bytes).decode()) + ',sha256:' + json.dumps(hashlib.sha256(stale_sheet_bytes).hexdigest()) + '}],geometry:window.terminalActions.page.geometry};\n' + 'async function showLabelMaker(preselectedEntityId=null){' + terminal_show_label_maker.replace('/label-assets/render.html', '/label-assets/render.html?fixture-delay=1') + '''
window.runTerminalActions=()=>showLabelMaker('item-1');
</script></body></html>''')
    terminal_identity = next(line for line in (root / 'kiosk/workflow-ui.js').read_text().splitlines() if line.startswith('updateIdentity=async function()'))
    context_host = output / 'terminal-context-host.html'
    context_host.write_text('''<!doctype html><html><body><div id="layout-nav"></div><div id="identity"></div><button id="end-session"></button><main id="view"><header class="toolbar"></header></main><script>
window.contextFixture={errors:[],equipment:null,templates:null,templateRequested:false,disposed:0};let identityGeneration=4,identityInstance='old-instance',identified=false,anonymousReturn=false,updateIdentity;
let labelDesignerHandle={dispose(){contextFixture.disposed++}},labelMakerDirty=true,labelMakerBusy=false,labelQueue=['old-item'],labelQueueContext='old-instance:4',labelMakerTemplates=[{id:'old'}],labelMakerReviews=[{review_id:'old-review'}],labelReviewOrder=['old-item'];
let returnCart=['unrelated-return'],checkoutCart=['unrelated-checkout'],returnKey=null,returnKitVersions={},kitDraft=null,returnReview=false,returnPicker=false,returnDestinationFor=null,checkoutMode=false,checkoutKey=null,checkoutKitVersions={},checkoutReview=false,pendingItemAction=null,itemActionOffer=null,itemActionOrigin=null,routeStack=[],routeRevision=0,routeTitle='';
const view=document.querySelector('#view'),status=document.createElement('span');function workflowBusy(){return false}let activeScanRequest=null;function node(tag,text){const element=document.createElement(tag);if(text)element.textContent=text;return element}function primary(text,fn){const button=node('button',text);button.onclick=fn;return button}function heading(text){routeTitle=text;routeRevision++;view.replaceChildren(node('header',''));view.firstChild.className='toolbar';view.append(node('h1',text))}function captureRoute(){return null}function routeBack(){}function acceptSession(data){identityGeneration=data.generation;identityInstance=data.instance;return true}function home(){}function ensureNavigation(){}function renderReturn(){}
function api(path){if(path==='/api/session')return Promise.resolve({generation:5,instance:'new-instance',user:null,return_only:false});if(path==='/label/equipment')return new Promise(resolve=>contextFixture.equipment=resolve);if(path==='/label/templates')return new Promise(resolve=>{contextFixture.templates=resolve;contextFixture.templateRequested=true});return Promise.resolve([])}
async function showLabelMaker(preselectedEntityId=null){''' + terminal_show_label_maker + '''
''' + terminal_identity + '''
window.runTerminalContext=async()=>{try{const pending=showLabelMaker();while(!contextFixture.equipment)await new Promise(resolve=>setTimeout(resolve,0));contextFixture.equipment([{id:'old-item',name:'Old item',assetId:'A'}]);while(!contextFixture.templateRequested)await new Promise(resolve=>setTimeout(resolve,0));await updateIdentity();contextFixture.templates([{id:'stale-template',revision:1,name:'Stale',profile:'letter'}]);await pending;if(identityGeneration!==5||identityInstance!=='new-instance'||contextFixture.disposed!==1||labelDesignerHandle!==null||labelQueue.length||labelMakerReviews.length||labelReviewOrder.length||labelMakerTemplates.length||labelQueueContext!==''||labelMakerDirty||labelMakerBusy)throw Error('session transition did not dispose and clear stale label state');if(returnCart[0]!=='unrelated-return'||checkoutCart[0]!=='unrelated-checkout')throw Error('no-badge identity refresh altered unrelated carts');if(!view.textContent.includes('session changed'))throw Error('stale label panel was not replaced with session-change notice')}catch(error){contextFixture.errors.push(error.message)}finally{contextFixture.done=true}};runTerminalContext();
</script></body></html>''')
    pi_source = (root / 'homebox-ui/overlay/components/Workshop/PiPrint.vue').read_text()
    pi_load = pi_source[pi_source.index('async function loadTemplates() {'):pi_source.index('\nonMounted(loadTemplates)')].replace('workshop.request<any[]>', 'workshop.request').replace(' as Error', '')
    pi_context = pi_source[pi_source.index('function contextChanged('):pi_source.index('\nwatch(')].replace(': unknown[]', '')
    pi_host = output / 'pi-print-context-host.html'
    pi_host.write_text(
        '<!doctype html><html><body><script>'
        'window.piPrintFixture={done:false,error:null,requests:0};const ref=value=>({value});'
        'let disposed=false,generation=0;const templates=ref([]),templateId=ref(""),loaded=ref(false),error=ref(""),preview=ref(null),sending=ref(false),uncertain=ref(false);let workshop;'
        'function setContext(identity){const previous=workshop.context.value;workshop.context.value={identity,group:{id:identity}};contextChanged([null,null,identity,identity],[null,null,previous.identity,previous.group.id])}'
        'workshop={context:{value:{identity:null,group:{id:null}}},refresh:async()=>{if(!workshop.context.value.identity)setContext("collection-A");return workshop.context.value},request:async()=>{window.piPrintFixture.requests++;const identity=workshop.context.value.identity;if(window.piPrintFixture.requests===1)await new Promise(resolve=>setTimeout(resolve,60));return [{id:identity+"-template",revision:1,name:identity,profile:"letter"}]}};'
        + pi_load + '\n' + pi_context + '\n'
        'window.runPiPrintRace=async()=>{try{const first=loadTemplates();setTimeout(()=>setContext("collection-B"),10);await first;await new Promise(resolve=>setTimeout(resolve,100));if(!loaded.value||templates.value[0]?.id!=="collection-B-template"||templateId.value!=="collection-B-template"||window.piPrintFixture.requests!==2)throw Error("context change did not discard the late old template result and reload the new collection")}catch(e){window.piPrintFixture.error=e.message}finally{window.piPrintFixture.done=true}};runPiPrintRace()'
        '</script></body></html>'
    )
    host.write_text('''<!doctype html><html><head><link rel="icon" href="data:,"><style>body{margin:7px;color:rgb(1,2,3)}#probe{font:13px monospace;color:rgb(1,2,3)}</style></head><body><div id="probe">host style sentinel</div><iframe id="editor" title="PrintDesignPro" src="/workshop-api/label-assets/editor.html" style="display:block;width:100%;height:calc(100vh - 35px);border:0"></iframe></body></html>''')

    class StagedAssetHandler(http.server.SimpleHTTPRequestHandler):
        def end_headers(self):
            if urlparse(self.path).path.startswith(ASSET_PREFIX) or urlparse(self.path).path.startswith('/label-assets/'):
                self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data: blob:; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'")
            super().end_headers()
        def translate_path(self, path):
            parsed = urlparse(path)
            route = parsed.path
            if route == '/bridge-host.html': return str(bridge_host)
            if route == '/plain-http-host.html': return str(plain_http_host)
            if route == '/native-host.html': return str(native_host)
            if route == '/terminal-host.html': return str(terminal_host)
            if route == '/terminal-actions-host.html': return str(terminal_actions_host)
            if route == '/terminal-context-host.html': return str(context_host)
            if route == '/pi-print-context-host.html': return str(pi_host)
            if route == '/label-editor.js': return str(output / 'label-editor.js')
            if route == '/workshop-tools.js': return str(output / 'workshop-tools.js')
            if route.startswith(ASSET_PREFIX):
                route = route[len(ASSET_PREFIX) - 1:]
            elif route.startswith('/label-assets/'):
                route = route[len('/label-assets'):]
            return super().translate_path(route)
        def do_GET(self):
            if urlparse(self.path).path.endswith('/render.html') and urlparse(self.path).query == 'fixture-delay=1': time.sleep(0.6)
            super().do_GET()

    handler = functools.partial(StagedAssetHandler, directory=str(build))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    (build / 'compat-host.html').write_text(host.read_text())
    report = {'upstream_commit': PIN, 'manifest_sha256': manifest_digest, 'asset_prefix': ASSET_PREFIX, 'viewports': [], 'outbound_requests': [], 'bad_asset_paths': [], 'font_requests': [], 'host_styles_unchanged': True, 'bridge_checks': []}

    def guard(route):
        url = route.request.url
        parsed = urlparse(url)
        allowed_origins={base,base.replace('127.0.0.1','inventory.test')}
        if f'{parsed.scheme}://{parsed.netloc}' not in allowed_origins:
            report['outbound_requests'].append(url)
            route.abort()
            return
        if parsed.path not in ('/compat-host.html','/bridge-host.html','/plain-http-host.html','/label-editor.js','/native-host.html','/terminal-host.html','/terminal-actions-host.html','/terminal-context-host.html','/pi-print-context-host.html','/workshop-tools.js') and not parsed.path.startswith(ASSET_PREFIX) and not parsed.path.startswith('/label-assets/'):
            report['bad_asset_paths'].append(parsed.path)
            route.abort()
            return
        route.continue_()

    try:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as error:
            raise SystemExit(f'FAIL: installed Playwright unavailable: {error}')
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox', '--disable-dev-shm-usage','--host-resolver-rules=MAP inventory.test 127.0.0.1'])
            try:
                viewport_cases = [] if args.host_fixtures_only else [(800, 480, 'terminal'), (1366, 850, 'desktop'), (390, 844, 'mobile')]
                for width, height, name in viewport_cases:
                    context = browser.new_context(viewport={'width': width, 'height': height}, device_scale_factor=1)
                    page = context.new_page()
                    page_errors = []
                    page.on('pageerror', lambda error: page_errors.append(str(error)))

                    page.route('**/*', guard)
                    page.goto(base + '/compat-host.html')
                    frame = page.frame_locator('#editor')
                    frame.locator('[data-pp-designer]').wait_for(timeout=30000)
                    font_sizes = frame.locator('body').evaluate('() => [window.labelFontPointsFromMm(2.25), window.labelFontPointsFromMm(3)]')
                    expected = [2.25 * 72 / 25.4, 3 * 72 / 25.4]
                    if any(abs(actual - wanted) > 1e-12 for actual, wanted in zip(font_sizes, expected)):
                        raise AssertionError(f'{name}: millimetre/point conversion mismatch: {font_sizes}')
                    before = page.locator('#probe').evaluate("e => ({style:e.getAttribute('style'), color:getComputedStyle(e).color, margin:getComputedStyle(document.body).margin})")
                    frame.locator('[data-pp-palette-tile="text"]').click(timeout=10000, force=(name == 'mobile'))
                    editor_text = frame.locator('[data-pp-text-section] textarea')
                    editor_text.fill('Offline compatibility edit')
                    if editor_text.input_value() != 'Offline compatibility edit':
                        raise AssertionError(f'{name}: text edit did not stick')
                    element = frame.locator('[data-pp-element-type="text"]').last
                    element.wait_for()
                    element.scroll_into_view_if_needed()
                    initial_style = element.get_attribute('style')
                    box = element.bounding_box()
                    if not box: raise AssertionError(f'{name}: text element is not rendered')
                    x, y = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
                    if not page.evaluate('([x,y]) => x >= 0 && y >= 0 && x < innerWidth && y < innerHeight', [x, y]):
                        raise AssertionError(f'{name}: selected element center is outside the host viewport: {box}, viewport={page.evaluate("() => [innerWidth,innerHeight,scrollX,scrollY]")}')
                    page.mouse.move(x, y)
                    page.mouse.down()
                    page.mouse.move(x + 16, y + 12, steps=4)
                    page.mouse.up()
                    moved_style = element.get_attribute('style')
                    if moved_style == initial_style:
                        raise AssertionError(f'{name}: upstream pointer move did not change element geometry')
                    handle = frame.locator('[data-pp-handle="se"]')
                    handle_box = handle.bounding_box()
                    if not handle_box: raise AssertionError(f'{name}: upstream resize handle is missing')
                    hx, hy = handle_box['x'] + handle_box['width']/2, handle_box['y'] + handle_box['height']/2
                    page.mouse.move(hx, hy)
                    page.mouse.down()
                    page.mouse.move(hx + 18, hy + 14, steps=4)
                    page.mouse.up()
                    resized_style = element.get_attribute('style')
                    if resized_style == moved_style:
                        raise AssertionError(f'{name}: upstream resize handle did not change element geometry')
                    frame.locator('[data-pp-undo]').click()
                    if element.get_attribute('style') == resized_style:
                        raise AssertionError(f'{name}: upstream undo did not restore the resize')
                    after = page.locator('#probe').evaluate("e => ({style:e.getAttribute('style'), color:getComputedStyle(e).color, margin:getComputedStyle(document.body).margin})")
                    if before != after:
                        report['host_styles_unchanged'] = False
                        raise AssertionError(f'{name}: editor styles leaked into host page')
                    if page_errors: raise AssertionError(f'{name}: browser errors: {page_errors}')
                    report['viewports'].append({'name': name, 'width': width, 'height': height, 'text_edit': True, 'move': True, 'resize': True, 'undo': True, 'font_floor_pt': font_sizes})
                    context.close()

                bridge_page = browser.new_page(viewport={'width': 800, 'height': 480})
                bridge_page.route('**/*', guard)
                bridge_page.goto(base + '/bridge-host.html')
                bridge_frame = bridge_page.frame_locator('iframe[title="Label maker"]')
                bridge_frame.locator('[data-pp-designer]').wait_for(timeout=30000)
                nonce = bridge_page.locator('iframe').get_attribute('src').split('nonce=', 1)[1]
                bridge_page.evaluate('fixture.dirty=[];fixture.calls=0')
                bridge_frame.locator('body').evaluate('''(body,nonce)=>parent.postMessage({channel:'label-designer',nonce:'wrong',type:'dirty',data:{dirty:true}},location.origin)''', nonce)
                bridge_page.evaluate('''nonce=>{const frame=document.querySelector('iframe');window.postMessage({channel:'label-designer',nonce, type:'dirty',data:{dirty:true}},location.origin);window.dispatchEvent(new MessageEvent('message',{origin:'https://attacker.invalid',source:frame.contentWindow,data:{channel:'label-designer',nonce,type:'dirty',data:{dirty:true}}}))}''', nonce)
                bridge_page.wait_for_timeout(50)
                if bridge_page.evaluate('fixture.dirty.length'):
                    raise AssertionError('bridge accepted wrong nonce or wrong message source')
                bridge_frame.locator('body').evaluate('''(body,nonce)=>parent.postMessage({channel:'label-designer',nonce,type:'dirty',data:{dirty:true}},location.origin)''', nonce)
                bridge_page.wait_for_function('fixture.dirty.length===1 && fixture.dirty[0]===true')
                bridge_frame.locator('body').evaluate('''(body,nonce)=>parent.postMessage({channel:'label-designer',nonce,type:'request',id:'unknown',action:'arbitrary/print'},location.origin)''', nonce)
                bridge_page.wait_for_timeout(50)
                if bridge_page.evaluate('fixture.calls'):
                    raise AssertionError('bridge forwarded an unknown action')
                bridge_frame.locator('body').evaluate('''body=>{window.__printResponse=null;window.addEventListener('message',event=>{if(event.data?.id==='physical-guard')window.__printResponse=event.data});parent.postMessage({channel:'label-designer',nonce:new URLSearchParams(location.search).get('nonce'),type:'request',id:'physical-guard',action:'labels/print',data:{entity_id:'fixture-item'}},location.origin)}''')
                try: bridge_page.wait_for_function("document.querySelector('iframe').contentWindow.__printResponse!==null", timeout=2500)
                except Exception as error: raise AssertionError(f'physical print fixture got no response: host={bridge_page.evaluate("({calls:fixture.calls,writes:fixture.writes})")}, child={bridge_frame.locator("body").evaluate("window.__printResponse")}, src={bridge_page.locator("iframe").get_attribute("src")}') from error
                print_response = bridge_frame.locator('body').evaluate('window.__printResponse')
                if print_response.get('ok') or 'separately reviewed' not in print_response.get('error', ''): raise AssertionError(f'physical print was not rejected by the guarded writer: {print_response}')
                if bridge_page.evaluate('fixture.calls!==0||fixture.writes!==1'):
                    raise AssertionError('iframe print request bypassed the guarded physical write callback')
                bridge_frame.locator('body').evaluate('''(body)=>{window.__responses=0;window.addEventListener('message',e=>{if(e.data?.type==='response')window.__responses++});parent.postMessage({channel:'label-designer',nonce:new URLSearchParams(location.search).get('nonce'),type:'request',id:'late-context',action:'labels/preview'},location.origin)}''')
                bridge_page.wait_for_function('fixture.calls===1')
                bridge_page.evaluate('handle.invalidate()')
                bridge_page.evaluate('fixture.resolve({templates:[]})')
                bridge_page.wait_for_timeout(150)
                if bridge_frame.locator('body').evaluate('window.__responses'):
                    raise AssertionError('bridge delivered a result after its context epoch was invalidated')
                bridge_frame.locator('[data-pp-element-type="text"]').first.click()
                latest_text = bridge_frame.locator('[data-pp-text-section] textarea')
                latest_text.fill('Immediate synchronous Save probe')
                bridge_frame.locator('body').evaluate('''body=>{const original=window.matchMedia.bind(window);window.matchMedia=query=>query.includes('pointer: coarse')?{matches:true,media:query,onchange:null,addListener(){},removeListener(){},addEventListener(){},removeEventListener(){},dispatchEvent(){return false}}:original(query)}''')
                numeric = bridge_frame.locator('input[type="number"]').first
                numeric.click()
                try: bridge_page.wait_for_function('fixture.touches===1', timeout=1500)
                except Exception as error: raise AssertionError(f'Terminal touch-field callback was not reached: touches={bridge_page.evaluate("fixture.touches")}, field={numeric.evaluate("e=>({type:e.type,readOnly:e.readOnly,focused:document.activeElement===e,value:e.value})")}') from error
                bridge_page.wait_for_function('''() => {const f=[...document.querySelector('iframe').contentDocument.querySelectorAll('input[type=number]')][0];return f&&f.value==='23.4'}''')
                bridge_page.evaluate('window.confirm=()=>false')
                if bridge_page.evaluate('handle.canLeave()'):
                    raise AssertionError('dirty editor incorrectly allowed departure')
                bridge_frame.get_by_role('button', name='Save', exact=True).click()
                try: bridge_page.wait_for_function('fixture.saved!==null', timeout=1500)
                except Exception as error: raise AssertionError(f'Editor Save did not reach the bridge: message={bridge_frame.locator(".label-host-message").inner_text()}') from error
                saved = bridge_page.evaluate('fixture.saved')
                if bridge_page.evaluate('fixture.writes!==2||fixture.calls!==1'):
                    raise AssertionError(f'template Save did not use the guarded writer without a request fallback: {bridge_page.evaluate("({calls:fixture.calls,writes:fixture.writes})")}')
                if not re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}', saved['request_key']) or saved.get('session_generation') != 7 or saved.get('session_instance') != 'session-a':
                    raise AssertionError(f'terminal template Save lost request identity: {saved}')
                updated = next((element for element in saved['document']['elements'] if element.get('content') == 'Immediate synchronous Save probe'), None)
                if not updated: raise AssertionError('immediate Save missed the last text edit from the synchronous Pinia document store')
                if abs(updated['xMm'] - 23.4) > .001: raise AssertionError(f'touch numeric geometry was not committed to Pinia before Save: {updated["xMm"]}')
                if not any(element.get('type')=='qr' and element.get('content')=='{{item_path}}' for element in saved['document']['elements']): raise AssertionError('saving the touched text element lost the canonical item QR token')
                bridge_frame.get_by_role('button', name='Undo', exact=True).click()
                bridge_page.wait_for_timeout(150)
                if not bridge_page.evaluate('fixture.dirty.at(-1)===true'):
                    raise AssertionError(f'Undo did not restore dirty state after Save; events={bridge_page.evaluate("fixture.dirty")}')
                report['bridge_checks'] = ['wrong origin rejected', 'wrong nonce rejected', 'wrong source rejected', 'unknown action rejected', 'physical print requires guarded write callback', 'template Save uses guarded write callback with request and session identity', 'late context result discarded', 'touch numeric Enter committed geometry before Save', 'immediate Save included final edit', 'undo restored dirty guard']
                bridge_page.close()

                plain_page=browser.new_page(viewport={'width':800,'height':480})
                plain_page.route('**/*',guard)
                plain_page.goto(base.replace('127.0.0.1','inventory.test')+'/plain-http-host.html')
                plain_page.wait_for_function('plainHttp.attempted===true')
                plain_state=plain_page.evaluate("({secure:isSecureContext,randomUUID:typeof crypto.randomUUID,randomValues:typeof crypto.getRandomValues,mounted:plainHttp.mounted,mountedNative:plainHttp.mountedNative,error:plainHttp.error,nonce:new URL(document.querySelectorAll('iframe')[0]?.src||'http://invalid').searchParams.get('nonce'),nativeNonce:new URL(document.querySelectorAll('iframe')[1]?.src||'http://invalid').searchParams.get('nonce')})")
                if plain_state['secure'] or plain_state['randomValues']!='function': raise AssertionError(f'plain HTTP fixture did not exercise an insecure LAN-like origin: {plain_state}')
                uuid4=r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}'
                if not plain_state['mounted'] or not plain_state['mountedNative'] or not re.fullmatch(uuid4,plain_state['nonce'] or '') or not re.fullmatch(uuid4,plain_state['nativeNonce'] or ''): raise AssertionError(f'Label adapter failed to mount for both hosts with a secure UUIDv4 nonce on ordinary HTTP: {plain_state}')
                plain_frame=plain_page.frame_locator('iframe').nth(0)
                native_plain_frame=plain_page.frame_locator('iframe').nth(1)
                plain_frame.locator('[data-pp-designer]').wait_for(timeout=10000)
                native_plain_frame.locator('[data-pp-designer]').wait_for(timeout=10000)
                plain_page.evaluate("plainHttp.dirty=[];for(const [i,frame] of [...document.querySelectorAll('iframe')].entries()){const nonce=new URL(frame.src).searchParams.get('nonce'),other=document.querySelectorAll('iframe')[1-i],send=(source,origin,n,data)=>window.dispatchEvent(new MessageEvent('message',{origin,source,data:{channel:'label-designer',nonce:n,type:'dirty',data:{dirty:data}}}));send(frame.contentWindow,location.origin,nonce,true);send(frame.contentWindow,location.origin,'wrong-nonce',true);send(frame.contentWindow,'https://attacker.invalid',nonce,true);send(other.contentWindow,location.origin,nonce,true)}")
                if plain_page.evaluate('JSON.stringify(plainHttp.dirty)')!='[true,true]': raise AssertionError(f'plain HTTP adapters failed valid nonce/source acceptance or accepted a forged nonce/origin/source: {plain_page.evaluate("plainHttp.dirty")}')
                plain_page.evaluate("for(const frame of document.querySelectorAll('iframe')){const nonce=new URL(frame.src).searchParams.get('nonce');window.dispatchEvent(new MessageEvent('message',{origin:location.origin,source:frame.contentWindow,data:{channel:'label-designer',nonce,type:'dirty',data:{dirty:false}}}))}")
                if plain_page.evaluate('JSON.stringify(plainHttp.dirty)')!='[true,true,false,false]': raise AssertionError('plain HTTP adapters did not accept valid nonce messages for both host types')
                plain_frame.locator('[data-pp-palette-tile="text"]').click()
                text_element=plain_frame.locator('[data-pp-element-type="text"]').last
                text_element.wait_for(timeout=5000)
                element_id=text_element.get_attribute('data-pp-element-id')
                if not element_id or not re.fullmatch(uuid4,element_id): raise AssertionError(f'plain HTTP palette element did not receive a cryptographic UUIDv4 id: {element_id}')
                plain_frame.get_by_role('button',name='Undo',exact=True).click()
                plain_frame.get_by_role('button',name='Save',exact=True).click()
                try: plain_page.wait_for_function("plainHttp.writes.some(call=>call.action==='labels/templates/save')",timeout=5000)
                except Exception as error: raise AssertionError(f'plain HTTP editor Save failed: parent={plain_page.evaluate("plainHttp.calls")}, frame={plain_frame.locator("body").inner_text()}, message={plain_frame.locator(".label-host-message").inner_text()}') from error
                saved_call=plain_page.evaluate("plainHttp.writes.find(call=>call.action==='labels/templates/save')")
                if plain_page.evaluate("plainHttp.calls.some(call=>call.action==='labels/templates/save')"): raise AssertionError('plain HTTP template Save bypassed the guarded write callback')
                if not re.fullmatch(uuid4,saved_call['data']['request_key']) or saved_call['data'].get('session_generation') != 1 or saved_call['data'].get('session_instance') != 'http-session-terminal': raise AssertionError(f'plain HTTP template Save lost request or session identity: {saved_call}')
                report['plain_http_nonce_fixture']={'secure_context':False,'random_values_available':True,'random_uuid_type':plain_state['randomUUID'],'terminal_and_native_mounted':True,'both_host_nonce_source_origin_guards':True,'adapter_nonce':plain_state['nonce'],'palette_element_uuid':element_id,'template_save_request_key':saved_call['data']['request_key'],'template_save_write_callback':True,'editor_request_and_save':True}
                plain_page.close()

                native_page = browser.new_page(viewport={'width': 800, 'height': 480})
                native_page_errors = []
                native_page.on('pageerror', lambda error: native_page_errors.append(str(error)))
                native_page.add_init_script("window.__printCalls=0;window.print=function(){window.top.__printCalls++;window.dispatchEvent(new Event('afterprint'))}")
                native_page.route('**/*', guard)
                native_page.goto(base + '/native-host.html')
                native_page.get_by_role('heading', name='Label maker').wait_for(timeout=10000)
                picks = native_page.locator('.label-item-picker input[type=checkbox]')
                if picks.count() != 19: raise AssertionError(f'native queue fixture expected 19 ordinary items, found {picks.count()}')
                for index in range(19): picks.nth(index).check()
                if native_page_errors: raise AssertionError(f'native selection raised browser errors: {native_page_errors}')
                native_page.get_by_label('Saved label template').select_option('letter-template')
                native_page.get_by_role('button', name='Review selected labels').click()
                native_page.wait_for_function("nativeFixture.calls.some(row=>row.path==='labels/preview')", timeout=5000)
                if native_page_errors or native_page.locator('#view .error').count(): raise AssertionError(f'native review rendered an error: page={native_page_errors}, view={native_page.locator("#view .error").all_inner_texts()}')
                ids = native_page.evaluate("nativeFixture.ids")
                preview_request = native_page.evaluate("nativeFixture.calls.find(row=>row.path==='labels/preview').data")
                if preview_request['entity_ids'] != ids: raise AssertionError('native batch review changed the 19-item UUID order')
                native_page.get_by_role('button', name='Compose reviewed Letter sheet').click()
                native_page.wait_for_function("nativeFixture.calls.some(row=>row.path==='labels/paper')", timeout=5000)
                paper_request = native_page.evaluate("nativeFixture.calls.find(row=>row.path==='labels/paper').data")
                if paper_request['review_ids'] != [f'review-{i}' for i in range(1, 20)]: raise AssertionError('native paper preview changed the ordered review tickets')
                if native_page.locator('img[alt^="Reviewed Letter sheet"]').count() != 2: raise AssertionError('19 reviewed labels did not produce the two mocked paper preview pages')
                print_count_before=native_page.evaluate("nativeFixture.calls.filter(row=>row.path==='labels/paper').length")
                native_page.get_by_role('button',name='Print reviewed pages').click()
                try: native_page.wait_for_function("nativeFixture.errors.some(value=>String(value).includes('Physical output is unconfirmed'))",timeout=10000)
                except Exception as error: raise AssertionError(f'Print action did not reach unconfirmed state: errors={native_page.evaluate("nativeFixture.errors")}, page={native_page_errors}, context={native_page.evaluate("({calls:nativeFixture.calls.filter(x=>x.path===\'labels/paper\').length,prints:window.__printCalls,frames:[...document.querySelectorAll(\'iframe\')].map(x=>({src:x.src,loaded:!!x.contentWindow?.exportReviewedPaper,children:[...x.contentDocument.querySelectorAll(\'iframe\')].map(c=>({srcdoc:!!c.srcdoc,html:c.contentDocument?.body?.innerHTML?.slice(0,100)}))}))})")}') from error
                if native_page.evaluate('window.__printCalls') != 1: raise AssertionError('PrintDesignPro did not call the stubbed frame window.print exactly once')
                if native_page.locator('img[alt^="Reviewed Letter sheet"]').count()!=2: raise AssertionError('closing/cancelling the browser print dialog removed reviewed pages')
                if native_page.evaluate('nativeFixture.writes.length')!=0: raise AssertionError('browser print dialog touched Pi print/write status')
                if native_page.evaluate("nativeFixture.calls.filter(row=>row.path==='labels/paper').length")!=print_count_before+1: raise AssertionError('browser Print action reused stale pages instead of rechecking reviews')
                download_count_before=native_page.evaluate("nativeFixture.calls.filter(row=>row.path==='labels/paper').length")
                with native_page.expect_download(timeout=15000) as download_info:
                    native_page.get_by_role('button',name='Download reviewed PDF').click()
                download=download_info.value;download_path=download.path()
                if pathlib.Path(download_path).read_bytes()[:4]!=b'%PDF': raise AssertionError('native queue PDF action did not download a real PDF')
                if native_page.evaluate("nativeFixture.calls.filter(row=>row.path==='labels/paper').length")!=download_count_before+1: raise AssertionError('native PDF action reused stale pages instead of rechecking reviews')
                if native_page.evaluate('nativeFixture.writes.length') != 0: raise AssertionError('paper export unexpectedly submitted a Pi print')
                if picks.count() != 19 or not all(picks.nth(i).is_checked() for i in range(19)): raise AssertionError('batch sheet preview lost the original selection')
                old_print = native_page.locator('.label-review-card button').first.element_handle()
                if not old_print: raise AssertionError('native review did not render reviewed label print controls')
                picks.nth(0).uncheck()
                if native_page.locator('.label-review-card').count() or native_page.locator('img[alt^="Reviewed Letter sheet"]').count() or native_page.get_by_role('button', name='Compose reviewed Letter sheet').is_enabled(): raise AssertionError('changing queue selection left stale reviewed labels or paper pages enabled')
                old_print.evaluate('(button)=>button.click()')
                if native_page.evaluate('nativeFixture.writes.length') != 0 or 'Review the current selection again' not in native_page.locator('#view .error').inner_text(): raise AssertionError('a detached old print control remained active after selection changed')
                native_page.get_by_label('Saved label template').select_option('letter-template-copy')
                native_page.get_by_role('button', name='Review selected labels').click()
                native_page.wait_for_function("nativeFixture.calls.filter(row=>row.path==='labels/preview').length===2", timeout=5000)
                latest_review = native_page.evaluate("nativeFixture.calls.filter(row=>row.path==='labels/preview').at(-1).data")
                if latest_review['template_id'] != 'letter-template-copy' or len(latest_review['entity_ids']) != 18 or native_page.locator('.label-review-card').count() != 18: raise AssertionError('reselected queue did not render a fresh review for the selected template and items')
                notices=native_page.evaluate('nativeFixture.errors')
                if native_page_errors or notices != ['Print dialog closed. Physical output is unconfirmed; the reviewed pages remain available.', 'PDF download requested. The reviewed pages remain available.']: raise AssertionError(f'native queue emitted an error or unexpected status: browser={native_page_errors}, notices={notices}')
                report['native_queue_fixture'] = {'selected_ids_in_order': ids, 'review_count': len(preview_request['entity_ids']), 'sheet_pages': 2, 'pdf_download': True, 'fresh_paper_validation_for_pdf': True, 'print_dialog_unconfirmed_and_pages_retained': True, 'print_writes': 0, 'selection_preserved': True, 'selection_change_cleared_old_review': True, 'new_selection_and_template_reviewed': True, 'browser_errors': native_page_errors, 'notices': native_page.evaluate('nativeFixture.errors')}
                native_page.close()

                terminal_page = browser.new_page(viewport={'width': 800, 'height': 480})
                terminal_page.route('**/*', guard)
                terminal_page.goto(base + '/terminal-host.html')
                terminal_page.evaluate('runOrdinary()')
                if terminal_page.evaluate('JSON.stringify(terminalFixture.preselected)') != '["ordinary-1"]' or terminal_page.evaluate('terminalFixture.calls.length'):
                    raise AssertionError('Terminal ordinary-item label action did not enter the shared saved-template review queue')
                terminal_page.evaluate('runLocation()')
                legacy = terminal_page.evaluate('terminalFixture.calls.at(-1)')
                if legacy['path'] != '/label/preview' or legacy['data'] != {'entity_id':'location-1'}:
                    raise AssertionError('Terminal location QR preview lost its existing legacy path')
                terminal_page.get_by_role('button', name='Print one label').click()
                terminal_page.wait_for_function("terminalFixture.calls.length===2")
                legacy_print = terminal_page.evaluate('terminalFixture.calls.at(-1)')
                if legacy_print['path'] != '/label/print' or legacy_print['data'].get('entity_id') != 'location-1' or not legacy_print['data'].get('request_key'):
                    raise AssertionError('Terminal location print did not retain its existing request-key flow')
                report['terminal_label_routes'] = {'ordinary_item_enters_review_queue': True, 'location_preview_legacy_payload': legacy['data'], 'location_print_request_key': True}
                terminal_page.close()

                terminal_actions_page = browser.new_page(viewport={'width': 800, 'height': 480}, accept_downloads=True)
                terminal_actions_page.add_init_script("window.__terminalPrintCalls=0;window.__terminalBlobHashes=[];const nativeCreateObjectURL=URL.createObjectURL.bind(URL);URL.createObjectURL=function(blob){if(blob.type==='image/png')blob.arrayBuffer().then(bytes=>crypto.subtle.digest('SHA-256',bytes)).then(digest=>window.top.__terminalBlobHashes.push([...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join('')));return nativeCreateObjectURL(blob)};window.print=function(){window.top.__terminalPrintCalls++;window.dispatchEvent(new Event('afterprint'))}")
                terminal_actions_page.route('**/*', guard)
                terminal_actions_page.goto(base + '/terminal-actions-host.html')
                terminal_actions_page.evaluate('runTerminalActions()')
                terminal_actions_page.get_by_label('Saved label template').select_option('letter-1')
                terminal_actions_page.get_by_role('button', name='Review 1 selected labels').click()
                try: terminal_actions_page.wait_for_function("labelMakerReviews.length===1", timeout=5000)
                except Exception as error: raise AssertionError(f'Terminal queue review failed: calls={terminal_actions_page.evaluate("terminalActions.calls")}, errors={terminal_actions_page.evaluate("terminalActions.errors")}, text={terminal_actions_page.locator("body").inner_text()}') from error
                if terminal_actions_page.locator('button:has-text("Compose reviewed Letter sheet")').count()!=1: raise AssertionError(f'Terminal review produced no Compose control: buttons={terminal_actions_page.locator("button").evaluate_all("buttons=>buttons.map(b=>({text:b.textContent,disabled:b.disabled}))")}, queue={terminal_actions_page.evaluate("({ids:labelQueue,order:labelReviewOrder,reviews:labelMakerReviews,templates:labelMakerTemplates})")}, errors={terminal_actions_page.evaluate("terminalActions.errors")}')
                completed_before_compose=terminal_actions_page.evaluate('terminalActions.completed')
                terminal_actions_page.get_by_role('button', name='Compose reviewed Letter sheet').click()
                terminal_actions_page.wait_for_function("terminalActions.calls.some(row=>row.path==='/label/paper')")
                terminal_actions_page.wait_for_function(f"terminalActions.pending===0 && terminalActions.completed>{completed_before_compose}")
                terminal_reviewed_hash=sheet_hash
                displayed=terminal_actions_page.locator('img[alt^="Reviewed sheet "]').evaluate_all("images=>images.map(image=>({sha:image.dataset.sha256,src:image.src}))")
                if len(displayed)!=1 or displayed[0]['sha']!=terminal_reviewed_hash or hashlib.sha256(base64.b64decode(displayed[0]['src'].split(',',1)[1])).hexdigest()!=terminal_reviewed_hash: raise AssertionError('Terminal queue did not display the exact returned reviewed page bytes and hash')
                completed_before_print=terminal_actions_page.evaluate('terminalActions.completed')
                terminal_actions_page.get_by_role('button', name='Print reviewed pages').click()
                try: terminal_actions_page.wait_for_function("document.querySelector('#status').textContent.includes('Physical output is unconfirmed')", timeout=10000)
                except Exception as error: raise AssertionError(f'Terminal Print action failed: api={terminal_actions_page.evaluate("terminalActions.calls")}, errors={terminal_actions_page.evaluate("terminalActions.error")}, page={error}') from error
                terminal_actions_page.wait_for_function(f"terminalActions.pending===0 && terminalActions.completed>{completed_before_print}")
                if terminal_actions_page.evaluate('window.__terminalPrintCalls') != 1: raise AssertionError('Terminal Print did not invoke the actual exporter print callback once')
                terminal_actions_page.wait_for_function("window.__terminalBlobHashes.length===1")
                printed_hashes=terminal_actions_page.evaluate('window.__terminalBlobHashes')
                if printed_hashes != [terminal_reviewed_hash]: raise AssertionError('Terminal Print received different PNG bytes from the exact frozen reviewed page')
                if terminal_actions_page.evaluate("terminalActions.calls.filter(row=>row.path==='/label/paper').length") != 2: raise AssertionError('Terminal Print did not fetch a fresh reviewed paper result')
                if terminal_actions_page.evaluate('terminalActions.writes.length') != 0: raise AssertionError('Terminal paper Print touched physical Pi write state')
                if terminal_actions_page.locator('img[alt^="Reviewed sheet "]').count() != 1: raise AssertionError('Terminal afterprint removed the reviewed sheet')
                completed_before_pdf=terminal_actions_page.evaluate('terminalActions.completed')
                with terminal_actions_page.expect_download(timeout=15000) as terminal_pdf_download:
                    terminal_actions_page.get_by_role('button', name='Download reviewed PDF').click()
                terminal_pdf_path=terminal_pdf_download.value.path()
                if pathlib.Path(terminal_pdf_path).read_bytes()[:4] != b'%PDF': raise AssertionError('Terminal PDF button did not download a real PDF')
                pdf_info=subprocess.run(['/usr/bin/pdfinfo', terminal_pdf_path],check=True,text=True,capture_output=True).stdout
                page_size=re.search(r'^Page size:\s+([0-9.]+) x ([0-9.]+) pts \(letter\)',pdf_info,re.M)
                page_count=re.search(r'^Pages:\s+(\d+)',pdf_info,re.M)
                if not page_size or tuple(map(float,page_size.groups()))!=(612.0,792.0) or not page_count or page_count.group(1)!='1': raise AssertionError(f'Terminal PDF page geometry is not exact Letter: {pdf_info}')
                terminal_pdf_sha=hashlib.sha256(pathlib.Path(terminal_pdf_path).read_bytes()).hexdigest()
                terminal_actions_page.wait_for_function(f"terminalActions.pending===0 && terminalActions.completed>{completed_before_pdf}")
                if terminal_actions_page.evaluate("terminalActions.calls.filter(row=>row.path==='/label/paper').length") != 3: raise AssertionError('Terminal PDF did not fetch a fresh reviewed paper result')
                if terminal_actions_page.evaluate('terminalActions.writes.length') != 0: raise AssertionError('Terminal PDF unexpectedly touched physical Pi write state')
                # Switch identity while the next paper read is pending; stale data must not open the print dialog.
                terminal_actions_page.evaluate('terminalActions.delayPaper=true')
                completion_before_stale=terminal_actions_page.evaluate('terminalActions.completed')
                terminal_actions_page.get_by_role('button', name='Print reviewed pages').click()
                terminal_actions_page.wait_for_function("!!terminalActions.paperResolve")
                print_calls_before=terminal_actions_page.evaluate('window.__terminalPrintCalls')
                terminal_actions_page.evaluate("identityInstance='new-session';identityGeneration++ ;terminalActions.paperResolve()")
                terminal_actions_page.wait_for_function(f"terminalActions.pending===0 && terminalActions.completed>{completion_before_stale}")
                if terminal_actions_page.evaluate('window.__terminalPrintCalls') != print_calls_before: raise AssertionError('Terminal stale delayed paper result opened Print after identity changed')
                stale_hash=hashlib.sha256(stale_sheet_bytes).hexdigest()
                visible_hashes=terminal_actions_page.locator('img[alt^="Reviewed sheet "]').evaluate_all("images=>images.map(image=>image.dataset.sha256)")
                if stale_hash in visible_hashes or visible_hashes != [terminal_reviewed_hash]: raise AssertionError('Terminal stale delayed paper bytes replaced or contaminated the current reviewed sheet')
                # Review again under the new identity, then switch while the real exporter frame is loading.
                terminal_actions_page.evaluate('terminalActions.delayPaper=false')
                completion_before_review=terminal_actions_page.evaluate('terminalActions.completed')
                terminal_actions_page.get_by_role('button', name='Review 1 selected labels').click()
                terminal_actions_page.wait_for_function(f"terminalActions.completed>{completion_before_review} && terminalActions.calls.filter(row=>row.path==='/label/preview').length===2")
                completion_before_export=terminal_actions_page.evaluate('terminalActions.completed')
                with terminal_actions_page.expect_request(lambda request: 'fixture-delay=1' in request.url, timeout=5000):
                    terminal_actions_page.get_by_role('button', name='Print reviewed pages').click()
                terminal_actions_page.evaluate("identityInstance='switched-during-export';identityGeneration++")
                terminal_actions_page.wait_for_function(f"terminalActions.pending===0 && terminalActions.completed>{completion_before_export}", timeout=10000)
                if terminal_actions_page.evaluate('window.__terminalPrintCalls') != print_calls_before: raise AssertionError('Terminal stale delayed exporter opened Print after identity changed')
                if terminal_actions_page.evaluate("terminalActions.calls.some(row=>row.path==='/label/print')"): raise AssertionError('Terminal paper action used the legacy individual Pi print API')
                report['terminal_paper_queue_fixture']={'fresh_paper_for_print_and_pdf':True,'displayed_and_printed_png_sha256':terminal_reviewed_hash,'actual_print_calls':1,'real_pdf_download':True,'pdf_sha256':terminal_pdf_sha,'pdfinfo_letter_geometry':True,'afterprint_unconfirmed_and_pages_retained':True,'stale_delayed_paper_suppressed':True,'stale_delayed_export_suppressed':True,'physical_writes':0}
                terminal_actions_page.close()

                context_page = browser.new_page(viewport={'width': 800, 'height': 480})
                context_page.route('**/*', guard)
                context_page.goto(base + '/terminal-context-host.html')
                context_page.wait_for_function('contextFixture.done===true', timeout=10000)
                if context_page.evaluate('contextFixture.errors.length'):
                    raise AssertionError('Terminal no-badge context fixture failed: '+context_page.evaluate('contextFixture.errors.join("; ")'))
                report['terminal_context_fixture'] = {'badge_absent': True, 'label_editor_disposed': True, 'label_queue_and_late_reads_cleared': True, 'unrelated_return_and_checkout_carts_preserved': True}
                context_page.close()

                pi_page = browser.new_page(viewport={'width': 800, 'height': 480})
                pi_page.route('**/*', guard)
                pi_page.goto(base + '/pi-print-context-host.html')
                pi_page.wait_for_function('piPrintFixture.done===true')
                if pi_page.evaluate('piPrintFixture.error'):
                    raise AssertionError('PiPrint fresh-context fixture failed: '+pi_page.evaluate('piPrintFixture.error'))
                report['pi_print_context_fixture'] = {'initial_null_context_loaded': True, 'collection_switch_reloaded_templates': True, 'late_old_collection_result_discarded': True}
                pi_page.close()

                render_page = browser.new_page(viewport={'width': 800, 'height': 480})
                def render_guard(route):
                    parsed = urlparse(route.request.url)
                    if f'{parsed.scheme}://{parsed.netloc}' != base:
                        report['outbound_requests'].append(route.request.url)
                        route.abort()
                    elif parsed.path.startswith(ASSET_PREFIX):
                        route.continue_()
                    else:
                        report['bad_asset_paths'].append(parsed.path)
                        route.abort()
                render_page.route('**/*', render_guard)
                render_page.goto(base + ASSET_PREFIX + 'render.html')
                render_page.wait_for_function("typeof window.renderLabelDocument === 'function'")
                if not render_page.evaluate("typeof window.printDesignSheetLayout === 'function'"):
                    raise AssertionError('pinned sheet-layout helper import is unavailable')
                csp_frame = render_page.evaluate('''async()=>{const f=document.createElement('iframe');f.srcdoc='<!doctype html><title>nested print frame</title>';document.body.append(f);await new Promise((resolve,reject)=>{f.onload=resolve;setTimeout(()=>reject(Error('same-origin CSP blocked srcdoc print frame')),3000)});const ok=f.contentDocument?.title==='nested print frame';f.remove();return ok}''')
                if not csp_frame: raise AssertionError('same-origin CSP did not permit the pinned library srcdoc frame')
                pdf = render_page.evaluate('''async ({image,sha256})=>{const geometry={page_mm:[215.9,279.4],label_mm:[60,40],margin_mm:10,gap_mm:3,dpi:300,cut_guides:true};const blob=await window.exportReviewedPaper([{image,sha256}],geometry,'pdf');const bytes=new Uint8Array(await blob.arrayBuffer());return {type:blob.type,size:blob.size,magic:new TextDecoder().decode(bytes.slice(0,4)),data:Array.from(bytes)}}''', {'image':sheet_image,'sha256':sheet_hash})
                if pdf['type']!='application/pdf' or pdf['magic']!='%PDF' or pdf['size']<1000: raise AssertionError('frozen reviewed PNG did not create a real PDF')
                pdf_bytes=bytes(pdf['data'])
                pdf_path=output/'reviewed-letter-fixture.pdf'
                try:
                    pdf_path.write_bytes(pdf_bytes)
                    pdf_info=subprocess.check_output(['pdfinfo',str(pdf_path)],text=True,stderr=subprocess.STDOUT)
                except (OSError,subprocess.CalledProcessError) as error:
                    raise AssertionError(f'could not parse the generated reviewed PDF: {error}') from error
                finally: pdf_path.unlink(missing_ok=True)
                page_size=re.search(r'^Page size:\s+([0-9.]+) x ([0-9.]+) pts',pdf_info,re.M)
                page_count=re.search(r'^Pages:\s+(\d+)',pdf_info,re.M)
                if not page_size or tuple(map(float,page_size.groups()))!=(612.0,792.0) or not page_count or page_count.group(1)!='1':
                    raise AssertionError(f'reviewed PDF must contain one Letter page at 612 x 792 points: {pdf_info}')
                stale_export = render_page.evaluate('''async ({image,sha256})=>{try{await window.exportReviewedPaper([{image,sha256}],{page_mm:[215.9,279.4],label_mm:[60,40],dpi:300},'pdf',()=>false);return false}catch(e){return /review changed before export/.test(e.message)}}''', {'image':sheet_image,'sha256':sheet_hash})
                if not stale_export: raise AssertionError('stale review guard allowed a PDF export')
                delayed_decode = render_page.evaluate('''async ({image,sha256})=>{let current=true,prints=0,release;const bitmap=window.createImageBitmap,print=window.print;window.createImageBitmap=()=>new Promise(resolve=>release=resolve);window.print=function(){prints++};const task=window.exportReviewedPaper([{image,sha256}],{page_mm:[215.9,279.4],label_mm:[60,40],dpi:300},'print',()=>current).then(()=>false,e=>/review changed before export/.test(e.message));while(!release)await Promise.resolve();current=false;release({width:2550,height:3300,close(){}});const rejected=await task;window.createImageBitmap=bitmap;window.print=print;return {rejected,prints}}''', {'image':sheet_image,'sha256':sheet_hash})
                if not delayed_decode['rejected'] or delayed_decode['prints']:
                    raise AssertionError(f'context switch during PNG decode reached printing: {delayed_decode}')
                delayed_frame = render_page.evaluate('''async ({image,sha256})=>{let current=true,prints=0;const timer=window.setTimeout.bind(window),print=window.print;window.print=function(){prints++};window.setTimeout=(callback,delay,...args)=>timer(()=>{if(delay===0)current=false;callback(...args)},delay);let rejected=false;try{await window.exportReviewedPaper([{image,sha256}],{page_mm:[215.9,279.4],label_mm:[60,40],dpi:300},'print',()=>current)}catch(e){rejected=/review changed before the print dialog opened/.test(e.message)}window.setTimeout=timer;window.print=print;return {rejected,prints}}''', {'image':sheet_image,'sha256':sheet_hash})
                if not delayed_frame['rejected'] or delayed_frame['prints']:
                    raise AssertionError(f'context switch during print frame readiness reached print: {delayed_frame}')
                sheet = render_page.evaluate("() => window.printDesignSheetLayout(60,40,{widthMm:215.9,heightMm:279.4})")
                if (sheet['columns'], sheet['rowsPerSheet']) != (3, 6):
                    raise AssertionError(f"upstream sheet helper returned unexpected default Letter capacity: {sheet['columns']} x {sheet['rowsPerSheet']}")
                edge_layouts = render_page.evaluate("""() => {const page={widthMm:215.9,heightMm:279.4},opts={marginMm:10,gapMm:0,orientation:'portrait'};const single=window.printDesignSheetLayout(190,240,page,opts);const nonfit=window.printDesignSheetLayout(200,260,page,opts);let invalid=false;try{window.printDesignSheetLayout(60,40,page,{...opts,marginMm:NaN})}catch{invalid=true}return {single:{columns:single.columns,rows:single.rowsPerSheet,perSheet:single.perSheet},nonfit:{columns:nonfit.columns,rows:nonfit.rowsPerSheet,perSheet:nonfit.perSheet},invalid}}""")
                if edge_layouts['single'] != {'columns':1,'rows':1,'perSheet':1} or edge_layouts['nonfit']['perSheet'] != 0 or not edge_layouts['invalid']:
                    raise AssertionError(f'paper layout edge geometry was accepted incorrectly: {edge_layouts}')
                zero_gap_pixels = render_page.evaluate('''async()=>{const source=document.createElement('canvas');source.width=300;source.height=300;const sourceContext=source.getContext('2d');sourceContext.fillStyle='#123456';sourceContext.fillRect(0,0,source.width,source.height);const review={png_base64:source.toDataURL('image/png').split(',')[1],width:300,height:300};const cases=[];for(const gap_mm of [0,0.01]){const result=await window.composePaperSheet(Array.from({length:8},()=>review),{page_mm:[215.9,279.4],label_mm:[25.4,25.4],margin_mm:10,gap_mm,dpi:300,cut_guides:true});const page=new Image();page.src='data:image/png;base64,'+result.pages[0].png_base64;await page.decode();const canvas=document.createElement('canvas');canvas.width=page.width;canvas.height=page.height;const context=canvas.getContext('2d');context.drawImage(page,0,0);const horizontal=context.getImageData(417,118,2,1).data;const vertical=context.getImageData(118,417,1,2).data;cases.push({gap_mm,columns:result.geometry.columns,rows:result.geometry.rows,horizontal:[...horizontal],vertical:[...vertical]})}const overlapping=document.createElement('canvas');overlapping.width=709;overlapping.height=472;const oc=overlapping.getContext('2d');oc.fillStyle='#123456';oc.fillRect(0,0,709,472);const big={png_base64:overlapping.toDataURL('image/png').split(',')[1],width:709,height:472};let collisionRejected=false;try{await window.composePaperSheet([big,big],{page_mm:[215.9,279.4],label_mm:[60,40],margin_mm:10,gap_mm:0,dpi:300,cut_guides:true})}catch(e){collisionRejected=/overlap after raster rounding/.test(e.message)}return {cases,collisionRejected}}''')
                if any(case['horizontal'] != [18,52,86,255,18,52,86,255] or case['vertical'] != [18,52,86,255,18,52,86,255] for case in zero_gap_pixels['cases']) or not zero_gap_pixels['collisionRejected']:
                    raise AssertionError(f'paper layout changed touching reviewed image pixels or allowed rounded overlap: {zero_gap_pixels}')
                result = render_page.evaluate('''async () => {
                  const doc = {schemaVersion:1,id:'compat',name:'40 by 28',page:{widthMm:40,heightMm:28,orientation:'portrait',marginTopMm:0,marginRightMm:0,marginBottomMm:0,marginLeftMm:0},elements:[{id:'font-check',name:'Font check',xMm:2,yMm:4,widthMm:36,heightMm:18,rotation:0,locked:false,visible:true,type:'text',content:'Offline DejaVu',fontSizePt:6.377952755905512,fontWeight:400,align:'left',color:'#000000',fontFamily:'DejaVu Sans'}],guides:[],variables:{}};
                  return await window.renderLabelDocument(doc,{dpi:203.2,background:'#ffffff'});
                }''')
                if (result['width'], result['height']) != (320, 224):
                    raise AssertionError(f"SUPVAN renderer expected 320x224, got {result['width']}x{result['height']}")
                if not result['png_base64']: raise AssertionError('SUPVAN renderer returned no PNG bytes')
                from PIL import Image
                pixels = Image.open(io.BytesIO(base64.b64decode(result['png_base64'], validate=True))).convert('RGB').getcolors(320 * 224)
                if not pixels or len(pixels) < 2:
                    raise AssertionError('offline text render is blank; bundled DejaVu Sans was not used')
                if not render_page.evaluate('document.fonts.check(\'400 16px "DejaVu Sans"\')'):
                    raise AssertionError('bundled DejaVu Sans did not load into renderer document.fonts')
                report['supvan'] = {'width': result['width'], 'height': result['height'], 'dpi': 203.2}
                report['supvan']['nonwhite_colors'] = len(pixels)
                report['sheet_helper'] = {'columns': sheet['columns'], 'rows': sheet['rowsPerSheet'], 'first_position_mm': sheet['positions'][0], 'last_position_mm': sheet['positions'][-1]}
                report['sheet_geometry_edges'] = edge_layouts
                report['cut_guide_slot_edges'] = zero_gap_pixels
                report['delayed_export_guards'] = {'decode_context_switch_blocks_print': delayed_decode, 'print_frame_context_switch_blocks_window_print': delayed_frame}
                if report['outbound_requests']:
                    raise AssertionError(f"offline runtime made outbound requests: {report['outbound_requests']}")
                if report['bad_asset_paths']:
                    raise AssertionError(f"assets escaped staged prefix {ASSET_PREFIX}: {report['bad_asset_paths']}")
                if report['font_requests']:
                    raise AssertionError(f"font/image requests escaped local asset root: {report['font_requests']}")
                report['result'] = 'passed'
                report_path = output / 'compatibility-report.json'
                report_path.write_text(json.dumps(report, indent=2) + '\n')
                print(f'PASS: offline editor/renderer compatibility ({len(report["viewports"])} viewports); report: {report_path}')
                browser.close()
            finally:
                if browser.is_connected(): browser.close()
    except Exception as error:
        report['result'] = 'failed'
        report['failure'] = str(error)
        (output / 'compatibility-report.json').write_text(json.dumps(report, indent=2) + '\n')
        raise SystemExit(f'FAIL: {error}')
    finally:
        server.shutdown()
        (build / 'compat-host.html').unlink(missing_ok=True)


if __name__ == '__main__': main()
