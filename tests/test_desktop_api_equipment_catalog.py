"""Isolated desktop API contracts for collection equipment catalog routes."""
import copy
import io
import json
import pathlib
import tempfile
import threading
import unittest
import urllib.error
from email.message import Message
from uuid import uuid4

import desktop_api as api
from badges import Badges
from equipment_catalog import EquipmentCatalog, Conflict
from homebox import Homebox
from ledger import Ledger
from native_jobs import NativeJobs


def ident():
    return str(uuid4())


class Request:
    def __init__(self, path, method='GET', data=None, headers=None):
        self.path, self.command = '/workshop-api/' + path, method
        self.headers = Message()
        values = {'Host': 'pi.local:17745', 'Cookie': 'hb.auth.token=manager; hb.auth.remember=true'}
        values.update(headers or {})
        body = json.dumps(data or {}).encode()
        if method == 'POST':
            values.setdefault('Origin', 'http://pi.local:17745')
            values.setdefault('Content-Type', 'application/json')
            values.setdefault('Content-Length', str(len(body)))
        for name, value in values.items():
            if value is not None:
                self.headers[name] = value
        self.rfile = io.BytesIO(body)
        self.status = self.result = None

    def reply_json(self, status, result):
        self.status, self.result = status, result


class CatalogNative:
    def __init__(self, owner, token):
        self.owner, self.token, self.tenant = owner, token, None

    def entity(self, entity_id):
        self.owner.native_calls.append((self.token, self.tenant, '/api/v1/entities/' + entity_id, 'GET', None))
        if self.tenant != self.owner.group or entity_id not in self.owner.entities or self.owner.entity_collections.get(entity_id, self.owner.group) != self.tenant:
            raise urllib.error.HTTPError('native', 404, 'missing', {}, None)
        return copy.deepcopy(self.owner.entities[entity_id])

    def entities(self, locations=False):
        if self.tenant != self.owner.group:
            return []
        return [copy.deepcopy(item) for item in self.owner.entities.values()
                if bool(item.get('entityType', {}).get('isLocation')) == locations]

    def call(self, path, method='GET', data=None):
        self.owner.native_calls.append((self.token, self.tenant, path, method, copy.deepcopy(data)))
        if self.token not in self.owner.users:
            raise urllib.error.HTTPError('native', 401, 'expired', {}, None)
        if path == '/api/v1/users/self':
            return {'item': copy.deepcopy(self.owner.users[self.token])}
        if path == '/api/v1/groups':
            return {'id': self.tenant, 'name': 'Fixture collection'}
        if path == '/api/v1/groups/members':
            return copy.deepcopy(self.owner.members)
        if path == '/api/v1/entity-types':
            return copy.deepcopy(self.owner.types)
        if path == '/api/v1/tags':
            return copy.deepcopy(self.owner.tags)
        if path.startswith('/api/v1/entities/'):
            return self.entity(path.rsplit('/', 1)[1])
        raise AssertionError('Unexpected native request: ' + path)


class EquipmentCatalogApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.group, self.actor, self.member, self.kind, self.item, self.location = [ident() for _ in range(6)]
        self.users = {
            'manager': {'id': self.actor, 'name': 'Admin', 'defaultGroupId': self.group, 'groupIds': [self.group]},
            'member': {'id': self.member, 'name': 'Member', 'defaultGroupId': self.group, 'groupIds': [self.group]},
        }
        self.entities = {
            self.item: {'id': self.item, 'name': 'Drone', 'entityType': {'id': self.kind, 'name': 'Drone', 'isLocation': False},
                        'manufacturer': 'Maker', 'modelNumber': 'Mini 4 Pro', 'description': 'Test unit', 'serialNumber': 'SERIAL-1',
                        'parent': {'id': self.location}, 'archived': False, 'quantity': 1, 'tags': [], 'attachments': []},
            self.location: {'id': self.location, 'name': 'Shelf', 'entityType': {'id': self.kind, 'name': 'Location', 'isLocation': True},
                            'archived': False, 'quantity': 0, 'tags': [], 'attachments': []},
        }
        self.entity_collections = {}
        self.users['stale'] = {'id': ident(), 'name': 'Stale', 'defaultGroupId': self.group, 'groupIds': [self.group]}
        self.manager = self.actor
        self.members = [{'id': self.actor, 'name': 'Admin'}, {'id': self.member, 'name': 'Member'}]
        self.borrower = self.member
        self.group_name = 'Equipment'
        self.tags = []
        self.native_calls = []
        self.types = [{'id': self.kind, 'name': 'Drone', 'isLocation': False}]
        self.ledger = Ledger(self.root / 'ledger.db')
        self.catalog = EquipmentCatalog(self.ledger)
        self.deps = {'root': self.root, 'lock': threading.Lock(), 'ledger': self.ledger,
                     'badges': Badges(self.ledger), 'native_jobs': NativeJobs(self.ledger),
                     'equipment_catalog': self.catalog, 'homebox_factory': self.native_factory,
                     'native_base': 'http://127.0.0.1:17747'}
        self.identity = self.request('context').result['identity']

    def tearDown(self):
        self.temp.cleanup()

    def native_factory(self, cookie, base=None):
        token = cookie.split('hb.auth.token=', 1)[1].split(';', 1)[0]
        return CatalogNative(self, token)

    def request(self, route, data=None, *, method=None, headers=None):
        method = method or ('GET' if data is None else 'POST')
        path = route if route.startswith('equipment/') or route == 'context' else route
        request = Request(path, method, data, {'X-Workshop-Identity': getattr(self, 'identity', ''), **(headers or {})})
        self.assertTrue(api.handle(request, self.deps))
        return request

    def template_fields(self, **changes):
        return {'name': 'Drone', 'entity_type_id': self.kind, 'manufacturer': 'Maker', 'model_number': 'Mini 4 Pro',
                'model_code': 'M4P', 'description': 'Shared detail', 'tag_ids': [], **changes}

    def test_member_can_save_list_and_archive_templates_scoped_to_collection(self):
        member_context = self.request('context', headers={'Cookie': 'hb.auth.token=member; hb.auth.remember=true'}).result
        headers = {'Cookie': 'hb.auth.token=member; hb.auth.remember=true', 'X-Workshop-Identity': member_context['identity']}
        saved = self.request('equipment/templates/save', {'request_key': ident(), 'fields': self.template_fields()}, headers=headers)
        self.assertEqual(200, saved.status)
        self.assertEqual(self.member, self.catalog.template_history(self.group, saved.result['id'])[0]['actor_id'])
        listing = self.request('equipment/templates')
        self.assertEqual([saved.result], listing.result)
        archive = self.request('equipment/templates/archive', {'request_key': ident(), 'template_id': saved.result['id']}, headers=headers)
        self.assertEqual(200, archive.status)
        self.assertEqual([], self.request('equipment/templates').result)
        archived_listing = self.request('equipment/templates?include_archived=true')
        self.assertEqual([archive.result], archived_listing.result)
        restore_key = ident()
        restored = self.request('equipment/templates/restore', {'request_key': restore_key, 'template_id': saved.result['id']}, headers=headers)
        self.assertEqual(200, restored.status)
        self.assertFalse(restored.result['archived'])
        self.assertEqual(restored.result, self.request('equipment/templates/restore', {'request_key': restore_key, 'template_id': saved.result['id']}, headers=headers).result)
        self.assertEqual([restored.result], self.request('equipment/templates').result)
        self.assertEqual(['saved', 'archived', 'restored'], [row['action'] for row in self.catalog.template_history(self.group, saved.result['id'])])
        other = self.catalog.list_templates(ident())
        self.assertEqual([], other)

    def test_saved_templates_survive_catalog_reopen_and_remain_readable_through_api(self):
        active = self.request('equipment/templates/save', {
            'request_key': ident(), 'fields': self.template_fields(name='Retained drone')
        })
        archived = self.request('equipment/templates/save', {
            'request_key': ident(), 'fields': self.template_fields(name='Archived drone', manufacturer='Other maker', model_code='OLD')
        })
        self.assertEqual(200, active.status)
        self.assertEqual(200, archived.status)
        self.assertEqual(200, self.request('equipment/templates/archive', {
            'request_key': ident(), 'template_id': archived.result['id']
        }).status)

        # A fresh catalog reads the same temporary database after the frontend changes.
        self.catalog = EquipmentCatalog(Ledger(self.root / 'ledger.db'))
        self.deps['equipment_catalog'] = self.catalog
        listing = self.request('equipment/templates')
        all_records = self.request('equipment/templates?include_archived=true')
        self.assertEqual(200, listing.status)
        self.assertEqual(200, all_records.status)
        self.assertEqual([active.result['id']], [row['id'] for row in listing.result])
        self.assertEqual({active.result['id'], archived.result['id']}, {row['id'] for row in all_records.result})
        self.assertEqual('Retained drone', listing.result[0]['name'])
        self.assertEqual('M4P', listing.result[0]['model_code'])
        self.assertTrue(next(row for row in all_records.result if row['id'] == archived.result['id'])['archived'])
        self.assertEqual(['saved'], [row['action'] for row in self.catalog.template_history(self.group, active.result['id'])])
        self.assertEqual(['saved', 'archived'], [row['action'] for row in self.catalog.template_history(self.group, archived.result['id'])])

    def test_template_routes_reject_unknown_members_and_per_unit_fields(self):
        bad = self.request('equipment/templates/save', {'request_key': ident(), 'fields': self.template_fields(serial_number='no')})
        self.assertEqual(400, bad.status)
        self.assertEqual([], self.catalog.list_templates(self.group))
        stale = self.request('equipment/templates', headers={'Cookie': 'hb.auth.token=stale; hb.auth.remember=true'})
        self.assertEqual(403, stale.status)

    def test_source_entity_is_refetched_and_only_shared_values_are_saved(self):
        fields = self.template_fields()
        fields.pop('entity_type_id')
        result = self.request('equipment/templates/save', {'request_key': ident(), 'source_entity_id': self.item, 'fields': fields})
        self.assertEqual(200, result.status)
        self.assertEqual(self.kind, result.result['entity_type_id'])
        self.assertEqual('M4P', result.result['model_code'])
        self.assertTrue(any(call[2] == '/api/v1/entities/' + self.item for call in self.native_calls))

    def test_template_photo_fallback_keeps_verified_attachment_owner_and_rejects_forged_owner(self):
        attachment = ident()
        self.entities[self.item]['attachments'] = [{'id': attachment, 'type': 'photo', 'primary': True}]
        saved = self.request('equipment/templates/save', {
            'request_key': ident(), 'source_entity_id': self.item, 'fields': self.template_fields(),
        })
        self.assertEqual(200, saved.status)
        self.assertEqual(attachment, saved.result['photo_attachment_id'])
        self.assertEqual(self.item, saved.result['photo_entity_id'])

        forged = self.template_fields(photo_attachment_id=attachment, photo_entity_id=ident())
        rejected = self.request('equipment/templates/save', {'request_key': ident(), 'fields': forged})
        self.assertEqual(400, rejected.status)
        self.assertEqual(1, len(self.catalog.list_templates(self.group)))

        fields = {key: saved.result[key] for key in ('name', 'entity_type_id', 'manufacturer', 'model_number', 'model_code', 'description', 'tag_ids', 'photo_entity_id', 'photo_attachment_id')}
        fields['description'] = 'Edited shared description'
        edited = self.request('equipment/templates/save', {
            'request_key': ident(), 'template_id': saved.result['id'],
            'expected_updated_at': saved.result['updated_at'], 'fields': fields,
        })
        self.assertEqual(200, edited.status)
        self.assertEqual(self.item, edited.result['photo_entity_id'])
        self.assertEqual(attachment, edited.result['photo_attachment_id'])
        fields['photo_entity_id'] = ident()
        rejected_edit = self.request('equipment/templates/save', {
            'request_key': ident(), 'template_id': edited.result['id'],
            'expected_updated_at': edited.result['updated_at'], 'fields': fields,
        })
        self.assertEqual(400, rejected_edit.status)

    def test_location_assignment_rejected_and_native_item_controls_product_identity(self):
        result = self.request('equipment/ids/assign', {'request_key': ident(), 'entity_id': self.location, 'model_code': 'M4P'})
        self.assertEqual(400, result.status)
        result = self.request('equipment/ids/assign', {'request_key': ident(), 'entity_id': self.item, 'model_code': 'M4P',
                                                       'manufacturer': 'Forged', 'entity_type_id': ident()})
        self.assertEqual(200, result.status)
        assignment = self.catalog.assignment(self.group, self.item)
        self.assertEqual('DRONE-M4P-1', assignment['display_id'])
        self.assertEqual([], self.catalog.list_templates(self.group))



    def test_template_assignment_rejects_native_metadata_conflict(self):
        saved = self.request('equipment/templates/save', {'request_key': ident(), 'fields': self.template_fields()})
        other = ident()
        self.entities[other] = {**copy.deepcopy(self.entities[self.item]), 'id': other,
                                'manufacturer': 'Different manufacturer', 'modelNumber': 'Different model'}
        result = self.request('equipment/ids/assign', {'request_key': ident(), 'entity_id': other,
                                                       'template_id': saved.result['id']})
        self.assertEqual(400, result.status)
        self.assertIsNone(self.catalog.assignment(self.group, other))

    def test_assignment_seeds_from_archived_matching_records_without_rewriting_them(self):
        archived = ident()
        self.entities[archived] = {**copy.deepcopy(self.entities[self.item]), 'id': archived, 'name': 'Older Drone', 'archived': True}
        result = self.request('equipment/ids/assign', {'request_key': ident(), 'entity_id': self.item, 'model_code': 'M4P'})
        self.assertEqual(200, result.status)
        self.assertEqual('DRONE-M4P-2', result.result['display_id'])
        self.assertIsNone(self.catalog.assignment(self.group, archived))

    def test_explicit_product_group_metadata_matches_existing_native_units(self):
        tag = {'id': ident(), 'name': 'C-Crate Product group: Drone fleet'}
        self.tags.append(tag)
        self.entities[self.item]['tags'] = [tag]
        other = ident()
        self.entities[other] = {**copy.deepcopy(self.entities[self.item]), 'id': other, 'name': 'Other drone',
                                'manufacturer': 'Different', 'modelNumber': 'Different', 'archived': True}
        result = self.request('equipment/ids/assign', {'request_key': ident(), 'entity_id': self.item, 'model_code': 'M4P'})
        self.assertEqual(200, result.status)
        self.assertEqual('DRONE-M4P-2', result.result['display_id'])

    def test_template_assignment_replay_conflict_and_resolution_are_scoped(self):
        saved = self.request('equipment/templates/save', {'request_key': ident(), 'fields': self.template_fields()})
        key = ident()
        first = self.request('equipment/ids/assign', {'request_key': key, 'entity_id': self.item, 'template_id': saved.result['id']})
        self.assertEqual(200, first.status)
        replay = self.request('equipment/ids/assign', {'request_key': key, 'entity_id': self.item, 'template_id': saved.result['id']})
        self.assertEqual(first.result, replay.result)
        other = ident()
        self.entities[other] = {**copy.deepcopy(self.entities[self.item]), 'id': other, 'name': 'Other Drone'}
        conflict = self.request('equipment/ids/assign', {'request_key': key, 'entity_id': other, 'template_id': saved.result['id']})
        self.assertEqual(409, conflict.status)
        resolved = self.request('equipment/ids/resolve', {'display_id': first.result['display_id']})
        self.assertEqual(self.item, resolved.result['entity_id'])
        self.assertEqual(403, self.request('equipment/ids/resolve', {'display_id': first.result['display_id']}, headers={'X-Workshop-Group': ident()}).status)


    def test_assignment_timeout_recovery_reuses_same_entity_and_does_not_create_product_again(self):
        original = self.catalog.assign_item
        def after_commit(*args, **kwargs):
            result = original(*args, **kwargs)
            raise OSError('lost assignment response')
        self.catalog.assign_item = after_commit
        request_key = ident()
        payload = {'request_key': request_key, 'entity_id': self.item, 'model_code': 'M4P'}
        first = self.request('equipment/ids/assign', payload)
        self.assertEqual(503, first.status)
        self.catalog.assign_item = original
        replay = self.request('equipment/ids/assign', payload)
        self.assertEqual(200, replay.status)
        self.assertEqual('DRONE-M4P-1', replay.result['display_id'])
        with self.ledger.connection() as db:
            self.assertEqual(1, db.execute('SELECT COUNT(*) FROM equipment_products').fetchone()[0])
        changed = self.request('equipment/ids/assign', {**payload, 'model_code': 'OTHER'})
        self.assertEqual(409, changed.status)
        with self.ledger.connection() as db:
            self.assertEqual('M4P', db.execute('SELECT model_code FROM equipment_products').fetchone()['model_code'])

    def test_assignment_reused_key_with_another_item_conflicts_before_allocation(self):
        request_key = ident()
        first = self.request('equipment/ids/assign', {'request_key': request_key, 'entity_id': self.item, 'model_code': 'M4P'})
        self.assertEqual(200, first.status)
        other = ident()
        self.entities[other] = {**copy.deepcopy(self.entities[self.item]), 'id': other, 'name': 'Second Drone'}
        conflict = self.request('equipment/ids/assign', {'request_key': request_key, 'entity_id': other, 'model_code': 'OTHER'})
        self.assertEqual(409, conflict.status)
        with self.ledger.connection() as db:
            self.assertEqual(1, db.execute('SELECT COUNT(*) FROM equipment_products').fetchone()[0])


    def test_assignment_retry_recovers_product_registration_committed_before_assignment(self):
        original = self.catalog.assign_item
        self.catalog.assign_item = lambda *args, **kwargs: (_ for _ in ()).throw(OSError('interrupted'))
        key = ident()
        payload = {'request_key': key, 'entity_id': self.item, 'model_code': 'M4P'}
        self.assertEqual(503, self.request('equipment/ids/assign', payload).status)
        with self.ledger.connection() as db:
            self.assertEqual(1, db.execute('SELECT COUNT(*) FROM equipment_products').fetchone()[0])
        self.catalog.assign_item = original
        retried = self.request('equipment/ids/assign', payload)
        self.assertEqual(200, retried.status)
        self.assertEqual('DRONE-M4P-1', retried.result['display_id'])

    def test_template_replay_digest_ignores_newly_matching_native_members(self):
        key = ident()
        payload = {'request_key': key, 'fields': self.template_fields()}
        first = self.request('equipment/templates/save', payload)
        self.assertEqual(200, first.status)
        extra = ident()
        self.entities[extra] = {**copy.deepcopy(self.entities[self.item]), 'id': extra, 'name': 'Legacy Drone'}
        replay = self.request('equipment/templates/save', payload)
        self.assertEqual(200, replay.status)
        self.assertEqual(first.result['id'], replay.result['id'])

    def test_explicit_product_group_is_part_of_persisted_product_identity(self):
        red = {'id': ident(), 'name': 'C-Crate Product group: Red fleet'}
        blue = {'id': ident(), 'name': 'C-Crate Product group: Blue fleet'}
        self.tags.extend([red, blue])
        self.entities[self.item]['tags'] = [red]
        first = self.request('equipment/templates/save', {'request_key': ident(), 'source_entity_id': self.item, 'fields': {'model_code': 'M4P'}})
        self.assertEqual(200, first.status)
        second_id = ident()
        self.entities[second_id] = {**copy.deepcopy(self.entities[self.item]), 'id': second_id, 'tags': [blue]}
        second = self.request('equipment/templates/save', {'request_key': ident(), 'source_entity_id': second_id, 'fields': {'model_code': 'M4P-BLUE'}})
        self.assertEqual(200, second.status)
        self.assertNotEqual(first.result['product_id'], second.result['product_id'])


    def test_template_refresh_excludes_target_from_seed_and_allows_blank_metadata(self):
        fields = self.template_fields(manufacturer='', model_number='', model_code='GENERIC')
        saved = self.request('equipment/templates/save', {'request_key': ident(), 'fields': fields})
        self.assertEqual(200, saved.status)
        assignment = self.request('equipment/ids/assign', {'request_key': ident(), 'entity_id': self.item, 'template_id': saved.result['id']})
        self.assertEqual(200, assignment.status)
        self.assertEqual('DRONE-GENERIC-1', assignment.result['display_id'])


    def test_template_assignment_group_identity_overrides_metadata_conflict(self):
        tag = {'id': ident(), 'name': 'C-Crate Product group: Shared rig'}
        self.tags.append(tag)
        self.entities[self.item]['tags'] = [tag]
        saved = self.request('equipment/templates/save', {'request_key': ident(), 'source_entity_id': self.item,
                                                           'fields': {'model_code': 'RIG'}})
        other = ident()
        self.entities[other] = {**copy.deepcopy(self.entities[self.item]), 'id': other,
                                'manufacturer': 'Different maker', 'modelNumber': 'Different model', 'tags': [tag]}
        result = self.request('equipment/ids/assign', {'request_key': ident(), 'entity_id': other,
                                                       'template_id': saved.result['id']})
        self.assertEqual(200, result.status)
        self.assertEqual(saved.result['product_id'], result.result['product_id'])

    def test_same_explicit_product_group_overrides_metadata_differences(self):
        tag = {'id': ident(), 'name': 'C-Crate Product group: Same rig'}
        self.tags.append(tag)
        first_item = self.item
        self.entities[first_item]['tags'] = [tag]
        first = self.request('equipment/templates/save', {'request_key': ident(), 'source_entity_id': first_item, 'fields': {'model_code': 'RIG'}})
        second_item = ident()
        self.entities[second_item] = {**copy.deepcopy(self.entities[first_item]), 'id': second_item,
                                      'manufacturer': 'Other maker', 'modelNumber': 'Different model', 'tags': [tag]}
        second = self.request('equipment/templates/save', {'request_key': ident(), 'source_entity_id': second_item, 'fields': {'model_code': 'RIG'}})
        self.assertEqual(200, first.status)
        self.assertEqual(200, second.status)
        self.assertEqual(first.result['product_id'], second.result['product_id'])

    def test_registration_retry_accepts_changed_inventory_matches(self):
        original = self.catalog.assign_item
        self.catalog.assign_item = lambda *args, **kwargs: (_ for _ in ()).throw(OSError('interrupted'))
        key = ident()
        payload = {'request_key': key, 'entity_id': self.item, 'model_code': 'M4P'}
        self.assertEqual(503, self.request('equipment/ids/assign', payload).status)
        old = ident()
        self.entities[old] = {**copy.deepcopy(self.entities[self.item]), 'id': old, 'name': 'Legacy unit'}
        self.catalog.assign_item = original
        retry = self.request('equipment/ids/assign', payload)
        self.assertEqual(200, retry.status)
        self.assertEqual('DRONE-M4P-2', retry.result['display_id'])

    def test_template_assignment_refreshes_members_added_after_template_save(self):
        saved = self.request('equipment/templates/save', {'request_key': ident(), 'fields': self.template_fields()})
        extra = ident()
        self.entities[extra] = {**copy.deepcopy(self.entities[self.item]), 'id': extra, 'name': 'Late legacy drone'}
        assigned = self.request('equipment/ids/assign', {'request_key': ident(), 'entity_id': self.item, 'template_id': saved.result['id']})
        self.assertEqual(200, assigned.status)
        self.assertEqual('DRONE-M4P-2', assigned.result['display_id'])

    def test_id_mapping_caps_batch_and_ignores_foreign_or_malformed_uuids(self):
        saved = self.request('equipment/templates/save', {'request_key': ident(), 'fields': self.template_fields()})
        assignment = self.request('equipment/ids/assign', {'request_key': ident(), 'entity_id': self.item, 'template_id': saved.result['id']}).result
        mapping = self.request('equipment/ids?ids=' + self.item)
        self.assertEqual(200, mapping.status)
        self.assertEqual({self.item: {'product_id': assignment['product_id'], 'display_id': assignment['display_id']}}, mapping.result)
        self.assertEqual(404, self.request('equipment/ids?ids=' + ident()).status)
        self.assertEqual(400, self.request('equipment/ids?ids=' + ','.join(ident() for _ in range(101))).status)
        self.assertEqual(400, self.request('equipment/ids?ids=bad').status)
        del self.entities[self.item]
        self.assertEqual(404, self.request('equipment/ids?ids=' + self.item).status)
        self.assertEqual(404, self.request('equipment/ids/resolve', {'display_id': assignment['display_id']}).status)
        self.entities[self.item] = {'id': self.item, 'name': 'Drone', 'entityType': {'id': self.kind, 'name': 'Drone', 'isLocation': False}, 'manufacturer': 'Maker', 'modelNumber': 'Mini 4 Pro', 'tags': [], 'attachments': []}

    def test_active_suggestions_are_type_collection_and_query_scoped_with_assigned_model_code(self):
        other = ident()
        archived = ident()
        assigned = ident()
        self.entities[other] = {**copy.deepcopy(self.entities[self.item]), 'id': other, 'name': 'Drone Case'}
        self.entities[archived] = {**copy.deepcopy(self.entities[self.item]), 'id': archived, 'name': 'Drone Archived', 'archived': True}
        self.entities[assigned] = {**copy.deepcopy(self.entities[self.item]), 'id': assigned, 'name': 'Camera', 'entityType': {'id': ident(), 'name': 'Camera', 'isLocation': False}}
        self.entity_collections[other] = ident()
        product = self.catalog.register_product(self.group, self.actor, ident(), {'entity_type_id': self.kind, 'type_prefix': 'DRONE', 'manufacturer': 'Maker', 'model_number': 'M4', 'model_code': 'CODE'}, [self.item])
        self.catalog.assign_item(self.group, self.actor, self.item, product['id'], ident())
        response = self.request('equipment/suggestions?type_id=' + self.kind + '&q=drone')
        self.assertEqual(200, response.status)
        self.assertEqual(1, len(response.result))
        self.assertEqual({'id': self.item, 'name': 'Drone', 'manufacturer': 'Maker', 'modelNumber': 'Mini 4 Pro', 'tagIds': [], 'modelCode': 'CODE'}, response.result[0])
        self.assertEqual([], self.request('equipment/suggestions?type_id=' + self.kind + '&q=missing').result)
        empty = self.request('equipment/suggestions?type_id=' + self.kind + '&q=')
        self.assertEqual(200, empty.status)
        self.assertEqual([], empty.result)
        self.assertEqual([], self.request('equipment/suggestions?type_id=' + self.kind + '&q=%20%20').result)
        self.assertEqual([], self.request('equipment/suggestions?type_id=' + self.kind).result)
        for index in range(10):
            extra = ident()
            self.entities[extra] = {**copy.deepcopy(self.entities[self.item]), 'id': extra, 'name': f'Drone {index:02d}'}
        limited = self.request('equipment/suggestions?type_id=' + self.kind + '&q=drone&limit=100')
        self.assertEqual(200, limited.status)
        self.assertEqual(8, len(limited.result))
        self.assertEqual(8, len(self.request('equipment/suggestions?type_id=' + self.kind + '&q=drone').result))
        self.assertEqual(400, self.request('equipment/suggestions?type_id=bad').status)

    def test_product_listing_and_code_edit_are_member_scoped(self):
        product = self.catalog.register_product(self.group, self.actor, ident(), {
            'entity_type_id': self.kind, 'type_prefix': 'DRONE', 'manufacturer': 'Maker',
            'model_number': 'Mini 4 Pro', 'model_code': 'OLD',
        }, [self.item, self.location])
        member_context = self.request('context', headers={'Cookie': 'hb.auth.token=member; hb.auth.remember=true'}).result
        headers = {'Cookie': 'hb.auth.token=member; hb.auth.remember=true', 'X-Workshop-Identity': member_context['identity']}
        listed = self.request('equipment/products', headers=headers)
        self.assertEqual(200, listed.status)
        self.assertEqual([product['id']], [row['id'] for row in listed.result])
        self.assertEqual(1, listed.result[0]['active_item_count'])
        self.assertEqual([], listed.result[0]['assignments'])
        self.assertEqual(product['updated_at'], listed.result[0]['updated_at'])
        updated = self.request('equipment/products/code', {
            'product_id': product['id'], 'model_code': 'NEW', 'expected_updated_at': product['updated_at'],
            'request_key': ident(),
        }, headers=headers)
        self.assertEqual(200, updated.status)
        self.assertEqual('NEW', updated.result['model_code'])
        self.assertNotEqual(product['updated_at'], updated.result['updated_at'])
        with self.ledger.connection() as db:
            history = db.execute('SELECT actor_id FROM equipment_product_model_code_history WHERE group_id=? AND product_id=?',
                                 (self.group, product['id'])).fetchone()
        self.assertEqual(self.member, history['actor_id'])

    def test_products_reject_unauthenticated_and_foreign_collection_access(self):
        unauth = self.request('equipment/products', headers={'Cookie': ''})
        self.assertEqual(401, unauth.status)
        foreign = self.request('equipment/products', headers={'X-Workshop-Group': ident()})
        self.assertEqual(403, foreign.status)

    def test_product_code_edit_returns_duplicate_and_stale_conflicts(self):
        product = self.catalog.register_product(self.group, self.actor, ident(), {
            'entity_type_id': self.kind, 'type_prefix': 'DRONE', 'manufacturer': 'Maker',
            'model_number': 'Mini 4 Pro', 'model_code': 'OLD',
        }, [self.item])
        duplicate = self.catalog.register_product(self.group, self.actor, ident(), {
            'entity_type_id': self.kind, 'type_prefix': 'DRONE', 'manufacturer': 'Maker',
            'model_number': 'Other', 'model_code': 'TAKEN',
        }, [])
        self.catalog.update_product_model_code(self.group, self.actor, duplicate['id'], 'TAKEN', duplicate['updated_at'], ident())
        dupe = self.request('equipment/products/code', {
            'product_id': product['id'], 'model_code': 'TAKEN', 'expected_updated_at': product['updated_at'], 'request_key': ident(),
        })
        self.assertEqual(409, dupe.status)
        stale = self.request('equipment/products/code', {
            'product_id': product['id'], 'model_code': 'NEW', 'expected_updated_at': 'stale', 'request_key': ident(),
        })
        self.assertEqual(409, stale.status)

    def test_suggestion_reads_canonical_code_and_assignment_cannot_revert_it(self):
        product = self.catalog.register_product(self.group, self.actor, ident(), {
            'entity_type_id': self.kind, 'type_prefix': 'DRONE', 'manufacturer': 'Maker',
            'model_number': 'Mini 4 Pro', 'model_code': 'OLD',
        }, [self.item])
        assigned = self.catalog.assign_item(self.group, self.actor, self.item, product['id'], ident())
        with self.ledger.connection() as db:
            current_updated_at = db.execute('SELECT updated_at FROM equipment_products WHERE id=?', (product['id'],)).fetchone()['updated_at']
        self.catalog.update_product_model_code(self.group, self.actor, product['id'], 'NEW', current_updated_at, ident())
        suggestion = self.request('equipment/suggestions?type_id=' + self.kind + '&q=drone')
        self.assertEqual('NEW', suggestion.result[0]['modelCode'])
        conflict = self.request('equipment/ids/assign', {'request_key': ident(), 'entity_id': self.item, 'model_code': 'OLD'})
        self.assertEqual(409, conflict.status)
        self.assertEqual('NEW', self.catalog.current_product_model_code(self.group, assigned['product_id']))


if __name__ == '__main__':
    unittest.main()
