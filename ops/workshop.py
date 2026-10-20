"""Modular floor-plan geometry; all storage identities remain native Homebox."""
import json,pathlib,sqlite3,math,hashlib,re
from contextlib import closing
from uuid import uuid4,uuid5,UUID
from ledger import uuid,Conflict
from native_fields import text_field,update_payload

KINDS=('Rack','Cabinet','Workbench','Table','Fence','Gate','Door','Area','Kiosk','Wall','Bin','Crate','Drawer','Misc','Custom')
STORAGE=('Area','Rack','Shelf','Bin','Cabinet','Drawer','Workbench','Location')

def number(value,low,high,name):
    if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:raise ValueError(name+' is out of range')
    return round(value,3)

def exact_number(value,low,high,name):
    if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:raise ValueError(name+' is out of range')
    return value

def layout(data):
    if not isinstance(data,dict):raise ValueError('Invalid layout')
    name=data.get('name','Workshop')
    if not isinstance(name,str) or not name.strip() or len(name)>120:raise ValueError('Room name is required (maximum 120 characters)')
    result={'name':name.strip(),'width':number(data.get('width'),4,200,'Room width'),'height':number(data.get('height'),4,200,'Room depth'),'unit':'ft','approximate':data.get('approximate') is True,'objects':[]}
    objects=data.get('objects',[])
    if not isinstance(objects,list) or len(objects)>200:raise ValueError('Use at most 200 drawing objects')
    seen=set()
    for item in objects:
        oid=uuid(item.get('id'))
        if oid in seen:raise ValueError('Duplicate drawing object ID')
        seen.add(oid);kind=item.get('kind');label=item.get('name','')
        if kind not in KINDS or not isinstance(label,str) or not label.strip() or len(label)>120:raise ValueError('Choose an object type and a name')
        width=number(item.get('width'),.1,result['width'],'Object width');height=number(item.get('height'),.1,result['height'],'Object depth');rotation=item.get('rotation',0)
        if rotation not in (0,90,180,270):raise ValueError('Rotate in quarter turns')
        result['objects'].append({'id':oid,'kind':kind,'name':label.strip(),'x':number(item.get('x'),0,result['width']-width,'Horizontal position'),'y':number(item.get('y'),0,result['height']-height,'Vertical position'),'width':width,'height':height,'rotation':rotation,'location_id':uuid(item['location_id']) if item.get('location_id') else None})
    return result

