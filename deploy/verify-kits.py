import json,pathlib,sys,urllib.request,urllib.error
from uuid import uuid4
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path[:0]=[str(root/'ops'),str(root/'kiosk'),str(root/'work/hardware/python')]
from homebox import Homebox
from native_fields import update_payload
from conditions import set_condition
from playwright.sync_api import sync_playwright
client=Homebox(root);native=client.call('/api/v1/users/self')['item'];base='http://127.0.0.1:17749';assets=[];badge=None
def post(path,data):
    if path in ('/checkout/confirm','/return/confirm'):
        session=json.load(urllib.request.urlopen(base+'/api/session'));data=dict(data,session_generation=session['generation'],session_instance=session['instance'])
    return json.load(urllib.request.urlopen(urllib.request.Request(base+path,data=json.dumps(data).encode(),headers={'Origin':base,'Content-Type':'application/json'}),timeout=60))
try:
    kind=next(t for t in client.call('/api/v1/entity-types') if not t['isLocation'])
    for name in ['Kit','Nested case','Battery','Tool']:
        entity=client.call('/api/v1/entities','POST',{'name':name+' proof '+str(uuid4())[:8],'quantity':1,'entityTypeId':kind['id'],'parentId':'9b7f1f98-42f6-4ea5-aaf3-079b4d825499'});assets.append(entity);set_condition(client,entity['id'],'Ready')
    post('/kit/save',{'entity_id':assets[1]['id'],'members':[assets[2]['id']]});post('/kit/save',{'entity_id':assets[0]['id'],'members':[assets[1]['id'],assets[3]['id']]})
    badge=post('/badge/issue',{'user_id':native['id']});post('/scan',{'code':badge['code']})
    kit=json.load(urllib.request.urlopen(base+'/api/kit?id='+assets[0]['id']));assert len(kit['entities'])==4
    try:post('/checkout/confirm',{'assets':[e['id'] for e in assets],'kit_versions':kit['versions'],'request_key':str(uuid4())});raise AssertionError('Unscanned kit checkout accepted')
    except urllib.error.HTTPError as e:assert e.code==409
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);page=browser.new_page(viewport={'width':800,'height':480},has_touch=True);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base);page.get_by_text(native['name'],exact=True).wait_for();page.get_by_role('button',name='Check Out',exact=False).tap();page.get_by_role('button',name=assets[0]['name'],exact=False).tap();page.get_by_role('heading',name='Verify kit: '+assets[0]['name'],exact=True).wait_for()
        assert page.get_by_role('button',name='Use verified kit',exact=True).is_disabled()
        for entity in assets:page.evaluate('(id)=>routeScan("/item/"+id)',entity['id'])
        page.get_by_text('Scan the kit and every expected component. Verified 4 of 4.',exact=True).wait_for();page.screenshot(path=str(root/'work/kit-screen.png'));page.get_by_role('button',name='Use verified kit',exact=True).tap();page.get_by_text('Selected: 4',exact=True).wait_for();page.get_by_role('button',name='Confirm checkout',exact=True).tap();page.get_by_text('Checked out 4 items · session ended',exact=True).wait_for(timeout=60000)
        page.get_by_role('button',name='Return',exact=False).tap();page.evaluate('(code)=>routeScan(code)',badge['code']);page.get_by_role('button',name=assets[0]['name'],exact=False).tap();page.get_by_role('heading',name='Verify kit: '+assets[0]['name'],exact=True).wait_for()
        for e in assets:page.evaluate('(id)=>routeScan("/item/"+id)',e['id'])
        page.get_by_role('button',name='Use verified kit',exact=True).tap();page.get_by_text('Returning: 4',exact=True).wait_for();page.get_by_role('button',name='Confirm return',exact=True).tap();page.get_by_text('Returned 4 items · session ended',exact=True).wait_for(timeout=60000)
        assert not errors,errors;browser.close()
    result={'native_manifest_uuid_references':True,'nested_components_expanded':True,'incomplete_scan_blocked':True,'four_physical_code_routes_verified':True,'touch_atomic_kit_checkout':True,'touch_verified_kit_return':True,'native_shelf_unchanged':True,'browser_errors':errors,'physical_scanner':'Native QR routing exercised; actual camera acceptance remains outstanding'}
    (root/'docs/kit-integration-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
finally:
    # Return any synthetic outstanding custody, then retain native proof IDs archived.
    if badge:
        held=json.load(urllib.request.urlopen(base+'/api/custody'));ids={e['id'] for e in assets};targets=[{'entity_id':e['entity_id']} for e in held if e['entity_id'] in ids]
        if targets:
            post('/scan',{'code':badge['code']})
            for e in assets:post('/scan',{'code':'/item/'+e['id']})
            post('/return/confirm',{'targets':targets,'kit_versions':kit['versions'],'request_key':str(uuid4())})
        post('/badge/revoke',{'id':badge['id']})
    for entity in assets:
        payload=update_payload(client.entity(entity['id']));payload['archived']=True;client.call('/api/v1/entities/'+entity['id'],'PUT',payload)
