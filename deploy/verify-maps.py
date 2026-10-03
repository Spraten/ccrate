import json,pathlib,sys,urllib.request
root=pathlib.Path('/home/user/Desktop/inventory-system')
sys.path.insert(0,str(root/'ops'));sys.path.insert(0,str(root/'work/hardware/python'))
from homebox import Homebox
from maps import ROOM_FIELD,OBJECT_FIELD
from native_fields import text_field
from playwright.sync_api import sync_playwright
client=Homebox(root);base='http://127.0.0.1:17749';created=[]
types=client.call('/api/v1/entity-types');types=types if isinstance(types,list) else types['items']
location_type=next(t for t in types if t['isLocation']);item_type=next(t for t in types if not t['isLocation'])
def create(name,parent=None,location=True):
    data={'name':name,'description':'Synthetic map acceptance fixture','quantity':0 if location else 1,'entityTypeId':(location_type if location else item_type)['id']}
    if parent:data['parentId']=parent
    entity=client.call('/api/v1/entities','POST',data);created.append(entity['id']);return entity
try:
    room=create('Workshop (map test)');shelf_a=create('Shelf A1 (map test)',room['id']);shelf_b=create('Shelf B2 (map test)',room['id']);asset=create('Drone (map test)',shelf_b['id'],False)
    original_asset=client.entity(asset['id']);original_shelf=client.entity(shelf_b['id'])
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True)
        page=browser.new_page(viewport={'width':800,'height':480},has_touch=True)
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base);page.get_by_text('Homebox connected',exact=False).wait_for()
        page.get_by_role('button',name='Admin',exact=True).tap();page.get_by_role('button',name='Workshop map editor',exact=True).tap()
        page.get_by_role('button',name='Use as room: '+room['name'],exact=True).tap();page.get_by_role('button',name='Save room',exact=True).tap()
        page.get_by_role('button',name='Place: '+shelf_a['name'],exact=True).tap()
        page.get_by_role('button',name='Column increase',exact=True).tap();page.get_by_role('button',name='Column increase',exact=True).tap()
        page.get_by_role('button',name='Row increase',exact=True).tap();page.get_by_role('button',name='Width increase',exact=True).tap()
        page.get_by_role('button',name='Save placement',exact=True).tap()
        page.get_by_role('button',name='Place: '+shelf_b['name'],exact=True).tap()
        for _ in range(6):page.get_by_role('button',name='Column increase',exact=True).tap()
        for _ in range(3):page.get_by_role('button',name='Row increase',exact=True).tap()
        page.get_by_role('button',name='Width increase',exact=True).tap();page.get_by_role('button',name='Save placement',exact=True).tap()
        page.get_by_role('button',name='Edit: '+shelf_b['name'],exact=True).wait_for()
        assert text_field(client.entity(room['id']),ROOM_FIELD)
        placement=json.loads(text_field(client.entity(shelf_b['id']),OBJECT_FIELD));assert placement['x']==6 and placement['y']==3 and placement['width']==2
        page.get_by_role('button',name='← Home',exact=True).tap();page.get_by_role('button',name='Browse Stock',exact=False).tap()
        page.get_by_role('button',name=asset['name'],exact=False).tap();page.get_by_role('button',name='Show on map',exact=True).tap()
        page.get_by_text('Highlighted shelf: '+shelf_b['name'],exact=True).wait_for()
        highlighted=page.locator('[data-location-id="'+shelf_b['id']+'"]');assert highlighted.get_attribute('data-highlighted')=='true'
        assert page.locator('[data-location-id="'+shelf_a['id']+'"]').get_attribute('data-highlighted')=='false'
        bounds=page.get_by_role('img',name=room['name']+' workshop layout').bounding_box();assert bounds['y']+bounds['height']<=430, bounds
        page.screenshot(path=str(root/'work/map-screen.png'))
        after_asset=client.entity(asset['id']);assert {k:v for k,v in after_asset.items() if k!='parent'}=={k:v for k,v in original_asset.items() if k!='parent'};assert after_asset['parent']['id']==original_asset['parent']['id']
        page.get_by_role('button',name='Admin',exact=True).tap();page.get_by_role('button',name='Workshop map editor',exact=True).tap()
        page.get_by_role('button',name='Edit room: '+room['name'],exact=True).tap();page.get_by_role('button',name='Edit: '+shelf_b['name'],exact=True).tap()
        page.get_by_role('button',name='Remove from map',exact=True).tap();page.get_by_role('button',name='Confirm removal',exact=True).tap()
        page.get_by_role('button',name='Place: '+shelf_b['name'],exact=True).wait_for()
        after=client.entity(shelf_b['id']);assert text_field(after,OBJECT_FIELD) is None
        for key in ('id','name','description','quantity','entityType','tags','fields'):assert after[key]==original_shelf[key],key
        assert after['parent']['id']==original_shelf['parent']['id']
        assert not errors,errors
        browser.close()
    result={'touch_room_configuration':True,'touch_position_and_resize':True,'native_fields_store_layout':True,'asset_exact_shelf_highlight':True,'map_fits_800x480':True,'asset_unchanged':True,'visual_removal_preserves_native_location':True,'browser_errors':errors,'fixture':'Synthetic native room/shelves; no real workshop layout assumed'}
    (root/'docs/map-integration-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
finally:
    for entity_id in reversed(created):client.call('/api/v1/entities/'+entity_id,'DELETE')
