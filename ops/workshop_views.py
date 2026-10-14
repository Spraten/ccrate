"""Read-only native selection and setup coverage for Workshop views."""
from datetime import datetime, timezone
from uuid import UUID
from urllib.parse import parse_qs, urlsplit

from hierarchy import validate_parent
from native_fields import text_field
from scan_codes import normalize, resolve_equipment, unique_entities
from conditions import condition, checkout_blocker
import json
import math

LEGACY_FIELDS = ('Workshop map room', 'Workshop map object')
_READ_MESSAGE = 'Native inventory could not be read; refresh and try again.'


class _NativeUnavailable(ValueError):
    pass


def _uuid(value):
    return str(UUID(str(value)))


def _parent(entity):
    return (entity.get('parent') or {}).get('id')


class _Graph:
    """One tenant-scoped snapshot per query, with full records fetched once."""
    def __init__(self, client):
        self.client = client
        self.nodes = {}
        self.summaries = {}
        self.read_errors = {}
        self.errors = []
        for locations in (True, False):
            try:
                rows = client.entities(locations=locations)
            except (RuntimeError, OSError):
                self.errors.append({'code': 'native_read_unavailable', 'entity_id': None,
                                   'drawing_id': None, 'message': _READ_MESSAGE})
                continue
            for row in rows:
                try:
                    key = _uuid(row['id'])
                except (KeyError, ValueError, TypeError):
                    continue
                self.summaries.setdefault(key, row)
        for key in self.summaries:
            self.get(key)

    def get(self, key):
        if not key:
            return None
        try:
            key = _uuid(key)
        except (ValueError, TypeError):
            return None
        if key not in self.nodes:
            try:
                entity = self.client.entity(key)
            except KeyError:
                self.nodes[key] = None
            except (RuntimeError, OSError):
                self.nodes[key] = None
                self.read_errors[key] = True
                self.errors.append({'code': 'native_read_unavailable', 'entity_id': key,
                                    'drawing_id': None, 'message': _READ_MESSAGE})
            else:
                if _uuid(entity['id']) != key:
                    raise ValueError('Native entity identity did not match')
                self.nodes[key] = entity
        return self.nodes[key]

    def active(self, key):
        entity = self.get(key)
        return entity if entity and not entity.get('archived') else None

    def is_location(self, entity):
        return bool(entity.get('entityType', {}).get('isLocation'))

    def path(self, key):
        entity = self.get(key)
        if not entity or entity.get('archived'):
            if key in self.read_errors:
                raise _NativeUnavailable(_READ_MESSAGE)
            raise ValueError('Native entity is unavailable')
        rows, seen = [], set()
        while entity:
            current = _uuid(entity['id'])
            if current in seen:
                raise ValueError('Native hierarchy contains a cycle')
            seen.add(current)
            rows.append({'id': current, 'name': entity.get('name') or '',
                         'is_location': self.is_location(entity), 'parent_id': _parent(entity)})
            parent = _parent(entity)
            if not parent:
                break
            parent_id = _uuid(parent)
            # Validate each edge through the shared ancestry safeguard. It reads only.
            validate_parent(_CachedClient(self), parent_id, current)
            entity = self.get(parent_id)
            if not entity:
                if parent_id in self.read_errors:
                    raise _NativeUnavailable(_READ_MESSAGE)
                raise ValueError('Native ancestor is unavailable in this tenant')
            if entity.get('archived'):
                raise ValueError('Native ancestry includes an archived entity')
        return list(reversed(rows))


class _CachedClient:
    def __init__(self, graph):
        self.graph = graph

    def entity(self, key):
        entity = self.graph.get(key)
        if entity is None:
            if _uuid(key) in self.graph.read_errors:
                raise _NativeUnavailable(_READ_MESSAGE)
            raise ValueError('Native ancestor is unavailable in this tenant')
        return entity


def _layout(layout_state):
    if not isinstance(layout_state, dict):
        return None, []
    layout = layout_state.get('layout')
    if layout is None and isinstance(layout_state.get('objects'), list):
        layout = layout_state
    if not isinstance(layout, dict):
        return None, []
    objects = layout.get('objects')
    return layout, objects if isinstance(objects, list) else []


