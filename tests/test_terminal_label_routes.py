"""Run Terminal label dispatch against disposable roots and mocked Homebox only."""
import io,json,os,pathlib,sys,tempfile,types,unittest
from email.message import Message
from unittest.mock import Mock,patch

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'ops'),str(ROOT/'kiosk'),'/home/user/Desktop/inventory-system/work/hardware/python']


def load_server(root):
    (root/'work').mkdir(parents=True)
    source=(ROOT/'deploy/kiosk-server.py').read_text()
    source=source.split('if _fixture_context:\n    _fixture_root,_fixture_ready=',1)[0]
    namespace={'__name__':'terminal_label_fixture','__file__':str(ROOT/'deploy/kiosk-server.py')}
    asset_root=root/'label-assets';asset_root.mkdir()
    with patch.dict(os.environ,{'WORKSHOP_ROOT':str(root),'WORKSHOP_LABEL_ASSET_ROOT':str(asset_root)}):
        os.environ.pop('WORKSHOP_CODE_ROOT',None)
        exec(compile(source,str(ROOT/'deploy/kiosk-server.py'),'exec'),namespace)
    assert namespace['ROOT']==root.resolve()
    assert namespace['LABEL_ASSET_ROOT']==asset_root.resolve()
    return namespace


class Request:
    def __init__(self,path,data,session):
        self.path=path;self.command='POST';self.session_fixture=session;self.headers=Message()
        body=json.dumps(data).encode()
        for key,value in {'Origin':'http://terminal.local:17749','Host':'terminal.local:17749','Content-Length':str(len(body)),'Content-Type':'application/json','X-Homebox-Client':'legacy'}.items():self.headers[key]=value
        self.rfile=io.BytesIO(body);self.response=None
    @property
    def session(self):return self.session_fixture
    def reply_json(self,status,result):self.response=(status,result)
    def send_error(self,status):self.response=(status,{})


class TerminalLabelRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.server=load_server(pathlib.Path(self.tmp.name)/'runtime')
        # Exercise the legacy adapter explicitly; production access is closed by default.
        self.server['OPEN_ADMIN']=True
        self.ns=self.server;self.group='11111111-1111-4111-8111-111111111111';self.manager='22222222-2222-4222-8222-222222222222';self.service='33333333-3333-4333-8333-333333333333'
        self.client_calls=[]
        class Client:
            def __init__(client,*args,**kwargs):client.tenant=None;client.timeout=kwargs.get('timeout',8)
            def call(client,path,*args):
                owner=self;owner.client_calls.append((path,client.tenant))
                if path=='/api/v1/users/self':return {'item':{'id':owner.service,'defaultGroupId':owner.group}}
                if path=='/api/v1/groups':return {'item':{'id':owner.group}}
                if path=='/api/v1/groups/members':return [{'id':owner.service},{'id':owner.manager}]
                raise AssertionError(path)
            def entities(client,locations=False):
                owner=self;owner.client_calls.append(('/api/v1/entities',client.tenant))
                return [{'id':'active-equipment','name':'Active','assetId':'A-1'}, {'id':'archived-equipment','name':'Archived','archived':True}, {'id':'location','name':'Shelf','isLocation':True}]
        self.ns['Homebox']=Client
        self.session=self.ns['sessions'].get('legacy');self.session.start(self.manager)
        self.ns['desktop_handle']=lambda *args:False
        self.ns['label_layouts']=Mock()
        self.ns['imports']=Mock();self.ns['imports'].label.return_value={'status':'completed'}
        self.ns['print_label']=Mock(return_value={'status':'completed'})
    def tearDown(self):self.tmp.cleanup()
    def dispatch(self,path,data):
        req=Request(path,data,self.session);self.ns['Handler'].do_POST(req);return req
    def dispatch_get(self,path):
        req=Request(path,{},self.session);self.ns['Handler'].do_GET(req);return req
    def test_import_confirmation_actor_and_tenant_are_current_operator(self):
        req=self.dispatch('/imports/label',{'id':'batch','index':0,'review_id':'review'})
        self.assertEqual(req.response[0],200)
        args=self.ns['imports'].label.call_args
        self.assertEqual(args.kwargs['actor'],self.manager)
        self.assertIs(args.kwargs['layouts'],self.ns['label_layouts'])
        self.assertEqual(args.args[2],self.group)
        self.assertTrue(all(tenant==self.group for path,tenant in self.client_calls if path=='/api/v1/groups'))


    def test_reviewed_print_route_passes_operator_and_review_id_without_client_raster(self):
        item='44444444-4444-4444-8444-444444444444';review='55555555-5555-4555-8555-555555555555';key='66666666-6666-4666-8666-666666666666'
        req=self.dispatch('/label/print',{'entity_id':item,'review_id':review,'request_key':key,'png':'attacker-data'})
        self.assertEqual(req.response[0],200)
        args=self.ns['print_label'].call_args
        self.assertEqual(args.args[2:6],(self.group,self.manager,key,item))
        self.assertEqual(args.kwargs['review_id'],review)
        self.assertTrue(args.kwargs['valid_context']())
        self.assertEqual(self.ns['label_layouts'].method_calls,[])
    def test_print_recovery_dispatch_injects_label_service(self):
        job=self.ns['native_jobs'].prepare(self.group,self.manager,'print_label','77777777-7777-4777-8777-777777777777',{'entity_id':'44444444-4444-4444-8444-444444444444','review_id':'55555555-5555-4555-8555-555555555555'})
        handler=Mock(return_value={'id':job['id'],'status':'cancelled'});self.ns['recover_print']=handler
        req=self.dispatch('/recovery/resolve',{'id':job['id'],'native_job':True,'outcome':'cancel'})
        self.assertEqual(req.response[0],200)
        self.assertIs(handler.call_args.kwargs['layouts'],self.ns['label_layouts'])
    def test_label_picker_reads_only_active_tenant_equipment(self):
        req=self.dispatch_get('/label/equipment')
        self.assertEqual(req.response[0],200)
        self.assertEqual([row['id'] for row in req.response[1]],['active-equipment'])
        self.assertIn(('/api/v1/entities',self.group),self.client_calls)


class TerminalLabelHostContractTests(unittest.TestCase):
    def test_terminal_label_designer_allows_template_save_but_not_physical_print(self):
        source=(ROOT/'kiosk/index.html').read_text(encoding='utf-8')
        self.assertIn("write:(action,data)=>{if(action==='labels/templates/save')return api('/label/templates/save',data);throw Error('Use the reviewed item queue to confirm physical printing.')}",source)
        self.assertIn("context:()=>({host:'terminal',generation:editorGeneration,instance:editorInstance})",source)


if __name__=='__main__':unittest.main()
