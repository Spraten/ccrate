import base64,io,json,pathlib,sys,urllib.request
from uuid import uuid4
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path[:0]=[str(root/'ops'),str(root/'kiosk'),str(root/'work/hardware/python')]
from PIL import Image
import zxingcpp
from playwright.sync_api import sync_playwright
base='http://127.0.0.1:17749';entity='efb41b6f-0386-452b-af21-75da992e9677'
def post(path,data):return json.load(urllib.request.urlopen(urllib.request.Request(base+path,data=json.dumps(data).encode(),headers={'Origin':base,'Content-Type':'application/json'}),timeout=90))
label=post('/label/preview',{'entity_id':entity});image=Image.open(io.BytesIO(base64.b64decode(label['image'].split(',')[1])))
assert [c.text for c in zxingcpp.read_barcodes(image)]==['/item/'+entity];image.save(root/'work/asset-label-preview.png')
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);page=browser.new_page(viewport={'width':800,'height':480},has_touch=True);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base);page.get_by_text('Homebox connected',exact=False).wait_for();page.evaluate('(id)=>routeScan("/item/"+id)',entity);page.get_by_role('button',name='Label preview',exact=True).tap();page.get_by_role('button',name='Print one label',exact=True).wait_for();page.screenshot(path=str(root/'work/label-screen.png'))
    assert not errors,errors;browser.close()
# One explicitly authorized synthetic hardware proof. Never retry an uncertain print.
key=str(uuid4());result=post('/label/print',{'entity_id':entity,'request_key':key});repeat=post('/label/print',{'entity_id':entity,'request_key':key})
assert result['id']==repeat['id'] and result['status']=='completed'
result={'native_qr_preview_decoded':True,'touch_preview':True,'printer_completed_one_label':True,'same_request_did_not_reprint':True,'stock_mm':[40,30],'browser_errors':errors,'physical_legibility':'Awaiting user inspection; protocol completion is not a visual quality check'}
(root/'docs/label-integration-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
