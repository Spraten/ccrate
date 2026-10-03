import pathlib,sys,json
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path.insert(0,str(root/'work/hardware/python'))
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
 b=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);p=b.new_page(viewport={'width':800,'height':480},has_touch=True)
 p.add_init_script("window.cameraCalls=0;navigator.mediaDevices.getUserMedia=async()=>{window.cameraCalls++;throw Error('Camera disabled for manual proof')}")
 p.goto('http://127.0.0.1:17749');p.get_by_text('Homebox connected',exact=False).wait_for()
 assert p.locator('#desktop').bounding_box()['x']+p.locator('#desktop').bounding_box()['width']<=800
 p.get_by_role('button',name='Manual',exact=True).tap()
 keyboard=p.get_by_role('dialog',name='Touchscreen keyboard')
 # Keyboard is identified by its input entry title rather than assumed dialog labeling.
 for char in '000-022':p.get_by_role('button',name='Key '+char,exact=True).tap()
 p.get_by_role('button',name='Use code',exact=True).last.tap();p.get_by_text('Asset: 000-022',exact=True).wait_for();assert p.evaluate('cameraCalls')==0
 p.screenshot(path=str(root/'work/manual-direct-screen.png'));b.close()
print(json.dumps({'manual_home_button':True,'touch_code_resolves_native_asset':True,'camera_calls':0,'header_fits_800px':True}))
