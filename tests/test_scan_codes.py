import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'kiosk'))
from scan_codes import normalize, resolve_serial, resolve_equipment, manufacturer_code, MANUFACTURER_FIELD
class ScanTests(unittest.TestCase):
    def test_native_asset_url(self):
        self.assertEqual(normalize('http://homebox.local/a/000-013'),{'kind':'asset','asset_id':'000-013'})
    def test_short_code_normalizes_case_and_whitespace(self):
        self.assertEqual(normalize('  dhp-1000 '), {'kind': 'short_code', 'short_code': 'DHP-1000'})
    def test_untrusted_url_is_only_an_identifier(self):
        self.assertEqual(normalize('https://untrusted.invalid/a/000-013')['asset_id'],'000-013')
    def test_script_is_rejected(self):
        self.assertEqual(normalize('javascript:alert(1)')['kind'],'invalid')
    def test_gtin_checksum(self):
        self.assertEqual(normalize('4006381333931')['kind'],'product')
        self.assertEqual(normalize('4006381333932')['kind'],'invalid')
    def test_excessive_input(self):
        self.assertEqual(normalize('x'*2049)['kind'],'invalid')
    def test_unknown_namespace(self):
        self.assertEqual(normalize('LAB:U:unapproved')['kind'],'invalid')
class ManufacturerSerialTests(unittest.TestCase):
    def test_dji_battery_serial(self):
        self.assertEqual(normalize('093XE5604401ME'),{'kind':'serial','serial':'093XE5604401ME'})
    def test_alphanumeric_serial(self):
        self.assertEqual(normalize('  DJI-SERIAL-123  '),{'kind':'serial','serial':'DJI-SERIAL-123'})
    def test_unsafe_or_unknown_urls_are_not_serials(self):
        self.assertEqual(normalize('https://example.com/serial')['kind'],'manufacturer')
        for raw in ['LAB:U:unapproved','SN\x001234','/unknown/1234']:
            self.assertEqual(normalize(raw)['kind'],'invalid')
    def test_exact_native_match(self):
        item={'id':'one','serialNumber':'DJI-SERIAL-123'}
        self.assertEqual(resolve_serial(normalize('DJI-SERIAL-123'),[item])['entity'],item)
        self.assertNotIn('entity',resolve_serial(normalize('dji-serial-123'),[item]))
    def test_unknown_and_duplicate_serials(self):
        code=normalize('DJI-SERIAL-123')
        self.assertIn('reason',resolve_serial(code,[]))
        items=[{'id':str(i),'serialNumber':code['serial']} for i in range(2)]
        result=resolve_serial(code,items)
        self.assertTrue(result['ambiguous'])
        self.assertNotIn('entity',result)
    def test_locations_cannot_resolve_as_equipment(self):
        code=normalize('DJI-SERIAL-123')
        self.assertNotIn('entity',resolve_serial(code,[{'serialNumber':code['serial'],'entityType':{'isLocation':True}}]))
if __name__=='__main__':unittest.main()


