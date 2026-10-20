import unittest
from uuid import uuid4

import desktop_api


class EquipmentLabelApiTests(unittest.TestCase):
    def test_preview_uses_authenticated_catalog_assignment_not_browser_display_id(self):
        group, actor, entity_id = (str(uuid4()) for _ in range(3))
        native = {'id': entity_id, 'name': 'Drone', 'displayId': 'HB-4', 'updatedAt': 'native-v1'}

        class Client:
            def entity(self, requested):
                if requested != entity_id:
                    raise AssertionError('unexpected native entity lookup')
                return dict(native)

        class Catalog:
            def assignment(self, requested_group, requested_entity):
                if requested_group == group and requested_entity == entity_id:
                    return {'entity_id': entity_id, 'display_id': 'DRONE-2S-6'}
                return None

        class Layouts:
            def preview(self, client, requested_group, requested_actor, data, deadline=None):
                entity = client.entity(data['entity_ids'][0])
                return {'display_id': entity['displayId'], 'item_path': f"/item/{entity['id']}"}

        deps = {
            'ledger': object(), 'native_jobs': object(), 'badges': object(),
            'equipment_catalog': Catalog(), 'label_layouts': Layouts(),
        }
        ctx = {'client': Client(), 'group': group, 'actor': actor, 'manager': True}
        result = desktop_api.post_action('labels/preview', {
            'mode': 'item', 'entity_ids': [entity_id], 'display_id': 'BROWSER-FORGED-99',
            'template_id': 'starter:supvan:left', 'template_revision': 0,
        }, ctx, deps, None)
        self.assertEqual(result['display_id'], 'DRONE-2S-6')
        self.assertEqual(result['item_path'], f'/item/{entity_id}')
        self.assertNotEqual(result['display_id'], 'BROWSER-FORGED-99')


if __name__ == '__main__':
    unittest.main()
