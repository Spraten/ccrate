"""Modular floor-plan geometry; all storage identities remain native Homebox."""
import json,pathlib,sqlite3,math
from uuid import uuid4
from ledger import uuid,Conflict
from native_fields import text_field,update_payload

KINDS=('Rack','Cabinet','Workbench','Table','Fence','Gate','Door','Area','Kiosk')
STORAGE=('Area','Rack','Shelf','Bin','Cabinet','Drawer','Workbench','Location')

def number(value,low,high,name):
    if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:raise ValueError(name+' is out of range')
    return round(value,3)

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

class Workshop:
    def __init__(self,path):
        self.path=pathlib.Path(path);self.path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        with sqlite3.connect(self.path) as db:db.execute('CREATE TABLE IF NOT EXISTS plans(group_id TEXT PRIMARY KEY,revision INTEGER NOT NULL,document TEXT NOT NULL)')
        self.path.chmod(0o600)
    def get(self,group):
        with sqlite3.connect(self.path) as db:row=db.execute('SELECT revision,document FROM plans WHERE group_id=?',(uuid(group),)).fetchone()
        return {'revision':row[0],'layout':json.loads(row[1])} if row else {'revision':0,'layout':None}
    def save(self,client,group,data):
        geometry=layout(data.get('layout'));revision=data.get('revision')
        if type(revision) is not int or revision<0:raise ValueError('Missing layout revision')
        locations={e['id'] for e in client.entities(True) if not e.get('archived')}
        if any(o['location_id'] and o['location_id'] not in locations for o in geometry['objects']):raise ValueError('A linked location was deleted or archived; choose an active location')
        with sqlite3.connect(self.path) as db:
            db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT revision FROM plans WHERE group_id=?',(uuid(group),)).fetchone()
            if (row[0] if row else 0)!=revision:raise Conflict('The layout changed elsewhere. Reload before saving your edits.')
            db.execute('INSERT INTO plans VALUES(?,?,?) ON CONFLICT(group_id) DO UPDATE SET revision=excluded.revision,document=excluded.document',(uuid(group),revision+1,json.dumps(geometry)))
        return self.get(group)
    def snapshot(self,client,group):
        result=self.get(group);locations=[]
        for summary in client.entities(True):
            e=client.entity(summary['id'])
            if e.get('archived'):continue
            locations.append({'id':e['id'],'name':e['name'],'parent_id':(e.get('parent') or {}).get('id'),'kind':text_field(e,'Storage kind') or 'Location','code':text_field(e,'Storage code') or '', 'updated_at':e.get('updatedAt')})
        result['locations']=locations;result['counts']={}
        for e in client.entities():
            if not e.get('archived'):
                parent=(e.get('parent') or {}).get('id');result['counts'][parent]=result['counts'].get(parent,0)+1
        result['types']=KINDS;result['storage_types']=STORAGE;return result

def move_location(client,data):
    key=uuid(data.get('id'));entity=client.entity(key)
    if not entity.get('entityType',{}).get('isLocation') or entity.get('archived'):raise ValueError('Choose an active storage location')
    parent=uuid(data['parent_id']) if data.get('parent_id') else None
    current=(entity.get('parent') or {}).get('id')
    if parent==current:return {'id':key,'parent_id':current}
    if entity.get('updatedAt')!=data.get('updated_at'):raise Conflict('This location changed. Reload it before moving.')
    code=text_field(entity,'Storage code')
    if code:
        for summary in client.entities(True):
            if summary['id']!=key and not summary.get('archived') and (summary.get('parent') or {}).get('id')==parent:
                sibling=client.entity(summary['id'])
                if (text_field(sibling,'Storage code') or '').casefold()==code.casefold():raise ValueError('That destination already contains storage code '+code)
    visited={key};ancestor=parent
    while ancestor:
        if ancestor in visited or len(visited)>64:raise ValueError('A location cannot be moved inside itself or its children')
        visited.add(ancestor);item=client.entity(ancestor)
        if not item.get('entityType',{}).get('isLocation') or item.get('archived'):raise ValueError('Choose an active destination location')
        ancestor=(item.get('parent') or {}).get('id')
    payload=update_payload(entity);payload['parentId']=parent;client.call('/api/v1/entities/'+key,'PUT',payload)
    confirmed=client.entity(key)
    if (confirmed.get('parent') or {}).get('id')!=parent:raise Conflict('Move was not confirmed. Reload and inspect Homebox before another attempt.')
    return {'id':key,'parent_id':parent}
