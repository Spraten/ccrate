"""Operational journal only: native Homebox UUID references, no inventory copy."""
import hashlib,json,pathlib,sqlite3
from contextlib import contextmanager
from datetime import datetime,timezone
from uuid import UUID,uuid4

class Conflict(ValueError):pass
def timestamp():return datetime.now(timezone.utc).isoformat()
def uuid(value):return str(UUID(str(value)))

class Ledger:
    SCHEMA_VERSION=2
    def __init__(self,path):
        self.path=pathlib.Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connection() as db:
            version=db.execute('PRAGMA user_version').fetchone()[0]
            if version>self.SCHEMA_VERSION:raise ValueError('Operational database is newer than this application')
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
            if version==0:
                db.executescript('''BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS operation_context(
                  operation_id TEXT PRIMARY KEY REFERENCES operations(id),payload TEXT NOT NULL);
                PRAGMA user_version=1;
                COMMIT;''')
            if version<2:
                db.executescript("BEGIN IMMEDIATE;\n                CREATE TABLE IF NOT EXISTS native_jobs(\n                  id TEXT PRIMARY KEY,group_id TEXT NOT NULL,actor_id TEXT NOT NULL,kind TEXT NOT NULL,\n                  request_key TEXT NOT NULL,request_hash TEXT NOT NULL,\n                  status TEXT NOT NULL CHECK(status IN ('prepared','sent','review','completed','cancelled')),\n                  result_id TEXT,payload TEXT,context TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,\n                  UNIQUE(group_id,request_key));\n                CREATE TABLE IF NOT EXISTS native_job_events(\n                  sequence INTEGER PRIMARY KEY,job_id TEXT NOT NULL REFERENCES native_jobs(id),\n                  kind TEXT NOT NULL,detail TEXT NOT NULL,created_at TEXT NOT NULL);\n                CREATE TRIGGER IF NOT EXISTS no_native_job_event_update BEFORE UPDATE ON native_job_events\n                  BEGIN SELECT RAISE(ABORT,'events are append-only'); END;\n                CREATE TRIGGER IF NOT EXISTS no_native_job_event_delete BEFORE DELETE ON native_job_events\n                  BEGIN SELECT RAISE(ABORT,'events are append-only'); END;\n                PRAGMA user_version=2;COMMIT;")
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
    def begin(self,group,actor,action,assets,request_key,context=None,intent=None):
        group,actor,key=uuid(group),uuid(actor),uuid(request_key)
        assets=[uuid(a) for a in assets]
        if not assets or len(assets)!=len(set(assets)):raise ValueError('A nonempty set of distinct assets is required')
        assets.sort()
        if action not in ('check_out','return'):raise ValueError('Unsupported operation')
        digest=self.request_digest(group,actor,action,assets,intent)
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
            if context is not None:
                db.execute('INSERT INTO operation_context VALUES(?,?)',(op,json.dumps(context,sort_keys=True)))
            self.event(db,op,'requested',{'intent':intent} if intent is not None else None)
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

    def custody(self,group):
        group=uuid(group)
        with self.connection() as db:
            return [dict(r) for r in db.execute('SELECT * FROM custody WHERE group_id=?',(group,))]

    @staticmethod
    def request_digest(group,actor,action,assets,intent=None):
        payload=[uuid(group),uuid(actor),action,sorted(uuid(a) for a in assets)]
        if intent is not None:payload.append(intent)
        return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()

    def request(self,group,key):
        with self.connection() as db:
            row=db.execute('SELECT * FROM operations WHERE group_id=? AND request_key=?',(uuid(group),uuid(key))).fetchone()
            return dict(row) if row else None

    def detail(self,group,op):
        with self.connection() as db:
            row=db.execute('SELECT * FROM operations WHERE group_id=? AND id=?',(uuid(group),uuid(op))).fetchone()
            if not row:raise ValueError('Unknown operation')
            result=dict(row)
            result['assets']=[r[0] for r in db.execute('SELECT entity_id FROM operation_assets WHERE operation_id=? ORDER BY entity_id',(result['id'],))]
            context=db.execute('SELECT payload FROM operation_context WHERE operation_id=?',(result['id'],)).fetchone()
            result['context']=json.loads(context[0]) if context else None
            result['events']=[dict(e) for e in db.execute('SELECT sequence,kind,detail,created_at FROM events WHERE operation_id=? ORDER BY sequence',(result['id'],))]
            for event in result['events']:event['detail']=json.loads(event['detail'])
            return result

    def record(self,op,kind,detail):
        with self.transaction() as db:
            row=db.execute('SELECT status FROM operations WHERE id=?',(uuid(op),)).fetchone()
            if not row or row['status'] not in ('pending','review'):raise Conflict('Operation is not awaiting completion')
            self.event(db,uuid(op),kind,detail)

    def history(self,group,entity=None,limit=100):
        with self.connection() as db:
            query='SELECT o.id,o.actor_id,o.action,o.status,o.created_at FROM operations o WHERE o.group_id=?'
            args=[uuid(group)]
            if entity:
                query+=' AND EXISTS(SELECT 1 FROM operation_assets a WHERE a.operation_id=o.id AND a.entity_id=?)';args.append(uuid(entity))
            query+=' ORDER BY o.created_at DESC LIMIT ?';args.append(min(max(int(limit),1),100))
            result=[dict(r) for r in db.execute(query,args)]
            for row in result:
                row['assets']=[r[0] for r in db.execute('SELECT entity_id FROM operation_assets WHERE operation_id=?',(row['id'],))]
                row['return_notes']=[]
                if row['action']=='return' and row['status']=='completed':
                    context=db.execute('SELECT payload FROM operation_context WHERE operation_id=?',(row['id'],)).fetchone()
                    payload=json.loads(context[0]) if context else {}
                    completed=db.execute("SELECT created_at FROM events WHERE operation_id=? AND kind='completed' ORDER BY sequence LIMIT 1",(row['id'],)).fetchone()
                    row['return_notes']=[dict(n,author=payload.get('note_author','Homebox member'),created_at=completed[0] if completed else row['created_at']) for n in payload.get('return_notes',[]) if not entity or n['entity_id']==uuid(entity)]
            return result