def room_document(data):
    """Validate an explicit version-2 room collection for a future save."""
    if not isinstance(data,dict) or data.get('version')!=2 or type(data.get('version')) is not int:
        raise ValueError('Unsupported workshop document version')
    rooms=data.get('rooms')
    if not isinstance(rooms,list) or len(rooms)>20:raise ValueError('Use at most 20 room plans')
    result=[];room_ids=set();object_ids=set()
    for item in rooms:
        if not isinstance(item,dict):raise ValueError('Invalid room plan')
        if 'location_id' not in item or 'objects' not in item or not isinstance(item['objects'],list):
            raise ValueError('Invalid room plan')
        if any(not isinstance(obj,dict) for obj in item['objects']):raise ValueError('Invalid drawing object')
        room_id=uuid(item.get('id'))
        if room_id in room_ids:raise ValueError('Duplicate room plan ID')
        room_ids.add(room_id)
        location_id=uuid(item['location_id']) if item['location_id'] is not None else None
        for obj in item['objects']:
            if 'location_id' in obj and obj['location_id'] is not None:uuid(obj['location_id'])
        if item.get('unit')!='ft' or type(item.get('approximate')) is not bool:
            raise ValueError('Room plans must use feet and an approximate flag')
        name=item.get('name')
        if not isinstance(name,str) or not name.strip() or len(name)>120:raise ValueError('Room name is required (maximum 120 characters)')
        width=exact_number(item.get('width'),4,200,'Room width');height=exact_number(item.get('height'),4,200,'Room depth')
        if len(item['objects'])>200:raise ValueError('Use at most 200 drawing objects')
        objects=[]
        for source in item['objects']:
            oid=uuid(source.get('id'))
            if oid in object_ids:raise ValueError('Duplicate drawing object ID across room plans')
            object_ids.add(oid)
            kind=source.get('kind');label=source.get('name','')
            if kind not in KINDS or not isinstance(label,str) or not label.strip() or len(label)>120:raise ValueError('Choose an object type and a name')
            obj_width=exact_number(source.get('width'),.1,width,'Object width')
            obj_height=exact_number(source.get('height'),.1,height,'Object depth')
            rotation=source.get('rotation',0)
            if rotation not in (0,90,180,270):raise ValueError('Rotate in quarter turns')
            x=exact_number(source.get('x'),0,width-obj_width,'Horizontal position')
            y=exact_number(source.get('y'),0,height-obj_height,'Vertical position')
            obj_location=uuid(source['location_id']) if source.get('location_id') is not None else None
            color=source.get('color','#477da8')
            opacity=source.get('opacity',1)
            layer=source.get('layer','above')
            if 'color' in source and (not isinstance(color,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',color)):raise ValueError('Choose a valid drawing color')
            if type(opacity) not in (int,float) or not math.isfinite(opacity) or not 0<=opacity<=1:raise ValueError('Drawing opacity is out of range')
            if layer not in ('above','below'):raise ValueError('Choose a valid drawing layer')
            if 'show_name' in source and type(source['show_name']) is not bool:raise ValueError('Drawing name visibility must be a boolean')
            obj={'id':oid,'kind':kind,'name':label,'x':x,'y':y,'width':obj_width,'height':obj_height,
                 'rotation':rotation,'location_id':obj_location}
            if 'color' in source:obj['color']=color
            if 'opacity' in source:obj['opacity']=opacity
            if 'layer' in source:obj['layer']=layer
            if 'show_name' in source:obj['show_name']=source['show_name']
            objects.append(obj)
        result.append({'id':room_id,'location_id':location_id,'name':item['name'],
                       'width':width,'height':height,'unit':'ft',
                       'approximate':item['approximate'],'objects':objects})
    return {'version':2,'rooms':result}

def normalize_document(group,stored):
    """Expose legacy single layouts as rooms without changing their geometry."""
    if stored is None:return {'version':2,'rooms':[]}
    if not isinstance(stored,dict):raise ValueError('Invalid workshop document')
    if 'version' in stored and stored.get('version')!=2:raise ValueError('Unsupported workshop document version')
    if stored.get('version')==2:
        room_document(stored)
        return stored
    room=dict(stored)
    room['id']=str(uuid5(UUID(uuid(group)),'workshop:legacy-room'))
    room['location_id']=None
    return {'version':2,'rooms':[room]}

class Workshop:
    def __init__(self,path):
        self.path=pathlib.Path(path);self.path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        db=sqlite3.connect(self.path)
        try:
            db.execute('CREATE TABLE IF NOT EXISTS plans(group_id TEXT PRIMARY KEY,revision INTEGER NOT NULL,document TEXT NOT NULL)')
            db.execute('''CREATE TABLE IF NOT EXISTS workshop_save_receipts(
              group_id TEXT NOT NULL,request_key TEXT NOT NULL,actor_id TEXT NOT NULL,digest TEXT NOT NULL,result TEXT NOT NULL,
              PRIMARY KEY(group_id,request_key))''')
        finally:db.close()
        self.path.chmod(0o600)
    def get(self,group):
        db=sqlite3.connect(self.path)
        try:row=db.execute('SELECT revision,document FROM plans WHERE group_id=?',(uuid(group),)).fetchone()
        finally:db.close()
        stored=json.loads(row[1]) if row else None
        version=2 if isinstance(stored,dict) and stored.get('version')==2 else 1
        return {'revision':row[0] if row else 0,'schema_version':2,'stored_schema_version':version,
                'document':normalize_document(group,stored),'layout':stored if version==1 else None}
    def validate_save(self,client,group,data):
        if not isinstance(data,dict) or set(data)!={'schema_version','revision','document','request_key'} or type(data.get('schema_version')) is not int or data['schema_version']!=2:
            raise ValueError('This Workshop save is outdated. Reload before saving.')
        revision=data.get('revision')
        if type(revision) is not int or revision<0:raise ValueError('Missing layout revision')
        if revision!=self.get(group)['revision']:raise Conflict('The layout changed elsewhere. Reload before saving your edits.')
        key=uuid(data.get('request_key'))
        document=room_document(data.get('document'))
        current=self.get(group)['document']
        self._validate_links(client,current,document)
        return {'request_key':key,'revision':revision,'document':document}
    @staticmethod
    def _validate_links(client,current,document):
        previous={(r['id'],r['location_id'],o['id'],o['location_id']) for r in current['rooms'] for o in r['objects']}
        requested={(r['id'],r['location_id'],o['id'],o['location_id']) for r in document['rooms'] for o in r['objects']}
        unchanged={row for row in previous & requested}
        previous_rooms={(r['id'],r['location_id']) for r in current['rooms']}
        changed_roots={(r['id'],r['location_id']) for r in document['rooms'] if r['location_id'] is not None and (r['id'],r['location_id']) not in previous_rooms}
        changed_links=[(r,o) for r in document['rooms'] for o in r['objects']
                       if (r['id'],r['location_id'],o['id'],o['location_id']) not in unchanged
                       and (r['location_id'] is not None or o['location_id'] is not None)]
        if not changed_roots and not changed_links:return
        try:
            summaries=client.entities(True)
            active={uuid(e['id']):e for e in summaries if not e.get('archived')}
            all_active={uuid(e['id']):e for e in summaries+client.entities() if not e.get('archived')}
            def location(key):
                if key not in active:raise ValueError('Choose an active location from this collection')
                detail=client.entity(key)
                if detail.get('archived') or not detail.get('entityType',{}).get('isLocation'):
                    raise ValueError('Choose an active location from this collection')
                return detail
            def parent(key):
                if key not in all_active:raise ValueError('Choose an active location from this collection')
                detail=client.entity(key)
                if detail.get('archived'):
                    raise ValueError('Choose an active location from this collection')
                return uuid((detail.get('parent') or {}).get('id')) if (detail.get('parent') or {}).get('id') else None
            def within(root, location):
                if location is None:return True
                seen=set();current_id=location
                while current_id:
                    if current_id in seen:raise ValueError('Native location ancestry contains a cycle')
                    seen.add(current_id)
                    if current_id==root:return True
                    current_id=parent(current_id)
                return False
            def validate_chain(location):
                seen=set();current_id=location
                while current_id:
                    if current_id in seen:raise ValueError('Native location ancestry contains a cycle')
                    seen.add(current_id);current_id=parent(current_id)
            for room_id,root in changed_roots:
                if root not in active:raise ValueError('Choose an active room location from this collection')
                location(root)
                validate_chain(root)
            for room,obj in changed_links:
                root=room['location_id']
                if root is not None and root not in active:
                    raise ValueError('Choose an active room location before changing drawing links')
                if root is not None:
                    location(root)
                    validate_chain(root)
                if obj['location_id'] is not None:
                    if obj['location_id'] not in active:raise ValueError('Choose an active drawing location from this collection')
                    location(obj['location_id'])
                    validate_chain(obj['location_id'])
                    if root is not None and not within(root,obj['location_id']):
                        raise ValueError('Linked locations must remain within the selected room location')
        except (KeyError,TypeError,OSError):
            raise ValueError('Native locations are unavailable; reload before changing room links') from None
    def save(self,client,group,data,*,actor_id):
        group,actor=uuid(group),uuid(actor_id)
        if not isinstance(data,dict) or set(data)!={'schema_version','revision','document','request_key'} or type(data.get('schema_version')) is not int or data['schema_version']!=2:
            raise ValueError('This Workshop save is outdated. Reload before saving.')
        key=uuid(data.get('request_key'));revision=data.get('revision')
        if type(revision) is not int or revision<0:raise ValueError('Missing layout revision')
        document=room_document(data.get('document'))
        digest=self._save_digest(data,document,actor)
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE')
            prior=db.execute('SELECT actor_id,digest,result FROM workshop_save_receipts WHERE group_id=? AND request_key=?',(group,key)).fetchone()
            if prior:
                if prior[0]!=actor or prior[1]!=digest:raise Conflict('This Workshop confirmation key belongs to a different save.')
                return json.loads(prior[2])
        self.validate_save(client,group,data)
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE')
            prior=db.execute('SELECT actor_id,digest,result FROM workshop_save_receipts WHERE group_id=? AND request_key=?',(group,key)).fetchone()
            if prior:
                if prior[0]!=actor or prior[1]!=digest:raise Conflict('This Workshop confirmation key belongs to a different save.')
                return json.loads(prior[2])
            row=db.execute('SELECT revision FROM plans WHERE group_id=?',(group,)).fetchone()
            if (row[0] if row else 0)!=revision:raise Conflict('The layout changed elsewhere. Reload before saving your edits.')
            current_row=db.execute('SELECT document FROM plans WHERE group_id=?',(group,)).fetchone()
            current=normalize_document(group,json.loads(current_row[0]) if current_row else None)
            self._validate_links(client,current,document)
            db.execute('INSERT INTO plans VALUES(?,?,?) ON CONFLICT(group_id) DO UPDATE SET revision=excluded.revision,document=excluded.document',(group,revision+1,json.dumps(document,separators=(',',':'))))
            stored=db.execute('SELECT revision,document FROM plans WHERE group_id=?',(group,)).fetchone()
            saved={'revision':stored[0],'schema_version':2,'stored_schema_version':2,'document':json.loads(stored[1]),'layout':None}
            db.execute('INSERT INTO workshop_save_receipts VALUES(?,?,?,?,?)',(group,key,actor,digest,json.dumps(saved,separators=(',',':'))))
        return saved
    @staticmethod
    def _save_digest(data,document,actor):
        intent={'schema_version':2,'revision':data['revision'],'document':document}
        return hashlib.sha256(json.dumps([actor,'workshop/save',intent],sort_keys=True,separators=(',',':')).encode()).hexdigest()
    @staticmethod
    def request_digest(actor_id,data):
        if not isinstance(data,dict) or set(data)!={'schema_version','revision','document','request_key'} or type(data.get('schema_version')) is not int or data['schema_version']!=2:
            raise ValueError('This Workshop save is outdated. Reload before saving.')
        uuid(data.get('request_key'))
        if type(data.get('revision')) is not int or data['revision']<0:raise ValueError('Missing layout revision')
        return Workshop._save_digest(data,room_document(data.get('document')),uuid(actor_id))
    def replay_save(self,group,data,*,actor_id):
        if not isinstance(data,dict) or set(data)!={'schema_version','revision','document','request_key'} or type(data.get('schema_version')) is not int or data['schema_version']!=2:
            raise ValueError('This Workshop save is outdated. Reload before saving.')
        group,actor,key=uuid(group),uuid(actor_id),uuid(data.get('request_key'))
        if type(data.get('revision')) is not int or data['revision']<0:raise ValueError('Missing layout revision')
        document=room_document(data.get('document'));digest=self._save_digest(data,document,actor)
        with closing(sqlite3.connect(self.path)) as db:
            row=db.execute('SELECT actor_id,digest,result FROM workshop_save_receipts WHERE group_id=? AND request_key=?',(group,key)).fetchone()
        if not row:return None
        if row[0]!=actor or row[1]!=digest:raise Conflict('This Workshop confirmation key belongs to a different save.')
        return json.loads(row[2])
    def save_status(self,group,request_key,*,actor_id):
        row=self.save_binding(group,request_key)
        if not row:return {'status':'not_started'}
        if row['actor_id']!=uuid(actor_id):raise Conflict('This Workshop confirmation key belongs to a different actor.')
        return {'status':'completed','action':'workshop/save','result':json.loads(row['result'])}
    def save_binding(self,group,request_key):
        with closing(sqlite3.connect(self.path)) as db:
            row=db.execute('SELECT actor_id,digest,result FROM workshop_save_receipts WHERE group_id=? AND request_key=?',(uuid(group),uuid(request_key))).fetchone()
        return {'actor_id':row[0],'digest':row[1],'result':row[2]} if row else None
    def snapshot(self,client,group):
        result=self.get(group);locations=[];all_locations=[]
        for summary in client.entities(True):
            e=client.entity(summary['id'])
            row={'id':e['id'],'name':e['name'],'parent_id':(e.get('parent') or {}).get('id'),'kind':text_field(e,'Storage kind') or 'Location','code':text_field(e,'Storage code') or '', 'updated_at':e.get('updatedAt'),'archived':bool(e.get('archived'))}
            all_locations.append(row)
            if not row['archived']:locations.append(row)
        result['locations']=locations;result['counts']={}
        equipment=client.entities()
        for e in equipment:
            if not e.get('archived'):
                parent=(e.get('parent') or {}).get('id');result['counts'][parent]=result['counts'].get(parent,0)+1
        parents=[dict(row,isLocation=True) for row in all_locations]
        for summary in equipment:
            parents.append({'id':summary['id'],'name':summary['name'],'parent_id':(summary.get('parent') or {}).get('id'),'kind':summary.get('entityType',{}).get('name') or 'Item','code':'','updated_at':summary.get('updatedAt'),'isLocation':False,'archived':bool(summary.get('archived'))})
        result['parents']=parents
        result['types']=KINDS;result['storage_types']=STORAGE;return result

def move_location(client,data):
    key=uuid(data.get('id'));entity=client.entity(key)
    if entity.get('archived'):raise ValueError('Choose an active item or location')
    parent=uuid(data['parent_id']) if data.get('parent_id') else None
    current=(entity.get('parent') or {}).get('id')
    if parent==current:return {'id':key,'parent_id':current}
    if entity.get('updatedAt')!=data.get('updated_at'):raise Conflict('This item or location changed. Reload it before moving.')
    code=text_field(entity,'Storage code')
    if code:
        for summary in client.entities(True):
            if summary['id']!=key and not summary.get('archived') and (summary.get('parent') or {}).get('id')==parent:
                sibling=client.entity(summary['id'])
                if (text_field(sibling,'Storage code') or '').casefold()==code.casefold():raise ValueError('That destination already contains storage code '+code)
    from hierarchy import validate_parent
    validate_parent(client,parent,key)
    payload=update_payload(entity);payload['parentId']=parent;client.call('/api/v1/entities/'+key,'PUT',payload)
    confirmed=client.entity(key)
    if (confirmed.get('parent') or {}).get('id')!=parent:raise Conflict('Move was not confirmed. Reload and inspect C-Crate before another attempt.')
    return {'id':key,'parent_id':parent}


ORDER_FIELD='Workshop shelf order'

def _order_request(data):
    if not isinstance(data,dict):raise ValueError('Invalid shelf order request')
    entity_id=uuid(data.get('entity_id'))
    updated_at=data.get('updated_at')
    if not isinstance(updated_at,str) or not updated_at:raise ValueError('Reload the rack before saving its shelf order')
    shelf_ids=data.get('shelf_ids')
    if shelf_ids is not None:
        if not isinstance(shelf_ids,list):raise ValueError('Shelf order must be a list of shelf IDs')
        shelf_ids=[uuid(value) for value in shelf_ids]
        if len(shelf_ids)!=len(set(shelf_ids)):raise ValueError('Shelf order contains duplicate shelves')
    return {'entity_id':entity_id,'updated_at':updated_at,'shelf_ids':shelf_ids}

def _shelf_order_state(client,rack_id):
    summaries=client.entities(True)
    summary=next((item for item in summaries if uuid(item['id'])==rack_id),None)
    if summary is None or summary.get('archived'):raise ValueError('Choose an active native rack')
    rack=client.entity(rack_id)
    if rack.get('archived') or not rack.get('entityType',{}).get('isLocation') or text_field(rack,'Storage kind')!='Rack':
        raise ValueError('Choose an active location with Storage kind Rack')
    existing=text_field(rack,ORDER_FIELD)
    shelves=[]
    for item in summaries:
        parent=(item.get('parent') or {}).get('id')
        if parent and uuid(parent)==rack_id and not item.get('archived'):
            child=client.entity(uuid(item['id']))
            if child.get('archived') or not child.get('entityType',{}).get('isLocation'):continue
            child_parent=(child.get('parent') or {}).get('id')
            if not child_parent or uuid(child_parent)!=rack_id:continue
            if text_field(child,'Storage kind')=='Shelf':shelves.append(uuid(child['id']))
    return rack,existing,sorted(shelves)

def _order_text(shelf_ids):
    if shelf_ids is None:return None
    value=json.dumps(shelf_ids,separators=(',',':'))
    if len(value.encode('utf-8'))>8000:raise ValueError('Native field value is too long')
    return value

def _write_order(client,rack,value):
    payload=update_payload(rack)
    matches=[field for field in payload['fields'] if field.get('name')==ORDER_FIELD]
    if value is None:payload['fields']=[field for field in payload['fields'] if field.get('name')!=ORDER_FIELD]
    else:
        field=matches[0] if matches else {'name':ORDER_FIELD,'type':'text'}
        field['textValue']=value
        if not matches:payload['fields'].append(field)
    client.call('/api/v1/entities/'+rack['id'],'PUT',payload)

def submit_shelf_order(client,jobs,group,actor,request_key,data):
    intent=_order_request(data);desired=_order_text(intent['shelf_ids'])
    prior=jobs.lookup(group,actor,'workshop_shelf_order',request_key,intent)
    if prior:
        if prior['status']=='completed':return {'id':prior['id'],'status':'completed','entity_id':prior['result_id']}
        raise Conflict('Shelf order needs Admin recovery; do not submit it again')
    rack,original,fingerprint=_shelf_order_state(client,intent['entity_id'])
    if rack.get('updatedAt')!=intent['updated_at']:raise Conflict('This rack changed. Reload it before saving the shelf order.')
    if intent['shelf_ids'] is not None and any(value not in fingerprint for value in intent['shelf_ids']):
        raise ValueError('Choose only immediate active Shelf children of this rack')
    job_context={'entity_id':intent['entity_id'],'desired':desired,'original':original,
                 'original_updated_at':intent['updated_at'],'rack_id':intent['entity_id'],'shelf_fingerprint':fingerprint}
    job=jobs.prepare(group,actor,'workshop_shelf_order',request_key,intent,context=job_context)
    if job['status']!='prepared':raise Conflict('Shelf order needs Admin recovery; do not submit it again')
    sent=False
    try:
        latest,current,children=_shelf_order_state(client,intent['entity_id'])
        if latest.get('updatedAt')!=intent['updated_at'] or current!=original or children!=fingerprint:
            raise Conflict('Rack metadata or immediate Shelf membership changed. Reload and review before saving.')
        jobs.sent(group,job['id'])
        sent=True
        _write_order(client,latest,desired)
        confirmed,current,children=_shelf_order_state(client,intent['entity_id'])
        if current!=desired or children!=fingerprint:raise Conflict('Shelf order was not confirmed; inspect the native rack before another update')
        jobs.bind(group,job['id'],intent['entity_id'])
        jobs.complete(group,job['id'])
    except Exception:
        current_job=jobs.detail(group,job['id'])
        if current_job['status']=='prepared':jobs.cancel(group,job['id'])
        elif sent and current_job['status'] in ('sent','review'):jobs.review(group,job['id'],'Shelf order update needs native inspection')
        raise
    return {'id':job['id'],'status':'completed','entity_id':intent['entity_id']}

def recover_shelf_order(client,jobs,group,job_id,outcome):
    job=jobs.detail(group,job_id)
    if job['kind']!='workshop_shelf_order':raise ValueError('Not a workshop shelf order')
    if job['status']=='completed':return {'id':job['id'],'status':'completed','entity_id':job['result_id']}
    if job['status']=='cancelled':return {'id':job['id'],'status':'cancelled'}
    if outcome not in ('complete','cancel'):raise ValueError('Choose complete or cancel')
    context=job['context']
    if job['status']=='prepared' and not context:
        if outcome=='cancel':
            jobs.cancel(group,job['id'])
            return {'id':job['id'],'status':'cancelled'}
        raise Conflict('No native update was sent; cancel the prepared shelf order')
    if job['status']=='prepared' and outcome=='complete':raise Conflict('No native update was sent; cancel the prepared shelf order')
    try:rack,current,children=_shelf_order_state(client,context['rack_id'])
    except Exception as error:
        jobs.review(group,job['id'],'Rack or Shelf membership is unavailable for inspection')
        raise Conflict('Rack or Shelf membership is unavailable; keep this order in review') from error
    if children!=context['shelf_fingerprint']:
        jobs.review(group,job['id'],'Immediate Shelf membership differs from the validated fingerprint')
        raise Conflict('Shelf membership changed; keep this order in review')
    if outcome=='complete' and current==context['desired']:
        if not job['result_id']:jobs.bind(group,job['id'],context['rack_id'])
        jobs.complete(group,job['id'])
        return {'id':job['id'],'status':'completed','entity_id':context['rack_id']}
    if outcome=='cancel' and current==context['original'] and not job['result_id']:
        jobs.cancel(group,job['id'])
        return {'id':job['id'],'status':'cancelled','entity_id':context['rack_id']}
    jobs.review(group,job['id'],'Native shelf order is neither the confirmed desired nor unchanged original value')
    raise Conflict('Native shelf order changed; inspect the rack and keep this task in review')
