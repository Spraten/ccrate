"""Native kit manifests contain UUID references, never copied inventory."""
import hashlib,json
from ledger import uuid,Conflict
from native_fields import text_field,set_text_field
from conditions import checkout_blocker
FIELD='Equipment kit manifest'
def members(entity):
    raw=text_field(entity,FIELD)
    if raw is None:return None
    try:
        value=json.loads(raw)
        if value['version']!=1 or not isinstance(value['members'],list):raise ValueError()
        ids=[uuid(i) for i in value['members']]
        if not ids or len(ids)>49 or len(set(ids))!=len(ids) or entity['id'] in ids:raise ValueError()
        return ids
    except (ValueError,KeyError,TypeError):raise ValueError('Kit manifest needs review in Homebox')
def manifest(client,entity_id):
    found={};versions={};visiting=set()
    def visit(key):
        if key in visiting:raise ValueError('Kit manifest contains a cycle')
        if key in found:return
        if len(found)>=50:raise ValueError('A verified kit can contain at most 50 tracked records')
        entity=client.entity(uuid(key))
        if entity.get('entityType',{}).get('isLocation') or entity.get('quantity')!=1:raise ValueError('Kit contents must be individually tracked equipment')
        found[key]=entity;refs=members(entity)
        if refs is not None:
            versions[key]=hashlib.sha256(json.dumps(refs,separators=(',',':')).encode()).hexdigest()
            visiting.add(key)
            for child in refs:visit(child)
            visiting.remove(key)
    visit(uuid(entity_id));root=found[uuid(entity_id)]
    return {'kit':members(root) is not None,'root':root,'entities':list(found.values()),'versions':versions,'blockers':[{'id':e['id'],'name':e['name'],'reason':reason} for e in found.values() if (reason:=checkout_blocker(e))]}
def save(client,entity_id,ids):
    entity=client.entity(uuid(entity_id));ids=[uuid(i) for i in ids]
    if not ids:raise ValueError('Choose at least one expected component')
    draft=dict(entity);draft['fields']=[f for f in entity.get('fields',[]) if f.get('name')!=FIELD]+[{'name':FIELD,'type':'text','textValue':json.dumps({'version':1,'members':ids})}]
    class Proposed:
        def entity(self,key):return draft if key==entity['id'] else client.entity(key)
    manifest(Proposed(),entity['id'])
    return set_text_field(client,entity,FIELD,json.dumps({'version':1,'members':ids},sort_keys=True))
def validate_checkout(client,entities,verified,versions):
    selected={e['id'] for e in entities};verified=set(verified or []);versions=versions or {}
    for entity in entities:
        if members(entity) is None:continue
        kit=manifest(client,entity['id']);expected={e['id'] for e in kit['entities']}
        if not expected<=selected:raise Conflict(entity['name']+': kit is incomplete; include every expected component')
        if not expected<=verified:raise Conflict(entity['name']+': scan the kit and every expected component before checkout')
        if any(versions.get(key)!=value for key,value in kit['versions'].items()):raise Conflict('Kit manifest changed; review and scan its contents again')

def validate_return(client,entities,held,verified,versions):
    selected={e['id'] for e in entities};verified=set(verified or []);versions=versions or {}
    for row in held:
        entity=client.entity(row['entity_id'])
        if members(entity) is None:continue
        kit=manifest(client,entity['id']);expected={e['id'] for e in kit['entities']}
        if not selected & expected:continue
        if not expected<=selected:raise Conflict(entity['name']+': select the kit container and return its complete manifest')
        if not expected<=verified:raise Conflict(entity['name']+': scan every expected component before returning the kit')
        if any(versions.get(key)!=value for key,value in kit['versions'].items()):raise Conflict('Kit contents changed; review and scan the manifest again')
