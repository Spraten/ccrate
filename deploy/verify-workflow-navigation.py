"""Staged UI only: every HTTP request is intercepted. No live writes or prints."""
import sys,json,pathlib,traceback,os
from urllib.parse import urlsplit
ROOT=pathlib.Path('/home/user/Desktop/inventory-system')
sys.path.insert(0,str(ROOT/'work/hardware/python'))
from playwright.sync_api import sync_playwright
FILES=pathlib.Path(os.environ.get('WORKFLOW_UI_ROOT',str(ROOT/'kiosk')))
OUTPUT=ROOT/'work/workflow-verification';OUTPUT.mkdir(exist_ok=True)
TOOL={'id':'10000000-0000-4000-8000-000000000001','name':'Fixture drill','assetId':'000-002','quantity':1,'archived':False,'condition':'Ready','parent':{'id':'30000000-0000-4000-8000-000000000001','name':'Fixture shelf'},'entityType':{'isLocation':False,'name':'Tool'},'attachments':[]}
PLACE={'id':'30000000-0000-4000-8000-000000000001','name':'Fixture shelf','archived':False,'entityType':{'isLocation':True}}
TYPE={'id':'40000000-0000-4000-8000-000000000001','name':'Tool','isLocation':False}
USER={'id':'20000000-0000-4000-8000-000000000001','name':'Borrower A'}
IMAGE='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl1sAAAAASUVORK5CYII='
def batch():
 return {'id':'batch','filename':'fixtures.csv','headers':['Name'],'raw':[{},{}],'items':[{'index':i,'csv_row':i+2,'status':'draft','input':{'name':'Item '+str(i),'location_id':PLACE['id'],'type_id':TYPE['id'],'import_condition':'Unreviewed'},'original':{},'errors':[],'selected':True} for i in range(2)]}
