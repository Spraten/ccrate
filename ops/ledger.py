"""Operational journal only: native Homebox UUID references, no inventory copy."""
import hashlib,json,pathlib,sqlite3
from contextlib import contextmanager
from datetime import datetime,timezone
from uuid import UUID,uuid4

class Conflict(ValueError):pass
def timestamp():return datetime.now(timezone.utc).isoformat()
def uuid(value):return str(UUID(str(value)))

class Ledger:
    def __init__(self,path):
        self.path=pathlib.Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connection() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS operations(
              id TEXT PRIMARY KEY, group_id TEXT NOT NULL, actor_id TEXT NOT NULL,
              action TEXT NOT NULL CHECK(action IN ('check_out','return')),
              request_key TEXT NOT NULL, request_hash TEXT NOT NULL,
              status TEXT NOT NULL CHECK(status IN ('pending','review','completed','cancelled')),
              created_at TEXT NOT NULL, UNIQUE(group_id,request_key));
            CREATE TABLE IF NOT EXISTS operation_assets(
              operation_id TEXT NOT NULL REFERENCES operations(id),entity_id TEXT NOT NULL,
              PRIMARY KEY(operation_id,entity_id));
            CREATE TABLE IF NOT EXISTS events(
              sequence INTEGER PRIMARY KEY,operation_id TEXT NOT NULL REFERENCES operations(id),
              kind TEXT NOT NULL, detail TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TRIGGER IF NOT EXISTS no_event_update BEFORE UPDATE ON events
              BEGIN SELECT RAISE(ABORT,'events are append-only'); END;
            CREATE TRIGGER IF NOT EXISTS no_event_delete BEFORE DELETE ON events
              BEGIN SELECT RAISE(ABORT,'events are append-only'); END;
            CREATE TABLE IF NOT EXISTS custody(
              group_id TEXT NOT NULL,entity_id TEXT NOT NULL,actor_id TEXT NOT NULL,
              operation_id TEXT NOT NULL REFERENCES operations(id),PRIMARY KEY(group_id,entity_id));
            ''')
    @contextmanager
    def connection(self):
        db=sqlite3.connect(self.path,timeout=5,isolation_level=None)
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON');db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA synchronous=FULL')
        try:yield db
        finally:db.close()
    @contextmanager
    def transaction(self):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:yield db;db.execute('COMMIT')
            except BaseException:db.execute('ROLLBACK');raise
    def event(self,db,op,kind,detail=None):
        db.execute('INSERT INTO events(operation_id,kind,detail,created_at) VALUES(?,?,?,?)',
            (op,kind,json.dumps(detail or {},sort_keys=True),timestamp()))
    def begin(self,group,actor,action,assets,request_key):
        group,actor,key=uuid(group),uuid(actor),uuid(request_key)
        assets=[uuid(a) for a in assets]
        if not assets or len(assets)!=len(set(assets)):raise ValueError('A nonempty set of distinct assets is required')
        assets.sort()
        if action not in ('check_out','return'):raise ValueError('Unsupported operation')
        digest=hashlib.sha256(json.dumps([group,actor,action,assets],separators=(',',':')).encode()).hexdigest()
        with self.transaction() as db:
            prior=db.execute('SELECT * FROM operations WHERE group_id=? AND request_key=?',(group,key)).fetchone()
            if prior:
                if prior['request_hash']!=digest:raise Conflict('Request key was already used for another operation')
                return dict(prior)
            for asset in assets:
                reserved=db.execute("SELECT 1 FROM operation_assets a JOIN operations o ON o.id=a.operation_id WHERE o.group_id=? AND a.entity_id=? AND o.status IN ('pending','review')",(group,asset)).fetchone()
                if reserved:raise Conflict('An unresolved operation already references this asset')
                held=db.execute('SELECT 1 FROM custody WHERE group_id=? AND entity_id=?',(group,asset)).fetchone()
                if action=='check_out' and held:raise Conflict('Asset is already checked out')
                if action=='return' and not held:raise Conflict('Asset is not checked out')
            op=str(uuid4())
            db.execute('INSERT INTO operations VALUES(?,?,?,?,?,?,?,?)',(op,group,actor,action,key,digest,'pending',timestamp()))
            db.executemany('INSERT INTO operation_assets VALUES(?,?)',[(op,a) for a in assets])
            self.event(db,op,'requested')
            return dict(db.execute('SELECT * FROM operations WHERE id=?',(op,)).fetchone())
    def complete(self,op):
        op=uuid(op)
        with self.transaction() as db:
            record=db.execute('SELECT * FROM operations WHERE id=?',(op,)).fetchone()
            if not record:raise ValueError('Unknown operation')
            if record['status']=='completed':return
            if record['status']!='pending':raise Conflict('Operation requires explicit reconciliation')
            self._complete(db,record)
    def _complete(self,db,record):
        op=record['id']
        assets=[r[0] for r in db.execute('SELECT entity_id FROM operation_assets WHERE operation_id=?',(op,))]
        for asset in assets:
            if record['action']=='check_out':
                db.execute('INSERT INTO custody VALUES(?,?,?,?)',(record['group_id'],asset,record['actor_id'],op))
            else:db.execute('DELETE FROM custody WHERE group_id=? AND entity_id=?',(record['group_id'],asset))
        db.execute("UPDATE operations SET status='completed' WHERE id=?",(op,));self.event(db,op,'completed')
    def review(self,op,reason):
        op=uuid(op)
        if not reason:raise ValueError('A recovery reason is required')
        with self.transaction() as db:
            row=db.execute('SELECT status FROM operations WHERE id=?',(op,)).fetchone()
            if not row:raise ValueError('Unknown operation')
            if row['status'] not in ('pending','review'):raise Conflict('Terminal operation cannot be marked unresolved')
            db.execute("UPDATE operations SET status='review' WHERE id=?",(op,));self.event(db,op,'review_required',{'reason':reason})
    def reconcile(self,op,outcome,reason):
        op=uuid(op)
        if outcome not in ('complete','cancel') or not reason:raise ValueError('Explicit recovery outcome and reason required')
        with self.transaction() as db:
            row=db.execute('SELECT * FROM operations WHERE id=?',(op,)).fetchone()
            if not row or row['status']!='review':raise Conflict('Only reviewed operations can be reconciled')
            self.event(db,op,'reconciled',{'outcome':outcome,'reason':reason})
            if outcome=='complete':self._complete(db,row)
            else:
                db.execute("UPDATE operations SET status='cancelled' WHERE id=?",(op,));self.event(db,op,'cancelled')
    def unresolved(self):
        with self.connection() as db:return [dict(r) for r in db.execute("SELECT * FROM operations WHERE status IN ('pending','review') ORDER BY created_at")]
