"""Private group-scoped label templates and short-lived reviewed output."""
import base64
import copy
import hashlib
import io
import json
import math
import pathlib
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import UUID, uuid4

from ledger import Conflict
import label_render

SUPVAN_MM=(40,28); LETTER_MM=(60,40); SYNTHETIC_ID='10000000-0000-4000-8000-000000000001'
STARTER_LAYOUTS=('left','top','compact'); PROFILES=('supvan','letter')
MAX_BODY=1024*1024; MAX_ELEMENTS=128; MAX_TEXT=1000; MAX_IMAGE_BYTES=512*1024; MAX_IMAGE_PIXELS=12_000_000
STARTER_DOCUMENTS=json.loads((pathlib.Path(__file__).resolve().parents[1]/'label-ui/src/starter-documents.json').read_text())


def _uuid(value):
    try:return str(UUID(str(value)))
    except (ValueError,TypeError,AttributeError):raise ValueError('A valid group, actor or item ID is required') from None


def _canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def _digest(value):return hashlib.sha256(_canonical(value).encode('utf-8')).hexdigest()


def _shape(value, required, optional=()):
    if not isinstance(value,dict) or not set(required)<=set(value) or set(value)-set(required)-set(optional):
        raise ValueError('Invalid upstream label document schema')


def _finite_number(value, *, positive=False, nonnegative=False):
    return type(value) in (int,float) and math.isfinite(value) and (not positive or value>0) and (not nonnegative or value>=0)


def _element_aabb(element, pad=0):
    angle=math.radians(element['rotation']);c=abs(math.cos(angle));s=abs(math.sin(angle))
    half_w=(c*element['widthMm']+s*element['heightMm'])/2+pad
    half_h=(s*element['widthMm']+c*element['heightMm'])/2+pad
    cx=element['xMm']+element['widthMm']/2;cy=element['yMm']+element['heightMm']/2
    return cx-half_w,cy-half_h,cx+half_w,cy+half_h


def _remaining(deadline):
    remaining=deadline-time.monotonic()
    if remaining<=0:raise TimeoutError('Label preview exceeded the 20-second request budget; select fewer items or preview again')
    return remaining


def _starter(profile, layout):
    key=f'starter:{profile}:{layout}'
    if key not in STARTER_DOCUMENTS:raise ValueError('Unknown starter template')
    return copy.deepcopy(STARTER_DOCUMENTS[key])


