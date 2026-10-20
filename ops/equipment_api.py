"""Authenticated collection-scoped equipment template and ID endpoints."""
import json
import re
import urllib.error
from uuid import uuid5, NAMESPACE_URL

from equipment_catalog import EquipmentCatalog
from ledger import Conflict, uuid

PRODUCT_GROUP_TAG_PREFIX = 'C-Crate Product group: '


def _optional(deps, name, default=None):
    return deps.get(name, default) if isinstance(deps, dict) else getattr(deps, name, default)


def _dependency(deps, name):
    return deps[name] if isinstance(deps, dict) else getattr(deps, name)


def equipment_catalog_service(deps):
    service = _optional(deps, 'equipment_catalog')
    if service is None:
        service = EquipmentCatalog(_dependency(deps, 'ledger'))
        if isinstance(deps, dict):
            deps['equipment_catalog'] = service
    return service


def require_current_member(ctx, ApiError):
    members = ctx['client'].call('/api/v1/groups/members')
    if ctx['actor'] not in {uuid(member['id']) for member in members}:
        raise ApiError(403, 'A current member of this C-Crate collection is required.', 'collection_forbidden')


def equipment_type(client, entity):
    entity_type = entity.get('entityType') or {}
    type_id = uuid(entity_type.get('id'))
    types = client.call('/api/v1/entity-types')
    selected = next((item for item in types if uuid(item.get('id')) == type_id), None)
    if not selected or selected.get('isLocation') or entity_type.get('isLocation') or entity.get('isLocation'):
        raise ValueError('Choose an equipment item with a current native type.')
    name = selected.get('name')
    if not isinstance(name, str) or not name.strip():
        raise ValueError('The native item type has no usable short ID prefix.')
    prefix = re.sub(r'[^A-Z0-9]+', '-', name.strip().upper()).strip('-')
    if not prefix:
        raise ValueError('The native item type has no usable short ID prefix.')
    return type_id, prefix


def _normalized(value):
    return ' '.join(str(value or '').split()).casefold()


def _native_product_fields(entity, type_id):
    photos = [attachment for attachment in entity.get('attachments', []) if attachment.get('type') == 'photo']
    photo = next((item for item in photos if item.get('primary')), photos[0] if photos else None)
    return {
        'name': entity.get('name', ''), 'entity_type_id': type_id,
        'manufacturer': entity.get('manufacturer', ''), 'model_number': entity.get('modelNumber', ''),
        'description': entity.get('description', ''), 'tag_ids': [tag['id'] for tag in entity.get('tags', []) if tag.get('id')],
        **({'photo_attachment_id': photo['id'], 'photo_entity_id': entity['id']} if photo and photo.get('id') and entity.get('id') else {}),
    }


def _product_group_tags(entity):
    labels = set()
    for tag in entity.get('tags', []):
        name = tag.get('name', '')
        if isinstance(name, str) and name.casefold().startswith(PRODUCT_GROUP_TAG_PREFIX.casefold()):
            label = _normalized(name[len(PRODUCT_GROUP_TAG_PREFIX):])
            if label:
                labels.add(label)
    if len(labels) > 1:
        raise Conflict('Native product group tags need review before matching items.')
    return labels


def product_group_identity(entity):
    groups = _product_group_tags(entity or {})
    return json.dumps(sorted(groups), separators=(',', ':')) if groups else ''


