"""Journal native return changes before clearing custody; recover explicitly."""
import hashlib
from conditions import condition,condition_note,set_condition,checkout_blocker
from ledger import Conflict,uuid

RETURN_STATES=('Needs Attention','Maintenance','Quarantined','Broken')


def note_hash(note):return hashlib.sha256(note.encode()).hexdigest()
def parent_id(entity):return (entity.get('parent') or {}).get('id')


def normalize_targets(targets):
    if not isinstance(targets,list) or not 1<=len(targets)<=50:
        raise ValueError('Select between 1 and 50 assets')
    result=[]
    for target in targets:
        state=target.get('condition')
        if state is not None and state not in RETURN_STATES:
            raise ValueError('Use Admin review to mark equipment Ready, Archived, Retired or Trashed')
        note=target.get('note')
        if note is not None:
            if not isinstance(note,str) or len(note)>1000:raise ValueError('Note must be at most 1000 characters')
            note=note.strip()
            if state is None:raise ValueError('Select a changed condition before adding an issue note')
        result.append({'entity_id':uuid(target.get('entity_id')),'condition':state,
            'destination_id':uuid(target['destination_id']) if target.get('destination_id') else None,'note':note})
    if len({t['entity_id'] for t in result})!=len(result):raise ValueError('Asset selected more than once')
    return sorted(result,key=lambda t:t['entity_id'])


def confirm_return(client,ledger,group,actor,targets,request_key,session_valid):
    group,actor,key=uuid(group),uuid(actor),uuid(request_key)
    targets=normalize_targets(targets);assets=[t['entity_id'] for t in targets]
    members=client.call('/api/v1/groups/members')
    if actor not in {m['id'] for m in members}:raise Conflict('Badge holder is no longer a Homebox group member')
    if not session_valid():raise Conflict('Session ended; scan your badge again')
    prior=ledger.request(group,key)
    if prior:
        if prior['request_hash']!=ledger.request_digest(group,actor,'return',assets,targets):
            raise Conflict('Confirmation key was already used for a different return')
        if prior['status']=='completed':return result(prior['id'],len(assets))
        if prior['status']=='pending':ledger.review(prior['id'],'Interrupted return requires explicit Admin review')
        raise Conflict('This return needs Admin recovery; do not start another transaction')
    steps=[]
    for target in targets:
        entity=client.entity(target['entity_id'])
        if entity.get('entityType',{}).get('isLocation') or entity.get('quantity')!=1:
            raise ValueError('Return individually tracked equipment only')
        destination=target['destination_id'] or parent_id(entity)
        if not destination:raise ValueError(entity['name']+': scan a destination; no assigned location exists')
        place=client.entity(destination)
        if place.get('archived'):raise Conflict('Return destination is archived')
        if target['destination_id'] and not place.get('entityType',{}).get('isLocation'):
            raise ValueError('Destination must be a native Homebox location')
        if entity.get('syncChildEntityLocations') and destination!=parent_id(entity):
            raise Conflict('This container moves child equipment; use the kit workflow')
        if entity.get('archived') and target['condition'] is not None:
            raise Conflict('Archived equipment needs Admin review before changing condition')
        steps.append({'entity_id':entity['id'],'condition_before':condition(entity),
            'condition_after':target['condition'] or condition(entity),
            'parent_before':parent_id(entity),'parent_after':destination,
            'note_before_hash':note_hash(condition_note(entity)),'note_after':target['note']})
    if not session_valid():raise Conflict('Session ended; scan your badge again')
    operation=ledger.begin(group,actor,'return',assets,key,context={'steps':steps},intent=targets)
    try:
        apply_steps(client,ledger,operation['id'],steps)
        ledger.complete(operation['id'])
    except Exception:
        ledger.review(operation['id'],'Native return result or ledger completion requires verification')
        raise Conflict('Return interrupted. Custody is retained; finish it from Admin recovery')
    return result(operation['id'],len(assets))


def result(op,count):return {'id':op,'status':'completed','action':'return','count':count}


def apply_steps(client,ledger,op,steps):
    for step in steps:
        entity=client.entity(step['entity_id'])
        current_condition=condition(entity);current_parent=parent_id(entity)
        if current_condition not in (step['condition_before'],step['condition_after']):
            raise Conflict('Equipment condition changed outside the return; inspect it in Homebox')
        if current_parent not in (step['parent_before'],step['parent_after']):
            raise Conflict('Equipment destination changed outside the return; inspect it in Homebox')
        target_note=step['note_after'];current_note=condition_note(entity)
        if target_note is not None and note_hash(current_note) not in (step['note_before_hash'],note_hash(target_note)):
            raise Conflict('Condition note changed outside this return')
        if current_condition!=step['condition_after'] or (target_note is not None and current_note!=target_note):
            ledger.record(op,'native_condition_started',{'entity_id':entity['id'],'condition':step['condition_after']})
            entity=set_condition(client,entity['id'],step['condition_after'],target_note)
            ledger.record(op,'native_condition_verified',{'entity_id':entity['id'],'condition':step['condition_after']})
        if parent_id(entity)!=step['parent_after']:
            destination=client.entity(step['parent_after'])
            if not destination.get('entityType',{}).get('isLocation') or destination.get('archived'):
                raise Conflict('Destination no longer accepts returns')
            ledger.record(op,'native_destination_started',{'entity_id':entity['id'],'destination_id':step['parent_after']})
            client.call('/api/v1/entities/'+entity['id'],'PATCH',{'parentId':step['parent_after']})
            entity=client.entity(entity['id'])
            if parent_id(entity)!=step['parent_after']:raise Conflict('Homebox did not confirm destination')
            ledger.record(op,'native_destination_verified',{'entity_id':entity['id'],'destination_id':step['parent_after']})
        if condition(entity)!=step['condition_after']:raise Conflict('Homebox did not confirm condition')


def recover(client,ledger,group,op,outcome):
    record=ledger.detail(group,op)
    if record['status'] not in ('pending','review'):raise Conflict('Operation is already resolved')
    if record['status']=='pending':ledger.review(op,'Admin inspected an interrupted operation')
    steps=(record['context'] or {}).get('steps',[])
    if outcome=='complete':
        if record['action']=='return':
            if not steps:raise Conflict('Return plan is missing; use documented manual recovery')
            apply_steps(client,ledger,op,steps)
        else:
            members=client.call('/api/v1/groups/members')
            if record['actor_id'] not in {m['id'] for m in members}:raise Conflict('Original borrower is no longer a member')
            for entity_id in record['assets']:
                reason=checkout_blocker(client.entity(entity_id))
                if reason:raise Conflict(reason)
        ledger.reconcile(op,'complete','Open setup Admin confirmed the physical result and verified native values')
    elif outcome=='cancel':
        if record['action']=='return':
            if not steps:raise Conflict('Return plan is missing; use documented manual recovery')
            for step in steps:
                entity=client.entity(step['entity_id'])
                if condition(entity)!=step['condition_before'] or parent_id(entity)!=step['parent_before'] or note_hash(condition_note(entity))!=step['note_before_hash']:
                    raise Conflict('Native changes already occurred. Finish the return, or restore previous values in Homebox before cancelling')
        ledger.reconcile(op,'cancel','Open setup Admin confirmed no return changes and cancelled the incomplete operation')
    else:raise ValueError('Choose complete or cancel')
    return {'id':op,'status':'completed' if outcome=='complete' else 'cancelled'}