def validate_document(document, profile):
    if profile not in PROFILES:raise ValueError('Unknown label profile')
    _shape(document,('schemaVersion','id','name','page','elements','guides'),('variables',))
    if document.get('schemaVersion')!=1 or not isinstance(document.get('id'),str) or not document['id'] or not isinstance(document.get('name'),str):raise ValueError('Invalid label document schema')
    document.setdefault('variables',{})
    if not isinstance(document['elements'],list) or not isinstance(document['guides'],list) or not isinstance(document['variables'],dict):raise ValueError('Invalid label document schema')
    _shape(document['page'],('widthMm','heightMm','orientation','marginTopMm','marginRightMm','marginBottomMm','marginLeftMm'))
    if document['page']['orientation'] not in ('portrait','landscape') or any(not _finite_number(document['page'].get(k),positive=k in ('widthMm','heightMm'),nonnegative=k.startswith('margin')) for k in ('widthMm','heightMm','marginTopMm','marginRightMm','marginBottomMm','marginLeftMm')):raise ValueError('Invalid page settings')
    width,height=SUPVAN_MM if profile=='supvan' else LETTER_MM
    page=document.get('page')
    if not isinstance(page,dict):raise ValueError('Document dimensions do not match selected profile')
    if profile=='supvan' and (page.get('widthMm')!=width or page.get('heightMm')!=height):raise ValueError('SUPVAN label size is fixed at 40 x 28 mm')
    if profile=='letter':
        width,height=page.get('widthMm'),page.get('heightMm')
        if any(type(x) not in (int,float) or not math.isfinite(x) or x<=0 for x in (width,height)):raise ValueError('Letter canvas dimensions must be finite and positive')
        pxw,pxh=round(width*300/25.4),round(height*300/25.4)
        if pxw>16384 or pxh>16384 or pxw*pxh>12_000_000:raise ValueError('Label dimensions exceed renderer limits')
    if len(document['elements'])>MAX_ELEMENTS:raise ValueError('A label may contain at most 128 elements')
    item_qrs=[element for element in document['elements'] if isinstance(element,dict) and element.get('type')=='qr']
    if len(item_qrs)!=1 or not item_qrs[0].get('visible'):raise ValueError('A printable label needs exactly one visible item QR')
    guide_ids=set()
    for guide in document['guides']:
        _shape(guide,('id','orientation','positionMm'))
        if not isinstance(guide['id'],str) or not guide['id'] or guide['id'] in guide_ids or guide['orientation'] not in ('horizontal','vertical') or not _finite_number(guide['positionMm']):raise ValueError('Invalid document guide')
        guide_ids.add(guide['id'])
    ids=set(); qr_elements=[]
    def walk(obj):
        if isinstance(obj,float) and not math.isfinite(obj):raise ValueError('Document numbers must be finite')
        if isinstance(obj,dict):
            for key,value in obj.items():
                if key in ('src','content') and isinstance(value,str) and re.match(r'https?://',value,re.I):raise ValueError('Remote images and URL content are not printable')
                if key in ('content','name','title') and isinstance(value,str) and len(value)>MAX_TEXT:raise ValueError('Label content exceeds 1000 characters')
                walk(value)
        elif isinstance(obj,list):
            for value in obj:walk(value)
    walk(document)
    for element in document['elements']:
        if not isinstance(element,dict):raise ValueError('Invalid label element')
        kind=element.get('type')
        if kind not in {'rect','line','circle','shape','text','image','qr','barcode','table'}:raise ValueError('Invalid label element type')
        common=('id','name','type','xMm','yMm','widthMm','heightMm','rotation','locked','visible')
        typed={
            'rect':('fillColor','strokeColor','strokeWidthMm','strokeStyle','cornerRadiusMm'),
            'line':('strokeColor','strokeWidthMm','strokeStyle','startCap','endCap'),
            'circle':('fillColor','strokeColor','strokeWidthMm','strokeStyle'),
            'shape':('kind','fillColor','strokeColor','strokeWidthMm','strokeStyle'),
            'text':('content','fontSizePt','fontWeight','align','color'),
            'image':('src',),'qr':('content','ecLevel','color','backgroundColor'),
            'barcode':('content','format','showText','lineColor'),
            'table':('columns','rows','fontSizePt','showHeader','headerBackground','borderColor','borderWidthMm','cellPaddingMm'),
        }[kind]
        optional=('fontFamily',) if kind=='text' else ('strokeStyle',) if kind in ('rect','line','circle','shape') else ('startCap','endCap') if kind=='line' else ()
        _shape(element,common+typed,optional)
        if kind=='text':element.setdefault('fontFamily','')
        if kind in ('rect','line','circle','shape'):element.setdefault('strokeStyle','solid')
        if kind=='line':element.setdefault('startCap','none');element.setdefault('endCap','none')
        eid=element.get('id')
        if not isinstance(eid,str) or not eid or eid in ids:raise ValueError('Invalid or duplicate element ID')
        if not isinstance(element['name'],str) or type(element['locked']) is not bool or type(element['visible']) is not bool:raise ValueError('Invalid label element metadata')
        ids.add(eid)
        for key in ('xMm','yMm','widthMm','heightMm','rotation'):
            value=element.get(key)
            if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('Element geometry must be finite')
        if element.get('widthMm',0)<=0 or element.get('heightMm',0)<=0:raise ValueError('Element dimensions must be positive')
        if element.get('type')=='text':
            family=element.get('fontFamily','')
            if family not in ('','DejaVu Sans'):raise ValueError('Only bundled DejaVu Sans is printable')
            floor=(2.25 if profile=='supvan' else 3)*72/25.4
            if not isinstance(element.get('content'),str) or not _finite_number(element.get('fontSizePt'),positive=True) or element.get('fontWeight') not in (400,700) or type(element.get('fontWeight')) is not int or element.get('align') not in ('left','center','right') or not isinstance(element.get('color'),str):raise ValueError('Invalid text element')
            if element.get('fontSizePt',0)<floor:raise ValueError('Text is below the printable size floor')
        if kind in ('rect','circle','shape','line'):
            if not all(isinstance(element.get(k),str) for k in (('strokeColor',) if kind=='line' else ('fillColor','strokeColor'))):raise ValueError('Invalid shape colors')
            if element.get('strokeStyle') not in ('solid','dashed','dotted'):raise ValueError('Invalid stroke style')
            if not _finite_number(element.get('strokeWidthMm'),positive=kind=='line',nonnegative=kind!='line'):raise ValueError('Invalid stroke width')
            if kind in ('rect','shape') and not _finite_number(element.get('cornerRadiusMm'),nonnegative=True) and kind=='rect':raise ValueError('Invalid rectangle corner radius')
            if kind=='line' and (element.get('startCap') not in ('none','arrow') or element.get('endCap') not in ('none','arrow')):raise ValueError('Invalid line caps')
            if kind=='shape' and element.get('kind') not in {'triangle','rightTriangle','diamond','parallelogram','trapezoid','pentagon','hexagon','octagon','star','star4','star6','arrow','chevron','plus'}:raise ValueError('Invalid shape kind')
            if not all(isinstance(element.get(k),str) for k in ('fillColor','strokeColor')) and kind!='line':raise ValueError('Invalid shape colors')
        if kind=='table':
            if not isinstance(element['columns'],list) or not element['columns'] or not isinstance(element['rows'],list) or not _finite_number(element['fontSizePt'],positive=True) or type(element['showHeader']) is not bool or not all(isinstance(element[k],str) for k in ('headerBackground','borderColor')) or not _finite_number(element['borderWidthMm'],nonnegative=True) or not _finite_number(element['cellPaddingMm'],nonnegative=True):raise ValueError('Invalid table element')
            seen_columns=set()
            for column in element['columns']:
                _shape(column,('id','title','widthMm'))
                if not isinstance(column['id'],str) or not column['id'] or column['id'] in seen_columns or not isinstance(column['title'],str) or not _finite_number(column['widthMm'],positive=True):raise ValueError('Invalid table column')
                seen_columns.add(column['id'])
            if any(not isinstance(row,list) or any(not isinstance(cell,str) for cell in row) for row in element['rows']):raise ValueError('Invalid table rows')
        if kind=='image' and not isinstance(element.get('src'),str):raise ValueError('Invalid image element')
        if element.get('type')=='qr':
            if not isinstance(element.get('content'),str) or element['content']!='{{item_path}}':raise ValueError('QR content is backend-bound to the item URL')
            if element.get('ecLevel') not in ('L','M','Q','H'):raise ValueError('Invalid QR error-correction level')
            if not isinstance(element.get('color'),str) or not isinstance(element.get('backgroundColor'),str) or element['color'].lower()!='#000000' or element['backgroundColor'].lower()!='#ffffff':raise ValueError('Printable item QR must be black on white')
            dpi=203.2 if profile=='supvan' else 300
            if element['widthMm']!=element['heightMm'] or abs(element['rotation']%90)>1e-8 or math.floor(math.floor(element['widthMm']*dpi/25.4)/37)<4:raise ValueError('QR must be square, unrotated by arbitrary angles, and provide at least four dots per module')
            left,top,right,bottom=_element_aabb(element)
            if min(left,top)<0 or right>width or bottom>height:raise ValueError('QR must fit inside the label')
            qr_elements.append(element)
        if kind=='barcode':
            if not isinstance(element['content'],str) or element['content']!='{{asset_code}}' or element['format'] not in ('CODE128','EAN13','EAN8','CODE39','ITF14','UPC') or type(element['showText']) is not bool or not isinstance(element['lineColor'],str):raise ValueError('Barcode content is bound to the native asset code')
        if element.get('type')=='image':_validate_image(element.get('src',''))
    for qr in qr_elements:
        qleft,qtop,qright,qbottom=_element_aabb(qr)
        for other in document['elements']:
            if other['id']==qr['id'] or not other.get('visible',True):continue
            pad=other.get('strokeWidthMm',0)
            left,top,right,bottom=_element_aabb(other,pad)
            if qleft<right and qright>left and qtop<bottom and qbottom>top:
                raise ValueError('QR elements cannot overlap other visible elements')
    for key,value in document['variables'].items():
        if not isinstance(key,str) or not isinstance(value,str):raise ValueError('Invalid label variable')
    return document