def matching_native_entities(client, fields, source_entity=None):
    type_id = uuid(fields['entity_type_id'])
    manufacturer, model = _normalized(fields.get('manufacturer')), _normalized(fields.get('model_number'))
    name = _normalized(fields.get('name'))
    target_groups = _product_group_tags(source_entity or {})
    matches = []
    # Homebox.entities() includes archived records; fetch matching type records in this tenant
    # before using their metadata. These UUIDs are linked as legacy members and never rewritten.
    for summary in client.entities():
        summary_type = summary.get('entityType') or {}
        try:
            candidate_type_id = uuid(summary_type.get('id'))
            candidate_id = uuid(summary.get('id'))
        except (ValueError, TypeError):
            continue
        if candidate_type_id != type_id:
            continue
        try:
            entity = client.entity(candidate_id)
        except urllib.error.HTTPError as error:
            if error.code in (403, 404):
                continue
            raise
        candidate_groups = _product_group_tags(entity)
        if target_groups:
            if candidate_groups == target_groups:
                matches.append(candidate_id)
            continue
        if candidate_groups and target_groups != candidate_groups:
            # Explicit group metadata on the native item wins over loose text matching.
            continue
        existing_manufacturer = _normalized(entity.get('manufacturer'))
        existing_model = _normalized(entity.get('modelNumber'))
        if manufacturer and model and existing_manufacturer and existing_model:
            if existing_manufacturer == manufacturer and existing_model == model:
                matches.append(candidate_id)
            continue
        if _normalized(entity.get('name')) != name:
            continue
        if manufacturer and existing_manufacturer and manufacturer != existing_manufacturer:
            continue
        if model and existing_model and model != existing_model:
            continue
        matches.append(candidate_id)
    return sorted(set(matches))


def _assignment_replay(catalog, group, request_key):
    with catalog.ledger.connection() as db:
        row = db.execute('SELECT * FROM equipment_assignment_requests WHERE group_id=? AND request_key=?',
                         (group, request_key)).fetchone()
    return dict(row) if row else None


def _assignment_public(result):
    return {key: result[key] for key in ('entity_id', 'product_id', 'display_id', 'type_prefix', 'model_code', 'number', 'assigned_at')}


def _catalog_model_code(value):
    code = re.sub(r'[^A-Z0-9]+', '-', str(value or '').strip().upper()).strip('-')
    if not code:
        raise ValueError('Enter a model code.')
    return code


def _active_product_entity_ids(client):
    active = set()
    for summary in client.entities():
        try:
            entity_id = uuid(summary.get('id'))
            entity = client.entity(entity_id)
        except urllib.error.HTTPError as error:
            if error.code in (403, 404):
                continue
            raise
        except (ValueError, TypeError):
            continue
        if entity.get('archived') or entity.get('isArchived'):
            continue
        if entity.get('isLocation') or (entity.get('entityType') or {}).get('isLocation'):
            continue
        active.add(entity_id)
    return active


def _product_summaries(catalog, group, client):
    products = catalog.list_products(group, _active_product_entity_ids(client))
    products = [product for product in products if product['active_item_count']]
    return products


def equipment_product_model_code_post(data, ctx, deps, ApiError):
    require_current_member(ctx, ApiError)
    if set(data) != {'product_id', 'model_code', 'expected_updated_at', 'request_key'}:
        raise ValueError('Provide product_id, model_code, expected_updated_at, and request_key.')
    catalog = equipment_catalog_service(deps)
    product_id = uuid(data.get('product_id'))
    visible = _product_summaries(catalog, ctx['group'], ctx['client'])
    if not any(product['id'] == product_id for product in visible):
        raise ApiError(404, 'Equipment product not found in this collection.')
    updated = catalog.update_product_model_code(ctx['group'], ctx['actor'], product_id,
                                               data.get('model_code'), data.get('expected_updated_at'),
                                               data.get('request_key'))
    summary = next(product for product in _product_summaries(catalog, ctx['group'], ctx['client'])
                   if product['id'] == updated['id'])
    return {**summary, 'model_code': updated['model_code'], 'updated_at': updated['updated_at']}


