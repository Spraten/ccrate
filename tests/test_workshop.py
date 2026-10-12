import pathlib,sys,tempfile,unittest
from uuid import uuid4
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'ops'))
from workshop import Workshop,layout,move_location,submit_shelf_order,recover_shelf_order
from ledger import Conflict,Ledger
from native_jobs import NativeJobs
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

class ShelfOrderClient(Client):
    def __init__(self):
        super().__init__()
        self.nodes[self.a].update(entityType={'id':self.nodes[self.a]['entityType']['id'],'isLocation':True},fields=[{'name':'Storage kind','type':'text','textValue':'Rack'}],updatedAt='rack-v1',attachments=[],tagIds=[])
        self.nodes[self.b].update(entityType={'id':self.nodes[self.b]['entityType']['id'],'isLocation':True},fields=[{'name':'Storage kind','type':'text','textValue':'Shelf'}],updatedAt='shelf-v1')
        self.fail_after_put=False
        self.fail_before_put=False
    def entity(self,key):return dict(self.nodes[key])
    def entities(self,locations=False):return [dict(node) for node in self.nodes.values()]
    def call(self,path,method='GET',data=None):
        if method=='PUT':
            if self.fail_before_put:
                self.fail_before_put=False
                raise OSError('native update was not applied')
            super().call(path,method,data)
            if self.fail_after_put:
                self.fail_after_put=False
                raise OSError('response lost after native update')

class WorkshopTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.store=Workshop(pathlib.Path(self.tmp.name)/'workshop.db');self.client=Client();self.group=str(uuid4());self.actor=str(uuid4());self.key=str(uuid4());self.jobs=NativeJobs(Ledger(pathlib.Path(self.tmp.name)/'ledger.db'))
    def tearDown(self):self.tmp.cleanup()
    def plan(self):return {'name':'Workshop','width':13.5,'height':21,'objects':[{'id':str(uuid4()),'name':'Rack XYZ','kind':'Rack','x':1,'y':1,'width':3,'height':1,'rotation':0,'location_id':self.client.a}]}
    def request(self,revision,name='Workshop',key=None):return {'schema_version':2,'revision':revision,'request_key':key or str(uuid4()),'document':{'version':2,'rooms':[{'id':str(uuid4()),'location_id':None,'name':name,'width':13.5,'height':21,'unit':'ft','approximate':False,'objects':[]}]}}
    def test_layout_and_storage_separate(self):
        saved=self.store.save(self.client,self.group,self.request(0),actor_id=self.actor);self.assertEqual(saved['revision'],1);self.assertFalse(self.client.writes);self.assertIsNone(self.store.get(str(uuid4()))['layout'])
    def test_conflicting_save_does_not_overwrite(self):
        self.store.save(self.client,self.group,self.request(0,key=self.key),actor_id=self.actor)
        with self.assertRaises(Conflict):self.store.save(self.client,self.group,self.request(0,'Old browser'),actor_id=self.actor)
        self.assertEqual(self.store.get(self.group)['document']['rooms'][0]['name'],'Workshop')
    def test_invalid_bounds_nan_duplicate(self):
        for change in ({'width':float('nan')},{'x':-1},{'height':50},{'rotation':35}):
            p=self.plan();p['objects'][0].update(change)
            with self.assertRaises(ValueError):layout(p)
        p=self.plan();p['objects'].append(p['objects'][0].copy())
        with self.assertRaises(ValueError):layout(p)
    def test_no_link_to_missing_location(self):
        document={'version':2,'rooms':[{'id':str(uuid4()),'location_id':None,'name':'Workshop','width':13.5,'height':21,
            'unit':'ft','approximate':False,'objects':[{'id':str(uuid4()),'kind':'Rack','name':'Rack XYZ','x':1,'y':1,
            'width':3,'height':1,'rotation':0,'location_id':str(uuid4())}]}]}
        request={'schema_version':2,'revision':0,'request_key':str(uuid4()),'document':document}
        with self.assertRaisesRegex(ValueError,'active|location'):self.store.save(self.client,self.group,request,actor_id=self.actor)
    def test_restart_persistence(self):
        self.store.save(self.client,self.group,self.request(0),actor_id=self.actor);other=Workshop(self.store.path);self.assertEqual(other.get(self.group)['revision'],1)
    def test_cycle_and_stale_parent_move_blocked(self):
        with self.assertRaises(ValueError):move_location(self.client,{'id':self.client.a,'parent_id':self.client.b,'updated_at':'1'})
        with self.assertRaises(Conflict):move_location(self.client,{'id':self.client.b,'parent_id':'','updated_at':'old'})
        self.assertFalse(self.client.writes)
    def test_move_preserves_metadata_and_retry_reads(self):
        self.client.nodes[self.client.b]['description']='Keep this';move_location(self.client,{'id':self.client.b,'parent_id':'','updated_at':'1'});self.assertEqual(self.client.writes[0]['description'],'Keep this');move_location(self.client,{'id':self.client.b,'parent_id':'','updated_at':'1'});self.assertEqual(len(self.client.writes),1)
    def test_mixed_parent_chain_has_no_fixed_depth_limit(self):
        parent=None
        for index in range(70):
            key=str(uuid4());self.client.nodes[key]={'id':key,'name':'Level '+str(index),'entityType':{'id':str(uuid4()),'isLocation':index%2==0},'parent':{'id':parent} if parent else None,'updatedAt':'1','fields':[],'tags':[]}
            parent=key
        move_location(self.client,{'id':self.client.b,'parent_id':parent,'updated_at':'1'})
        self.assertEqual(self.client.nodes[self.client.b]['parent']['id'],parent)
        with self.assertRaises(ValueError):move_location(self.client,{'id':parent,'parent_id':self.client.b,'updated_at':'1'})
        self.assertEqual(len(self.client.writes),1)

    def test_native_storage_kind_and_code(self):
        plan=prepare_location(self.client,{'name':'XYZ-2-B','parent_id':self.client.b,'storage_kind':'Bin','storage_code':'B'});self.assertEqual(plan['create']['parentId'],self.client.b);self.assertEqual(plan['fields'][0]['textValue'],'Bin');self.assertEqual(plan['fields'][1]['textValue'],'B')
    def test_duplicate_storage_code_within_parent(self):
        self.client.nodes[self.client.b]['fields']=[{'name':'Storage code','type':'text','textValue':'2'}]
        with self.assertRaises(Conflict):prepare_location(self.client,{'name':'Another shelf','parent_id':self.client.a,'storage_kind':'Shelf','storage_code':'2'})

    def test_lost_order_response_recovers_without_put(self):
        self.client=ShelfOrderClient();self.client.fail_after_put=True
        data={'entity_id':self.client.a,'updated_at':'rack-v1','shelf_ids':[self.client.b]}
        with self.assertRaises(OSError):submit_shelf_order(self.client,self.jobs,self.group,self.actor,self.key,data)
        job=self.jobs.unresolved(self.group)[0]
        self.assertEqual(job['status'],'review')
        before=len(self.client.writes)
        result=recover_shelf_order(self.client,self.jobs,self.group,job['id'],'complete')
        self.assertEqual(result['status'],'completed')
        self.assertEqual(len(self.client.writes),before)

    def order_data(self,client=None):
        client=client or self.client
        return {'entity_id':client.a,'updated_at':'rack-v1','shelf_ids':[client.b]}

    def test_order_validation_and_metadata_preservation(self):
        c=ShelfOrderClient();bad=self.order_data(c)
        bad['updated_at']='old'
        with self.assertRaises(Conflict):submit_shelf_order(c,self.jobs,self.group,self.actor,self.key,bad)
        c=ShelfOrderClient();c.nodes[c.a]['fields'][0]['textValue']='Cabinet'
        with self.assertRaises(ValueError):submit_shelf_order(c,self.jobs,self.group,self.actor,self.key,self.order_data(c))
        for mode in ('nonchild','nonShelf','foreign','duplicate'):
            c=ShelfOrderClient();data=self.order_data(c)
            if mode=='nonchild':
                other=str(uuid4());c.nodes[other]={'id':other,'name':'Other rack','entityType':{'id':str(uuid4()),'isLocation':True},'parent':None,'updatedAt':'1','fields':[{'name':'Storage kind','type':'text','textValue':'Rack'}],'tags':[]}
                child=str(uuid4());c.nodes[child]={'id':child,'name':'Elsewhere','entityType':{'id':str(uuid4()),'isLocation':True},'parent':{'id':other},'updatedAt':'1','fields':[{'name':'Storage kind','type':'text','textValue':'Shelf'}]}
                data['shelf_ids']=[child]
            elif mode=='nonShelf':
                child=str(uuid4());c.nodes[child]={'id':child,'name':'Drawer','entityType':{'id':str(uuid4()),'isLocation':True},'parent':{'id':c.a},'updatedAt':'1','fields':[{'name':'Storage kind','type':'text','textValue':'Drawer'}]}
                data['shelf_ids']=[child]
            elif mode=='foreign':data['shelf_ids']=[str(uuid4())]
            else:data['shelf_ids']=[c.b,c.b]
            with self.assertRaises(ValueError):submit_shelf_order(c,self.jobs,self.group,self.actor,self.key,data)
            self.assertEqual(c.writes,[])
        for native_fields in ([{'name':'Workshop shelf order','type':'text','textValue':'[]'},{'name':'Workshop shelf order','type':'text','textValue':'[]'}], [{'name':'Workshop shelf order','type':'number','textValue':'1'}]):
            c=ShelfOrderClient();c.nodes[c.a]['fields'].extend(native_fields)
            with self.assertRaises(ValueError):submit_shelf_order(c,self.jobs,self.group,self.actor,self.key,self.order_data(c))
            self.assertEqual(c.writes,[])
        c=ShelfOrderClient();oversized=self.order_data(c);oversized['shelf_ids']=[str(uuid4()) for _ in range(300)]
        with self.assertRaises(ValueError):submit_shelf_order(c,self.jobs,self.group,self.actor,self.key,oversized)
        self.assertEqual(c.writes,[])
        c=ShelfOrderClient();c.nodes[c.a].update(parent={'id':c.b},description='Description',tags=[{'id':'tag-1','name':'Keep'}],attachments=[{'id':'attachment-1'}],custom='preserve')
        c.nodes[c.a]['fields'].append({'name':'Other native field','type':'text','textValue':'unchanged','id':'native-field-id'})
        submit_shelf_order(c,self.jobs,self.group,self.actor,self.key,self.order_data(c))
        payload=c.writes[0]
        self.assertEqual(payload['parentId'],c.b);self.assertEqual(payload['tagIds'],['tag-1'])
        self.assertEqual(payload['attachments'],[{'id':'attachment-1'}]);self.assertEqual(payload['description'],'Description')
        self.assertEqual(payload['entityTypeId'],c.nodes[c.a]['entityType']['id'])
        self.assertEqual(payload['custom'],'preserve');self.assertIn({'name':'Other native field','type':'text','textValue':'unchanged','id':'native-field-id'},payload['fields'])
        c=ShelfOrderClient();c.nodes[c.a]['fields'].extend([{'name':'Workshop shelf order','type':'text','textValue':'[]'},{'name':'Keep field','type':'text','textValue':'keep'}])
        remove=dict(self.order_data(c),shelf_ids=None)
        submit_shelf_order(c,self.jobs,self.group,self.actor,str(uuid4()),remove)
        self.assertEqual(c.writes[0]['fields'],[{'name':'Storage kind','type':'text','textValue':'Rack'},{'name':'Keep field','type':'text','textValue':'keep'}])

    def test_order_restart_key_conflict_and_cancel(self):
        c=ShelfOrderClient();data=self.order_data(c);c.fail_before_put=True
        with self.assertRaises(OSError):submit_shelf_order(c,self.jobs,self.group,self.actor,self.key,data)
        job=self.jobs.unresolved(self.group)[0]
        reopened=NativeJobs(Ledger(self.jobs.ledger.path));saved=reopened.detail(self.group,job['id'])
        self.assertEqual(saved['status'],'review');self.assertEqual(saved['context']['original_updated_at'],'rack-v1')
        before=len(c.writes)
        with self.assertRaises(Conflict):submit_shelf_order(c,reopened,self.group,self.actor,self.key,data)
        changed=dict(data,shelf_ids=[])
        with self.assertRaises(Conflict):submit_shelf_order(c,reopened,self.group,self.actor,self.key,changed)
        with self.assertRaises(Conflict):submit_shelf_order(c,reopened,self.group,str(uuid4()),self.key,data)
        self.assertEqual(len(c.writes),before)
        result=recover_shelf_order(c,reopened,self.group,job['id'],'cancel')
        self.assertEqual(result['status'],'cancelled')
        self.assertEqual(recover_shelf_order(c,reopened,self.group,job['id'],'cancel'),{'id':job['id'],'status':'cancelled'})
        c=ShelfOrderClient();c.fail_after_put=True
        with self.assertRaises(OSError):submit_shelf_order(c,self.jobs,self.group,str(uuid4()),str(uuid4()),self.order_data(c))
        uncertain=self.jobs.unresolved(self.group)[0]
        c.nodes[c.a]['fields'].append({'name':'Workshop shelf order','type':'text','textValue':'["third-state"]'})
        with self.assertRaises(Conflict):recover_shelf_order(c,self.jobs,self.group,uncertain['id'],'cancel')
        self.assertEqual(self.jobs.detail(self.group,uncertain['id'])['status'],'review')

    def test_completed_shelf_order_key_retries_without_native_read_or_put(self):
        c=ShelfOrderClient();data=self.order_data(c)
        first=submit_shelf_order(c,self.jobs,self.group,self.actor,self.key,data)
        c.nodes[c.a]['updatedAt']='changed-after-completion'
        c.entity=lambda _key: (_ for _ in ()).throw(AssertionError('completed retry read native state'))
        before=len(c.writes)
        second=submit_shelf_order(c,self.jobs,self.group,self.actor,self.key,data)
        self.assertEqual(second,first);self.assertEqual(len(c.writes),before)

    def test_prepared_order_context_survives_crash_and_restart(self):
        c=ShelfOrderClient();data=self.order_data(c);prepare=self.jobs.prepare
        def crash_after_prepare(*args,**kwargs):
            prepare(*args,**kwargs)
            raise SystemExit('simulated process exit after prepare transaction')
        self.jobs.prepare=crash_after_prepare
        with self.assertRaises(SystemExit):submit_shelf_order(c,self.jobs,self.group,self.actor,self.key,data)
        reopened=NativeJobs(Ledger(self.jobs.ledger.path));job=reopened.unresolved(self.group)[0]
        self.assertEqual(job['status'],'prepared');self.assertEqual(job['context']['rack_id'],c.a)
        result=recover_shelf_order(c,reopened,self.group,job['id'],'cancel')
        self.assertEqual(result['status'],'cancelled');self.assertEqual(c.writes,[])
        self.jobs.prepare=prepare
        legacy_key=str(uuid4());legacy=self.jobs.prepare(self.group,self.actor,'workshop_shelf_order',legacy_key,self.order_data(c))
        legacy_reopened=NativeJobs(Ledger(self.jobs.ledger.path))
        c.entities=lambda *_: (_ for _ in ()).throw(AssertionError('contextless unsent cancellation read native state'))
        self.assertEqual(recover_shelf_order(c,legacy_reopened,self.group,legacy['id'],'cancel')['status'],'cancelled')
        self.assertEqual(c.writes,[])

    def test_shelf_order_rejects_list_detail_parent_disagreement(self):
        c=ShelfOrderClient();original_entity=c.entity
        def moved_detail(key):
            entity=original_entity(key)
            if key==c.b:entity['parent']={'id':str(uuid4())}
            return entity
        c.entity=moved_detail
        with self.assertRaises(ValueError):submit_shelf_order(c,self.jobs,self.group,self.actor,self.key,self.order_data(c))
        self.assertEqual(c.writes,[]);self.assertEqual(self.jobs.unresolved(self.group),[])

    def test_shelf_order_recovery_rejects_list_detail_parent_disagreement(self):
        c=ShelfOrderClient();c.fail_after_put=True
        with self.assertRaises(OSError):submit_shelf_order(c,self.jobs,self.group,self.actor,self.key,self.order_data(c))
        job=self.jobs.unresolved(self.group)[0];original_entity=c.entity
        def moved_detail(key):
            entity=original_entity(key)
            if key==c.b:entity['parent']={'id':str(uuid4())}
            return entity
        c.entity=moved_detail
        with self.assertRaises(Conflict):recover_shelf_order(c,self.jobs,self.group,job['id'],'complete')
        self.assertEqual(len(c.writes),1);self.assertEqual(self.jobs.detail(self.group,job['id'])['status'],'review')

if __name__=='__main__':unittest.main()
