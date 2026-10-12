import copy
import json
import pathlib
import sys
import tempfile
import unittest
from uuid import uuid4

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'ops'))
from workshop_views import build_view, scoped_equipment, resolve_workshop_code


def uid():
    return str(uuid4())


class Client:
    def __init__(self):
        self.nodes = {}
        self.summaries = []
        self.writes = []
        self.entity_reads = 0
        self.base = 'https://native.example'

    def add(self, name, *, location=False, parent=None, archived=False, **extra):
        key = uid()
        node = {'id': key, 'name': name, 'entityType': {'id': uid(), 'isLocation': location,
                'name': 'Location' if location else 'Equipment'}, 'parent': {'id': parent} if parent else None,
                'archived': archived, 'assetId': '', 'serialNumber': '', 'fields': [], 'attachments': [],
                'tags': [], 'description': '', **extra}
        self.nodes[key] = node
        self.summaries.append(copy.deepcopy(node))
        return key

    def entity(self, key):
        self.entity_reads += 1
        return copy.deepcopy(self.nodes[key])

    def entities(self, locations=False):
        return copy.deepcopy(self.summaries if locations else [e for e in self.summaries if not e['entityType']['isLocation']])


class WorkshopViewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.client = Client()
        self.other_cage = self.client.add('The Cage', location=True)
        self.cage = self.client.add('The Cage', location=True)
        self.rack = self.client.add('Rack 1', location=True, parent=self.cage)
        self.shelf = self.client.add('Shelf 1-A', location=True, parent=self.rack)
        self.box = self.client.add('Box 7', parent=self.shelf)
        self.tool = self.client.add('Drill', parent=self.box, assetId='000-123', serialNumber='SERIAL-1234')
        self.drawing_a, self.drawing_b = uid(), uid()
        self.state = {'revision': 2, 'layout': {'name': 'Workshop', 'width': 10, 'height': 8,
            'objects': [
                {'id': self.drawing_a, 'name': 'Shelf drawing', 'kind': 'Rack', 'x': 0, 'y': 0, 'width': 2, 'height': 1, 'rotation': 0, 'location_id': self.rack},
                {'id': self.drawing_b, 'name': 'Second view', 'kind': 'Rack', 'x': 3, 'y': 0, 'width': 2, 'height': 1, 'rotation': 0, 'location_id': self.rack},
            ]}}
        self.layout_path = pathlib.Path(self.tmp.name) / 'layout.json'
        self.layout_path.write_text(json.dumps(self.state))
        self.state = json.loads(self.layout_path.read_text())

    def tearDown(self):
        self.tmp.cleanup()

    def test_mixed_path_and_duplicate_cage_identity(self):
        self.client.summaries.append(copy.deepcopy(self.client.summaries[-1]))
        v = build_view(self.client, self.state, [], entity_id=self.tool)
        self.assertEqual([p['id'] for p in v['path']], [self.cage, self.rack, self.shelf, self.box, self.tool])
        self.assertEqual(v['selection']['kind'], 'containing')
        self.assertEqual({m['drawing_id'] for m in v['selection']['matches']}, {self.drawing_a, self.drawing_b})
        self.assertNotIn(self.other_cage, [p['id'] for p in v['path']])
        self.assertEqual(self.client.writes, [])

    def test_exact_requires_immediate_location_parent(self):
        self.assertEqual(build_view(self.client, self.state, [], entity_id=self.rack)['selection']['kind'], 'exact')
        self.assertEqual(build_view(self.client, self.state, [], entity_id=self.shelf)['selection']['kind'], 'containing')
        direct = self.client.add('Direct drill', parent=self.rack)
        self.assertEqual(build_view(self.client, self.state, [], entity_id=direct)['selection']['kind'], 'exact')
        self.assertEqual(build_view(self.client, self.state, [], entity_id=self.tool)['selection']['kind'], 'containing')

    def test_contents_follow_selected_native_location(self):
        shelf_tool = self.client.add('Shelf tool', parent=self.shelf)
        direct = build_view(self.client, self.state, [], entity_id=self.shelf)
        self.assertEqual(direct['selection']['destination_id'], self.rack)
        self.assertEqual({item['id'] for item in direct['contents']}, {self.box, shelf_tool})
        nested = build_view(self.client, self.state, [], entity_id=self.shelf, include_nested=True)
        self.assertEqual({item['id'] for item in nested['contents']}, {self.box, self.tool, shelf_tool})
        unmapped = self.client.add('Unmapped shelf', location=True, parent=self.rack)
        loose = self.client.add('Loose tool', parent=unmapped)
        view = build_view(self.client, {'revision': 0, 'layout': None}, [], entity_id=unmapped)
        self.assertEqual(view['selection']['kind'], 'unmapped')
        self.assertEqual([item['id'] for item in view['contents']], [loose])

    def test_scope_counts_and_private_custody(self):
        scope = self.client.add('Status shelf', location=True, parent=self.rack)
        ready = lambda: [{'name': 'Equipment condition', 'type': 'text', 'textValue': 'Ready'}]
        items = [
            self.client.add('Ready available', parent=scope, quantity=1, fields=ready()),
            self.client.add('Ready held', parent=scope, fields=ready()+[{'name': 'Loan to Private Borrower', 'type': 'text', 'textValue': 'Private Borrower'}]),
            self.client.add('Broken held', parent=scope, fields=[{'name': 'Equipment condition', 'type': 'text', 'textValue': 'Broken'}]),
            self.client.add('Blocked quantity', parent=scope, quantity=2, fields=ready()),
            self.client.add('Unreviewed', parent=scope),
            self.client.add('Archived', parent=scope, archived=True, fields=ready()),
        ]
        borrower_uuid = uid()
        custody = [{'entity_id': items[1], 'actor_id': borrower_uuid},
                   {'entity_id': items[2], 'actor_id': uid()}]
        v = build_view(self.client, self.state, custody, entity_id=scope, include_nested=True)
        self.assertEqual(v['counts'], {'assigned': 5, 'checked_out': 2, 'available': 1, 'needs_attention': 2})
        self.assertEqual(len({e['id'] for e in v['contents']}), 5)
        self.assertNotIn('Private Borrower', json.dumps(v))
        self.assertEqual(self.client.nodes[items[1]]['fields'][-1]['name'], 'Loan to Private Borrower')
        self.assertEqual(self.client.nodes[items[1]]['fields'][-1]['textValue'], 'Private Borrower')
        self.assertTrue(v['include_nested'])
        visible = build_view(self.client, self.state, custody, entity_id=scope, include_nested=True, can_view_loans=True)
        held = next(item for item in visible['contents'] if item['id'] == items[1])
        self.assertEqual(held['borrower_id'], borrower_uuid)
        self.assertIn('Loan to Private Borrower', json.dumps(visible))

    def test_direct_scope_includes_box_without_descendants(self):
        v = build_view(self.client, self.state, [], entity_id=self.shelf)
        self.assertEqual({e['id'] for e in v['contents']}, {self.box})
        nested = build_view(self.client, self.state, [], entity_id=self.shelf, include_nested=True)
        self.assertEqual({e['id'] for e in nested['contents']}, {self.box, self.tool})

    def test_selected_boxed_equipment_status_is_private_and_does_not_expand_scope(self):
        self.client.nodes[self.tool]['fields'] = [
            {'name': 'Equipment condition', 'type': 'text', 'textValue': 'Broken'}]
        actor_id = uid()
        result = build_view(self.client, self.state,
                            [{'entity_id': self.tool, 'actor_id': actor_id}],
                            entity_id=self.tool)

        self.assertEqual(result['selection']['target_id'], self.tool)
        self.assertNotIn(self.tool, {row['id'] for row in result['contents']},
                         'A directly scoped box remains the contents row; selecting its descendant does not widen scope.')
        self.assertEqual(result['counts']['assigned'], 1)
        self.assertEqual(result['selection_status'], {
            'condition': 'Broken', 'checked_out': True, 'blocker': 'Condition: Broken'})
        self.assertNotIn(actor_id, json.dumps(result))
        self.assertNotIn('borrower_id', result['selection_status'])
        self.assertEqual(self.client.writes, [])

    def test_invalid_order_keeps_other_children_reachable(self):
        shelf_bottom = self.client.add('Shelf bottom', location=True, parent=self.rack, fields=[{'name': 'Storage kind', 'type': 'text', 'textValue': 'Shelf'}])
        shelf_top = self.client.add('Shelf top', location=True, parent=self.rack, fields=[{'name': 'Storage kind', 'type': 'text', 'textValue': 'Shelf'}])
        shelf_new = self.client.add('Shelf new', location=True, parent=self.rack, fields=[{'name': 'Storage kind', 'type': 'text', 'textValue': 'Shelf'}])
        self.client.nodes[self.rack]['fields'] = [{'name': 'Storage kind', 'type': 'text', 'textValue': 'Rack'},
            {'name': 'Workshop shelf order', 'type': 'text', 'textValue': json.dumps({'version': 1, 'shelf_ids': [shelf_top, shelf_bottom, shelf_top, uid(), 'bad']})}]
        non_shelf = self.client.add('Box child', parent=self.rack)
        self.client.summaries[-1]['parent'] = {'id': self.rack}
        v = build_view(self.client, self.state, [], entity_id=self.rack)
        self.assertEqual([row['id'] for row in v['rack']['shelves']], [shelf_top, shelf_bottom])
        self.assertEqual([row['id'] for row in v['rack']['unordered']], [shelf_new])
        self.assertIn(non_shelf, {row['id'] for row in v['rack']['other_children']})
        self.assertTrue(v['rack']['errors'])
        self.client.nodes[self.rack]['fields'][-1] = {'name': 'Workshop shelf order', 'type': 'number', 'value': 1}
        wrong_type = build_view(self.client, self.state, [], entity_id=self.rack)
        self.assertTrue(wrong_type['rack']['errors'])
        self.assertIn(non_shelf, {row['id'] for row in wrong_type['rack']['other_children']})

    def test_numeric_order_and_photos(self):
        shelves = []
        for name, code in [('Ten', '10'), ('Two', '2'), ('Tie B', '2'), ('Tie A', '2'), ('Named level', ''), ('Words', 'abc')]:
            shelves.append(self.client.add(name, location=True, parent=self.rack, fields=[
                {'name': 'Storage kind', 'type': 'text', 'textValue': 'Shelf'}, {'name': 'Storage code', 'type': 'text', 'textValue': code}]))
        tie_a, tie_b = shelves[3], shelves[2]
        self.client.nodes[self.rack]['fields'] = [{'name': 'Storage kind', 'type': 'text', 'textValue': 'Rack'}]
        self.client.nodes[self.rack]['attachments'] = [
            {'id': 'doc-1', 'title': 'Safety manual', 'type': 'document', 'primary': True, 'url': '/private/document'},
            {'id': 'photo-2', 'title': 'Second', 'type': 'photo', 'primary': False, 'url': '/private/photo'},
            {'id': 'photo-1', 'title': 'Main', 'type': 'photo', 'primary': True, 'url': '/private/photo'},
        ]
        v = build_view(self.client, self.state, [], entity_id=self.rack)
        ordered = [row['id'] for row in v['rack']['shelves']]
        self.assertEqual(ordered, [tie_a, tie_b, shelves[1], shelves[0]])
        self.assertEqual({row['id'] for row in v['rack']['unordered']}, {shelves[4], shelves[5]})
        self.assertEqual([p['id'] for p in v['photos']], ['photo-1', 'photo-2'])
        self.assertNotIn('doc-1', {p['id'] for p in v['photos']})
        self.assertEqual(set(v['photos'][0]), {'id', 'title', 'primary', 'alt'})
        self.assertNotIn('/private/photo', json.dumps(v))

    def test_unavailable_and_cycles_preserve_layout(self):
        original = copy.deepcopy(self.state)
        self.client.nodes[self.box]['parent'] = {'id': self.tool}
        v = build_view(self.client, self.state, [], entity_id=self.tool)
        self.assertTrue(v['errors'])
        self.assertEqual(self.state, original)
        with self.assertRaises(ValueError):
            scoped_equipment(self.client, uid())
        archived = self.client.add('Retired', location=True, archived=True)
        with self.assertRaises(ValueError):
            scoped_equipment(self.client, archived)
        with self.assertRaises(ValueError):
            scoped_equipment(self.client, self.rack)
        self.client.nodes[self.box]['parent'] = {'id': self.tool}
        with self.assertRaises(ValueError):
            scoped_equipment(self.client, self.rack, include_nested=True)

    def test_coverage_separates_indirect_and_legacy(self):
        bin_id = self.client.add('Bin', location=True, parent=self.shelf)
        drawing_only = uid()
        foreign = uid()
        archived = self.client.add('Archived Rack', location=True, archived=True)
        self.state['layout']['objects'].extend([
            {'id': drawing_only, 'name': 'Unlinked', 'kind': 'Rack', 'x': 0, 'y': 2, 'width': 1, 'height': 1, 'rotation': 0, 'location_id': None},
            {'id': uid(), 'name': 'Foreign link', 'kind': 'Rack', 'x': 2, 'y': 2, 'width': 1, 'height': 1, 'rotation': 0, 'location_id': foreign},
            {'id': uid(), 'name': 'Archived link', 'kind': 'Rack', 'x': 4, 'y': 2, 'width': 1, 'height': 1, 'rotation': 0, 'location_id': archived},
        ])
        self.client.nodes[self.shelf]['fields'] = [
            {'name': 'Workshop map room', 'type': 'text', 'textValue': '{"version":1,"width":2,"height":2}'},
            {'name': 'Workshop map object', 'type': 'text', 'textValue': '{"version":1,"room_id":"'+uid()+'"}'},
        ]
        v = build_view(self.client, self.state, [])
        bin_row = next(r for r in v['coverage'] if r['location_id'] == bin_id)
        self.assertEqual(bin_row['covered_by'], self.rack)
        self.assertEqual(bin_row['kind'], 'multiple')
        self.assertTrue(any(r['kind'] == 'drawing_only' and r['drawing_id'] == drawing_only for r in v['coverage']))
        self.assertTrue(any(r['kind'] == 'legacy_review' and r['location_id'] == self.shelf for r in v['coverage']))
        self.assertTrue(any(r['kind'] == 'unavailable' and r['drawing_id'] for r in v['coverage']))
        self.assertEqual(self.client.writes, [])

    def test_query_ambiguity_and_unknown_codes(self):
        one = self.client.entity(self.tool)
        two = copy.deepcopy(one); two['id'] = uid()
        two['parent'] = {'id': self.cage}
        self.client.nodes[two['id']] = two
        self.client.summaries.append(two)
        result = resolve_workshop_code(self.client, 'SERIAL-1234')
        self.assertIsNone(result['entity_id'])
        self.assertEqual({c['id'] for c in result['candidates']}, {self.tool, two['id']})
        self.assertTrue(all(c['path'] for c in result['candidates']))
        for code in ('LAB:U:badge', 'https://foreign.invalid/item/'+self.tool, 'unknown-code'):
            self.assertIsNone(resolve_workshop_code(self.client, code)['entity_id'])

    def test_native_and_foreign_url_origins(self):
        for code in ('https://native.example/item/'+self.tool, 'https://native.example/a/000-123',
                     '/item/'+self.tool, '/a/000-123', self.tool, '000-123'):
            self.assertEqual(resolve_workshop_code(self.client, code)['entity_id'], self.tool)
        self.client.workshop_code_origins = ('https://alt-native.example',)
        self.assertEqual(resolve_workshop_code(self.client, 'https://alt-native.example/item/'+self.tool)['entity_id'], self.tool)
        self.client.nodes[self.tool]['fields'] = [
            {'name': 'Manufacturer QR code', 'type': 'text', 'textValue': 'https://foreign.invalid/item/'+self.tool},
            {'name': 'Manufacturer QR code', 'type': 'text', 'textValue': 'https://foreign.invalid/a/000-123'},
        ]
        for code in ('https://foreign.invalid/item/'+self.tool, 'https://foreign.invalid/a/000-123'):
            self.assertIsNone(resolve_workshop_code(self.client, code)['entity_id'])

    def test_authority_references_and_explicit_zero_port_are_rejected(self):
        for code in ('//foreign.invalid/item/'+self.tool, '//foreign.invalid/a/000-123',
                     'https://native.example:0/item/'+self.tool,
                     'https://native.example:0/a/000-123'):
            result = resolve_workshop_code(self.client, code)
            self.assertIsNone(result['entity_id'], code)

    def test_registered_opaque_manufacturer_codes_still_resolve(self):
        opaque = '{"part":"battery","batch":42}'
        one = self.client.add('Opaque match', fields=[{'name': 'Manufacturer QR code', 'type': 'text', 'textValue': opaque}])
        result = resolve_workshop_code(self.client, opaque)
        self.assertEqual(result['entity_id'], one)

        second = self.client.add('Second opaque match', fields=[{'name': 'Manufacturer QR code', 'type': 'text', 'textValue': opaque}])
        result = resolve_workshop_code(self.client, opaque)
        self.assertIsNone(result['entity_id'])
        self.assertEqual({candidate['id'] for candidate in result['candidates']}, {one, second})

        short = self.client.add('Single character match', fields=[{'name': 'Manufacturer QR code', 'type': 'text', 'textValue': 'a'}])
        self.assertEqual(resolve_workshop_code(self.client, 'a')['entity_id'], short)

    def test_badge_metadata_never_resolves(self):
        self.client.nodes[self.tool]['fields'] = [{'name': 'Manufacturer QR code', 'type': 'text', 'textValue': 'LAB:U:badge'}]
        result = resolve_workshop_code(self.client, 'LAB:U:badge')
        self.assertIsNone(result['entity_id'])
        self.assertEqual(result['candidates'], [])

    def test_ambiguous_manufacturer_candidates_ignore_scan_whitespace(self):
        raw = 'https://maker.example/code'
        ids = {self.client.add('Maker one', fields=[{'name': 'Manufacturer QR code', 'type': 'text', 'textValue': raw}]),
               self.client.add('Maker two', fields=[{'name': 'Manufacturer QR code', 'type': 'text', 'textValue': raw}])}
        result = resolve_workshop_code(self.client, '  '+raw+'  ')
        self.assertIsNone(result['entity_id'])
        self.assertEqual({item['id'] for item in result['candidates']}, ids)
        self.assertTrue(all(item['path'] for item in result['candidates']))

    def test_native_read_failures_are_safe_diagnostics(self):
        class ListingFailure(Client):
            def entities(self, locations=False):
                raise RuntimeError('secret /private/homebox/path')
        listed = ListingFailure()
        view = build_view(listed, self.state, [])
        self.assertTrue(view['errors'])
        self.assertNotIn('/private/homebox/path', str(view['errors']))
        self.assertTrue(any(error['code'] == 'native_read_unavailable' for error in view['errors']))

        class AncestorFailure(Client):
            def entity(self, key):
                self.entity_reads += 1
                if key == self.cage_id:
                    raise RuntimeError('secret /private/homebox/path')
                return super().entity(key)
        broken = AncestorFailure()
        broken.nodes, broken.summaries = copy.deepcopy(self.client.nodes), copy.deepcopy(self.client.summaries)
        broken.cage_id = self.cage
        view = build_view(broken, self.state, [], entity_id=self.tool)
        self.assertEqual(view['selection']['kind'], 'unavailable')
        self.assertTrue(any(error['code'] == 'native_read_unavailable' for error in view['errors']))
        self.assertNotIn('/private/homebox/path', str(view['errors']))

    def test_long_path_and_native_uuid_resolution(self):
        parent = self.cage
        ids = []
        for i in range(70):
            parent = self.client.add('Level '+str(i), location=bool(i % 2), parent=parent)
            ids.append(parent)
        before = self.client.entity_reads
        view = build_view(self.client, self.state, [], entity_id=ids[-1], include_nested=True)
        self.assertEqual(len(view['path']), 71)
        self.assertLessEqual(self.client.entity_reads - before, len(self.client.nodes))
        result = resolve_workshop_code(self.client, self.tool)
        self.assertEqual(result['entity_id'], self.tool)
        self.assertEqual(result['candidates'][0]['id'], self.tool)


if __name__ == '__main__':
    unittest.main()
