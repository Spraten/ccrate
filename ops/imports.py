"""Private, resumable CSV review batches; inventory remains in native Homebox."""
import csv,io,json,hashlib,pathlib,sqlite3,contextlib
from uuid import uuid4
from ledger import Conflict,uuid
from setup_native import submit,text
from native_fields import text_field
from labels import print_label

KEY_FIELD='Import source key'
FIELDS=('name','serial','manufacturer','model','description','location','category','external_id','source_condition')

def parse_csv(content):
    if not isinstance(content,str) or len(content.encode('utf-8'))>700000:raise ValueError('Use a CSV smaller than 700 KB')
    if '\ufffd' in content or '\x00' in content:raise ValueError('Save the export as CSV UTF-8, then choose it again')
    content=content.lstrip('\ufeff')
    try:delimiter=csv.Sniffer().sniff(content[:8192],delimiters=',;\t').delimiter
    except csv.Error:delimiter=','
    try:records=list(csv.reader(io.StringIO(content),delimiter=delimiter,strict=True))
    except csv.Error:raise ValueError('CSV quoting is invalid')
    if len(records)<2:raise ValueError('CSV needs column headings and at least one item')
    headers=[h.strip() for h in records[0]]
    if not headers or len(headers)>40 or any(not h or len(h)>120 for h in headers) or len(set(headers))!=len(headers):raise ValueError('Use unique, nonempty column headings (maximum 40 columns)')
    rows=[r for r in records[1:] if any(c.strip() for c in r)]
    if not 1<=len(rows)<=500:raise ValueError('Import 1 to 500 items per file')
    for index,row in enumerate(rows,2):
        if len(row)!=len(headers):raise ValueError('CSV row '+str(index)+' has a different number of columns')
        if any(len(c)>1000 for c in row):raise ValueError('A value in row '+str(index)+' is longer than 1000 characters')
    return headers,rows

