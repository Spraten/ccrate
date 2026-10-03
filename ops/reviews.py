"""Explicit Admin condition review and native maintenance completion."""
from datetime import datetime,timezone
from ledger import uuid,Conflict
from conditions import STATES,condition,set_condition
def entries(client,entity_id):return client.call('/api/v1/entities/'+entity_id+'/maintenance')
def submit_review(client,jobs,group,actor,key,data,kind='review_condition'):
    job=jobs.prepare(group,actor,kind,key,data)
    if job['status']=='completed':return {'id':job['id'],'status':'completed','entity_id':job['result_id']}
    if job['status']!='prepared':raise Conflict('Review needs Admin recovery')
    try:
        entity=client.entity(uuid(data.get('entity_id')))
        if entity.get('entityType',{}).get('isLocation'):raise ValueError('Choose equipment for review')
        context={'entity_id':entity['id'],'date':datetime.now(timezone.utc).date().isoformat()}
        if kind=='review_condition':
            if data.get('state') not in STATES:raise ValueError('Unknown equipment condition')
            context.update(before=condition(entity),state=data['state'])
        else:
            entry=next((e for e in entries(client,entity['id']) if e['id']==uuid(data.get('maintenance_id'))),None)
            if not entry:raise ValueError('Unknown native maintenance entry')
            context.update(entry=entry)
        jobs.context(group,job['id'],**context);jobs.sent(group,job['id']);jobs.bind(group,job['id'],entity['id']);finish_review(client,jobs,group,job['id'])
    except Exception:
        if jobs.detail(group,job['id'])['status']=='prepared':jobs.cancel(group,job['id']);raise
        jobs.review(group,job['id'],'Admin review requires native verification');raise Conflict('Review interrupted; finish it in Admin recovery')
    return {'id':job['id'],'status':'completed','entity_id':entity['id']}
def finish_review(client,jobs,group,key):
    job=jobs.detail(group,key);c=job['context'];entity=client.entity(c['entity_id'])
    if job['kind']=='review_condition':
        if condition(entity) not in (c['before'],c['state']):raise Conflict('Condition changed outside this review')
        if condition(entity)!=c['state']:set_condition(client,entity['id'],c['state'])
        marker='[Kiosk review '+job['id']+']';found=[e for e in entries(client,entity['id']) if marker in e.get('description','')]
        if len(found)>1:raise Conflict('Duplicate review references need manual inspection')
        if not found:
            if c.get('entry_started'):raise Conflict('Review record outcome unknown; inspect native maintenance')
            jobs.context(group,key,entry_started=True)
            found=[client.call('/api/v1/entities/'+entity['id']+'/maintenance','POST',{'name':'Condition review: '+c['state'],'description':'Setup Admin explicitly confirmed this condition. '+marker,'completedDate':c['date'],'scheduledDate':'','cost':'0'})]
        jobs.record(group,key,'native_condition_review_verified',{'maintenance_id':found[0]['id'],'state':c['state']})
    else:
        before=c['entry'];current=next((e for e in entries(client,entity['id']) if e['id']==before['id']),None)
        if not current:raise Conflict('Maintenance entry was removed')
        if current['completedDate'] not in (before['completedDate'],c['date']):raise Conflict('Maintenance completion changed outside this review')
        if any(current[k]!=before[k] for k in ['name','description','scheduledDate','cost']):raise Conflict('Maintenance details changed outside this review')
        if current['completedDate']!=c['date']:
            payload=dict(current,completedDate=c['date']);client.call('/api/v1/maintenance/'+before['id'],'PUT',payload)
        verified=next(e for e in entries(client,entity['id']) if e['id']==before['id'])
        if verified['completedDate']!=c['date']:raise Conflict('Maintenance completion was not confirmed')
        jobs.record(group,key,'native_maintenance_completed',{'maintenance_id':before['id']})
    jobs.complete(group,key)
    return {'id':key,'status':'completed','entity_id':entity['id']}
def recover_review(client,jobs,group,key,outcome):
    job=jobs.detail(group,key)
    if outcome!='complete':raise Conflict('Started review must be verified and finished')
    if job['status']=='completed':return {'id':key,'status':'completed','entity_id':job['result_id']}
    return finish_review(client,jobs,group,key)
