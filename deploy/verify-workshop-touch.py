import pathlib,sys,json
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path.insert(0,str(root/'work/hardware/python'))
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);page=browser.new_page(viewport={'width':800,'height':480},has_touch=True);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:17749');page.locator('#layout-nav').tap();page.locator('svg[aria-label="Overhead workshop floor plan"]').wait_for();assert page.locator('#workshop-details').is_hidden();page.get_by_role('button',name='Show workshop sidebar',exact=True).tap();assert page.locator('#workshop-details').is_visible();page.get_by_role('button',name='Hide workshop sidebar',exact=True).tap();assert page.locator('#workshop-details').is_hidden()
    page.get_by_role('button',name='Show view controls',exact=True).tap();page.get_by_role('button',name='Pan right',exact=True).tap();assert page.evaluate('workshopPanX')==-70;page.get_by_role('button',name='Fit',exact=True).tap();assert page.evaluate('workshopPanX')==0;page.get_by_role('button',name='Hide view controls',exact=True).tap()
    page.locator('#layout-nav').tap();page.locator('[data-workshop-object]').first.tap();assert page.locator('#workshop-details').is_visible();page.get_by_role('button',name='Hide workshop sidebar',exact=True).tap()
    cdp=page.context.new_cdp_session(page)
    def touch(kind,points):cdp.send('Input.dispatchTouchEvent',{'type':kind,'touchPoints':[{'id':i,'x':x,'y':y} for i,x,y in points]})
    touch('touchStart',[(1,300,260)]);touch('touchMove',[(1,360,290)]);touch('touchEnd',[]);assert page.evaluate('workshopPanX')==60
    touch('touchStart',[(1,250,260),(2,450,260)]);touch('touchMove',[(1,200,260),(2,500,260)]);touch('touchEnd',[]);assert page.evaluate('workshopZoom')>1.4;assert not page.evaluate('workshopDirty');assert not errors,errors;page.screenshot(path=str(root/'work/workshop-touch-screen.png'));browser.close()
print(json.dumps({'collapsible_workshop_sidebar':True,'directional_navigation':True,'real_browser_touch_drag':True,'real_browser_pinch_zoom':True,'layout_not_modified_by_navigation':True,'browser_errors':errors}))
