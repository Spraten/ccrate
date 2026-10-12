"""Optional native parent edges for items and locations, with cycle checks."""
from ledger import uuid


def validate_parent(client, parent, entity_id=None):
    parent = uuid(parent) if parent else None
    seen = {uuid(entity_id)} if entity_id else set()
    ancestor = parent
    immediate = True
    while ancestor:
        if ancestor in seen:
            raise ValueError('An item or location cannot be placed inside itself or its descendants')
        seen.add(ancestor)
        entity = client.entity(ancestor)
        if immediate and entity.get('archived'):
            raise ValueError('Choose an active parent item or location')
        immediate = False
        ancestor = (entity.get('parent') or {}).get('id')
    return parent
