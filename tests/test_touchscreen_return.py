import pathlib, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class TouchscreenReturnContract(unittest.TestCase):
 def test_return_requires_scan_availability_review_batch_and_status_only_recovery(self):
  s=(ROOT/'kiosk/return-ui.js').read_text()
  for token in ["req('/scan'",'candidate&&candidate.id!==root.id','already in the batch','/return/availability?ids=','Recorded condition:','Return location:','Required note if condition changed','Optional return note','at most 50 items','Confirm return',"req('/operation/status'",'s.uncertain=true','session_generation:c.generation','session_instance:c.instance']:
   self.assertIn(token,s)
  self.assertNotIn('anonymous_return',s)
 def test_html_and_shell_mount_return_flow(self):
  html=(ROOT/'kiosk/touchscreen.html').read_text();shell=(ROOT/'kiosk/touchscreen.js').read_text();server=(ROOT/'deploy/kiosk-server.py').read_text()
  self.assertIn('/return-ui.js',html);self.assertIn("window.beginReturn?.()",shell);self.assertIn("'/return-ui.js':'return-ui.js'",server)
if __name__=='__main__':unittest.main()
