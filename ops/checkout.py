"""Native validation around the approved operational ledger."""
from conditions import checkout_blocker
from ledger import Conflict,uuid
from kits import validate_checkout


def confirm_checkout(client, ledger, group, actor, assets, request_key, session_valid, verified=None, kit_versions=None):
    group,actor=uuid(group),uuid(actor)
    assets=[uuid(a) for a in assets]
    if not assets or len(assets)>50 or len(assets)!=len(set(assets)):
        raise ValueError('Select between 1 and 50 distinct assets')
    members=client.call('/api/v1/groups/members')
    if actor not in {m['id'] for m in members}:
        raise Conflict('Badge holder is no longer a Homebox group member')
    entities=[]
    for asset in assets:
        entity=client.entity(asset)
        entities.append(entity)
        reason=checkout_blocker(entity)
        if reason:
            raise Conflict(entity['name']+': '+reason)
    validate_checkout(client,entities,verified,kit_versions)
    if not session_valid():
        raise Conflict('Session ended; scan your badge again')
    operation=ledger.begin(group,actor,'check_out',assets,request_key)
    ledger.complete(operation['id'])
    return {'id':operation['id'],'status':'completed','action':'check_out','count':len(assets)}
