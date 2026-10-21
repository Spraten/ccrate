import pathlib
import shutil
import subprocess
import unittest
import ast,io,json,sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit,parse_qs
from uuid import UUID,uuid4

ROOT=pathlib.Path(__file__).resolve().parents[1]

class TouchscreenCheckoutTests(unittest.TestCase):
    def test_checkout_requires_scan_and_review_and_has_manual_recovery(self):
        source=(ROOT/'kiosk/checkout-ui.js').read_text()
        self.assertIn("request('/scan'",source)
        self.assertIn('Physical scan verified',source)
        self.assertIn('This item is already in the batch',source)
        self.assertIn('at most 50 distinct items',source)
        self.assertIn("request('/checkout/availability?ids='",source)
        self.assertIn('Optional note for this item',source)
        self.assertIn('Confirm checkout',source)
        self.assertIn("request('/operation/status'",source)
        self.assertIn("state.uncertain=true",source)
        self.assertIn('session_generation:saved.generation',source)
        self.assertIn('session_instance:saved.instance',source)
        self.assertIn("'X-Homebox-Client':window.touchscreenClientId",source)
        self.assertIn("request('/api/kit?id='",source)
        self.assertIn('state.items=[...retainedItems,item];state.reviewed=false',source)
        self.assertIn('const kitIds=new Set(entities.map(x=>x.id))',source)

    def test_checkout_handler_forwards_edited_notes_to_receipt_operation(self):
        tree=ast.parse((ROOT/'deploy/kiosk-server.py').read_text())
        handler=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='Handler')
        actor,generation,instance=str(uuid4()),9,'session-x';captured={}
        class Session:
            def snapshot(self):return actor,generation
            def scans(self,gen):return {'scan-proof'}
            def __init__(self):self.instance=instance
        class Lock:
            def __enter__(self):return self
            def __exit__(self,*args):return False
        class Client:
            tenant=None
            def call(self,path):return {'item':{'defaultGroupId':str(uuid4())}}
        def confirm(*args,**kwargs):captured.update(kwargs);captured['args']=args;return {'id':'receipt','status':'completed'}
        names=('shelf_checks badges native_jobs imports workshop sessions web_item_actions label_layouts LABEL_ASSET_ROOT')
        namespace={'BaseHTTPRequestHandler':BaseHTTPRequestHandler,'desktop_handle':lambda *args:False,'same_origin':lambda *args:True,
            'json':json,'ROOT':'unused','lock':Lock(),'ledger':object(),'checkout_cart':object(),'Homebox':lambda root:Client(),
            'checkout_cart_context':lambda *args:{},'confirm_checkout':confirm,'NativeUUID':UUID,'Conflict':Exception,'invalidate_stock':lambda:None,
            'urlsplit':urlsplit,'parse_qs':parse_qs}
        namespace.update({name:None for name in names.split()})
        exec(compile(ast.Module(body=[handler],type_ignores=[]),'<Handler>','exec'),namespace)
        class FixtureHandler(namespace['Handler']):
            @property
            def session(self):return Session()
        h=FixtureHandler.__new__(FixtureHandler);h.path='/checkout/confirm';h.headers={'Origin':'http://test','Host':'test','Content-Length':'2'};h.rfile=io.BytesIO(b'{}')
        payload={'assets':[str(uuid4())],'request_key':str(uuid4()),'notes':{'item-id':'Edited checkout note'},'session_generation':generation,'session_instance':instance}
        body=json.dumps(payload).encode();h.headers['Content-Length']=str(len(body));h.rfile=io.BytesIO(body);h.reply_json=lambda code,data:None
        h.do_POST()
        self.assertEqual(captured.get('notes'),payload['notes'])

    def test_page_serves_the_flow_script(self):
        server=(ROOT/'deploy/kiosk-server.py').read_text()
        self.assertIn("'/checkout-ui.js': 'checkout-ui.js'",server)

    def test_uncertain_recovery_is_status_only_and_receipt_done_signals_shell(self):
        node=shutil.which('node')
        if not node:self.skipTest('Node is unavailable')
        source=(ROOT/'kiosk/checkout-ui.js').read_text()
        script=r'''global.window={checkoutSession:{generation:3,instance:'session-x'},touchscreenClientId:'client-uuid',listeners:{},addEventListener(k,f){this.listeners[k]=f},dispatchEvent(e){this.listeners[e.type]?.(e)}};
global.Event=class{constructor(type){this.type=type}};global.CustomEvent=class extends Event{constructor(type,opts){super(type);this.detail=opts?.detail}};
global.localStorage={getItem(){return 'client-uuid'}};
class Node{constructor(tag){this.tag=tag;this.children=[];this.listeners={};this.textContent='';this.value='';this.disabled=false;this.attrs={};}append(...x){this.children.push(...x)}replaceChildren(){this.children=[]}addEventListener(k,f){this.listeners[k]=f}setAttribute(k,v){this.attrs[k]=v}focus(){}async fire(k){return await this.listeners[k]?.({preventDefault(){}})}}
const host=new Node('section');global.document={querySelector(){return host},createElement(tag){return new Node(tag)}};
let confirms=0,statuses=0,doneEvents=0,doneDetail=null,calls=[],payload=null,verified=[];window.addEventListener('ccrate-flow-done',e=>{doneEvents++;doneDetail=e.detail});
global.fetch=async(path,opts={})=>{calls.push([path,opts]);if(path==='/checkout/cart')return response({revision:0,items:[],notes:{}});if(path==='/scan'){const code=JSON.parse(opts.body).code;const id=code==='KIT'?'kit-root':code==='PART'?'kit-part':'asset-two';verified.push(id);return response({entity:{id,name:id==='kit-root'?'Native Kit':id==='kit-part'?'Native component':'Asset Two',...(id==='kit-root'?{customFields:[{name:'Equipment kit manifest',value:'{"version":1}'}]}:{})}})}if(path.startsWith('/api/kit'))return response(path.includes('kit-root')?{kit:true,entities:[{id:'kit-root',name:'Native Kit'},{id:'kit-part',name:'Native component'}],versions:{'kit-root':'v1'},verified:[...new Set(verified)]}:{kit:false});if(path.startsWith('/checkout/availability'))return response([]);if(path==='/checkout/confirm'){confirms++;payload=JSON.parse(opts.body);throw Error('lost response')}if(path==='/operation/status'){statuses++;return response({status:'completed',id:'receipt-1',count:1})}throw Error('unexpected '+path)};
function response(data){return {ok:true,json:async()=>data}}
function find(n,p){if(p(n))return n;for(const c of n.children){const x=find(c,p);if(x)return x}return null}
        '''+source+r'''
;(async()=>{await window.beginCheckout();const all=n=>[n,...n.children.flatMap(all)];async function add(code){const scan=find(host,n=>n.attrs['aria-label']==='Scan item barcode');scan.value=code;await find(host,n=>n.tag==='form').fire('submit');}await add('KIT');if(!find(host,n=>n.textContent.includes('Scan kit component'))||all(host).some(n=>n.tag==='article'))throw Error('incomplete native kit did not request component scans');await add('PART');await add('KIT');if(all(host).filter(n=>n.tag==='article').length!==1)throw Error('scanned kit component was not folded into the kit root');const note=find(host,n=>n.placeholder==='Optional note for this item');note.value='Edited checkout note';await note.fire('input');await find(host,n=>n.textContent==='Review checkout').fire('click');let confirm=find(host,n=>n.textContent==='Confirm checkout');if(confirm.disabled)throw Error('review did not enable confirmation');await add('SECOND');confirm=find(host,n=>n.textContent==='Confirm checkout');if(!confirm.disabled)throw Error('adding an item did not invalidate checkout review');if(all(host).filter(n=>n.tag==='article').length!==2)throw Error('kit merge retained duplicate component rows');await find(host,n=>n.textContent==='Review checkout').fire('click');confirm=find(host,n=>n.textContent==='Confirm checkout');if(confirm.disabled)throw Error('reviewing the changed batch did not enable confirmation');await confirm.fire('click');if(confirms!==1||new Set(payload.assets).size!==payload.assets.length||payload.assets.length!==3||payload.notes['kit-root']!=='Edited checkout note')throw Error('kit expansion or edited note was not sent');const check=find(host,n=>n.textContent==='Check saved result');if(!check)throw Error('uncertain result recovery action is missing');await check.fire('click');if(statuses!==1||confirms!==1)throw Error('recovery retried confirmation');if(!find(host,n=>n.textContent==='Checkout complete'))throw Error('completed status did not show receipt');for(const [path,opts] of calls)if(opts.headers?.['X-Homebox-Client']!=='client-uuid')throw Error('missing stable client header for '+path);window.checkoutSession={generation:4,instance:'new-session'};window.dispatchEvent(new Event('ccrate-session-change'));if(find(host,n=>n.textContent==='Checkout complete')||find(host,n=>n.textContent==='Done'))throw Error('old checkout receipt leaked into the next session');})().catch(e=>{console.error(e);process.exitCode=1});'''
        result=subprocess.run([node,'-e',script],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_receipt_done_ends_captured_session_and_returns_home(self):
        node=shutil.which('node')
        if not node:self.skipTest('Node is unavailable')
        source=(ROOT/'kiosk/touchscreen.js').read_text()
        script=r'''global.localStorage={getItem(){return 'stable-client'},setItem(){}};global.crypto={randomUUID(){return 'stable-client'}};global.setInterval=()=>0;global.setTimeout=()=>1;global.clearTimeout=()=>{};
global.Event=class{constructor(type){this.type=type}};
class Node{constructor(){this.listeners={};this.hidden=false;this.textContent='';this.value=''}addEventListener(k,f){this.listeners[k]=f}reset(){}click(){this.fire('click')}async fire(k){return await this.listeners[k]?.({preventDefault(){}})}}
global.window={listeners:{},addEventListener(k,f){this.listeners[k]=f},dispatchEvent(e){this.listeners[e.type]?.(e)}};let current={user:{id:'member',name:'Member'},generation:8,instance:'captured-instance'};const docListeners={};const nodes=Object.fromEntries(['#badge-form','#badge-code','#home','#flow','#flow-title','#flow-message','#member','#done','#checkout-ui'].map(k=>[k,new Node()]));global.document={querySelector:k=>nodes[k],querySelectorAll:()=>[],addEventListener(k,f){docListeners[k]=f}};let endPayload=null,finishEnd=null;
global.fetch=async(path,opts={})=>{if(path==='/session/end'){endPayload=JSON.parse(opts.body);return new Promise(resolve=>{finishEnd=()=>resolve({ok:true,json:async()=>({ended:true})})})}return {ok:true,json:async()=>path==='/api/session'?current:{}}};
'''+source+r'''
;(async()=>{await Promise.resolve();await Promise.resolve();window.dispatchEvent(Object.assign(new Event('ccrate-flow-done'),{detail:{generation:8,instance:'captured-instance'}}));await new Promise(r=>setTimeout(r,0));if(endPayload?.expected_generation!==8)throw Error('Done did not send captured session identity');current={user:{id:'new',name:'New member'},generation:9,instance:'new-instance'};await docListeners.visibilitychange();await new Promise(r=>setTimeout(r,0));finishEnd();await new Promise(r=>setTimeout(r,0));if(nodes['#home'].hidden||!nodes['#flow'].hidden)throw Error('Done did not return the shell to home');if(nodes['#member'].textContent!=='New member')throw Error('pending Done cleanup cleared newer member identity');if(nodes['#done'].hidden!==true)throw Error('Done control remained visible');})().catch(e=>{console.error(e);process.exitCode=1});'''
        result=subprocess.run([node,'-e',script],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__': unittest.main()
