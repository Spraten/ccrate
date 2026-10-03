"""Core workflows in a namespace with loopback only and a restored filesystem."""
import json,pathlib,subprocess,sys,time,urllib.request
from uuid import uuid4
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path[:0]=[str(root/'ops'),str(root/'kiosk'),str(root/'work/hardware/python')]
from homebox import Homebox
from conditions import set_condition
from playwright.sync_api import sync_playwright
base='http://127.0.0.1:17749';processes=[]
def wait(url):
    for attempt in range(80):
        try:urllib.request.urlopen(url,timeout=1).close();return
        except OSError:time.sleep(.25)
    raise RuntimeError('Isolated local service did not start')
def post(path,data):
    if path in ('/checkout/confirm','/return/confirm'):
        session=json.load(urllib.request.urlopen(base+'/api/session'));data=dict(data,session_generation=session['generation'],session_instance=session['instance'])
    return json.load(urllib.request.urlopen(urllib.request.Request(base+path,data=json.dumps(data).encode(),headers={'Origin':base,'Content-Type':'application/json'}),timeout=60))
try:
    links=json.loads(subprocess.check_output(['ip','-j','link'],text=True));assert [link['ifname'] for link in links]==['lo']
    for command in [['python3',str(root/'deploy/run-homebox.py')],['python3',str(root/'deploy/kiosk-server.py')]]:processes.append(subprocess.Popen(command,stdout=(root/'work/offline-test.log').open('ab'),stderr=subprocess.STDOUT))
    wait('http://127.0.0.1:17745/api/v1/status');wait(base)
    client=Homebox(root);native=client.call('/api/v1/users/self')['item'];types=client.call('/api/v1/entity-types');item=next(t for t in types if not t['isLocation']);location=next(e for e in client.entities(True) if not e.get('archived'))
    asset=client.call('/api/v1/entities','POST',{'name':'Isolated offline proof '+str(uuid4())[:8],'quantity':1,'entityTypeId':item['id'],'parentId':location['id']});set_condition(client,asset['id'],'Ready');badge=post('/badge/issue',{'user_id':native['id']});post('/scan',{'code':badge['code']});post('/checkout/confirm',{'assets':[asset['id']],'request_key':str(uuid4())});post('/scan',{'code':badge['code']});post('/return/confirm',{'targets':[{'entity_id':asset['id']}],'request_key':str(uuid4())})
    catalog=json.load(urllib.request.urlopen(base+'/api/catalog'));assert catalog['products'];assert post('/label/preview',{'entity_id':asset['id']})['image'].startswith('data:image/png')
    assert json.load(urllib.request.urlopen(base+'/api/map'))['rooms'] is not None
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--use-fake-device-for-media-stream','--disable-background-networking']);page=browser.new_page(viewport={'width':800,'height':480},has_touch=True,permissions=['camera']);errors=[];external=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda request:external.append(request.url) if not request.url.startswith(base) else None)
        page.goto(base);page.get_by_text('Homebox connected',exact=False).wait_for();page.get_by_role('button',name='Browse Stock',exact=False).tap();page.get_by_label('Condition filter',exact=True).wait_for();page.get_by_role('button',name='← Home',exact=True).tap();page.get_by_role('button',name='Scan',exact=True).tap();page.get_by_text('Hold your badge or a Homebox QR code',exact=False).wait_for();assert page.evaluate('scanStream.getVideoTracks()[0].readyState')=='live';page.get_by_role('button',name='Cancel scan',exact=True).tap();assert not external,external;assert not errors,errors;browser.close()
    result={'network_interfaces':['lo'],'native_and_companion_start_without_network':True,'native_authentication':True,'checkout_return':True,'native_inventory_catalog_map':True,'qr_label_preview':True,'touch_browser':True,'camera_start_cancel_synthetic':True,'external_browser_requests':external,'browser_errors':errors,'live_deployment_mutated':False,'physical_cable_disconnection':'Not performed; kernel network namespace had no Ethernet or Wi-Fi interface'}
    (root/'docs/offline-isolation-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
finally:
    for proc in reversed(processes):proc.terminate()
    for proc in reversed(processes):proc.wait(timeout=15)
