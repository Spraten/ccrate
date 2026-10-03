import json,unittest
from uuid import uuid4
from kits import FIELD,manifest,members,validate_checkout
from ledger import Conflict
class KitsTests(unittest.TestCase):
    def setUp(self):
        self.items={}
        for name in ['root','nested','battery','tool']:
            key=str(uuid4());self.items[name]={'id':key,'name':name,'quantity':1,'entityType':{'isLocation':False},'fields':[{'name':'Equipment condition','type':'text','textValue':'Ready'}]}
        outer=self
        class Client:
            def entity(self,key):return next(e for e in outer.items.values() if e['id']==key)
        self.client=Client()
    def link(self,name,children):self.items[name]['fields'].append({'name':FIELD,'type':'text','textValue':json.dumps({'version':1,'members':[self.items[c]['id'] for c in children]})})
    def test_nested_flattened_once(self):
        self.link('root',['nested','tool']);self.link('nested',['battery','tool']);data=manifest(self.client,self.items['root']['id']);self.assertEqual(len(data['entities']),4)
    def test_cycle_rejected(self):
        self.link('root',['nested']);self.link('nested',['root'])
        with self.assertRaises(ValueError):manifest(self.client,self.items['root']['id'])
    def test_location_component_rejected(self):
        self.link('root',['battery']);self.items['battery']['entityType']['isLocation']=True
        with self.assertRaises(ValueError):manifest(self.client,self.items['root']['id'])
    def test_missing_selection_rejected(self):
        self.link('root',['battery'])
        with self.assertRaises(Conflict):validate_checkout(self.client,[self.items['root']],[],{})
    def test_unscanned_component_rejected(self):
        self.link('root',['battery']);data=manifest(self.client,self.items['root']['id'])
        with self.assertRaises(Conflict):validate_checkout(self.client,data['entities'],[self.items['root']['id']],data['versions'])
    def test_changed_manifest_rejected(self):
        self.link('root',['battery']);data=manifest(self.client,self.items['root']['id'])
        with self.assertRaises(Conflict):validate_checkout(self.client,data['entities'],[e['id'] for e in data['entities']],{})
    def test_verified_complete_allowed(self):
        self.link('root',['battery']);data=manifest(self.client,self.items['root']['id']);validate_checkout(self.client,data['entities'],[e['id'] for e in data['entities']],data['versions'])
    def test_future_format_rejected(self):
        self.items['root']['fields'].append({'name':FIELD,'type':'text','textValue':'{"version":2,"members":[]}'})
        with self.assertRaises(ValueError):members(self.items['root'])
