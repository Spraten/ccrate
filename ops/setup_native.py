"""Create native records once, with temporary native markers for recovery."""
import json,urllib.error
from ledger import Conflict,uuid
from attachments import photo_bytes,ensure_photo
from conditions import FIELD,NOTE_FIELD,condition,STATES
from native_fields import update_payload,text_field
from maps import ROOM_FIELD,room_geometry
from products import GTIN_FIELD,MARKER_FIELD,gtin,lookup,template_update


def text(value,name,maximum=255,required=False):
    if not isinstance(value,str) or len(value)>maximum or (required and not value.strip()):raise ValueError(name+' is missing or too long')
    return value.strip()


def prepare_location(client,data):
    name=text(data.get('name',''),'Name',required=True)
    parent=uuid(data['parent_id']) if data.get('parent_id') else None
    if parent:
        entity=client.entity(parent)
        if not entity.get('entityType',{}).get('isLocation') or entity.get('archived'):raise ValueError('Choose an active native parent location')
    types=client.call('/api/v1/entity-types')
    location_type=next(t for t in types if t['isLocation'])
    fields=[]
    if data.get('map_room'):fields.append({'name':ROOM_FIELD,'type':'text','textValue':json.dumps(room_geometry({'width':10,'height':6}),sort_keys=True)})
    return {'path':'/api/v1/entities','create':{'name':name,'description':text(data.get('description',''),'Description',1000),'quantity':0,'entityTypeId':location_type['id'],'parentId':parent},'fields':fields,'metadata':{},'location':True}


def prepare_product(client,data):
    code=gtin(data.get('gtin',''))
    if lookup(client,code)['product']:raise Conflict('This product barcode is already in the native catalog')
    name=text(data.get('name',''),'Product name',required=True)
    description=text(data.get('description',''),'Description',1000)
    fields=[{'name':GTIN_FIELD,'type':'text','textValue':code}]
    mpn=text(data.get('mpn',''),'Part number')
    if mpn:fields.append({'name':'Product MPN','type':'text','textValue':mpn})
    return {'path':'/api/v1/templates','create':{'name':name,'description':description,'defaultName':name,'defaultDescription':description,
        'defaultManufacturer':text(data.get('manufacturer',''),'Manufacturer'),'defaultModelNumber':text(data.get('model',''),'Model'),'defaultQuantity':1,'fields':fields},'template':True}


def prepare_asset(client,data):
    if data.get("photo"):photo_bytes(data["photo"])
    name=text(data.get('name',''),'Equipment name',required=True)
    serial=text(data.get('serial',''),'Serial number')
    destination=client.entity(uuid(data.get('location_id')))
    if not destination.get('entityType',{}).get('isLocation') or destination.get('archived'):raise ValueError('Scan or choose an active storage location')
    types=client.call('/api/v1/entity-types')
    type_id=uuid(data['type_id']) if data.get('type_id') else next(t['id'] for t in types if not t['isLocation'])
    if not any(t['id']==type_id and not t['isLocation'] for t in types):raise ValueError('Choose a native equipment type')
    if serial:
        for summary in client.entities():
            entity=client.entity(summary['id'])
            if entity.get('serialNumber')==serial:raise Conflict('This serial number already belongs to '+entity['name'])
    create={'name':name,'description':text(data.get('description',''),'Description',1000),'quantity':1,'entityTypeId':type_id,'parentId':destination['id']}
    result={'path':'/api/v1/entities','create':create,'fields':[],'metadata':{'serialNumber':serial},'location':False,'reviewed':bool(data.get('reviewed'))}
    if data.get('template_id'):
        template=client.call('/api/v1/templates/'+uuid(data['template_id']))
        if data.get('template_revision') and template['updatedAt']!=data['template_revision']:raise Conflict('Product details changed; look up the barcode again')
        if text_field(template,MARKER_FIELD):raise Conflict('Catalog template is still being created')
        result['path']='/api/v1/templates/'+template['id']+'/create-item'
        result['create']['tagIds']=[t['id'] for t in template.get('defaultTags',[])]
    else:
        result['metadata'].update(manufacturer=text(data.get('manufacturer',''),'Manufacturer'),modelNumber=text(data.get('model',''),'Model'))
        if data.get('gtin'):result['fields'].append({'name':GTIN_FIELD,'type':'text','textValue':gtin(data['gtin'])})
    if data.get('import_source_key'):
        key=text(data['import_source_key'],'Import source key',64,True)
        if len(key)!=64 or any(c not in '0123456789abcdef' for c in key):raise ValueError('Invalid import identity')
        for summary in client.entities():
            if text_field(client.entity(summary['id']),'Import source key')==key:raise Conflict('This source item is already in Homebox')
        for field,value in (('Import source key',key),('Import source',text(data.get('import_source',''),'Import source',120,True)),('Import external ID',text(data.get('import_external_id',''),'External ID')),('Import original condition',text(data.get('import_source_condition',''),'Original condition'))):
            if value:result['fields'].append({'name':field,'type':'text','textValue':value})
        state=data.get('import_condition','Unreviewed')
        if state not in ('Unreviewed',*STATES):raise ValueError('Unknown import condition')
        if state=='Ready' and data.get('reviewed') is not True:raise ValueError('Inspect equipment before marking it Ready')
        result['initial_state']=state
    return result