def _validate_image(src):
    if not isinstance(src,str) or not src:return
    match=re.fullmatch(r'data:image/(png|jpeg);base64,([A-Za-z0-9+/=]+)',src)
    if not match:raise ValueError('Images must be embedded PNG or JPEG files')
    try:raw=base64.b64decode(match.group(2),validate=True)
    except Exception:raise ValueError('Invalid embedded image') from None
    if len(raw)>MAX_IMAGE_BYTES:raise ValueError('Embedded image exceeds 512 KiB')
    from PIL import Image
    try:
        image=Image.open(io.BytesIO(raw)); image.verify(); image=Image.open(io.BytesIO(raw))
        if image.format not in ('PNG','JPEG') or image.width*image.height>MAX_IMAGE_PIXELS:raise ValueError('Embedded image exceeds pixel limits')
    except ValueError:raise
    except Exception:raise ValueError('Invalid embedded PNG or JPEG image') from None


def _native_values(entity):
    if not isinstance(entity,dict) or not entity.get('id') or not isinstance(entity.get('name',''),str):raise ValueError('Native item data is incomplete')
    name=entity.get('name',''); asset=entity.get('assetId') or ''
    if not isinstance(asset,str):raise ValueError('Native asset code is invalid')
    short_code=entity.get('shortCode','')
    if not isinstance(short_code,str):raise ValueError('Native item short code is invalid')
    display_id=entity.get('displayId','')
    if not isinstance(display_id,str):raise ValueError('Native display ID is invalid')
    warnings=[]
    if len(name)>MAX_TEXT:
        name=name[:MAX_TEXT];warnings.append('Item name exceeded the document limit and was shortened.')
    if len(asset)>MAX_TEXT:
        asset=asset[:MAX_TEXT];warnings.append('Asset code exceeded the document limit and was shortened.')
    if len(short_code)>MAX_TEXT:
        short_code=short_code[:MAX_TEXT];warnings.append('Short code exceeded the document limit and was shortened.')
    if len(display_id)>MAX_TEXT:
        display_id=display_id[:MAX_TEXT];warnings.append('Display ID exceeded the document limit and was shortened.')
    updated=entity.get('updatedAt')
    if not isinstance(updated,str) or not updated:raise ValueError('Native item version is unavailable; reload the item')
    return name,asset,short_code,display_id,updated,warnings


