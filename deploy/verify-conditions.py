import json,pathlib,sys,urllib.request
from uuid import uuid4
root=pathlib.Path('/home/user/Desktop/inventory-system')
sys.path.insert(0,str(root/'ops'))
sys.path.insert(0,str(root/'work/hardware/python'))
from homebox import Homebox
from conditions import STATES,condition,checkout_blocker,update_payload
from playwright.sync_api import sync_playwright
client=Homebox(root)
types=client.call('/api/v1/entity-types')
if isinstance(types,dict):types=types.get('items',[])
item_type=next(t for t in types if not t['isLocation'])
name='Condition proof '+str(uuid4())[:8]
asset=client.call('/api/v1/entities','POST',{'name':name,'description':'Disposable synthetic integration asset','quantity':1,'entityTypeId':item_type['id'],'parentId':'9b7f1f98-42f6-4ea5-aaf3-079b4d825499'})
base='http://127.0.0.1:17749'
def post(state):
    request=urllib.request.Request(base+'/condition',data=json.dumps({'entity_id':asset['id'],'state':state,'request_key':str(uuid4())}).encode(),headers={'Content-Type':'application/json','Origin':base})
    return json.load(urllib.request.urlopen(request,timeout=15))
try:
    assert condition(client.entity(asset['id']))=='Unreviewed'
    initial=client.entity(asset['id'])
    payload=update_payload(initial,'Needs Attention')
    payload.update(serialNumber='CONDITION-PROOF',manufacturer='Synthetic manufacturer',purchasePrice=27,purchaseDate='2026-10-01',warrantyDetails='Preserve warranty')
    payload['fields'].append({'name':'Calibration proof','type':'text','textValue':'Keep this value'})
    client.call('/api/v1/entities/'+asset['id'],'PUT',payload)
    before=client.entity(asset['id'])
    for state in STATES:
        result=post(state);after=client.entity(asset['id'])
        assert result['condition']==state and condition(after)==state
        assert (result['blocker'] is None)==(state=='Ready')
        for key in ('name','description','quantity','assetId','serialNumber','manufacturer','purchasePrice','purchaseDate','warrantyDetails','parent','entityType','tags'):
            assert after[key]==before[key],(state,key)
        assert next(f for f in after['fields'] if f['name']=='Calibration proof')['textValue']=='Keep this value'
        if state=='Archived':
            items=json.load(urllib.request.urlopen(base+'/api/inventory',timeout=15))
            assert any(e['id']==asset['id'] for e in items)
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True)
        page=browser.new_page(viewport={'width':800,'height':480},has_touch=True)
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base);page.get_by_text('Homebox connected',exact=False).wait_for()
        page.get_by_role('button',name='Browse Stock').tap()
        page.get_by_role('button',name=name,exact=False).tap()
        page.get_by_text('Condition: Trashed',exact=True).wait_for()
        page.get_by_role('button',name='Review condition',exact=True).tap()
        page.get_by_role('button',name='Ready',exact=True).tap()
        assert condition(client.entity(asset['id']))=='Trashed', 'State must not change before confirmation'
        page.get_by_role('button',name='Confirm Ready',exact=True).tap()
        page.get_by_text('Condition: Ready',exact=True).wait_for()
        assert not page.get_by_text('Checkout blocked:',exact=False).count()
        assert not errors,errors
        browser.close()
    result={'native_states_roundtrip':True,'archived_visible_in_inventory':True,'metadata_preserved':True,'unreviewed_blocked':True,'only_ready_checkout_eligible':True,'touch_review_requires_confirmation':True,'browser_errors':errors}
    (root/'docs/condition-integration-results.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
finally:
    client.call('/api/v1/entities/'+asset['id'],'DELETE')
