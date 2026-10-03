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
class LabelTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.ledger=Ledger(Path(self.temp.name)/'ledger.db');self.jobs=NativeJobs(self.ledger);self.badges=Badges(self.ledger);self.group=str(uuid4());self.user=str(uuid4());self.badge=self.badges.issue(self.group,self.user,[self.user]);self.prints=[]
        owner=self
        class Client:
            def call(self,*args):return [{'id':owner.user,'name':'Proof person'}]
        self.client=Client()
    def tearDown(self):self.temp.cleanup()
    def run_print(self,key):
        def send(*args,**kwargs):self.prints.append(kwargs['input']);return SimpleNamespace(stdout=b'{"status":"printed"}')
        with patch.object(labels,'probe',return_value={'width_mm':40,'height_mm':30}),patch.object(labels,'printer_path',return_value='/dev/proof'),patch.object(labels,'font',side_effect=lambda size:ImageFont.load_default(size=size)),patch.object(labels.subprocess,'run',side_effect=send):
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
