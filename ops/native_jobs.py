"""Temporary native-write intent; completed jobs retain IDs and outcomes only."""
import hashlib,json
from uuid import uuid4
from ledger import Conflict,uuid,timestamp

KINDS=('create_location','create_asset','create_template','report_problem','print_label','review_condition','complete_maintenance','create_type','print_badge','register_code','add_note','workshop_shelf_order')

def _is_uuid(value):
    try:uuid(value);return True
    except (TypeError,ValueError):return False


class NativeJobs:
    def __init__(self,ledger):self.ledger=ledger
    @staticmethod
    def request_digest(group,actor,kind,payload):
        encoded=json.dumps(payload,sort_keys=True,separators=(',',':'))
        return hashlib.sha256(json.dumps([uuid(group),uuid(actor),kind,encoded],separators=(',',':')).encode()).hexdigest()
    def existing(self,group,actor,kind,key,payload):
        """Return an idempotent request-key match without creating a journal row."""
        group,actor,key=uuid(group),uuid(actor),uuid(key)
        if kind not in KINDS:raise ValueError('Unsupported native task')
        digest=self.request_digest(group,actor,kind,payload)
        with self.ledger.connection() as db:
            row=db.execute('SELECT * FROM native_jobs WHERE group_id=? AND request_key=?',(group,key)).fetchone()
        if not row:return None
        if row['request_hash']!=digest:raise Conflict('Request key already belongs to another task')
        return self.decode(row)
    def lookup(self,group,actor,kind,key,payload):
        """Accepted Workshop API name for the existing idempotency lookup."""
        return self.existing(group,actor,kind,key,payload)
    def prepare(self,group,actor,kind,key,payload,context=None):
        group,actor,key=uuid(group),uuid(actor),uuid(key)
        if kind not in KINDS:raise ValueError('Unsupported native task')
        if kind=='add_note':
            if not isinstance(payload,dict) or set(payload)!= {'entity_id','note'}:raise ValueError('Invalid item note request')
            payload=dict(payload);payload['entity_id']=uuid(payload['entity_id'])
            if not isinstance(payload['note'],str):raise ValueError('Item note must be text')
        if context is not None and not isinstance(context,dict):raise ValueError('Invalid native task context')
        encoded=json.dumps(payload,sort_keys=True,separators=(',',':'))
        digest=self.request_digest(group,actor,kind,payload)
        with self.ledger.transaction() as db:
            prior=db.execute('SELECT * FROM native_jobs WHERE group_id=? AND request_key=?',(group,key)).fetchone()
            if prior:
                if prior['request_hash']!=digest:raise Conflict('Request key already belongs to another task')
                return self.decode(prior)
            if kind=='add_note':
                entity_id=payload['entity_id']
                for pending in db.execute("SELECT payload FROM native_jobs WHERE group_id=? AND actor_id=? AND kind='add_note' AND status IN ('prepared','sent','review')",(group,actor)):
                    pending_payload=json.loads(pending['payload'] or '{}')
                    if pending_payload.get('entity_id')==entity_id:
                        raise Conflict('An item note for this equipment is unresolved; inspect Recovery before starting another')
            if kind=='print_label':
                pending=db.execute("SELECT id FROM native_jobs WHERE group_id=? AND kind='print_label' AND status IN ('prepared','sent','review') LIMIT 1",(group,)).fetchone()
                if pending:raise Conflict('A printer request is unresolved. Inspect its output and finish Recovery before printing another label')
            job=str(uuid4());now=timestamp()
            db.execute('INSERT INTO native_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                (job,group,actor,kind,key,digest,'prepared',None,encoded,json.dumps(context or {},sort_keys=True),now,now))
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
    def start_note(self,group,job,entity_id):
        """Atomically bind an item note and durably mark its one permitted POST started."""
        group,job,entity_id=uuid(group),uuid(job),uuid(entity_id)
        with self.ledger.transaction() as db:
            row=db.execute("SELECT * FROM native_jobs WHERE group_id=? AND id=?",(group,job)).fetchone()
            if not row or row['kind']!='add_note' or row['status']!='prepared':
                raise Conflict('Item note was already started or resolved; inspect Recovery')
            payload=json.loads(row['payload'] or '{}');context=json.loads(row['context'])
            if payload.get('entity_id')!=entity_id or context.get('entity_id')!=entity_id:
                raise Conflict('Prepared item note does not match the selected equipment')
            context['note_creation_started']=True
            now=timestamp()
            changed=db.execute("UPDATE native_jobs SET status='sent',result_id=?,context=?,updated_at=? WHERE group_id=? AND id=? AND status='prepared'",
                (entity_id,json.dumps(context,sort_keys=True),now,group,job)).rowcount
            if not changed:raise Conflict('Item note was already started; inspect Recovery')
            self.event(db,job,'native_write_started',{'kind':'add_note','entity_id':entity_id})
            self.event(db,job,'native_result_linked',{'entity_id':entity_id})
    def sent_print(self,group,job,entity_id,review_metadata):
        """Atomically bind an already reviewed raster before starting physical output."""
        group,job,entity_id=uuid(group),uuid(job),uuid(entity_id)
        allowed={'review_id','template_id','template_revision','template_hash','sha256','profile','label_mm','dpi','width','height'}
        if not isinstance(review_metadata,dict) or set(review_metadata)!=allowed:raise ValueError('Invalid reviewed print metadata')
        review_id=uuid(review_metadata['review_id']);template_id=review_metadata['template_id']
        if not isinstance(template_id,str) or not (template_id in {f'starter:{profile}:{layout}' for profile in ('supvan','letter') for layout in ('left','top','compact')} or _is_uuid(template_id)):raise ValueError('Invalid reviewed template ID')
        for key in ('template_hash','sha256'):
            if not isinstance(review_metadata[key],str) or len(review_metadata[key])!=64 or any(c not in '0123456789abcdef' for c in review_metadata[key]):raise ValueError('Invalid reviewed print hash')
        starter=template_id.startswith('starter:')
        if type(review_metadata['template_revision']) is not int or (review_metadata['template_revision']!=0 if starter else review_metadata['template_revision']<1) or review_metadata['profile']!='supvan' or (starter and not template_id.startswith('starter:supvan:')) or review_metadata['label_mm']!=[40,28] or review_metadata['dpi']!=203.2 or (review_metadata['width'],review_metadata['height'])!=(320,224):raise ValueError('Reviewed print does not match SUPVAN stock')
        safe={key:review_metadata[key] for key in allowed}
        with self.ledger.transaction() as db:
            row=db.execute("SELECT * FROM native_jobs WHERE group_id=? AND id=?",(group,job)).fetchone()
            if not row or row['kind']!='print_label' or row['status']!='prepared':raise Conflict('Print was already started or resolved; inspect its output')
            payload=json.loads(row['payload'] or '{}')
            if set(payload)!={'entity_id','review_id'} or uuid(payload['entity_id'])!=entity_id or uuid(payload['review_id'])!=review_id:raise Conflict('Prepared print does not match the reviewed item')
            now=timestamp()
            changed=db.execute("UPDATE native_jobs SET status='sent',result_id=?,updated_at=? WHERE group_id=? AND id=? AND status='prepared'",(entity_id,now,group,job)).rowcount
            if not changed:raise Conflict('Print was already started; inspect its output')
            self.event(db,job,'print_reviewed',safe)
            self.event(db,job,'native_write_started',{})
            self.event(db,job,'native_result_linked',{'entity_id':entity_id})
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
            for row in result:
                job_id=row['id']
                row['assets']=[row.pop('result_id')] if row['result_id'] else []
                row['source']='native_job'
                completed=db.execute("SELECT created_at FROM native_job_events WHERE job_id=? AND kind='completed' ORDER BY sequence LIMIT 1",(job_id,)).fetchone()
                row['confirmed_at']=completed['created_at'] if completed else None
                row['time_basis']='confirmation' if completed else 'request'
            return result
    def events(self,group,job):
        with self.ledger.connection() as db:
            rows=db.execute('SELECT kind,detail,created_at FROM native_job_events WHERE job_id=? AND job_id IN (SELECT id FROM native_jobs WHERE group_id=?) ORDER BY sequence',(uuid(job),uuid(group))).fetchall()
            return [dict(row,detail=json.loads(row['detail'])) for row in rows]
