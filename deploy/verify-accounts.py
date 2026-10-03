import json,pathlib,secrets,sys,urllib.request
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path[:0]=[str(root/'ops'),str(root/'kiosk'),str(root/'work/hardware/python')]
from homebox import Homebox
from playwright.sync_api import sync_playwright
client=Homebox(root);base='http://127.0.0.1:17749';email='proof'+secrets.token_hex(4)+'@example.invalid';password=secrets.token_hex(8);created=False
try:
    invites_before={e['id'] for e in client.call('/api/v1/groups/invitations')}
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);page=browser.new_page(viewport={'width':800,'height':480},has_touch=True);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base);page.get_by_text('Homebox connected',exact=False).wait_for();page.get_by_role('button',name='Admin',exact=True).tap();page.get_by_role('button',name='Create Homebox account',exact=True).tap()
        for label,value in [('Person name','proof user'),('Email address',email),('Homebox password',password)]:
            page.get_by_label(label,exact=True).tap()
            for char in value:
                page.get_by_role('button',name='Space' if char==' ' else 'Key '+char.upper(),exact=True).tap()
            if label=='Homebox password':assert password not in page.locator('output').inner_text()
            page.get_by_role('button',name='Done',exact=True).tap()
        page.get_by_role('button',name='Confirm new account',exact=True).tap();page.get_by_role('heading',name='Account created',exact=True).wait_for(timeout=60000);created=True
        assert not errors,errors;browser.close()
    member=next(m for m in client.call('/api/v1/groups/members') if m['email']==email)
    assert {e['id'] for e in client.call('/api/v1/groups/invitations')}==invites_before
    login=Homebox.__new__(Homebox);login.base='http://127.0.0.1:17745';login.token=None;login.token=login.call('/api/v1/users/login','POST',{'username':email,'password':password})['token'].removeprefix('Bearer ')
    assert login.call('/api/v1/users/self')['item']['id']==member['id']
    result={'touch_only_account_creation':True,'native_group_membership_verified':True,'native_login_works':True,'password_masked':True,'single_use_invitation_cleaned':True,'companion_password_storage':False,'browser_errors':errors}
    (root/'docs/account-integration-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
finally:
    if any(m['email']==email for m in client.call('/api/v1/groups/members')):
        login=Homebox.__new__(Homebox);login.base='http://127.0.0.1:17745';login.token=None;login.token=login.call('/api/v1/users/login','POST',{'username':email,'password':password})['token'].removeprefix('Bearer ');login.call('/api/v1/users/self','DELETE')