def _drawings(objects):
    result = []
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        try:
            drawing_id = _uuid(obj.get('id'))
            location_id = _uuid(obj['location_id']) if obj.get('location_id') else None
        except (ValueError, TypeError):
            continue
        result.append((obj, drawing_id, location_id))
    return result


def _room_drawings(graph, layout_state):
    document = layout_state.get('document', layout_state) if isinstance(layout_state, dict) else None
    if not isinstance(document, dict) or document.get('version') != 2:
        layout, objects = _layout(layout_state)
        return _drawings(objects), []
    plans = document.get('rooms')
    if not isinstance(plans, list):
        return [], [{'code': 'room_plan_review', 'entity_id': None, 'drawing_id': None,
                     'message': 'Workshop room plans need review.'}]
    drawings, errors = [], []
    for plan in plans:
        if not isinstance(plan, dict):
            errors.append({'code': 'room_plan_review', 'entity_id': None, 'drawing_id': None,
                           'message': 'Workshop room plan needs review.'})
            continue
        try:
            room_id = _uuid(plan.get('id'))
            root_id = _uuid(plan['location_id']) if plan.get('location_id') is not None else None
        except (ValueError, TypeError, KeyError):
            errors.append({'code': 'room_plan_review', 'entity_id': None, 'drawing_id': None,
                           'message': 'Workshop room plan identity needs review.'})
            continue
        root = None
        root_path = None
        if root_id:
            try:
                root = graph.active(root_id)
                if not root or not graph.is_location(root):
                    raise ValueError()
                root_path = graph.path(root_id)
            except (ValueError, TypeError, KeyError):
                errors.append({'code': 'room_root_unavailable', 'entity_id': root_id,
                               'drawing_id': None, 'room_id': room_id,
                               'room_name': plan.get('name') or '',
                               'message': 'Linked room root is unavailable or needs review.'})
        else:
            root_path = []
        if root_id and root_path is not None:
            drawings.append((None, None, root_id, room_id, plan.get('name') or '', root_id,
                             root.get('name') or ''))
        for obj in plan.get('objects', []) if isinstance(plan.get('objects'), list) else []:
            try:
                drawing_id = _uuid(obj.get('id'))
                location_id = _uuid(obj['location_id']) if obj.get('location_id') is not None else None
            except (ValueError, TypeError, KeyError, AttributeError):
                continue
            context = (room_id, plan.get('name') or '', root_id, root.get('name') or '' if root else '')
            if not location_id:
                drawings.append((obj, drawing_id, None, *context))
                continue
            try:
                linked = graph.active(location_id)
                linked_path = graph.path(location_id) if linked and graph.is_location(linked) else None
                if linked_path is None or (root_id and (root_path is None or root_id not in
                        [row['id'] for row in linked_path if row['is_location']])):
                    raise ValueError()
            except (ValueError, TypeError, KeyError):
                errors.append({'code': 'room_link_unavailable', 'entity_id': location_id,
                               'drawing_id': drawing_id, 'room_id': room_id,
                               'room_name': plan.get('name') or '',
                               'root_location_id': root_id, 'root_name': root.get('name') or '' if root else '',
                               'message': 'Room drawing link is unavailable or outside its linked root.'})
                continue
            drawings.append((obj, drawing_id, location_id, *context))
    return drawings, errors


