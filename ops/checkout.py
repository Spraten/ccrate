"""Native validation around the approved operational ledger."""
from conditions import checkout_blocker
from ledger import Conflict,uuid
from kits import manifest,validate_checkout


def expand_cart_assets(client, cart_items):
    """Expand each selected cart root through its current native kit manifest."""
    if not isinstance(cart_items, list) or len(cart_items)>50:
        raise ValueError('Select at most 50 distinct checkout cart items')
    roots=[uuid(item) for item in cart_items]
    if len(roots)!=len(set(roots)):
        raise ValueError('Select distinct checkout cart items')
    assets=set()
    for root in roots:
        kit=manifest(client,root)
        if kit['kit']:
            assets.update(entity['id'] for entity in kit['entities'])
        else:
            assets.add(root)
    return sorted(assets)


def checkout_status_actor(ledger, group, request_key, badge_actor, service_actor):
    """Use the badge holder for checkout status, retaining service scope for other kiosk writes."""
    operation=ledger.request(group,request_key)
    return badge_actor if operation and operation['action']=='check_out' else service_actor


def confirm_checkout(client, ledger, group, actor, assets, request_key, session_valid, verified=None, kit_versions=None, cart_context=None):
    group,actor=uuid(group),uuid(actor)
    assets=[uuid(a) for a in assets]
    if not assets or len(assets)>50 or len(assets)!=len(set(assets)):
        raise ValueError('Select between 1 and 50 distinct assets')
    members=client.call('/api/v1/groups/members')
    if actor not in {m['id'] for m in members}:
        raise Conflict('Badge holder is no longer a C-Crate group member')
    snapshot=None
    if cart_context is not None:
        revision=cart_context.get('revision') if isinstance(cart_context,dict) else None
        items=cart_context.get('items') if isinstance(cart_context,dict) else None
        if isinstance(revision,bool) or not isinstance(revision,int) or revision<0 or not isinstance(items,list) or len(items)>50:
            raise ValueError('Checkout cart changed; reload the saved selection.')
        items=[uuid(item) for item in items]
        if len(items)!=len(set(items)) or set(expand_cart_assets(client,items))!=set(assets):
            raise Conflict('Checkout items do not match the saved cart selection and current kit manifests.')
        snapshot={'revision':revision,'items':sorted(items)}
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
    operation_context = operation_intent = None
    if snapshot is not None:
        operation_context = {'checkout_cart': snapshot}
        operation_intent = {'checkout_cart': snapshot}
    operation=ledger.begin(group,actor,'check_out',assets,request_key,context=operation_context,intent=operation_intent)
    ledger.complete(operation['id'])
    return {'id':operation['id'],'status':'completed','action':'check_out','count':len(assets)}
