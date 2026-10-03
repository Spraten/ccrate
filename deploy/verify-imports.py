import pathlib,sys,json,time
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path[:0]=[str(root/'work/hardware/python'),str(root/'ops')]
from playwright.sync_api import sync_playwright
from homebox import Homebox
from conditions import condition
from native_fields import text_field
stamp=str(int(time.time()));csv='Name,Serial,ID,Condition\n"Demo CSV drill, blue",CSV-'+stamp+'-1,CSV-'+stamp+'-1,Needs repair\nDemo CSV driver,CSV-'+stamp+'-2,CSV-'+stamp+'-2,Unknown\n'
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);page=browser.new_page(viewport={'width':800,'height':480},has_touch=True);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:17749');page.get_by_text('Homebox connected',exact=False).wait_for();page.locator('#admin').tap();page.get_by_role('button',name='Import CSV',exact=True).tap();page.get_by_label('CSV file').set_input_files({'name':'demo-import.csv','mimeType':'text/csv','buffer':csv.encode()});page.get_by_role('button',name='Next: map columns',exact=True).tap();page.get_by_role('heading',name='Map CSV columns').wait_for()
    loc=page.get_by_label('Default location when CSV location is empty');loc.select_option(index=1);page.get_by_label('Default category when CSV category is empty').select_option(index=1);page.get_by_role('button',name='Next: review items',exact=True).tap();page.get_by_role('heading',name='Review item 1 of 2').wait_for()
    page.get_by_label('Equipment name',exact=True).tap();page.get_by_role('button',name='Clear',exact=True).tap()
    for char in 'demo csv drill':
        page.get_by_role('button',name='Space' if char==' ' else 'Key '+char.upper(),exact=True).tap()
    page.get_by_role('button',name='Done',exact=True).tap();page.get_by_label('Condition',exact=True).select_option('Broken');page.get_by_role('button',name='Save review & next',exact=True).tap();page.get_by_role('heading',name='Review item 2 of 2').wait_for();page.get_by_role('button',name='Save review & next',exact=True).tap();page.wait_for_function("importBatch.items[1].status==='reviewed'",timeout=60000);page.get_by_role('button',name='Batch summary',exact=True).tap();page.get_by_role('button',name='Confirm: create 2 reviewed items',exact=True).wait_for();page.screenshot(path=str(root/'work/import-summary-screen.png'))
    batch_id=page.evaluate('importBatch.id');page.get_by_role('button',name='Confirm: create 2 reviewed items',exact=True).tap();page.get_by_text('2 of 2 completed. Saved progress is retained.',exact=True).wait_for(timeout=120000);page.get_by_role('button',name='Return to batch',exact=True).tap();page.get_by_role('heading',name='Label queue',exact=True).wait_for();page.get_by_role('button',name='Preview',exact=True).first.tap();page.locator('img[alt^="Label for"]').wait_for();page.screenshot(path=str(root/'work/import-label-queue-screen.png'))
    batch=page.evaluate('importBatch');client=Homebox(root)
    for index,row in enumerate(batch['items']):
        entity=client.entity(row['entity_id']);assert text_field(entity,'Import external ID')=='CSV-'+stamp+'-'+str(index+1);assert entity['serialNumber']=='CSV-'+stamp+'-'+str(index+1);assert condition(entity)==('Broken' if index==0 else 'Unreviewed')
    assert batch['items'][0]['input']['name']=='demo csv drill'
    # Reopening in a fresh page resolves the existing batch rather than creating copies.
    page.reload();page.get_by_text('Homebox connected',exact=False).wait_for();page.evaluate("async id=>{importBatch=await api('/imports/get',{id});await importReview(0)}",batch_id);page.get_by_role('heading',name='Review item 1 of 2').wait_for();assert page.get_by_text('Homebox asset ',exact=False).count()
    duplicate=page.evaluate("async csv=>{const b=await api('/imports/upload',{csv,source:'Asset Manager',filename:'duplicate-test.csv'});return api('/imports/map',{id:b.id,mapping:{name:'Name',serial:'Serial',external_id:'ID',source_condition:'Condition'},location_id:importBatch.items[0].input.location_id,type_id:importBatch.items[0].input.type_id})}",csv)
    assert all(any('Already in Homebox' in error for error in row['errors']) for row in duplicate['items']);assert not errors,errors
    browser.close()
print(json.dumps({'touchscreen_edit':True,'created':2,'native_provenance':True,'blocked_conditions_preserved':True,'resume':True,'duplicate_import_blocked':True,'label_queue_and_preview':True,'browser_errors':errors,'batch_id':batch_id}))

