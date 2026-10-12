import pathlib
import sys
import unittest
import io
import hashlib
import base64
import json
import subprocess
import signal
import tempfile
from PIL import ImageChops
from unittest.mock import patch
from PIL import Image
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'ops'))
import label_render
from label_layouts import _starter


class LabelRenderTests(unittest.TestCase):
    def test_profile_dimensions_fail_before_launch(self):
        with self.assertRaisesRegex(ValueError,'dimensions'):
            label_render.render_documents([{'page':{'widthMm':39,'heightMm':28}}],['supvan'])

    def test_paper_rejects_mismatched_review_without_scaling(self):
        with self.assertRaisesRegex(ValueError,'Review profile or dimensions'):
            label_render.render_paper_sheet([{'profile':'letter','label_mm':[60,40],'dpi':300,'png':b'x'}],{'page_mm':[215.9,279.4],'label_mm':[50,30],'margin_mm':10,'gap_mm':3,'cut_guides':False})

    def test_paper_geometry_rejects_nonfinite_gutters_and_nonfitting_slots(self):
        base={'page_mm':[215.9,279.4],'label_mm':[60,40],'margin_mm':10,'gap_mm':3,'cut_guides':False}
        for key,value in [('margin_mm',float('nan')),('gap_mm',float('inf'))]:
            geometry={**base,key:value}
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'finite'):
                label_render.render_paper_sheet([{}],geometry)
        with self.assertRaisesRegex(ValueError,'Paper margin and gap'):
            label_render.render_paper_sheet([{}],{**base,'margin_mm':-1})

    def test_input_and_output_caps_are_separate(self):
        self.assertEqual(label_render.MAX_INPUT,1024*1024)
        self.assertEqual(label_render.MAX_TRUSTED_INPUT,32*1024*1024)
        self.assertEqual(label_render.MAX_OUTPUT,16*1024*1024)

    def test_untrusted_input_cap_is_enforced_before_subprocess(self):
        with patch.object(label_render.subprocess,'Popen') as popen:
            with self.assertRaisesRegex(ValueError,'input exceeds its byte limit'):
                label_render._run({'asset_root':'unused','padding':'x'*label_render.MAX_INPUT},20)
            with self.assertRaisesRegex(ValueError,'input exceeds its byte limit'):
                label_render._run({'asset_root':'unused','trusted_sheet':True,'padding':'x'*label_render.MAX_TRUSTED_INPUT},20)
            popen.assert_not_called()

    def test_renderer_output_cap_is_enforced(self):
        class Completed:
            returncode=0
            def communicate(self, *_args, **_kwargs):return b'x'*(label_render.MAX_OUTPUT+1),b''
        with patch.object(label_render.subprocess,'Popen',return_value=Completed()):
            with self.assertRaisesRegex(ValueError,'output exceeds 16 MiB'):
                label_render._run({'asset_root':'unused'},20)

    def test_timeout_kills_the_renderer_process_group(self):
        class TimedOut:
            pid=12345
            returncode=-signal.SIGKILL
            def __init__(self):self.calls=0
            def communicate(self,*_args,**_kwargs):
                self.calls+=1
                if self.calls==1:raise subprocess.TimeoutExpired('renderer',.01)
                return b'',b''
        process=TimedOut()
        with patch.object(label_render.subprocess,'Popen',return_value=process),patch.object(label_render.os,'killpg') as killpg:
            with self.assertRaisesRegex(TimeoutError,'20-second request budget'):
                label_render._run({'asset_root':'unused'},.01)
        killpg.assert_called_once_with(process.pid,signal.SIGKILL)

    def test_missing_staged_asset_has_a_clear_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp);(root/'manifest.json').write_text(json.dumps({'runtime_assets':{'render.html':'a'*64,'fonts/DejaVuSans.ttf':'b'*64}}))
            with self.assertRaisesRegex(ValueError,'asset is missing'):
                label_render._check_manifest(root)

    def test_six_starters_render_with_canonical_profile_output(self):
        docs=[_starter(profile,layout) for profile in ('supvan','letter') for layout in ('left','top','compact')]
        profiles=['supvan']*3+['letter']*3
        docs[0]['variables']['item_name']='Unicode Ω microscope'
        docs[0]['variables']['item_path']='/item/10000000-0000-4000-8000-000000000001'
        outputs=label_render.render_documents(docs,profiles)
        self.assertEqual([o['width'] for o in outputs[:6]],[320,320,320,709,709,709])
        self.assertEqual([o['height'] for o in outputs[:6]],[224,224,224,472,472,472])
        self.assertEqual(outputs[0]['sha256'],hashlib.sha256(outputs[0]['png']).hexdigest())
        supvan=Image.open(io.BytesIO(outputs[0]['png']))
        self.assertEqual(supvan.mode,'L');self.assertEqual(set(supvan.getdata()),{0,255})
        # The SUPVAN starter places a four-module (16 dot) white border around
        # the 29-module QR matrix; 4-dot integer module cells are enforced by paintQr.
        # Element origin is (16,36) px. Its 148px raster is centered with a
        # 2px inset; the matrix occupies x=34..150,y=54..170, leaving exactly
        # 16px/four-cell white margins on every side.
        self.assertEqual(set(supvan.crop((18,54,34,170)).getdata()),{255})
        self.assertEqual(set(supvan.crop((150,54,166,170)).getdata()),{255})
        self.assertEqual(set(supvan.crop((34,38,150,54)).getdata()),{255})
        self.assertEqual(set(supvan.crop((34,170,150,186)).getdata()),{255})
        self.assertEqual(Image.open(io.BytesIO(outputs[3]['png'])).mode,'RGB')

    def test_independent_render_contexts_have_same_hash(self):
        doc=_starter('supvan','left')
        first=label_render.render_document(doc,'supvan')
        second=label_render.render_document(doc,'supvan')
        self.assertEqual(first['sha256'],second['sha256'])

    def test_short_unicode_text_that_overflows_box_is_visibly_truncated(self):
        doc=_starter('supvan','left')
        doc['variables']={'item_name':'Ω microscope','asset_code':'','item_path':'/item/10000000-0000-4000-8000-000000000001'}
        name=next(e for e in doc['elements'] if e['id']=='item-name')
        name['widthMm']=2.5;name['heightMm']=4
        result=label_render.render_document(doc,'supvan')
        self.assertTrue(any('ellipsis' in warning for warning in result['warnings']))

    def test_quarter_turn_qr_with_fractional_origin_decodes_after_canonicalization(self):
        doc=_starter('supvan','left')
        qr=next(element for element in doc['elements'] if element['type']=='qr')
        qr.update(xMm=2.1,yMm=4.6,rotation=90)
        doc['variables']['item_path']='/item/10000000-0000-4000-8000-000000000001'
        output=label_render.render_document(doc,'supvan')
        self.assertEqual(output['width'],320)
        self.assertEqual(label_render._decode_qr_l(Image.open(io.BytesIO(output['png']))),doc['variables']['item_path'])

    def test_nineteen_frozen_labels_compose_two_letter_pages(self):
        documents=[]
        for index in range(19):
            doc=_starter('letter','left')
            doc['variables']={'item_name':f'Item {index+1}','asset_code':'','item_path':f'/item/10000000-0000-4000-8000-{index+1:012d}'}
            documents.append(doc)
        outputs=label_render.render_documents(documents,['letter']*19)
        reviews=[{'profile':'letter','label_mm':[60,40],'dpi':300,'png':row['png'],'sha256':row['sha256']} for row in outputs]
        sheet=label_render.render_paper_sheet(reviews,{'page_mm':[215.9,279.4],'label_mm':[60,40],'margin_mm':10,'gap_mm':3,'cut_guides':True})
        self.assertEqual(sheet['geometry']['columns'],3);self.assertEqual(sheet['geometry']['rows'],6)
        self.assertEqual(len(sheet['pages']),2)
        first=Image.open(io.BytesIO(base64.b64decode(sheet['pages'][0]['image'].split(',',1)[1])))
        second=Image.open(io.BytesIO(base64.b64decode(sheet['pages'][1]['image'].split(',',1)[1])))
        self.assertEqual(first.size,(2550,3300));self.assertEqual(second.size,(2550,3300))
        self.assertEqual(first.mode,'RGB');self.assertEqual(second.mode,'RGB')
        # Slots are placed row-major from the 10 mm margin; composition must
        # preserve each frozen reviewed raster pixel-for-pixel and in order.
        x=round(10*300/25.4); y=x
        self.assertIsNone(ImageChops.difference(first.crop((x,y,x+709,y+472)),Image.open(io.BytesIO(outputs[0]['png'])).convert('RGB')).getbbox())
        self.assertIsNone(ImageChops.difference(second.crop((x,y,x+709,y+472)),Image.open(io.BytesIO(outputs[18]['png'])).convert('RGB')).getbbox())


if __name__=='__main__': unittest.main()
