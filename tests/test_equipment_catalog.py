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
        template = self.catalog.save_template(self.group, self.actor, uid(), self.payload())
        self.assertEqual(template['model_code'], '2S')
        self.assertEqual([template], self.catalog.list_templates(self.group))
        self.assertEqual([], self.catalog.list_templates(uid()))
        with self.assertRaises(ValueError):
            self.catalog.save_template(self.group, self.actor, uid(), {'name': 'Missing fields'})
        with self.assertRaises(ValueError):
            self.catalog.save_template(self.group, self.actor, uid(), self.payload(serial_number='bad'))
        with self.assertRaises(ValueError):
            self.catalog.save_template(self.group, self.actor, uid(), self.payload(extra_field=True))
        history = self.catalog.template_history(self.group, template['id'])
        self.assertEqual(history[0]['actor_id'], self.actor)
        self.assertTrue(history[0]['created_at'])

    def test_code_unique_per_type_and_archive_reserves_it(self):
        first = self.catalog.save_template(self.group, self.actor, uid(), self.payload())
        other_type = self.payload(entity_type_id=uid())
        second = self.catalog.save_template(self.group, self.actor, uid(), other_type)
        with self.assertRaises(Conflict):
            self.catalog.save_template(self.group, self.actor, uid(), self.payload(name='Other', model_number='Different model'))
        self.catalog.archive_template(self.group, self.actor, first['id'], uid())
        self.assertEqual([second], [row for row in self.catalog.list_templates(self.group) if row['id'] == second['id']])
        self.assertNotIn(first['id'], [row['id'] for row in self.catalog.list_templates(self.group)])
        with self.assertRaises(Conflict):
            self.catalog.save_template(self.group, self.actor, uid(), self.payload(name='Replacement', model_number='Different model'))

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