def equipment_catalog_post(route, data, ctx, deps, ApiError, public_entity):
    client, group, actor = ctx['client'], ctx['group'], ctx['actor']
    require_current_member(ctx, ApiError)
    catalog = equipment_catalog_service(deps)
    if route == 'equipment/templates/save':
        request_key = uuid(data.get('request_key'))
        raw_fields = data.get('fields')
        if not isinstance(raw_fields, dict):
            raise ValueError('Template fields must be an object.')
        source_id = data.get('source_entity_id')
        if source_id:
            source = public_entity(client, source_id)
            if uuid(source.get('id')) != uuid(source_id):
                raise Conflict('Native source item changed during validation.')
            if (source.get('entityType') or {}).get('isLocation') or source.get('isLocation'):
                raise ValueError('Choose equipment, not a storage location.')
            type_id, prefix = equipment_type(client, source)
            fields = _native_product_fields(source, type_id)
            fields.update(raw_fields)
            # Attachment IDs are scoped to the verified native entity. Never
            # accept an owner or attachment path supplied by the browser.
            native_photo = _native_product_fields(source, type_id)
            for field in ('photo_attachment_id', 'photo_entity_id'):
                fields.pop(field, None)
            for field in ('photo_attachment_id', 'photo_entity_id'):
                if native_photo.get(field):
                    fields[field] = native_photo[field]
            fields['entity_type_id'] = type_id
            # An entity type is native authority and cannot be overridden by submitted template data.
            if uuid(raw_fields.get('entity_type_id', type_id)) != type_id:
                raise ValueError('Template type must match its source item.')
        else:
            fields = dict(raw_fields)
            if fields.get('photo_entity_id') or fields.get('photo_attachment_id'):
                if not data.get('template_id'):
                    raise ValueError('A template photo must come from a verified source item.')
                existing = next((row for row in catalog.list_templates(group) if row['id'] == uuid(data['template_id'])), None)
                if not existing:
                    raise ApiError(404, 'Equipment template not found in this collection.')
                for field in ('photo_entity_id', 'photo_attachment_id'):
                    if fields.get(field) != existing.get(field):
                        raise ValueError('A template photo can only retain its verified source attachment.')
            elif data.get('template_id'):
                existing = next((row for row in catalog.list_templates(group) if row['id'] == uuid(data['template_id'])), None)
                if existing:
                    for field in ('photo_entity_id', 'photo_attachment_id'):
                        if existing.get(field):
                            fields[field] = existing[field]
            type_id = uuid(fields.get('entity_type_id'))
            type_info = next((item for item in client.call('/api/v1/entity-types') if uuid(item.get('id')) == type_id), None)
            if not type_info or type_info.get('isLocation'):
                raise ValueError('Choose a current equipment type.')
            prefix = equipment_type(client, {'entityType': type_info})[1]
        if not set(fields).issubset({'name', 'entity_type_id', 'manufacturer', 'model_number', 'model_code', 'description', 'tag_ids', 'photo_attachment_id', 'photo_entity_id'}):
            raise ValueError('Templates accept shared fields only.')
        native_tags = [item for item in client.call('/api/v1/tags') if item.get('id')]
        tags = {uuid(item['id']) for item in native_tags}
        if any(uuid(tag_id) not in tags for tag_id in fields.get('tag_ids', [])):
            raise ValueError('Choose tags from this C-Crate collection.')
        matching_source = source if source_id else {'tags': [item for item in native_tags if uuid(item['id']) in set(fields.get('tag_ids', []))]}
        product_group = product_group_identity(matching_source)
        matching_native_entities(client, fields, matching_source)  # Refetch candidates for validation; assignment seeds them, excluding its target.
        return catalog.save_template(group, actor, request_key, fields, [],
                                     type_prefix=prefix, template_id=data.get('template_id'),
                                     expected_updated_at=data.get('expected_updated_at'), product_group=product_group)
    if route == 'equipment/templates/archive':
        return catalog.archive_template(group, actor, data.get('template_id'), data.get('request_key'))
    if route == 'equipment/templates/restore':
        return catalog.restore_template(group, actor, data.get('template_id'), data.get('request_key'))
    if route == 'equipment/ids/assign':
        request_key = uuid(data.get('request_key'))
        entity_id = uuid(data.get('entity_id'))
        template_id, model_code = data.get('template_id'), data.get('model_code')
        if bool(template_id) == bool(model_code):
            raise ValueError('Choose exactly one template or model code.')
        previous_request = _assignment_replay(catalog, group, request_key)
        if previous_request and previous_request['entity_id'] != entity_id:
            raise Conflict('Request key was already used for another item.')
        entity = public_entity(client, entity_id)
        if uuid(entity.get('id')) != entity_id:
            raise Conflict('Native item changed during validation.')
        if (entity.get('entityType') or {}).get('isLocation') or entity.get('isLocation'):
            raise ValueError('Choose equipment, not a storage location.')
        type_id, prefix = equipment_type(client, entity)
        native_fields = _native_product_fields(entity, type_id)
        prior_result = json.loads(previous_request['result_json']) if previous_request else None
        if template_id:
            tid = uuid(template_id)
            if previous_request:
                with catalog.ledger.connection() as db:
                    template = db.execute('SELECT product_id FROM equipment_templates WHERE group_id=? AND id=?', (group, tid)).fetchone()
                if not template or template['product_id'] != previous_request['product_id']:
                    raise Conflict('Request key was already used for another product.')
                return _assignment_public(prior_result)
            template = next((row for row in catalog.list_templates(group) if row['id'] == tid), None)
            if not template:
                raise ApiError(404, 'Equipment template not found in this collection.')
            if template['entity_type_id'] != type_id:
                raise ValueError('Template item type does not match the native item.')
            product_id = template['product_id']
            with catalog.ledger.connection() as db:
                product_identity = db.execute('SELECT product_group FROM equipment_products WHERE group_id=? AND id=?', (group, product_id)).fetchone()
            entity_group = product_group_identity(entity)
            if not product_identity or str(product_identity['product_group'] or '') != entity_group:
                raise ValueError('Template product group does not match the native item.')
            # An explicit matching product group is the stronger native identity signal.
            if not entity_group:
                for template_field, native_field in (('manufacturer', 'manufacturer'), ('model_number', 'model_number')):
                    template_value = _normalized(template.get(template_field))
                    native_value = _normalized(native_fields.get(native_field))
                    if template_value and native_value and template_value != native_value:
                        raise ValueError('Template product does not match the native item metadata.')
            matching = [match for match in matching_native_entities(client, {**native_fields, 'model_code': template['model_code']}, entity) if match != entity_id]
            catalog.refresh_product_members(group, product_id, matching)
        else:
            code = _catalog_model_code(model_code)
            if previous_request:
                if prior_result['model_code'] != code or prior_result['type_prefix'] != prefix:
                    raise Conflict('Request key was already used for a different product.')
                return _assignment_public(prior_result)
            product = {'entity_type_id': type_id, 'type_prefix': prefix,
                       'manufacturer': native_fields['manufacturer'], 'model_number': native_fields['model_number'],
                       'model_code': code, 'product_group': product_group_identity(entity)}
            matching = [match for match in matching_native_entities(client, {**native_fields, 'model_code': code}, entity) if match != entity_id]
            registered = catalog.register_product(group, actor, str(uuid5(NAMESPACE_URL, 'equipment-assignment:' + request_key)), product, matching)
            product_id = registered['id']
        return _assignment_public(catalog.assign_item(group, actor, entity_id, product_id, request_key))
    if route == 'equipment/products/code':
        return equipment_product_model_code_post(data, ctx, deps, ApiError)
    if route == 'equipment/ids/resolve':
        display_id = data.get('display_id')
        if not isinstance(display_id, str) or not display_id.strip() or len(display_id) > 100:
            raise ValueError('Enter a valid equipment ID.')
        entity_id = catalog.resolve_id(group, display_id)
        if not entity_id:
            raise ApiError(404, 'Equipment ID not found in this collection.')
        public_entity(client, entity_id)
        return {'entity_id': entity_id}
    raise ApiError(404, 'Unknown equipment catalog action.')

