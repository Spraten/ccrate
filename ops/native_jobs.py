"""Temporary native-write intent; completed jobs retain IDs and outcomes only."""
import hashlib,json
from uuid import uuid4
from ledger import Conflict,uuid,timestamp

KINDS=('create_location','create_asset','create_template','report_problem','print_label','review_condition','complete_maintenance','create_type','print_badge')


class NativeJobs:
    def __init__(self,ledger):self.ledger=ledger
    def prepare(self,group,actor,kind,key,payload):
        group,actor,key=uuid(group),uuid(actor),uuid(key)
        if kind not in KINDS:raise ValueError('Unsupported native task')
        encoded=json.dumps(payload,sort_keys=True,separators=(',',':'))
        digest=hashlib.sha256(json.dumps([group,actor,kind,encoded],separators=(',',':')).encode()).hexdigest()
        with self.ledger.transaction() as db:
            prior=db.execute('SELECT * FROM native_jobs WHERE group_id=? AND request_key=?',(group,key)).fetchone()
            if prior:
                if prior['request_hash']!=digest:raise Conflict('Request key already belongs to another task')
                return self.decode(prior)
            job=str(uuid4());now=timestamp()
            db.execute('INSERT INTO native_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                (job,group,actor,kind,key,digest,'prepared',None,encoded,'{}',now,now))
            self.event(db,job,'prepared',{})
            return self.decode(db.execute('SELECT * FROM native_jobs WHERE id=?',(job,)).fetchone())
    @staticmethod
    def decode(row):
        data=dict(row);data['payload']=json.loads(data['payload']) if data['payload'] else None;data['context']=json.loads(data['context']);return data
    def detail(self,group,job):
        with self.ledger.connection() as db:
            row=db.execute('SELECT * FROM native_jobs WHERE group_id=? AND id=?',(uuid(group),uuid(job))).fetchone()
            if not row:raise ValueError('Unknown native task')
            return self.decode(row)
    def event(self,db,job,kind,detail):
        db.execute('INSERT INTO native_job_events(job_id,kind,detail,created_at) VALUES(?,?,?,?)',
            (job,kind,json.dumps(detail,sort_keys=True),timestamp()))
    def sent(self,group,job):
        with self.ledger.transaction() as db:
            changed=db.execute("UPDATE native_jobs SET status='sent',updated_at=? WHERE group_id=? AND id=? AND status='prepared'",(timestamp(),uuid(group),uuid(job))).rowcount
            if not changed:raise Conflict('Task was already sent; use Admin recovery')
            self.event(db,uuid(job),'native_write_started',{})
    def context(self,group,job,**values):
        with self.ledger.transaction() as db:
            row=db.execute("SELECT * FROM native_jobs WHERE group_id=? AND id=? AND status IN ('prepared','sent','review')",(uuid(group),uuid(job))).fetchone()
            if not row:raise Conflict('Task is already resolved')
            context=json.loads(row['context']);context.update(values)
            db.execute('UPDATE native_jobs SET context=?,updated_at=? WHERE id=?',(json.dumps(context,sort_keys=True),timestamp(),row['id']))
    def record(self,group,job,kind,detail):
        with self.ledger.transaction() as db:
            row=db.execute("SELECT id FROM native_jobs WHERE group_id=? AND id=? AND status IN ('sent','review')",(uuid(group),uuid(job))).fetchone()
            if not row:raise Conflict('Task is not awaiting native completion')
            self.event(db,row['id'],kind,detail)
    def bind(self,group,job,entity_id):
        with self.ledger.transaction() as db:
            row=db.execute("SELECT * FROM native_jobs WHERE group_id=? AND id=? AND status IN ('sent','review')",(uuid(group),uuid(job))).fetchone()
            if not row:raise Conflict('Task is already resolved')
            if row['result_id'] and row['result_id']!=uuid(entity_id):raise Conflict('Native result ID cannot be replaced')
            db.execute('UPDATE native_jobs SET result_id=?,updated_at=? WHERE id=?',(uuid(entity_id),timestamp(),row['id']))
            self.event(db,row['id'],'native_result_linked',{'entity_id':uuid(entity_id)})
    def review(self,group,job,reason):
        with self.ledger.transaction() as db:
            changed=db.execute("UPDATE native_jobs SET status='review',updated_at=? WHERE group_id=? AND id=? AND status IN ('prepared','sent','review')",(timestamp(),uuid(group),uuid(job))).rowcount
            if not changed:raise Conflict('Task is already resolved')
            self.event(db,uuid(job),'review_required',{'reason':reason})
    def complete(self,group,job):
        with self.ledger.transaction() as db:
            changed=db.execute("UPDATE native_jobs SET status='completed',payload=NULL,context='{}',updated_at=? WHERE group_id=? AND id=? AND status IN ('sent','review') AND result_id IS NOT NULL",(timestamp(),uuid(group),uuid(job))).rowcount
            if not changed:raise Conflict('Native result has not been linked or task is already resolved')
            self.event(db,uuid(job),'completed',{})
    def cancel(self,group,job):
        with self.ledger.transaction() as db:
            changed=db.execute("UPDATE native_jobs SET status='cancelled',payload=NULL,context='{}',updated_at=? WHERE group_id=? AND id=? AND status IN ('prepared','sent','review') AND result_id IS NULL",(timestamp(),uuid(group),uuid(job))).rowcount
            if not changed:raise Conflict('A created native record cannot be cancelled here')
            self.event(db,uuid(job),'cancelled',{})
    def unresolved(self,group):
        with self.ledger.connection() as db:
            return [self.decode(r) for r in db.execute("SELECT * FROM native_jobs WHERE group_id=? AND status IN ('prepared','sent','review') ORDER BY created_at",(uuid(group),))]
    def history(self,group,entity=None):
        with self.ledger.connection() as db:
            query='SELECT id,actor_id,kind AS action,status,created_at,result_id FROM native_jobs WHERE group_id=?'
            args=[uuid(group)]
            if entity:query+=' AND result_id=?';args.append(uuid(entity))
            query+=' ORDER BY created_at DESC LIMIT 100'
            result=[dict(row) for row in db.execute(query,args)]
            for row in result:row['assets']=[row.pop('result_id')] if row['result_id'] else []
            return result