def _coverage(graph, drawings):
    rows = []
    linked = {}
    for entry in drawings:
        obj, drawing_id, location_id = entry[:3]
        room_id, room_name, root_id, root_name = (entry[3:7] if len(entry) > 3 else (None, '', None, ''))
        if not location_id:
            if drawing_id is not None:
                rows.append({'location_id': None, 'drawing_id': drawing_id, 'kind': 'drawing_only',
                             'covered_by': None, 'matches': [], 'message': 'Drawing has no native location link.',
                             **({'room_id': room_id, 'room_name': room_name,
                                 'root_location_id': root_id, 'root_name': root_name} if room_id else {})})
            continue
        entity = graph.get(location_id)
        if not entity or entity.get('archived') or not graph.is_location(entity):
            rows.append({'location_id': location_id, 'drawing_id': drawing_id, 'kind': 'unavailable',
                         'covered_by': None, 'matches': [], 'message': 'Linked native location is unavailable; review the link.'})
            continue
        linked.setdefault(location_id, []).append({'room_id': room_id, 'drawing_id': drawing_id,
                                                   'location_id': location_id, 'name': entity.get('name') or '',
                                                   **({'room_name': room_name, 'root_location_id': root_id,
                                                       'root_name': root_name} if room_id else {})})
    for key, entity in graph.nodes.items():
        if not entity or entity.get('archived') or not graph.is_location(entity):
            continue
        try:
            for field in LEGACY_FIELDS:
                value = text_field(entity, field)
                if value is not None:
                    rows.append({'location_id': key, 'drawing_id': None, 'kind': 'legacy_review',
                                 'covered_by': None, 'matches': [],
                                 'message': field+' is a legacy native map field and needs review.'})
        except (ValueError, TypeError):
            rows.append({'location_id': key, 'drawing_id': None, 'kind': 'legacy_review',
                         'covered_by': None, 'matches': [], 'message': 'Legacy native map fields need review.'})
    for location_id, entity in graph.nodes.items():
        if not entity or entity.get('archived') or not graph.is_location(entity):
            continue
        try:
            path = graph.path(location_id)
        except (ValueError, TypeError, KeyError):
            rows.append({'location_id': location_id, 'drawing_id': None, 'kind': 'unavailable',
                         'covered_by': None, 'matches': [], 'message': 'Native ancestry needs review.'})
            continue
        ancestors = [p['id'] for p in path if p['is_location']]
        matches = next((linked[key] for key in reversed(ancestors) if key in linked), [])
        if matches:
            chosen = matches[0]['location_id']
            kind = 'multiple' if len(matches) > 1 else ('exact' if chosen == location_id else 'containing')
            rows.append({'location_id': location_id, 'drawing_id': None, 'kind': kind,
                         'covered_by': chosen, 'matches': matches,
                         'message': 'Covered by a linked native location.' if kind != 'multiple' else 'Several drawings represent the linked location.'})
        else:
            rows.append({'location_id': location_id, 'drawing_id': None, 'kind': 'unmapped',
                         'covered_by': None, 'matches': [], 'message': 'No active linked drawing covers this location.'})
    rows.extend({'location_id': key, 'drawing_id': match['drawing_id'], 'kind': 'exact',
                 'covered_by': key, 'matches': [match], 'message': 'Native location is linked to this drawing.'}
                for key, matches in linked.items() for match in matches)
    return rows


def _scoped_equipment(graph, location_id, include_nested):
    try:
        root_id = _uuid(location_id)
    except (ValueError, TypeError):
        raise ValueError('Choose an available native location') from None
    if graph.errors:
        raise _NativeUnavailable(_READ_MESSAGE)
    root = graph.active(root_id)
    if not root or not graph.is_location(root):
        if root_id in graph.read_errors:
            raise _NativeUnavailable(_READ_MESSAGE)
        raise ValueError('Choose an available native location')
    # Validate the entire root ancestry before returning any records.
    graph.path(root_id)
    result, seen = [], set()
    for key, entity in graph.nodes.items():
        if not entity or entity.get('archived') or graph.is_location(entity):
            continue
        parent = _parent(entity)
        if not parent:
            continue
        try:
            path = graph.path(key)
        except (ValueError, TypeError, KeyError):
            if _is_descendant(graph, key, root_id):
                raise ValueError('Native hierarchy contains a cycle or unavailable ancestor') from None
            continue
        ancestors = [p['id'] for p in path[:-1]]
        if root_id not in ancestors:
            continue
        distance = len(ancestors) - 1 - ancestors.index(root_id)
        if (include_nested or distance == 0) and key not in seen:
            seen.add(key)
            result.append(entity)
    return result


