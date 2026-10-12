"""Preserve native entity metadata when changing a companion text field."""
import copy


def update_payload(entity):
    payload=copy.deepcopy(entity)
    payload['parentId']=(entity.get('parent') or {}).get('id')
    payload['entityTypeId']=entity['entityType']['id']
    payload['tagIds']=[t['id'] for t in entity.get('tags',[])]
    payload['fields']=copy.deepcopy(entity.get('fields') or [])
    return payload


def text_field(entity,name):
    matches=[f for f in entity.get('fields',[]) if f.get('name')==name]
    if not matches:return None
    if len(matches)!=1 or matches[0].get('type')!='text':raise ValueError(name+' needs review in C-Crate')
    return matches[0].get('textValue','')


def set_text_field(client,entity,name,value):
    payload=update_payload(entity)
    text_field(entity,name)
    matches=[f for f in payload['fields'] if f.get('name')==name]
    if value is None:
        payload['fields']=[f for f in payload['fields'] if f.get('name')!=name]
    else:
        if not isinstance(value,str) or len(value)>8000:raise ValueError('Native field value is too long')
        field=matches[0] if matches else {'name':name,'type':'text'}
        field['textValue']=value
        if not matches:payload['fields'].append(field)
    client.call('/api/v1/entities/'+entity['id'],'PUT',payload)
    result=client.entity(entity['id'])
    if text_field(result,name)!=value:raise ValueError('C-Crate did not confirm '+name)
    return result
