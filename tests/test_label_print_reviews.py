import hashlib,io,json,pathlib,tempfile,unittest
from uuid import uuid4
from unittest.mock import patch
from PIL import Image
from ledger import Conflict,Ledger
from native_jobs import NativeJobs
from label_layouts import LabelLayouts
import labels


class Client:
    def __init__(self,item):self.item=item
    def entity(self,_):return dict(self.item)


class Layouts:
    def __init__(self,group,actor,item,changed=False):
        self.group,self.actor,self.item=group,actor,item;self.attached=None;self.resolved=False
        self.png=io.BytesIO();Image.new('L',(320,224),255).save(self.png,format='PNG');self.png=self.png.getvalue()
        self.doc={'id':str(uuid4()),'profile':'supvan'};self.fail_cleanup=False
        self.meta={'review_id':str(uuid4()),'template_id':str(uuid4()),'template_revision':1,'template_hash':hashlib.sha256(json.dumps(self.doc,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest(),'sha256':hashlib.sha256(self.png).hexdigest(),'profile':'supvan','label_mm':[40,28],'dpi':203.2,'width':320,'height':224,'item_id':item,'item_updated_at':'v1','item_display_id':'BIN-D-GC-C-1-A17-U1234567890ABCDEF1234567890ABCDEF','png':self.png,'actor_id':actor,'attached_job':None}
    def review(self,group,actor,review):return dict(self.meta) if (group,actor,review)==(self.group,self.actor,self.meta['review_id']) and not self.resolved else None
    def get(self,group,template):return {'revision':1,'document':self.doc}
    def attach_review(self,g,a,r,j):self.attached=j;self.meta['attached_job']=j
    def resolve_review(self,g,r):
        if self.fail_cleanup:raise OSError('fixture cleanup failure')
        self.resolved=True


class PrintReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.ledger=Ledger(pathlib.Path(self.temp.name)/'ledger.db');self.jobs=NativeJobs(self.ledger)
        self.group,self.actor,self.item,self.key=[str(uuid4()) for _ in range(4)]
        self.layouts=Layouts(self.group,self.actor,self.item);self.sent=[]
        self.client=Client({'id':self.item,'name':'Drill','updatedAt':'v1','displayId':self.layouts.meta['item_display_id']})
    def tearDown(self):self.temp.cleanup()
    def send(self,*args,**kwargs):self.sent.append(kwargs['input']);return type('Result',(),{'stdout':b'{"status":"printed"}'})()
    def print_once(self):
        with patch.object(labels,'probe',return_value={'width_mm':40,'height_mm':30}),patch.object(labels,'printer_path',return_value='/dev/fixture'),patch.object(labels.subprocess,'run',side_effect=self.send):
            return labels.print_label(self.client,self.jobs,self.group,self.actor,self.key,self.item,layouts=self.layouts,review_id=self.layouts.meta['review_id'])
    def test_confirmed_print_sends_frozen_png_bytes_once_and_replays(self):
        first=self.print_once();second=self.print_once()
        with Image.open(io.BytesIO(self.layouts.png)) as image:image.load();expected=image.tobytes()
        self.assertEqual(self.sent,[expected]);self.assertEqual(first['id'],second['id']);self.assertTrue(self.layouts.resolved)
    def test_changed_native_item_is_rejected_before_send(self):
        self.client.item['updatedAt']='v2'
        with self.assertRaises(Conflict):self.print_once()
        self.assertEqual(self.sent,[])
    def test_changed_ancestor_display_id_is_rejected_before_send(self):
        self.client.item['displayId']='DRILL-RELOCATED-A17-U1234567890ABCDEF1234567890ABCDEF'
        with self.assertRaises(Conflict):self.print_once()
        self.assertEqual(self.sent,[])
    def test_foreign_ticket_rejection_does_not_purge_another_actors_png(self):
        other=str(uuid4())
        with self.assertRaises(ValueError):
            with patch.object(labels,'probe',return_value={'width_mm':40,'height_mm':30}):
                labels.print_label(self.client,self.jobs,self.group,other,self.key,self.item,layouts=self.layouts,review_id=self.layouts.meta['review_id'])
        self.assertFalse(self.layouts.resolved);self.assertTrue(self.layouts.png)
    def test_cross_key_unresolved_item_does_not_purge_current_review(self):
        self.jobs.prepare(self.group,self.actor,'print_label',str(uuid4()),{'entity_id':self.item,'review_id':str(uuid4())})
        with self.assertRaises(Conflict):self.print_once()
        self.assertFalse(self.layouts.resolved);self.assertTrue(self.layouts.png)
    def test_interrupted_prepared_key_is_never_resumed(self):
        self.jobs.prepare(self.group,self.actor,'print_label',self.key,{'entity_id':self.item,'review_id':self.layouts.meta['review_id']})
        with self.assertRaises(Conflict):self.print_once()
        self.assertEqual(self.sent,[]);self.assertFalse(self.layouts.resolved)
    def test_attached_prepared_restart_does_not_send_or_purge_ticket(self):
        job=self.jobs.prepare(self.group,self.actor,'print_label',self.key,{'entity_id':self.item,'review_id':self.layouts.meta['review_id']})
        self.layouts.attach_review(self.group,self.actor,self.layouts.meta['review_id'],job['id'])
        with self.assertRaises(Conflict):self.print_once()
        self.assertEqual(self.sent,[]);self.assertFalse(self.layouts.resolved);self.assertEqual(self.layouts.meta['attached_job'],job['id'])
    def test_atomic_sent_restart_does_not_send_or_purge_ticket(self):
        job=self.jobs.prepare(self.group,self.actor,'print_label',self.key,{'entity_id':self.item,'review_id':self.layouts.meta['review_id']})
        self.layouts.attach_review(self.group,self.actor,self.layouts.meta['review_id'],job['id'])
        metadata={key:self.layouts.meta[key] for key in ('review_id','template_id','template_revision','template_hash','sha256','profile','label_mm','dpi','width','height')}
        self.jobs.sent_print(self.group,job['id'],self.item,metadata)
        with self.assertRaises(Conflict):self.print_once()
        self.assertEqual(self.sent,[]);self.assertFalse(self.layouts.resolved);self.assertEqual(self.jobs.detail(self.group,job['id'])['status'],'sent')
    def test_started_prepared_print_cannot_be_cancelled_with_uppercase_job_id(self):
        job=self.jobs.prepare(self.group,self.actor,'print_label',self.key,{'entity_id':self.item,'review_id':self.layouts.meta['review_id']})
        self.layouts.attach_review(self.group,self.actor,self.layouts.meta['review_id'],job['id'])
        with self.ledger.transaction() as db:self.jobs.event(db,job['id'],'native_write_started',{})
        with self.assertRaises(Conflict):labels.recover_print(self.client,self.jobs,self.group,job['id'].upper(),'cancel',layouts=self.layouts)
        self.assertEqual(self.jobs.detail(self.group,job['id'])['status'],'prepared')
        self.assertFalse(self.layouts.resolved);self.assertTrue(self.layouts.png);self.assertEqual(self.sent,[])
    def test_legacy_sent_before_bind_requires_explicit_ack_and_never_prints(self):
        job=self.jobs.prepare(self.group,self.actor,'print_label',self.key,{'entity_id':self.item})
        self.jobs.sent(self.group,job['id'])
        with patch.object(labels.subprocess,'run') as printer:
            result=labels.recover_print(self.client,self.jobs,self.group,job['id'].upper(),'complete',layouts=self.layouts)
            printer.assert_not_called()
        self.assertEqual(result,{'id':job['id'],'status':'completed','entity_id':self.item})
        self.assertEqual(self.jobs.detail(self.group,job['id'])['result_id'],self.item)
        self.assertFalse(self.layouts.resolved)
    def test_completed_truth_survives_ticket_cleanup_failure_and_replay(self):
        self.layouts.fail_cleanup=True
        first=self.print_once();second=self.print_once()
        self.assertEqual(first['status'],second['status']);self.assertEqual(len(self.sent),1)
        self.assertEqual(self.jobs.detail(self.group,first['id'])['status'],'completed')
    def test_recovery_cancel_does_not_resolve_ticket_attached_elsewhere(self):
        job=self.jobs.prepare(self.group,self.actor,'print_label',self.key,{'entity_id':self.item,'review_id':self.layouts.meta['review_id']})
        self.layouts.meta['attached_job']=str(uuid4())
        result=labels.recover_print(self.client,self.jobs,self.group,job['id'],'cancel',layouts=self.layouts)
        self.assertEqual(result['status'],'cancelled');self.assertFalse(self.layouts.resolved)
    def test_restart_reconciliation_purges_only_a_resolved_job_attachment(self):
        store=LabelLayouts(pathlib.Path(self.temp.name)/'layouts.db');job=self.jobs.prepare(self.group,self.actor,'print_label',self.key,{'entity_id':self.item,'review_id':self.layouts.meta['review_id']})
        metadata={key:self.layouts.meta[key] for key in ('review_id','template_id','template_revision','template_hash','sha256','profile','label_mm','dpi','width','height')}
        self.jobs.sent_print(self.group,job['id'],self.item,metadata);self.jobs.complete(self.group,job['id'])
        with store._conn() as db:
            db.execute('INSERT INTO reviews(id,group_id,actor_id,created,attached_job,resolved,metadata,png) VALUES(?,?,?,?,?,0,?,?)',(self.layouts.meta['review_id'],self.group,self.actor,1,job['id'],json.dumps({'item_id':self.item}),self.layouts.png))
        store.reconcile_reviews(self.group,self.jobs)
        self.assertIsNone(store.review(self.group,self.actor,self.layouts.meta['review_id']))
        job2=self.jobs.prepare(self.group,self.actor,'print_label',str(uuid4()),{'entity_id':self.item,'review_id':str(uuid4())})
        with store._conn() as db:db.execute('INSERT INTO reviews(id,group_id,actor_id,created,attached_job,resolved,metadata,png) VALUES(?,?,?,?,?,0,?,?)',(str(uuid4()),self.group,self.actor,1,job2['id'],'{}',self.layouts.png))
        store.reconcile_reviews(self.group,self.jobs)
        with store._conn() as db:self.assertEqual(db.execute('SELECT count(*) FROM reviews WHERE attached_job=? AND resolved=0',(job2['id'],)).fetchone()[0],1)


class LegacyRasterReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();root=pathlib.Path(self.temp.name)
        self.ledger=Ledger(root/'ledger.db');self.jobs=NativeJobs(self.ledger);self.layouts=LabelLayouts(root/'layouts.db')
        self.group,self.actor,self.item,self.key=[str(uuid4()) for _ in range(4)]
        self.client=Client({'id':self.item,'name':'Long multiword storage location','updatedAt':'v1','isLocation':True})
    def tearDown(self):self.temp.cleanup()
    def review_legacy_location(self):
        image=Image.new('L',(320,208),255)
        with patch.object(labels,'render',return_value=(image,'location-code')) as render,patch.object(labels,'probe',side_effect=AssertionError('preview must not require a printer')) as probe:
            preview=labels.preview(self.client,self.item,layouts=self.layouts,group=self.group,actor=self.actor)
        probe.assert_not_called();render.assert_called_once_with(self.client.item,40,28)
        return image,preview
    def test_legacy_location_preview_works_offline_at_fixed_supvan_dimensions(self):
        image,preview=self.review_legacy_location()
        self.assertEqual((preview['width'],preview['height']),(320,208))
        self.assertIn('review_id',preview)
    def test_stock_change_after_legacy_review_requires_a_fresh_preview(self):
        image,preview=self.review_legacy_location();sent=[]
        def print_once(*args,**kwargs):
            sent.append(kwargs['input']);return type('Result',(),{'stdout':b'{"status":"printed"}'})()
        with patch.object(labels,'render',side_effect=AssertionError('print must use the reviewed raster')),patch.object(labels,'probe',return_value={'width_mm':40,'height_mm':30}),patch.object(labels,'printer_path',return_value='/dev/fixture'),patch.object(labels.subprocess,'run',side_effect=print_once):
            with self.assertRaisesRegex(ValueError,'40 x 28 mm SUPVAN stock'):
                labels.print_label(self.client,self.jobs,self.group,self.actor,self.key,self.item,layouts=self.layouts,review_id=preview['review_id'])
        self.assertEqual(sent,[])
        with patch.object(labels,'probe',return_value={'width_mm':40,'height_mm':28}),patch.object(labels,'printer_path',return_value='/dev/fixture'),patch.object(labels.subprocess,'run',side_effect=print_once) as printer:
            with self.assertRaisesRegex(ValueError,'missing, expired'):
                labels.print_label(self.client,self.jobs,self.group,self.actor,str(uuid4()),self.item,layouts=self.layouts,review_id=preview['review_id'])
        printer.assert_not_called()
    def test_legacy_location_print_sends_exact_reviewed_raster(self):
        image,preview=self.review_legacy_location();sent=[]
        def print_once(*args,**kwargs):sent.append(kwargs['input']);return type('Result',(),{'stdout':b'{"status":"printed"}'})()
        with patch.object(labels,'render',side_effect=AssertionError('print must use the reviewed raster')),patch.object(labels,'probe',return_value={'width_mm':40,'height_mm':28}),patch.object(labels,'printer_path',return_value='/dev/fixture'),patch.object(labels.subprocess,'run',side_effect=print_once):
            printed=labels.print_label(self.client,self.jobs,self.group,self.actor,self.key,self.item,layouts=self.layouts,review_id=preview['review_id'])
        self.assertEqual(printed['status'],'completed')
        self.assertEqual(sent,[image.tobytes()])


if __name__=='__main__':unittest.main()
