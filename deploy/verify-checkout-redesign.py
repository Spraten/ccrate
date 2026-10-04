"""Browser fixture tests: no live accounts, inventory, custody or transactions are changed."""
import pathlib,sys,json
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path.insert(0,str(root/'work/hardware/python'))
from playwright.sync_api import sync_playwright
tool={'id':'10000000-0000-4000-8000-000000000001','name':'TEST – QR Tool','assetId':'000-002','quantity':1,'archived':False,'condition':'Ready','parent':{'name':'TEST – Workflow shelf'},'entityType':{'isLocation':False}}
blocked={**tool,'id':'10000000-0000-4000-8000-000000000002','name':'TEST – Broken Tool','condition':'Broken'}
location={**tool,'id':'10000000-0000-4000-8000-000000000003','name':'TEST – Shelf','entityType':{'isLocation':True}}
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':800,'height':480},has_touch=True);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    state={'user':None,'generation':1,'instance':'test-fixture-instance'};requests=[]
    def reply(route,data,status=200):route.fulfill(status=status,content_type='application/json',body=json.dumps(data))
    def api(route):
        path=route.request.url.split('17749')[-1];data=route.request.post_data_json if route.request.method=='POST' else {}
        if path=='/api/session':reply(route,state)
        elif path in ('/api/inventory','/api/stock'):reply(route,[tool,blocked])
        elif path=='/api/custody':reply(route,[])
        elif path.startswith('/api/kit'):reply(route,{'kit':False})
        elif path.startswith('/api/entity'):reply(route,{'entity':blocked if blocked['id'] in path else tool,'blocker':'Broken equipment cannot be checked out' if blocked['id'] in path else None})
        elif path=='/scan':
            code=data['code']
            if code=='BADGE':state['user']={'id':'20000000-0000-4000-8000-000000000001','name':'Workflow Test User'};reply(route,state)
            else:reply(route,{'entity':{'TOOL':tool,'BLOCKED':blocked,'LOCATION':location}[code]})
        elif path=='/session/activity':reply(route,{'active':bool(state['user'])})
        elif path=='/checkout/confirm':
            requests.append(data)
            if len(requests)==1:reply(route,{'error':'Temporary connection test'},503)
            else:state['user']=None;state['generation']+=1;reply(route,{'status':'completed','count':len(data['assets'])})
        else:reply(route,{'error':'Unexpected fixture route '+path},400)
    for pattern in ['**/api/**','**/scan','**/session/activity','**/checkout/confirm']:page.route(pattern,api)
    page.goto('http://127.0.0.1:17749');page.locator('[data-action="Check Out"]').tap();assert page.get_by_role('button',name='Scan my badge',exact=True).is_visible();assert page.get_by_role('button',name='Confirm checkout',exact=True).count()==0
    page.evaluate("routeScan('BADGE')");assert page.get_by_role('button',name='Scan equipment',exact=True).is_visible()
    page.evaluate("routeScan('TOOL')");assert page.get_by_text('Your equipment (1)',exact=True).is_visible();assert page.get_by_text('Added: TEST – QR Tool',exact=True).is_visible();assert page.get_by_role('button',name='Confirm checkout',exact=True).count()==0
    review=page.get_by_role('button',name='Review checkout',exact=True);assert review.is_enabled();box=review.bounding_box();assert box['y']+box['height']<=480
    page.screenshot(path=str(root/'work/checkout-redesign-cart.png'))
    page.evaluate("routeScan('TOOL')");assert page.evaluate('checkoutCart.length')==1
    page.evaluate("routeScan('BLOCKED')");assert page.get_by_text('TEST – Broken Tool: Broken equipment cannot be checked out',exact=True).is_visible();assert review.is_enabled();assert page.evaluate('checkoutCart.length')==1
    page.evaluate("routeScan('LOCATION')");assert page.get_by_text('This is a storage label. Scan an equipment label instead.',exact=True).is_visible()
    page.get_by_role('button',name='Find equipment',exact=True).tap();page.get_by_text('TEST – Broken Tool',exact=True).wait_for();assert page.locator('.checkout-choice').first.is_disabled();page.get_by_role('button',name='Back to list',exact=True).tap()
    review.tap();assert page.get_by_role('button',name='Confirm checkout',exact=True).is_visible();assert page.get_by_role('button',name='Back to items',exact=True).is_visible();page.screenshot(path=str(root/'work/checkout-redesign-review.png'))
    page.get_by_role('button',name='Confirm checkout',exact=True).tap();page.get_by_role('button',name='Retry confirmation',exact=True).wait_for();assert page.get_by_role('button',name='Back to items',exact=True).is_disabled()
    page.get_by_role('button',name='Retry confirmation',exact=True).tap();page.get_by_role('heading',name='Checkout complete',exact=True).wait_for();assert requests[0]['request_key']==requests[1]['request_key'];assert requests[0]['assets']==[tool['id']];assert not page.evaluate('identified');assert not page.evaluate('checkoutMode');assert not errors,errors
    page.get_by_role('button',name='Done',exact=True).tap();assert page.locator('[data-action="Check Out"]').is_visible()
    browser.close()
print(json.dumps({'badge_then_scan_auto_adds':True,'duplicate_scan_no_duplicate_item':True,'blocked_asset_and_storage_scan_explained':True,'confirm_only_after_review':True,'bottom_action_fits_touchscreen':True,'unavailable_picker_disabled':True,'retry_keeps_request_key':True,'completion_ends_session':True,'live_mutations':0,'browser_errors':errors}))
