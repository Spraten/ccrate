import io,json,os,pathlib,signal,subprocess,sys,time,urllib.request
r=pathlib.Path('/home/user/Desktop/inventory-system')
sys.path.insert(0,str(r/'work/hardware/python'))
from playwright.sync_api import sync_playwright
import qrcode
for entry in pathlib.Path('/proc').iterdir():
    if not entry.name.isdigit():continue
    try:
        args=(entry/'cmdline').read_bytes().split(b'\0')
        if args[0].endswith(b'python3') and (b'deploy/kiosk-server.py' in args or str(r/'deploy/kiosk-server.py').encode() in args):
            os.kill(int(entry.name),signal.SIGTERM)
    except (OSError,IndexError):pass
time.sleep(.5)
subprocess.Popen(['python3',str(r/'deploy/kiosk-server.py')],cwd=r,stdout=(r/'work/kiosk-server.log').open('ab'),stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
time.sleep(.5)
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
    page.get_by_role('textbox').fill('Demo Drone')
    page.get_by_role('button',name='Demo Drone 001',exact=False).click()
    assert page.get_by_role('heading',name='Demo Drone 001').is_visible()
    page.get_by_role('button',name='← Home').click()
    page.get_by_role('button',name='Scan',exact=True).click()
    page.get_by_text('Hold a Homebox QR code',exact=False).wait_for()
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
result={'decoder_native_qr':True,'native_asset_resolution':True,'browse_search_detail':True,'camera_start_cancel':True,'scan_opens_detail':True,'touch_exit_cancel':True,'browser_errors':errors,'camera_test':'synthetic browser device; physical scan acceptance still required'}
(r/'docs/scan-integration-results.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
