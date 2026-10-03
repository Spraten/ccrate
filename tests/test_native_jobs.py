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


if __name__=='__main__':unittest.main()
