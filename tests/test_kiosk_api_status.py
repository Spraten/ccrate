import pathlib
import unittest
import ast
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit,parse_qs
from uuid import UUID
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ops'))
import returns
from conditions import condition,checkout_blocker
from ledger import Conflict

class RouteFixture:
    def __init__(self,actor,generation,entities,custody=(),unresolved=(),members=None,stale=False):
        self.actor=actor;self.generation=generation;self.entities=entities;self.rows=custody;self.pending=unresolved;self.members=members or [actor];self.calls=0;self.stale=stale
    def snapshot(self):
        self.calls+=1
        return (self.actor,self.generation+(1 if self.stale and self.calls>1 else 0))
class FixtureLock:
    def __enter__(self):return self
    def __exit__(self,*args):return False
class FixtureClient:
    def __init__(self,fixture):self.fixture=fixture
    def call(self,path,*args,**kwargs):
        if path=='/api/v1/users/self':return {'item':{'defaultGroupId':'group'}}
        if path=='/api/v1/groups/members':return [{'id':m} for m in self.fixture.members]
        raise AssertionError(path)
    def entity(self,item):return self.fixture.entities[item]

def availability_handler():
    tree=ast.parse((ROOT/'deploy/kiosk-server.py').read_text())
    handler=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Handler')
    namespace={'BaseHTTPRequestHandler':BaseHTTPRequestHandler,'property':property,'urlsplit':urlsplit,'parse_qs':parse_qs,'NativeUUID':UUID,
      'ROOT':ROOT,'desktop_handle':lambda *a:False,'lock':FixtureLock(),'ledger':None,'Homebox':None,'returns':returns,
      'condition':condition,'checkout_blocker':checkout_blocker,'Conflict':Conflict,'sessions':None}
    exec(compile(ast.Module(body=[handler],type_ignores=[]),'<Handler>','exec'),namespace)
    class FixtureHandler(namespace['Handler']):
      @property
      def session(self):return self.fixture
    return FixtureHandler,namespace


class KioskApiStatusTests(unittest.TestCase):
    def test_handler_availability_contract_with_isolated_fixtures(self):
        from uuid import uuid4
        Handler,ns=availability_handler();actor=str(uuid4());held=str(uuid4());attention=str(uuid4());stock=str(uuid4());loc=str(uuid4())
        def entity(i,name='Item',state='Ready'):
            return {'id':i,'name':name,'quantity':1,'entityType':{'isLocation':False},'parent':{'id':loc},'fields':[{'name':'Equipment condition','type':'text','textValue':state}]}
        class Ledger:
            def __init__(self,rows=(),pending=()):self.rows=rows;self.pending=pending
            def custody(self,group):return list(self.rows)
            def unresolved(self):return list(self.pending)
        def get(path,fixture,ledger):
            ns['ledger']=ledger;ns['Homebox']=lambda root:FixtureClient(fixture)
            h=Handler.__new__(Handler);h.fixture=fixture;h.path=path;h.headers={};out=[];h.reply_json=lambda c,d:out.append((c,d));h.do_GET();return out[0]
        entities={held:entity(held,state='Broken'),attention:entity(attention,state='Needs Attention'),stock:entity(stock),loc:{'id':loc,'name':'Bench','quantity':1,'entityType':{'isLocation':True}}}
        f=RouteFixture(actor,4,entities,custody=[{'entity_id':held},{'entity_id':attention}]);status,data=get('/return/availability?ids='+held+','+attention+','+stock,f,Ledger([{'entity_id':held},{'entity_id':attention}]))
        self.assertEqual(status,200);self.assertEqual(set(data),{'items'});self.assertEqual([x['id'] for x in data['items']],[held,attention,stock])
        self.assertTrue(data['items'][0]['eligible']);self.assertEqual(data['items'][0]['condition'],'Broken');self.assertTrue(data['items'][1]['eligible']);self.assertEqual(data['items'][1]['condition'],'Needs Attention');self.assertEqual(data['items'][0]['location'],{'id':loc,'name':'Bench'})
        self.assertFalse(data['items'][2]['eligible']);self.assertIn('not currently checked out',data['items'][2]['reason'])
        self.assertFalse(any('borrower' in x or 'actor' in x for x in data['items']))
        status,data=get('/return/availability?ids='+held,RouteFixture(actor,4,entities),Ledger([{'entity_id':held}],[{'status':'pending'}]))
        self.assertFalse(data['items'][0]['eligible']);self.assertIn('staff review',data['items'][0]['reason'])
        for query in ('','x',''+held+','+held,','.join(str(uuid4()) for _ in range(51))):
            status,_=get('/return/availability?ids='+query,RouteFixture(actor,4,entities),Ledger())
            self.assertEqual(status,400,query)
        status,_=get('/return/availability?ids='+held,RouteFixture(None,4,entities),Ledger());self.assertEqual(status,401)
        status,data=get('/return/availability?ids='+held,RouteFixture(actor,4,entities,stale=True),Ledger([{'entity_id':held}]))
        self.assertEqual(status,409);self.assertIn('session changed',data['error'])
    def test_scoped_return_availability_does_not_expose_custody_rows(self):
        source=(ROOT/'deploy/kiosk-server.py').read_text()
        route=source[source.index("if urlsplit(self.path).path == '/return/availability':"):source.index("terminal_path=urlsplit(self.path)")]
        for token in ('self.session.snapshot()', 'ledger.custody(group)', 'item.get(\'entityType\',{}).get(\'isLocation\')', "item.get('quantity')!=1", 'returns.parent_id(item)', 'condition(item)', '1<=len(ids)<=50', "'items':rows"):
            self.assertIn(token,route)
        for token in ('ledger.unresolved()', "if not actor", 'len(ids)!=len(set(ids))', 'client.entity(item_id)', 'self.session.snapshot()!=(actor,generation)', "'Item is not currently checked out'", "'An operation needs staff review'"):
            self.assertIn(token,route)
        self.assertNotIn("'borrower'",route);self.assertNotIn('reply_json(200,ledger.custody',route)
        self.assertNotIn("'actor':",route)

    def test_return_availability_is_bound_and_selected_only(self):
        source=(ROOT/'deploy/kiosk-server.py').read_text()
        route=source[source.index("if urlsplit(self.path).path == '/return/availability':"):source.index('terminal_path=urlsplit(self.path)')]
        self.assertIn("if not actor",route);self.assertIn('parse_qs',route);self.assertIn('len(ids)!=len(set(ids))',route)
        self.assertIn("{'id':item_id,'eligible':reason is None,'reason':reason,'condition':condition(item),'location':location}",route)


if __name__ == '__main__':
    unittest.main()