def _child_descriptor(entity, errors=None):
    try:
        code = text_field(entity, 'Storage code') or ''
    except (ValueError, TypeError) as exc:
        code = ''
        if errors is not None:
            errors.append(str(exc))
    return {'id': str(entity['id']), 'name': entity.get('name') or '',
            'code': code, 'parent_id': _parent(entity)}


def _rack_view(graph, entity):
    result = {'id': str(entity['id']), 'name': entity.get('name') or '',
              'parent_id': _parent(entity), 'shelves': [], 'unordered': [],
              'other_children': [], 'errors': []}
    try:
        if text_field(entity, 'Storage kind') != 'Rack':
            return None
        field_value = text_field(entity, 'Workshop shelf order')
    except (ValueError, TypeError) as exc:
        result['errors'].append(str(exc))
        field_value = None
    children = [row for row in graph.nodes.values()
                if row and not row.get('archived') and _parent(row) == entity['id']]
    shelves = []
    for child in children:
        try:
            kind = text_field(child, 'Storage kind')
        except (ValueError, TypeError) as exc:
            result['errors'].append(str(exc))
            result['other_children'].append(_child_descriptor(child, result['errors']))
            continue
        descriptor = _child_descriptor(child, result['errors'])
        if graph.is_location(child) and kind == 'Shelf':
            shelves.append((child, descriptor))
        else:
            result['other_children'].append(descriptor)
    if field_value is not None:
        try:
            order = json.loads(field_value)
            if not isinstance(order, dict) or order.get('version') != 1 or not isinstance(order.get('shelf_ids'), list):
                raise ValueError('Workshop shelf order needs review in C-Crate')
            ordered_ids, seen = [], set()
            valid = {str(row['id']) for row, _ in shelves}
            for raw in order['shelf_ids']:
                try:
                    shelf_id = _uuid(raw)
                except (ValueError, TypeError):
                    result['errors'].append('Workshop shelf order contains a malformed shelf ID.')
                    continue
                if shelf_id in seen:
                    result['errors'].append('Workshop shelf order contains a duplicate shelf ID.')
                    continue
                seen.add(shelf_id)
                if shelf_id not in valid:
                    result['errors'].append('Workshop shelf order refers to a missing or non-shelf child.')
                    continue
                ordered_ids.append(shelf_id)
            by_id = {str(row['id']): desc for row, desc in shelves}
            result['shelves'] = [by_id[shelf_id] for shelf_id in ordered_ids]
            result['unordered'] = [desc for row, desc in shelves if str(row['id']) not in seen or str(row['id']) not in ordered_ids]
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            result['errors'].append(str(exc) or 'Workshop shelf order needs review in C-Crate')
            result['unordered'] = [desc for _, desc in shelves]
        return result
    numeric, unordered = [], []
    for row, desc in shelves:
        try:
            code = text_field(row, 'Storage code')
        except (ValueError, TypeError) as exc:
            result['errors'].append(str(exc))
            unordered.append(desc)
            continue
        try:
            value = float(code) if code is not None and code.strip() else math.nan
        except (ValueError, AttributeError):
            value = math.nan
        if math.isfinite(value):
            numeric.append((value, desc['name'].casefold(), desc['name'], desc['id'], desc))
        else:
            unordered.append(desc)
    result['shelves'] = [entry[-1] for entry in sorted(numeric)]
    result['unordered'] = unordered
    return result


def _photos(entity):
    photos = []
    for attachment in entity.get('attachments') or []:
        if not isinstance(attachment, dict) or attachment.get('type') != 'photo' or not attachment.get('id'):
            continue
        title = attachment.get('title') or ''
        photos.append({'id': str(attachment['id']), 'title': title,
                       'primary': bool(attachment.get('primary', attachment.get('isPrimary', False))),
                       'alt': title or ('Photo of ' + (entity.get('name') or 'location'))})
    return sorted(photos, key=lambda row: not row['primary'])


