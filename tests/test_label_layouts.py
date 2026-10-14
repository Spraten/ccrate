import pathlib
import tempfile
import unittest
import base64
import io
import time
import sqlite3
from unittest.mock import patch
from PIL import Image
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'ops'))
from label_layouts import LabelLayouts, Conflict, _native_values


def document():
    return {'schemaVersion':1,'id':'draft','name':'Starter','page':{'widthMm':40,'heightMm':28,'orientation':'portrait','marginTopMm':0,'marginRightMm':0,'marginBottomMm':0,'marginLeftMm':0},'elements':[{'id':'qr','name':'Item QR','type':'qr','xMm':2,'yMm':4,'widthMm':19,'heightMm':19,'rotation':0,'locked':False,'visible':True,'content':'{{item_path}}','ecLevel':'M','color':'#000000','backgroundColor':'#ffffff'}],'guides':[],'variables':{}}


class LabelLayoutTests(unittest.TestCase):
    def test_legacy_native_item_without_short_code_renders_blank_fallback(self):
        name, asset, short_code, display_id, updated, warnings = _native_values({'id':'44444444-4444-4444-8444-444444444444','name':'Legacy','assetId':'A-1','updatedAt':'2026-10-07T12:00:00Z'})
        self.assertEqual((name, asset, short_code, display_id, updated), ('Legacy', 'A-1', '', '', '2026-10-07T12:00:00Z'))
        self.assertEqual(warnings, [])

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=LabelLayouts(pathlib.Path(self.tmp.name)/'private.db')
        self.group='11111111-1111-4111-8111-111111111111';self.other='22222222-2222-4222-8222-222222222222'
        self.actor='33333333-3333-4333-8333-333333333333'

    def tearDown(self): self.tmp.cleanup()

    def save(self,key='save-1',name='First',**extra):
        return self.store.save(self.group,self.actor,{'revision':0,'name':name,'profile':'supvan','document':document(),'request_key':key,**extra})

    def test_group_isolation_and_starters(self):
        saved=self.save(); self.assertIn(saved,self.store.list(self.group)); self.assertNotIn(saved,self.store.list(self.other))
        starters=[x['id'] for x in self.store.list(self.group) if x['id'].startswith('starter:')]
        self.assertEqual(len(starters),6)
        for starter in self.store.list(self.group):
            if starter['id'].startswith('starter:'):
                self.assertEqual(sum(e['type']=='qr' and e['visible'] for e in starter['document']['elements']),1)
                from label_layouts import validate_document
                validate_document(starter['document'],starter['profile'])
        compact=self.store.get(self.group,'starter:supvan:compact')['document']
        left=self.store.get(self.group,'starter:supvan:left')['document']
        self.assertNotEqual((compact['elements'][0]['xMm'],compact['elements'][0]['yMm']),(left['elements'][0]['xMm'],left['elements'][0]['yMm']))

    def test_dedupe_replays_original_result_and_rejects_changed_payload(self):
        first=self.save(); later=self.store.save(self.group,self.actor,{'id':first['id'],'revision':1,'name':'Later','profile':'supvan','document':document(),'request_key':'save-2'})
        self.assertEqual(self.save(),first)
        with self.assertRaises(Conflict): self.save(name='Changed')
        self.assertEqual(self.store.get(self.group,first['id'])['revision'],later['revision'])

    def test_duplicate_assigns_new_identity_and_revision_conflicts(self):
        first=self.save(); duplicate=self.store.save(self.group,self.actor,{'revision':0,'name':first['name'],'profile':first['profile'],'document':first['document'],'request_key':'duplicate'})
        self.assertNotEqual(first['id'],duplicate['id'])
        self.assertEqual({k:v for k,v in first['document'].items() if k!='id'}, {k:v for k,v in duplicate['document'].items() if k!='id'})
        with self.assertRaises(Conflict): self.store.save(self.group,self.actor,{'id':first['id'],'revision':0,'name':'Stale','profile':'supvan','document':document(),'request_key':'stale'})

    def test_drafts_never_issue_review_tickets(self):
        rendered_docs=[]
        self.store.renderer=lambda doc,profile:(rendered_docs.append(doc) or {'png':b'png','width':320,'height':224,'sha256':'a'*64,'warnings':['Text was shortened with an ellipsis.']})
        synthetic=self.store.preview(None,self.group,self.actor,{'mode':'synthetic','profile':'supvan','document':document(),'sample':{'item_name':'Demo','asset_code':'','short_code':'TMP-001','display_id':'BIN-D-GC-C-1-A17'}})
        draft=self.store.preview(FakeClient(),self.group,self.actor,{'mode':'item_draft','entity_id':'44444444-4444-4444-8444-444444444444','profile':'supvan','document':document()})
        self.assertNotIn('review_id',synthetic);self.assertNotIn('review_id',draft)
        self.assertEqual(rendered_docs[0]['variables']['short_code'],'TMP-001')
        self.assertEqual(rendered_docs[1]['variables']['short_code'],'DHP-001')
        self.assertEqual(rendered_docs[0]['variables']['display_id'],'BIN-D-GC-C-1-A17')
        self.assertEqual(rendered_docs[1]['variables']['display_id'],'BIN-D-GC-C-1-A17-U00000000000000000000000000000000')
        self.assertIn('Text was shortened with an ellipsis.',synthetic['warnings'])
        self.assertIn('Text was shortened with an ellipsis.',draft['warnings'])
        self.assertEqual(self.store.review(self.group,self.actor,'missing'),None)

    def test_reset_is_read_only_and_save_result_is_actor_scoped(self):
        self.assertEqual(self.store.save_result(self.group,self.actor,'nope'),None)
        first=self.save();self.assertEqual(self.store.save_result(self.group,self.actor,'save-1'),first)
        self.assertIsNone(self.store.save_result(self.group,self.other,'save-1'))

    def test_untrusted_document_rejects_font_urls_nan_and_heavy_images(self):
        for mutate in (
            lambda d:d['elements'].append({'id':'font','name':'Bad font','type':'text','xMm':1,'yMm':1,'widthMm':10,'heightMm':5,'rotation':0,'locked':False,'visible':True,'content':'X','fontSizePt':7,'fontWeight':400,'align':'left','color':'#000','fontFamily':'Arial'}),
            lambda d:d['elements'].append({'id':'remote','name':'Remote','type':'image','xMm':1,'yMm':1,'widthMm':5,'heightMm':5,'rotation':0,'locked':False,'visible':True,'src':'https://example.invalid/x.png'}),
            lambda d:d['elements'].append({'id':'nan','name':'NaN','type':'rect','xMm':float('nan'),'yMm':1,'widthMm':5,'heightMm':5,'rotation':0,'locked':False,'visible':True}),
        ):
            doc=document();mutate(doc)
            with self.assertRaises(ValueError): self.store.save(self.group,self.actor,{'revision':0,'name':'Bad','profile':'supvan','document':doc,'request_key':'bad-'+str(id(doc))})
        image=Image.new('RGB',(3001,4000),'white');stream=io.BytesIO();image.save(stream,format='PNG')
        doc=document();doc['elements'].append({'id':'heavy','name':'Heavy image','type':'image','xMm':1,'yMm':1,'widthMm':5,'heightMm':5,'rotation':0,'locked':False,'visible':True,'src':'data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode()})
        with self.assertRaisesRegex(ValueError,'pixel limits'):
            self.store.save(self.group,self.actor,{'revision':0,'name':'Heavy','profile':'supvan','document':doc,'request_key':'heavy-image'})

    def test_save_rejects_missing_type_fields_and_unsafe_qr_geometry(self):
        mutations=(
            lambda d:d['elements'][1].pop('content'),
            lambda d:d['elements'][0].update(widthMm=20),
            lambda d:d['elements'][0].update(widthMm=1,heightMm=1),
            lambda d:d['elements'][0].update(rotation=45),
            lambda d:d['elements'][0].update(ecLevel='BAD'),
            lambda d:d['elements'][0].update(ecLevel='BAD'),
            lambda d:d['page'].pop('orientation'),
        )
        for index,mutate in enumerate(mutations):
            doc=document()
            doc['elements'].append({'id':'name','name':'Item name','type':'text','xMm':23,'yMm':4,'widthMm':15,'heightMm':7,'rotation':0,'locked':False,'visible':True,'fontSizePt':7,'fontWeight':700,'align':'left','color':'#000000','fontFamily':'DejaVu Sans','content':'{{item_name}}'})
            mutate(doc)
            with self.subTest(index=index),self.assertRaises(ValueError):
                self.store.save(self.group,self.actor,{'revision':0,'name':'Bad schema','profile':'supvan','document':doc,'request_key':f'bad-schema-{index}'})
        doc=document();doc['variables']={'item_name':'Sensitive selected value','asset_code':'secret','short_code':'DHP-001','display_id':'BIN-D-GC-C-1-A17'}
        saved=self.store.save(self.group,self.actor,{'revision':0,'name':'Sanitized','profile':'supvan','document':doc,'request_key':'sanitized-samples'})
        self.assertEqual(saved['document']['variables']['item_name'],'Sample item')
        self.assertEqual(saved['document']['variables']['asset_code'],'')
        self.assertEqual(saved['document']['variables']['short_code'],'')
        self.assertEqual(saved['document']['variables']['display_id'],'')

    def test_save_accepts_a_supported_square_quarter_turn_qr(self):
        doc=document();doc['elements'][0]['rotation']=90
        saved=self.store.save(self.group,self.actor,{'revision':0,'name':'Rotated QR','profile':'supvan','document':doc,'request_key':'rotated-qr'})
        self.assertEqual(saved['document']['elements'][0]['rotation'],90)

    def test_storage_busy_returns_a_retryable_error(self):
        blocker=sqlite3.connect(self.store.path,timeout=0)
        blocker.execute('BEGIN IMMEDIATE')
        try:
            started=time.monotonic()
            with self.assertRaisesRegex(TimeoutError,'Label storage is busy'):
                self.save(key='sqlite-busy')
            self.assertLess(time.monotonic()-started,2.5)
        finally:
            blocker.rollback();blocker.close()

    def test_expired_draft_and_ticket_transaction_return_no_partial_result(self):
        fake={'now':0.0}
        self.store.renderer=lambda doc,profile:(fake.update(now=21.0) or {'png':b'png','width':320,'height':224,'sha256':'a'*64,'warnings':[]})
        with patch('label_layouts.time.monotonic',side_effect=lambda:fake['now']):
            with self.assertRaisesRegex(TimeoutError,'request budget'):
                self.store.preview(None,self.group,self.actor,{'mode':'synthetic','profile':'supvan','document':document(),'sample':{}})
        fake['now']=0.0
        with patch('label_layouts.time.monotonic',side_effect=lambda:fake['now']):
            with self.assertRaisesRegex(TimeoutError,'request budget'):
                self.store.preview(FakeClient(),self.group,self.actor,{'mode':'item_draft','entity_id':'44444444-4444-4444-8444-444444444444','profile':'supvan','document':document()})
        self.assertEqual(self.store.review(self.group,self.actor,'missing'),None)

        fake['now']=0.0
        self.store.renderer=lambda doc,profile:{'png':b'png','width':320,'height':224,'sha256':'a'*64,'warnings':[]}
        real_response=LabelLayouts._response
        def expiring_response(*args):
            fake['now']=20.1
            return real_response(*args)
        data={'mode':'item','entity_id':'44444444-4444-4444-8444-444444444444','template_id':'starter:supvan:left','template_revision':0}
        with patch('label_layouts.time.monotonic',side_effect=lambda:fake['now']),patch.object(self.store,'_response',side_effect=expiring_response):
            with self.assertRaisesRegex(TimeoutError,'request budget'):
                self.store.preview(FakeClient(),self.group,self.actor,data)
        with self.store._conn() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM reviews').fetchone()[0],0)

    def test_failed_batch_does_not_store_partial_reviews(self):
        calls=[]
        def renderer(doc,profile):
            calls.append(doc)
            if len(calls)==2:raise TimeoutError('slow renderer')
            return {'png':b'png','width':320,'height':224,'sha256':'a'*64,'warnings':[]}
        self.store.renderer=renderer
        data={'mode':'item','entity_ids':['44444444-4444-4444-8444-444444444444','55555555-5555-4555-8555-555555555555'],'template_id':'starter:supvan:left','template_revision':0}
        with self.assertRaisesRegex(TimeoutError,'slow renderer'): self.store.preview(FakeClient(),self.group,self.actor,data)
        with self.store._conn() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM reviews').fetchone()[0],0)

    def test_item_review_is_group_actor_scoped_and_freezes_bound_values(self):
        seen=[]
        def renderer(doc,profile):
            seen.append(doc)
            return {'png':b'canonical-png','width':320,'height':224,'sha256':'b'*64,'warnings':[]}
        self.store.renderer=renderer
        response=self.store.preview(FakeClient(),self.group,self.actor,{'mode':'item','entity_id':'44444444-4444-4444-8444-444444444444','template_id':'starter:supvan:left','template_revision':0})
        self.assertEqual(seen[0]['variables']['asset_code'],'')
        self.assertEqual(seen[0]['variables']['short_code'],'DHP-001')
        self.assertEqual(seen[0]['variables']['display_id'],'BIN-D-GC-C-1-A17-U00000000000000000000000000000000')
        self.assertEqual(seen[0]['elements'][0]['content'],'/item/44444444-4444-4444-8444-444444444444')
        ticket=self.store.review(self.group,self.actor,response['review_id'])
        self.assertEqual(ticket['png'],b'canonical-png')
        self.assertEqual(ticket['item_display_id'],'BIN-D-GC-C-1-A17-U00000000000000000000000000000000')
        self.assertIsNone(self.store.review(self.other,self.actor,response['review_id']))
        self.store.attach_review(self.group,self.actor,response['review_id'],'job-1')
        self.assertEqual(self.store.review(self.group,self.actor,response['review_id'])['attached_job'],'job-1')
        self.store.resolve_review(self.group,response['review_id'])
        self.assertIsNone(self.store.review(self.group,self.actor,response['review_id']))

    def test_item_review_exposes_custom_letter_label_dimensions(self):
        letter=document();letter['page'].update(widthMm=210,heightMm=297)
        saved=self.store.save(self.group,self.actor,{'revision':0,'name':'Letter','profile':'letter','document':letter,'request_key':'letter-save'})
        self.store.renderer=lambda doc,profile:{'png':b'canonical-png','width':709,'height':1003,'sha256':'c'*64,'warnings':[]}
        response=self.store.preview(FakeClient(),self.group,self.actor,{'mode':'item','entity_id':'44444444-4444-4444-8444-444444444444','template_id':saved['id'],'template_revision':saved['revision']})
        self.assertEqual(response['profile'],'letter')
        self.assertEqual(response['label_mm'],[210,297])

    def test_review_expiry_retains_attached_tickets_and_survives_restart(self):
        self.store.renderer=lambda doc,profile:{'png':b'canonical-png','width':320,'height':224,'sha256':'b'*64,'warnings':[]}
        data={'mode':'item','entity_id':'44444444-4444-4444-8444-444444444444','template_id':'starter:supvan:left','template_revision':0}
        expiring=self.store.preview(FakeClient(),self.group,self.actor,data)
        retained=self.store.preview(FakeClient(),self.group,self.actor,{**data,'entity_id':'55555555-5555-4555-8555-555555555555'})
        self.store.attach_review(self.group,self.actor,retained['review_id'],'job-keep')
        with self.store._conn() as db:
            db.execute('UPDATE reviews SET created=? WHERE id IN (?,?)',(time.time()-86401,expiring['review_id'],retained['review_id']))
        restarted=LabelLayouts(self.store.path,renderer=self.store.renderer)
        self.assertIsNone(restarted.review(self.group,self.actor,expiring['review_id']))
        kept=restarted.review(self.group,self.actor,retained['review_id'])
        self.assertEqual(kept['png'],b'canonical-png')
        self.assertEqual(kept['attached_job'],'job-keep')


class FakeClient:
    def entity(self,key): return {'id':key,'name':'Sample','assetId':'','shortCode':'DHP-001','displayId':'BIN-D-GC-C-1-A17-U00000000000000000000000000000000','updatedAt':'2026-10-07T12:00:00Z'}


if __name__=='__main__': unittest.main()
