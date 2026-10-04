import pathlib,sys,json
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path.insert(0,str(root/'work/hardware/python'))
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1366,'height':768});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:17749');page.locator('#layout-nav').click();page.locator('#workshop-details').wait_for()
    assert page.locator('#workshop-details').is_visible()
    assert page.locator('.workshop-details-tab').is_hidden()
    side=page.locator('#workshop-details').bounding_box();canvas=page.locator('.workshop-canvas').bounding_box()
    assert side['x'] >= canvas['x']+canvas['width']
    page.get_by_role('button',name='Room settings',exact=True).click()
    field=page.locator('.workshop-dialog input').first
    assert not field.evaluate('(e)=>e.readOnly')
    field.fill('Keyboard test');assert field.input_value()=='Keyboard test'
    page.get_by_role('button',name='Cancel',exact=True).click()
    assert not page.evaluate('workshopDirty')
    assert not errors,errors
    page.screenshot(path=str(root/'work/laptop-workshop-screen.png'))
    browser.close()
print(json.dumps({'desktop_side_by_side':True,'physical_keyboard':True,'no_saved_changes':True,'browser_errors':errors}))
