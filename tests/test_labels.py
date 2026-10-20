import hashlib,json,tempfile,unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch
from types import SimpleNamespace
from PIL import ImageFont
from ledger import Ledger,Conflict
from native_jobs import NativeJobs
from badges import Badges
import labels

def _drawn_name_lines(name):
    real_draw=labels.ImageDraw.Draw;drawn=[]
    class TrackingDraw:
        def __init__(self,*args,**kwargs):self.inner=real_draw(*args,**kwargs)
        def __getattr__(self,name):return getattr(self.inner,name)
        def text(self,xy,text,*args,**kwargs):
            if 30 <= xy[1] < 152:drawn.append(text)
            return self.inner.text(xy,text,*args,**kwargs)
    with patch.object(labels,'font',side_effect=lambda size:ImageFont.load_default(size=size)),patch.object(labels.ImageDraw,'Draw',side_effect=TrackingDraw):
        labels.render({'id':str(uuid4()),'name':name},32,28,code_override='x')
    return drawn

class _FixedWidthDraw:
    def __init__(self,width):self.width=width
    def textbbox(self,xy,text,font=None):
        if text=='e\u0301':return (0,0,3,1)
        if text=='e\u0301…':return (0,0,4,1)
        width=sum(10 if ord(character)>0xffff else self.width for character in text)
        return (0,0,width,1)

class _NegativeBearingDraw:
    def textbbox(self,xy,text,font=None):
        if text=='…':return (0,0,3,1)
        if text=='J':return (-2,0,5,1)
        return (0,0,len(text),1)

class LegacyLabelTextTests(unittest.TestCase):
    def test_single_glyph_wider_than_box_due_to_negative_bearing_is_truncated(self):
        self.assertEqual(labels._fit_name_lines('J',_NegativeBearingDraw(),None,6,1),['…'])

    def test_explicit_newline_remains_a_line_break_in_the_legacy_preview(self):
        self.assertEqual(_drawn_name_lines('Alpha\nBeta'),['Alpha','Beta'])

    def test_multiword_overflow_is_marked_with_an_ellipsis(self):
        drawn=_drawn_name_lines('alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu')
        self.assertTrue(drawn[-1].endswith('…'),drawn)

    def test_unbroken_overflow_wraps_and_is_marked_with_an_ellipsis(self):
        drawn=_drawn_name_lines('ABCDEFGHIJKLMNOPQRSTUVWXYZ' * 5)
        self.assertGreater(len(drawn),1,drawn)
        self.assertTrue(drawn[-1].endswith('…'),drawn)

    def test_crlf_preserves_line_breaks_and_marks_overflow(self):
        drawn=_drawn_name_lines('Alpha\r\nBeta\r\nGamma\r\nDelta\r\nEpsilon')
        self.assertEqual(len(drawn),4,drawn)
        self.assertEqual(drawn[:3],['Alpha','Beta','Gamma'])
        self.assertTrue(drawn[-1].endswith('…'),drawn)

    def test_overwide_grapheme_is_omitted_from_name_lines(self):
        self.assertEqual(labels._fit_name_lines('🧰',_FixedWidthDraw(10),None,5,1),[])

    def test_truncation_does_not_split_combining_grapheme(self):
        self.assertEqual(labels._fit_name_lines('e\u0301🧰',_FixedWidthDraw(1),None,3,1),['…'])

class LegacyLabelPreviewTests(unittest.TestCase):
    def test_legacy_preview_uses_fixed_stock_dimensions_without_probing(self):
        user=str(uuid4())
        entity={'id':user,'name':'Multiword storage location','entityType':{'isLocation':True}}
        class Client:
            def entity(self,entity_id):return entity
        image=SimpleNamespace(width=320,height=208,save=lambda stream,format:stream.write(b'png'))
        with patch.object(labels,'probe',side_effect=AssertionError('offline preview must not probe')) as probe,patch.object(labels,'render',return_value=(image,'location-code')) as render:
            result=labels.preview(Client(),user)
        probe.assert_not_called()
        render.assert_called_once_with(entity,40,28)
        self.assertEqual((result['width'],result['height']),(320,208))

class LabelTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.ledger=Ledger(Path(self.temp.name)/'ledger.db');self.jobs=NativeJobs(self.ledger);self.badges=Badges(self.ledger);self.group=str(uuid4());self.user=str(uuid4());self.badge=self.badges.issue(self.group,self.user,[self.user]);self.prints=[]
        owner=self
        class Client:
            def call(self,*args):return [{'id':owner.user,'name':'Proof person'}]
        self.client=Client()
    def tearDown(self):self.temp.cleanup()
    def run_print(self,key,reprint=False):
        def send(*args,**kwargs):self.prints.append(kwargs['input']);return SimpleNamespace(stdout=b'{"status":"printed"}')
        with patch.object(labels,'probe',return_value={'width_mm':40,'height_mm':30}),patch.object(labels,'printer_path',return_value='/dev/proof'),patch.object(labels,'font',side_effect=lambda size:ImageFont.load_default(size=size)),patch.object(labels.subprocess,'run',side_effect=send):
            if reprint:return labels.reprint_badge(self.client,self.badges,self.jobs,self.group,self.user,key,self.badge['id'])
            return labels.print_badge(self.client,self.badges,self.jobs,self.group,self.user,key,self.badge['id'],self.badge['code'])
    def test_badge_raw_token_never_persisted(self):
        self.run_print(str(uuid4()))
        with self.ledger.connection() as db:
            self.assertFalse(any(self.badge['code'] in str(tuple(row)) for row in db.execute('SELECT * FROM native_jobs')))
            self.assertFalse(any(self.badge['code'] in row['detail'] for row in db.execute('SELECT * FROM native_job_events')))
        self.assertTrue(self.prints)
    def test_same_badge_request_prints_once(self):
        key=str(uuid4());self.assertEqual(self.run_print(key)['id'],self.run_print(key)['id']);self.assertEqual(len(self.prints),1)
    def test_revoked_badge_cannot_print(self):
        self.badges.revoke(self.group,self.badge['id'])
        with self.assertRaises(ValueError):self.run_print(str(uuid4()))
        self.assertFalse(self.prints)
    def test_unknown_output_cannot_be_retried(self):
        key=str(uuid4())
        with patch.object(labels,'probe',return_value={'width_mm':40,'height_mm':30}),patch.object(labels,'printer_path',return_value='/dev/proof'),patch.object(labels,'font',side_effect=lambda size:ImageFont.load_default(size=size)),patch.object(labels.subprocess,'run',side_effect=OSError('Lost completion')):
            with self.assertRaises(Conflict):labels.print_badge(self.client,self.badges,self.jobs,self.group,self.user,key,self.badge['id'],self.badge['code'])
        with self.assertRaises(Conflict):self.run_print(key)
        self.assertFalse(self.prints)
    def test_too_small_stock_rejected(self):
        with self.assertRaises(ValueError):labels.render({'id':self.user,'name':'Proof'},width_mm=20,height_mm=20)
    def test_reprint_keeps_identity_and_does_not_create_a_badge(self):
        self.run_print(str(uuid4()))
        key=str(uuid4());self.run_print(key,reprint=True);self.run_print(key,reprint=True)
        self.assertEqual(len(self.prints),2)
        self.assertEqual(self.prints[0],self.prints[1])
        self.assertEqual(len(self.badges.list(self.group)),1)
    def test_new_reprint_cannot_repeat_an_unconfirmed_initial_print(self):
        key=str(uuid4())
        with patch.object(labels,'probe',return_value={'width_mm':40,'height_mm':30}),patch.object(labels,'printer_path',return_value='/dev/proof'),patch.object(labels,'font',side_effect=lambda size:ImageFont.load_default(size=size)),patch.object(labels.subprocess,'run',side_effect=OSError('Lost completion')):
            with self.assertRaises(Conflict):labels.print_badge(self.client,self.badges,self.jobs,self.group,self.user,key,self.badge['id'],self.badge['code'])
        with self.assertRaises(Conflict):self.run_print(str(uuid4()),reprint=True)
        self.assertFalse(self.prints)


