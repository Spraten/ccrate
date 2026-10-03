import pathlib,sys,json
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path.insert(0,str(root/'work/hardware/python'))
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);page=browser.new_page(viewport={'width':800,'height':480},has_touch=True);errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto('http://127.0.0.1:17749');page.get_by_text('Homebox connected',exact=False).wait_for()
    assert page.locator('.action').count()==6
    assert page.locator('.action').filter(has_text='Report Problem').count()==0
    warning=page.get_by_role('button',name='Report a problem',exact=True);admin=page.locator('#admin');assert warning.bounding_box()['x']<admin.bounding_box()['x']
    assert page.locator('#desktop').bounding_box()['x']+page.locator('#desktop').bounding_box()['width']<=800
    page.screenshot(path=str(root/'work/workshop-home-screen.png'))
    warning.tap();page.get_by_role('heading',name='Report problem',exact=True).wait_for();page.get_by_text('Scan your badge to report an equipment issue.',exact=True).wait_for()
    page.get_by_role('button',name='← Home',exact=True).tap();page.get_by_role('button',name='Workshop Explore locations and equipment',exact=True).tap()
    page.locator('svg[aria-label$="workshop layout"]').wait_for();page.screenshot(path=str(root/'work/workshop-map-screen.png'));mapped=page.locator('[data-location-id]');assert mapped.count()>0
    mapped.first.tap();page.get_by_text('Homebox location',exact=True).wait_for();page.get_by_role('heading',name='Equipment here',exact=True).wait_for()
    assert not errors,errors;browser.close()
print(json.dumps({'six_home_tiles':True,'caution_next_to_admin':True,'header_fits_800px':True,'problem_badge_flow':True,'workshop_map':True,'tap_location_equipment':True,'browser_errors':errors}))
