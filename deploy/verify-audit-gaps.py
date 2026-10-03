import json,pathlib,sys
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path.insert(0,str(root/'work/hardware/python'))
from playwright.sync_api import sync_playwright
base='http://127.0.0.1:17749'
with sync_playwright() as pw:
 b=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);p=b.new_page(viewport={'width':800,'height':480},has_touch=True);errors=[];p.on('pageerror',lambda e:errors.append(str(e)))
 rows=[{'id':'11111111-1111-4111-8111-111111111111','name':'Search proof asset','assetId':'000-901','parent':{'name':'Proof shelf'},'entityType':{'name':'Aircraft'},'quantity':1,'archived':False,'condition':'Ready','manufacturer':'Proofmaker','modelNumber':'AirModel77','serialNumber':'SerialABC99','description':'Field platform','tags':[{'name':'Aerial'}]}, {'id':'22222222-2222-4222-8222-222222222222','name':'Bulk proof record','quantity':2,'archived':False,'condition':'Ready'}]
 p.route('**/api/stock',lambda route:route.fulfill(json=rows));p.route('**/api/custody',lambda route:route.fulfill(json=[]));p.goto(base);p.get_by_text('Homebox connected',exact=False).wait_for();p.get_by_role('button',name='Find Item',exact=False).tap();p.locator('#results').wait_for()
 for query in ['serialabc99','airmodel77','proofmaker','aircraft','aerial','field platform','000-901']:
  p.evaluate('(q)=>list(q)',query);assert p.locator('#results button').count()==1,query
 p.evaluate("list('')");p.get_by_role('button',name='Available only: Off',exact=True).tap();assert p.locator('#results button').count()==1
 p.route('**/api/system',lambda route:route.fulfill(json={'homebox_version':'0.26.2','homebox':'active','companion':'active','printer':{'connected':False},'camera_devices':0,'free_gb':0.2,'private_backups':1,'backup':None,'storage':{'level':'critical','message':'Storage critically low. Preserve inventory and recovery files.'}}))
 p.get_by_role('button',name='Admin',exact=True).tap();p.get_by_role('button',name='System status & backup',exact=True).tap();p.get_by_role('alert').get_by_text('Storage critically low.',exact=False).wait_for();p.get_by_text('Printer: Not ready',exact=True).wait_for();p.screenshot(path=str(root/'work/storage-warning-screen.png'))
 p.add_init_script("navigator.mediaDevices.getUserMedia=async()=>{throw new DOMException('No webcam','NotFoundError')}");p.reload();p.get_by_role('button',name='Scan',exact=True).tap();p.get_by_text('Webcam not found. Reconnect it, then try again.',exact=True).wait_for();p.get_by_role('button',name='Enter code',exact=True).tap();p.get_by_role('button',name='Key 1',exact=True).wait_for();assert not errors,errors;b.close()
result={'native_search_fields_supported':True,'available_excludes_nonindividual_quantity':True,'storage_warning_visible':True,'disconnected_printer_status_visible':True,'missing_camera_manual_fallback_reachable':True,'failure_injection':'Synthetic API/storage and browser media errors; physical hardware not disconnected'}
(root/'docs/audit-gaps-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))

