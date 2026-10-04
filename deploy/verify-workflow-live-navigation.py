"""Live navigation only; block every operation that could mutate inventory/custody."""
import pathlib,sys,json
from urllib.parse import urlsplit
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path.insert(0,str(root/'work/hardware/python'))
from playwright.sync_api import sync_playwright
steps=[];errors=[];blocked=[]
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':800,'height':480},has_touch=True);page.set_default_timeout(20000)
 page.on('pageerror',lambda e:errors.append(str(e)))
 def protect(route):
  if route.request.method=='POST' and urlsplit(route.request.url).path not in ('/workshop/get','/imports/list','/imports/get','/session/activity','/scan/cancel'):
   blocked.append(urlsplit(route.request.url).path);route.abort();return
  route.continue_()
 page.route('**/*',protect)
 page.goto('http://127.0.0.1:17749');page.wait_for_load_state('networkidle');assert page.locator('[data-action]').count()==6
 for title in ['Check Out','Return','Find Item','Browse Stock','Workshop','Add Equipment']:
  page.locator('[data-action="'+title+'"]').tap();page.wait_for_load_state('networkidle');assert page.locator('#view').text_content().strip();assert page.get_by_role('button',name='Home',exact=True).is_visible();page.locator('#home-nav').tap();assert page.locator('[data-action]').count()==6;steps.append(title+' and Home')
 page.locator('#manual').tap();page.get_by_role('dialog').get_by_role('button',name='Back',exact=True).tap();assert page.locator('[data-action]').count()==6;steps.append('Manual entry Back')
 page.locator('#admin').tap();page.wait_for_load_state('networkidle');page.get_by_role('button',name='System status & backup',exact=True).tap();page.get_by_role('button',name='Refresh status',exact=True).wait_for();page.get_by_role('button',name='Back',exact=True).tap();page.get_by_role('heading',name='Administration',exact=True).wait_for();page.get_by_role('button',name='Review interrupted operations',exact=True).tap();page.wait_for_load_state('networkidle');page.get_by_role('button',name='Back',exact=True).tap();page.locator('#home-nav').tap();steps.append('Admin, System, Recovery and Back')
 page.locator('#storage-nav').tap();page.wait_for_load_state('networkidle');page.get_by_role('button',name='Add top-level location',exact=True).wait_for();page.locator('#home-nav').tap();steps.append('Live Storage and Home')
 editor=browser.new_page(viewport={'width':1280,'height':800});editor.on('pageerror',lambda e:errors.append(str(e)));editor.route('**/*',protect);editor.goto('http://127.0.0.1:17749/?mode=editor');editor.wait_for_load_state('networkidle');assert page.evaluate('clientId')!=editor.evaluate('clientId');editor.locator('#desktop').click();editor.get_by_role('heading',name='Disconnect laptop',exact=True).wait_for();steps.append('Separate editor client and local disconnect')
 browser.close()
assert not errors,errors;assert not blocked,blocked
report={'live_navigation_passed':len(steps),'steps':steps,'inventory_mutations':0,'custody_mutations':0,'prints':0,'page_errors':errors}
(root/'work/workflow-verification/live-smoke-results.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
