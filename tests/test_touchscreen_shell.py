import pathlib
import re
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class TouchscreenShellTests(unittest.TestCase):
 def test_home_actions_and_session_ownership_contract(self):
  html=(ROOT/'kiosk/touchscreen.html').read_text(); js=(ROOT/'kiosk/touchscreen.js').read_text(); css=(ROOT/'kiosk/touchscreen.css').read_text()
  self.assertIn('Check out',html); self.assertIn('Return',html)
  self.assertIn('X-Homebox-Client',js); self.assertIn("api('/api/session')",js)
  self.assertIn("api('/session/end'",js); self.assertIn("api('/session/activity'",js)
  self.assertIn("api('/scan'",js); self.assertIn('result.kind===\'user\'',js)
  self.assertIn('result.user.name',js); self.assertIn('expected_generation',js); self.assertIn('expected_instance',js)
  self.assertRegex(js,r'setTimeout\(.*?120000\)')
  self.assertIn('generation',js); self.assertIn('instance',js); self.assertIn('clearDraft()',js)
  self.assertIn('badge-form',html); self.assertIn('focus-visible',css); self.assertIn('min-height:100px',css)
 def test_newly_adopted_session_arms_expiry_once_without_poll_activity(self):
  js=(ROOT/'kiosk/touchscreen.js').read_text()
  adopt=re.search(r'function adopt\(session\)\{(.*?)\n  function armExpiry',js,re.S).group(1)
  self.assertIn('armExpiry()',adopt)
  self.assertIn('window.returnReceiptPreserved&&state.flow===\'return\'',adopt)
  self.assertIn('window.checkoutReceiptPreserved&&state.flow===\'checkout\'',adopt)
  self.assertIn('generation:authenticated?gen:null',adopt)
  self.assertNotIn('armExpiry()',re.search(r'async function refresh\(\)(.*?)\n  badgeForm',js,re.S).group(1))
 def test_server_session_response_shape(self):
  source=(ROOT/'deploy/kiosk-server.py').read_text()
  self.assertRegex(source,r"'user':\{'id':member\['id'\],'name':member\['name'\]\} if member else None,'generation':snapshot\[1\],'instance':self\.session\.instance")
  self.assertIn("'kind':'user','user':{'id':user,'name':name},'generation':generation,'instance':self.session.instance",source)
 def test_expiry_ends_auth_but_preserves_completed_receipts_until_done(self):
  import shutil,subprocess
  node=shutil.which('node')
  if not node:self.skipTest('Node unavailable')
  source=(ROOT/'kiosk/touchscreen.js').read_text()
  fixture=r'''const vm=require('vm'),source=process.env.SHELL_SOURCE;
class N{constructor(){this.listeners={};this.hidden=false;this.textContent='';this.value=''}addEventListener(k,f){this.listeners[k]=f}reset(){}async fire(k){return await this.listeners[k]?.({preventDefault(){}})}click(){this.fire('click')}}
async function scenario(flow,marker){let timers=[];global.localStorage={getItem(){return 'client'},setItem(){}};global.crypto={randomUUID(){return 'client'}};global.setTimeout=(fn,ms)=>{timers.push({fn,ms});return timers.length};global.clearTimeout=()=>{};global.setInterval=()=>0;let current={user:{id:'member',name:'Member'},generation:17,instance:'session-A'};let win={listeners:{},addEventListener(k,f){(this.listeners[k]??=[]).push(f)},dispatchEvent(e){for(const f of this.listeners[e.type]||[])f(e)}};global.window=win;const names=['#badge-form','#badge-code','#home','#flow','#flow-title','#flow-message','#member','#done','#checkout-ui','#return-ui'];const nodes=Object.fromEntries(names.map(k=>[k,new N()]));const flows=['checkout','return'].map(x=>Object.assign(new N(),{dataset:{flow:x}}));global.document={querySelector:k=>nodes[k],querySelectorAll:()=>flows,addEventListener(){}};global.Event=class{constructor(type){this.type=type}};global.fetch=async path=>({ok:true,json:async()=>path==='/api/session'?current:{ended:true}});vm.runInThisContext(source);for(let i=0;i<5;i++)await Promise.resolve();await flows.find(x=>x.dataset.flow===flow).fire('click');win[marker]=true;const timer=timers.find(x=>x.ms===120000);if(!timer)throw Error('session expiry was not armed');timer.fn();for(let i=0;i<8;i++)await Promise.resolve();if(!nodes['#home'].hidden||nodes['#flow'].hidden)throw Error(flow+' expiry cleared the completed receipt screen');if(win.checkoutSession?.generation!==17||win.checkoutSession.authenticated!==false)throw Error(flow+' expiry did not retain receipt identity while ending auth');}
;(async()=>{await scenario('checkout','checkoutReceiptPreserved');await scenario('return','returnReceiptPreserved')})().catch(e=>{console.error(e);process.exitCode=1});'''
  env=__import__('os').environ.copy();env['SHELL_SOURCE']=source
  result=subprocess.run([node,'-e',fixture],cwd=ROOT,capture_output=True,text=True,env=env)
  self.assertEqual(result.returncode,0,result.stderr)
if __name__=='__main__': unittest.main()
