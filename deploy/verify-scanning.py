import io,json,os,pathlib,signal,subprocess,sys,time,urllib.request
r=pathlib.Path('/home/user/Desktop/inventory-system')
sys.path.insert(0,str(r/'work/hardware/python'))
from playwright.sync_api import sync_playwright
import qrcode
subprocess.run(['systemctl','--user','restart','homebox-companion.service'],check=True)
for attempt in range(40):
    try:
        urllib.request.urlopen('http://127.0.0.1:17749/',timeout=1).close();break
    except OSError:time.sleep(.25)
base='http://127.0.0.1:17749'
items=json.load(urllib.request.urlopen(base+'/api/inventory',timeout=15))
asset=next(e for e in items if e['name']=='Demo Drone 001')
code='http://homebox.local/a/'+asset['assetId']
def post(path,body,mime):
    req=urllib.request.Request(base+path,data=body,headers={'Origin':base,'Content-Type':mime})
    return json.load(urllib.request.urlopen(req,timeout=15))
buffer=io.BytesIO();qrcode.make(code).save(buffer,format='PNG')
assert code in post('/decode',buffer.getvalue(),'image/png')['codes']
assert post('/scan',json.dumps({'code':code}).encode(),'application/json')['entity']['id']==asset['id']
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--use-fake-device-for-media-stream'])
    ctx=browser.new_context(viewport={'width':800,'height':480},permissions=['camera'],has_touch=True)
    page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base);page.wait_for_load_state('networkidle')
    page.get_by_text('Homebox connected',exact=False).wait_for()
    page.get_by_role('button',name='Browse Stock').click()
    page.get_by_role('textbox').tap()
    for letter in 'DEMO':page.get_by_role('button',name='Key '+letter,exact=True).tap()
    page.get_by_role('button',name='Space',exact=True).tap()
    for letter in 'DRONEX':page.get_by_role('button',name='Key '+letter,exact=True).tap()
    page.get_by_role('button',name='Backspace',exact=True).tap()
    assert page.get_by_role('textbox').input_value()=='demo drone'
    bounds=page.get_by_role('button',name='Backspace',exact=True).bounding_box()
    assert bounds['y']+bounds['height']<=480
    page.get_by_role('button',name='Show results',exact=True).tap()
    assert not page.get_by_role('dialog',name='Touchscreen search keyboard').count()
    page.get_by_role('button',name='Demo Drone 001',exact=False).click()
    assert page.get_by_role('heading',name='Demo Drone 001').is_visible()
    page.get_by_role('button',name='← Home').click()
    page.get_by_role('button',name='Scan',exact=True).click()
    page.get_by_text('Hold your badge or a Homebox QR code',exact=False).wait_for()
    assert page.evaluate('scanStream.getVideoTracks()[0].readyState')=='live'
    page.get_by_role('button',name='Cancel scan').click()
    assert page.evaluate('scanStream===null')
    page.evaluate('(code)=>routeScan(code)',code)
    assert page.get_by_role('heading',name='Demo Drone 001').is_visible()
    page.get_by_role('button',name='Desktop',exact=True).click()
    page.get_by_role('button',name='Stay here').click()
    assert not page.get_by_text('Return to the desktop?').is_visible()
    page.screenshot(path=str(r/'work/scanner-screen.png'))
    assert not errors,errors
    browser.close()
result={'decoder_native_qr':True,'native_asset_resolution':True,'browse_search_detail':True,'touchscreen_keyboard_search':True,'keyboard_fits_800x480':True,'camera_start_cancel':True,'scan_opens_detail':True,'touch_exit_cancel':True,'browser_errors':errors,'camera_test':'synthetic browser device; physical scan acceptance still required'}
(r/'docs/scan-integration-results.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
