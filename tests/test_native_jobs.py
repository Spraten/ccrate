import pathlib,sqlite3,tempfile,unittest
from uuid import uuid4
from ledger import Ledger,Conflict
from native_jobs import NativeJobs


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.ledger=Ledger(pathlib.Path(self.temp.name)/'ops.db');self.jobs=NativeJobs(self.ledger)
        self.group,self.actor,self.key=[str(uuid4()) for _ in range(3)]
    def tearDown(self):self.temp.cleanup()
    def prepare(self,payload=None):return self.jobs.prepare(self.group,self.actor,'create_location',self.key,payload or {'name':'Room'})
    def test_same_request_is_idempotent_and_changed_request_rejected(self):
        first=self.prepare();self.assertEqual(self.prepare()['id'],first['id'])
        with self.assertRaises(Conflict):self.prepare({'name':'Other room'})
    def test_only_one_native_send_is_allowed(self):
        job=self.prepare();self.jobs.sent(self.group,job['id'])
        with self.assertRaises(Conflict):self.jobs.sent(self.group,job['id'])
    def test_completed_job_drops_pending_profile_data(self):
        job=self.prepare({'name':'Temporary input','description':'Not a copied catalog'})
        self.jobs.sent(self.group,job['id']);self.jobs.bind(self.group,job['id'],str(uuid4()));self.jobs.complete(self.group,job['id'])
        detail=self.jobs.detail(self.group,job['id']);self.assertIsNone(detail['payload']);self.assertEqual(detail['context'],{});self.assertEqual(detail['status'],'completed')
    def test_result_cannot_be_replaced_or_created_record_cancelled(self):
        job=self.prepare();self.jobs.sent(self.group,job['id']);self.jobs.bind(self.group,job['id'],str(uuid4()))
        with self.assertRaises(Conflict):self.jobs.bind(self.group,job['id'],str(uuid4()))
        with self.assertRaises(Conflict):self.jobs.cancel(self.group,job['id'])
    def test_event_history_is_append_only_and_group_isolation_applies(self):
        job=self.prepare()
        with self.ledger.connection() as db:
            with self.assertRaises(sqlite3.IntegrityError):db.execute("UPDATE native_job_events SET kind='changed'")
            with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM native_job_events')
        with self.assertRaises(ValueError):self.jobs.detail(str(uuid4()),job['id'])
        self.assertEqual(self.jobs.unresolved(str(uuid4())),[])
    def test_inflight_intent_survives_restart(self):
        job=self.prepare();self.jobs.sent(self.group,job['id']);self.jobs.context(self.group,job['id'],marker_id=str(uuid4()))
        reopened=NativeJobs(Ledger(self.ledger.path));detail=reopened.detail(self.group,job['id'])
        self.assertEqual(detail['status'],'sent');self.assertIn('marker_id',detail['context']);self.assertEqual(detail['payload']['name'],'Room')
    def test_sent_print_atomically_reviews_and_links_before_started(self):
        entity=str(uuid4());review=str(uuid4())
        job=self.jobs.prepare(self.group,self.actor,'print_label',self.key,{'entity_id':entity,'review_id':review})
        metadata={'review_id':review,'template_id':str(uuid4()),'template_revision':1,'template_hash':'a'*64,'sha256':'b'*64,'profile':'supvan','label_mm':[40,28],'dpi':203.2,'width':320,'height':224}
        self.jobs.sent_print(self.group,job['id'],entity,metadata)
        saved=self.jobs.detail(self.group,job['id'])
        self.assertEqual((saved['status'],saved['result_id']),('sent',entity))
        with self.ledger.connection() as db:
            events=[dict(row) for row in db.execute('SELECT kind,detail FROM native_job_events WHERE job_id=? ORDER BY rowid',(job['id'],))]
        kinds=[row['kind'] for row in events]
        self.assertLess(kinds.index('print_reviewed'),kinds.index('native_write_started'))
        self.assertLess(kinds.index('native_write_started'),kinds.index('native_result_linked'))
        with self.assertRaises(Conflict):self.jobs.sent_print(self.group,job['id'],entity,metadata)
    def test_atomic_print_accepts_immutable_starter_revision_zero(self):
        entity=str(uuid4());review=str(uuid4());key=str(uuid4())
        job=self.jobs.prepare(self.group,self.actor,'print_label',key,{'entity_id':entity,'review_id':review})
        metadata={'review_id':review,'template_id':'starter:supvan:left','template_revision':0,'template_hash':'a'*64,'sha256':'b'*64,'profile':'supvan','label_mm':[40,28],'dpi':203.2,'width':320,'height':224}
        self.jobs.sent_print(self.group,job['id'],entity,metadata)
    def test_history_marks_first_completion_time_separately_from_request_time(self):
        entity=str(uuid4());job=self.jobs.prepare(self.group,self.actor,'add_note',self.key,
            {'entity_id':entity,'note':'A short note'},context={'entity_id':entity})
        self.jobs.start_note(self.group,job['id'],entity)
        pending=next(row for row in self.jobs.history(self.group,entity) if row['id']==job['id'])
        self.assertEqual((pending['source'],pending['time_basis'],pending['confirmed_at']),('native_job','request',None))
        self.jobs.record(self.group,job['id'],'note_verified',{'maintenance_id':str(uuid4())})
        self.jobs.complete(self.group,job['id'])
        completed=next(row for row in self.jobs.history(self.group,entity) if row['id']==job['id'])
        self.assertEqual(completed['source'],'native_job');self.assertEqual(completed['time_basis'],'confirmation')
        self.assertIsNotNone(completed['confirmed_at']);self.assertGreaterEqual(completed['confirmed_at'],completed['created_at'])


    def test_shelf_order_is_a_supported_native_job_kind(self):
        job=self.jobs.prepare(self.group,self.actor,'workshop_shelf_order',self.key,{'entity_id':str(uuid4()),'shelf_ids':[]})
        self.assertEqual(job['kind'],'workshop_shelf_order')
    def test_shelf_order_preparation_persists_recovery_context_atomically(self):
        rack=str(uuid4());payload={'entity_id':rack,'shelf_ids':[]};context={'rack_id':rack,'original':'[]','shelf_fingerprint':[]}
        job=self.jobs.prepare(self.group,self.actor,'workshop_shelf_order',self.key,payload,context=context)
        reopened=NativeJobs(Ledger(self.ledger.path));recovered=reopened.detail(self.group,job['id'])
        self.assertEqual(recovered['status'],'prepared');self.assertEqual(recovered['context'],context)


if __name__=='__main__':unittest.main()
