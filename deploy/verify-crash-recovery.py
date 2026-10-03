import json,os,pathlib,signal,sqlite3,subprocess,sys,time,urllib.error,urllib.request
from uuid import uuid4
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path[:0]=[str(root/'ops'),str(root/'kiosk'),str(root/'work/hardware/python')]
from homebox import Homebox
from conditions import set_condition
from native_fields import update_payload
base='http://127.0.0.1:17749';asset=None;badge=None
def wait(url):
    for attempt in range(100):
        try:urllib.request.urlopen(url,timeout=1).close();return
        except OSError:time.sleep(.2)
    raise RuntimeError('Service did not recover')
def post(path,data):
    if path in ('/checkout/confirm','/return/confirm'):
        session=json.load(urllib.request.urlopen(base+'/api/session'));data=dict(data,session_generation=session['generation'],session_instance=session['instance'])
    return json.load(urllib.request.urlopen(urllib.request.Request(base+path,data=json.dumps(data).encode(),headers={'Origin':base,'Content-Type':'application/json'}),timeout=30))
def kill_unit(name):
    pid=int(subprocess.check_output(['systemctl','--user','show',name,'--property=MainPID','--value'],text=True));assert pid>1;os.kill(pid,signal.SIGKILL)
def held():return json.load(urllib.request.urlopen(base+'/api/custody'))
client=Homebox(root);native=client.call('/api/v1/users/self')['item']
try:
    kind=next(t for t in client.call('/api/v1/entity-types') if not t['isLocation']);asset=client.call('/api/v1/entities','POST',{'name':'Crash recovery proof '+str(uuid4())[:8],'quantity':1,'entityTypeId':kind['id'],'parentId':'9b7f1f98-42f6-4ea5-aaf3-079b4d825499'});set_condition(client,asset['id'],'Ready');badge=post('/badge/issue',{'user_id':native['id']});post('/scan',{'code':badge['code']});post('/checkout/confirm',{'assets':[asset['id']],'request_key':str(uuid4())})
    assert any(r['entity_id']==asset['id'] for r in held())
    kill_unit('homebox-companion.service');time.sleep(.3);wait(base);assert any(r['entity_id']==asset['id'] for r in held());assert json.load(urllib.request.urlopen(base+'/api/session'))['user'] is None
    ids={e['id'] for e in client.entities()};kill_unit('homebox-native.service');time.sleep(.3);wait('http://127.0.0.1:17745/api/v1/status');assert {e['id'] for e in Homebox(root).entities()}==ids
    subprocess.run(['systemctl','--user','restart','homebox-native.service','homebox-companion.service'],check=True);wait('http://127.0.0.1:17745/api/v1/status');wait(base);assert any(r['entity_id']==asset['id'] for r in held())
    post('/scan',{'code':badge['code']})
    with sqlite3.connect(root/'work/ops/ledger.db') as db:before=db.execute('SELECT COUNT(*) FROM operations').fetchone()[0]
    try:post('/checkout/confirm',{'assets':[asset['id'],asset['id']],'request_key':str(uuid4())});raise AssertionError('Corrupt transaction accepted')
    except urllib.error.HTTPError as error:assert error.code==400
    with sqlite3.connect(root/'work/ops/ledger.db') as db:assert before==db.execute('SELECT COUNT(*) FROM operations').fetchone()[0];assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    post('/return/confirm',{'targets':[{'entity_id':asset['id']}],'request_key':str(uuid4())})
    result={'companion_sigkill_auto_restart':True,'completed_custody_survived_crash':True,'badge_ram_session_cleared':True,'homebox_sigkill_auto_restart':True,'native_inventory_ids_preserved':True,'full_service_restart':True,'corrupt_transaction_rejected_without_journal_write':True,'operational_integrity':'ok','abrupt_power_loss':'Not physically performed; process crashes were exercised'}
    (root/'docs/crash-recovery-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
finally:
    wait('http://127.0.0.1:17745/api/v1/status');wait(base);client=Homebox(root)
    if badge:
        if asset and any(r['entity_id']==asset['id'] for r in held()):post('/scan',{'code':badge['code']});post('/return/confirm',{'targets':[{'entity_id':asset['id']}],'request_key':str(uuid4())})
        post('/badge/revoke',{'id':badge['id']})
    if asset:
        payload=update_payload(client.entity(asset['id']));payload['archived']=True;client.call('/api/v1/entities/'+asset['id'],'PUT',payload)
