import json,pathlib,sys,urllib.request
from uuid import uuid4
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path[:0]=[str(root/'ops'),str(root/'kiosk'),str(root/'work/hardware/python')]
from homebox import Homebox
from native_fields import update_payload
from conditions import condition,set_condition
from ledger import Ledger,Conflict
from native_jobs import NativeJobs
from problems import submit_problem,recover_problem
from playwright.sync_api import sync_playwright
client=Homebox(root);native=client.call('/api/v1/users/self')['item'];group=native['defaultGroupId'];base='http://127.0.0.1:17749';asset=None;badge=None
def post(path,data):return json.load(urllib.request.urlopen(urllib.request.Request(base+path,data=json.dumps(data).encode(),headers={'Origin':base,'Content-Type':'application/json'}),timeout=60))
try:
    kind=next(t for t in client.call('/api/v1/entity-types') if not t['isLocation'])
    asset=client.call('/api/v1/entities','POST',{'name':'Problem proof '+str(uuid4())[:8],'quantity':1,'entityTypeId':kind['id'],'parentId':'9b7f1f98-42f6-4ea5-aaf3-079b4d825499'})
    set_condition(client,asset['id'],'Ready');badge=post('/badge/issue',{'user_id':native['id']});post('/scan',{'code':badge['code']})
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);page=browser.new_page(viewport={'width':800,'height':480},has_touch=True);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base);page.get_by_text(native['name'],exact=True).wait_for();page.get_by_role('button',name='Report Problem',exact=False).tap();page.get_by_role('button',name=asset['name'],exact=True).tap();page.get_by_label('Describe the problem',exact=True).tap()
        for key in ['C','R','A','C','K']:page.get_by_role('button',name='Key '+key,exact=True).tap()
        page.get_by_role('button',name='Done',exact=True).tap();page.get_by_role('button',name='Broken',exact=True).tap();page.get_by_role('button',name='Review report',exact=True).tap();page.get_by_role('button',name='Confirm problem report',exact=True).tap();page.get_by_text('Problem saved in Homebox · session ended',exact=True).wait_for(timeout=60000)
        after=client.entity(asset['id']);assert condition(after)=='Broken' and after['parent']['id']==asset['parent']['id']
        entries=client.call('/api/v1/entities/'+asset['id']+'/maintenance');assert len(entries)==1 and entries[0]['description'].startswith('crack') and entries[0]['scheduledDate'] and not entries[0]['completedDate']
        assert not errors,errors;page.screenshot(path=str(root/'work/problem-screen.png'));browser.close()
    # Lost response after native creation: recovery must find the same maintenance UUID.
    jobs=NativeJobs(Ledger(root/'work/ops/ledger.db'));key=str(uuid4());data={'entity_id':asset['id'],'state':'Maintenance','note':'Synthetic recovery proof'}
    class LostResponse:
        def entity(self,*args):return client.entity(*args)
        def call(self,path,method='GET',body=None):
            result=client.call(path,method,body)
            if path.endswith('/maintenance') and method=='POST':raise OSError('Synthetic lost response')
            return result
    try:submit_problem(LostResponse(),jobs,group,native['id'],key,data);raise AssertionError('Uncertain response accepted')
    except Conflict:pass
    job=next(j for j in jobs.unresolved(group) if j['request_key']==key);assert job['status']=='review'
    recover_problem(client,jobs,group,job['id'],'complete');assert len(client.call('/api/v1/entities/'+asset['id']+'/maintenance'))==2
    result={'touch_problem_note':True,'blocked_native_condition':True,'native_shelf_preserved':True,'open_native_maintenance_entry':True,'session_ended':True,'lost_response_recovery_no_duplicate':True,'browser_errors':errors}
    (root/'docs/problem-integration-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
finally:
    if badge:post('/badge/revoke',{'id':badge['id']})
    if asset:
        payload=update_payload(client.entity(asset['id']));payload['archived']=True;client.call('/api/v1/entities/'+asset['id'],'PUT',payload)
