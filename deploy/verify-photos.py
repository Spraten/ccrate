import base64,io,json,pathlib,sys,urllib.request
from uuid import uuid4
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path[:0]=[str(root/'ops'),str(root/'kiosk'),str(root/'work/hardware/python')]
from homebox import Homebox
from native_fields import update_payload
from playwright.sync_api import sync_playwright
from PIL import Image
client=Homebox(root);native=client.call('/api/v1/users/self')['item'];base='http://127.0.0.1:17749';assets=[];badge=None
def post(path,data):return json.load(urllib.request.urlopen(urllib.request.Request(base+path,data=json.dumps(data).encode(),headers={'Origin':base,'Content-Type':'application/json'}),timeout=60))
try:
    kind=next(t for t in client.call('/api/v1/entity-types') if not t['isLocation'])
    asset=client.call('/api/v1/entities','POST',{'name':'Photo proof '+str(uuid4())[:8],'quantity':1,'entityTypeId':kind['id'],'parentId':'9b7f1f98-42f6-4ea5-aaf3-079b4d825499'});assets.append(asset['id'])
    badge=post('/badge/issue',{'user_id':native['id']});post('/scan',{'code':badge['code']})
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--use-fake-device-for-media-stream']);page=browser.new_page(viewport={'width':800,'height':480},has_touch=True,permissions=['camera']);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base);page.get_by_text(native['name'],exact=True).wait_for();page.get_by_role('button',name='Report Problem',exact=False).tap();page.get_by_role('button',name=asset['name'],exact=True).tap();page.get_by_role('button',name='Add equipment photo',exact=True).tap();page.get_by_role('button',name='Capture photo',exact=True).wait_for();page.get_by_role('button',name='Cancel photo',exact=True).tap();assert page.evaluate('photoStream===null')
        page.get_by_role('button',name='Add equipment photo',exact=True).tap();page.wait_for_function("!Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Capture photo').disabled");page.get_by_role('button',name='Capture photo',exact=True).tap();assert page.evaluate('photoStream===null');page.get_by_role('img',name='Equipment photo to save in Homebox',exact=True).wait_for()
        page.get_by_label('Describe the problem',exact=True).tap()
        for char in 'PHOTO':page.get_by_role('button',name='Key '+char,exact=True).tap()
        page.get_by_role('button',name='Done',exact=True).tap();page.screenshot(path=str(root/'work/photo-screen.png'));page.get_by_role('button',name='Review report',exact=True).tap();page.get_by_role('button',name='Confirm problem report',exact=True).tap();page.get_by_text('Problem saved in Homebox · session ended',exact=True).wait_for(timeout=60000)
        assert not errors,errors;browser.close()
    photo=next(a for a in client.entity(asset['id'])['attachments'] if a['type']=='photo')
    request=urllib.request.Request(client.base+'/api/v1/entities/'+asset['id']+'/attachments/'+photo['id'],headers={'Authorization':'Bearer '+client.token})
    raw=urllib.request.urlopen(request).read();assert Image.open(io.BytesIO(raw)).size==(640,480)
    post('/scan',{'code':badge['code']});session=json.load(urllib.request.urlopen(base+'/api/session'))
    created=post('/enroll/confirm',{'request_key':str(uuid4()),'session_generation':session['generation'],'session_instance':session['instance'],'input':{'name':'Enrollment photo proof '+str(uuid4())[:8],'location_id':'9b7f1f98-42f6-4ea5-aaf3-079b4d825499','photo':'data:image/jpeg;base64,'+base64.b64encode(raw).decode()}});assets.append(created['entity_id']);assert any(a['type']=='photo' for a in client.entity(created['entity_id'])['attachments'])
    result={'camera_preview_cancel_stops_stream':True,'deliberate_capture_stops_stream':True,'native_problem_photo_verified':True,'native_enrollment_photo_verified':True,'native_photo_size':[640,480],'browser_errors':errors,'camera_source':'Synthetic Chromium device; physical webcam acceptance remains outstanding'}
    (root/'docs/photo-integration-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
finally:
    if badge:post('/badge/revoke',{'id':badge['id']})
    for key in assets:
        payload=update_payload(client.entity(key));payload['archived']=True;client.call('/api/v1/entities/'+key,'PUT',payload)
