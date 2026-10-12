import sys,pathlib,tempfile,unittest
from uuid import uuid4
from unittest.mock import patch
sys.path[:0]=[str(pathlib.Path(__file__).resolve().parents[1]/'ops'),str(pathlib.Path(__file__).resolve().parents[1]/'kiosk')]
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from imports import Imports,parse_csv
from ledger import Conflict
from setup_native import prepare_asset

class Client:
    def __init__(self):
        self.location=str(uuid4());self.kind=str(uuid4());self.items={};self.loc={'id':self.location,'name':'Shelf A','entityType':{'isLocation':True},'archived':False}
    def entities(self,locations=False):return [self.loc] if locations else list(self.items.values())
    def entity(self,key):return self.loc if key==self.location else self.items[key]
    def call(self,path,*args):return [{'id':self.kind,'name':'Equipment','isLocation':False}]

class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Imports(pathlib.Path(self.temp.name)/'imports.db');self.client=Client();self.group=str(uuid4());self.actor=str(uuid4())
    def tearDown(self):self.temp.cleanup()
    def batch(self,csv='Name,Serial,ID\n"Tool, blue",SN1,A1\nTool two,SN2,A2\n'):
        batch=self.store.upload(self.group,self.actor,{'csv':csv,'source':'Asset Manager','filename':'test.csv'})
        return self.store.map(self.client,self.group,{'id':batch['id'],'mapping':{'name':'Name','serial':'Serial','external_id':'ID'},'location_id':self.client.location,'type_id':self.client.kind})
    def test_utf8_quotes_semicolon(self):
        heads,rows=parse_csv('\ufeffName;Serial\n"Drill; blå";123\n');self.assertEqual(rows,[['Drill; blå','123']])
    def test_malformed_rejected(self):
        for content in ['Name,Name\na,b','Name,Serial\na,b,c','Name\n"unterminated','Name\n']:
            with self.assertRaises(ValueError):parse_csv(content)
    def test_private_group_scope(self):
        batch=self.batch()
        with self.assertRaises(ValueError):self.store.get(str(uuid4()),batch['id'])
        self.assertEqual(self.store.list(str(uuid4())),[])
    def test_preview_no_native_create(self):
        batch=self.batch();self.assertEqual(len(self.client.items),0);self.assertEqual(batch['items'][0]['input']['import_condition'],'Unreviewed');self.assertFalse(batch['items'][0]['errors'])
    def test_duplicate_source_and_serial(self):
        batch=self.batch();d=batch['items'][0]['input'];key=str(uuid4());self.client.items[key]={'id':key,'name':'Existing','serialNumber':'SN1','fields':[{'name':'Import source key','type':'text','textValue':d['import_source_key']}]}
        batch=self.store.validate(self.client,self.group,batch['id']);self.assertIn('Already in C-Crate',batch['items'][0]['errors'][0])
    def test_duplicate_within_batch_and_skip(self):
        batch=self.batch('Name,Serial,ID\na,same,A\nb,same,B\n');self.assertTrue(batch['items'][1]['errors'])
        batch=self.store.save(self.client,None,self.group,{'id':batch['id'],'index':0,'selected':False,'input':{}});self.assertFalse(batch['items'][1]['errors'])
    def test_ready_needs_inspection(self):
        batch=self.batch();batch=self.store.save(self.client,None,self.group,{'id':batch['id'],'index':0,'input':{'import_condition':'Ready'}});self.assertTrue(batch['items'][0]['errors'])
        with self.assertRaises(ValueError):prepare_asset(self.client,batch['items'][0]['input'])
        batch=self.store.save(self.client,None,self.group,{'id':batch['id'],'index':0,'input':{'reviewed':True}});self.assertFalse(batch['items'][0]['errors']);self.assertEqual(prepare_asset(self.client,batch['items'][0]['input'])['initial_state'],'Ready')
    def test_optional_parent_and_item_parent(self):
        batch=self.batch();batch=self.store.save(self.client,None,self.group,{'id':batch['id'],'index':0,'input':{'location_id':''}})
        self.assertFalse(batch['items'][0]['errors']);self.assertIsNone(prepare_asset(self.client,batch['items'][0]['input'])['create']['parentId'])
        box=str(uuid4());self.client.items[box]={'id':box,'name':'Box','quantity':1,'archived':False,'entityType':{'id':self.client.kind,'isLocation':False},'fields':[]}
        batch=self.store.save(self.client,None,self.group,{'id':batch['id'],'index':0,'input':{'location_id':box}})
        self.assertFalse(batch['items'][0]['errors']);self.assertEqual(prepare_asset(self.client,batch['items'][0]['input'])['create']['parentId'],box)
    def test_native_provenance_and_condition(self):
        batch=self.batch();d=batch['items'][0]['input'];d['import_condition']='Broken';plan=prepare_asset(self.client,d);self.assertEqual(plan['initial_state'],'Broken');self.assertEqual(plan['metadata']['serialNumber'],'SN1');self.assertEqual(len(plan['fields']),3)
    def test_completed_creation_reconciles_without_post(self):
        batch=self.batch();key=str(uuid4());self.client.items[key]={'id':key,'name':'Created','assetId':'0007','fields':[]}
        with patch.object(self.store,'native_job',return_value={'status':'completed','result_id':key}),patch('imports.submit') as submit:
            result=self.store.create(self.client,None,self.group,{'id':batch['id'],'index':0});submit.assert_not_called();self.assertEqual(result['items'][0]['entity_id'],key)
    def test_uncertain_creation_no_retry(self):
        batch=self.batch()
        with patch.object(self.store,'native_job',return_value={'status':'review'}),patch('imports.submit') as submit:
            with self.assertRaises(Conflict):self.store.create(self.client,None,self.group,{'id':batch['id'],'index':0})
            submit.assert_not_called()
    def test_uncertain_print_no_retry(self):
        batch=self.batch();batch['items'][0]['status']='created';batch['items'][0]['entity_id']=str(uuid4());self.store.put(self.group,batch)
        with patch.object(self.store,'native_job',return_value={'status':'review'}),patch('imports.print_label') as printer:
            with self.assertRaises(Conflict):self.store.label(self.client,None,self.group,{'id':batch['id'],'index':0})
            printer.assert_not_called()
    def test_confirming_manager_owns_new_import_print_and_uploader_stays_unchanged(self):
        batch=self.batch();row=batch['items'][0];row.update(status='created',entity_id=str(uuid4()));self.store.put(self.group,batch)
        manager=str(uuid4());review=str(uuid4());layouts=object()
        with patch.object(self.store,'native_job',return_value=None),patch('imports.print_label') as printer:
            result=self.store.label(self.client,object(),self.group,{'id':batch['id'],'index':0,'review_id':review},actor=manager,layouts=layouts)
        self.assertEqual(printer.call_args.args[3],manager)
        self.assertEqual(printer.call_args.kwargs,{'layouts':layouts,'review_id':review,'valid_context':None})
        self.assertEqual(result['actor'],self.actor)
    def test_reopen_persists_edits(self):
        batch=self.batch();self.store.save(self.client,None,self.group,{'id':batch['id'],'index':0,'input':{'name':'Edited'}})
        other=Imports(self.store.path);self.assertEqual(other.get(self.group,batch['id'])['items'][0]['input']['name'],'Edited')

if __name__=='__main__':unittest.main()