results=[];errors=[]
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
 def setup(editor=False,width=800):
  page=browser.new_page(viewport={'width':width,'height':480 if width==800 else 800},has_touch=not editor)
  page.set_default_timeout(8000)
  state={'user':None,'generation':1,'instance':'fixture-instance','held':False,'outcome':'not_started','confirmation':'reject','batch':batch()};pending={};requests=[];page_errors=[]
  page.on('pageerror',lambda e:page_errors.append(str(e)))
  def reply(route,data,status=200):route.fulfill(status=status,content_type='application/json',body=json.dumps(data))
  def handle(route):
   req=route.request;path=urlsplit(req.url).path
   if path=='/':route.fulfill(content_type='text/html',body=(FILES/'index.html').read_text());return
   if path.endswith('.js'):route.fulfill(content_type='application/javascript',body=(FILES/path.lstrip('/')).read_text());return
   if path.startswith('/assets/'):route.fulfill(status=404,body='');return
   data=req.post_data_json if req.method=='POST' and req.headers.get('content-type','').startswith('application/json') else {}
   requests.append((path,data,req.headers.get('x-homebox-client')))
   if path=='/api/session':reply(route,{k:state[k] for k in ('user','generation','instance')})
   elif path in ('/api/inventory','/api/stock'):reply(route,[] if state.get('empty') else [TOOL])
   elif path=='/api/custody':reply(route,[{'entity_id':TOOL['id'],'borrower':'Borrower A'}] if state['held'] else [])
   elif path=='/api/locations':reply(route,[PLACE])
   elif path=='/api/types':reply(route,[TYPE])
   elif path=='/api/members':reply(route,[USER])
   elif path in ('/api/badges','/api/history','/api/maintenance','/api/recovery'):
    if state.get('delay')==path:pending[path]=route
    elif path=='/api/maintenance' and state.get('maintenance'):reply(route,[{'id':'maintenance','name':'Fixture inspection','scheduledDate':'2026-10-04','completedDate':None,'description':'Fixture only'}])
    else:reply(route,[])
   elif path=='/api/catalog':reply(route,{'products':[]})
   elif path=='/api/product':reply(route,{'product':None})
   elif path=='/api/system':reply(route,{'homebox_version':'fixture','homebox':'Connected','companion':'Ready','printer':{'connected':False},'camera_devices':0,'free_gb':10,'private_backups':0})
   elif path=='/workshop/get':reply(route,{'revision':0,'layout':{'name':'Fixture shop','width':13.5,'height':21,'unit':'ft','objects':[]},'locations':[{'id':PLACE['id'],'name':PLACE['name'],'kind':'Shelf','parent_id':None,'code':'A-2'}],'counts':{PLACE['id']:1},'storage_types':['Rack','Shelf','Bin'],'types':['Rack','Fence']})
   elif path=='/api/kit':reply(route,{'kit':True,'root':TOOL,'entities':[TOOL],'verified':[],'versions':{TOOL['id']:1},'blockers':[]} if state.get('kit') else {'kit':False})
   elif path=='/api/entity':reply(route,{'entity':TOOL,'condition':'Ready','blocker':'Broken equipment' if state.get('blocked') else None,'states':['Ready','Broken','Retired']})
   elif path=='/label/preview':reply(route,{'error':'Fixture printer unavailable'} if state.get('printer_error') else {'image':IMAGE},503 if state.get('printer_error') else 200)
   elif path=='/scan':
    if data['code']=='DELAY':pending['scan']=route
    elif data['code']=='NETWORK':route.abort('connectionfailed')
    elif data['code']=='BADGE':state['user']=USER;state['generation']+=1;reply(route,{k:state[k] for k in ('user','generation','instance')})
    elif data['code']=='WRONG':reply(route,{'kind':'invalid','reason':'Code not recognized'})
    elif data['code']=='SHELF':reply(route,{'entity':PLACE})
    else:reply(route,{'entity':TOOL})
   elif path=='/scan/cancel':
    if state.get('scan_token')==data['scan_token']:state['user']=None;state['generation']+=1
    reply(route,{'cancelled':True})
   elif path=='/session/end':state['user']=None;state['generation']+=1;reply(route,{'ended':True})
   elif path=='/session/activity':reply(route,{'active':bool(state['user'])})
   elif path in ('/checkout/confirm','/return/confirm'):
    if state['confirmation']=='delay':pending['confirmation']=route
    elif state['confirmation']=='success':state['outcome']='completed';state['user']=None;state['generation']+=1;reply(route,{'count':1})
    else:reply(route,{'error':'Fixture rejection'},409 if state['outcome']=='not_started' else 503)
   elif path=='/operation/status':
    if state.get('delay')==path:pending['status']=route
    else:reply(route,{'status':state['outcome']})
   elif path in ('/imports/list',):reply(route,[])
   elif path in ('/imports/get','/imports/upload','/imports/map'):reply(route,state['batch'])
   elif path=='/imports/save':state['batch']['items'][data['index']]['input']=data['input'];state['batch']['items'][data['index']]['status']='reviewed';reply(route,state['batch'])
   elif path in ('/condition','/categories/create','/label/print','/accounts/create','/locations/create','/catalog/create','/enroll/confirm','/problem/confirm','/badge/issue','/badge/revoke','/maintenance/complete'):reply(route,{'error':'Fixture write rejected'},400)
   else:errors.append('Unexpected request '+path);reply(route,{'error':'Fixture endpoint unavailable: '+path},400)
  page.route('http://127.0.0.1:17749/**',handle)
  page.goto('http://127.0.0.1:17749/'+('?mode=editor' if editor else ''));page.wait_for_function('typeof clientId!=="undefined"');page.wait_for_load_state('networkidle')
  return page,state,pending,requests,page_errors,reply
 def check(name,test,editor=False,width=800):
  page,state,pending,requests,page_errors,reply=setup(editor,width)
  try:test(page,state,pending,requests,reply);assert not page_errors,page_errors;results.append(name)
  except Exception:page.screenshot(path=str(OUTPUT/'failure.png'));raise
  finally:page.close()
 def start(p,title='Check Out'):p.locator('[data-action="'+title+'"]').tap();p.evaluate("routeScan('BADGE')")
 def checkout(p,s,*_):
  start(p);p.evaluate("routeScan('TOOL')");p.get_by_role('button',name='Review checkout',exact=True).tap();p.screenshot(path=str(OUTPUT/'checkout-review.png'));p.get_by_role('button',name='Back to items',exact=True).tap();assert p.evaluate('checkoutCart.length')==1
  p.get_by_role('button',name='Review checkout',exact=True).tap();s['confirmation']='success';p.get_by_role('button',name='Confirm checkout',exact=True).tap();p.get_by_role('heading',name='Checkout complete',exact=True).wait_for();p.get_by_role('button',name='Done',exact=True).tap();assert p.locator('[data-action]').count()==6
 check('Checkout scan → review → Back → confirm → Done',checkout)
 def rejected(p,s,*_):
  start(p);p.evaluate("routeScan('TOOL')");p.get_by_role('button',name='Review checkout',exact=True).tap();p.get_by_role('button',name='Confirm checkout',exact=True).tap();p.get_by_text('No changes were made.',exact=False).wait_for();assert p.get_by_role('button',name='Back to items',exact=True).is_enabled();p.get_by_role('button',name='Back to items',exact=True).tap();p.get_by_role('button',name='Remove Fixture drill',exact=True).tap();assert p.evaluate('checkoutCart.length')==0
 check('Known rejection allows cart correction',rejected)
 def uncertain(p,s,*_):
  start(p);p.evaluate("routeScan('TOOL')");s['outcome']='review';p.get_by_role('button',name='Review checkout',exact=True).tap();p.get_by_role('button',name='Confirm checkout',exact=True).tap();p.get_by_role('button',name='Check saved result',exact=True).wait_for();assert p.get_by_role('button',name='Check result below',exact=True).is_disabled();p.get_by_role('button',name='Open recovery',exact=True).tap();p.get_by_role('heading',name='Interrupted operations',exact=True).wait_for();assert p.get_by_role('button',name='Back',exact=True).is_visible()
 check('Uncertain confirmation exposes recovery without blind retry',uncertain)
 def delayed(p,s,pending,requests,reply):
  p.locator('[data-action="Check Out"]').tap();p.get_by_role('button',name='Enter badge code',exact=True).tap();p.evaluate("document.querySelector('input[aria-label=\"Manual code\"]').value='DELAY'");p.get_by_role('dialog').get_by_role('button',name='Use code',exact=True).tap();p.wait_for_timeout(80);p.get_by_role('button',name='Back',exact=True).tap();s['user']=USER;s['generation']+=1;s['scan_token']=[r[1]['scan_token'] for r in requests if r[0]=='/scan'][-1];reply(pending['scan'],{k:s[k] for k in ('user','generation','instance')});p.wait_for_timeout(200);assert not p.evaluate('identified');assert p.get_by_role('button',name='Scan my badge',exact=True).is_visible()
 check('Manual Back cancels late badge response',delayed)
 def identity(p,s,*_):
  start(p);p.evaluate("routeScan('TOOL')");s['user']={**USER,'name':'Borrower B','id':'20000000-0000-4000-8000-000000000002'};s['generation']+=1;p.evaluate('updateIdentity()');assert p.evaluate('checkoutCart.length')==0;assert not p.evaluate('checkoutMode');assert p.locator('[data-action]').count()==6
 check('Badge change clears old cart and task',identity)
 def storage(p,s,*_):
  start(p);p.evaluate("routeScan('TOOL')");p.locator('#storage-nav').tap();p.get_by_role('button',name='Keep editing',exact=True).tap();assert p.evaluate('checkoutMode');p.locator('#storage-nav').tap();p.get_by_role('button',name='Discard & leave',exact=True).tap();p.get_by_role('button',name='Add top-level location',exact=True).wait_for();assert not p.evaluate('checkoutMode');p.evaluate("routeScan('TOOL')");p.get_by_role('heading',name=TOOL['name'],exact=True).wait_for()
 check('Global navigation guards drafts and clears hidden scan modes',storage)
 def returning(p,s,*_):
  s['held']=True;start(p,'Return');p.evaluate("routeScan('TOOL')");p.get_by_role('button',name='Condition',exact=True).tap();p.get_by_role('button',name='Broken',exact=True).tap();p.get_by_role('button',name='Condition',exact=True).tap();p.get_by_role('button',name='Back',exact=True).first.tap();p.get_by_role('button',name='Shelf',exact=True).tap();p.get_by_role('button',name='Keep assigned shelf',exact=True).tap();p.get_by_role('button',name='Review return',exact=True).tap();p.screenshot(path=str(OUTPUT/'return-review.png'));assert p.evaluate('returnCart[0].condition')=='Broken';p.get_by_role('button',name='Back to items',exact=True).tap();p.get_by_role('button',name='Review return',exact=True).tap();s['confirmation']='success';p.get_by_role('button',name='Confirm return',exact=True).tap();p.get_by_role('heading',name='Return complete',exact=True).wait_for();p.get_by_role('button',name='Done',exact=True).tap()
 check('Return condition, shelf, review, Back, confirmation and receipt',returning)
 def note_flow(p,s,pending,requests,reply):
  s['held']=True;start(p,'Return');p.evaluate("routeScan('TOOL')")
  p.get_by_role('button',name='Add note',exact=True).tap()
  p.get_by_label('Note',exact=True).tap();p.get_by_role('button',name='Key A',exact=True).tap();p.get_by_role('button',name='Done',exact=True).tap()
  p.get_by_role('button',name='Save note',exact=True).tap()
  assert p.evaluate('returnCart[0].return_note')=='a'
  p.get_by_role('button',name='Edit note',exact=True).tap();p.get_by_role('button',name='Cancel',exact=True).tap()
  p.get_by_role('button',name='Review return',exact=True).tap();p.get_by_text('Return note: a',exact=True).wait_for()
  s['confirmation']='success';p.get_by_role('button',name='Confirm return',exact=True).tap();p.get_by_role('heading',name='Return complete',exact=True).wait_for()
  assert next(data for path,data,_ in requests if path=='/return/confirm')['targets'][0]['return_note']=='a'
 check('Touch return note saves, cancels edit, reviews and submits without condition change',note_flow)
 def note_history(p,s,pending,requests,reply):
  s['delay']='/api/history';p.evaluate('void showHistory()');p.wait_for_timeout(80)
  reply(pending['/api/history'],[{'action':'return','status':'completed','actor':'Andreas','created_at':'2026-10-04T22:43:00Z','assets':[],'return_notes':[{'text':'Was dirty, returned clean','author':'Andreas','created_at':'2026-10-04T22:43:00Z'}]}])
  p.get_by_text('Was dirty, returned clean',exact=True).wait_for();p.get_by_text('Andreas · 10/04/2026, 18:43 EDT',exact=True).wait_for()
 check('Return note history displays author and Eastern daylight time',note_history)

 def search(p,s,*_):
  p.locator('[data-action="Find Item"]').tap();p.get_by_role('button',name=TOOL['name']+' 000-002 · Fixture shelf · Ready',exact=False).wait_for();p.evaluate("let f=document.querySelector('input[aria-label=\"Search equipment or location\"]');f.value='drill';f.oninput()");p.locator('#results button').tap();p.get_by_role('button',name='Activity history',exact=True).tap();p.get_by_role('button',name='Back',exact=True).tap();p.get_by_role('button',name='Photos & files',exact=True).tap();p.get_by_role('button',name='Back',exact=True).tap();p.get_by_role('button',name='Back',exact=True).tap();assert p.locator('input').input_value()=='drill'
 check('Search → detail → history/files → Back retains query',search)
 def csv(p,s,*_):
  p.evaluate('importBatch='+json.dumps(batch())+';importReview(0)');p.get_by_label('Equipment name',exact=True).wait_for();p.evaluate("const f=document.querySelector('input[aria-label=\"Equipment name\"]');f.value='Edited item';f.oninput()");p.get_by_role('button',name='Next',exact=True).click();p.get_by_role('button',name='Previous',exact=True).click();assert p.get_by_label('Equipment name',exact=True).input_value()=='Edited item';p.get_by_role('button',name='Batch summary',exact=True).click();p.get_by_text('Unsaved edits in 1 item(s).',exact=False).wait_for();assert p.get_by_role('button',name='Confirm: create 0 reviewed items',exact=True).is_disabled();p.get_by_role('button',name='Review items',exact=True).click();p.get_by_role('button',name='Save review & next',exact=True).click();assert s['batch']['items'][0]['input']['name']=='Edited item'
 check('CSV Previous/Next/summary retain edits; explicit save persists',csv,True,1280)
 def laptop(p,s,_,requests,__):
  p.locator('#desktop').click();assert p.get_by_role('heading',name='Disconnect laptop',exact=True).is_visible();assert not any(r[0]=='/exit' for r in requests);assert all(r[2] for r in requests);p.get_by_role('button',name='Return to editor',exact=True).click();p.locator('[data-action="Check Out"]').click();p.get_by_role('button',name='Enter badge code',exact=True).click();assert p.get_by_label('Manual code').is_editable();p.get_by_label('Manual code').fill('WRONG');p.get_by_label('Manual code').press('Enter');p.get_by_text('Code not recognized',exact=True).wait_for();p.get_by_role('button',name='Back',exact=True).click()
 check('Laptop manual keyboard, invalid-code recovery and local disconnect',laptop,True,1280)
 def keyboard(p,s,*_):
  p.evaluate("heading('Fixture form');window.fixtureDraft={name:''};touchField(view,'Name',fixtureDraft,'name').click()");p.get_by_role('button',name='Key A',exact=True).tap();p.get_by_role('button',name='Close keyboard',exact=True).tap();assert p.evaluate('fixtureDraft.name')=='a';p.locator('#home-nav').tap();p.get_by_role('button',name='Keep editing',exact=True).tap();assert p.get_by_label('Name').input_value()=='a';p.locator('#home-nav').tap();p.get_by_role('button',name='Discard & leave',exact=True).tap()
 check('Touch keyboard close keeps edits; leaving offers keep/discard',keyboard)
 def stale(p,s,pending,requests,reply):
  s['delay']='/api/history';p.evaluate('void showHistory()');p.wait_for_timeout(80);p.locator('#home-nav').tap();reply(pending['/api/history'],[{'action':'check_out','status':'completed','actor':'Fixture','created_at':'2026-01-01','assets':[]}]);p.wait_for_timeout(100);assert p.locator('[data-action]').count()==6;assert p.get_by_text('Fixture',exact=False).count()==0
 check('Slow history response cannot replace Home',stale)
 def writegate(p,s,pending,requests,reply):
  start(p);p.evaluate("routeScan('TOOL')");s['confirmation']='delay';p.get_by_role('button',name='Review checkout',exact=True).tap();p.get_by_role('button',name='Confirm checkout',exact=True).tap();p.wait_for_timeout(80);p.locator('#home-nav').tap();assert p.get_by_role('heading',name='Review checkout',exact=True).is_visible();s['user']=None;s['generation']+=1;reply(pending['confirmation'],{'count':1});p.get_by_role('heading',name='Checkout complete',exact=True).wait_for()
 check('Pending confirmation prevents conflicting navigation',writegate)
 def pages(p,s,*_):
  start(p,'Add Equipment');p.get_by_label('Equipment name',exact=True).wait_for();p.locator('#home-nav').tap();p.locator('#admin').tap();p.get_by_role('button',name='Equipment categories',exact=True).tap();p.get_by_role('button',name='Create category',exact=True).tap();p.get_by_role('button',name='Confirm category',exact=True).tap();p.get_by_role('button',name='Confirm category',exact=True).wait_for(state='visible');p.wait_for_timeout(100);assert p.get_by_role('button',name='Confirm category',exact=True).is_enabled();p.get_by_role('button',name='Back',exact=True).tap();p.locator('#home-nav').tap();p.locator('#layout-nav').tap();p.get_by_role('button',name='Show view controls',exact=True).tap();p.get_by_role('button',name='Pan right',exact=True).tap();p.get_by_role('button',name='Fit',exact=True).tap();p.locator('#home-nav').tap()
 check('Enrollment, Admin form rejection, Back and workshop view controls',pages)
 def duplicate(p,s,*_):
  start(p);p.evaluate("routeScan('TOOL')");p.evaluate("routeScan('TOOL')");assert p.evaluate('checkoutCart.length')==1;p.get_by_text('Already in your list: Fixture drill',exact=True).wait_for();p.evaluate("routeScan('SHELF')");assert p.evaluate('checkoutCart.length')==1
 check('Duplicate and wrong-type scans cannot add invalid checkout items',duplicate)
 def blocked(p,s,*_):
  start(p);s['blocked']=True;p.evaluate("routeScan('TOOL')");assert p.evaluate('checkoutCart.length')==0;p.get_by_text('Fixture drill: Broken equipment',exact=True).wait_for();assert p.get_by_role('button',name='Review checkout',exact=True).is_disabled();p.get_by_role('button',name='Find equipment',exact=True).tap();p.get_by_role('button',name='Back to list',exact=True).tap()
 check('Blocked asset stays out of cart; picker has a return path',blocked)
 def expire(p,s,*_):
  start(p);p.evaluate("routeScan('TOOL')");s['user']=None;s['generation']+=1;p.evaluate('updateIdentity()');assert p.locator('[data-action]').count()==6;assert p.evaluate('checkoutCart.length')==0
 check('Expired identity ends task and clears selected items',expire)
 def camera(p,s,*_):
  p.evaluate("() => {navigator.mediaDevices.getUserMedia=()=>Promise.reject(Object.assign(new Error('Fixture denied'),{name:'NotAllowedError'}));}");p.locator('#scan').tap();p.get_by_text('Camera permission needed.',exact=False).wait_for();p.get_by_role('button',name='Cancel scan',exact=True).tap();assert p.locator('[data-action]').count()==6;p.locator('#scan').tap();p.get_by_role('button',name='Enter code',exact=True).tap();p.get_by_role('dialog').get_by_role('button',name='Back',exact=True).tap();assert p.locator('[data-action]').count()==6
 check('Camera permission failure offers Cancel and manual entry',camera)
 def label(p,s,*_):
  s['printer_error']=True;p.evaluate('detail('+json.dumps(TOOL)+')');p.get_by_role('button',name='Label preview',exact=True).tap();p.get_by_text('Fixture printer unavailable',exact=True).wait_for();p.get_by_role('button',name='Back',exact=True).tap();p.get_by_role('heading',name=TOOL['name'],exact=True).wait_for()
 check('Label preview failure retains a working Back path',label)
 def formback(p,s,*_):
  p.locator('#admin').tap();p.get_by_role('button',name='Create Homebox account',exact=True).tap();p.evaluate("const f=document.querySelector('input[aria-label=\"Person name\"]');f.value='Fixture name';f.oninput()");p.get_by_role('button',name='Back',exact=True).tap();p.get_by_role('button',name='Keep editing',exact=True).tap();assert p.get_by_label('Person name').input_value()=='Fixture name';p.get_by_role('button',name='Back',exact=True).tap();p.get_by_role('button',name='Discard & go back',exact=True).tap();p.get_by_role('heading',name='Administration',exact=True).wait_for()
 check('Back from an edited Admin form requires explicit discard',formback)
 def return_reject(p,s,*_):
  s['held']=True;start(p,'Return');p.evaluate("routeScan('TOOL')");p.get_by_role('button',name='Review return',exact=True).tap();p.get_by_role('button',name='Confirm return',exact=True).tap();p.get_by_text('No changes were made.',exact=False).wait_for();assert p.get_by_role('button',name='Back to items',exact=True).is_enabled();p.get_by_role('button',name='Back to items',exact=True).tap();p.get_by_role('button',name='Remove',exact=True).tap();assert p.evaluate('returnCart.length')==0
 check('Rejected return allows correction and removal',return_reject)
 def return_unknown(p,s,*_):
  s['held']=True;start(p,'Return');p.evaluate("routeScan('TOOL')");s['outcome']='review';p.get_by_role('button',name='Review return',exact=True).tap();p.get_by_role('button',name='Confirm return',exact=True).tap();p.get_by_role('button',name='Check saved result',exact=True).wait_for();p.get_by_role('button',name='Open recovery',exact=True).tap();p.get_by_role('button',name='Back',exact=True).tap();assert p.evaluate('returnMode');s['outcome']='completed';p.get_by_role('button',name='Check saved result',exact=True).tap();p.get_by_role('heading',name='Return complete',exact=True).wait_for()
 check('Unknown return can open recovery, Back and reconcile completion',return_unknown)
 def empty(p,s,*_):
  s['empty']=True;p.locator('[data-action="Browse Stock"]').tap();p.get_by_text('No matching equipment.',exact=True).wait_for();p.get_by_role('button',name='Back',exact=True).tap();assert p.locator('[data-action]').count()==6
 check('Empty stock has a usable return to Home',empty)
 def kit(p,s,*_):
  start(p);s['kit']=True;p.evaluate("routeScan('TOOL')");p.get_by_role('button',name='Cancel kit',exact=True).tap();assert p.evaluate('checkoutCart.length')==0;p.evaluate("routeScan('TOOL')");assert p.get_by_role('button',name='Use verified kit',exact=True).is_disabled();p.evaluate("routeScan('TOOL')");p.get_by_role('button',name='Use verified kit',exact=True).tap();assert p.evaluate('checkoutCart.length')==1;assert p.evaluate('Object.keys(checkoutKitVersions).length')==1
 check('Kit cancel, verification and use preserve the cart workflow',kit)
 def problem(p,s,*_):
  p.locator('#report-problem').tap();p.evaluate("routeScan('BADGE')");p.get_by_role('button',name=TOOL['name'],exact=True).tap();p.evaluate("const f=document.querySelector('input[aria-label=\"Describe the problem\"]');f.value='Fixture problem note';f.oninput()");p.get_by_role('button',name='Review report',exact=True).tap();p.get_by_role('button',name='Back',exact=True).last.tap();assert p.get_by_label('Describe the problem').input_value()=='Fixture problem note';p.get_by_role('button',name='Review report',exact=True).tap();p.get_by_role('button',name='Confirm problem report',exact=True).tap();p.get_by_text('Fixture write rejected',exact=True).wait_for();assert p.get_by_role('button',name='Confirm problem report',exact=True).is_enabled();p.locator('#home-nav').tap();p.get_by_role('button',name='Discard & leave',exact=True).tap()
 check('Problem report review/Back retains note; rejection permits correction',problem)
 def enrollment(p,s,*_):
  start(p,'Add Equipment');p.get_by_label('Equipment name',exact=True).wait_for();p.evaluate("const f=document.querySelector('input[aria-label=\"Equipment name\"]');f.value='Fixture enrollment';f.oninput()");p.get_by_role('button',name='Review equipment',exact=True).tap();p.get_by_role('button',name='Back',exact=True).last.tap();assert p.get_by_label('Equipment name').input_value()=='Fixture enrollment';p.get_by_role('button',name='Review equipment',exact=True).tap();p.get_by_role('button',name='Confirm add equipment',exact=True).tap();p.get_by_text('Fixture write rejected',exact=True).wait_for();assert p.get_by_role('button',name='Confirm add equipment',exact=True).is_enabled()
 check('Enrollment review/Back retains draft and handles rejection',enrollment)
 def nativeforms(p,s,*_):
  for manager,form,submit in [('Locations','Create location','Confirm new location'),('Offline products','Add product barcode','Confirm product')]:
   p.locator('#admin').tap();p.get_by_role('button',name=manager,exact=True).tap();p.get_by_role('button',name=form,exact=True).tap();p.get_by_role('button',name=submit,exact=True).tap();p.get_by_text('Fixture write rejected',exact=True).wait_for();assert p.get_by_role('button',name=submit,exact=True).is_enabled();p.get_by_role('button',name='Back',exact=True).first.tap()
 check('Location and product forms have correction and Back after rejection',nativeforms)
 def backup(p,s,*_):
  p.locator('#admin').tap();p.get_by_role('button',name='System status & backup',exact=True).tap();p.get_by_role('button',name='Create recovery backup',exact=True).tap();p.get_by_role('button',name='Back',exact=True).tap();p.get_by_role('heading',name='System status',exact=True).wait_for()
 check('Backup review can be canceled without starting a backup',backup)
 def nativeLink(p,s,*_):
  p.evaluate('detail('+json.dumps(TOOL)+')');p.get_by_role('button',name='Label preview',exact=True).wait_for();assert not p.get_by_role('link',name='Open in Homebox',exact=True).is_visible()
 check('Touch kiosk keeps native browser links out of the routine flow',nativeLink)
 def network(p,s,*_):
  p.locator('#manual').tap();p.evaluate("document.querySelector('input[aria-label=\"Manual code\"]').value='NETWORK'");p.get_by_role('dialog').get_by_role('button',name='Use code',exact=True).tap();p.get_by_text('Failed to fetch',exact=True).wait_for();p.get_by_role('button',name='Back',exact=True).tap();assert p.locator('[data-action]').count()==6
 check('Network failure during manual entry keeps Back usable',network)
 def uncertain_leave(p,s,*_):
  start(p);p.evaluate("routeScan('TOOL')");s['outcome']='review';p.get_by_role('button',name='Review checkout',exact=True).tap();p.get_by_role('button',name='Confirm checkout',exact=True).tap();p.get_by_role('button',name='Check saved result',exact=True).wait_for();p.locator('#home-nav').tap();p.get_by_role('button',name='Keep task',exact=True).tap();assert p.evaluate('checkoutKey') is not None;p.screenshot(path=str(OUTPUT/'uncertain-checkout.png'));box=p.get_by_role('button',name='Open recovery',exact=True).bounding_box();assert box['y']+box['height']<=480
 check('Uncertain outcome cannot be discarded; recovery remains within touch viewport',uncertain_leave)
 def photo(p,s,*_):
  p.evaluate("() => {navigator.mediaDevices.getUserMedia=()=>Promise.reject(new Error('Fixture unavailable'));}");start(p,'Add Equipment');p.get_by_role('button',name='Add equipment photo',exact=True).tap();p.get_by_text('Camera unavailable. Cancel to continue without a photo.',exact=True).wait_for();p.get_by_role('button',name='Cancel photo',exact=True).tap();assert p.get_by_label('Equipment name').is_visible()
 check('Photo camera failure can be canceled back to the draft',photo)
 def recovery_race(p,s,pending,requests,reply):
  start(p);p.evaluate("routeScan('TOOL')");s['outcome']='review';p.get_by_role('button',name='Review checkout',exact=True).tap();p.get_by_role('button',name='Confirm checkout',exact=True).tap();p.get_by_role('button',name='Check saved result',exact=True).wait_for();s['delay']='/operation/status';p.get_by_role('button',name='Check saved result',exact=True).tap();p.wait_for_timeout(80);p.get_by_role('button',name='Open recovery',exact=True).tap();reply(pending['status'],{'status':'completed'});p.wait_for_timeout(100);assert p.get_by_role('heading',name='Interrupted operations',exact=True).is_visible();assert p.get_by_role('heading',name='Checkout complete',exact=True).count()==0
 check('Delayed recovery status cannot replace a newer route',recovery_race)
 def maintenance(p,s,*_):
  s['maintenance']=True;p.evaluate('detail('+json.dumps(TOOL)+')');p.get_by_role('button',name='Maintenance & inspections',exact=True).tap();p.get_by_role('button',name='Mark entry completed',exact=True).tap();p.get_by_role('button',name='Confirm completed work',exact=True).tap();p.get_by_text('Fixture write rejected',exact=True).wait_for();assert p.get_by_role('button',name='Confirm completed work',exact=True).is_enabled();p.get_by_role('button',name='Cancel',exact=True).tap();p.get_by_role('heading',name='Maintenance: '+TOOL['name'],exact=True).wait_for()
 check('Maintenance rejection permits correction or Cancel',maintenance)
 def scrolling(p,s,*_):
  start(p,'Add Equipment');p.get_by_role('button',name='Review equipment',exact=True).wait_for();p.locator('#view').evaluate('(n)=>n.scrollTop=n.scrollHeight');back=p.get_by_role('button',name='Back',exact=True).first.bounding_box();assert 60<=back['y']<120;assert p.get_by_role('button',name='Review equipment',exact=True).is_visible();p.screenshot(path=str(OUTPUT/'enrollment-actions.png'))
 check('Long form keeps Back visible while scrolling to its action',scrolling)
 browser.close()
assert not errors,errors
report={'fixture_only':True,'live_writes':0,'passed':len(results),'scenarios':results}
(OUTPUT/'interaction-results.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
