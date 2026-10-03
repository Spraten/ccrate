import json,pathlib,sys
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path.insert(0,str(root/'work/hardware/python'))
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);page=browser.new_page(viewport={'width':800,'height':480},permissions=['camera'])
    page.goto('http://127.0.0.1:17749/');page.get_by_role('button',name='Scan',exact=True).click();page.get_by_text('Hold your badge or a Homebox QR code',exact=False).wait_for(timeout=20000)
    page.wait_for_function("scanStream&&document.querySelector('video').readyState>=2",timeout=20000)
    settings=page.evaluate('scanStream.getVideoTracks()[0].getSettings()');page.get_by_role('button',name='Cancel scan',exact=True).click();assert page.evaluate('scanStream===null');browser.close()
    result={'physical_camera_stream_started':True,'video_frame_ready':True,'width':settings['width'],'height':settings['height'],'cancel_stopped_stream':True,'frames_saved':False,'physical_qr_in_front_of_camera':'Still needs user placement and scan acceptance'}
    (root/'docs/real-camera-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
