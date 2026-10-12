import base64,io,pathlib,tempfile,unittest
from unittest.mock import patch
from uuid import uuid4
from PIL import Image
from attachments import ensure_photo,photo_bytes,validate_photos
from ledger import Ledger,Conflict
from native_jobs import NativeJobs

class Photos(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.jobs=NativeJobs(Ledger(pathlib.Path(self.tmp.name)/'ledger.db'))
        self.group,self.actor,self.entity=[str(uuid4()) for _ in range(3)]
        self.files={};self.uploads=0
        self.client=type('Client',(),{'base':'http://fixture','token':'fixture'})()
        self.client.entity=lambda _: {'attachments':[{'id':title,'title':title} for title in self.files]}
        self.values=[]
        for color in ['red','blue']:
            out=io.BytesIO();Image.new('RGB',(32,24),color).save(out,format='JPEG')
            self.values.append('data:image/jpeg;base64,'+base64.b64encode(out.getvalue()).decode())
    def job(self,payload):
        j=self.jobs.prepare(self.group,self.actor,'create_asset',str(uuid4()),payload)
        self.jobs.sent(self.group,j['id']);self.jobs.bind(self.group,j['id'],self.entity);return j['id']
    def upload(self,client,entity,title,content):
        self.uploads+=1;self.files[title]=content
    def read(self,request,**kwargs):
        response=io.BytesIO(self.files[request.full_url.rsplit('/',1)[1]])
        return response
    def test_multiple_photos_recovery_never_duplicates(self):
        key=self.job({'photos':self.values})
        def lost(client,entity,title,content):
            self.upload(client,entity,title,content)
            if self.uploads==2:raise OSError('lost response')
        with patch('attachments.upload',side_effect=lost),patch('attachments.urllib.request.urlopen',side_effect=self.read):
            with self.assertRaises(OSError):ensure_photo(self.client,self.jobs,self.group,key,self.entity)
            ensure_photo(self.client,self.jobs,self.group,key,self.entity)
        self.assertEqual(self.uploads,2);self.assertEqual(len(self.files),2)
    def test_unknown_upload_not_retried(self):
        key=self.job({'photos':self.values})
        with patch('attachments.upload',side_effect=OSError('unknown')) as upload:
            with self.assertRaises(OSError):ensure_photo(self.client,self.jobs,self.group,key,self.entity)
            with self.assertRaises(Conflict):ensure_photo(self.client,self.jobs,self.group,key,self.entity)
            self.assertEqual(upload.call_count,1)
    def test_legacy_photo_recovery(self):
        key=self.job({'photo':self.values[0]})
        self.files['Equipment photo '+key+'.jpg']=photo_bytes(self.values[0])
        self.jobs.context(self.group,key,photo_post_started=True)
        with patch('attachments.upload') as upload,patch('attachments.urllib.request.urlopen',side_effect=self.read):
            ensure_photo(self.client,self.jobs,self.group,key,self.entity);upload.assert_not_called()
    def test_invalid_photo_collection(self):
        for values in ['bad',self.values*4,[None]]:
            with self.assertRaises(ValueError):validate_photos({'photos':values})