def _redact(value, private_ids):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            lowered = key.casefold()
            if any(secret in lowered for secret in ('borrower', 'actor_id', 'loan_identity')):
                continue
            if lowered in ('textvalue', 'value') and isinstance(item, str) and any(
                    marker in (value.get('name') or '').casefold() for marker in ('borrower', 'loan')):
                result[key] = '[redacted]'
            else:
                result[key] = _redact(item, private_ids)
        return result
    if isinstance(value, list):
        return [_redact(item, private_ids) for item in value
                if not (isinstance(item, dict) and isinstance(item.get('name'), str) and
                        any(marker in item['name'].casefold() for marker in ('borrower', 'loan')) and
                        ('textValue' in item or 'value' in item))]
    if isinstance(value, str):
        for private_id in private_ids:
            if private_id:
                value = value.replace(str(private_id), '[redacted]')
    return value


def scoped_equipment(client, location_id: str, *, include_nested: bool = False) -> list[dict]:
    return _scoped_equipment(_Graph(client), location_id, include_nested)


def _is_descendant(graph, key, root_id):
    seen = set()
    while key:
        if key in seen:
            return True
        seen.add(key)
        entity = graph.get(key)
        if not entity:
            return False
        key = _parent(entity)
        if key == root_id:
            return True
    return False


