import json,pathlib,sys,urllib.request,urllib.error
from uuid import uuid4
root=pathlib.Path('/home/user/Desktop/inventory-system')
sys.path[:0]=[str(root/'ops'),str(root/'work/hardware/python')]
from homebox import Homebox
from native_fields import update_payload
from conditions import condition
from playwright.sync_api import sync_playwright
client=Homebox(root);base='http://127.0.0.1:17749';created=[];template=None;badge=None
def post(path,data):
    if path=='/enroll/confirm':data=dict(data,session_generation=json.load(urllib.request.urlopen(base+'/api/session'))['generation'],session_instance=json.load(urllib.request.urlopen(base+'/api/session'))['instance'])
    return json.load(urllib.request.urlopen(urllib.request.Request(base+path,data=json.dumps(data).encode(),headers={'Origin':base,'Content-Type':'application/json'}),timeout=60))
def get(path):return json.load(urllib.request.urlopen(base+path,timeout=60))
try:
    user=client.call('/api/v1/users/self')['item'];badge=post('/badge/issue',{'user_id':user['id']})
    location=post('/locations/create',{'request_key':str(uuid4()),'input':{'name':'Enrollment proof shelf '+str(uuid4())[:8],'map_room':True}});created.append(location['entity_id'])
    # Valid synthetic GTIN. Remove this exact template only after test completion.
    code='12345678901231'
    assert not get('/api/product?gtin='+code)['product'],'Synthetic GTIN already exists'
    product=post('/catalog/create',{'request_key':str(uuid4()),'input':{'gtin':code,'name':'Enrollment proof product','manufacturer':'Proof maker','model':'Proof model'}});template=product['entity_id']
    catalog=get('/api/product?gtin='+code)['product'];assert catalog['manufacturer']=='Proof maker'
    post('/scan',{'code':badge['code']})
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':800,'height':480},has_touch=True);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base);page.get_by_text(user['name'],exact=True).wait_for()
        page.get_by_role('button',name='Add Equipment',exact=False).tap()
        page.get_by_label('Product barcode',exact=True).wait_for()
        # Drive the same scanner route used by decoded camera frames.
        page.evaluate('(code)=>routeScan(code)',code)
        page.get_by_label('Equipment name',exact=True).wait_for()
        page.wait_for_function("document.querySelector('[aria-label=\"Equipment name\"]').value==='Enrollment proof product'")
        page.get_by_label('Serial number',exact=True).tap()
        for key in ['S','E','R','1','2','3']:page.get_by_role('button',name='Key '+key,exact=True).tap()
        page.get_by_role('button',name='Done',exact=True).tap()
        page.get_by_label('Storage location',exact=True).select_option(location['entity_id'])
        page.get_by_role('button',name='Review equipment',exact=True).tap()
        page.get_by_role('button',name='Confirm add equipment',exact=True).tap()
        page.get_by_text('Equipment saved in Homebox · session ended',exact=True).wait_for(timeout=60000)
        native=next(e for e in client.entities() if e['name']=='Enrollment proof product');created.append(native['id']);native=client.entity(native['id'])
        assert native['manufacturer']=='Proof maker' and native['modelNumber']=='Proof model'
        assert native['serialNumber']=='ser123' and native['parent']['id']==location['entity_id']
        assert condition(native)=='Unreviewed'
        assert get('/api/session')['user'] is None
        assert not any(t['name'].startswith('Pending kiosk ') for t in native.get('tags',[]))
        assert not errors,errors
        page.screenshot(path=str(root/'work/enrollment-screen.png'))
        browser.close()
    result={'native_location_created':True,'native_template_catalog':True,'product_scan_prefill':True,'touch_serial_entry':True,'native_manufacturer_model_serial_preserved':True,'unreviewed_by_default':True,'badge_session_ended':True,'temporary_marker_removed':True,'browser_errors':errors}
    (root/'docs/enrollment-integration-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
finally:
    if badge:
        try:post('/badge/revoke',{'id':badge['id']})
        except Exception:pass
    # Keep native records referenced by the operational journal, archived as proof.
    for entity_id in created:
        entity=client.entity(entity_id);payload=update_payload(entity);payload['archived']=True;client.call('/api/v1/entities/'+entity_id,'PUT',payload)
    if template:
        # Native templates have no archive flag; retain named proof for journal provenance.
        pass