class LabelLayouts:
    def __init__(self,path,*,asset_root=None,renderer=None):
        self.path=pathlib.Path(path);self.path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        try:self.path.parent.chmod(0o700)
        except OSError:pass
        self.asset_root=pathlib.Path(asset_root).resolve() if asset_root else None
        self.renderer=renderer
        self._lock=threading.RLock()
        db=sqlite3.connect(self.path,timeout=2)
        try:
            db.executescript('''CREATE TABLE IF NOT EXISTS templates(group_id TEXT NOT NULL,id TEXT NOT NULL,revision INTEGER NOT NULL,name TEXT NOT NULL,profile TEXT NOT NULL,document TEXT NOT NULL,PRIMARY KEY(group_id,id));
            CREATE TABLE IF NOT EXISTS save_requests(group_id TEXT NOT NULL,actor_id TEXT NOT NULL,request_key TEXT NOT NULL,payload_hash TEXT NOT NULL,result TEXT NOT NULL,PRIMARY KEY(group_id,actor_id,request_key));
            CREATE TABLE IF NOT EXISTS reviews(id TEXT PRIMARY KEY,group_id TEXT NOT NULL,actor_id TEXT NOT NULL,created REAL NOT NULL,attached_job TEXT,resolved INTEGER NOT NULL DEFAULT 0,metadata TEXT NOT NULL,png BLOB NOT NULL);''')
        finally:db.close()
        self.path.chmod(0o600)

    @contextmanager
    def _conn(self,timeout=2,deadline=None):
        if deadline is not None:timeout=min(timeout,_remaining(deadline))
        timeout=max(.01,min(2,timeout))
        db=sqlite3.connect(self.path,timeout=timeout);db.row_factory=sqlite3.Row;db.execute(f'PRAGMA busy_timeout={int(timeout*1000)}')
        try:
            yield db
            if deadline is not None:_remaining(deadline)
            db.commit()
        except sqlite3.OperationalError as error:
            db.rollback()
            if 'locked' in str(error).lower() or 'busy' in str(error).lower():raise TimeoutError('Label storage is busy; try again') from None
            raise
        except Exception:
            db.rollback()
            raise
        finally:db.close()

    def _render(self,doc,profile,timeout=20):return label_render.render_document(doc,profile,asset_root=self.asset_root,timeout=timeout)

    def _render_one(self,doc,profile,timeout):
        return self.renderer(doc,profile) if self.renderer else self._render(doc,profile,timeout)

    def _starter_rows(self):
        return [{'id':f'starter:{p}:{layout}','revision':0,'name':_starter(p,layout)['name'],'profile':p,'document':_starter(p,layout)} for p in PROFILES for layout in STARTER_LAYOUTS]

    def list(self,group):
        group=_uuid(group)
        with self._conn() as db: rows=db.execute('SELECT id,revision,name,profile,document FROM templates WHERE group_id=? ORDER BY name,id',(group,)).fetchall()
        return self._starter_rows()+[self._row(row) for row in rows]

    @staticmethod
    def _row(row):return {'id':row['id'],'revision':row['revision'],'name':row['name'],'profile':row['profile'],'document':json.loads(row['document'])}

    def get(self,group,template_id):
        group=_uuid(group)
        if isinstance(template_id,str) and template_id.startswith('starter:'):
            parts=template_id.split(':')
            if len(parts)==3 and parts[1] in PROFILES and parts[2] in STARTER_LAYOUTS:return {'id':template_id,'revision':0,'name':_starter(parts[1],parts[2])['name'],'profile':parts[1],'document':_starter(parts[1],parts[2])}
            raise ValueError('Unknown starter template')
        with self._conn() as db:row=db.execute('SELECT id,revision,name,profile,document FROM templates WHERE group_id=? AND id=?',(group,_uuid(template_id))).fetchone()
        if not row:raise KeyError('Label template not found in this collection')
        return self._row(row)

    def save_result(self,group,actor,request_key):
        group,actor=_uuid(group),_uuid(actor)
        if not isinstance(request_key,str) or not request_key or len(request_key)>200:return None
        with self._conn() as db:row=db.execute('SELECT result FROM save_requests WHERE group_id=? AND actor_id=? AND request_key=?',(group,actor,request_key)).fetchone()
        return json.loads(row['result']) if row else None

    def save(self,group,actor,data):
        group,actor=_uuid(group),_uuid(actor)
        if not isinstance(data,dict):raise ValueError('Invalid template save')
        if len(_canonical(data).encode('utf-8'))>MAX_BODY:raise ValueError('Label document exceeds 1 MiB')
        key=data.get('request_key')
        if not isinstance(key,str) or not key or len(key)>200:raise ValueError('A Save request key is required')
        profile=data.get('profile');source_doc=copy.deepcopy(data.get('document'))
        if not isinstance(source_doc,dict):raise ValueError('Invalid label document')
        # Saved templates contain no current-item sample values.
        source_doc['variables']={'item_name':'Sample item','asset_code':'','short_code':'','display_id':'','item_path':f'/item/{SYNTHETIC_ID}'}
        doc=validate_document(source_doc,profile)
        name=data.get('name')
        if not isinstance(name,str) or not name.strip() or len(name)>120:raise ValueError('Template name is required (maximum 120 characters)')
        revision=data.get('revision')
        if type(revision) is not int or revision<0:raise ValueError('A template revision is required')
        template_id=data.get('id')
        if template_id is not None:
            if not isinstance(template_id,str) or template_id.startswith('starter:'):raise ValueError('Starter templates are immutable')
            template_id=_uuid(template_id)
        payload={'id':template_id,'revision':revision,'name':name.strip(),'profile':profile,'document':doc}
        digest=_digest(payload)
        if not self._lock.acquire(timeout=2):raise TimeoutError('Label storage is busy; try again')
        try:
            with self._conn() as db:
                db.execute('BEGIN IMMEDIATE')
                prior=db.execute('SELECT payload_hash,result FROM save_requests WHERE group_id=? AND actor_id=? AND request_key=?',(group,actor,key)).fetchone()
                if prior:
                    if prior['payload_hash']!=digest:raise Conflict('This Save key was already used for different template data')
                    return json.loads(prior['result'])
                if template_id is None:
                    if revision!=0:raise Conflict('A new template must start at revision zero')
                    template_id=str(uuid4());new_revision=1
                else:
                    current=db.execute('SELECT revision FROM templates WHERE group_id=? AND id=?',(group,template_id)).fetchone()
                    if not current:raise KeyError('Label template not found in this collection')
                    if current['revision']!=revision:raise Conflict('Template changed elsewhere; reload before saving')
                    new_revision=revision+1
                result={'id':template_id,'revision':new_revision,'name':name.strip(),'profile':profile,'document':{**doc,'id':template_id,'name':name.strip()}}
                db.execute('INSERT INTO templates(group_id,id,revision,name,profile,document) VALUES(?,?,?,?,?,?) ON CONFLICT(group_id,id) DO UPDATE SET revision=excluded.revision,name=excluded.name,profile=excluded.profile,document=excluded.document',(group,template_id,new_revision,result['name'],profile,_canonical(result['document'])))
                db.execute('INSERT INTO save_requests VALUES(?,?,?,?,?)',(group,actor,key,digest,_canonical(result)))
                return result
        finally:self._lock.release()

    def _load_item(self,client,entity_id,remaining=20):
        key=_uuid(entity_id);old_timeout=getattr(client,'timeout',None)
        if old_timeout is not None:client.timeout=max(.001,min(old_timeout,remaining))
        try:entity=client.entity(key)
        finally:
            if old_timeout is not None:client.timeout=old_timeout
        if _uuid(entity.get('id'))!=key or entity.get('archived'):raise ValueError('Choose a current active item')
        if entity.get('isLocation') is True or (entity.get('entityType') or {}).get('isLocation') is True:raise ValueError('Location labels are not available in the item-label workflow')
        return entity

    def _prepared_doc(self,template,profile,name,asset,short_code,display_id,path):
        doc=copy.deepcopy(template)
        values={'item_name':name,'asset_code':asset,'short_code':short_code,'display_id':display_id,'item_path':path};doc['variables']=values
        for element in doc['elements']:
            if element.get('type')=='qr':element['content']=path
        return doc

    def preview(self,client,group,actor,data,*,deadline=None):
        started=time.monotonic();deadline=deadline if deadline is not None else started+20
        group,actor=_uuid(group),_uuid(actor)
        if not isinstance(data,dict):raise ValueError('Invalid label preview')
        if len(_canonical(data).encode('utf-8'))>MAX_BODY:raise ValueError('Label document exceeds 1 MiB')
        mode=data.get('mode')
        if not self._lock.acquire(timeout=2):raise TimeoutError('Label preview is busy; try again')
        try:
            _remaining(deadline)
            if mode=='synthetic':
                profile=data.get('profile');doc=validate_document(data.get('document'),profile);sample=data.get('sample') or {}
                name=sample.get('item_name','Sample item');asset=sample.get('asset_code','');short_code=sample.get('short_code','');display_id=sample.get('display_id','')
                if not isinstance(name,str) or not isinstance(asset,str) or not isinstance(short_code,str) or not isinstance(display_id,str):raise ValueError('Invalid preview sample')
                warnings=[]
                if len(name)>180:name=name[:179]+'…';warnings.append('Item name was shortened to fit the label.')
                if len(asset)>120:asset=asset[:119]+'…';warnings.append('Asset code was shortened to fit the label.')
                if len(short_code)>120:short_code=short_code[:119]+'…';warnings.append('Short code was shortened to fit the label.')
                if len(display_id)>120:display_id=display_id[:119]+'…';warnings.append('Display ID was shortened to fit the label.')
                final=self._prepared_doc(doc,profile,name,asset,short_code,display_id,f'/item/{SYNTHETIC_ID}')
                rendered=self._render_one(final,profile,_remaining(deadline))
                response=self._response(rendered,profile,warnings+rendered.get('warnings',[]))
                _remaining(deadline)
                return response
            if mode=='item_draft':
                profile=data.get('profile');doc=validate_document(data.get('document'),profile)
                remaining=_remaining(deadline)
                entity=self._load_item(client,data.get('entity_id'),remaining);name,asset,short_code,display_id,updated,warnings=_native_values(entity)
                _remaining(deadline)
                final=self._prepared_doc(doc,profile,name,asset,short_code,display_id,f"/item/{_uuid(entity['id'])}")
                rendered=self._render_one(final,profile,_remaining(deadline))
                response=self._response(rendered,profile,warnings+rendered.get('warnings',[]))
                _remaining(deadline)
                return response
            if mode!='item':raise ValueError('Choose synthetic, item_draft or saved item preview')
            template=self.get(group,data.get('template_id'))
            requested_revision=data.get('template_revision')
            if type(requested_revision) is not int or requested_revision!=template['revision']:raise Conflict('Template revision changed; reload before preview')
            profile=template['profile'];doc=validate_document(template['document'],profile)
            entity_ids=data.get('entity_ids')
            if entity_ids is None:entity_ids=[data.get('entity_id')]
            if not isinstance(entity_ids,list) or not 1<=len(entity_ids)<=36:raise ValueError('Select 1 to 36 items')
            prepared=[]
            for entity_id in entity_ids:
                remaining=_remaining(deadline)
                entity=self._load_item(client,entity_id,remaining);name,asset,short_code,display_id,updated,warnings=_native_values(entity)
                _remaining(deadline)
                final=self._prepared_doc(doc,profile,name,asset,short_code,display_id,f"/item/{_uuid(entity['id'])}")
                prepared.append((entity,updated,warnings,final))
            remaining=_remaining(deadline)
            if self.renderer is None:
                rendered=label_render.render_documents([row[3] for row in prepared],[profile]*len(prepared),asset_root=self.asset_root,timeout=remaining)
            else:
                rendered=[self.renderer(row[3],profile) for row in prepared]
            _remaining(deadline)
            responses=[]
            with self._conn(timeout=2,deadline=deadline) as db:
                db.execute('BEGIN IMMEDIATE');self._purge_expired(db)
                for (entity,updated,warnings,_),image in zip(prepared,rendered):
                    _remaining(deadline)
                    review_id=str(uuid4());metadata={'profile':profile,'label_mm':[prepared[len(responses)][3]['page']['widthMm'],prepared[len(responses)][3]['page']['heightMm']],'dpi':203.2 if profile=='supvan' else 300,'width':image['width'],'height':image['height'],'sha256':image['sha256'],'template_id':template['id'],'template_revision':template['revision'],'template_hash':_digest(template['document']),'item_id':_uuid(entity['id']),'item_updated_at':updated,'item_display_id':entity.get('displayId',''),'warnings':warnings+image.get('warnings',[])}
                    db.execute('INSERT INTO reviews(id,group_id,actor_id,created,metadata,png) VALUES(?,?,?,?,?,?)',(review_id,group,actor,time.time(),_canonical(metadata),image['png']))
                    responses.append({**self._response(image,profile,metadata['warnings']),'label_mm':metadata['label_mm'],'review_id':review_id,'item_updated_at':updated,'template_id':template['id'],'template_revision':template['revision']})
            return {'reviews':responses} if len(responses)>1 or data.get('entity_ids') is not None else responses[0]
        finally:self._lock.release()

    def save_legacy_review(self,group,actor,entity,png,width,height):
        group,actor,entity_id=_uuid(group),_uuid(actor),_uuid(entity.get('id'))
        if not isinstance(png,bytes) or len(png)>MAX_BODY:raise ValueError('Legacy label preview is too large')
        if (width,height)!=(320,208):raise ValueError('Legacy location previews require 40 x 28 mm SUPVAN stock')
        review_id=str(uuid4())
        metadata={'kind':'legacy_location','profile':'supvan','label_mm':[40,28],'dpi':203.2,'width':width,'height':height,'sha256':hashlib.sha256(png).hexdigest(),'item_id':entity_id,'item_updated_at':entity.get('updatedAt'),'item_display_id':entity.get('displayId','')}
        with self._conn(timeout=2) as db:
            db.execute('BEGIN IMMEDIATE');self._purge_expired(db)
            db.execute('INSERT INTO reviews(id,group_id,actor_id,created,metadata,png) VALUES(?,?,?,?,?,?)',(review_id,group,actor,time.time(),_canonical(metadata),png))
        return review_id

    @staticmethod
    def _response(rendered,profile,warnings):
        image=base64.b64encode(rendered['png']).decode('ascii')
        return {'image':'data:image/png;base64,'+image,'width':rendered['width'],'height':rendered['height'],'sha256':rendered['sha256'],'profile':profile,'warnings':list(warnings)}

    @staticmethod
    def _purge_expired(db):db.execute('DELETE FROM reviews WHERE attached_job IS NULL AND resolved=0 AND created<?',(time.time()-86400,))

    def review(self,group,actor,review_id):
        group,actor=_uuid(group),_uuid(actor)
        if not isinstance(review_id,str):return None
        with self._conn() as db:
            self._purge_expired(db)
            row=db.execute('SELECT * FROM reviews WHERE id=? AND group_id=? AND actor_id=?',(review_id,group,actor)).fetchone()
        if not row:return None
        meta=json.loads(row['metadata'])
        if row['resolved']:return None
        return {**meta,'review_id':row['id'],'group_id':group,'actor_id':actor,'attached_job':row['attached_job'],'created':row['created'],'png':bytes(row['png'])}

    def attach_review(self,group,actor,review_id,job_id):
        group,actor=_uuid(group),_uuid(actor)
        if not isinstance(job_id,str) or not job_id:raise ValueError('A print job ID is required')
        with self._conn() as db:
            db.execute('BEGIN IMMEDIATE');self._purge_expired(db);row=db.execute('SELECT attached_job FROM reviews WHERE id=? AND group_id=? AND actor_id=? AND resolved=0',(review_id,group,actor)).fetchone()
            if not row:raise KeyError('Reviewed label is missing or expired')
            if row['attached_job'] not in (None,job_id):raise Conflict('Reviewed label is already attached to another print job')
            db.execute('UPDATE reviews SET attached_job=? WHERE id=?',(job_id,review_id))

    def resolve_review(self,group,review_id):
        group=_uuid(group)
        with self._conn() as db:
            db.execute('BEGIN IMMEDIATE');db.execute('UPDATE reviews SET resolved=1,png=X\'\',metadata=? WHERE group_id=? AND id=?',('{}',group,review_id))

    def reconcile_reviews(self,group,jobs):
        group=_uuid(group)
        with self._conn() as db:rows=db.execute('SELECT id,attached_job FROM reviews WHERE group_id=? AND attached_job IS NOT NULL AND resolved=0',(group,)).fetchall()
        for row in rows:
            try:state=jobs.detail(group,row['attached_job'])['status']
            except ValueError:continue
            if state in ('completed','cancelled'):self.resolve_review(group,row['id'])