def build_view(client, layout_state: dict, custody: list[dict], *, entity_id: str | None = None,
               include_nested: bool = False, room_id: str | None = None,
               can_view_loans: bool = False) -> dict:
    graph = _Graph(client)
    drawings, room_errors = _room_drawings(graph, layout_state)
    coverage = _coverage(graph, drawings)
    coverage.extend({'location_id': error.get('entity_id'), 'drawing_id': error.get('drawing_id'),
                     'kind': 'unavailable', 'covered_by': None, 'matches': [],
                     'message': error['message'], **{key: error[key] for key in
                     ('room_id', 'room_name', 'root_location_id', 'root_name') if key in error}}
                    for error in room_errors if error['code'] in ('room_root_unavailable', 'room_link_unavailable'))
    errors = list(room_errors)
    for row in coverage:
        if row['kind'] == 'unavailable':
            errors.append({'code': 'coverage_unavailable', 'entity_id': row['location_id'],
                           'drawing_id': row['drawing_id'], 'message': row['message']})
    try:
        requested_room = _uuid(room_id) if room_id is not None else None
    except (ValueError, TypeError):
        requested_room = None
    path, selection = [], {'target_id': None, 'destination_id': None, 'kind': 'unmapped', 'matches': []}
    document = layout_state.get('document', layout_state) if isinstance(layout_state, dict) else None
    known_rooms = {str(row.get('id')) for row in document.get('rooms', [])
                   if isinstance(row, dict)} if isinstance(document, dict) and isinstance(document.get('rooms'), list) else set()
    contents, selected_entity = [], None
    if entity_id:
        try:
            target_id = _uuid(entity_id)
            path = graph.path(target_id)
            selection['target_id'] = target_id
            target = graph.get(target_id)
            selected_entity = target
            linked_by_location = {}
            for entry in drawings:
                _, drawing_id, location_id = entry[:3]
                if not location_id:
                    continue
                candidate = graph.get(location_id)
                if candidate and not candidate.get('archived') and graph.is_location(candidate):
                    room_key, room_name, root_id, root_name = (entry[3:7] if len(entry) > 3 else (None, '', None, ''))
                    linked_by_location.setdefault(location_id, []).append(
                        {'room_id': room_key, 'drawing_id': drawing_id, 'location_id': location_id,
                         'name': candidate.get('name') or '', **({'room_name': room_name,
                         'root_location_id': root_id, 'root_name': root_name} if room_key else {})})
            nearest = next((p['id'] for p in reversed(path) if p['is_location'] and p['id'] in linked_by_location), None)
            if nearest:
                matches = linked_by_location[nearest]
                if requested_room is not None:
                    matches = [match for match in matches if match['room_id'] == requested_room]
                selection.update(destination_id=nearest, kind='exact' if nearest == target_id or
                                 (not path[-1]['is_location'] and len(path) >= 2 and path[-2]['id'] == nearest)
                                 else 'containing', matches=matches)
            scope_id = target_id if graph.is_location(target) else next(
                (p['id'] for p in reversed(path[:-1]) if p['is_location']), None)
            if scope_id:
                try:
                    contents = _scoped_equipment(graph, scope_id, include_nested)
                except _NativeUnavailable:
                    errors.append({'code': 'native_read_unavailable', 'entity_id': scope_id,
                                   'drawing_id': None, 'message': _READ_MESSAGE})
            elif target and target.get('archived'):
                selection['kind'] = 'unavailable'
                errors.append({'code': 'unavailable', 'entity_id': target_id, 'drawing_id': None,
                               'message': 'Native entity is archived.'})
        except (ValueError, TypeError, KeyError) as exc:
            selection['target_id'] = str(entity_id)
            selection['kind'] = 'unavailable'
            errors.append({'code': 'ancestry_unavailable', 'entity_id': str(entity_id), 'drawing_id': None,
                           'message': str(exc)})
    if room_id is not None and (requested_room is None or requested_room not in known_rooms):
        selection['kind'] = 'unavailable'
    custody_by_entity = {str(row.get('entity_id')): row for row in (custody or []) if row.get('entity_id')}
    selection_status = None
    if selected_entity and not selected_entity.get('archived') and not graph.is_location(selected_entity):
        held = custody_by_entity.get(str(selected_entity['id']))
        selection_status = {
            'condition': condition(selected_entity),
            'checked_out': bool(held),
            'blocker': checkout_blocker(selected_entity),
        }
    for item in contents:
        held = custody_by_entity.get(str(item['id']))
        state = condition(item)
        blocker = checkout_blocker(item)
        item['condition'] = state
        item['checkout_blocker'] = blocker
        item['checked_out'] = bool(held)
        if held and can_view_loans:
            item['borrower_id'] = held.get('actor_id')
    counts = {'assigned': len(contents),
              'checked_out': sum(1 for item in contents if item['checked_out']),
              'available': sum(1 for item in contents if not item['checked_out'] and not item['checkout_blocker']),
              'needs_attention': sum(1 for item in contents if item['condition'] != 'Ready')}
    rack = _rack_view(graph, selected_entity) if selected_entity and graph.is_location(selected_entity) else None
    if rack:
        errors.extend({'code': 'rack_order_review', 'entity_id': rack['id'], 'drawing_id': None, 'message': message}
                      for message in rack['errors'])
    errors.extend(error for error in graph.errors if error not in errors)
    result = {'selection': selection, 'selection_status': selection_status,
              'path': path, 'contents': contents, 'include_nested': bool(include_nested),
              'counts': counts, 'coverage': coverage, 'rack': rack,
              'photos': _photos(selected_entity) if selected_entity and graph.is_location(selected_entity) else [],
              'errors': errors, 'refreshed_at': datetime.now(timezone.utc).isoformat()}
    return result if can_view_loans else _redact(result, [row.get('actor_id') for row in (custody or [])])


def _origin(value):
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in ('http', 'https') or not parsed.hostname:
            return None
        scheme, host = parsed.scheme.lower(), parsed.hostname.lower()
        port = parsed.port
    except (AttributeError, TypeError, ValueError):
        return None
    if port is not None and port != (443 if scheme == 'https' else 80):
        host += ':'+str(port)
    return scheme+'://'+host


def _native_origin_allowed(client, raw):
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return False
    if not parsed.scheme:
        return not parsed.netloc
    allowed = {_origin(getattr(client, 'base', None))}
    try:
        allowed.update(_origin(origin) for origin in getattr(client, 'workshop_code_origins', ()))
    except TypeError:
        pass
    allowed.discard(None)
    return _origin(raw) in allowed


