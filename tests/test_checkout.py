import copy,json,pathlib,tempfile,unittest
from uuid import uuid4
from ledger import Ledger,Conflict
from checkout import checkout_status_actor, confirm_checkout, expand_cart_assets
from checkout_cart import CheckoutCart
from kits import manifest


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
        return confirm_checkout(self.client,self.ledger,self.group,self.user,kwargs.get('assets',[self.asset]),kwargs.get('key',str(uuid4())),kwargs.get('valid',lambda:True),kwargs.get('verified'),kwargs.get('kit_versions'),kwargs.get('cart_context'))
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
    def test_completed_checkout_receipt_consumes_only_the_saved_cart_selection(self):
        cart=CheckoutCart(self.ledger);other=str(uuid4())
        other_entity=copy.deepcopy(self.entity);other_entity['id']=other;self.client.assets[other]=other_entity
        saved=cart.save(self.group,self.user,[self.asset,other],0,str(uuid4()))

        receipt=self.confirm(cart_context={'revision':saved['revision'],'items':[self.asset]})
        consumed=cart.consume_completed_receipt(self.group,self.user,receipt['id'])

        self.assertEqual(consumed['consumed'],[self.asset])
        self.assertEqual(consumed['cart']['items'],[other])

    def test_saved_kit_root_expands_only_to_its_current_verified_manifest(self):
        child=str(uuid4())
        self.client.assets[child]={'id':child,'name':'Kit component','quantity':1,'archived':False,
                                   'parent':{'id':str(uuid4())},'entityType':{'isLocation':False},
                                   'fields':[{'name':'Equipment condition','type':'text','textValue':'Ready'}]}
        self.entity['fields'].append({'name':'Equipment kit manifest','type':'text',
                                      'textValue':json.dumps({'version':1,'members':[child]})})
        expanded=expand_cart_assets(self.client,[self.asset])
        versions=manifest(self.client,self.asset)['versions']

        self.assertEqual(set(expanded),{self.asset,child})
        receipt=self.confirm(assets=expanded,verified=expanded,kit_versions=versions,
                            cart_context={'revision':4,'items':[self.asset]})
        self.assertEqual(self.ledger.detail(self.group,receipt['id'])['context']['checkout_cart'],
                         {'revision':4,'items':[self.asset]})
        with self.assertRaises(Conflict):
            self.confirm(assets=expanded,verified=expanded,kit_versions=versions,
                         cart_context={'revision':4,'items':[child]})

    def test_checkout_status_uses_badge_actor_instead_of_native_service_actor(self):
        operation=self.ledger.begin(self.group,self.user,'check_out',[self.asset],str(uuid4()))

        self.assertEqual(checkout_status_actor(self.ledger,self.group,operation['request_key'],self.user,'service-actor'),self.user)
        self.assertIsNone(checkout_status_actor(self.ledger,self.group,operation['request_key'],None,'service-actor'))


if __name__=='__main__':unittest.main()
