"""Isolated browser fixtures. Every request intercepted; no real inventory or prints."""
import json,os,pathlib,sys
from urllib.parse import urlsplit,parse_qs
ROOT=pathlib.Path('/home/user/Desktop/inventory-system')
sys.path.insert(0,str(ROOT/'work/hardware/python'))
from playwright.sync_api import sync_playwright,expect
FILES=pathlib.Path(os.environ.get('DESKTOP_UI_ROOT',str(ROOT/'desktop')))
OUTPUT=pathlib.Path(os.environ.get('DESKTOP_UI_OUTPUT',str(ROOT/'work/desktop-ui-verification')))
OUTPUT.mkdir(parents=True,exist_ok=True)
IMAGE='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl1sAAAAASUVORK5CYII='
USER={'id':'20000000-0000-4000-8000-000000000001','name':'Fixture Manager','email':'fixture@example.invalid'}
GROUP={'id':'50000000-0000-4000-8000-000000000001','name':'Fixture Collection'}
PLACE={'id':'30000000-0000-4000-8000-000000000001','name':'Fixture shelf','parent_id':None,'parent':None,'kind':'Shelf','code':'XYZ-2','updated_at':'v1','archived':False}
TOOLS=[{'id':'10000000-0000-4000-8000-00000000000'+str(i),'name':'Fixture '+name,'assetId':'000-00'+str(i),'quantity':1,'archived':False,'condition':'Ready','blocker':None,'parent':{'id':PLACE['id'],'name':PLACE['name']},'entityType':{'isLocation':False}} for i,name in [(1,'drill'),(2,'saw')]]
TYPE={'id':'40000000-0000-4000-8000-000000000001','name':'Tool','isLocation':False}
def batch(key='batch',mapped=True):
 result={'id':key,'filename':key+'.csv','source':'Asset Manager','headers':['Name','ID'],'items':[]}
 if not mapped:result['raw']=[['Fixture imported drill','AM-1']];return result
 result['items']=[{'index':i,'csv_row':i+2,'status':'reviewed','input':{'name':'Fixture imported '+str(i),'serial':'','manufacturer':'','model':'','description':'','location_id':PLACE['id'],'type_id':TYPE['id'],'import_condition':'Unreviewed','reviewed':False},'original':{'external_id':'AM-'+str(i)},'errors':[],'selected':True,'entity_id':None,'create_key':'60000000-0000-4000-8000-00000000000'+str(i),'label_key':'70000000-0000-4000-8000-00000000000'+str(i),'label_status':'pending'} for i in (1,2)]
 return result
