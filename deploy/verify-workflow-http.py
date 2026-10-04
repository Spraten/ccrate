"""Exercise real handlers with temporary databases and native fixture APIs."""
import pathlib,sys,tempfile,threading,json,urllib.request,urllib.error,unittest
from uuid import uuid4
ROOT=pathlib.Path('/home/user/Desktop/inventory-system')
for path in ('ops','kiosk','work/hardware/python'):sys.path.insert(0,str(ROOT/path))
from http.server import ThreadingHTTPServer
GROUP=str(uuid4());USER=str(uuid4());OTHER=str(uuid4());TOOL=str(uuid4())
with tempfile.TemporaryDirectory(prefix='workflow-http-') as tmp:
 target=pathlib.Path(tmp);(target/'work').mkdir();(target/'ops').mkdir();(target/'kiosk').mkdir()
 source=(ROOT/'deploy/kiosk-server.py').read_text()
 source=source.replace("ROOT=pathlib.Path('/home/user/Desktop/inventory-system')",'ROOT=pathlib.Path('+repr(tmp)+')')
 source=source[:source.index("print('Kiosk prototype:")]
 scope={};exec(compile(source,'staged-kiosk-server.py','exec'),scope)
 scope['native_context']=lambda:(GROUP,[{'id':USER,'name':'Alice'},{'id':OTHER,'name':'Bob'}])
 scope['inventory']=lambda locations=False:[{'id':TOOL,'assetId':'000-002','name':'Fixture tool'}]
 badge=scope['badges'].issue(GROUP,USER,[USER,OTHER]);other_badge=scope['badges'].issue(GROUP,OTHER,[USER,OTHER])
 server=ThreadingHTTPServer(('127.0.0.1',0),scope['Handler']);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 base='http://127.0.0.1:'+str(server.server_port)
 def call(path,client,data=None,mode='kiosk'):
  request=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers={'Origin':'http://127.0.0.1:17749','Content-Type':'application/json','X-Homebox-Client':client,'X-Homebox-Client-Mode':mode})
  try:
   with urllib.request.urlopen(request,timeout=8) as r:return r.status,json.load(r)
  except urllib.error.HTTPError as e:
   try:return e.code,json.load(e)
   except ValueError:return e.code,{}
 class HTTPTests(unittest.TestCase):
  def test_separate_browser_sessions_and_scan_verification(self):
   a,b=str(uuid4()),str(uuid4());_,first=call('/scan',a,{'code':badge['code'],'scan_token':str(uuid4())});_,second=call('/scan',b,{'code':other_badge['code'],'scan_token':str(uuid4())})
   self.assertEqual(first['user']['id'],USER);self.assertEqual(second['user']['id'],OTHER);self.assertNotEqual(first['instance'],second['instance'])
   call('/scan',a,{'code':'000-002'});self.assertEqual(scope['sessions'].get(a).scans(first['generation']),{TOOL});self.assertEqual(scope['sessions'].get(b).scans(second['generation']),set())
   call('/session/end',b,{});self.assertEqual(call('/api/session',a)[1]['user']['id'],USER);self.assertIsNone(call('/api/session',b)[1]['user'])
  def test_cancel_before_and_after_scan_response(self):
   client=str(uuid4());token=str(uuid4());call('/scan/cancel',client,{'scan_token':token});self.assertEqual(call('/scan',client,{'code':badge['code'],'scan_token':token})[1]['kind'],'cancelled');self.assertIsNone(call('/api/session',client)[1]['user'])
   token=str(uuid4());call('/scan',client,{'code':badge['code'],'scan_token':token});call('/scan/cancel',client,{'scan_token':token});self.assertIsNone(call('/api/session',client)[1]['user'])
  def test_old_cancel_cannot_end_new_badge(self):
   client=str(uuid4());first=str(uuid4());second=str(uuid4());call('/scan',client,{'code':badge['code'],'scan_token':first});call('/scan',client,{'code':other_badge['code'],'scan_token':second});call('/scan/cancel',client,{'scan_token':first});self.assertEqual(call('/api/session',client)[1]['user']['id'],OTHER)
  def test_status_distinguishes_absent_pending_and_completed(self):
   client=str(uuid4());key=str(uuid4());self.assertEqual(call('/operation/status',client,{'request_key':key})[1]['status'],'not_started')
   op=scope['ledger'].begin(GROUP,USER,'check_out',[TOOL],key);self.assertEqual(call('/operation/status',client,{'request_key':key})[1]['status'],'pending');scope['ledger'].complete(op['id']);self.assertEqual(call('/operation/status',client,{'request_key':key})[1]['status'],'completed')
  def test_editor_cannot_exit_physical_kiosk(self):
   self.assertEqual(call('/exit',str(uuid4()),{},'editor')[0],403)
  def test_invalid_client_or_cancel_token_returns_clear_error(self):
   self.assertEqual(call('/api/session','invalid')[0],400);self.assertEqual(call('/scan/cancel',str(uuid4()),{'scan_token':'invalid'})[0],400)
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(HTTPTests);result=unittest.TextTestRunner(verbosity=2).run(suite)
 server.shutdown();server.server_close();assert result.wasSuccessful()