class EquipmentCodeTests(unittest.TestCase):
    def item(self,identifier='one',serial='',code=None,gtin=None,archived=False,shortCode=None):
        fields=[]
        if code is not None:fields.append({'name':MANUFACTURER_FIELD,'type':'text','textValue':code})
        if gtin is not None:fields.append({'name':'Product GTIN','type':'text','textValue':gtin})
        return {'id':identifier,'serialNumber':serial,'shortCode':shortCode,'fields':fields,'archived':archived}
    def resolve(self,raw,items):return resolve_equipment(raw,normalize(raw),items)
    def test_homebox_uuid_and_entity_url(self):
        identifier='efb41b6f-0386-452b-af21-75da992e9677'
        for raw in [identifier,'http://homebox/entity/'+identifier]:self.assertEqual(normalize(raw)['entity_id'],identifier)
    def test_arbitrary_qr_text_is_registered_exactly(self):
        for raw in ['https://vendor.invalid/device/opaque', '{"part":"battery","batch":42}', 'a']:
            self.assertEqual(manufacturer_code(raw),raw)
            self.assertEqual(self.resolve(raw,[self.item(code=raw)])['entity']['id'],'one')
    def test_url_serial_and_registered_override(self):
        raw='https://vendor.invalid/device?serial=SERIAL-42&model=ABC'
        self.assertEqual(self.resolve(raw,[self.item(serial='SERIAL-42')])['entity']['id'],'one')
        self.assertNotIn('entity',self.resolve(raw,[self.item(serial='serial-42')]))
        raw+='&sn=OTHER';self.assertNotIn('entity',self.resolve(raw,[self.item(serial='SERIAL-42')]))
    def test_duplicate_or_archived_codes_never_choose(self):
        raw='https://vendor.invalid/label'
        result=self.resolve(raw,[self.item(code=raw),self.item('two',code=raw)])
        self.assertTrue(result['ambiguous']);self.assertNotIn('entity',result)
        self.assertNotIn('entity',self.resolve(raw,[self.item(code=raw,archived=True)]))
    def test_shared_product_code_needs_individual_label(self):
        raw='4006381333931';items=[self.item(gtin='04006381333931')]
        self.assertIn('entity',self.resolve(raw,items))
        items.append(self.item('two',gtin=raw));self.assertNotIn('entity',self.resolve(raw,items))
    def test_serial_and_linked_code_conflict(self):
        result=self.resolve('SERIAL-42',[self.item(serial='SERIAL-42'),self.item('two',code='SERIAL-42')])
        self.assertTrue(result['ambiguous']);self.assertNotIn('entity',result)
    def test_short_code_conflict_with_serial_fails_closed(self):
        result=self.resolve(' dhp-001 ',[self.item(serial='DHP-001'),self.item('two',shortCode='DHP-001')])
        self.assertTrue(result['ambiguous']);self.assertNotIn('entity',result)
    def test_short_code_resolves_exactly_case_insensitively(self):
        item=self.item(shortCode='DHP-001')
        self.assertEqual(self.resolve(' dhp-001 ',[item])['entity'],item)
    def test_legacy_serial_or_manufacturer_code_can_resolve_a_shaped_token(self):
        for item in [self.item(serial='DHP-001'),self.item(code='DHP-001')]:
            self.assertEqual(self.resolve('DHP-001',[item])['entity'],item)
    def test_legacy_cross_kind_matches_for_one_item_are_deduplicated(self):
        item=self.item(serial='DHP-001',code='DHP-001')
        self.assertEqual(self.resolve('DHP-001',[item])['entity'],item)
    def test_repeated_native_uuid_is_one_match_for_linked_code(self):
        from uuid import uuid4
        item=self.item(identifier=str(uuid4()),code='NETUM-LABEL-42')
        repeated={**item,'id':item['id'].upper(),'fields':[dict(field) for field in item['fields']]}
        self.assertEqual(self.resolve('NETUM-LABEL-42',[item,repeated])['entity']['id'],item['id'])
    def test_repeated_native_uuid_is_one_match_for_barcode(self):
        from uuid import uuid4
        item=self.item(identifier=str(uuid4()),gtin='4006381333931')
        repeated={**item,'fields':[dict(field) for field in item['fields']]}
        self.assertEqual(self.resolve('4006381333931',[item,repeated])['entity']['id'],item['id'])
    def test_distinct_native_uuids_remain_ambiguous_for_linked_code(self):
        from uuid import uuid4
        items=[self.item(identifier=str(uuid4()),code='NETUM-LABEL-42'),
               self.item(identifier=str(uuid4()),code='NETUM-LABEL-42')]
        result=self.resolve('NETUM-LABEL-42',items)
        self.assertTrue(result['ambiguous'])
        self.assertNotIn('entity',result)
    def test_case_folded_code_collision_is_ambiguous(self):
        items=[self.item(shortCode='DHP-001'),self.item('two',code='dhp-001')]
        result=self.resolve('DHP-001',items)
        self.assertTrue(result['ambiguous'])
        self.assertNotIn('entity',result)
    def test_archived_short_code_does_not_resolve(self):
        self.assertNotIn('entity',self.resolve('DHP-001',[self.item(shortCode='DHP-001',archived=True)]))
    def test_badge_and_homebox_cannot_be_registered(self):
        for raw in ['LAB:U:secret','000-022','/item/efb41b6f-0386-452b-af21-75da992e9677']:
            with self.assertRaises(ValueError):manufacturer_code(raw)

class InvalidRegisteredCodes(unittest.TestCase):
    def test_empty_or_oversize_scan_never_matches_a_native_field(self):
        for raw in ['', 'x'*2049, 'SN\x001234']:
            item={'id':'one','fields':[{'name':MANUFACTURER_FIELD,'type':'text','textValue':raw}]}
            self.assertNotIn('entity',resolve_equipment(raw,normalize(raw),[item]))

class NativeBarcodeTests(unittest.TestCase):
    def resolve(self,raw,items):return resolve_equipment(raw,normalize(raw),items)
    def item(self,identifier,barcode,archived=False):
        return {'id':identifier,'barcode':barcode,'archived':archived}
    def test_numeric_native_barcode_resolves_exactly(self):
        item=self.item('one','4006381333931')
        self.assertEqual(self.resolve('4006381333931',[item])['entity'],item)
    def test_alphanumeric_native_barcode_resolves_exactly(self):
        item=self.item('one','NETUM-C750-YELLOW')
        self.assertEqual(self.resolve('NETUM-C750-YELLOW',[item])['entity'],item)
    def test_duplicate_native_barcodes_fail_closed(self):
        result=self.resolve('NETUM-C750-YELLOW',[
            self.item('one','NETUM-C750-YELLOW'),
            self.item('two','NETUM-C750-YELLOW'),
        ])
        self.assertTrue(result['ambiguous'])
        self.assertNotIn('entity',result)
    def test_archived_native_barcode_does_not_resolve(self):
        self.assertNotIn('entity',self.resolve('NETUM-C750-YELLOW',[
            self.item('one','NETUM-C750-YELLOW',archived=True),
        ]))
    def test_unmatched_native_barcode_does_not_resolve(self):
        result=self.resolve('NETUM-C750-YELLOW',[self.item('one','OTHER-CODE')])
        self.assertNotIn('entity',result)
    def test_native_barcode_and_product_gtin_collision_is_ambiguous(self):
        raw='4006381333931'
        native={'id':'native','barcode':raw,'fields':[]}
        product={'id':'product','barcode':'OTHER-CODE','fields':[
            {'name':'Product GTIN','textValue':'04006381333931'}]}
        result=self.resolve(raw,[native,product])
        self.assertTrue(result['ambiguous'])
        self.assertNotIn('entity',result)
    def test_native_barcode_and_url_serial_fallback_collision_is_ambiguous(self):
        raw='https://vendor.invalid/device?serial=SERIAL-42'
        native={'id':'native','barcode':raw,'fields':[]}
        serial={'id':'serial','barcode':'OTHER-CODE','serialNumber':'SERIAL-42','fields':[]}
        result=self.resolve(raw,[native,serial])
        self.assertTrue(result['ambiguous'])
        self.assertNotIn('entity',result)
