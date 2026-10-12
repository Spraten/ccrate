"""Every request is intercepted; fixture-only scan and registration checks."""
import pathlib,sys,json
from urllib.parse import urlsplit
ROOT=pathlib.Path('/home/user/Desktop/inventory-system')
sys.path[:0]=[str(ROOT/'work/hardware/python'),str(ROOT/'kiosk')]
from playwright.sync_api import sync_playwright
from scan_codes import normalize,resolve_equipment,MANUFACTURER_FIELD
ID='10000000-0000-4000-8000-000000000001'
RAW='https://maker.invalid/device?model=Fixture&opaque=42'
tool={'id':ID,'name':'Fixture equipment','assetId':'000-002','serialNumber':'SERIAL-42','quantity':1,'archived':False,'condition':'Ready','parent':{'name':'Fixture shelf'},'entityType':{'isLocation':False},'fields':[{'name':MANUFACTURER_FIELD,'type':'text','textValue':RAW}]}
state={'user':None,'generation':1,'instance':'fixture-instance','held':False,'duplicate':False};writes=[];errors=[]
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':800,'height':480},has_touch=True);page.set_default_timeout(8000);page.on('pageerror',lambda e:errors.append(str(e)))
 def reply(route,data,status=200):route.fulfill(status=status,content_type='application/json',body=json.dumps(data))
 def handle(route):
  path=urlsplit(route.request.url).path
  if path=='/':route.fulfill(content_type='text/html',body=(ROOT/'kiosk/index.html').read_text());return
  if path.endswith('.js'):route.fulfill(content_type='application/javascript',body=(ROOT/'kiosk'/path.lstrip('/')).read_text());return
  data=route.request.post_data_json if route.request.method=='POST' else {}
  if path=='/api/session':reply(route,{k:state[k] for k in ('user','generation','instance')})
  elif path in ('/api/inventory','/api/stock'):reply(route,[tool])
  elif path=='/api/custody':reply(route,[{'entity_id':ID,'borrower':'Fixture user'}] if state['held'] else [])
  elif path=='/api/entity':reply(route,{'entity':tool,'condition':'Ready','blocker':None,'states':['Ready']})
  elif path=='/api/kit':reply(route,{'kit':False})
  elif path in ('/session/activity','/scan/cancel'):reply(route,{})
  elif path=='/scan':
   if data['code']=='BADGE':
    state['user']={'id':'20000000-0000-4000-8000-000000000001','name':'Fixture user'};state['generation']+=1;reply(route,{k:state[k] for k in ('user','generation','instance')})
   else:
    code=normalize(data['code'])
    if code['kind'] in ('asset','entity'):reply(route,{**code,'entity':tool})
    else:reply(route,resolve_equipment(data['code'],code,[tool,{**tool,'id':'30000000-0000-4000-8000-000000000001'}] if state['duplicate'] else [tool]))
  elif path=='/equipment/code':writes.append(data);reply(route,{'status':'completed','entity_id':ID})
  elif path=='/session/end':state['user']=None;state['generation']+=1;reply(route,{})
  else:reply(route,[],200)
 page.route('**/*',handle);page.goto('http://127.0.0.1:17749/');page.wait_for_function("typeof routeScan==='function' && typeof editorMode==='boolean'")
 page.evaluate("open('Check Out')");page.evaluate("routeScan('BADGE')")
 for raw in ['/item/'+ID,'000-002',RAW,'SERIAL-42','https://maker.invalid/?sn=SERIAL-42']:
  page.evaluate('(raw)=>routeScan(raw)',raw)
  assert page.evaluate('checkoutCart.length')==1
  page.evaluate('checkoutCart=[];renderCheckout()')
 state['duplicate']=True;result=page.evaluate('(raw)=>routeScan(raw)',RAW)
 assert 'multiple' in result.lower();assert page.evaluate('checkoutCart.length')==0
 state['duplicate']=False;state['held']=True;page.evaluate("resetTask();open('Return');routeScan('BADGE')")
 for raw in ['/item/'+ID,RAW,'SERIAL-42']:
  page.evaluate('(raw)=>routeScan(raw)',raw);assert page.evaluate('returnCart.length')==1
  page.evaluate('returnCart=[];renderReturn()')
 page.evaluate('(e)=>{resetTask();manufacturerCodeForm(e)}',tool)
 page.evaluate('scanPurpose="register_manufacturer"');page.evaluate('(raw)=>routeScan(raw)', '{"arbitrary":"factory payload"}')
 page.get_by_role('button',name='Confirm code for this item',exact=True).tap()
 page.wait_for_function("routeTitle==='Fixture equipment'")
 assert writes[0]['input']=={'entity_id':ID,'code':'{"arbitrary":"factory payload"}'}
 assert not errors,errors;browser.close()
print('Passed: checkout and return accept Homebox UUID/asset label, serial, manufacturer URL and registered opaque QR; ambiguous scans do not add equipment; registration confirms exact item. All HTTP intercepted; no live writes.')
