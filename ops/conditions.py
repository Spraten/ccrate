"""Equipment state lives in native fields, not a companion inventory table."""
import copy

FIELD = 'Equipment condition'
NOTE_FIELD = 'Equipment condition note'
STATES = ('Ready', 'Needs Attention', 'Maintenance', 'Quarantined',
          'Archived', 'Retired', 'Broken', 'Trashed')


def condition(entity):
    if entity.get('archived'):
        return 'Archived'
    fields = [f for f in entity.get('fields', []) if f.get('name') == FIELD]
    if len(fields) != 1 or fields[0].get('type') != 'text':
        return 'Unreviewed'
    state = fields[0].get('textValue')
    return state if state in STATES else 'Unreviewed'


def checkout_blocker(entity):
    if entity.get('entityType', {}).get('isLocation'):
        return 'Locations cannot be checked out'
    state = condition(entity)
    if state != 'Ready':
        return 'Condition: '+state
    if entity.get('quantity') != 1:
        return 'This workflow requires an individually tracked asset (quantity 1)'
    return None


def update_payload(entity, state):
    if state not in STATES:
        raise ValueError('Unknown equipment condition')
    if entity.get('entityType', {}).get('isLocation'):
        raise ValueError('Equipment condition cannot be applied to a location')
    payload = copy.deepcopy(entity)
    payload['parentId'] = (entity.get('parent') or {}).get('id')
    payload['entityTypeId'] = entity['entityType']['id']
    payload['tagIds'] = [tag['id'] for tag in entity.get('tags', [])]
    matches = [f for f in payload.get('fields', []) if f.get('name') == FIELD]
    if len(matches) > 1:
        raise ValueError('Duplicate condition fields require review in Homebox')
    if matches and matches[0].get('type') != 'text':
        raise ValueError('Condition field must be text; review it in Homebox')
    field = matches[0] if matches else {'name': FIELD, 'type': 'text'}
    field['textValue'] = state
    if not matches:
        payload.setdefault('fields', []).append(field)
    payload['archived'] = state == 'Archived'
    return payload


def set_condition(client, entity_id, state, note=None):
    before = client.entity(entity_id)
    payload=update_payload(before,state)
    if note is not None:
        if not isinstance(note,str) or len(note)>1000:raise ValueError('Condition note must be at most 1000 characters')
        matches=[f for f in payload['fields'] if f.get('name')==NOTE_FIELD]
        if len(matches)>1 or (matches and matches[0].get('type')!='text'):raise ValueError('Condition note field requires review in Homebox')
        field=matches[0] if matches else {'name':NOTE_FIELD,'type':'text'}
        field['textValue']=note
        if not matches:payload['fields'].append(field)
    client.call('/api/v1/entities/'+before['id'], 'PUT', payload)
    after = client.entity(entity_id)
    if condition(after) != state:
        raise ValueError('Homebox did not confirm the requested condition; review the asset')
    if note is not None and condition_note(after)!=note:raise ValueError('Homebox did not confirm the condition note')
    return after

def condition_note(entity):
    return next((f.get('textValue','') for f in entity.get('fields',[]) if f.get('name')==NOTE_FIELD and f.get('type')=='text'),'')