def _ambiguous_equipment(raw, code, entities):
    value = raw.strip()
    active = [e for e in entities if not e.get('archived') and not e.get('entityType', {}).get('isLocation')]
    matches = [e for e in active if e.get('barcode') == value or
               value in [f.get('textValue', '') for f in e.get('fields', [])
                         if f.get('name') == 'Manufacturer QR code']]
    if code.get('kind') == 'short_code':
        canonical = code.get('short_code', '').upper()
        matches.extend(e for e in active if isinstance(e.get('shortCode'), str) and
                       e['shortCode'].strip().upper() == canonical or
                       isinstance(e.get('serialNumber'), str) and
                       e['serialNumber'].strip().upper() == canonical or
                       canonical in [f.get('textValue', '').strip().upper() for f in e.get('fields', [])
                                     if f.get('name') == 'Manufacturer QR code' and
                                     isinstance(f.get('textValue', ''), str)])
    elif code.get('kind') == 'serial':
        matches.extend(e for e in active if e.get('serialNumber') == code.get('serial'))
    elif code.get('kind') == 'manufacturer':
        serials = {v for k, values in parse_qs(urlsplit(value).query).items()
                   if k.lower() in ('sn', 'serial', 'serialnumber', 'serial_number') for v in values if v}
        if len(serials) == 1:
            matches.extend(e for e in active if e.get('serialNumber') == next(iter(serials)))
    elif code.get('kind') == 'product':
        canonical = code.get('gtin', '').zfill(14)
        matches.extend(e for e in active if any(f.get('name') == 'Product GTIN' and
                   isinstance(f.get('textValue'), str) and f['textValue'].zfill(14) == canonical
                   for f in e.get('fields', [])))
    return unique_entities(matches)


def resolve_workshop_code(client, raw: str) -> dict:
    graph = _Graph(client)
    all_entities = [e for e in graph.nodes.values() if e and not e.get('archived')]
    code = normalize(raw)
    lookup_raw = raw.strip() if isinstance(raw, str) else ''
    reject_lookup = False
    if lookup_raw.startswith('LAB:U:'):
        code = {'kind': 'invalid', 'reason': 'A person badge cannot identify equipment.'}
        reject_lookup = True
    if code.get('kind') in ('entity', 'asset') and not _native_origin_allowed(client, lookup_raw):
        code = {'kind': 'invalid', 'reason': 'Use a native C-Crate code from this server.'}
        reject_lookup = True
    if graph.errors:
        return {'kind': code.get('kind', 'invalid'), 'entity_id': None, 'candidates': [], 'message': _READ_MESSAGE}
    entity = None
    if code.get('kind') == 'entity':
        candidate = graph.active(code['entity_id'])
        if candidate:
            entity = candidate
        else:
            code = {**code, 'reason': 'Native entity is unavailable in this tenant.'}
    elif code.get('kind') == 'asset':
        found = [e for e in all_entities if not graph.is_location(e) and e.get('assetId') == code['asset_id']]
        if len(found) == 1:
            entity = found[0]
        elif len(found) > 1:
            code = {**code, 'ambiguous': True, 'reason': 'Multiple equipment records use this asset ID.'}
    elif not reject_lookup:
        result = resolve_equipment(lookup_raw, code, all_entities)
        entity = result.get('entity')
        code = result
    candidate_entities = []
    if entity:
        candidate_entities = [entity]
    elif code.get('ambiguous'):
        candidate_entities = (_ambiguous_equipment(lookup_raw, code, all_entities)
                              if code.get('kind') != 'asset' else
                              [e for e in all_entities if not graph.is_location(e) and
                               e.get('assetId') == code.get('asset_id')])
    candidates = []
    for item in candidate_entities:
        try:
            item_path = graph.path(item['id'])
        except (ValueError, TypeError, KeyError):
            item_path = []
        candidates.append({'id': item['id'], 'name': item.get('name', ''),
                           'is_location': graph.is_location(item), 'asset_id': item.get('assetId'), 'path': item_path})
    reason = ('Select the matching native record.' if code.get('ambiguous') else
              'Native record resolved.' if entity else code.get('reason') or
              'No active native record matches this code.')
    return {'kind': code.get('kind', 'invalid'), 'entity_id': entity['id'] if entity else None,
            'candidates': candidates, 'message': reason}
