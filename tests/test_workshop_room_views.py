import copy
import json
import pathlib
import sqlite3
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'ops'))
from test_workshop_views import Client, uid
from workshop_views import build_view


class WorkshopRoomViewTests(unittest.TestCase):
    def setUp(self):
        self.client = Client()
        self.cage = self.client.add('The Cage', location=True)
        self.rack = self.client.add('Rack', location=True, parent=self.cage)
        self.shelf = self.client.add('Shelf', location=True, parent=self.rack)
        self.box = self.client.add('Box', parent=self.shelf)
        self.tool = self.client.add('Drill', parent=self.box, fields=[
            {'name': 'Equipment condition', 'type': 'text', 'textValue': 'Ready'},
            {'name': 'Loan to Borrower Secret', 'type': 'text', 'textValue': 'Borrower Secret'}])
        self.overview, self.inset, self.third, self.farther = uid(), uid(), uid(), uid()
        self.overview_drawing, self.inset_drawing, self.third_drawing, self.farther_drawing = (uid() for _ in range(4))
        self.state = {'revision': 4, 'schema_version': 2, 'document': {'version': 2, 'rooms': [
            self.room(self.overview, 'Overview', self.cage, self.overview_drawing, self.rack),
            self.room(self.inset, 'Rack inset', self.rack, self.inset_drawing, self.rack),
            self.room(self.third, 'Second rack view', self.cage, self.third_drawing, self.rack),
            self.room(self.farther, 'Cage overview', self.cage, self.farther_drawing, self.cage),
        ]}}

    @staticmethod
    def room(room_id, name, root, drawing_id, location):
        return {'id': room_id, 'name': name, 'location_id': root, 'width': 10, 'height': 8,
                'unit': 'ft', 'approximate': False, 'objects': [
                    {'id': drawing_id, 'name': name + ' drawing', 'kind': 'Rack', 'x': 0, 'y': 0,
                     'width': 2, 'height': 1, 'rotation': 0, 'location_id': location}]}

    def test_ambiguous_and_dangling_room_selection(self):
        before = copy.deepcopy(self.state)
        item = build_view(self.client, self.state, [], entity_id=self.tool)
        self.assertEqual(item['selection']['destination_id'], self.rack)
        self.assertEqual({m['room_id'] for m in item['selection']['matches']},
                         {self.overview, self.inset, self.third})
        farther_filter = build_view(self.client, self.state, [], entity_id=self.tool, room_id=self.farther)
        self.assertEqual(farther_filter['selection']['destination_id'], self.rack)
        self.assertEqual(farther_filter['selection']['matches'], [])
        chosen = build_view(self.client, self.state, [], entity_id=self.tool, room_id=self.overview)
        self.assertEqual(chosen['selection']['destination_id'], self.rack)
        self.assertEqual({m['room_id'] for m in chosen['selection']['matches']}, {self.overview})
        dangling = build_view(self.client, self.state, [], entity_id=self.tool, room_id=uid())
        self.assertEqual(dangling['selection']['kind'], 'unavailable')
        self.assertEqual(self.state, before)
        self.assertEqual(self.client.writes, [])
        self.assertNotIn('Borrower Secret', json.dumps(item))

    def test_moved_link_is_excluded_from_placement(self):
        self.state['document']['rooms'] = [self.room(self.overview, 'Overview', self.cage,
                                                       self.overview_drawing, self.shelf)]
        before = copy.deepcopy(self.state)
        self.client.nodes[self.shelf]['parent'] = None
        result = build_view(self.client, self.state, [], entity_id=self.tool)
        self.assertIn(self.shelf, [row['id'] for row in result['path']])
        self.assertIsNone(result['selection']['destination_id'])
        self.assertTrue(any(row.get('room_id') == self.overview and row['kind'] == 'unavailable'
                            for row in result['coverage']))
        self.assertTrue(result['errors'])
        self.assertEqual(self.state, before)
        self.assertEqual(self.client.writes, [])

    def test_room_reads_preserve_stage_one_scope_and_privacy(self):
        state = {'version': 2, 'rooms': [self.room(self.overview, 'Overview', self.cage,
                                                    self.overview_drawing, self.rack)]}
        legacy = {'revision': 4, 'layout': {'objects': []}}
        result = build_view(self.client, state, [{'entity_id': self.tool, 'actor_id': uid()}],
                            entity_id=self.shelf, room_id=self.overview)
        baseline = build_view(self.client, legacy, [], entity_id=self.shelf)
        self.assertEqual(set(result), set(baseline))
        for key in ('path', 'contents', 'counts', 'rack', 'photos', 'include_nested'):
            self.assertEqual(type(result[key]), type(baseline[key]))
        self.assertEqual({row['id'] for row in result['contents']}, {self.box})
        self.assertEqual(result['counts']['assigned'], 1)
        self.assertNotIn('Borrower Secret', json.dumps(result))
        self.assertEqual(self.client.writes, [])

    def test_desktop_and_terminal_view_room_parameters_match(self):
        from desktop_api import get_action
        from test_workshop_routes import WorkshopRouteTests
        route = WorkshopRouteTests()
        route.setUp()
        self.addCleanup(route.tearDown)
        room_id, drawing_id = uid(), uid()
        document = {'version': 2, 'rooms': [
            {'id': room_id, 'location_id': route.rack, 'name': 'Rack plan', 'width': 10,
             'height': 8, 'unit': 'ft', 'approximate': False,
             'objects': [{'id': drawing_id, 'name': 'Shelf', 'kind': 'Rack', 'x': 0, 'y': 0,
                          'width': 2, 'height': 1, 'rotation': 0, 'location_id': route.shelf}]}]}
        with sqlite3.connect(route.workshop.path) as db:
            db.execute('INSERT INTO plans VALUES(?,?,?)',
                       (route.group, 1, json.dumps(document)))
        terminal_status, terminal = route.request('/workshop/view', 'POST', {
            'entity_id': route.shelf, 'include_nested': False, 'room_id': room_id})
        desktop = get_action('workshop/view', {'id': [route.shelf], 'nested': ['0'], 'room_id': [room_id]},
                             {'client': route.native, 'group': route.group, 'manager': True},
                             {'workshop': route.workshop, 'ledger': route.ledger})
        self.assertEqual(terminal_status, 200)
        self.assertEqual(terminal['selection'], desktop['selection'])
        self.assertEqual(terminal['selection']['matches'][0]['room_id'], room_id)
        self.assertEqual(route.put_count, 0)


if __name__ == '__main__':
    unittest.main()
