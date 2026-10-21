import pathlib,sys,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ops'))
class ReturnScanContract(unittest.TestCase):
 def test_anonymous_return_remains_backend_only(self):
  source=(ROOT/'deploy/kiosk-server.py').read_text();ui=(ROOT/'kiosk/return-ui.js').read_text()
  self.assertIn("data.get('anonymous_return') is True",source)
  self.assertNotIn('anonymous_return',ui)
 def test_search_candidate_requires_separate_physical_scan(self):
  ui=(ROOT/'kiosk/return-ui.js').read_text()
  self.assertIn("req('/scan'",ui);self.assertIn('candidate&&candidate.id!==root.id',ui)
if __name__=='__main__':unittest.main()
