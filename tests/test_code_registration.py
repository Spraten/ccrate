import copy,pathlib,tempfile,unittest
from uuid import uuid4
from code_registration import register_code,recover_code
from scan_codes import MANUFACTURER_FIELD
from native_fields import text_field
from native_jobs import NativeJobs
from ledger import Ledger,Conflict

class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.jobs=NativeJobs(Ledger(pathlib.Path(self.tmp.name)/'ledger.db'))
        self.group,self.actor,self.key,self.identifier=[str(uuid4()) for _ in range(4)]
        self.record={'id':self.identifier,'name':'Fixture','quantity':1,'entityType':{'id':str(uuid4()),'isLocation':False},'parent':{'id':'shelf'},'tags':[{'id':'tag'}],'fields':[{'name':'Existing','type':'text','textValue':'keep'}],'serialNumber':'serial'}
        self.client=type('Client',(),{})();self.client.entity=lambda _:copy.deepcopy(self.record);self.client.entities=lambda:[{'id':self.identifier}];self.client.call=self.call;self.puts=0;self.lose=False
    def call(self,path,method,data):
        self.assertEqual(method,'PUT');self.puts+=1
        self.record=copy.deepcopy(data)
        if self.lose:raise OSError('lost response')
    def submit(self):return register_code(self.client,self.jobs,self.group,self.actor,self.key,{'entity_id':self.identifier,'code':'https://vendor.invalid/opaque'})
    def test_native_metadata_preserved_and_repeated_confirm_idempotent(self):
        before=copy.deepcopy(self.record);self.submit();self.submit();self.assertEqual(self.puts,1)
        for name in ['name','serialNumber','tags','parent']:self.assertEqual(self.record[name],before[name])
        self.assertEqual(text_field(self.record,'Existing'),'keep')
        self.assertEqual(text_field(self.record,MANUFACTURER_FIELD),'https://vendor.invalid/opaque')
    def test_lost_response_requires_recovery_without_another_write(self):
        self.lose=True
        with self.assertRaises(Conflict):self.submit()
        with self.assertRaises(Conflict):self.submit()
        job=self.jobs.unresolved(self.group)[0];recover_code(self.client,self.jobs,self.group,job['id'],'complete')
        self.assertEqual(self.puts,1)
    def test_existing_code_is_not_overwritten(self):
        self.record['fields'].append({'name':MANUFACTURER_FIELD,'type':'text','textValue':'other'})
        with self.assertRaises(Conflict):self.submit()
        self.assertEqual(self.puts,0)
