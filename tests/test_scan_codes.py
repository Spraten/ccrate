import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'kiosk'))
from scan_codes import normalize
class ScanTests(unittest.TestCase):
    def test_native_asset_url(self):
        self.assertEqual(normalize('http://homebox.local/a/000-013'),{'kind':'asset','asset_id':'000-013'})
    def test_untrusted_url_is_only_an_identifier(self):
        self.assertEqual(normalize('https://untrusted.invalid/a/000-013')['asset_id'],'000-013')
    def test_script_is_rejected(self):
        self.assertEqual(normalize('javascript:alert(1)')['kind'],'invalid')
    def test_gtin_checksum(self):
        self.assertEqual(normalize('4006381333931')['kind'],'product')
        self.assertEqual(normalize('4006381333932')['kind'],'invalid')
    def test_excessive_input(self):
        self.assertEqual(normalize('x'*2049)['kind'],'invalid')
    def test_unknown_namespace(self):
        self.assertEqual(normalize('LAB:U:unapproved')['kind'],'invalid')
if __name__=='__main__':unittest.main()
