"""Native equipment category creation with a recoverable temporary name."""
from ledger import Conflict,uuid
from setup_native import text
PREFIX='Pending kiosk type '
def create_category(client,jobs,group,actor,key,data):
    job=jobs.prepare(group,actor,'create_type',key,data)
    if job['status']=='completed':return {'id':job['id'],'status':'completed','entity_id':job['result_id']}
    if job['status']!='prepared':raise Conflict('Category creation needs Admin recovery')
    try:
        name=text(data.get('name',''),'Category name',required=True)
        if name.startswith(PREFIX) or any(t['name'].casefold()==name.casefold() for t in client.call('/api/v1/entity-types')):raise ValueError('Choose a unique category name')
        jobs.context(group,job['id'],name=name);jobs.sent(group,job['id']);finish_category(client,jobs,group,job['id'],start=True)
    except Exception:
        if jobs.detail(group,job['id'])['status']=='prepared':jobs.cancel(group,job['id']);raise
        jobs.review(group,job['id'],'Native category creation requires verification');raise Conflict('Category creation interrupted; finish it in Admin recovery')
    return {'id':job['id'],'status':'completed','entity_id':jobs.detail(group,job['id'])['result_id']}
def find(client,job):
    types=client.call('/api/v1/entity-types')
    found=[t for t in types if t['id']==job['result_id']] if job['result_id'] else [t for t in types if t['name']==PREFIX+job['id']]
    if len(found)>1:raise Conflict('Multiple pending categories need manual review')
    return found[0] if found else None
def finish_category(client,jobs,group,key,start=False):
    job=jobs.detail(group,key);entity=find(client,job)
    if not entity:
        if not start or job['context'].get('creation_started'):raise Conflict('No native category found. Inspect Homebox before cancelling')
        jobs.context(group,key,creation_started=True);entity=client.call('/api/v1/entity-types','POST',{'name':PREFIX+job['id'],'isLocation':False,'icon':''})
    jobs.bind(group,key,entity['id'])
    if entity['name'] not in (PREFIX+job['id'],job['context']['name']) or entity['isLocation']:raise Conflict('Native category changed outside this creation')
    if entity['name']!=job['context']['name']:
        body={'name':job['context']['name'],'isLocation':False,'icon':entity.get('icon',''),'defaultTemplateId':entity.get('defaultTemplateId')};client.call('/api/v1/entity-types/'+entity['id'],'PUT',body)
    verified=find(client,jobs.detail(group,key))
    if verified['name']!=job['context']['name']:raise Conflict('Native category name was not confirmed')
    jobs.complete(group,key);return {'id':key,'status':'completed','entity_id':entity['id']}
def recover_category(client,jobs,group,key,outcome):
    job=jobs.detail(group,key)
    if job['status']=='completed':return {'id':key,'status':'completed','entity_id':job['result_id']}
    if outcome=='complete':return finish_category(client,jobs,group,key)
    if outcome!='cancel':raise ValueError('Choose finish or cancel')
    if find(client,job):raise Conflict('Category already exists. Finish its creation')
    jobs.cancel(group,key);return {'id':key,'status':'cancelled'}
