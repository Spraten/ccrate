import pathlib
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class TouchscreenShellTests(unittest.TestCase):
 def test_home_actions_and_session_ownership_contract(self):
  html=(ROOT/'kiosk/touchscreen.html').read_text(); js=(ROOT/'kiosk/touchscreen.js').read_text(); css=(ROOT/'kiosk/touchscreen.css').read_text()
  self.assertIn('Check out',html); self.assertIn('Return',html)
  self.assertIn('X-Homebox-Client',js); self.assertIn('/api/session',js); self.assertIn('/session/end',js)
  self.assertIn('generation',js); self.assertIn('instance',js); self.assertIn('clearDraft()',js)
  self.assertIn('focus-visible',css); self.assertIn('min-height:100px',css)
if __name__=='__main__': unittest.main()
