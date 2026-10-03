import pathlib,sys,json
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path.insert(0,str(root/'work/hardware/python'))
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);page=browser.new_page(viewport={'width':800,'height':480},has_touch=True);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:17749');page.get_by_text('Homebox connected · 0 assets',exact=True).wait_for()
    assert page.locator('.dashboard-actions .action').count()==6
    assert page.evaluate("view.scrollHeight<=view.clientHeight"),'Home dashboard needs scrolling'
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"),'Horizontal overflow'
    for button in page.locator('header button,.dashboard-actions button').all():
        box=button.bounding_box();assert box['height']>=44 and box['width']>=44
    page.screenshot(path=str(root/'work/dashboard-redesign-screen.png'))
    for action,heading in [('Check Out','Check out equipment'),('Return','Return equipment'),('Workshop','Workshop map')]:
        page.locator('[data-action="'+action+'"]').tap()
        page.wait_for_timeout(300)
        assert not page.locator('#view').evaluate('(el)=>el.classList.contains("dashboard")')
        page.locator('#home-nav').tap()
    page.get_by_role('button',name='Report a problem',exact=True).tap();page.get_by_role('heading',name='Report problem',exact=True).wait_for();page.locator('#home-nav').tap()
    page.locator('#manual').tap();page.get_by_role('dialog',name='Touchscreen search keyboard').wait_for();page.get_by_role('button',name='Use code',exact=True).last.wait_for()
    page.reload();page.get_by_text('Homebox connected · 0 assets',exact=True).wait_for();page.set_viewport_size({'width':480,'height':800});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');page.screenshot(path=str(root/'work/dashboard-redesign-mobile.png'));assert not errors,errors
    browser.close()
print(json.dumps({'six_actions':True,'no_home_scroll_800x480':True,'touch_targets_44px':True,'transaction_navigation':True,'workshop_and_problem':True,'manual_keyboard':True,'mobile_no_horizontal_overflow':True,'inventory_stays_empty':True,'browser_errors':errors}))
