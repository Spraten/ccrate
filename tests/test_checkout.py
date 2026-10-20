import copy,json,pathlib,tempfile,unittest
from uuid import uuid4
from ledger import Ledger,Conflict
from checkout import checkout_availability, checkout_cart_context, checkout_status_actor, confirm_checkout, expand_cart_assets
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
        return confirm_checkout(self.client,self.ledger,self.group,self.user,kwargs.get('assets',[self.asset]),kwargs.get('key',str(uuid4())),kwargs.get('valid',lambda:True),kwargs.get('verified'),kwargs.get('kit_versions'),kwargs.get('cart_context'),kwargs.get('notes'))
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

    def test_completed_kiosk_edit_consumes_checked_out_and_removed_saved_rows(self):
        cart=CheckoutCart(self.ledger);other=str(uuid4())
        other_entity=copy.deepcopy(self.entity);other_entity['id']=other;self.client.assets[other]=other_entity
        saved=cart.save(self.group,self.user,[self.asset,other],0,str(uuid4()))

        receipt=self.confirm(assets=[self.asset],cart_context={'revision':saved['revision'],'items':[self.asset],
                                                               'original_items':[self.asset,other]})

        result=cart.consume_completed_receipt(self.group,self.user,receipt['id'])
        self.assertEqual(result['cart']['items'],[other])
        self.assertEqual(result['cart']['notes'],{})
        self.assertEqual(result['cart']['revision'],saved['revision']+1)

    def test_kiosk_can_confirm_items_added_beyond_the_desk_cart(self):
        cart=CheckoutCart(self.ledger);other=str(uuid4())
        other_entity=copy.deepcopy(self.entity);other_entity['id']=other;self.client.assets[other]=other_entity
        saved=cart.save(self.group,self.user,[self.asset],0,str(uuid4()))

        receipt=self.confirm(assets=[self.asset,other],cart_context={'revision':saved['revision'],'items':[self.asset,other]})

        self.assertEqual(self.ledger.detail(self.group,receipt['id'])['assets'],sorted([self.asset,other]))
        self.assertEqual(cart.consume_completed_receipt(self.group,self.user,receipt['id'])['cart']['items'],[])

    def test_atomic_ledger_revalidation_rejects_asset_checked_out_before_confirmation(self):
        self.ledger.begin(self.group,self.user,'check_out',[self.asset],str(uuid4()))

        with self.assertRaises(Conflict):self.confirm()

        self.assertEqual(len(self.ledger.unresolved()),1)

    def test_availability_reports_unresolved_operation_blockers(self):
        self.ledger.begin(self.group,self.user,'check_out',[self.asset],str(uuid4()))

        result=checkout_availability(self.client,self.ledger,self.group,[self.asset])

        self.assertEqual(result,[{'id':self.asset,'name':'Test equipment',
                                  'reason':'Checkout operation requires recovery (pending)'}])
        operation=self.ledger.unresolved()[0]
        self.ledger.review(operation['id'],'Native result needs inspection')

        result=checkout_availability(self.client,self.ledger,self.group,[self.asset])

        self.assertEqual(result[0]['reason'],'Checkout operation requires recovery (review)')

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

    def test_checkout_notes_bound_to_receipt(self):
        note = 'Use the shorter clamp.'
        receipt = self.confirm(notes={self.asset: note})
        detail = self.ledger.detail(self.group, receipt['id'])
        self.assertEqual(detail['context']['checkout_notes'], {self.asset: note})
        self.assertEqual(detail['events'][0]['detail']['intent']['checkout_notes'], {self.asset: note})
        self.assertEqual(receipt, self.confirm(key=self.ledger.detail(self.group, receipt['id'])['request_key'],
                                                notes={self.asset: note}))

    def test_cart_checkout_carries_only_root_notes_to_receipt(self):
        cart = CheckoutCart(self.ledger)
        child = str(uuid4())
        self.client.assets[child] = {'id': child, 'name': 'Component', 'quantity': 1, 'archived': False,
                                     'parent': {'id': str(uuid4())}, 'entityType': {'isLocation': False},
                                     'fields': [{'name': 'Equipment condition', 'type': 'text', 'textValue': 'Ready'}]}
        self.entity['fields'].append({'name': 'Equipment kit manifest', 'type': 'text',
                                      'textValue': json.dumps({'version': 1, 'members': [child]})})
        saved = cart.save(self.group, self.user, [self.asset], 0, str(uuid4()), {self.asset: 'return clamp'})
        expanded = expand_cart_assets(self.client, [self.asset])
        receipt = self.confirm(assets=expanded, verified=expanded, kit_versions=manifest(self.client, self.asset)['versions'],
                              cart_context={'revision': saved['revision'], 'items': [self.asset], 'notes': saved['notes']})
        self.assertEqual(self.ledger.detail(self.group, receipt['id'])['context']['checkout_notes'],
                         {self.asset: 'return clamp'})
        consumed = cart.consume_completed_receipt(self.group, self.user, receipt['id'])
        self.assertEqual(consumed['consumed'], [self.asset])
        self.assertEqual(consumed['cart']['notes'], {})
        self.assertEqual(consumed['cart']['items'], [])
        with self.assertRaises(ValueError):
            self.confirm(assets=expanded, verified=expanded, kit_versions=manifest(self.client, self.asset)['versions'],
                         cart_context={'revision': saved['revision'], 'items': [self.asset],
                                       'notes': {child: 'wrong component'}})

    def test_legacy_cart_checkout_replay_keeps_original_intent_shape(self):
        key = str(uuid4())
        cart_context = {'revision': 4, 'items': [self.asset], 'original_items': [self.asset]}
        prior = self.ledger.begin(self.group, self.user, 'check_out', [self.asset], key,
                                  context={'checkout_cart': cart_context},
                                  intent={'checkout_cart': cart_context})
        self.ledger.complete(prior['id'])

        replay = self.confirm(key=key, cart_context=cart_context)

        self.assertEqual(replay, {'id': prior['id'], 'status': 'completed', 'action': 'check_out', 'count': 1})
        self.assertEqual(self.ledger.detail(self.group, prior['id'])['context']['checkout_cart'], cart_context)

    def test_kiosk_adapter_replays_empty_note_context_with_or_without_original_items(self):
        for include_original in (True, False):
            for include_empty_notes in (True, False):
                with self.subTest(include_original=include_original, include_empty_notes=include_empty_notes):
                    asset = str(uuid4())
                    entity = copy.deepcopy(self.entity)
                    entity['id'] = asset
                    self.client.assets[asset] = entity
                    saved = {'revision': 4, 'items': [asset]}
                    if include_empty_notes:
                        saved['notes'] = {}
                    saved = json.loads(json.dumps(saved))
                    context = checkout_cart_context(saved, [asset], include_original_items=include_original)
                    expected = {'revision': 4, 'items': [asset]}
                    if include_original:
                        expected['original_items'] = [asset]
                    self.assertEqual(context, expected)

                    key = str(uuid4())
                    prior = self.ledger.begin(self.group, self.user, 'check_out', [asset], key,
                                              context={'checkout_cart': context},
                                              intent={'checkout_cart': context})
                    self.ledger.complete(prior['id'])
                    replay = self.confirm(assets=[asset], key=key, cart_context=context)
                    self.assertEqual(replay['id'], prior['id'])

    def test_failed_checkout_note_does_not_create_operation_or_standalone_job(self):
        with self.assertRaises(ValueError):
            self.confirm(notes={self.asset: 'x' * 1001})
        self.assertEqual(self.ledger.unresolved(), [])
        with self.ledger.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM operations').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM native_jobs').fetchone()[0], 0)

    def test_checkout_note_limits_unicode_and_selected_ids(self):
        self.assertEqual(self.confirm(notes={self.asset: 'x' * 1000})['status'], 'completed')
        for key, value in [(self.asset, '\ud800'), (str(uuid4()), 'extra')]:
            with self.assertRaises(ValueError):
                self.confirm(notes={key: value})


if __name__=='__main__':unittest.main()
