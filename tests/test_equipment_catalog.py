import concurrent.futures
import hashlib
import json
import sqlite3
import tempfile
import unittest
import uuid
from contextlib import closing
from pathlib import Path

from equipment_catalog import EquipmentCatalog, Conflict


def uid():
    return str(uuid.uuid4())


class EquipmentCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.catalog = EquipmentCatalog(Path(self.tmp.name) / 'catalog.sqlite')
        self.group, self.actor = uid(), uid()
        self.type_id = uid()
        self.product = {'entity_type_id': self.type_id, 'manufacturer': 'DJI', 'model_number': 'Air 2S', 'model_code': ' 2s ', 'type_prefix': 'DRONE'}

    def tearDown(self):
        self.tmp.cleanup()

    def payload(self, **extra):
        return {'name': 'Air 2S', 'entity_type_id': self.type_id, 'manufacturer': 'DJI',
                'model_number': 'Air 2S', 'model_code': ' 2s ', 'description': 'Drone', 'tag_ids': [], **extra}



    def test_legacy_schema_template_and_assignment_replay_after_migration(self):
        path = Path(self.tmp.name) / 'legacy-replay.sqlite'
        group, actor, request_key, assign_key = uid(), uid(), uid(), uid()
        type_id, entity_id, product_id, template_id = uid(), uid(), uid(), uid()
        payload = {'name': 'Kit', 'entity_type_id': type_id, 'manufacturer': 'Maker', 'model_number': 'Kit model',
                   'model_code': 'KIT', 'description': 'shared', 'tag_ids': []}
        encoded = json.dumps(payload, sort_keys=True)
        digest = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        legacy_identity = digest([type_id, 'maker', 'kit model'])
        legacy_template_result = {**payload, 'id': template_id, 'product_id': product_id, 'archived': False,
                                  'created_at': '2026-01-01T00:00:00Z', 'updated_at': '2026-01-01T00:00:00Z', 'type_prefix': 'DRONE'}
        assignment = {'group_id': group, 'entity_id': entity_id, 'product_id': product_id,
                      'display_id': 'DRONE-KIT-1', 'type_prefix': 'DRONE', 'model_code': 'KIT',
                      'number': 1, 'request_key': assign_key, 'actor_id': actor,
                      'assigned_at': '2026-01-01T00:00:00Z', 'deleted': 0}
        legacy_template_digest = digest({'payload': payload, 'type_prefix': 'DRONE', 'matching_entity_ids': [entity_id],
                                         'template_id': None, 'expected_updated_at': None})
        with closing(sqlite3.connect(path)) as db, db:
            db.executescript('''
            CREATE TABLE equipment_products(id TEXT PRIMARY KEY, group_id TEXT NOT NULL, entity_type_id TEXT NOT NULL,
              type_prefix TEXT NOT NULL, manufacturer TEXT NOT NULL, model_number TEXT NOT NULL, model_code TEXT NOT NULL,
              high_water INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              identity_key TEXT NOT NULL DEFAULT '', UNIQUE(group_id,id));
            CREATE TABLE equipment_templates(id TEXT PRIMARY KEY, group_id TEXT NOT NULL, product_id TEXT NOT NULL,
              payload TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE equipment_template_history(sequence INTEGER PRIMARY KEY, group_id TEXT NOT NULL, template_id TEXT NOT NULL,
              actor_id TEXT NOT NULL, request_key TEXT NOT NULL, action TEXT NOT NULL, payload TEXT NOT NULL,
              created_at TEXT NOT NULL, UNIQUE(group_id,request_key));
            CREATE TABLE equipment_catalog_requests(group_id TEXT NOT NULL, request_key TEXT NOT NULL, action TEXT NOT NULL,
              request_hash TEXT NOT NULL, result_id TEXT NOT NULL, result_json TEXT NOT NULL, created_at TEXT NOT NULL,
              PRIMARY KEY(group_id,request_key));
            CREATE TABLE equipment_product_members(group_id TEXT NOT NULL, product_id TEXT NOT NULL, entity_id TEXT NOT NULL,
              PRIMARY KEY(group_id,product_id,entity_id));
            CREATE TABLE equipment_assignments(group_id TEXT NOT NULL, entity_id TEXT NOT NULL, product_id TEXT NOT NULL,
              display_id TEXT NOT NULL, type_prefix TEXT NOT NULL, model_code TEXT NOT NULL, number INTEGER NOT NULL,
              request_key TEXT NOT NULL, actor_id TEXT NOT NULL, assigned_at TEXT NOT NULL,
              PRIMARY KEY(group_id,entity_id), UNIQUE(group_id,display_id));
            CREATE TABLE equipment_assignment_requests(group_id TEXT NOT NULL, request_key TEXT NOT NULL, request_hash TEXT NOT NULL,
              entity_id TEXT NOT NULL, product_id TEXT NOT NULL, result_json TEXT NOT NULL, created_at TEXT NOT NULL,
              PRIMARY KEY(group_id,request_key));
            ''')
            db.execute('INSERT INTO equipment_products VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                       (product_id, group, type_id, 'DRONE', 'Maker', 'Kit model', 'KIT', 1, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', legacy_identity))
            db.execute('INSERT INTO equipment_templates VALUES(?,?,?,?,0,?,?)',
                       (template_id, group, product_id, encoded, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z'))
            db.execute('INSERT INTO equipment_template_history(group_id,template_id,actor_id,request_key,action,payload,created_at) VALUES(?,?,?,?,?,?,?)',
                       (group, template_id, actor, request_key, 'saved', encoded, '2026-01-01T00:00:00Z'))
            db.execute('INSERT INTO equipment_catalog_requests VALUES(?,?,?,?,?,?,?)',
                       (group, request_key, 'template', legacy_template_digest, template_id, json.dumps(legacy_template_result, sort_keys=True), '2026-01-01T00:00:00Z'))
            db.execute('INSERT INTO equipment_product_members VALUES(?,?,?)', (group, product_id, entity_id))
            db.execute('INSERT INTO equipment_assignments VALUES(?,?,?,?,?,?,?,?,?,?)', tuple(assignment[key] for key in
                       ('group_id','entity_id','product_id','display_id','type_prefix','model_code','number','request_key','actor_id','assigned_at')))
            db.execute('INSERT INTO equipment_assignment_requests VALUES(?,?,?,?,?,?,?)',
                       (group, assign_key, digest([entity_id, product_id]), entity_id, product_id, json.dumps(assignment, sort_keys=True), '2026-01-01T00:00:00Z'))
        current = EquipmentCatalog(path)
        replay = current.save_template(group, actor, request_key, payload, [entity_id], type_prefix='DRONE')
        self.assertEqual(template_id, replay['id'])
        self.assertEqual(product_id, replay['product_id'])
        assignment_replay = current.assign_item(group, actor, entity_id, product_id, assign_key)
        self.assertEqual('DRONE-KIT-1', assignment_replay['display_id'])

    def test_additive_product_group_schema_migration_preserves_legacy_products(self):
        path = Path(self.tmp.name) / 'legacy.sqlite'
        group, product_id, type_id = uid(), uid(), uid()
        legacy_identity = hashlib.sha256(json.dumps([type_id, 'dji', 'air 2s'], separators=(',', ':')).encode()).hexdigest()
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE equipment_products(id TEXT PRIMARY KEY, group_id TEXT NOT NULL, entity_type_id TEXT NOT NULL, type_prefix TEXT NOT NULL, manufacturer TEXT NOT NULL, model_number TEXT NOT NULL, model_code TEXT NOT NULL, high_water INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, identity_key TEXT NOT NULL DEFAULT '', UNIQUE(group_id,id))")
            db.execute('INSERT INTO equipment_products VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                       (product_id, group, type_id, 'DRONE', 'DJI', 'Air 2S', '2S', 4, 't', 't', legacy_identity))
        migrated = EquipmentCatalog(path)
        with migrated.ledger.connection() as db:
            row = db.execute('SELECT * FROM equipment_products WHERE id=?', (product_id,)).fetchone()
            self.assertIn('product_group', row.keys())
            self.assertEqual('', row['product_group'])
            self.assertNotEqual(legacy_identity, row['identity_key'])
            self.assertEqual(4, row['high_water'])

    def test_collection_scoping_validation_normalization_and_audit(self):
        template = self.catalog.save_template(self.group, self.actor, uid(), self.payload(), type_prefix='DRONE')
        self.assertEqual(template['model_code'], '2S')
        self.assertEqual([template], self.catalog.list_templates(self.group))
        self.assertEqual([], self.catalog.list_templates(uid()))
        with self.assertRaises(ValueError):
            self.catalog.save_template(self.group, self.actor, uid(), {'name': 'Missing fields'})
        with self.assertRaises(ValueError):
            self.catalog.save_template(self.group, self.actor, uid(), self.payload(serial_number='bad'), type_prefix='DRONE')
        with self.assertRaises(ValueError):
            self.catalog.save_template(self.group, self.actor, uid(), self.payload(extra_field=True), type_prefix='DRONE')
        history = self.catalog.template_history(self.group, template['id'])
        self.assertEqual(history[0]['actor_id'], self.actor)
        self.assertTrue(history[0]['created_at'])

    def test_code_unique_per_type_and_archive_reserves_it(self):
        first = self.catalog.save_template(self.group, self.actor, uid(), self.payload(), type_prefix='DRONE')
        other_type = self.payload(entity_type_id=uid())
        second = self.catalog.save_template(self.group, self.actor, uid(), other_type, type_prefix='CAMERA')
        with self.assertRaises(Conflict):
            self.catalog.save_template(self.group, self.actor, uid(), self.payload(name='Other', model_number='Different model'), type_prefix='DRONE')
        self.catalog.archive_template(self.group, self.actor, first['id'], uid())
        self.assertEqual([second], [row for row in self.catalog.list_templates(self.group) if row['id'] == second['id']])
        self.assertNotIn(first['id'], [row['id'] for row in self.catalog.list_templates(self.group)])
        with self.assertRaises(Conflict):
            self.catalog.save_template(self.group, self.actor, uid(), self.payload(name='Replacement', model_number='Different model'), type_prefix='DRONE')

    def test_archive_restore_is_replay_safe_and_records_each_lifecycle_transition(self):
        template = self.catalog.save_template(self.group, self.actor, uid(), self.payload(), type_prefix='DRONE')
        archive_key, restore_key = uid(), uid()
        archived = self.catalog.archive_template(self.group, self.actor, template['id'], archive_key)
        self.assertTrue(archived['archived'])
        self.assertEqual(archived, self.catalog.archive_template(self.group, self.actor, template['id'], archive_key))
        self.assertEqual([], self.catalog.list_templates(self.group))
        self.assertEqual([archived], self.catalog.list_templates(self.group, include_archived=True))
        restored = self.catalog.restore_template(self.group, self.actor, template['id'], restore_key)
        self.assertFalse(restored['archived'])
        self.assertEqual(restored, self.catalog.restore_template(self.group, self.actor, template['id'], restore_key))
        self.assertEqual([restored], self.catalog.list_templates(self.group))
        self.assertEqual(['saved', 'archived', 'restored'], [row['action'] for row in self.catalog.template_history(self.group, template['id'])])
        with self.assertRaises(Conflict):
            self.catalog.restore_template(self.group, self.actor, template['id'], archive_key)

    def test_matching_legacy_members_seed_after_active_and_archived_records_without_id_mutation(self):
        ids = [uid() for _ in range(5)]
        product = self.catalog.register_product(self.group, self.actor, uid(), self.product, ids)
        self.assertEqual(product['model_code'], '2S')
        for entity in ids:
            self.assertIsNone(self.catalog.assignment(self.group, entity))
        new_entity = uid()
        assignment = self.catalog.assign_item(self.group, self.actor, new_entity, product['id'], uid())
        self.assertEqual(assignment['number'], 6)
        self.assertEqual(assignment['display_id'], 'DRONE-2S-6')
        self.assertEqual(new_entity, self.catalog.resolve_id(self.group, 'DRONE-2S-6'))
        self.assertIsNone(self.catalog.resolve_id(uid(), 'DRONE-2S-6'))

    def test_product_membership_and_assignment_stability_nonreuse_and_replay(self):
        product = self.catalog.register_product(self.group, self.actor, uid(), self.product, [uid(), uid()])
        entity, request = uid(), uid()
        one = self.catalog.assign_item(self.group, self.actor, entity, product['id'], request)
        self.assertEqual(one, self.catalog.assign_item(self.group, self.actor, entity, product['id'], request))
        self.catalog.record_entity_context(self.group, entity, name='Renamed', location_id=uid())
        self.assertEqual(one, self.catalog.assignment(self.group, entity))
        with self.assertRaises(Conflict):
            self.catalog.assign_item(self.group, self.actor, uid(), product['id'], request)
        deleted = uid()
        second = self.catalog.assign_item(self.group, self.actor, deleted, product['id'], uid())
        self.assertEqual(one['number'] + 1, second['number'])
        self.catalog.delete_assignment(self.group, deleted)
        third = self.catalog.assign_item(self.group, self.actor, uid(), product['id'], uid())
        self.assertEqual(second['number'] + 1, third['number'])
        with self.assertRaises(Conflict):
            self.catalog.assign_item(self.group, self.actor, entity, uid(), uid())


    def test_template_edit_preserves_product_and_sequence_and_reserves_old_codes(self):
        payload = self.payload()
        first = self.catalog.save_template(self.group, self.actor, uid(), payload, type_prefix='DRONE')
        product_id = first['product_id']
        first_assignment = self.catalog.assign_item(self.group, self.actor, uid(), product_id, uid())
        changed = {**payload, 'model_code': ' M4P ', 'model_number': 'Air 2S Combo', 'description': 'Updated'}
        updated = self.catalog.save_template(self.group, self.actor, uid(), changed,
                                             template_id=first['id'], expected_updated_at=first['updated_at'],
                                             type_prefix='DRONE')
        self.assertEqual(product_id, updated['product_id'])
        self.assertEqual('M4P', updated['model_code'])
        second_assignment = self.catalog.assign_item(self.group, self.actor, uid(), product_id, uid())
        self.assertEqual(first_assignment['number'] + 1, second_assignment['number'])
        self.assertEqual('DRONE-M4P-2', second_assignment['display_id'])
        with self.assertRaises(Conflict):
            self.catalog.save_template(self.group, self.actor, uid(), self.payload(name='Other', model_number='Other'), type_prefix='DRONE')

    def test_template_replay_is_atomic_and_authoritative_prefix_is_required(self):
        req = uid()
        saved = self.catalog.save_template(self.group, self.actor, req, self.payload(), type_prefix='DRONE')
        replay = self.catalog.save_template(self.group, self.actor, req, self.payload(), type_prefix='DRONE')
        self.assertEqual(saved, replay)
        with self.assertRaises(Conflict):
            self.catalog.save_template(self.group, self.actor, req, self.payload(description='changed'), type_prefix='DRONE')
        with self.assertRaises(ValueError):
            self.catalog.save_template(self.group, self.actor, uid(), self.payload())
        product = self.catalog.register_product(self.group, self.actor, uid(), self.product, [])
        self.assertEqual('DRONE', product['type_prefix'])

    def test_product_registration_replay_and_code_collision_across_native_types(self):
        request = uid()
        product = self.catalog.register_product(self.group, self.actor, request, self.product, [])
        self.assertEqual(product, self.catalog.register_product(self.group, self.actor, request, self.product, []))
        with self.assertRaises(Conflict):
            self.catalog.register_product(self.group, self.actor, request, {**self.product, 'model_number': 'Different'}, [])
        with self.assertRaises(Conflict):
            self.catalog.register_product(self.group, self.actor, uid(), {**self.product, 'entity_type_id': uid()}, [])

    def test_assignment_key_bound_before_existing_entity_shortcut_and_tombstone_replay(self):
        product = self.catalog.register_product(self.group, self.actor, uid(), self.product, [])
        entity, key1, key2 = uid(), uid(), uid()
        assigned = self.catalog.assign_item(self.group, self.actor, entity, product['id'], key1)
        self.assertEqual(assigned, self.catalog.assign_item(self.group, self.actor, entity, product['id'], key2))
        with self.assertRaises(Conflict):
            self.catalog.assign_item(self.group, self.actor, uid(), product['id'], key1)
        self.catalog.delete_assignment(self.group, entity)
        self.assertEqual(assigned, self.catalog.assign_item(self.group, self.actor, entity, product['id'], key1))
        self.assertEqual(assigned['display_id'], self.catalog.resolve_id(self.group, assigned['display_id']) and assigned['display_id'])



    def test_incomplete_product_metadata_does_not_merge_distinct_names(self):
        tripod = self.catalog.save_template(self.group, self.actor, uid(),
            self.payload(name='Tripod', manufacturer='', model_number='', model_code='TP'), type_prefix='ACCESSORY')
        stand = self.catalog.save_template(self.group, self.actor, uid(),
            self.payload(name='Light stand', manufacturer='', model_number='', model_code='LS'), type_prefix='ACCESSORY')
        self.assertNotEqual(tripod['product_id'], stand['product_id'])
        with self.assertRaises(Conflict):
            self.catalog.save_template(self.group, self.actor, uid(),
                self.payload(name='Unknown stand', manufacturer='', model_number='', model_code='TP'), type_prefix='ACCESSORY')

    def test_template_edit_cannot_duplicate_another_product_identity(self):
        first = self.catalog.save_template(self.group, self.actor, uid(),
            self.payload(name='Camera A', manufacturer='Acme', model_number='Camera A', model_code='CA'), type_prefix='CAMERA')
        self.catalog.save_template(self.group, self.actor, uid(),
            self.payload(name='Camera B', manufacturer='Acme', model_number='Camera B', model_code='CB'), type_prefix='CAMERA')
        with self.assertRaises(Conflict):
            self.catalog.save_template(self.group, self.actor, uid(),
                self.payload(name='Camera B', manufacturer='Acme', model_number='Camera B', model_code='CA2'),
                type_prefix='CAMERA', template_id=first['id'], expected_updated_at=first['updated_at'])

    def test_native_type_code_and_display_base_reservations_survive_prefix_changes(self):
        first = self.catalog.save_template(self.group, self.actor, uid(),
            self.payload(name='Sensor A', manufacturer='Acme', model_number='Sensor A', model_code='S'), type_prefix='DRONE-2')
        changed = self.catalog.save_template(self.group, self.actor, uid(),
            self.payload(name='Sensor A', manufacturer='Acme', model_number='Sensor A', model_code='SA2'),
            type_prefix='AIRCRAFT', template_id=first['id'], expected_updated_at=first['updated_at'])
        with self.assertRaises(Conflict):
            self.catalog.save_template(self.group, self.actor, uid(),
                self.payload(name='Other Sensor', manufacturer='Other', model_number='Other', model_code='S'), type_prefix='OTHER')
        self.assertEqual(first['product_id'], changed['product_id'])
        with self.assertRaises(Conflict):
            self.catalog.register_product(self.group, self.actor, uid(),
                {'entity_type_id': uid(), 'type_prefix': 'DRONE', 'manufacturer': 'Other', 'model_number': 'Other', 'model_code': '2-S'}, [])

    def test_concurrent_same_template_request_returns_one_saved_result(self):
        request = uid()
        def save(_):
            return self.catalog.save_template(self.group, self.actor, request, self.payload(), type_prefix='DRONE')
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(save, range(12)))
        self.assertTrue(all(item == results[0] for item in results))
        self.assertEqual(1, len(self.catalog.list_templates(self.group)))

    def test_concurrent_first_assignment_is_unique_and_monotonic(self):
        product = self.catalog.register_product(self.group, self.actor, uid(), self.product, [])
        entities = [uid() for _ in range(12)]
        def assign(entity):
            return self.catalog.assign_item(self.group, self.actor, entity, product['id'], uid())
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            assignments = list(pool.map(assign, entities))
        numbers = sorted(row['number'] for row in assignments)
        self.assertEqual(list(range(1, 13)), numbers)
        self.assertEqual(12, len({row['display_id'] for row in assignments}))


if __name__ == '__main__':
    unittest.main()
