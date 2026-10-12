import copy,pathlib,tempfile,unittest
from uuid import uuid4
from ledger import Ledger,Conflict
from native_jobs import NativeJobs
from setup_native import submit,recover_creation
from products import lookup,GTIN_FIELD,MARKER_FIELD
from conditions import condition
from maps import ROOM_FIELD


class Client:
    def __init__(self):
        self.item_type,self.loc_type,self.room=[str(uuid4()) for _ in range(3)]
        self.records={self.room:self.make(self.room,{'name':'Workshop','quantity':0,'entityTypeId':self.loc_type})}
        self.tags={};self.templates={};self.posts=0;self.lose_entity_response=False
    def make(self,key,body):
        entity={'id':key,'name':body['name'],'description':body.get('description',''),'quantity':body.get('quantity',1),'archived':False,'parent':{'id':body['parentId']} if body.get('parentId') else None,'entityType':{'id':body['entityTypeId'],'isLocation':body['entityTypeId']==self.loc_type},'tags':[{'id':tag} for tag in body.get('tagIds',[])],'fields':[],'serialNumber':'','manufacturer':'','modelNumber':''}
        return entity
    def entity(self,key):return copy.deepcopy(self.records[key])
    def entities(self,locations=False):return [self.entity(k) for k,e in self.records.items() if e['entityType']['isLocation']==locations]
    def call(self,path,method='GET',data=None):
        if path=='/api/v1/entity-types':return [{'id':self.item_type,'isLocation':False},{'id':self.loc_type,'isLocation':True}]
        if path=='/api/v1/tags':
            if method=='GET':return list(copy.deepcopy(self.tags).values())
            key=str(uuid4());self.tags[key]={'id':key,**data};return copy.deepcopy(self.tags[key])
        if path.startswith('/api/v1/tags/'):
            self.tags.pop(path.rsplit('/',1)[1],None);return None
        if path=='/api/v1/templates':
            if method=='GET':return [{'id':key} for key in self.templates]
            key=str(uuid4());self.templates[key]={'id':key,'updatedAt':'2026-10-03T00:00:00Z','defaultLocation':None,'defaultTags':[],**copy.deepcopy(data)};return copy.deepcopy(self.templates[key])
        if path.startswith('/api/v1/templates/') and not path.endswith('/create-item'):
            key=path.rsplit('/',1)[1]
            if method=='PUT':self.templates[key]=copy.deepcopy(data)
            return copy.deepcopy(self.templates[key])
        if method=='POST' and (path=='/api/v1/entities' or path.endswith('/create-item')):
            key=str(uuid4());entity=self.make(key,data);self.posts+=1
            if path.endswith('/create-item'):
                template=self.templates[path.split('/')[-2]];entity['fields']=copy.deepcopy(template['fields']);entity['manufacturer']=template.get('defaultManufacturer','');entity['modelNumber']=template.get('defaultModelNumber','')
            self.records[key]=entity
            if self.lose_entity_response:self.lose_entity_response=False;raise OSError('Native creation happened; response was lost')
            return self.entity(key)
        if path.startswith('/api/v1/entities/'):
            key=path.rsplit('/',1)[1]
            if method=='PUT':
                payload=copy.deepcopy(data);payload['parent']={'id':payload['parentId']} if payload['parentId'] else None;self.records[key]=payload
            if method=='PATCH' and 'tagIds' in data:self.records[key]['tags']=[{'id':tag} for tag in data['tagIds']]
            return self.entity(key)
        raise AssertionError((path,method))


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.jobs=NativeJobs(Ledger(pathlib.Path(self.temp.name)/'ops.db'));self.client=Client()
        self.group,self.actor=[str(uuid4()) for _ in range(2)]
    def tearDown(self):self.temp.cleanup()
    def submit(self,kind,data,key=None):return submit(self.client,self.jobs,self.group,self.actor,kind,key or str(uuid4()),data)
    def test_location_creation_is_native_and_removes_temporary_marker(self):
        result=self.submit('create_location',{'name':'New room','map_room':True})
        entity=self.client.entity(result['entity_id']);self.assertTrue(entity['entityType']['isLocation']);self.assertEqual(entity['tags'],[]);self.assertEqual(self.client.tags,{})
        self.assertTrue(any(f['name']==ROOM_FIELD for f in entity['fields']))
    def test_lost_create_response_recovers_existing_uuid_without_duplicate(self):
        key=str(uuid4());self.client.lose_entity_response=True
        with self.assertRaises(Conflict):self.submit('create_location',{'name':'Shelf','parent_id':self.client.room},key)
        job=self.jobs.unresolved(self.group)[0];recover_creation(self.client,self.jobs,self.group,job['id'],'complete')
        result=self.submit('create_location',{'name':'Shelf','parent_id':self.client.room},key)
        self.assertEqual(self.client.posts,1);self.assertEqual(self.client.entity(result['entity_id'])['name'],'Shelf')
    def test_unreviewed_enrollment_and_serial_metadata(self):
        result=self.submit('create_asset',{'name':'Drone','serial':'SERIAL-1','location_id':self.client.room})
        entity=self.client.entity(result['entity_id']);self.assertEqual(entity['serialNumber'],'SERIAL-1');self.assertEqual(condition(entity),'Unreviewed')
        with self.assertRaises(Conflict):self.submit('create_asset',{'name':'Other drone','serial':'SERIAL-1','location_id':self.client.room})
    def test_explicit_review_can_mark_new_equipment_ready(self):
        result=self.submit('create_asset',{'name':'Drone','location_id':self.client.room,'reviewed':True})
        self.assertEqual(condition(self.client.entity(result['entity_id'])),'Ready')
    def test_native_catalog_is_separate_from_owned_assets(self):
        result=self.submit('create_template',{'name':'Synthetic product','gtin':'4006381333931','manufacturer':'Demo','model':'Model-1'})
        self.assertEqual(len(self.client.records),1);self.assertEqual(len(self.client.templates),1)
        product=lookup(self.client,'04006381333931')['product'];self.assertEqual(product['id'],result['entity_id']);self.assertEqual(product['manufacturer'],'Demo')
        template=self.client.templates[result['entity_id']];self.assertFalse(any(f['name']==MARKER_FIELD for f in template['fields']))
        with self.assertRaises(Conflict):self.submit('create_template',{'name':'Duplicate','gtin':'4006381333931'})
    def test_enrollment_from_native_template_copies_product_metadata(self):
        product=self.submit('create_template',{'name':'Synthetic product','gtin':'4006381333931','manufacturer':'Demo','model':'Model-1'})
        result=self.submit('create_asset',{'name':'Owned product','serial':'UNIT-1','location_id':self.client.room,'template_id':product['entity_id']})
        entity=self.client.entity(result['entity_id']);self.assertEqual(entity['manufacturer'],'Demo');self.assertEqual(entity['modelNumber'],'Model-1')
        self.assertTrue(any(f['name']==GTIN_FIELD for f in entity['fields']));self.assertEqual(condition(entity),'Unreviewed')
    def test_created_record_cannot_be_cancelled_after_lost_response(self):
        self.client.lose_entity_response=True
        with self.assertRaises(Conflict):self.submit('create_location',{'name':'Shelf','parent_id':self.client.room})
        job=self.jobs.unresolved(self.group)[0]
        with self.assertRaises(Conflict):recover_creation(self.client,self.jobs,self.group,job['id'],'cancel')
    def test_invalid_native_parent_never_creates_an_asset(self):
        asset_id=str(uuid4());self.client.records[asset_id]=self.client.make(asset_id,{'name':'Equipment','entityTypeId':self.client.item_type});self.client.records[asset_id]['archived']=True
        with self.assertRaises(ValueError):self.submit('create_asset',{'name':'Other','location_id':asset_id})
        self.assertEqual(self.client.posts,0)

    def test_optional_mixed_parents_keep_native_types(self):
        box=self.submit('create_asset',{'name':'Box'})['entity_id']
        shelf=self.submit('create_location',{'name':'Shelf in box','parent_id':box})['entity_id']
        nested=self.submit('create_asset',{'name':'Item in box','location_id':box})['entity_id']
        self.assertIsNone(self.client.entity(box)['parent'])
        self.assertTrue(self.client.entity(shelf)['entityType']['isLocation'])
        self.assertEqual(self.client.entity(shelf)['parent']['id'],box)
        self.assertEqual(self.client.entity(nested)['parent']['id'],box)

    def test_manufacturer_code_enrollment_is_native_and_preserves_serial(self):
        code='{"opaque":"manufacturer payload"}'
        result=self.submit('create_asset',{'name':'Fixture equipment','serial':'SERIAL-QR','manufacturer_code':code,'location_id':self.client.room})
        entity=self.client.entity(result['entity_id'])
        self.assertEqual(entity['serialNumber'],'SERIAL-QR')
        self.assertEqual(next(f['textValue'] for f in entity['fields'] if f['name']=='Manufacturer QR code'),code)
        before=self.client.posts
        with self.assertRaises(Conflict):self.submit('create_asset',{'name':'Other equipment','manufacturer_code':code,'location_id':self.client.room})
        self.assertEqual(self.client.posts,before)


if __name__=='__main__':unittest.main()
