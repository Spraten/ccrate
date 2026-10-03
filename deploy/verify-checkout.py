import json,pathlib,sys,urllib.error,urllib.request
from uuid import uuid4
root=pathlib.Path('/home/user/Desktop/inventory-system')
sys.path.insert(0,str(root/'ops'));sys.path.insert(0,str(root/'work/hardware/python'))
from homebox import Homebox
from conditions import set_condition
from ledger import Ledger
from playwright.sync_api import sync_playwright
client=Homebox(root);native=client.call('/api/v1/users/self')['item'];group=native['defaultGroupId'];actor=native['id']
types=client.call('/api/v1/entity-types');types=types if isinstance(types,list) else types['items']
item_type=next(t for t in types if not t['isLocation'])
base='http://127.0.0.1:17749'
def post(path,data):
    req=urllib.request.Request(base+path,data=json.dumps(data).encode(),headers={'Origin':base,'Content-Type':'application/json'})
    return json.load(urllib.request.urlopen(req,timeout=20))
assets=[];badge=None;ledger=Ledger(root/'work/ops/ledger.db')
try:
    for index in range(2):
        asset=client.call('/api/v1/entities','POST',{'name':'Checkout proof '+str(uuid4())[:8], 'description':'Synthetic checkout integration proof; not real equipment','quantity':1,'entityTypeId':item_type['id'],'parentId':'9b7f1f98-42f6-4ea5-aaf3-079b4d825499'})
        assets.append(asset)
    try:post('/checkout/confirm',{'assets':[a['id'] for a in assets],'request_key':str(uuid4())});raise AssertionError('Unauthenticated checkout accepted')
    except urllib.error.HTTPError as e:assert e.code==401
    badge=post('/badge/issue',{'user_id':actor})
    post('/scan',{'code':badge['code']})
    try:post('/checkout/confirm',{'assets':[a['id'] for a in assets],'request_key':str(uuid4())});raise AssertionError('Unreviewed checkout accepted')
    except urllib.error.HTTPError as e:assert e.code==409
    assert not any(r['entity_id'] in {a['id'] for a in assets} for r in ledger.custody(group))
    for asset in assets:set_condition(client,asset['id'],'Ready')
    before=[client.entity(a['id']) for a in assets]
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True)
        page=browser.new_page(viewport={'width':800,'height':480},has_touch=True)
        errors=[];requests=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda req:requests.append(req.post_data_json) if req.url==base+'/checkout/confirm' else None)
        page.goto(base);page.get_by_text('Homebox connected',exact=False).wait_for()
        page.get_by_role('button',name='Check Out',exact=False).tap()
        for asset in assets:page.get_by_role('button',name=asset['name'],exact=False).tap();page.get_by_role('button',name='Remove '+asset['name'],exact=True).wait_for()
        assert page.get_by_text('Selected: 2',exact=True).is_visible()
        page.get_by_role('button',name='Confirm checkout',exact=True).tap()
        page.get_by_text('Checked out 2 items · session ended',exact=True).wait_for()
        assert json.load(urllib.request.urlopen(base+'/api/session'))['user'] is None
        held=ledger.custody(group);assert all(any(r['entity_id']==a['id'] and r['actor_id']==actor for r in held) for a in assets)
        post('/scan',{'code':badge['code']})
        repeat=post('/checkout/confirm',requests[0]);assert repeat['status']=='completed' and repeat['count']==2
        for original in before:
            after=client.entity(original['id']);assert after==original,'Checkout must leave all native inventory unchanged'
        page.get_by_role('button',name='Browse Stock',exact=False).tap()
        page.get_by_role('button',name=assets[0]['name'],exact=False).tap()
        page.get_by_text('Checked out by: '+native['name'],exact=True).wait_for()
        assert not errors,errors
        browser.close()
    result={'badge_required':True,'unreviewed_cart_rejected':True,'two_asset_touch_checkout':True,'repeat_confirmation_idempotent':True,'native_inventory_unchanged':True,'borrower_visible':True,'session_ends_after_confirmation':True,'browser_errors':errors,'cleanup':'Synthetic custody returned through tested ledger API; live return UI not yet implemented'}
    (root/'docs/checkout-integration-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
finally:
    held={r['entity_id'] for r in ledger.custody(group)}
    cleanup=[a['id'] for a in assets if a['id'] in held]
    if cleanup:
        op=ledger.begin(group,actor,'return',cleanup,str(uuid4()));ledger.complete(op['id'])
    if badge:post('/badge/revoke',{'id':badge['id']})
    for asset in assets:set_condition(client,asset['id'],'Archived')
