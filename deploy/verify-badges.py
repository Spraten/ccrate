import io,json,pathlib,sys,urllib.request
r=pathlib.Path('/home/user/Desktop/inventory-system');sys.path.insert(0,str(r/'work/hardware/python'))
from playwright.sync_api import sync_playwright
from PIL import Image
import zxingcpp,base64
base='http://127.0.0.1:17749'
def get(path):return json.load(urllib.request.urlopen(base+path,timeout=15))
def post(path,payload):
    req=urllib.request.Request(base+path,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Origin':base})
    return json.load(urllib.request.urlopen(req,timeout=15))
members=get('/api/members');member=members[0];badge=post('/badge/issue',{'user_id':member['id']})
try:
    decoded=zxingcpp.read_barcodes(Image.open(io.BytesIO(base64.b64decode(badge['qr'].split(',')[1]))))
    assert decoded[0].text==badge['code']
    assert post('/scan',{'code':badge['code']})['user']['id']==member['id']
    assert get('/api/session')['user']['id']==member['id']
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium')
        page=browser.new_page(viewport={'width':800,'height':480},has_touch=True);errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        try:
            page.goto(base);page.wait_for_load_state('networkidle')
            assert page.locator('#identity').inner_text()==member['name']
            page.get_by_role('button',name='End session',exact=True).tap()
            page.get_by_text('Scan badge to identify yourself',exact=True).wait_for()
            assert get('/api/session')['user'] is None
            page.get_by_role('button',name='Admin',exact=True).tap()
            page.get_by_role('button',name='Issue badge: '+member['name'],exact=True).tap()
            page.get_by_role('img',name='Test badge QR').wait_for()
            page.get_by_role('button',name='Revoke this badge',exact=True).tap()
            page.get_by_role('heading',name='What would you like to do?').wait_for()
            assert not errors,errors
        finally:browser.close()
    assert all('token_hash' not in b and 'code' not in b for b in get('/api/badges'))
finally:post('/badge/revoke',{'id':badge['id']})
assert post('/scan',{'code':badge['code']})['kind']=='invalid'
result={'native_member_badge_issue':True,'qr_decodes':True,'badge_identifies_member':True,'end_session_touch':True,'admin_issue_revoke_touch':True,'revoked_badge_rejected':True,'tokens_not_in_list':True,'browser_errors':errors}
(r/'docs/badge-integration-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
