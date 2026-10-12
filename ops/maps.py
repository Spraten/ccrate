"""Versioned workshop geometry on native Homebox locations."""
import json
from ledger import uuid
from native_fields import text_field,set_text_field

ROOM_FIELD='Workshop map room'
OBJECT_FIELD='Workshop map object'
TYPES=('Shelf','Rack','Table','Cabinet','Cage','Workbench','Charging Station',
       'Maintenance Area','Quarantine Area','Door','Kiosk')


def decode(entity,name):
    value=text_field(entity,name)
    if value is None:return None
    data=json.loads(value)
    if not isinstance(data,dict) or data.get('version')!=1:raise ValueError('Unsupported workshop map format')
    return data


def integer(value,low,high,name):
    if type(value) is not int or not low<=value<=high:raise ValueError(name+' is outside the map grid')
    return value


def room_geometry(data):
    return {'version':1,'width':integer(data.get('width'),4,20,'Width'),
            'height':integer(data.get('height'),3,12,'Height')}


def object_geometry(data,room):
    x=integer(data.get('x'),0,room['width']-1,'Column')
    y=integer(data.get('y'),0,room['height']-1,'Row')
    width=integer(data.get('width'),1,room['width']-x,'Object width')
    height=integer(data.get('height'),1,room['height']-y,'Object height')
    kind=data.get('type','Shelf')
    if kind not in TYPES:raise ValueError('Unknown map object type')
    return {'version':1,'room_id':uuid(data.get('room_id')),'x':x,'y':y,'width':width,'height':height,'rotation':0,'type':kind}


def location(client,key):
    entity=client.entity(uuid(key))
    if not entity.get('entityType',{}).get('isLocation'):raise ValueError('Choose a native C-Crate location')
    if entity.get('archived'):raise ValueError('Archived locations cannot be placed on an active map')
    return entity


def ancestry(client,entity):
    result=[];visited=set()
    while entity:
        key=entity['id']
        if key in visited:raise ValueError('The native hierarchy contains a cycle; clear a parent to repair it')
        visited.add(key);result.append({'id':key,'name':entity['name']})
        parent=(entity.get('parent') or {}).get('id')
        entity=client.entity(parent) if parent else None
    return result


def list_map(client,entity_id=None):
    rooms=[];objects=[];unplaced=[];errors=[]
    for summary in client.entities(locations=True):
        if summary.get('archived'):continue
        entity=client.entity(summary['id'])
        try:
            room=decode(entity,ROOM_FIELD)
            placement=decode(entity,OBJECT_FIELD)
            if room:rooms.append({'id':entity['id'],'name':entity['name'],**room_geometry(room)})
            if placement:objects.append({'id':entity['id'],'name':entity['name'],**placement})
            if not room and not placement:unplaced.append({'id':entity['id'],'name':entity['name']})
        except (ValueError,TypeError,KeyError):errors.append({'id':entity['id'],'name':entity['name'],'error':'Map fields need review in C-Crate'})
    valid=[]
    for obj in objects:
        room=next((r for r in rooms if r['id']==obj.get('room_id')),None)
        try:
            if room is None:raise ValueError('Room missing')
            valid.append({'id':obj['id'],'name':obj['name'],**object_geometry(obj,room)})
        except (ValueError,TypeError):errors.append({'id':obj['id'],'name':obj['name'],'error':'Map placement needs review'})
    result={'rooms':rooms,'objects':valid,'unplaced':unplaced,'errors':errors,'types':TYPES,'path':[],'highlight_id':None,'room_id':None,'exact':False}
    if entity_id:
        entity=client.entity(uuid(entity_id));path=ancestry(client,entity);result['path']=list(reversed(path))
        chain=path if entity.get('entityType',{}).get('isLocation') else path[1:]
        for entry in chain:
            obj=next((o for o in valid if o['id']==entry['id']),None)
            if obj:
                result.update(highlight_id=obj['id'],room_id=obj['room_id'],exact=bool(chain and obj['id']==chain[0]['id']))
                break
            room=next((r for r in rooms if r['id']==entry['id']),None)
            if room:result['room_id']=room['id'];break
    return result


def rename(entity,data):
    name=data.get('name',entity['name'])
    if not isinstance(name,str) or not 1<=len(name.strip())<=255:raise ValueError('Location name must contain 1 to 255 characters')
    entity['name']=name.strip()

def save_room(client,key,data):
    entity=location(client,key);geometry=room_geometry(data)
    current=list_map(client)
    for obj in current['objects']:
        if obj['room_id']==entity['id']:object_geometry(obj,geometry)
    rename(entity,data)
    set_text_field(client,entity,ROOM_FIELD,json.dumps(geometry,sort_keys=True))
    return geometry


def save_object(client,key,data):
    entity=location(client,key);room=location(client,data.get('room_id'))
    if entity['id']==room['id']:raise ValueError('Place a shelf or other location inside the room')
    geometry=decode(room,ROOM_FIELD)
    if not geometry:raise ValueError('Configure the map room first')
    if room['id'] not in {p['id'] for p in ancestry(client,entity)[1:]}:
        raise ValueError('Location must belong to the selected room in C-Crate')
    placement=object_geometry(data,room_geometry(geometry))
    rename(entity,data)
    set_text_field(client,entity,OBJECT_FIELD,json.dumps(placement,sort_keys=True))
    return placement


def remove_object(client,key):
    entity=location(client,key)
    set_text_field(client,entity,OBJECT_FIELD,None)
    return {'removed':True}
