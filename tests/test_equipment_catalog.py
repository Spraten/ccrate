import concurrent.futures
import tempfile
import unittest
import uuid
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
