import pathlib,sys,json,urllib.request,io
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path.insert(0,str(root/'work/hardware/python'))
import qrcode
from playwright.sync_api import sync_playwright
stream=io.BytesIO();qrcode.make('OUTLINE-TEST-ONLY').save(stream,format='PNG')
req=urllib.request.Request('http://127.0.0.1:17749/decode',data=stream.getvalue(),headers={'Origin':'http://127.0.0.1:17749'})
with urllib.request.urlopen(req) as response:decoded=json.load(response)
assert decoded['codes']==['OUTLINE-TEST-ONLY'];assert len(decoded['detections'][0]['corners'])==4
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream'])
    page=browser.new_page(viewport={'width':800,'height':480},user_agent='Mozilla/5.0 (X11; Linux aarch64) Chrome/152.0.0.0');errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.route('**/decode',lambda route:route.fulfill(status=200,content_type='application/json',body=json.dumps(decoded)))
    page.route('**/scan',lambda route:route.fulfill(status=200,content_type='application/json',body='{"reason":"Test outline"}'))
    page.goto('http://127.0.0.1:17749');page.get_by_role('button',name='Scan',exact=True).click();page.get_by_text('Test outline',exact=True).wait_for()
    slider=page.get_by_label('Pi camera focus: far to near');assert slider.is_visible();box=slider.bounding_box();assert box['y']+box['height']<=480,box
    green=page.evaluate("()=>{const c=document.querySelector('canvas[style*=absolute]'),pixels=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let n=0;for(let i=0;i<pixels.length;i+=4)if(pixels[i]===25&&pixels[i+1]===216&&pixels[i+2]===120)n++;return n}")
    assert green>100;assert not errors,errors
    page.get_by_role('button',name='Cancel scan',exact=True).click();browser.close()
print(json.dumps({'decoder_corners':True,'green_detection_outline':True,'touchscreen_focus_controls_fit':True,'browser_errors':errors}))
