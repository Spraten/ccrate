import pathlib,sys,json,urllib.request,urllib.error,subprocess,time
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path.insert(0,str(root/'ops'))
from homebox import Homebox
from native_jobs import NativeJobs
from ledger import Ledger
batch_id=sys.argv[1]
def api(action,data,origin=True):
    req=urllib.request.Request('http://127.0.0.1:17749/imports/'+action,data=json.dumps(data).encode(),headers={'Content-Type':'application/json',**({'Origin':'http://127.0.0.1:17749'} if origin else {})})
    with urllib.request.urlopen(req,timeout=60) as response:return json.load(response)
try:api('get',{'id':batch_id},False);raise AssertionError('Missing origin was allowed')
except urllib.error.HTTPError as error:assert error.code==403
subprocess.run(['systemctl','--user','restart','homebox-companion.service'],check=True)
for _ in range(10):
    try:batch=api('get',{'id':batch_id});break
    except urllib.error.URLError:time.sleep(1)
assert len(batch['items'])==2 and all(row['status']=='created' for row in batch['items'])
result={'service_restart_resume':True,'missing_origin_rejected':True}
if '1820:207f' not in subprocess.check_output(['lsusb'],text=True):
    try:api('label',{'id':batch_id,'index':0});raise AssertionError('Missing printer was accepted')
    except urllib.error.HTTPError as error:assert error.code==400
    batch=api('get',{'id':batch_id});assert batch['items'][0]['label_status']=='pending';assert all(row['status']=='created' for row in batch['items'])
    jobs=NativeJobs(Ledger(root/'work/ops/ledger.db'));client=Homebox(root);group=client.call('/api/v1/users/self')['item']['defaultGroupId']
    with jobs.ledger.connection() as db:job=db.execute('SELECT id FROM native_jobs WHERE group_id=? AND request_key=?',(group,batch['items'][0]['label_key'])).fetchone()
    assert jobs.detail(group,job['id'])['status']=='cancelled';result['missing_printer_stops_safely']=True
print(json.dumps(result))
