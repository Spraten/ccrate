"""Temporary fixtures for versioned Workshop room documents."""
import json
import pathlib
import sqlite3
import tempfile
from uuid import uuid4

from workshop import Workshop


class RoomClient:
    def __init__(self, root, shelf):
        kind = str(uuid4())
        self.nodes = {
            root: {'id': root, 'name': 'Storage Room', 'archived': False, 'entityType': {'isLocation': True}, 'parent': None,
                   'fields': [{'name':'Storage kind','type':'text','textValue':'Room'}], 'attachments':[{'id':str(uuid4()),'type':'photo'}], 'history':['unchanged']},
            shelf: {'id': shelf, 'name': 'Shelf', 'archived': False, 'entityType': {'isLocation': True}, 'parent': {'id': root},
                    'fields': [{'name':'Storage kind','type':'text','textValue':'Shelf'}], 'attachments':[], 'history':['unchanged']},
        }
        self.writes = []

    def entities(self, locations=False):
        return [node for node in self.nodes.values() if node['entityType']['isLocation'] is locations]

    def entity(self, key):
        return self.nodes[key]


class RoomFixture:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.tmp.name) / 'workshop.db'
        self.store = Workshop(self.path)
        self.group, self.actor = str(uuid4()), str(uuid4())
        self.root, self.shelf, self.room, self.drawing, self.compatible_root = (str(uuid4()) for _ in range(5))
        self.client = RoomClient(self.root, self.shelf)
        self.client.nodes[self.compatible_root] = {'id': self.compatible_root, 'name': 'Compatible room', 'archived': False,
            'entityType': {'isLocation': True}, 'parent': None, 'fields': [], 'attachments': [], 'history': []}
        self.legacy = {
            'name': 'High precision room', 'width': 13.123456789, 'height': 21.987654321,
            'unit': 'ft', 'approximate': True,
            'objects': [{'id': self.drawing, 'kind': 'Rack', 'name': ' Rack  A ',
                         'x': 1.123456789, 'y': 2.987654321, 'width': 3.123456789,
                         'height': 4.123456789, 'rotation': 90, 'location_id': self.shelf}],
        }
        self.document = {
            'version': 2,
            'rooms': [{'id': self.room, 'location_id': self.root, 'name': 'Plan',
                       'width': 12, 'height': 16, 'unit': 'ft', 'approximate': False,
                       'objects': []}],
        }

    def seed_legacy(self):
        db = sqlite3.connect(self.path)
        try:
            db.execute('INSERT OR REPLACE INTO plans VALUES(?,?,?)',
                       (self.group, 7, json.dumps(self.legacy)))
            db.commit()
        finally:
            db.close()

    def stored_row(self):
        db = sqlite3.connect(self.path)
        try:
            return db.execute('SELECT revision,document FROM plans WHERE group_id=?',
                              (self.group,)).fetchone()
        finally:
            db.close()

    def request(self, document=None, revision=0):
        return {'schema_version': 2, 'revision': revision,
                'request_key': str(uuid4()), 'document': self.document if document is None else document}

    def move_shelf_outside_root(self):
        self.client.nodes[self.shelf]['parent'] = None

    def repair_request(self):
        document = json.loads(json.dumps(self.document))
        document['rooms'][0]['location_id'] = self.compatible_root
        document['rooms'][0]['objects'] = [{'id': self.drawing, 'kind': 'Rack', 'name': 'Rack', 'x': 0, 'y': 0,
            'width': 1, 'height': 1, 'rotation': 0, 'location_id': self.shelf}]
        return self.request(document, self.store.get(self.group)['revision'])

    def close(self):
        self.tmp.cleanup()
