"""Journaled native condition and scheduled maintenance issue reporting."""
from datetime import datetime,timezone
from ledger import uuid,Conflict
from conditions import condition,condition_note,set_condition
from setup_native import text
STATES=('Needs Attention','Broken','Maintenance','Quarantined')
def marker(job):return '[Kiosk issue '+job['id']+']'
def submit_problem(client,jobs,group,actor,key,data):
    job=jobs.prepare(group,actor,'report_problem',key,data)
    if job['status']=='completed':return {'id':job['id'],'status':'completed','entity_id':job['result_id']}
    if job['status']!='prepared':raise Conflict('Problem report needs Admin recovery; do not submit another copy')
    try:
        entity=client.entity(uuid(data.get('entity_id')))
        if entity.get('entityType',{}).get('isLocation') or entity.get('archived'):raise ValueError('Choose active equipment')
        state=data.get('state','Needs Attention')
        if state not in STATES:raise ValueError('Choose a blocked equipment condition')
        note=text(data.get('note',''),'Problem description',1000,True)
        jobs.context(group,job['id'],entity_id=entity['id'],before=condition(entity),before_note=condition_note(entity),state=state,note=note,date=datetime.now(timezone.utc).date().isoformat())
        jobs.sent(group,job['id']);jobs.bind(group,job['id'],entity['id'])
        finish_problem(client,jobs,group,job['id'],start=True)
    except Exception:
        current=jobs.detail(group,job['id'])
        if current['status']=='prepared':jobs.cancel(group,job['id']);raise
        jobs.review(group,job['id'],'Problem report native changes require verification')
        raise Conflict('Report interrupted. Review it in Admin before submitting again')
    return {'id':job['id'],'status':'completed','entity_id':entity['id']}
def finish_problem(client,jobs,group,job_id,start=False):
    job=jobs.detail(group,job_id);c=job['context'];entity=client.entity(c['entity_id'])
    current=(condition(entity),condition_note(entity));before=(c['before'],c['before_note']);after=(c['state'],c['note'])
    if current not in (before,after):raise Conflict('Condition changed in Homebox; review the report manually')
    if current!=after:
        set_condition(client,entity['id'],c['state'],c['note'])
        jobs.record(group,job_id,'condition_verified',{'entity_id':entity['id']})
    entries=client.call('/api/v1/entities/'+entity['id']+'/maintenance')
    matches=[e for e in entries if marker(job) in e.get('description','')]
    if len(matches)>1:raise Conflict('Duplicate native maintenance references require review')
    if not matches:
        if c.get('maintenance_started'):raise Conflict('Maintenance outcome is unknown; verify Homebox before creating another entry')
        # This durable flag prevents a second POST after an uncertain response.
        jobs.context(group,job_id,maintenance_started=True)
        entry=client.call('/api/v1/entities/'+entity['id']+'/maintenance','POST',{'name':'Equipment issue: '+c['state'],'description':c['note']+'\n\n'+marker(job),'scheduledDate':c['date'],'completedDate':'','cost':'0'})
        matches=[entry]
    jobs.record(group,job_id,'maintenance_verified',{'maintenance_id':matches[0]['id'],'entity_id':entity['id']})
    jobs.complete(group,job_id)
    return {'id':job_id,'status':'completed','entity_id':entity['id']}
def recover_problem(client,jobs,group,job_id,outcome):
    job=jobs.detail(group,job_id)
    if job['kind']!='report_problem':raise ValueError('Not a problem report')
    if job['status']=='completed':return {'id':job_id,'status':'completed','entity_id':job['result_id']}
    if outcome!='complete':raise Conflict('A started report cannot be cancelled; verify its native condition and maintenance entry')
    return finish_problem(client,jobs,group,job_id)
