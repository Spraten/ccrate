import pathlib,sys,json
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path.insert(0,str(root/'work/hardware/python'))
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);page=browser.new_page(viewport={'width':800,'height':480},has_touch=True);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:17749');page.get_by_text('Homebox connected · 0 assets',exact=True).wait_for();page.locator('[data-action="Workshop"]').tap();page.wait_for_function('workshopState!==null');
    if page.get_by_role('button',name='Start from my sketch',exact=True).count():
        page.get_by_role('button',name='Start from my sketch',exact=True).tap();page.get_by_role('button',name='Save layout',exact=True).tap();page.wait_for_function('!workshopDirty')
    assert page.evaluate('workshopDraft.objects.length')==12
    if page.get_by_role('button',name='View layout',exact=True).count():page.get_by_role('button',name='View layout',exact=True).tap()
    page.screenshot(path=str(root/'work/workshop-overhead-screen.png'))
    page.get_by_role('button',name='Edit layout',exact=True).tap();page.get_by_role('button',name='Rack A',exact=True).last.tap();before=page.evaluate('workshopDraft.objects[0].x');page.get_by_role('button',name='→',exact=True).tap();assert page.evaluate('workshopDraft.objects[0].x')==before+.25;page.get_by_role('button',name='Rotate 90°',exact=True).tap();assert page.evaluate('workshopDraft.objects[0].rotation')==90
    page.get_by_role('button',name='Duplicate drawing',exact=True).tap();assert page.evaluate('workshopDraft.objects.length')==13;page.get_by_role('button',name='Remove drawing',exact=True).tap();page.get_by_role('button',name='Confirm',exact=True).tap();assert page.evaluate('workshopDraft.objects.length')==12
    page.get_by_role('button',name='Undo',exact=True).tap();assert page.evaluate('workshopDraft.objects.length')==13
    # Reload discards these test edits; the saved user sketch remains unchanged.
    page.reload();page.get_by_text('Homebox connected · 0 assets',exact=True).wait_for();page.locator('[data-action="Workshop"]').tap();page.locator('svg[aria-label="Overhead workshop floor plan"]').wait_for();assert page.evaluate('workshopDraft.objects.length')==12;assert page.evaluate('workshopDraft.objects[0].rotation')==0
    page.get_by_role('button',name='Storage',exact=True).tap();page.get_by_role('button',name='Add top-level location',exact=True).tap();page.get_by_label('Location name',exact=True).tap();page.get_by_role('dialog',name='Touchscreen search keyboard').wait_for();page.get_by_role('button',name='Done',exact=True).tap();page.get_by_role('button',name='Cancel',exact=True).tap()
    # Test the storage navigation with browser-only mocked native locations.
    locations=[{'id':'11111111-1111-4111-8111-111111111111','name':'XYZ','kind':'Rack','code':'XYZ','parent_id':None,'updated_at':'1'},{'id':'22222222-2222-4222-8222-222222222222','name':'Shelf 2','kind':'Shelf','code':'2','parent_id':'11111111-1111-4111-8111-111111111111','updated_at':'1'},{'id':'33333333-3333-4333-8333-333333333333','name':'Bin B','kind':'Bin','code':'B','parent_id':'22222222-2222-4222-8222-222222222222','updated_at':'1'}]
    page.evaluate('(locations)=>{workshopState.locations=locations;workshopStorageRender(null)}',locations);page.get_by_role('button',name='XYZ',exact=False).tap();page.get_by_role('button',name='Shelf 2',exact=False).tap();page.get_by_role('button',name='Bin B',exact=False).tap();page.get_by_text('XYZ / 2 / B',exact=True).wait_for();page.get_by_role('button',name='Move this location',exact=True).tap();assert page.get_by_label('Destination location').locator('option').count()==3;page.get_by_role('button',name='Cancel',exact=True).tap();assert not errors,errors
    browser.close()
print(json.dumps({'saved_user_sketch_objects':12,'touch_position_rotate_duplicate_undo':True,'reload_saved_layout':True,'native_inventory_unchanged':True,'touch_keyboard':True,'rack_shelf_bin_navigation_mocked':True,'browser_errors':errors}))
