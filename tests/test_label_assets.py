import io,json,pathlib,sys,unittest
from email.message import Message
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'ops'))
import desktop_api

ROOT=pathlib.Path(__file__).resolve().parents[1]

class AssetRequest:
    def __init__(self,path):self.path=path;self.command='GET';self.headers=Message();self.status=None;self.headers_out={};self.wfile=io.BytesIO()
    def send_response(self,status):self.status=status
    def send_header(self,key,value):self.headers_out[key]=value
    def end_headers(self):pass
    def reply_json(self,status,result):self.status=status;self.result=result
    def send_error(self,status):self.status=status

class LabelAssetTests(unittest.TestCase):
    def test_only_manifest_assets_are_served_with_safe_cache_and_csp(self):
        manifest=json.loads((ROOT/'work/label-ui-build/manifest.json').read_text())
        chunk=next(name for name in manifest['runtime_assets'] if name.startswith('assets/') and name.endswith('.js'))
        root=ROOT/'work/label-ui-build'
        def request(name):
            handler=AssetRequest('/workshop-api/label-assets/'+name)
            self.assertTrue(desktop_api.handle(handler,{'root':ROOT,'label_asset_root':root}))
            return handler
        html=request('editor.html')
        self.assertEqual(html.status,200);self.assertEqual(html.headers_out['Cache-Control'],'no-cache')
        self.assertIn("object-src 'none'",html.headers_out['Content-Security-Policy'])
        self.assertIn("frame-src 'self'",html.headers_out['Content-Security-Policy'])
        self.assertEqual(request(chunk).headers_out['Cache-Control'],'public, max-age=31536000, immutable')
        self.assertEqual(request('manifest.json').headers_out['Cache-Control'],'no-cache')
        self.assertEqual(request('../../etc/passwd').status,404)

if __name__=='__main__':unittest.main()
