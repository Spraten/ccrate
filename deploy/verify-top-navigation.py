import pathlib,sys,json
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path.insert(0,str(root/'work/hardware/python'))
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);page=browser.new_page(viewport={'width':800,'height':480},has_touch=True);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:17749');page.get_by_text('Homebox connected · 0 assets',exact=True).wait_for();assert page.locator('header strong').count()==0
    for selector in ('#home-nav','#storage-nav','#layout-nav','#manual','#scan','#report-problem','#admin','#desktop'):
        box=page.locator(selector).bounding_box();assert box['height']>=44 and box['x']>=0 and box['x']+box['width']<=800
    page.locator('#layout-nav').tap();page.locator('svg[aria-label="Overhead workshop floor plan"]').wait_for();assert page.locator('#view>.toolbar').count()==0;assert page.locator('.workshop-scroll').bounding_box()['height']>260
    page.screenshot(path=str(root/'work/workshop-top-navigation-screen.png'));page.get_by_role('button',name='Rack A',exact=True).last.tap();page.get_by_role('button',name='→',exact=True).tap();page.locator('#storage-nav').tap();page.get_by_role('button',name='Add top-level location',exact=True).wait_for();assert page.locator('button').filter(has_text='← Home').count()==0
    page.locator('#layout-nav').tap();assert page.get_by_role('button',name='Save layout',exact=True).count()==1;page.locator('#home-nav').tap();page.get_by_role('button',name='Cancel',exact=True).tap();assert page.evaluate('workshopDirty')
    page.locator('#home-nav').tap();page.get_by_role('button',name='Confirm',exact=True).tap();page.get_by_role('heading',name='What do you need?',exact=True).wait_for();assert not page.evaluate('workshopDirty')
    page.locator('#admin').tap();page.get_by_role('heading',name='Administration',exact=True).wait_for();assert page.locator('#storage-nav').is_visible();page.locator('#home-nav').tap();page.locator('#report-problem').tap();page.get_by_role('heading',name='Report problem',exact=True).wait_for();page.locator('#home-nav').tap();assert not errors,errors;browser.close()
print(json.dumps({'shared_navigation_all_pages':True,'title_removed':True,'header_fits_800px':True,'larger_workshop_canvas':True,'dirty_edits_preserved_between_views':True,'discard_confirmation':True,'no_browser_errors':True}))
