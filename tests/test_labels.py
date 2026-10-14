import json,tempfile,unittest
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

class LegacyLabelTextTests(unittest.TestCase):
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
