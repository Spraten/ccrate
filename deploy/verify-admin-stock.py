import io,json,pathlib,sys,urllib.request
from uuid import uuid4
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path[:0]=[str(root/'ops'),str(root/'kiosk'),str(root/'work/hardware/python')]
from homebox import Homebox
from native_fields import update_payload
from conditions import set_condition
from attachments import upload
from PIL import Image
from playwright.sync_api import sync_playwright
client=Homebox(root);native=client.call('/api/v1/users/self')['item'];base='http://127.0.0.1:17749';asset=None;category=None;badge=None
def post(path,data):return json.load(urllib.request.urlopen(urllib.request.Request(base+path,data=json.dumps(data).encode(),headers={'Origin':base,'Content-Type':'application/json'}),timeout=60))
try:
    suffix=str(uuid4())[:8];name='category '+suffix
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--use-fake-device-for-media-stream']);page=browser.new_page(viewport={'width':800,'height':480},has_touch=True,permissions=['camera']);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base);page.get_by_text('Homebox connected',exact=False).wait_for();page.get_by_role('button',name='Admin',exact=True).tap();page.get_by_role('button',name='Equipment categories',exact=True).tap();page.get_by_role('button',name='Create category',exact=True).tap();page.get_by_label('Category name',exact=True).tap()
        for char in name:page.get_by_role('button',name='Space' if char==' ' else 'Key '+char.upper(),exact=True).tap()
        page.get_by_role('button',name='Done',exact=True).tap();page.get_by_role('button',name='Confirm category',exact=True).tap();page.get_by_text('Category saved in Homebox',exact=True).wait_for()
        category=next(t for t in client.call('/api/v1/entity-types') if t['name']==name)
        asset=client.call('/api/v1/entities','POST',{'name':'Admin stock proof '+suffix,'quantity':1,'entityTypeId':category['id'],'parentId':'9b7f1f98-42f6-4ea5-aaf3-079b4d825499','manufacturer':'Proof manufacturer'});set_condition(client,asset['id'],'Ready')
        image=Image.new('RGB',(64,48),'#245c89');blob=io.BytesIO();image.save(blob,format='JPEG');upload(client,asset['id'],'admin-proof-photo.jpg',blob.getvalue())
        page.reload();page.get_by_text('Homebox connected',exact=False).wait_for();page.get_by_role('button',name='Browse Stock',exact=False).tap();page.get_by_label('Category filter',exact=True).select_option(name);page.get_by_label('Condition filter',exact=True).select_option('Ready');assert page.locator('#results button').count()==1;page.get_by_role('button',name=asset['name'],exact=False).tap();page.get_by_role('button',name='Photos & files',exact=True).tap();page.get_by_role('img',name='admin-proof-photo.jpg',exact=True).wait_for();page.wait_for_function("document.querySelector('main img').naturalWidth===64")
        badge=post('/badge/issue',{'user_id':native['id']});post('/scan',{'code':badge['code']});session=json.load(urllib.request.urlopen(base+'/api/session'));post('/problem/confirm',{'request_key':str(uuid4()),'session_generation':session['generation'],'session_instance':session['instance'],'input':{'entity_id':asset['id'],'state':'Maintenance','note':'Proof maintenance task'}})
        page.evaluate('updateIdentity()')
        page.evaluate('(id)=>routeScan("/item/"+id)',asset['id']);page.get_by_role('button',name='Maintenance & inspections',exact=True).tap();page.get_by_role('button',name='Mark entry completed',exact=True).tap();page.get_by_role('button',name='Confirm completed work',exact=True).tap();page.get_by_text('Native maintenance completed',exact=True).wait_for();assert all(e['completedDate'] for e in client.call('/api/v1/entities/'+asset['id']+'/maintenance'))
        page.evaluate('(id)=>routeScan("/item/"+id)',asset['id']);page.get_by_role('button',name='Review condition',exact=True).tap();page.get_by_role('button',name='Ready',exact=True).tap();page.get_by_role('button',name='Confirm Ready',exact=True).tap();page.get_by_text('Condition: Ready',exact=True).wait_for()
        page.get_by_role('button',name='Scan',exact=True).tap();page.get_by_role('button',name='Enter code',exact=True).tap()
        for char in asset['assetId']:page.get_by_role('button',name='Key '+char,exact=True).tap()
        page.get_by_role('dialog',name='Touchscreen search keyboard').get_by_role('button',name='Use code',exact=True).tap();page.get_by_role('heading',name=asset['name'],exact=True).wait_for();assert page.evaluate('scanStream===null')
        page.evaluate('(code)=>routeScan(code)',badge['code']);page.get_by_role('button',name='Add Equipment',exact=False).tap();page.get_by_role('button',name='Scan serial number',exact=True).tap();page.evaluate('(code)=>routeScan(code)','PROOF-SERIAL-123');page.get_by_label('Serial number',exact=True).wait_for();assert page.get_by_label('Serial number',exact=True).input_value()=='PROOF-SERIAL-123'
        post('/session/end',{});page.evaluate('updateIdentity()');page.get_by_role('button',name='Browse Stock',exact=False).tap();page.get_by_label('Category filter',exact=True).select_option(name);page.screenshot(path=str(root/'work/stock-screen.png'));page.get_by_role('button',name='← Home',exact=True).tap();page.screenshot(path=str(root/'work/home-screen.png'))
        assert not errors,errors;browser.close()
    result={'touch_native_category_creation':True,'native_stock_category_condition_filters':True,'native_photo_viewer':True,'touch_native_maintenance_completion':True,'explicit_ready_inspection_journaled':True,'manual_asset_code_touch_fallback':True,'serial_scan_preserves_case':True,'browser_errors':errors}
    (root/'docs/admin-stock-integration-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
finally:
    if badge:post('/badge/revoke',{'id':badge['id']})
    if asset:
        payload=update_payload(client.entity(asset['id']));payload['archived']=True;client.call('/api/v1/entities/'+asset['id'],'PUT',payload)
