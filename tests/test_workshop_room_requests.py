import copy
import hashlib
import json
import pathlib
import sys
import unittest
from contextlib import contextmanager
from uuid import uuid4

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'ops'))
from ledger import Conflict
from ledger import Ledger
from native_jobs import NativeJobs
import desktop_api
from workshop import Workshop
from workshop_room_fixtures import RoomFixture


class RoomRequestTests(unittest.TestCase):
    def setUp(self):
        self.f = RoomFixture()
        self.addCleanup(self.f.close)

    @staticmethod
    def journal_row(ledger,group,key):
        with ledger.connection() as db:
            row=db.execute('SELECT * FROM desktop_requests WHERE group_id=? AND request_key=?',(group,key)).fetchone()
        return dict(row) if row else None

    def test_first_save_migrates_once_and_rejects_old_writer(self):
        f = self.f
        f.seed_legacy()
        old = f.store.get(f.group)
        legacy_document = copy.deepcopy(old['document'])
        native_before=copy.deepcopy(f.client.nodes)
        request = f.request(legacy_document, old['revision'])
        saved = f.store.save(f.client, f.group, request, actor_id=f.actor)
        self.assertEqual(saved['revision'], 8)
        self.assertEqual(saved['stored_schema_version'], 2)
        self.assertEqual(saved['document'], legacy_document)
        reopened=Workshop(f.store.path)
        self.assertEqual(reopened.get(f.group)['document'],legacy_document)
        self.assertEqual(reopened.save(f.client,f.group,request,actor_id=f.actor),saved)
        self.assertEqual(reopened.get(f.group)['revision'],8)
        with self.assertRaises(ValueError): f.store.save(f.client, f.group, {'revision': 8, 'layout': f.legacy}, actor_id=f.actor)
        self.assertEqual(f.store.get(f.group), saved)
        self.assertEqual(f.client.writes,[])
        for key,row in native_before.items():
            self.assertEqual(f.client.nodes[key]['fields'],row['fields'])
            self.assertEqual(f.client.nodes[key]['attachments'],row['attachments'])
            self.assertEqual(f.client.nodes[key]['history'],row['history'])

    def test_two_sessions_and_key_reuse_conflict(self):
        f = self.f
        req = f.request()
        saved = f.store.save(f.client, f.group, req, actor_id=f.actor)
        self.assertEqual(f.store.save(f.client, f.group, req, actor_id=f.actor), saved)
        with self.assertRaises(Conflict): f.store.save(f.client, f.group, req, actor_id=str(uuid4()))
        changed = copy.deepcopy(req); changed['document']['rooms'][0]['name'] = 'Changed'
        with self.assertRaises(Conflict): f.store.save(f.client, f.group, changed, actor_id=f.actor)
        with self.assertRaises(Conflict): f.store.save(f.client, f.group, f.request(), actor_id=f.actor)

    def test_receipt_recovers_interrupted_generic_journal(self):
        f = self.f
        ledger = Ledger(f.path.parent / 'ledger.db')
        deps = {'ledger': ledger, 'native_jobs': NativeJobs(ledger), 'workshop': f.store}
        ctx = {'group': f.group, 'actor': f.actor}
        request = f.request()
        original = ledger.transaction
        count = [0]
        @contextmanager
        def fail_completion(*args, **kwargs):
            count[0] += 1
            if count[0] == 3: raise OSError('injected generic journal completion failure')
            with original(*args, **kwargs) as db: yield db
        ledger.transaction = fail_completion
        with self.assertRaises(OSError):
            desktop_api.once(ctx, deps, 'workshop/save', request,
                             lambda: f.store.save(f.client, f.group, request, actor_id=f.actor))
        self.assertEqual(f.store.get(f.group)['revision'], 1)
        reopened=Ledger(ledger.path);deps['ledger']=reopened;deps['workshop']=Workshop(f.store.path)
        calls=[]
        replay=desktop_api.once(ctx,deps,'workshop/save',request,lambda:calls.append('perform'))
        self.assertEqual(replay,deps['workshop'].get(f.group));self.assertEqual(calls,[])
        self.assertEqual(desktop_api.request_row(reopened,f.group,request['request_key'])['status'],'completed')
        self.assertEqual(desktop_api.operation_status(ctx, deps, {'request_key': request['request_key']}),
                         {'status':'completed','action':'workshop/save','result':f.store.get(f.group)})
        self.assertEqual(f.store.save(f.client, f.group, request, actor_id=f.actor), f.store.get(f.group))
        self.assertEqual(f.client.writes, [])

    def test_root_mismatch_survives_edit_and_can_be_repaired(self):
        f = self.f
        document = copy.deepcopy(f.document)
        document['rooms'][0]['objects'] = [{'id':f.drawing,'kind':'Rack','name':'Rack','x':0,'y':0,
            'width':1,'height':1,'rotation':0,'location_id':f.shelf}]
        native_before=copy.deepcopy(f.client.nodes)
        initial = f.store.save(f.client, f.group, f.request(document), actor_id=f.actor)
        f.move_shelf_outside_root()
        changed = copy.deepcopy(initial['document'])
        changed['rooms'][0]['name'] = 'Unrelated edit'
        entities=f.client.entities
        f.client.entities=lambda *_: (_ for _ in ()).throw(OSError('native inventory unavailable'))
        saved = f.store.save(f.client, f.group, f.request(changed, initial['revision']), actor_id=f.actor)
        f.client.entities=entities
        self.assertEqual(saved['document']['rooms'][0]['location_id'], f.root)
        self.assertEqual(saved['document']['rooms'][0]['objects'][0]['location_id'], f.shelf)
        f.client.nodes[f.shelf]['parent']={'id':f.compatible_root}
        repaired = f.repair_request()
        self.assertEqual(f.store.save(f.client, f.group, repaired, actor_id=f.actor)['document']['rooms'][0]['location_id'], f.compatible_root)
        self.assertEqual(f.client.writes, [])
        for key,row in native_before.items():
            for field in ('fields','attachments','history'):
                self.assertEqual(f.client.nodes[key][field],row[field])

    def test_new_root_links_require_active_collection_locations(self):
        f = self.f
        request = f.request()
        f.client.nodes[f.root]['archived'] = True
        with self.assertRaises(ValueError): f.store.save(f.client, f.group, request, actor_id=f.actor)
        self.assertEqual(f.store.get(f.group)['revision'], 0)
        f.client.nodes[f.root]['archived'] = False
        incompatible=copy.deepcopy(f.document)
        incompatible['rooms'][0]['objects']=[{'id':f.drawing,'kind':'Rack','name':'Rack','x':0,'y':0,
            'width':1,'height':1,'rotation':0,'location_id':f.shelf}]
        f.client.nodes[f.shelf]['parent']={'id':f.compatible_root}
        with self.assertRaises(ValueError): f.store.save(f.client,f.group,f.request(incompatible),actor_id=f.actor)
        mixed=str(uuid4())
        f.client.nodes[mixed]={'id':mixed,'name':'Mixed ancestry item','archived':False,'entityType':{'isLocation':False},
                               'parent':{'id':f.root},'fields':[],'attachments':[],'history':[]}
        f.client.nodes[f.shelf]['parent']={'id':mixed}
        f.client.nodes[f.root]['parent']={'id':f.shelf}
        with self.assertRaises(ValueError): f.store.save(f.client,f.group,f.request(),actor_id=f.actor)
        self.assertEqual(f.store.get(f.group)['revision'], 0)

    def test_receipt_insert_failure_rolls_back_plan_revision(self):
        f = self.f
        import sqlite3
        db = sqlite3.connect(f.path)
        db.execute("CREATE TRIGGER fail_receipt BEFORE INSERT ON workshop_save_receipts BEGIN SELECT RAISE(ABORT,'injected receipt failure'); END")
        db.commit(); db.close()
        with self.assertRaises(sqlite3.IntegrityError): f.store.save(f.client, f.group, f.request(), actor_id=f.actor)
        self.assertEqual(f.store.get(f.group)['revision'], 0)
        db = sqlite3.connect(f.path); db.execute('DROP TRIGGER fail_receipt'); db.commit(); db.close()

    def test_changed_native_link_is_revalidated_before_receipt_commit(self):
        f=self.f
        document=copy.deepcopy(f.document)
        document['rooms'][0]['objects']=[{'id':f.drawing,'kind':'Rack','name':'Rack','x':0,'y':0,
            'width':1,'height':1,'rotation':0,'location_id':None}]
        first=f.store.save(f.client,f.group,f.request(document),actor_id=f.actor)
        changed=copy.deepcopy(first['document'])
        changed['rooms'][0]['objects'][0]['location_id']=f.shelf
        request=f.request(changed,first['revision'])
        validate=f.store.validate_save
        def move_after_preflight(client,group,data):
            result=validate(client,group,data)
            f.client.nodes[f.shelf]['parent']=None
            return result
        f.store.validate_save=move_after_preflight
        with self.assertRaises(ValueError):f.store.save(f.client,f.group,request,actor_id=f.actor)
        f.store.validate_save=validate
        self.assertEqual(f.store.get(f.group)['revision'],first['revision'])
        self.assertEqual(f.store.save_status(f.group,request['request_key'],actor_id=f.actor),{'status':'not_started'})

    def test_valid_location_item_location_chain_saves_and_reopens(self):
        f=self.f
        item=str(uuid4())
        f.client.nodes[item]={'id':item,'name':'Box','archived':False,'entityType':{'isLocation':False},
                              'parent':{'id':f.root},'fields':[],'attachments':[],'history':[]}
        f.client.nodes[f.shelf]['parent']={'id':item}
        document=copy.deepcopy(f.document)
        document['rooms'][0]['objects']=[{'id':f.drawing,'kind':'Rack','name':'Rack','x':0,'y':0,
            'width':1,'height':1,'rotation':0,'location_id':f.shelf}]
        saved=f.store.save(f.client,f.group,f.request(document),actor_id=f.actor)
        self.assertEqual(Workshop(f.store.path).get(f.group),saved)

    def test_changed_links_validate_complete_mixed_ancestry(self):
        f=self.f
        foreign=str(uuid4())
        f.client.nodes[foreign]={'id':foreign,'name':'Out-of-catalog parent','archived':False,
                                 'entityType':{'isLocation':False},'parent':None,'fields':[],'attachments':[],'history':[]}
        list_entities=f.client.entities
        f.client.entities=lambda locations=False:[node for node in list_entities(locations) if node['id']!=foreign]
        for parent in (f.shelf,str(uuid4()),foreign):
            f.client.nodes[f.shelf]['parent']={'id':parent}
            document=copy.deepcopy(f.document)
            document['rooms'][0]['location_id']=None
            document['rooms'][0]['objects']=[{'id':f.drawing,'kind':'Rack','name':'Rack','x':0,'y':0,
                'width':1,'height':1,'rotation':0,'location_id':f.shelf}]
            with self.assertRaises(ValueError):f.store.save(f.client,f.group,f.request(document),actor_id=f.actor)
        f.client.nodes[f.shelf]['parent']={'id':f.root}
        document=copy.deepcopy(f.document)
        document['rooms'][0]['objects']=[{'id':f.drawing,'kind':'Rack','name':'Rack','x':0,'y':0,
            'width':1,'height':1,'rotation':0,'location_id':f.shelf}]
        saved=f.store.save(f.client,f.group,f.request(document),actor_id=f.actor)
        f.client.nodes[f.root]['parent']={'id':f.shelf}
        changed=copy.deepcopy(saved['document']);changed['rooms'][0]['objects'][0]['location_id']=None
        with self.assertRaises(ValueError):f.store.save(f.client,f.group,f.request(changed,saved['revision']),actor_id=f.actor)

    def test_generic_save_intent_is_bounded_but_identifies_rooms(self):
        f=self.f;ledger=Ledger(f.path.parent/'ledger.db')
        deps={'ledger':ledger,'native_jobs':NativeJobs(ledger),'workshop':f.store}
        request=f.request()
        desktop_api.once({'group':f.group,'actor':f.actor},deps,'workshop/save',request,
                         lambda:f.store.save(f.client,f.group,request,actor_id=f.actor))
        with ledger.connection() as db:
            row=db.execute('SELECT intent FROM desktop_requests WHERE request_key=?',(request['request_key'],)).fetchone()
        intent=json.loads(row['intent'])
        self.assertEqual(intent['room_summaries'],[{'id':f.room,'name':'Plan','object_count':0}])
        canonical=json.dumps(request['document'],sort_keys=True,separators=(',',':'))
        self.assertEqual(intent['document_digest'],hashlib.sha256(canonical.encode()).hexdigest())
        self.assertNotIn('objects',intent)

    def test_status_does_not_reconcile_a_different_generic_action(self):
        f=self.f;ledger=Ledger(f.path.parent/'ledger.db')
        deps={'ledger':ledger,'native_jobs':NativeJobs(ledger),'workshop':f.store}
        request=f.request();f.store.save(f.client,f.group,request,actor_id=f.actor)
        unrelated={'request_key':request['request_key'],'uses':1}
        with self.assertRaises(OSError):
            desktop_api.once({'group':f.group,'actor':f.actor},deps,'invitation/create',unrelated,
                             lambda:(_ for _ in ()).throw(OSError('uncertain invitation')))
        before=self.journal_row(ledger,f.group,request['request_key'])
        with self.assertRaises(Conflict):
            desktop_api.once({'group':f.group,'actor':f.actor},deps,'workshop/save',request,
                             lambda:(_ for _ in ()).throw(AssertionError('wrong-family replay performed')))
        self.assertEqual(self.journal_row(ledger,f.group,request['request_key']),before)
        status=desktop_api.operation_status({'group':f.group,'actor':f.actor},deps,{'request_key':request['request_key']})
        after=self.journal_row(ledger,f.group,request['request_key'])
        self.assertEqual(status,{'id':before['id'],'status':'review','action':'invitation/create','desktop_job':True,'result':None})
        self.assertEqual(after,before)

    def test_status_rejects_receipt_actor_or_intent_mismatch_without_reconciliation(self):
        f=self.f;ledger=Ledger(f.path.parent/'ledger.db')
        deps={'ledger':ledger,'native_jobs':NativeJobs(ledger),'workshop':f.store}
        for actor_mismatch in (True,False):
            request=f.request(revision=f.store.get(f.group)['revision'])
            with self.assertRaises(OSError):
                desktop_api.once({'group':f.group,'actor':f.actor},deps,'workshop/save',request,
                                 lambda:(_ for _ in ()).throw(OSError('uncertain save')))
            receipt_actor=str(uuid4()) if actor_mismatch else f.actor
            receipt_request=copy.deepcopy(request)
            if not actor_mismatch:receipt_request['document']['rooms'][0]['name']='Different intent'
            f.store.save(f.client,f.group,receipt_request,actor_id=receipt_actor)
            before=self.journal_row(ledger,f.group,request['request_key'])
            with self.assertRaises(Conflict):
                desktop_api.once({'group':f.group,'actor':f.actor},deps,'workshop/save',request,
                                 lambda:(_ for _ in ()).throw(AssertionError('mismatched receipt replay performed')))
            self.assertEqual(self.journal_row(ledger,f.group,request['request_key']),before)
            with self.assertRaises(Conflict):
                desktop_api.operation_status({'group':f.group,'actor':f.actor},deps,{'request_key':request['request_key']})
            self.assertEqual(self.journal_row(ledger,f.group,request['request_key']),before)


if __name__ == '__main__': unittest.main()
