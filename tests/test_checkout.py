import copy,pathlib,tempfile,unittest
from uuid import uuid4
from ledger import Ledger,Conflict
from checkout import confirm_checkout


class Client:
    def __init__(self,user,assets):self.user=user;self.assets=assets;self.writes=[]
    def call(self,path,method='GET',data=None):
        if method!='GET':self.writes.append((path,method,data));raise AssertionError('Checkout must not write native inventory')
        return [{'id':self.user}]
    def entity(self,asset):return copy.deepcopy(self.assets[asset])


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.ledger=Ledger(pathlib.Path(self.temp.name)/'ops.db')
        self.group,self.user,self.asset=[str(uuid4()) for _ in range(3)]
        self.entity={'id':self.asset,'name':'Test equipment','quantity':1,'archived':False,'parent':{'id':str(uuid4())},'entityType':{'isLocation':False},'fields':[{'name':'Equipment condition','type':'text','textValue':'Ready'}]}
        self.client=Client(self.user,{self.asset:self.entity})
    def tearDown(self):self.temp.cleanup()
    def confirm(self,**kwargs):
        return confirm_checkout(self.client,self.ledger,self.group,self.user,kwargs.get('assets',[self.asset]),kwargs.get('key',str(uuid4())),kwargs.get('valid',lambda:True))
    def test_native_shelf_preserved_and_repeat_confirm_idempotent(self):
        original=copy.deepcopy(self.entity);key=str(uuid4())
        first=self.confirm(key=key);second=self.confirm(key=key)
        self.assertEqual(first,second);self.assertEqual(self.entity,original);self.assertFalse(self.client.writes)
    def test_unreviewed_and_each_blocked_state_leave_no_operation(self):
        for state in ('Unreviewed','Broken','Trashed','Retired','Maintenance','Quarantined','Needs Attention','Archived'):
            self.entity['fields'][0]['textValue']=state
            with self.assertRaises(Conflict):self.confirm()
        with self.ledger.connection() as db:self.assertEqual(db.execute('SELECT count(*) FROM operations').fetchone()[0],0)
    def test_expired_session_rejected_after_native_validation(self):
        with self.assertRaises(Conflict):self.confirm(valid=lambda:False)
        self.assertEqual(self.ledger.unresolved(),[])
    def test_removed_member_rejected(self):
        self.client.user=str(uuid4())
        with self.assertRaises(Conflict):self.confirm()
    def test_duplicate_asset_rejected(self):
        with self.assertRaises(ValueError):self.confirm(assets=[self.asset,self.asset])


if __name__=='__main__':unittest.main()
