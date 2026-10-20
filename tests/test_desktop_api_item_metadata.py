"""Authenticated metadata route fixtures using an isolated native client."""
import tempfile, pathlib, threading, unittest
from uuid import uuid4
import desktop_api as api
from ledger import Ledger
from native_jobs import NativeJobs
from badges import Badges
from test_desktop_api_equipment_catalog import EquipmentCatalogApiTests, ident


class ItemMetadataApiTests(unittest.TestCase):
    def setUp(self): EquipmentCatalogApiTests.setUp(self)
    def tearDown(self): EquipmentCatalogApiTests.tearDown(self)
    request = EquipmentCatalogApiTests.request
    native_factory = EquipmentCatalogApiTests.native_factory

    def test_member_notes_and_related_links_and_symmetric_removal(self):
        context = self.request('context', headers={'Cookie':'hb.auth.token=member; hb.auth.remember=true'}).result
        headers={'Cookie':'hb.auth.token=member; hb.auth.remember=true','X-Workshop-Identity':context['identity']}
        key=ident()
        saved=self.request('item-metadata/field-notes', {'request_key':key,'entity_id':self.item,'fields':[{'name':'Serial Number','note':'Base label'}]}, headers=headers)
        self.assertEqual(200,saved.status)
        self.assertEqual({'serial number':'Base label'},saved.result['fieldNotes'])
        self.assertEqual(saved.result,self.request('item-metadata/field-notes', {'request_key':key,'entity_id':self.item,'fields':[{'name':'Serial Number','note':'Base label'}]}, headers=headers).result)
        added=self.request('item-metadata/related/add', {'request_key':ident(),'entity_id':self.item,'related_entity_id':self.item}, headers=headers)
        self.assertEqual(400,added.status)
        second=ident(); self.entities[second]={'id':second,'name':'Camera','entityType':{'isLocation':False}}
        added=self.request('item-metadata/related/add', {'request_key':ident(),'entity_id':self.item,'related_entity_id':second}, headers=headers)
        self.assertEqual(200,added.status)
        view=self.request('item-metadata?entity_id='+second, headers=headers)
        self.assertEqual(self.item,view.result['relatedItems'][0]['id'])
        removed=self.request('item-metadata/related/remove', {'request_key':ident(),'entity_id':second,'related_entity_id':self.item}, headers=headers)
        self.assertEqual(200,removed.status)
        self.assertEqual([],self.request('item-metadata?entity_id='+self.item).result['relatedItems'])

    def test_inaccessible_and_location_rejected_before_mutation(self):
        for entity in (self.location, ident()):
            response=self.request('item-metadata/field-notes', {'request_key':ident(),'entity_id':entity,'fields':[]})
            self.assertEqual(400,response.status)


if __name__ == '__main__': unittest.main()