def equipment_catalog_get(route, query, ctx, deps, ApiError):
    client, group = ctx['client'], ctx['group']
    if route == 'equipment/templates':
        require_current_member(ctx, ApiError)
        include_archived = any(str(value).lower() in ('1', 'true', 'yes') for value in query.get('include_archived', []))
        return equipment_catalog_service(deps).list_templates(group, include_archived=include_archived)
    if route == 'equipment/products':
        require_current_member(ctx, ApiError)
        catalog = equipment_catalog_service(deps)
        return _product_summaries(catalog, group, client)
    if route == 'equipment/ids':
        require_current_member(ctx, ApiError)
        values = query.get('ids', []) + query.get('entity_ids', [])
        ids = [part for value in values for part in value.split(',') if part]
        if not ids or len(ids) > 100:
            raise ValueError('Choose 1 to 100 native equipment UUIDs.')
        normalized = [uuid(item) for item in ids]
        if len(normalized) != len(set(normalized)):
            raise ValueError('Choose distinct native equipment UUIDs.')
        catalog = equipment_catalog_service(deps)
        result = {}
        for entity_id in normalized:
            client.entity(entity_id)
            assignment = catalog.assignment(group, entity_id)
            if assignment:
                result[entity_id] = {'product_id': assignment['product_id'], 'display_id': assignment['display_id']}
        return result
    if route == 'equipment/suggestions':
        require_current_member(ctx, ApiError)
        if set(query) - {'type_id', 'q', 'limit'} or len(query.get('type_id', [])) != 1:
            raise ValueError('Choose one equipment type.')
        type_id = uuid(query['type_id'][0])
        types = client.call('/api/v1/entity-types')
        selected = next((item for item in types if uuid(item.get('id')) == type_id), None)
        if not selected or selected.get('isLocation'):
            raise ValueError('Choose a current equipment type.')
        values = query.get('q', [''])
        if len(values) != 1 or not isinstance(values[0], str):
            raise ValueError('Enter one search query.')
        term = _normalized(values[0])
        if not term:
            return []
        limits = query.get('limit', ['8'])
        if len(limits) != 1:
            raise ValueError('Choose a valid result limit.')
        try: limit = int(limits[0])
        except (ValueError, TypeError): raise ValueError('Choose a valid result limit.') from None
        if limit < 1:
            raise ValueError('Choose a positive result limit.')
        limit = min(limit, 8)
        catalog = equipment_catalog_service(deps)
        results = []
        for summary in client.entities():
            entity = summary
            try:
                if uuid((entity.get('entityType') or {}).get('id')) != type_id or entity.get('archived') or entity.get('isArchived'):
                    continue
                entity_id = uuid(entity.get('id'))
                entity = client.entity(entity_id)
            except urllib.error.HTTPError as error:
                if error.code in (403, 404): continue
                raise
            except (ValueError, TypeError):
                continue
            if entity.get('archived') or entity.get('isArchived') or (entity.get('entityType') or {}).get('isLocation') or entity.get('isLocation'):
                continue
            try:
                if uuid((entity.get('entityType') or {}).get('id')) != type_id:
                    continue
            except (ValueError, TypeError):
                continue
            name = str(entity.get('name') or '')
            if term and term not in _normalized(' '.join((name, entity.get('manufacturer', ''), entity.get('modelNumber', '')))):
                continue
            assignment = catalog.assignment(group, entity_id)
            current_code = catalog.current_product_model_code(group, assignment['product_id']) if assignment and not assignment.get('deleted') else None
            results.append({'id': entity_id, 'name': name, 'manufacturer': entity.get('manufacturer', ''),
                            'modelNumber': entity.get('modelNumber', ''),
                            'tagIds': [tag['id'] for tag in entity.get('tags', []) if tag.get('id')],
                            'modelCode': current_code or ''})
        results.sort(key=lambda item: (_normalized(item['name']), item['id']))
        return results[:limit]
    raise ApiError(404, 'Unknown equipment catalog route.')

