import copy
import math
import pathlib
import sqlite3
import json
import sys
import unittest
from uuid import UUID, uuid4, uuid5

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'ops'))
from workshop import Workshop, normalize_document, room_document
from workshop_room_fixtures import RoomFixture


class WorkshopRoomTests(unittest.TestCase):
    def setUp(self):
        self.fixture = RoomFixture()
        self.addCleanup(self.fixture.close)

    def test_legacy_reads_are_stable_and_write_free(self):
        f = self.fixture
        f.seed_legacy()
        before = f.stored_row()
        a = f.store.get(f.group)
        b = Workshop(f.store.path).get(f.group)
        self.assertEqual(a, b)
        self.assertEqual(f.stored_row(), before)
        room = a['document']['rooms'][0]
        self.assertEqual(room['id'], str(uuid5(UUID(f.group), 'workshop:legacy-room')))
        self.assertIsNone(room['location_id'])
        self.assertEqual({k: room[k] for k in f.legacy}, f.legacy)
        self.assertEqual(f.store.get(str(uuid4()))['document']['rooms'], [])
        self.assertEqual(f.client.writes, [])

    def test_document_limits_and_cross_room_ids(self):
        f = self.fixture
        self.assertEqual(len(room_document(f.document)['rooms']), 1)
        max_document = {'version': 2, 'rooms': [
            {**f.document['rooms'][0], 'id': str(uuid4()),
             'objects': [{'id': str(uuid4()), 'kind': 'Area', 'name': 'Area',
                          'x': 0, 'y': 0, 'width': 200, 'height': 200,
                          'rotation': 0, 'location_id': None} for _ in range(200)]}
        ]}
        # At the exact limits, independent objects with unique identities are accepted.
        max_document['rooms'][0].update(width=200, height=200)
        self.assertEqual(len(room_document(max_document)['rooms'][0]['objects']), 200)
        too_many_rooms = {'version': 2, 'rooms': [
            {**f.document['rooms'][0], 'id': str(uuid4())} for _ in range(21)]}
        with self.assertRaises(ValueError): room_document(too_many_rooms)
        too_many_objects = copy.deepcopy(f.document)
        too_many_objects['rooms'][0]['objects'] = max_document['rooms'][0]['objects'] + [
            {**max_document['rooms'][0]['objects'][0], 'id': str(uuid4())}]
        with self.assertRaises(ValueError): room_document(too_many_objects)
        duplicate_rooms = {'version': 2, 'rooms': [f.document['rooms'][0],
                         {**f.document['rooms'][0], 'name': 'Second'}]}
        with self.assertRaises(ValueError): room_document(duplicate_rooms)
        duplicate_objects = copy.deepcopy(f.document)
        duplicate_objects['rooms'] = [
            {**f.document['rooms'][0], 'objects': [max_document['rooms'][0]['objects'][0]]},
            {**f.document['rooms'][0], 'id': str(uuid4()), 'name': 'Second',
             'objects': [max_document['rooms'][0]['objects'][0]]},
        ]
        with self.assertRaises(ValueError): room_document(duplicate_objects)
        for bad in ({'kind': 'Unknown', 'name': 'Bad'},
                    {'kind': 'Rack', 'name': 'Bad', 'x': math.nan}):
            invalid = copy.deepcopy(f.document)
            invalid['rooms'][0]['objects'] = [{**max_document['rooms'][0]['objects'][0], **bad}]
            with self.assertRaises(ValueError): room_document(invalid)
        for rotation in (45, -90):
            invalid = copy.deepcopy(f.document)
            invalid['rooms'][0]['objects'] = [{**max_document['rooms'][0]['objects'][0], 'rotation': rotation}]
            with self.assertRaises(ValueError): room_document(invalid)
        invalid = copy.deepcopy(f.document)
        invalid['rooms'][0]['objects'] = [{**max_document['rooms'][0]['objects'][0], 'x': 10}]
        with self.assertRaises(ValueError): room_document(invalid)
        # Valid UUID syntax from another namespace is syntactically valid; group scoping owns it.
        foreign_looking = copy.deepcopy(f.document)
        foreign_looking['rooms'][0]['location_id'] = str(uuid4())
        self.assertEqual(room_document(foreign_looking)['rooms'][0]['location_id'],
                         foreign_looking['rooms'][0]['location_id'])

    def test_v2_rejects_falsy_non_null_location_links(self):
        for invalid_id in (False, 0, ''):
            with self.subTest(field='room root', value=invalid_id):
                invalid = copy.deepcopy(self.fixture.document)
                invalid['rooms'][0]['location_id'] = invalid_id
                with self.assertRaises(ValueError): room_document(invalid)
            with self.subTest(field='drawing link', value=invalid_id):
                invalid = copy.deepcopy(self.fixture.document)
                invalid['rooms'][0]['objects'] = [{
                    'id': str(uuid4()), 'kind': 'Rack', 'name': 'Rack',
                    'x': 0, 'y': 0, 'width': 1, 'height': 1,
                    'rotation': 0, 'location_id': invalid_id,
                }]
                with self.assertRaises(ValueError): room_document(invalid)

    def test_exact_room_limit_allows_duplicate_names(self):
        document = {'version': 2, 'rooms': [
            {**self.fixture.document['rooms'][0], 'id': str(uuid4()), 'name': 'Overview', 'objects': []}
            for _ in range(20)
        ]}
        self.assertEqual(len(room_document(document)['rooms']), 20)

    def test_v2_save_validation_preserves_valid_precision_and_caption(self):
        room=copy.deepcopy(self.fixture.document['rooms'][0])
        room.update(width=4.0004,height=4.25,name='  Precision room  ')
        room['objects']=[{'id':str(uuid4()),'kind':'Rack','name':' Rack  A ','x':0.0005,'y':0,
                          'width':3.9996,'height':1,'rotation':0,'location_id':None}]
        document={'version':2,'rooms':[room]}
        saved=room_document(document)
        self.assertEqual(saved['rooms'][0]['width'],4.0004)
        self.assertEqual(saved['rooms'][0]['name'],'  Precision room  ')
        self.assertEqual(saved['rooms'][0]['objects'][0]['x'],0.0005)
        self.assertEqual(saved['rooms'][0]['objects'][0]['width'],3.9996)
        self.assertEqual(saved['rooms'][0]['objects'][0]['name'],' Rack  A ')

    def test_v2_save_preserves_custom_drawing_kind_and_appearance(self):
        room=copy.deepcopy(self.fixture.document['rooms'][0])
        room['objects']=[{'id':str(uuid4()),'kind':'Wall','name':'North wall','x':0,'y':0,
                          'width':3,'height':.2,'rotation':0,'location_id':None,
                          'color':'#336699','opacity':.65,'layer':'below'}]
        saved=room_document({'version':2,'rooms':[room]})
        self.assertEqual(saved['rooms'][0]['objects'][0]['kind'],'Wall')
        self.assertEqual(saved['rooms'][0]['objects'][0]['color'],'#336699')
        self.assertEqual(saved['rooms'][0]['objects'][0]['opacity'],.65)
        self.assertEqual(saved['rooms'][0]['objects'][0]['layer'],'below')

    def test_v2_save_preserves_optional_drawing_show_name_flag(self):
        room=copy.deepcopy(self.fixture.document['rooms'][0])
        drawing={'id':str(uuid4()),'kind':'Wall','name':'North wall','x':0,'y':0,
                 'width':3,'height':.2,'rotation':0,'location_id':None}
        room['objects']=[drawing]
        saved=room_document({'version':2,'rooms':[room]})
        self.assertNotIn('show_name',saved['rooms'][0]['objects'][0])
        drawing['show_name']=False
        saved=room_document({'version':2,'rooms':[room]})
        self.assertIs(saved['rooms'][0]['objects'][0]['show_name'],False)
        request=self.fixture.request({'version':2,'rooms':[room]})
        self.fixture.store.save(self.fixture.client,self.fixture.group,request,actor_id=self.fixture.actor)
        self.assertIs(self.fixture.store.get(self.fixture.group)['document']['rooms'][0]['objects'][0]['show_name'],False)
        drawing['show_name']=True
        saved=room_document({'version':2,'rooms':[room]})
        self.assertIs(saved['rooms'][0]['objects'][0]['show_name'],True)
        for value in (None,0,1,'false'):
            drawing['show_name']=value
            with self.subTest(value=value),self.assertRaises(ValueError):
                room_document({'version':2,'rooms':[room]})

    def test_missing_and_versioned_documents(self):
        f = self.fixture
        result = f.store.get(f.group)
        self.assertEqual((result['revision'], result['schema_version'], result['stored_schema_version']), (0, 2, 1))
        self.assertEqual(result['document'], {'version': 2, 'rooms': []})
        saved = copy.deepcopy(f.document)
        db = sqlite3.connect(f.path)
        try:
            db.execute('INSERT INTO plans VALUES(?,?,?)', (f.group, 1, json.dumps(saved)))
            db.commit()
        finally:
            db.close()
        got = f.store.get(f.group)
        self.assertEqual(got['stored_schema_version'], 2)
        self.assertEqual(got['document'], saved)
        self.assertIsNone(got['layout'])

    def test_supported_versions_and_room_ids_are_required(self):
        invalid = copy.deepcopy(self.fixture.document)
        invalid['version'] = 3
        with self.assertRaises(ValueError): normalize_document(self.fixture.group, invalid)
        invalid = copy.deepcopy(self.fixture.document)
        invalid['rooms'][0]['id'] = 'not-a-uuid'
        with self.assertRaises(ValueError): room_document(invalid)


if __name__ == '__main__':
    unittest.main()