results=[];page_errors=[]
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
 def setup(manager=True,mobile=False):
  page=browser.new_page(viewport={'width':390 if mobile else 1366,'height':844 if mobile else 850})
  page.set_default_timeout(6000)
  page.add_init_script("Object.defineProperty(crypto,'randomUUID',{value:undefined,configurable:true});")
  page.on('pageerror',lambda e:page_errors.append(str(e)))
  state={'manager':manager,'identity':'fixture-bound-identity','signed':True,'held':True,'batch':batch(),'delays':{},'print_count':0,'print_fail':False,'operations':{},'kit':False,'layout':{'name':'Fixture room','width':13.5,'height':21,'unit':'ft','approximate':True,'objects':[{'id':'80000000-0000-4000-8000-000000000001','kind':'Rack','name':'Fixture rack','x':1,'y':1,'width':3,'height':2,'rotation':0,'location_id':PLACE['id']}]},'revision':1}
  requests=[];delayed={}
  def reply(route,data,status=200):route.fulfill(status=status,content_type='application/json',body=json.dumps(data))
  def handler(route):
   request=route.request;parsed=urlsplit(request.url);path=parsed.path
   if path in ('/workshop','/workshop/'):
    route.fulfill(content_type='text/html',body=(FILES/'index.html').read_text(encoding='utf-8'));return
   if path.startswith('/workshop/'):
    name=path.rsplit('/',1)[-1];route.fulfill(content_type='text/css' if name.endswith('.css') else 'application/javascript',body=(FILES/name).read_text(encoding='utf-8'));return
   if not path.startswith('/workshop-api/'):
    route.fulfill(status=404,body='Fixture request blocked');return
   endpoint=path[len('/workshop-api/'):];data=request.post_data_json if request.method=='POST' else {};requests.append((endpoint,data,request.headers))
   if endpoint in state['delays']:
    delayed[endpoint]=route;return
   if endpoint=='context':reply(route,{'user':USER,'group':GROUP,'manager':state['manager'],'identity':state['identity']} if state['signed'] else {'error':'Sign in required'},200 if state['signed'] else 401)
   elif endpoint=='equipment':reply(route,TOOLS)
   elif endpoint=='locations':reply(route,[PLACE])
   elif endpoint=='types':reply(route,[TYPE])
   elif endpoint=='loans':reply(route,[{'entity_id':TOOLS[0]['id'],'entity_name':TOOLS[0]['name'],'borrower':'Fixture Borrower'}] if state['held'] else [])
   elif endpoint=='entity':reply(route,{'entity':next(e for e in TOOLS if e['id']==parse_qs(parsed.query)['id'][0]),'condition':'Ready','states':['Ready','Broken','Retired'],'blocker':None})
   elif endpoint=='kit':reply(route,{'kit':state['kit'],'entities':TOOLS,'versions':{TOOLS[0]['id']:1}})
   elif endpoint=='history':reply(route,[{'action':'return','status':'completed','actor':'Fixture Manager','assets':[TOOLS[0]['id']],'return_notes':[{'entity_id':TOOLS[0]['id'],'text':'Was dirty, returned clean.','author':'Fixture Manager','created_at':'2026-10-04T22:43:00Z'}]}])
   elif endpoint=='people':reply(route,[USER]+([{'id':'20000000-0000-4000-8000-000000000002','name':'Fixture Staff','email':'staff@example.invalid','workshop_manager':state.get('staff_manager',False)}] if state.get('extra_staff') else []))
   elif endpoint=='permissions/set':state['staff_manager']=data['enabled'];state['operations'][data['request_key']]='completed';reply(route,{'status':'completed'})
   elif endpoint=='badges':reply(route,[{'id':'badge-existing','user_id':USER['id'],'revoked':False}])
   elif endpoint=='badges/issue':state['operations'][data['request_key']]='completed';reply(route,{'id':'fixture-issued-badge','user_id':USER['id'],'code':'FIXTURE-SECRET-CODE','qr':IMAGE,'status':'completed'})
   elif endpoint in ('badges/revoke','badges/print','condition','backup/start'):
    state['operations'][data['request_key']]='completed';reply(route,{'status':'completed'})
   elif endpoint=='invitation/create':state['operations'][data['request_key']]='completed';reply(route,{'join_url':'/join?token=fixture-invitation','status':'completed'})
   elif endpoint=='return':state['held']=False;state['operations'][data['request_key']]='completed';reply(route,{'status':'completed','count':len(data['targets'])})
   elif endpoint=='labels/preview':reply(route,{'image':IMAGE,'width':320,'height':160})
   elif endpoint=='labels/print':
    state['print_count']+=1
    if state['print_fail'] and state['print_count']==2:state['operations'][data['request_key']]='review';reply(route,{'error':'Fixture uncertain printer output'},503)
    else:state['operations'][data['request_key']]='completed';reply(route,{'status':'completed'})
   elif endpoint=='operation/status':reply(route,{'status':state['operations'].get(data['request_key'],'not_started')})
   elif endpoint=='workshop':reply(route,{'revision':state['revision'],'layout':state['layout'],'locations':[PLACE],'counts':{PLACE['id']:2},'types':['Rack','Cabinet','Fence','Door'],'storage_types':['Location','Rack','Shelf','Bin']})
   elif endpoint=='workshop/save':
    if state.get('layout_conflict'):reply(route,{'error':'Fixture layout changed elsewhere. Reload before saving.'},409)
    else:state['layout']=data['layout'];state['revision']+=1;state['operations'][data['request_key']]='completed';reply(route,{'revision':state['revision'],'layout':state['layout']})
   elif endpoint in ('workshop/move','locations/create'):state['operations'][data['request_key']]='completed';reply(route,{'entity_id':PLACE['id']})
   elif endpoint=='imports':reply(route,[{'id':'batch','filename':'batch.csv','source':'Asset Manager','count':2},{'id':'other','filename':'other.csv','source':'Asset Manager','count':2}])
   elif endpoint=='imports/get':reply(route,batch(data['id']))
   elif endpoint=='imports/upload':state['batch']=batch('uploaded',False);state['operations'][data['request_key']]='completed';reply(route,state['batch'])
   elif endpoint=='imports/map':state['batch']=batch('uploaded');state['operations'][data['request_key']]='completed';reply(route,state['batch'])
   elif endpoint=='imports/save':state['batch']['id']=data['id'];row=state['batch']['items'][next(i for i,r in enumerate(state['batch']['items']) if r['index']==data['index'])];row.update(input=data['input'],selected=data['selected'],status='reviewed' if data['selected'] else 'skipped');state['operations'][data['request_key']]='completed';reply(route,state['batch'])
   elif endpoint in ('imports/create','imports/label'):state['operations'][data['request_key']]='completed';reply(route,state['batch'])
   elif endpoint=='recovery':reply(route,[{'id':'fixture-desktop-job','desktop_job':True,'action':'badge_issue','status':'review','native_assets':[],'created_at':'2026-10-04T22:43:00Z','intent':{'user_id':USER['id']}}])
   elif endpoint=='recovery/resolve':state['operations'][data['request_key']]='completed';reply(route,{'status':'completed'})
   elif endpoint=='system':reply(route,{'homebox':'Ready','homebox_version':'fixture','companion':'Ready','printer':{'connected':True,'width_mm':50,'height_mm':30},'free_gb':12,'private_backups':1,'camera_devices':1})
   else:reply(route,{'error':'Unexpected fixture API '+endpoint},404)
  page.route('**/*',handler)
  page.goto('http://pi-fixture.local/workshop');page.wait_for_load_state('networkidle');expect(page.get_by_role('heading',name='Workshop overview')).to_be_visible()
  return page,state,requests,delayed,reply
 def nav(page,name):
  if page.locator('#mobile-nav').is_visible():page.locator('#mobile-nav').select_option(label=name)
  else:page.locator('#nav').get_by_role('button',name=name,exact=True).click()
  expect(page.get_by_role('heading',name={'Overview':'Workshop overview','Equipment':'Equipment','Loans & notes':'Loans & notes','People & badges':'People & badges','Workshop & storage':'Workshop & storage','Imports':'Import equipment','Labels':'Label queue','Recovery':'Recovery','System':'System'}[name],exact=True)).to_be_visible()
  page.wait_for_load_state('networkidle')
 def done(page,name):results.append(name);print('PASS: '+name,flush=True);page.close()
 if os.environ.get('DESKTOP_UI_FAST_AUTH'):
  page,state,requests,delayed,reply=setup(False)
  page.goto('http://pi-fixture.local/workshop#people');expect(page.get_by_role('heading',name='Workshop overview',exact=True)).to_be_visible();assert page.url.endswith('#overview');assert page.locator('#nav button').count()==4
  done(page,'Member manager-only bookmark opens permitted overview')
  page,state,requests,delayed,reply=setup();nav(page,'People & badges');page.get_by_role('button',name='Issue badge').click();state['manager']=False;page.evaluate('window.dispatchEvent(new Event("focus"))');expect(page.get_by_role('heading',name='Sign in to Homebox')).to_be_visible();expect(page.locator('#dialog')).not_to_be_visible();page.get_by_role('button',name='Check my sign-in').click();expect(page.get_by_role('heading',name='Workshop overview',exact=True)).to_be_visible();assert page.locator('#nav button').count()==4;assert not any(ep=='badges/issue' for ep,_,_ in requests)
  done(page,'Revoked manager permission clears private dialog and reopens member overview')
  assert not page_errors,page_errors
  browser.close();print(json.dumps({'passed':len(results),'scenarios':results,'browser_errors':page_errors},indent=2));(OUTPUT/'desktop-ui-auth-results.json').write_text(json.dumps({'passed':len(results),'scenarios':results,'browser_errors':page_errors},indent=2),encoding='utf-8');sys.exit(0)
 page,state,requests,delayed,reply=setup()
 page.screenshot(path=str(OUTPUT/'desktop-overview.png'),full_page=True)
 for name in ['Equipment','Loans & notes','People & badges','Workshop & storage','Imports','Labels','Recovery','System','Overview']:nav(page,name);expect(page.locator('main h1')).to_be_visible();page.screenshot(path=str(OUTPUT/('desktop-'+{'People & badges':'people','Workshop & storage':'workshop','Loans & notes':'loans','Labels':'labels'}.get(name,name.lower())+'.png')),full_page=True)
 done(page,'Nine management sections load with fixture APIs')
 page,state,requests,delayed,reply=setup(False)
 assert page.locator('#nav').get_by_role('button',name='People & badges').count()==0
 nav(page,'Equipment');page.get_by_role('button',name='Fixture drill',exact=True).click();expect(page.get_by_role('link',name='Edit equipment in Homebox')).to_have_attribute('href','/item/'+TOOLS[0]['id']);assert page.get_by_role('button',name='Review condition').count()==0
 done(page,'Member navigation hides manager actions and native links use current host')
 page,state,requests,delayed,reply=setup()
 nav(page,'Equipment');page.get_by_role('textbox',name='Search equipment').fill('drill');page.get_by_role('button',name='Fixture drill',exact=True).click();page.get_by_role('button',name='Return notes',exact=True).click();expect(page.get_by_text('Was dirty, returned clean.',exact=True)).to_be_visible();expect(page.get_by_text('Fixture Manager · 10/04/2026, 06:43 PM EDT',exact=True)).to_be_visible();page.keyboard.press('Escape');expect(page.get_by_role('textbox',name='Search equipment')).to_have_value('drill')
 done(page,'Item note log attributes author, Eastern daylight time, and preserves equipment search')
 page,state,requests,delayed,reply=setup()
 nav(page,'Loans & notes');page.get_by_role('button',name='Record return',exact=True).click();page.get_by_role('textbox',name='Return note: Fixture drill').fill('Cleaned on return');page.get_by_role('button',name='Confirm administrative return').click();expect(page.locator('#dialog')).not_to_be_visible();page.wait_for_load_state('networkidle');returns=[data for ep,data,_ in requests if ep=='return'];assert returns[0]['targets'][0]['return_note']=='Cleaned on return';assert returns[0]['targets'][0]['condition'] is None
 done(page,'Administrative return preserves condition and submits optional note')
 page,state,requests,delayed,reply=setup();state['kit']=True
 nav(page,'Loans & notes');page.get_by_role('button',name='Record return',exact=True).click();page.get_by_role('button',name='Confirm administrative return').click();expect(page.get_by_text('Verify every kit component before confirming.')).to_be_visible();assert not any(ep=='return' for ep,_,_ in requests);page.get_by_role('checkbox',name='Physically verified: Fixture drill').check();page.get_by_role('checkbox',name='Physically verified: Fixture saw').check();page.get_by_role('button',name='Confirm administrative return').click();expect(page.locator('#dialog')).not_to_be_visible();page.wait_for_load_state('networkidle');assert len(next(data for ep,data,_ in requests if ep=='return')['verified'])==2
 done(page,'Kit returns require individual physical verification')
 page,state,requests,delayed,reply=setup()
 nav(page,'People & badges');page.get_by_role('button',name='Issue badge',exact=True).click();page.get_by_role('button',name='Confirm badge issuance').click();expect(page.get_by_role('img',name='New personal badge for Fixture Manager')).to_be_visible();assert not any(ep=='badges/print' for ep,_,_ in requests);assert 'FIXTURE-SECRET' not in page.evaluate('JSON.stringify(localStorage)');page.keyboard.press('Escape');assert page.get_by_role('img').count()==0
 done(page,'Badge QR is ephemeral and issuing a badge never prints automatically')
 page,state,requests,delayed,reply=setup()
 nav(page,'People & badges');page.get_by_role('button',name='Create invitation link').click();page.get_by_role('button',name='Confirm invitation link').click();expect(page.get_by_role('textbox',name='Invitation link')).to_have_value('http://pi-fixture.local/join?token=fixture-invitation');assert not any('email' in ep for ep,_,_ in requests)
 done(page,'Native invitation uses reachable origin and sends no email')
 page,state,requests,delayed,reply=setup();state['print_fail']=True
 nav(page,'Equipment');page.get_by_role('checkbox',name='Select Fixture drill').check();page.get_by_role('checkbox',name='Select Fixture saw').check();page.get_by_role('button',name='Queue selected labels').click();page.get_by_role('button',name='Preview label').first.click();expect(page.get_by_role('img',name='Actual label preview for Fixture drill')).to_be_visible();assert state['print_count']==0;page.keyboard.press('Escape');page.get_by_role('button',name='Review 2 Pi labels').click();page.get_by_role('button',name='Confirm print on Pi').click();expect(page.get_by_role('button',name='Queue stopped — check Recovery')).to_be_disabled();assert state['print_count']==2;page.evaluate("document.querySelector('#dialog .main').click()");page.wait_for_timeout(200);assert state['print_count']==2;page.get_by_role('button',name='Open Recovery').click();page.get_by_role('button',name='Check saved result').click();expect(page.get_by_text('The outcome still needs inspection.',exact=False)).to_be_visible()
 done(page,'Pi preview prints nothing; partial queue stops and cannot repeat completed labels')
 page,state,requests,delayed,reply=setup()
 nav(page,'Imports');page.get_by_role('button',name='Resume batch').first.click();expect(page.get_by_role('heading',name='batch.csv')).to_be_visible();page.screenshot(path=str(OUTPUT/'desktop-import-review.png'),full_page=True);page.get_by_role('button',name='Edit row').first.click();page.get_by_role('textbox',name='Equipment name').fill('Corrected fixture item');page.get_by_role('button',name='Save row review').click();expect(page.get_by_text('Corrected fixture item',exact=True)).to_be_visible();assert next(data for ep,data,_ in requests if ep=='imports/save')['id']=='batch'
 done(page,'Saved CSV batch resumes, row editor saves correct batch and durable key')
 page,state,requests,delayed,reply=setup()
 nav(page,'Imports');page.get_by_role('textbox',name='Source system').fill('Fixture Source');page.get_by_label('CSV file').set_input_files({'name':'training.csv','mimeType':'text/csv','buffer':b'Name,ID\nFixture import,AM-1\n'});page.get_by_role('button',name='Upload & map CSV').click();expect(page.get_by_role('heading',name='Map CSV columns')).to_be_visible();page.get_by_role('button',name='Save mapping & review rows').click();expect(page.get_by_role('heading',name='uploaded.csv')).to_be_visible();assert next(data for ep,data,_ in requests if ep=='imports/map')['mapping']['name']=='Name'
 done(page,'CSV file upload and column mapping use live-shaped APIs')
 page,state,requests,delayed,reply=setup()
 nav(page,'Imports');page.get_by_role('button',name='Resume batch').first.click();page.get_by_role('button',name='Review creation of 2 items').click();state['delays']['imports/create']=True;page.get_by_role('button',name='Confirm selected creation').click();page.wait_for_timeout(100);expect(page.get_by_role('button',name='Stop after current item')).to_be_enabled();expect(page.get_by_role('checkbox',name='Fixture imported 2')).to_be_disabled();page.get_by_role('button',name='Stop after current item').click();reply(delayed['imports/create'],state['batch']);state['delays'].pop('imports/create');expect(page.locator('#dialog')).not_to_be_visible();page.wait_for_load_state('networkidle');assert sum(ep=='imports/create' for ep,_,_ in requests)==1
 done(page,'Import Stop remains available during a write and freezes submitted selection')
 page,state,requests,delayed,reply=setup()
 nav(page,'Workshop & storage');page.get_by_role('button',name='Select Fixture rack').click();page.get_by_role('button',name='Edit drawing properties').click();page.get_by_role('textbox',name='Object name').fill('Renamed drawing');page.get_by_role('button',name='Apply drawing changes').click();page.get_by_role('button',name='Save layout changes').click();expect(page.get_by_role('button',name='Layout saved')).to_be_visible();page.wait_for_load_state('networkidle');assert state['layout']['objects'][0]['name']=='Renamed drawing';assert not any(ep=='workshop/move' for ep,_,_ in requests);assert any(ep=='workshop/save' and data.get('request_key') for ep,data,_ in requests)
 page.locator('#toast').evaluate('(e)=>e.hidden=true');page.screenshot(path=str(OUTPUT/'desktop-workshop.png'),full_page=True)
 done(page,'Layout geometry saves with revision; drawing edit does not move native storage')
 page,state,requests,delayed,reply=setup()
 nav(page,'Recovery');page.get_by_role('button',name='Inspect operation').click();page.get_by_role('button',name='Confirm completion').click();expect(page.get_by_text('Inspect and confirm the physical result first.',exact=True)).to_be_visible();page.get_by_role('checkbox',name='I inspected physical equipment or labels and the stored values.').check();page.get_by_role('button',name='Confirm completion').click();expect(page.locator('#dialog')).not_to_be_visible();page.wait_for_load_state('networkidle');data=next(d for ep,d,_ in requests if ep=='recovery/resolve');assert data['desktop_job'] and data['inspected'] and data['outcome']=='complete'
 done(page,'Desktop recovery requires inspection and submits correct desktop job flags')
 page,state,requests,delayed,reply=setup(mobile=True)
 nav(page,'People & badges');page.get_by_role('button',name='Issue badge').click();page.keyboard.press('Escape');expect(page.locator('#dialog')).not_to_be_visible();nav(page,'Equipment');assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
 page.screenshot(path=str(OUTPUT/'desktop-mobile.png'),full_page=True)
 done(page,'Mobile navigation, Escape and table overflow work without horizontal page overflow')
 page,state,requests,delayed,reply=setup()
 nav(page,'Equipment');state['delays']['entity']=True;page.get_by_role('button',name='Fixture drill',exact=True).click();page.locator('#nav').get_by_role('button',name='Overview',exact=True).click();reply(delayed['entity'],{'entity':TOOLS[0],'condition':'Ready','states':['Ready'],'blocker':None});page.wait_for_load_state('networkidle');expect(page.locator('#dialog')).not_to_be_visible();expect(page.get_by_role('heading',name='Workshop overview')).to_be_visible()
 done(page,'Delayed item response cannot reopen a dialog after navigation')
 page,state,requests,delayed,reply=setup()
 nav(page,'Equipment');page.get_by_role('button',name='Fixture drill',exact=True).click();state['delays']['history']=True;page.get_by_role('button',name='Return notes',exact=True).click();page.get_by_role('button',name='Summary',exact=True).click();reply(delayed['history'],[{'return_notes':[{'text':'Stale notes','author':'Fixture','created_at':'2026-10-04T00:00:00Z'}]}]);page.wait_for_load_state('networkidle');assert page.get_by_text('Stale notes',exact=True).count()==0;expect(page.get_by_role('link',name='Edit equipment in Homebox')).to_be_visible()
 done(page,'Delayed notes cannot append into a newly selected summary tab')
 page,state,requests,delayed,reply=setup()
 nav(page,'Imports');state['delays']['imports/get']=True;page.get_by_role('button',name='Resume batch').first.click();first=delayed['imports/get'];page.get_by_role('button',name='Resume batch').last.click();last=delayed['imports/get'];reply(last,batch('other'));page.wait_for_timeout(100);reply(first,batch('batch'));page.wait_for_load_state('networkidle');expect(page.get_by_role('heading',name='other.csv')).to_be_visible();assert page.get_by_role('heading',name='batch.csv').count()==0
 done(page,'Out-of-order import resume responses preserve the latest chosen batch')
 page,state,requests,delayed,reply=setup()
 nav(page,'Equipment');page.get_by_role('button',name='Fixture drill',exact=True).click();state['identity']='different-account';page.evaluate('window.dispatchEvent(new Event("focus"))');page.wait_for_timeout(200);expect(page.get_by_role('heading',name='Sign in to Homebox')).to_be_visible();expect(page.locator('#dialog')).not_to_be_visible();assert page.locator('#nav button').count()==0
 done(page,'Account change clears old identity, private dialogs and management navigation')
 page,state,requests,delayed,reply=setup()
 nav(page,'Workshop & storage');page.get_by_role('button',name='Select Fixture rack').click();page.get_by_role('button',name='Edit drawing properties').click();page.get_by_role('textbox',name='Object name').fill('Rejected edit');page.get_by_role('button',name='Apply drawing changes').click();state['layout_conflict']=True;page.get_by_role('button',name='Save layout changes').click();expect(page.get_by_text('Fixture layout changed elsewhere. Reload before saving.',exact=True)).to_be_visible();assert page.evaluate('pending().length')==0;state['layout_conflict']=False;page.on('dialog',lambda d:d.accept());page.get_by_role('button',name='Reload saved layout').click();expect(page.get_by_role('button',name='Layout saved')).to_be_visible();page.get_by_role('button',name='Select Fixture rack').click();page.get_by_role('button',name='Edit drawing properties').click();page.get_by_role('textbox',name='Object name').fill('Fresh valid edit');page.get_by_role('button',name='Apply drawing changes').click();page.get_by_role('button',name='Save layout changes').click();expect(page.get_by_role('button',name='Layout saved')).to_be_visible();assert state['layout']['objects'][0]['name']=='Fresh valid edit'
 done(page,'Rejected stale layout clears only proven-not-started request and allows fresh edit after reload')
 page,state,requests,delayed,reply=setup();state['layout']=None
 nav(page,'Workshop & storage');page.get_by_role('button',name='Create empty room').click();expect(page.get_by_text('No saved floor plan yet.',exact=True)).not_to_be_visible();expect(page.get_by_role('heading',name='Native storage hierarchy',exact=True)).to_have_count(1);page.get_by_role('button',name='Save layout changes').click();expect(page.get_by_role('button',name='Layout saved')).to_be_visible();assert state['layout']['objects']==[]
 done(page,'Empty collection can create and save one clean room without stale prompts or duplicate hierarchy')
 page,state,requests,delayed,reply=setup(False)
 page.goto('http://pi-fixture.local/workshop#people');expect(page.get_by_role('heading',name='Workshop overview',exact=True)).to_be_visible();assert page.url.endswith('#overview');assert page.locator('#nav button').count()==4
 done(page,'Member manager-only bookmark returns to permitted overview without sign-in loop')
 page,state,requests,delayed,reply=setup();state['extra_staff']=True
 nav(page,'People & badges');page.get_by_role('button',name='Allow management',exact=True).click();page.get_by_role('button',name='Confirm management access',exact=True).click();expect(page.get_by_role('button',name='Remove management access',exact=True)).to_be_visible();assert state['staff_manager']
 page.get_by_role('button',name='Remove management access',exact=True).click();page.get_by_role('button',name='Confirm management access',exact=True).click();expect(page.get_by_role('button',name='Allow management',exact=True)).to_be_visible();assert not state['staff_manager']
 done(page,'Homebox people tools grant and remove staff management access')
 assert not page_errors,page_errors
 browser.close()
print(json.dumps({'passed':len(results),'scenarios':results,'browser_errors':page_errors},indent=2))
(OUTPUT/'desktop-ui-results.json').write_text(json.dumps({'passed':len(results),'scenarios':results,'browser_errors':page_errors},indent=2),encoding='utf-8')
