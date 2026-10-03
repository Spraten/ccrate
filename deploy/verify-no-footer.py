import pathlib,sys,json
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path.insert(0,str(root/'work/hardware/python'))
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);page=browser.new_page(viewport={'width':800,'height':480},has_touch=True);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:17749');page.get_by_text('Homebox connected',exact=False).wait_for();assert page.locator('footer').count()==0;box=page.locator('#view').bounding_box();assert box['y']+box['height']==480
    page.locator('#layout-nav').tap();page.locator('svg[aria-label="Overhead workshop floor plan"]').wait_for();assert page.locator('.workshop-scroll').bounding_box()['height']>310
    page.evaluate("document.querySelector('#end-session').style.display='block'")
    for button in page.locator('header button').all():
        box=button.bounding_box();assert box['x']+box['width']<=800
    page.evaluate("status.textContent='Workshop layout saved'");page.locator('#status.visible').wait_for();page.locator('#home-nav').tap();assert page.locator('.dashboard-actions button').count()==6;assert not errors,errors;browser.close()
print(json.dumps({'bottom_bar_removed':True,'content_uses_full_height':True,'active_session_button_fits_top_bar':True,'brief_status_messages':True,'browser_errors':errors}))
