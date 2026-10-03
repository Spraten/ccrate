import json,pathlib,sys,time,urllib.request
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path.insert(0,str(root/'work/hardware/python'))
from playwright.sync_api import sync_playwright
base='http://127.0.0.1:17749'
with sync_playwright() as pw:
 b=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);p=b.new_page(viewport={'width':800,'height':480},has_touch=True);errors=[];p.on('pageerror',lambda e:errors.append(str(e)));p.goto(base);p.get_by_text('Homebox connected',exact=False).wait_for();p.get_by_role('button',name='Admin',exact=True).tap();p.get_by_role('button',name='Locations',exact=True).tap();p.get_by_role('button',name='Demo Shelf A1',exact=True).tap();p.get_by_role('button',name='Label preview',exact=True).tap();p.get_by_role('button',name='Print one label',exact=True).wait_for();p.screenshot(path=str(root/'work/location-label-screen.png'));p.get_by_role('button',name='Admin',exact=True).tap();p.get_by_role('button',name='System status & backup',exact=True).tap();p.get_by_role('button',name='Create recovery backup',exact=True).tap();p.get_by_role('button',name='Confirm backup',exact=True).tap();
 deadline=time.time()+100
 while time.time()<deadline:
  time.sleep(2)
  try:
   state=json.load(urllib.request.urlopen(base+'/api/system',timeout=3))['backup']
   if state and state['status']=='completed':break
  except Exception:pass
 else:raise AssertionError('Backup did not complete')
 assert not errors,errors;b.close()
result={'location_label_reachable_from_admin':True,'touch_backup_completed':True,'external_backup_copy':False};(root/'docs/final-touch-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))

