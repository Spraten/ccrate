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
  self.assertIn('Boolean(window.returnReceiptPreserved&&state.flow===\'return\'&&!authenticated)',adopt)
  self.assertIn('generation:authenticated?gen:null',adopt)
  self.assertNotIn('armExpiry()',re.search(r'async function refresh\(\)(.*?)\n  badgeForm',js,re.S).group(1))
 def test_server_session_response_shape(self):
  source=(ROOT/'deploy/kiosk-server.py').read_text()
  self.assertRegex(source,r"'user':\{'id':member\['id'\],'name':member\['name'\]\} if member else None,'generation':snapshot\[1\],'instance':self\.session\.instance")
  self.assertIn("'kind':'user','user':{'id':user,'name':name},'generation':generation,'instance':self.session.instance",source)
if __name__=='__main__': unittest.main()
