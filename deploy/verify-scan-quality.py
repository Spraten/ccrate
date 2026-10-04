import pathlib,sys,json,io
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path.insert(0,str(root/'work/hardware/python'))
from playwright.sync_api import sync_playwright
from PIL import Image
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream'])
    page=browser.new_page(viewport={'width':800,'height':480});errors=[];page.on('pageerror',lambda error:errors.append(str(error)));frames=[]
    def decode(route):
        frame=Image.open(io.BytesIO(route.request.post_data_buffer));frames.append(frame.size)
        route.fulfill(status=200,content_type='application/json',body='{"codes":[]}')
    page.route('**/decode',decode)
    page.goto('http://127.0.0.1:17749');page.get_by_role('button',name='Scan',exact=True).click();page.wait_for_function("scanStream&&document.querySelector('video').readyState>=2")
    settings=page.evaluate('scanStream.getVideoTracks()[0].getSettings()')
    page.wait_for_timeout(1200);assert frames;assert all(size==(settings['width'],settings['height']) for size in frames)
    assert settings['width']>=1280
    page.get_by_role('button',name='Cancel scan',exact=True).click();assert page.evaluate('scanStream===null');assert not errors,errors
    browser.close()
print(json.dumps({'capture_size':frames[0],'native_frame_dimensions_preserved':True,'cancel_stops_camera':True,'browser_errors':errors,'physical_focus_acceptance':'pending'}))