def submit(client,jobs,group,actor,kind,key,data):
    # Hash the user intent before refreshing native defaults, so a completed retry
    # resolves the same native UUID even if the catalog has subsequently changed.
    job=jobs.prepare(group,actor,kind,key,data)
    if job['status']=='completed':return {'id':job['id'],'status':'completed','entity_id':job['result_id']}
    if job['status']!='prepared':raise Conflict('Native task needs Admin recovery; do not create another copy')
    try:
        if kind=='create_location':plan=prepare_location(client,data)
        elif kind=='create_template':plan=prepare_product(client,data)
        elif kind=='create_asset':plan=prepare_asset(client,data)
        else:raise ValueError('Unsupported creation task')
        jobs.context(group,job['id'],plan=plan)
        jobs.sent(group,job['id'])
        perform_creation(client,jobs,group,job['id'],start=True)
    except (ValueError,Conflict):
        current=jobs.detail(group,job['id'])
        if current['status']=='prepared':jobs.cancel(group,job['id'])
        else:jobs.review(group,job['id'],'Native record creation or metadata requires verification')
        raise
    except Exception:
        jobs.review(group,job['id'],'Native record creation or metadata requires verification')
        raise Conflict('Creation interrupted. Review it from Admin before trying again')
    final=jobs.detail(group,job['id'])
    return {'id':job['id'],'status':'completed','entity_id':final['result_id']}


def marker_name(job):return 'Pending kiosk '+job['id']


def find_entity(client,job):
    if job['result_id']:return client.entity(job['result_id'])
    marker=job['context'].get('marker_id')
    if not marker:
        tags=[t for t in client.call('/api/v1/tags') if t['name']==marker_name(job)]
        if len(tags)>1:raise Conflict('Temporary native markers need manual review')
        marker=tags[0]['id'] if tags else None
    if not marker:return None
    found=[e for e in client.entities(locations=job['context']['plan']['location']) if any(t['id']==marker for t in e.get('tags',[]))]
    if len(found)>1:raise Conflict('More than one native record uses this pending marker; inspect Homebox')
    return client.entity(found[0]['id']) if found else None


def find_template(client,job):
    if job['result_id']:return client.call('/api/v1/templates/'+job['result_id'])
    found=[]
    for summary in client.call('/api/v1/templates'):
        template=client.call('/api/v1/templates/'+summary['id'])
        if text_field(template,MARKER_FIELD)==job['id']:found.append(template)
    if len(found)>1:raise Conflict('More than one native template uses the pending marker')
    return found[0] if found else None


