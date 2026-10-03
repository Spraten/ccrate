import copy,pathlib,tempfile,unittest
from uuid import uuid4
from ledger import Ledger,Conflict
from returns import confirm_return,recover


class Client:
    def __init__(self,members,entities):self.members=members;self.entities=entities;self.writes=[];self.fail_patch=False;self.fail_put=False
    def entity(self,key):return copy.deepcopy(self.entities[key])
    def call(self,path,method='GET',data=None):
        if path=='/api/v1/groups/members':return [{'id':m} for m in self.members]
        key=path.rsplit('/',1)[1];self.writes.append((method,key,copy.deepcopy(data)))
        if method=='PUT':
            if self.fail_put:raise OSError('Injected interruption before write')
            payload=copy.deepcopy(data);payload['parent']={'id':payload['parentId']};self.entities[key]=payload
        elif method=='PATCH':
            self.entities[key]['parent']={'id':data['parentId']}
            if self.fail_patch:raise OSError('Injected lost response after write')
        return self.entity(key)


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.ledger=Ledger(pathlib.Path(self.temp.name)/'ops.db')
        self.group,self.borrower,self.returner,self.asset,self.shelf,self.other,self.type=[str(uuid4()) for _ in range(7)]
        item={'id':self.asset,'name':'Equipment','quantity':1,'archived':False,'serialNumber':'preserve','parent':{'id':self.shelf},'entityType':{'id':self.type,'isLocation':False},'tags':[],'fields':[{'name':'Equipment condition','type':'text','textValue':'Ready'}]}
        place=lambda key:{'id':key,'name':'Shelf','archived':False,'entityType':{'isLocation':True}}
        self.client=Client([self.borrower,self.returner],{self.asset:item,self.shelf:place(self.shelf),self.other:place(self.other)})
        checkout=self.ledger.begin(self.group,self.borrower,'check_out',[self.asset],str(uuid4()));self.ledger.complete(checkout['id'])
    def tearDown(self):self.temp.cleanup()
    def confirm(self,**kwargs):
        return confirm_return(self.client,self.ledger,self.group,self.returner,[{'entity_id':self.asset,**kwargs.get('target',{})}],kwargs.get('key',str(uuid4())),kwargs.get('valid',lambda:True))
    def test_colleague_return_preserves_native_asset_and_records_actor(self):
        before=self.client.entity(self.asset);result=self.confirm()
        self.assertEqual(self.ledger.custody(self.group),[]);self.assertEqual(self.client.entity(self.asset),before);self.assertFalse(self.client.writes)
        self.assertEqual(self.ledger.detail(self.group,result['id'])['actor_id'],self.returner)
    def test_repeat_return_has_one_operation(self):
        key=str(uuid4());first=self.confirm(key=key);second=self.confirm(key=key);self.assertEqual(first,second)
        with self.ledger.connection() as db:self.assertEqual(db.execute('SELECT count(*) FROM operations').fetchone()[0],2)
    def test_changed_return_key_rejected(self):
        key=str(uuid4());self.confirm(key=key)
        with self.assertRaises(Conflict):self.confirm(key=key,target={'condition':'Broken'})
    def test_changed_condition_note_and_destination(self):
        self.confirm(target={'condition':'Broken','note':'Cracked housing','destination_id':self.other})
        entity=self.client.entity(self.asset);self.assertEqual(entity['parent']['id'],self.other);self.assertEqual(entity['serialNumber'],'preserve')
        fields={f['name']:f['textValue'] for f in entity['fields']}
        self.assertEqual(fields['Equipment condition'],'Broken');self.assertEqual(fields['Equipment condition note'],'Cracked housing')
    def test_lost_native_response_retains_custody_and_recovers_once(self):
        self.client.fail_patch=True
        with self.assertRaises(Conflict):self.confirm(target={'destination_id':self.other})
        operation=self.ledger.unresolved()[0];self.assertEqual(operation['status'],'review');self.assertEqual(len(self.ledger.custody(self.group)),1)
        with self.assertRaises(Conflict):recover(self.client,self.ledger,self.group,operation['id'],'cancel')
        self.client.fail_patch=False;recover(self.client,self.ledger,self.group,operation['id'],'complete')
        self.assertEqual(self.ledger.custody(self.group),[])
        self.assertEqual(sum(w[0]=='PATCH' for w in self.client.writes),1)
        with self.assertRaises(Conflict):recover(self.client,self.ledger,self.group,operation['id'],'complete')
    def test_failed_before_native_write_can_cancel(self):
        self.client.fail_put=True
        with self.assertRaises(Conflict):self.confirm(target={'condition':'Broken'})
        op=self.ledger.unresolved()[0];recover(self.client,self.ledger,self.group,op['id'],'cancel')
        self.assertEqual(len(self.ledger.custody(self.group)),1);self.assertEqual(self.ledger.unresolved(),[])
    def test_expired_session_and_removed_member_rejected(self):
        with self.assertRaises(Conflict):self.confirm(valid=lambda:False)
        self.client.members=[self.borrower]
        with self.assertRaises(Conflict):self.confirm()
    def test_normal_return_cannot_mark_ready_or_trash(self):
        for state in ('Ready','Trashed','Archived','Retired'):
            with self.assertRaises(ValueError):self.confirm(target={'condition':state})
    def test_non_location_or_archived_destination_rejected(self):
        with self.assertRaises(ValueError):self.confirm(target={'destination_id':self.asset})
        self.client.entities[self.other]['archived']=True
        with self.assertRaises(Conflict):self.confirm(target={'destination_id':self.other})
    def test_recovery_rejects_group_mismatch_and_unexpected_native_change(self):
        self.client.fail_put=True
        with self.assertRaises(Conflict):self.confirm(target={'condition':'Broken'})
        op=self.ledger.unresolved()[0]
        with self.assertRaises(ValueError):recover(self.client,self.ledger,str(uuid4()),op['id'],'complete')
        self.client.entities[self.asset]['fields'][0]['textValue']='Retired'
        with self.assertRaises(Conflict):recover(self.client,self.ledger,self.group,op['id'],'complete')


if __name__=='__main__':unittest.main()
