import pathlib
import shutil
import subprocess
import unittest

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

    def test_page_serves_the_flow_script(self):
        server=(ROOT/'deploy/kiosk-server.py').read_text()
        self.assertIn("'/checkout-ui.js': 'checkout-ui.js'",server)

    def test_uncertain_recovery_is_status_only_and_receipt_done_signals_shell(self):
        node=shutil.which('node')
        if not node:self.skipTest('Node is unavailable')
        source=(ROOT/'kiosk/checkout-ui.js').read_text()
        script=r'''global.window={checkoutSession:{generation:3,instance:'session-x'},listeners:{},addEventListener(k,f){this.listeners[k]=f},dispatchEvent(e){this.listeners[e.type]?.(e)}};
global.Event=class{constructor(type){this.type=type}};global.CustomEvent=class extends Event{constructor(type,opts){super(type);this.detail=opts?.detail}};
class Node{constructor(tag){this.tag=tag;this.children=[];this.listeners={};this.textContent='';this.value='';this.disabled=false;this.attrs={};}append(...x){this.children.push(...x)}replaceChildren(){this.children=[]}addEventListener(k,f){this.listeners[k]=f}setAttribute(k,v){this.attrs[k]=v}focus(){}async fire(k){return await this.listeners[k]?.({preventDefault(){}})}}
const host=new Node('section');global.document={querySelector(){return host},createElement(tag){return new Node(tag)}};
let confirms=0,statuses=0,doneEvents=0,doneDetail=null;window.addEventListener('ccrate-flow-done',e=>{doneEvents++;doneDetail=e.detail});
global.fetch=async(path,opts={})=>{if(path==='/checkout/cart')return response({revision:0,items:[],notes:{}});if(path==='/scan')return response({entity:{id:'asset',name:'Asset'}});if(path.startsWith('/checkout/availability'))return response([]);if(path==='/checkout/confirm'){confirms++;throw Error('lost response')}if(path==='/operation/status'){statuses++;return response({status:'completed',id:'receipt-1',count:1})}throw Error('unexpected '+path)};
function response(data){return {ok:true,json:async()=>data}}
function find(n,p){if(p(n))return n;for(const c of n.children){const x=find(c,p);if(x)return x}return null}
'''+source+r'''
;(async()=>{await window.beginCheckout();const scan=find(host,n=>n.attrs['aria-label']==='Scan item barcode');scan.value='PHYSICAL';await find(host,n=>n.tag==='form').fire('submit');if(!find(host,n=>n.textContent==='Remove'))throw Error('scan did not add item; status='+host.children.map(n=>n.textContent).join('|'));await find(host,n=>n.textContent==='Review checkout').fire('click');let confirm=find(host,n=>n.textContent==='Confirm checkout');if(confirm.disabled)throw Error('review did not enable confirmation');await confirm.fire('click');if(confirms!==1)throw Error('confirmation was not one-shot');const check=find(host,n=>n.textContent==='Check saved result');if(!check)throw Error('uncertain result recovery action is missing');await check.fire('click');if(statuses!==1||confirms!==1)throw Error('recovery retried confirmation');if(!find(host,n=>n.textContent==='Checkout complete'))throw Error('completed status did not show receipt');window.checkoutSession={generation:4,instance:'new-session'};window.dispatchEvent(new Event('ccrate-session-change'));await find(host,n=>n.textContent==='Done').fire('click');if(doneEvents!==1||doneDetail?.generation!==3||doneDetail?.instance!=='session-x')throw Error('receipt Done lost original session identity');})().catch(e=>{console.error(e);process.exitCode=1});'''
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