def perform_creation(client,jobs,group,key,start=False):
    job=jobs.detail(group,key);plan=job['context'].get('plan')
    if not plan:raise Conflict('Native task has no verified creation plan; cancel it')
    if plan.get('template'):
        entity=find_template(client,job)
        if entity is None:
            if not start or job['context'].get('record_post_started'):raise Conflict('No native template was found. Inspect Homebox before cancelling this task')
            body=dict(plan['create']);body['fields']=list(body['fields'])+[{'name':MARKER_FIELD,'type':'text','textValue':job['id']}]
            jobs.context(group,key,record_post_started=True)
            entity=client.call(plan['path'],'POST',body)
        jobs.bind(group,key,entity['id'])
        # Remove only the temporary marker; the product remains a native template.
        entity=client.call('/api/v1/templates/'+entity['id']);payload=template_update(entity)
        payload['fields']=[f for f in entity.get('fields',[]) if f.get('name')!=MARKER_FIELD]
        client.call('/api/v1/templates/'+entity['id'],'PUT',payload)
        if text_field(client.call('/api/v1/templates/'+entity['id']),MARKER_FIELD) is not None:raise Conflict('Catalog marker cleanup needs verification')
    else:
        entity=find_entity(client,job)
        if entity is None:
            if not start or job['context'].get('record_post_started'):raise Conflict('No created native record was found. Inspect Homebox before cancelling this task')
            marker=client.call('/api/v1/tags','POST',{'name':marker_name(job),'description':'Temporary marker for recoverable kiosk creation','color':'#e5b34a'})
            jobs.context(group,key,marker_id=marker['id'],record_post_started=True)
            body=dict(plan['create']);body['tagIds']=list(body.get('tagIds',[]))+[marker['id']]
            entity=client.call(plan['path'],'POST',body)
        jobs.bind(group,key,entity['id'])
        entity=client.entity(entity['id'])
        if entity['name']!=plan['create']['name'] or (entity.get('parent') or {}).get('id')!=plan['create'].get('parentId'):
            raise Conflict('Native record changed outside the pending creation; inspect it before finishing')
        payload=update_payload(entity)
        for name,value in plan['metadata'].items():
            if entity.get(name,'') not in ('',value):raise Conflict('Native metadata changed outside this creation')
            payload[name]=value
        for desired in plan['fields']:
            existing=[f for f in payload['fields'] if f.get('name')==desired['name']]
            if len(existing)>1:raise Conflict('Duplicate native fields require review')
            if existing:
                if existing[0].get('textValue')!=desired['textValue']:raise Conflict('Native field changed outside this creation')
            else:payload['fields'].append(desired)
        if not plan['location']:
            state=condition(entity)
            if state not in ('Unreviewed','Ready',plan.get('initial_state')):raise Conflict('Equipment condition changed during enrollment; use Admin review')
            payload['fields']=[f for f in payload['fields'] if f.get('name') not in (FIELD,NOTE_FIELD)]
            desired_state=plan.get('initial_state','Ready' if plan['reviewed'] else 'Unreviewed')
            if desired_state!='Unreviewed':payload['fields'].append({'name':FIELD,'type':'text','textValue':desired_state})
            if desired_state=='Archived':payload['archived']=True
        client.call('/api/v1/entities/'+entity['id'],'PUT',payload)
        verified=client.entity(entity['id'])
        for name,value in plan['metadata'].items():
            if verified.get(name,'')!=value:raise Conflict('Native enrollment metadata was not confirmed')
        if not plan['location'] and condition(verified)!=plan.get('initial_state','Ready' if plan['reviewed'] else 'Unreviewed'):raise Conflict('Native enrollment condition was not confirmed')
        for desired in plan['fields']:
            if text_field(verified,desired['name'])!=desired['textValue']:raise Conflict('Native creation field was not confirmed')
        # Result ID is durable before removing the temporary native marker.
        marker=jobs.detail(group,key)['context'].get('marker_id')
        if marker:
            client.call('/api/v1/entities/'+entity['id'],'PATCH',{'tagIds':[t['id'] for t in verified.get('tags',[]) if t['id']!=marker]})
            try:client.call('/api/v1/tags/'+marker,'DELETE')
            except urllib.error.HTTPError as error:
                if error.code!=404:raise
    if not plan.get("template"):ensure_photo(client,jobs,group,key,entity["id"])
    jobs.complete(group,key)


def recover_creation(client,jobs,group,key,outcome):
    job=jobs.detail(group,key)
    if job['status'] not in ('prepared','sent','review'):raise Conflict('Native task is already resolved')
    if outcome=='complete':
        if job['status']=='prepared':raise Conflict('Nothing has been sent yet; cancel and submit again')
        perform_creation(client,jobs,group,key,start=False)
        return {'id':key,'status':'completed'}
    if outcome!='cancel':raise ValueError('Choose finish or cancel')
    plan=job['context'].get('plan')
    if job['result_id'] or (plan and (find_template(client,job) if plan.get('template') else find_entity(client,job))):
        raise Conflict('A native record already exists. Finish setup instead of cancelling it')
    marker=job['context'].get('marker_id')
    if marker:
        try:client.call('/api/v1/tags/'+marker,'DELETE')
        except urllib.error.HTTPError as error:
            if error.code!=404:raise
    jobs.cancel(group,key)
    return {'id':key,'status':'cancelled'}
