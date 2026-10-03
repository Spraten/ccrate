import pathlib,sqlite3,tempfile,unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from ledger import Ledger,Conflict

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=pathlib.Path(self.temp.name)/'ledger.db'
        self.ledger=Ledger(self.path);self.group=str(uuid4());self.actor=str(uuid4());self.assets=[str(uuid4()),str(uuid4())]
    def tearDown(self):self.temp.cleanup()
    def begin(self,action='check_out',assets=None,key=None):
        return self.ledger.begin(self.group,self.actor,action,assets or self.assets,key or str(uuid4()))
    def test_repeat_request_has_one_operation(self):
        key=str(uuid4());a=self.begin(key=key);b=self.begin(key=key);self.assertEqual(a['id'],b['id'])
        self.ledger.complete(a['id']);self.ledger.complete(a['id'])
        with self.ledger.connection() as db:self.assertEqual(db.execute('SELECT count(*) FROM events').fetchone()[0],2)
    def test_changed_request_key_rejected(self):
        key=str(uuid4());self.begin(key=key)
        with self.assertRaises(Conflict):self.begin(assets=[str(uuid4())],key=key)
    def test_checkout_return_custody(self):
        a=self.begin();self.ledger.complete(a['id'])
        with self.assertRaises(Conflict):self.begin()
        b=self.begin('return');self.ledger.complete(b['id'])
        with self.ledger.connection() as db:self.assertEqual(db.execute('SELECT count(*) FROM custody').fetchone()[0],0)
        with self.assertRaises(Conflict):self.begin('return')
    def test_interrupted_intent_survives_reopen(self):
        a=self.begin();other=Ledger(self.path)
        self.assertEqual(other.unresolved()[0]['id'],a['id'])
        with self.assertRaises(Conflict):self.begin()
        other.review(a['id'],'External result is unknown')
        with self.assertRaises(Conflict):other.complete(a['id'])
    def test_cart_rollback_is_atomic(self):
        a=self.begin()
        with self.ledger.connection() as db:
            db.execute("CREATE TRIGGER fail_second BEFORE INSERT ON custody WHEN (SELECT count(*) FROM custody)=1 BEGIN SELECT RAISE(ABORT,'injected failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.ledger.complete(a['id'])
        with self.ledger.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM custody').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT status FROM operations').fetchone()[0],'pending')
            self.assertEqual(db.execute('SELECT count(*) FROM events').fetchone()[0],1)
    def test_history_cannot_be_overwritten(self):
        self.begin()
        with self.ledger.connection() as db:
            with self.assertRaises(sqlite3.IntegrityError):db.execute("UPDATE events SET kind='changed'")
            with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM events')
    def test_simultaneous_checkouts_one_wins(self):
        def attempt(_):
            try:return self.begin()['id']
            except Conflict:return None
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,range(2)))
        self.assertEqual(sum(x is not None for x in results),1)
    def test_group_isolation(self):
        self.begin()
        other=self.ledger.begin(str(uuid4()),self.actor,'check_out',self.assets,str(uuid4()))
        self.assertEqual(other['status'],'pending')
    def test_duplicate_asset_rejected(self):
        with self.assertRaises(ValueError):self.begin(assets=[self.assets[0],self.assets[0]])
    def test_reconciliation_can_cancel_and_release_reservation(self):
        op=self.begin();self.ledger.review(op['id'],'Uncertain result')
        self.ledger.reconcile(op['id'],'cancel','Verified no external change')
        self.assertEqual(self.begin()['status'],'pending')
    def test_reconciliation_can_complete_once(self):
        op=self.begin();self.ledger.review(op['id'],'Uncertain result')
        self.ledger.reconcile(op['id'],'complete','Verified intended result')
        with self.assertRaises(Conflict):self.ledger.reconcile(op['id'],'complete','Repeated')
        with self.ledger.connection() as db:self.assertEqual(db.execute('SELECT count(*) FROM custody').fetchone()[0],2)

if __name__=='__main__':unittest.main()
