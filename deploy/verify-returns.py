import json,pathlib,sys,urllib.request
from uuid import uuid4
root=pathlib.Path('/home/user/Desktop/inventory-system')
sys.path.insert(0,str(root/'ops'));sys.path.insert(0,str(root/'work/hardware/python'))
from homebox import Homebox
from conditions import set_condition,condition,condition_note
from ledger import Ledger,Conflict
from returns import confirm_return,recover
from playwright.sync_api import sync_playwright
client=Homebox(root);native=client.call('/api/v1/users/self')['item'];group=native['defaultGroupId'];actor=native['id']
types=client.call('/api/v1/entity-types');types=types if isinstance(types,list) else types['items']
item_type=next(t for t in types if not t['isLocation'])
base='http://127.0.0.1:17749'
def post(path,data):
    request=urllib.request.Request(base+path,data=json.dumps(data).encode(),headers={'Origin':base,'Content-Type':'application/json'})
    return json.load(urllib.request.urlopen(request,timeout=20))
locations=json.load(urllib.request.urlopen(base+'/api/locations'))
shelf=next(e for e in locations if e['name']=='Demo Shelf A1')
other=next(e for e in locations if e['name']=='Demo Shelf A2')
assets=[];badge=None;ledger=Ledger(root/'work/ops/ledger.db')
class LostResponse:
    def entity(self,key):return client.entity(key)
    def call(self,path,method='GET',data=None):
        result=client.call(path,method,data)
        if method=='PATCH':raise OSError('Injected lost response after native destination update')
        return result
try:
    for index in range(3):
        asset=client.call('/api/v1/entities','POST',{'name':'Return proof '+str(uuid4())[:8],'description':'Synthetic return integration proof; not real equipment','quantity':1,'entityTypeId':item_type['id'],'parentId':shelf['id']})
        assets.append(asset);set_condition(client,asset['id'],'Ready')
    badge=post('/badge/issue',{'user_id':actor});post('/scan',{'code':badge['code']})
    post('/checkout/confirm',{'assets':[a['id'] for a in assets],'request_key':str(uuid4())})
    before=[client.entity(a['id']) for a in assets]
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--use-fake-device-for-media-stream'])
        page=browser.new_page(viewport={'width':800,'height':480},has_touch=True,permissions=['camera'])
        errors=[];requests=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda req:requests.append(req.post_data_json) if req.url==base+'/return/confirm' else None)
        page.goto(base);page.get_by_text('Homebox connected',exact=False).wait_for()
        page.get_by_role('button',name='Return',exact=False).tap()
        page.get_by_text('Scan your badge. You may return equipment for a colleague.',exact=True).wait_for()
        page.evaluate('(code)=>routeScan(code)',badge['code'])
        page.get_by_role('button',name=assets[0]['name'],exact=False).tap()
        page.get_by_text('Returning: 1',exact=True).wait_for()
        page.get_by_text('Destination: '+shelf['name'],exact=True).wait_for()
        page.get_by_role('button',name='Confirm return',exact=True).tap()
        page.get_by_text('Returned 1 item · session ended',exact=True).wait_for()
        assert client.entity(assets[0]['id'])==before[0],'Unchanged return must not rewrite native inventory'
        assert json.load(urllib.request.urlopen(base+'/api/session'))['user'] is None
        post('/scan',{'code':badge['code']});repeat=post('/return/confirm',requests[0]);assert repeat['status']=='completed'
        page.get_by_role('button',name='Return',exact=False).tap();page.evaluate('(code)=>routeScan(code)',badge['code'])
        page.get_by_role('button',name=assets[1]['name'],exact=False).tap();page.get_by_text('Returning: 1',exact=True).wait_for()
        page.get_by_role('button',name='Condition',exact=True).tap();page.get_by_role('button',name='Broken',exact=True).tap()
        page.get_by_role('textbox',name='Issue note for '+assets[1]['name']).tap()
        for letter in 'CRACKED':page.get_by_role('button',name='Key '+letter,exact=True).tap()
        page.get_by_role('button',name='Done',exact=True).tap()
        page.get_by_role('button',name='Change destination',exact=True).tap()
        page.get_by_text('Hold your badge or a Homebox QR code',exact=False).wait_for()
        page.evaluate('(code)=>routeScan(code)','/location/'+other['id'])
        page.get_by_text('Destination: '+other['name'],exact=True).wait_for()
        page.get_by_role('button',name='Confirm return',exact=True).tap();page.get_by_text('Returned 1 item · session ended',exact=True).wait_for()
        changed=client.entity(assets[1]['id']);assert condition(changed)=='Broken' and condition_note(changed)=='cracked';assert changed['parent']['id']==other['id']
        for key in ('name','description','quantity','serialNumber','assetId','tags','entityType','attachments'):
            assert changed[key]==before[1][key],key
        try:
            confirm_return(LostResponse(),ledger,group,actor,[{'entity_id':assets[2]['id'],'destination_id':other['id']}],str(uuid4()),lambda:True)
            raise AssertionError('Injected lost response was ignored')
        except Conflict:pass
        unresolved=next(row for row in ledger.unresolved() if assets[2]['id'] in ledger.detail(group,row['id'])['assets'])
        assert unresolved['status']=='review'
        assert any(r['entity_id']==assets[2]['id'] for r in ledger.custody(group))
        page.get_by_role('button',name='Admin',exact=True).tap();page.get_by_role('button',name='Review interrupted operations',exact=True).tap()
        page.get_by_text(assets[2]['name']+' · Ready · '+other['name'],exact=True).wait_for()
        page.get_by_role('button',name='Finish operation',exact=True).tap();page.get_by_role('button',name='Confirm finish',exact=True).tap()
        page.get_by_text('No interrupted operations.',exact=True).wait_for()
        assert not any(r['entity_id'] in {a['id'] for a in assets} for r in ledger.custody(group))
        page.get_by_role('button',name='← Home',exact=True).tap();page.get_by_role('button',name='Browse Stock',exact=False).tap()
        page.get_by_role('button',name=assets[1]['name'],exact=False).tap();page.get_by_role('button',name='Activity history',exact=True).wait_for();page.get_by_role('button',name='Activity history',exact=True).tap()
        page.get_by_text('Return · completed',exact=True).wait_for();page.get_by_text('Checkout · completed',exact=True).wait_for()
        assert not errors,errors
        browser.close()
    result={'touch_unchanged_return':True,'assigned_shelf_default':True,'unchanged_native_record_preserved':True,'changed_condition_note_touch_input':True,'different_destination_scan':True,'native_metadata_preserved':True,'idempotent_return':True,'session_ends':True,'lost_native_response_retains_custody':True,'admin_recovery_finishes_without_duplicate_move':True,'asset_history_visible':True,'browser_errors':errors}
    (root/'docs/return-integration-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
finally:
    own={a['id'] for a in assets}
    for op in ledger.unresolved():
        detail=ledger.detail(group,op['id'])
        if not set(detail['assets'])<=own:continue
        try:recover(client,ledger,group,op['id'],'complete')
        except Exception:recover(client,ledger,group,op['id'],'cancel')
    held={r['entity_id'] for r in ledger.custody(group)};remaining=sorted(own&held)
    if remaining:
        op=ledger.begin(group,actor,'return',remaining,str(uuid4()));ledger.complete(op['id'])
    if badge:post('/badge/revoke',{'id':badge['id']})
    for asset in assets:set_condition(client,asset['id'],'Archived')
