import pathlib,sys,tempfile,unittest
from uuid import uuid4
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'ops'))
from workshop import Workshop,layout,move_location
from ledger import Conflict
from setup_native import prepare_location

class Client:
    def __init__(self):
        self.a=str(uuid4());self.b=str(uuid4());self.nodes={self.a:{'id':self.a,'name':'Rack XYZ','entityType':{'id':str(uuid4()),'isLocation':True},'parent':None,'updatedAt':'1','fields':[],'tags':[],'description':'Keep this'},self.b:{'id':self.b,'name':'Shelf 2','entityType':{'id':str(uuid4()),'isLocation':True},'parent':{'id':self.a},'updatedAt':'1','fields':[],'tags':[]}}
        self.writes=[]
    def entity(self,key):return self.nodes[key]
    def entities(self,locations=False):return list(self.nodes.values()) if locations else []
    def call(self,path,method='GET',data=None):
        if path=='/api/v1/entity-types':return [{'id':str(uuid4()),'isLocation':True}]
        self.writes.append(data);key=path.rsplit('/',1)[1];self.nodes[key]={**self.nodes[key],**data,'parent':{'id':data['parentId']} if data['parentId'] else None,'updatedAt':'2'}

class WorkshopTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.store=Workshop(pathlib.Path(self.tmp.name)/'workshop.db');self.client=Client();self.group=str(uuid4())
    def tearDown(self):self.tmp.cleanup()
    def plan(self):return {'name':'Workshop','width':13.5,'height':21,'objects':[{'id':str(uuid4()),'name':'Rack XYZ','kind':'Rack','x':1,'y':1,'width':3,'height':1,'rotation':0,'location_id':self.client.a}]}
    def test_layout_and_storage_separate(self):
        saved=self.store.save(self.client,self.group,{'revision':0,'layout':self.plan()});self.assertEqual(saved['revision'],1);self.assertFalse(self.client.writes);self.assertIsNone(self.store.get(str(uuid4()))['layout'])
    def test_conflicting_save_does_not_overwrite(self):
        plan=self.plan();self.store.save(self.client,self.group,{'revision':0,'layout':plan})
        with self.assertRaises(Conflict):self.store.save(self.client,self.group,{'revision':0,'layout':{**plan,'name':'Old browser'}})
        self.assertEqual(self.store.get(self.group)['layout']['name'],'Workshop')
    def test_invalid_bounds_nan_duplicate(self):
        for change in ({'width':float('nan')},{'x':-1},{'height':50},{'rotation':35}):
            p=self.plan();p['objects'][0].update(change)
            with self.assertRaises(ValueError):layout(p)
        p=self.plan();p['objects'].append(p['objects'][0].copy())
        with self.assertRaises(ValueError):layout(p)
    def test_no_link_to_missing_location(self):
        p=self.plan();p['objects'][0]['location_id']=str(uuid4())
        with self.assertRaises(ValueError):self.store.save(self.client,self.group,{'revision':0,'layout':p})
    def test_restart_persistence(self):
        self.store.save(self.client,self.group,{'revision':0,'layout':self.plan()});other=Workshop(self.store.path);self.assertEqual(other.get(self.group)['revision'],1)
    def test_cycle_and_stale_parent_move_blocked(self):
        with self.assertRaises(ValueError):move_location(self.client,{'id':self.client.a,'parent_id':self.client.b,'updated_at':'1'})
        with self.assertRaises(Conflict):move_location(self.client,{'id':self.client.b,'parent_id':'','updated_at':'old'})
        self.assertFalse(self.client.writes)
    def test_move_preserves_metadata_and_retry_reads(self):
        self.client.nodes[self.client.b]['description']='Keep this';move_location(self.client,{'id':self.client.b,'parent_id':'','updated_at':'1'});self.assertEqual(self.client.writes[0]['description'],'Keep this');move_location(self.client,{'id':self.client.b,'parent_id':'','updated_at':'1'});self.assertEqual(len(self.client.writes),1)
    def test_native_storage_kind_and_code(self):
        plan=prepare_location(self.client,{'name':'XYZ-2-B','parent_id':self.client.b,'storage_kind':'Bin','storage_code':'B'});self.assertEqual(plan['create']['parentId'],self.client.b);self.assertEqual(plan['fields'][0]['textValue'],'Bin');self.assertEqual(plan['fields'][1]['textValue'],'B')
    def test_duplicate_storage_code_within_parent(self):
        self.client.nodes[self.client.b]['fields']=[{'name':'Storage code','type':'text','textValue':'2'}]
        with self.assertRaises(Conflict):prepare_location(self.client,{'name':'Another shelf','parent_id':self.client.a,'storage_kind':'Shelf','storage_code':'2'})

if __name__=='__main__':unittest.main()
