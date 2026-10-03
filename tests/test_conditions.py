import copy
import unittest
from conditions import FIELD, STATES, condition, checkout_blocker, update_payload


class Tests(unittest.TestCase):
    def setUp(self):
        self.entity = {'id': 'asset', 'entityType': {'id': 'type', 'isLocation': False},
            'parent': {'id': 'shelf'}, 'tags': [{'id': 'tag'}], 'quantity': 1,
            'fields': [{'id': 'custom', 'name': 'Calibration', 'type': 'text', 'textValue': 'keep'}],
            'serialNumber': 'serial', 'purchasePrice': 45, 'archived': False}

    def test_unreviewed_is_blocked(self):
        self.assertEqual(condition(self.entity), 'Unreviewed')
        self.assertIsNotNone(checkout_blocker(self.entity))

    def test_all_states_only_ready_is_eligible(self):
        for state in STATES:
            e = update_payload(self.entity, state)
            self.assertEqual(condition(e), state)
            self.assertEqual(checkout_blocker(e) is None, state == 'Ready')

    def test_update_preserves_native_metadata_and_input(self):
        original = copy.deepcopy(self.entity)
        payload = update_payload(self.entity, 'Ready')
        self.assertEqual(self.entity, original)
        for name in ('serialNumber', 'purchasePrice', 'quantity'):
            self.assertEqual(payload[name], original[name])
        self.assertEqual(payload['fields'][0], original['fields'][0])
        self.assertEqual(payload['parentId'], 'shelf')
        self.assertEqual(payload['tagIds'], ['tag'])

    def test_archived_always_blocked(self):
        e = update_payload(self.entity, 'Ready');e['archived'] = True
        self.assertEqual(condition(e), 'Archived')
        self.assertIsNotNone(checkout_blocker(e))

    def test_duplicate_or_incompatible_field_rejected(self):
        f = {'name': FIELD, 'type': 'text', 'textValue': 'Ready'}
        self.entity['fields'] = [f, copy.deepcopy(f)]
        with self.assertRaises(ValueError):update_payload(self.entity, 'Ready')
        self.entity['fields'] = [{'name': FIELD, 'type': 'number'}]
        with self.assertRaises(ValueError):update_payload(self.entity, 'Ready')

    def test_location_and_bulk_quantity_blocked(self):
        e = update_payload(self.entity, 'Ready');e['quantity'] = 2
        self.assertIsNotNone(checkout_blocker(e))
        e['entityType']['isLocation'] = True
        with self.assertRaises(ValueError):update_payload(e, 'Ready')


if __name__ == '__main__':unittest.main()
