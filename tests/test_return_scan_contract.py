import ast,pathlib,sys,unittest
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit,parse_qs
from uuid import UUID
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ops'))
class ReturnScanContract(unittest.TestCase):
 def test_anonymous_return_remains_backend_only(self):
  source=(ROOT/'deploy/kiosk-server.py').read_text();ui=(ROOT/'kiosk/return-ui.js').read_text()
  self.assertIn("data.get('anonymous_return') is True",source)
  self.assertNotIn('anonymous_return',ui)
 def test_actual_handler_session_get_reports_anonymous_context(self):
  from sessions import Session
  tree=ast.parse((ROOT/'deploy/kiosk-server.py').read_text())
  handler=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Handler')
  dummy=object()
  ns={'BaseHTTPRequestHandler':BaseHTTPRequestHandler,'property':property,'urlsplit':urlsplit,'parse_qs':parse_qs,'UUID':UUID,
      'ROOT':ROOT,'desktop_handle':lambda *a:False,'sessions':None,'lock':None,'ledger':dummy,'Homebox':None,'Conflict':ValueError,
      'checkout_cart':dummy,'shelf_checks':dummy,'badges':dummy,'native_jobs':dummy,'imports':dummy,'workshop':dummy,
      'web_item_actions':dummy,'label_layouts':dummy,'LABEL_ASSET_ROOT':ROOT}
  exec(compile(ast.Module(body=[handler],type_ignores=[]),'<Handler>','exec'),ns)
  session=Session();generation=session.begin_anonymous_return()
  class Sessions:
   def get(self,client):return session
  ns['sessions']=Sessions()
  class Fixture(ns['Handler']):
   @property
   def session(self):return session
  instance=Fixture.__new__(Fixture);instance.path='/api/session';instance.headers={}
  result=[];instance.reply_json=lambda code,data:result.append((code,data))
  instance.do_GET()
  self.assertEqual(result[0],(200,{'user':None,'generation':generation,'instance':session.instance,'return_only':True}))
 def test_search_candidate_requires_separate_physical_scan(self):
  ui=(ROOT/'kiosk/return-ui.js').read_text()
  self.assertIn("request('/scan'",ui);self.assertIn('candidate.id !== root.id',ui)
if __name__=='__main__':unittest.main()
