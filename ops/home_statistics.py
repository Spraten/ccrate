"""Bounded, privacy-preserving Home statistics projection."""
from datetime import datetime, timezone

from conditions import STATES, checkout_blocker, condition


def _location_paths(locations):
    by_id = {row.get('id'): row for row in locations if row.get('id')}
    paths = {}
    for location_id, location in by_id.items():
        parts = []
        seen = set()
        current_id = location_id
        while current_id and current_id in by_id and current_id not in seen:
            seen.add(current_id)
            current = by_id[current_id]
            name = current.get('name')
            if name:
                parts.append(str(name))
            parent = current.get('parent') or {}
            current_id = parent.get('id')
        paths[location_id] = ' / '.join(reversed(parts)) or str(location.get('name') or 'Location')
    return by_id, paths


def build_home_statistics(items, locations, loans, unresolved_assets, total_locations, total_tags):
    """Project native records and current collection ledgers to aggregate counts only."""
    location_by_id, location_paths = _location_paths(locations)
    loan_ids = {row.get('entity_id') for row in loans}
    unresolved_ids = set(unresolved_assets or ())
    conditions = {state: 0 for state in (*STATES, 'Unreviewed')}
    availability = {'available': 0, 'checked_out': 0, 'blocked': 0, 'unknown': 0}
    by_location = {}
    attention = {'needs_attention': 0, 'unreviewed': 0, 'missing_photo': 0, 'unassigned_location': 0}
    item_count = 0

    for item in items:
        if item.get('archived') or (item.get('entityType') or {}).get('isLocation'):
            continue
        item_count += 1
        state = condition(item)
        conditions[state] = conditions.get(state, 0) + 1
        if item.get('id') in loan_ids:
            availability['checked_out'] += 1
        elif item.get('id') in unresolved_ids:
            availability['blocked'] += 1
        elif state == 'Unreviewed':
            availability['unknown'] += 1
        elif checkout_blocker(item):
            availability['blocked'] += 1
        else:
            availability['available'] += 1

        if state == 'Unreviewed':
            attention['unreviewed'] += 1
        elif state != 'Ready':
            attention['needs_attention'] += 1
        if not any(attachment.get('type') == 'photo' for attachment in item.get('attachments', [])):
            attention['missing_photo'] += 1

        parent_id = (item.get('parent') or {}).get('id')
        if not parent_id or parent_id not in location_by_id:
            attention['unassigned_location'] += 1
            key = None
            bucket = by_location.setdefault(key, {'id': None, 'name': 'Unassigned', 'path': 'Unassigned', 'count': 0})
        else:
            location = location_by_id[parent_id]
            key = parent_id
            bucket = by_location.setdefault(key, {'id': parent_id, 'name': str(location.get('name') or 'Location'),
                                                   'path': location_paths[parent_id], 'count': 0})
        bucket['count'] += 1

    unassigned = by_location.pop(None, {'id': None, 'name': 'Unassigned', 'path': 'Unassigned', 'count': 0})
    named = sorted(by_location.values(), key=lambda row: (-row['count'], row['name'].casefold(), row['id']))
    top = named[:5]
    other_count = sum(row['count'] for row in named[5:])
    location_counts = top
    if other_count:
        location_counts.append({'id': None, 'name': 'Other', 'path': 'Other', 'count': other_count})
    location_counts.append(unassigned)

    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'totals': {'items': item_count, 'locations': int(total_locations), 'tags': int(total_tags)},
        'condition_counts': conditions,
        'availability_counts': availability,
        'location_counts': location_counts,
        'attention_counts': attention,
    }
