import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from ledger import Conflict, Ledger
from item_metadata import ItemMetadata


def ident(): return str(uuid4())


class ItemMetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.ledger = Ledger(Path(self.tmp.name) / 'ledger.db')
        self.store = ItemMetadata(self.ledger); self.group, self.other = ident(), ident()
        self.actor, self.a, self.b = ident(), ident(), ident()
    def tearDown(self): self.tmp.cleanup()
    def test_notes_save_read_replay_and_normalized_uniqueness(self):
        key = ident(); fields = [{'name':' Serial Number ', 'note':'Sticker on base'}]
        self.store.save_field_notes(self.group, self.actor, self.a, fields, key)
        self.assertEqual({'serial number':'Sticker on base'}, self.store.field_notes(self.group, self.a))
        self.store.save_field_notes(self.group, self.actor, self.a, fields, key)
        with self.assertRaises(ValueError): self.store.save_field_notes(self.group,self.actor,self.a,[{'name':'x','note':'1'},{'name':' X ','note':'2'}],ident())
        with self.assertRaises(ValueError): self.store.save_field_notes(self.group,self.actor,self.a,[{'name':'x','note':''},{'name':' X ','note':'2'}],ident())
    def test_relations_are_symmetric_idempotent_and_removable(self):
        key=ident(); self.store.add_related(self.group,self.actor,self.a,self.b,key)
        self.store.add_related(self.group,self.actor,self.b,self.a,key)
        self.assertEqual([self.b],self.store.related_items(self.group,self.a))
        self.assertEqual([self.a],self.store.related_items(self.group,self.b))
        self.store.remove_related(self.group,self.actor,self.b,self.a,ident())
        self.assertEqual([],self.store.related_items(self.group,self.a))
    def test_collection_isolation_and_request_replay_conflict(self):
        key=ident(); self.store.add_related(self.group,self.actor,self.a,self.b,key)
        self.assertEqual([],self.store.related_items(self.other,self.a))
        with self.assertRaises(Conflict): self.store.remove_related(self.group,self.actor,self.a,self.b,key)


if __name__ == '__main__': unittest.main()