class PrinterAdapterResolutionTests(unittest.TestCase):
    def test_adapter_uses_code_root_over_runtime_data_root(self):
        with patch.dict(labels.os.environ, {'WORKSHOP_PRINTER_ADAPTER':'','WORKSHOP_CODE_ROOT':'/srv/ccrate','WORKSHOP_ROOT':'/srv/data'}, clear=True):
            self.assertEqual(labels.adapter(), '/srv/ccrate/work/supvan-cups/target/release/examples/kiosk-label')

    def test_explicit_printer_adapter_overrides_code_root(self):
        with patch.dict(labels.os.environ, {'WORKSHOP_PRINTER_ADAPTER':'/opt/kiosk-label','WORKSHOP_CODE_ROOT':'/srv/ccrate'}, clear=True):
            self.assertEqual(labels.adapter(), '/opt/kiosk-label')

    def test_legacy_workshop_root_is_used_when_code_root_is_unset(self):
        with patch.dict(labels.os.environ, {'WORKSHOP_ROOT':'/srv/legacy-code'}, clear=True):
            self.assertEqual(labels.adapter(), '/srv/legacy-code/work/supvan-cups/target/release/examples/kiosk-label')

    def test_missing_adapter_is_detected_before_hidraw_or_subprocess(self):
        with patch.dict(labels.os.environ, {'WORKSHOP_PRINTER_ADAPTER':'/missing/kiosk-label'}, clear=True), \
             patch.object(labels.os.path, 'isfile', return_value=False), \
             patch.object(labels.subprocess, 'run') as run, \
             patch.object(labels.pathlib.Path, 'glob') as glob:
            with self.assertRaisesRegex(FileNotFoundError, 'adapter'):
                labels.probe()
            run.assert_not_called()
            glob.assert_not_called()


class AssignedEquipmentLabelTests(unittest.TestCase):
    def setUp(self):
        self.group = str(uuid4())
        self.item = str(uuid4())
        self.native = {'id': self.item, 'name': 'Drone', 'displayId': 'HB-104', 'updatedAt': 'v1'}

    def test_assigned_id_projection_preserves_native_uuid_and_legacy_display_id(self):
        class Client:
            timeout = 5
            def entity(inner, entity_id): return dict(self.native)
        class Catalog:
            def assignment(inner, group, entity_id):
                return {'entity_id': entity_id, 'display_id': 'DRONE-2S-6'} if group == self.group and entity_id == self.item else None
        projected = labels.with_assigned_display_ids(Client(), Catalog(), self.group)
        entity = projected.entity(self.item)
        self.assertEqual(entity['id'], self.item)
        self.assertEqual(entity['displayId'], 'DRONE-2S-6')
        self.assertEqual(projected.timeout, 5)
        self.assertEqual(labels.with_assigned_display_ids(Client(), Catalog(), str(uuid4())).entity(self.item)['displayId'], 'HB-104')

    def test_label_preview_uses_effective_id_and_keeps_qr_destination_native(self):
        class Client:
            def entity(inner, entity_id): return dict(self.native)
        class Catalog:
            def assignment(inner, group, entity_id): return {'display_id': 'DRONE-2S-6'}
        class Layouts:
            def preview(inner, client, group, actor, data):
                entity = client.entity(data['entity_id'])
                return {'variables': {'display_id': entity['displayId'], 'item_path': f"/item/{entity['id']}"}}
        result = labels.preview(Client(), self.item, layouts=Layouts(), group=self.group, actor=str(uuid4()), template_id='template', template_revision=1, catalog=Catalog())
        self.assertEqual(result['variables']['display_id'], 'DRONE-2S-6')
        self.assertEqual(result['variables']['item_path'], f'/item/{self.item}')

    def test_changed_effective_id_invalidates_review_before_printer_access(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        ledger = Ledger(Path(temporary.name)/'ledger.db')
        jobs = NativeJobs(ledger)
        review_id = str(uuid4())
        class Client:
            def entity(inner, entity_id): return dict(self.native)
        class Catalog:
            def assignment(inner, group, entity_id): return {'display_id': 'DRONE-2S-7'}
        class Layouts:
            def reconcile_reviews(inner, group, jobs): pass
            def get(inner, group, template_id): return {'revision': 1, 'document': {}}
            def review(inner, group, actor, key):
                digest = hashlib.sha256(json.dumps({}, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
                return {'item_id': self.item, 'attached_job': None, 'item_updated_at': 'v1', 'item_display_id': 'DRONE-2S-6', 'template_id': 'template', 'template_revision': 1, 'template_hash': digest, 'png': b'', 'sha256': 'hash', 'profile': 'supvan', 'label_mm': [40,28], 'dpi': 203.2, 'width': 320, 'height': 224}
        with patch.object(labels, 'probe', side_effect=AssertionError('stale review must be rejected before printer access')):
            with self.assertRaisesRegex(Conflict, 'changed since review'):
                labels.print_label(Client(), jobs, self.group, str(uuid4()), str(uuid4()), self.item, layouts=Layouts(), review_id=review_id, catalog=Catalog())
