"""Deliberately link a manufacturer code to native equipment with durable recovery."""
from ledger import Conflict,uuid
from native_fields import text_field,set_text_field
from scan_codes import manufacturer_code,MANUFACTURER_FIELD

def register_code(client,jobs,group,actor,key,data):
    job=jobs.prepare(group,actor,'register_code',key,data)
    if job['status']=='completed':return {'id':job['id'],'status':'completed','entity_id':job['result_id']}
    if job['status']!='prepared':raise Conflict('Code registration needs Admin recovery; do not submit again')
    try:
        code=manufacturer_code(data.get('code'));entity=client.entity(uuid(data.get('entity_id')))
        if entity.get('archived') or entity.get('entityType',{}).get('isLocation'):raise ValueError('Choose active equipment')
        previous=text_field(entity,MANUFACTURER_FIELD)
        if previous not in (None,'',code):raise Conflict('This item already has a manufacturer QR code. Review it in C-Crate before changing it')
        for summary in client.entities():
            if summary['id']!=entity['id'] and text_field(client.entity(summary['id']),MANUFACTURER_FIELD)==code:raise Conflict('This code already belongs to another item. Use an individual serial or C-Crate label')
        jobs.context(group,job['id'],entity_id=entity['id'],code=code)
        jobs.sent(group,job['id']);jobs.bind(group,job['id'],entity['id'])
        if previous!=code:set_text_field(client,entity,MANUFACTURER_FIELD,code)
        return recover_code(client,jobs,group,job['id'],'complete')
    except Exception:
        if jobs.detail(group,job['id'])['status']=='prepared':jobs.cancel(group,job['id']);raise
        jobs.review(group,job['id'],'Verify manufacturer QR field in C-Crate before finishing')
        raise Conflict('Registration interrupted. Check Admin recovery before trying again')

def recover_code(client,jobs,group,key,outcome):
    job=jobs.detail(group,key)
    if job['kind']!='register_code':raise ValueError('Not a code registration')
    if job['status']=='completed':return {'id':key,'status':'completed','entity_id':job['result_id']}
    if outcome!='complete':raise Conflict('Inspect the native manufacturer QR field before finishing')
    c=job['context'];entity=client.entity(c['entity_id'])
    if text_field(entity,MANUFACTURER_FIELD)!=c['code']:raise Conflict('Manufacturer QR code is not confirmed in C-Crate. Review the native record')
    jobs.record(group,key,'manufacturer_code_verified',{'entity_id':entity['id']});jobs.complete(group,key)
    return {'id':key,'status':'completed','entity_id':entity['id']}