class Imports:
    def __init__(self,path):
        self.path=pathlib.Path(path);self.path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS batches(id TEXT PRIMARY KEY,group_id TEXT NOT NULL,actor_id TEXT NOT NULL,document TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
        self.path.chmod(0o600)
    @contextlib.contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=15);db.row_factory=sqlite3.Row
        try:
            db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE');yield db;db.commit()
        except Exception:db.rollback();raise
        finally:db.close()
    def put(self,group,batch):
        with self.db() as db:
            if not db.execute('UPDATE batches SET document=? WHERE id=? AND group_id=?',(json.dumps(batch),uuid(batch['id']),uuid(group))).rowcount:raise ValueError('Unknown import batch')
    def get(self,group,batch_id):
        with self.db() as db:row=db.execute('SELECT document FROM batches WHERE id=? AND group_id=?',(uuid(batch_id),uuid(group))).fetchone()
        if not row:raise ValueError('Unknown import batch')
        return json.loads(row['document'])
    def list(self,group):
        with self.db() as db:rows=db.execute('SELECT document FROM batches WHERE group_id=? ORDER BY created_at DESC,rowid DESC LIMIT 30',(uuid(group),)).fetchall()
        return [{'id':b['id'],'filename':b['filename'],'source':b['source'],'count':len(b.get('items',[])) or len(b.get('raw',[])),'mapped':bool(b.get('items'))} for b in [json.loads(r['document']) for r in rows]]
    def upload(self,group,actor,data):
        headers,rows=parse_csv(data.get('csv'));batch={'id':str(uuid4()),'actor':uuid(actor),'filename':text(data.get('filename','Import.csv'),'Filename',255,True),'source':text(data.get('source',''),'Source system',120,True),'headers':headers,'raw':rows,'items':[]}
        with self.db() as db:db.execute('INSERT INTO batches(id,group_id,actor_id,document) VALUES(?,?,?,?)',(batch['id'],uuid(group),uuid(actor),json.dumps(batch)))
        return batch
    def map(self,client,group,data):
        batch=self.get(group,data.get('id'))
        if batch['items']:raise Conflict('This batch is already mapped; review its existing rows')
        mapping=data.get('mapping',{});headers=batch['headers']
        if not isinstance(mapping,dict) or mapping.get('name') not in headers:raise ValueError('Map the equipment name column')
        if any(k not in FIELDS or v and v not in headers for k,v in mapping.items()):raise ValueError('Unknown CSV column mapping')
        locations=[e for e in client.entities(True) if not e.get('archived')];types=[t for t in client.call('/api/v1/entity-types') if not t['isLocation']]
        def match(value,choices):
            hits=[c['id'] for c in choices if c['name'].strip().casefold()==value.strip().casefold()]
            return hits[0] if len(hits)==1 else ''
        for index,raw in enumerate(batch['raw']):
            original={k:raw[headers.index(mapping[k])].strip() if mapping.get(k) else '' for k in FIELDS}
            identity=original['external_id'] or hashlib.sha256(json.dumps(original,sort_keys=True).encode()).hexdigest()
            source_key=hashlib.sha256(json.dumps([batch['source'].casefold(),identity],ensure_ascii=False).encode()).hexdigest()
            payload={k:original[k] for k in ('name','serial','manufacturer','model','description')}
            payload.update(location_id=match(original['location'],locations) if original['location'] else data.get('location_id',''),type_id=match(original['category'],types) if original['category'] else data.get('type_id',''),reviewed=False,import_condition='Unreviewed',import_source=batch['source'],import_source_key=source_key,import_external_id=original['external_id'],import_source_condition=original['source_condition'])
            batch['items'].append({'index':index,'csv_row':index+2,'original':original,'input':payload,'status':'draft','selected':True,'error':None,'entity_id':None,'asset_id':None,'create_key':str(uuid4()),'label_key':str(uuid4()),'label_status':'pending'})
        batch.pop('raw');batch['mapping']=mapping;self.put(group,batch);return self.validate(client,group,batch['id'])
    def validate(self,client,group,batch_id):
        batch=self.get(group,batch_id);existing=[client.entity(e['id']) for e in client.entities()];serials={e.get('serialNumber'):e for e in existing if e.get('serialNumber')};keys={text_field(e,KEY_FIELD):e for e in existing if text_field(e,KEY_FIELD)}
        location_ids={e['id'] for e in client.entities(True) if not e.get('archived')};type_ids={t['id'] for t in client.call('/api/v1/entity-types') if not t['isLocation']};seen_keys=set();seen_serials=set()
        for row in batch['items']:
            d=row['input'];errors=[];duplicate=keys.get(d['import_source_key']) or serials.get(d['serial'])
            if not d['name'].strip():errors.append('Equipment name is required')
            for k in ('name','serial','manufacturer','model','import_external_id','import_source_condition'):
                if len(d[k])>255:errors.append(k+' exceeds 255 characters')
            if len(d['description'])>1000:errors.append('Description exceeds 1000 characters')
            if d['location_id'] not in location_ids:errors.append('Choose an existing active location')
            if d['type_id'] not in type_ids:errors.append('Choose an existing equipment category')
            if d['import_condition']=='Ready' and not d['reviewed']:errors.append('Ready requires explicit inspection confirmation')
            if row['selected'] and row['status']!='created':
                if d['import_source_key'] in seen_keys:errors.append('Duplicate source identity in this batch; skip one row')
                if d['serial'] and d['serial'] in seen_serials:errors.append('Duplicate serial in this batch; skip one row')
                if duplicate and duplicate['id']!=row.get('entity_id'):errors.append('Already in Homebox: '+duplicate['name']+' â€” skip this row')
            if row['selected']:
                seen_keys.add(d['import_source_key'])
                if d['serial']:seen_serials.add(d['serial'])
            row['errors']=errors;row['duplicate_id']=duplicate['id'] if duplicate else None
        self.put(group,batch);return batch
    def save(self,client,jobs,group,data):
        from conditions import STATES
        batch=self.get(group,data.get('id'));row=self.row(batch,data)
        if row['status'] in ('creating','created','review'):raise Conflict('Created or uncertain rows cannot be edited; use Admin recovery or edit in Homebox')
        changes=data.get('input',{})
        for k in ('name','serial','manufacturer','model','description','location_id','type_id'):
            if k in changes:row['input'][k]=text(changes[k],k,1000 if k=='description' else 255)
        state=changes.get('import_condition',row['input']['import_condition'])
        if state not in ('Unreviewed',*STATES):raise ValueError('Unknown condition')
        row['input']['import_condition']=state;row['input']['reviewed']=changes.get('reviewed') is True;row['selected']=data.get('selected',True) is True
        row['status']='reviewed' if row['selected'] else 'skipped';row['error']=None;row['create_key']=str(uuid4())
        self.put(group,batch);return self.validate(client,group,batch['id'])
    @staticmethod
    def row(batch,data):
        index=data.get('index')
        if type(index) is not int or not 0<=index<len(batch['items']):raise ValueError('Unknown import item')
        return batch['items'][index]
    def native_job(self,jobs,group,key):
        with jobs.ledger.connection() as db:row=db.execute('SELECT id FROM native_jobs WHERE group_id=? AND request_key=?',(group,key)).fetchone()
        return jobs.detail(group,row['id']) if row else None
    def create(self,client,jobs,group,data):
        batch=self.get(group,data.get('id'));row=self.row(batch,data)
        if row['status']=='created':return batch
        prior=self.native_job(jobs,group,row['create_key'])
        if prior and prior['status']=='completed':
            entity=client.entity(prior['result_id']);row.update(status='created',entity_id=entity['id'],asset_id=entity.get('assetId'),error=None);self.put(group,batch);return batch
        if prior and prior['status']!='cancelled':
            row.update(status='review',error='Finish the interrupted native task in Admin recovery, then refresh this batch');self.put(group,batch);raise Conflict(row['error'])
        if row['status'] not in ('reviewed','creating') or not row['selected']:raise Conflict('Review and save this row before creating it')
        batch=self.validate(client,group,batch['id']);row=self.row(batch,data)
        if row['errors']:raise ValueError('; '.join(row['errors']))
        if prior:raise Conflict('Cancelled task: edit and save the row to prepare a new attempt')
        row['status']='creating';self.put(group,batch)
        try:
            result=submit(client,jobs,group,batch['actor'],'create_asset',row['create_key'],row['input']);entity=client.entity(result['entity_id'])
            row.update(status='created',entity_id=entity['id'],asset_id=entity.get('assetId'),error=None)
        except Exception:
            job=self.native_job(jobs,group,row['create_key']);row.update(status='error' if not job or job['status']=='cancelled' else 'review',error='Creation stopped. Inspect Admin recovery before repeating this item.');self.put(group,batch);raise
        self.put(group,batch);return batch
    def label(self,client,jobs,group,data):
        batch=self.get(group,data.get('id'));row=self.row(batch,data)
        if row['status']!='created':raise Conflict('Create this item before printing its label')
        if row['label_status']=='printed':return batch
        prior=self.native_job(jobs,group,row['label_key'])
        if prior and prior['status']=='completed':row['label_status']='printed';self.put(group,batch);return batch
        if prior and prior['status'] not in ('prepared','cancelled'):row['label_status']='review';self.put(group,batch);raise Conflict('Inspect the physical output and finish this print in Admin recovery. Do not resend it.')
        if prior and prior['status']=='cancelled':row['label_key']=str(uuid4());self.put(group,batch)
        try:print_label(client,jobs,group,batch['actor'],row['label_key'],row['entity_id']);row['label_status']='printed';row['error']=None
        except Exception:
            job=self.native_job(jobs,group,row['label_key']);row['label_status']='review' if job and job['status']=='review' else 'pending';row['error']='Printing stopped. Check the printer and review any uncertain output.';self.put(group,batch);raise
        self.put(group,batch);return batch

    def sync(self,client,jobs,group,data):
        batch=self.get(group,data.get('id'))
        for row in batch['items']:
            job=self.native_job(jobs,group,row['create_key'])
            if job and job['status']=='completed' and row['status']!='created':
                entity=client.entity(job['result_id']);row.update(status='created',entity_id=entity['id'],asset_id=entity.get('assetId'),error=None)
            elif job and job['status']=='cancelled' and row['status']=='review':row.update(status='error',error='Cancelled safely. Edit and save to retry.')
            job=self.native_job(jobs,group,row['label_key'])
            if job and job['status']=='completed':row.update(label_status='printed',error=None)
            elif job and job['status']=='cancelled' and row['label_status']=='review':row.update(label_status='pending',error=None)
        self.put(group,batch);return self.validate(client,group,batch['id']) if batch['items'] else batch
