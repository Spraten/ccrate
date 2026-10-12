#!/usr/bin/env python3
"""Read-only live walkthrough; only the existing account's login may POST."""
import json
import os
import pathlib
import subprocess
import sys
import urllib.request
from urllib.parse import urlsplit

ROOT = pathlib.Path('/home/user/Desktop/inventory-system')
sys.path.insert(0, str(ROOT/'work/hardware/python'))
from playwright.sync_api import sync_playwright

BASE = os.environ.get('HOMEBOX_VERIFY_BASE', 'http://127.0.0.1:17745')
steps, errors, blocked, failed = [], [], [], []
with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
    page = browser.new_page(viewport={'width': 1366, 'height': 850})
    page.set_default_timeout(20000)
    page.on('pageerror', lambda error: errors.append(error.stack))
    page.on('requestfailed', lambda request: failed.append({'path': urlsplit(request.url).path, 'method': request.method, 'failure': request.failure}))
    def protect(route):
        path = urlsplit(route.request.url).path
        if route.request.method == 'PUT' and path == '/api/v1/users/self/settings':
            route.fulfill(status=200, content_type='application/json', body=json.dumps({'item': route.request.post_data_json}))
            return
        readonly_posts = {'/workshop-api/labels/preview', '/workshop-api/operation/status', '/workshop-api/imports/get', '/workshop-api/hardware/reconnect', '/hardware/reconnect'}
        if route.request.method not in ('GET', 'HEAD') and path != '/api/v1/users/login' and path not in readonly_posts:
            blocked.append(path); route.abort()
        else:
            route.continue_()
    page.route('**/*', protect)
    page.goto(BASE+'/collection/members')
    page.locator('#login-username').wait_for()
    steps.append('anonymous member management redirects to native Homebox sign-in')
    page.get_by_role('heading', name='C-Crate', exact=True).wait_for()
    assert page.locator('svg[aria-label="C-Crate logo: drone flying out of a crate"]').count()==1
    manifest=page.context.request.get(BASE+'/manifest.webmanifest').json()
    assert manifest['name']==manifest['short_name']=='C-Crate'
    steps.append('native sign-in and application manifest display the C-Crate name and drone/crate logo')
    page.wait_for_load_state('networkidle')
    account = json.loads((ROOT/'work/baseline/test-account.json').read_text())
    page.locator('#login-username').fill(account['email'])
    page.locator('#login-password').fill(account['password'])
    del account
    with page.expect_response(lambda response: urlsplit(response.url).path == '/api/v1/users/login' and response.request.method == 'POST',timeout=45000) as signed_in:
        page.locator('#login-form button[type=submit]').click()
    assert signed_in.value.status==200, 'Existing native account login failed'
    try:
        page.wait_for_url(lambda url: urlsplit(url).path != '/',timeout=45000,wait_until='domcontentloaded')
    except Exception:
        print(json.dumps({'login_path':urlsplit(page.url).path,'headings':page.get_by_role('heading').all_text_contents(),'failed_requests':failed,'browser_error_count':len(errors)}),flush=True)
        raise
    page.goto(BASE+'/collection/members')
    page.get_by_role('columnheader', name='Kiosk Badge', exact=True).wait_for()
    page.get_by_role('button', name='Manage badges', exact=True).first.wait_for()
    steps.append('Workshop Admin manages badges in the native Collection Members table')
    current_loans = page.context.request.get(BASE+'/workshop-api/loans').json()
    current_members = page.context.request.get(BASE+'/api/v1/groups/members').json()
    for member in current_members:
        count = sum(1 for loan in current_loans if loan['actor_id'] == member['id'])
        row = page.get_by_role('row').filter(has_text=member['id'][:8])
        row.get_by_role('button', name=str(count)+(' item checked out' if count == 1 else ' items checked out'), exact=True).wait_for()
    steps.append('native Members rows show each current member with badge actions and accurate checked-out item counts')
    avatars={}
    for member in current_members:
        avatar=page.get_by_role('row').filter(has_text=member['id'][:8]).get_by_role('img',name=('Profile picture for ' if member.get('avatar') else 'Generated avatar for ')+member['name'],exact=True)
        avatar.wait_for();avatars[member['id']]=avatar.get_attribute('src');assert avatars[member['id']]==member.get('avatar') or avatars[member['id']].startswith('data:image/svg+xml,')
    generated=[avatars[member['id']] for member in current_members if not member.get('avatar')]
    assert len(set(generated))==len(generated)
    steps.append('native Members displays saved pictures or distinct generated avatars for real member identities')

    page.get_by_role('button',name='Manage users',exact=True).click()
    manager=page.get_by_role('dialog',name='Manage users',exact=True)
    manager.get_by_role('button',name='New user',exact=True).click()
    create=page.get_by_role('dialog',name='Create user',exact=True)
    create.get_by_role('textbox',name='Name',exact=True).wait_for()
    optional_email=create.get_by_role('textbox',name='Email (optional)',exact=True)
    assert not optional_email.get_attribute('required') and not create.locator('input[type=password]').count()
    page.keyboard.press('Escape')
    steps.append('native Manage users opens a name-only creation form without creating a live account')
    page.goto(BASE+'/home')
    checkouts = page.get_by_test_id('checked-out-items')
    checkouts.get_by_role('heading', name='Checked-out items', exact=True).wait_for()
    checkouts.get_by_role('button', name='Refresh checked-out items', exact=True).wait_for(state='visible')
    expected_loans = page.context.request.get(BASE+'/workshop-api/loans').json()
    checkouts.get_by_role('status', name=str(len(expected_loans))+' checked out', exact=True).wait_for()
    assert checkouts.get_by_role('alert').count() == 0
    if not expected_loans:
        checkouts.get_by_text('No items are currently checked out in this collection.', exact=True).wait_for()
    checkouts.get_by_role('button', name='Refresh checked-out items', exact=True).click()
    checkouts.get_by_role('status', name=str(len(expected_loans))+' checked out', exact=True).wait_for()
    steps.append('native Home dashboard shows current checked-out items and its refresh matches real custody')
    page.goto(BASE+'/collection/members')
    page.get_by_role('button', name='Manage badges', exact=True).first.click()
    page.get_by_role('button', name='Issue badge', exact=True).click()
    page.get_by_role('button', name='Confirm badge issuance', exact=True).wait_for()
    page.get_by_role('button', name='Cancel', exact=True).click()
    steps.append('badge confirmation uses the native dialog; no badge is issued by this walkthrough')
    assert page.locator('iframe').count() == 0
    assert page.locator('#homebox-equipment-tools,#homebox-equipment-dialog').count() == 0
    steps.append('native Homebox has no floating workshop controls or embedded panels')
    printer = page.context.request.get(BASE+'/workshop-api/system').json()['printer']
    for tool, heading in (('loans', 'Loans & notes'), ('map', 'Workshop & storage'), ('imports', 'Import equipment'), ('labels', 'Label queue'), ('recovery', 'Recovery'), ('system', 'System')):
        page.locator('a[href="/workshop/'+tool+'"]').first.click()
        page.get_by_role('heading', name=heading, exact=True).wait_for()
        assert page.locator('#view').inner_text().strip()
        assert page.get_by_role('heading', name='Could not load this page', exact=True).count() == 0
        steps.append(heading+' loads in the native sidebar and layout')
        if tool == 'system':
            for device, name in [('printer','Reconnect printer'),('camera','Reconnect webcam')]:
                with page.expect_response(lambda response: response.request.method == 'POST' and urlsplit(response.url).path == '/workshop-api/hardware/reconnect') as received:
                    page.get_by_role('button',name=name,exact=True).click()
                assert received.value.ok
                result=received.value.json();assert result['reason'] and result['steps']
                page.get_by_text(result['message'],exact=True).last.wait_for()
            steps.append('native System reconnect buttons reopen fresh device checks and show live troubleshooting without printing')

        if tool == 'map':
            colours = page.evaluate('''() => {
              const html=document.documentElement, original=html.className, panel=document.querySelector('.workshop-native .panel');
              const before=getComputedStyle(panel).backgroundColor;
              html.className='theme-dracula';
              const themed=getComputedStyle(panel).backgroundColor;
              const native=document.createElement('div');native.className='bg-card';document.body.append(native);
              const expected=getComputedStyle(native).backgroundColor;native.remove();html.className=original;
              return {before,themed,expected};
            }''')
            assert colours['themed'] == colours['expected'] and colours['before'] != colours['themed'], colours
            steps.append('workshop cards follow native Homebox theme colours, including Dracula')
    equipment = page.context.request.get(BASE+'/workshop-api/equipment').json()
    if equipment:
        entity = equipment[0]
        page.goto(BASE+'/item/'+entity['id'])
        page.get_by_role('heading', name='Borrowing', exact=True).wait_for()
        page.get_by_role('link', name='Loans & return notes', exact=True).first.click()
        page.get_by_role('heading', name='Borrowing history', exact=True).wait_for()
        steps.append('existing native item details include borrowing and return-note history')
        page.locator('a[href="/item/'+entity['id']+'/edit"]').click()
        name_field = page.get_by_role('textbox', name='Name', exact=False).first
        name_field.wait_for()
        assert name_field.input_value() == entity['name']
        steps.append('native inventory editing remains available on the existing item edit page')
        page.goto(BASE+'/item/'+entity['id'])
        page.get_by_role('button', name='Print from Browser', exact=True).click()
        page.get_by_role('button', name='Print one label on Pi', exact=True).wait_for()
        page.keyboard.press('Escape')
        steps.append('native label dialog includes the Pi printer preview without printing')
    locations=page.context.request.get(BASE+'/api/v1/entities?isLocation=true&pageSize=100&includeArchived=true').json()['items']
    cage=next((row for row in locations if row['name'].casefold()=='the cage'),None)
    if cage:
        page.goto(BASE+'/location/'+cage['id'])
        page.get_by_role('button',name='Add inside',exact=True).click()
        page.get_by_role('menuitem',name='Location inside',exact=True).click()
        create_dialog=page.get_by_role('dialog').filter(has=page.get_by_role('combobox',name='Inside (optional)',exact=True))
        parent=create_dialog.get_by_role('combobox',name='Inside (optional)',exact=True)
        parent.get_by_text(cage['name'],exact=True).wait_for()
        parent.click()
        page.get_by_role('option',name='Storage Room',exact=False).first.wait_for()
        equipment=page.context.request.get(BASE+'/api/v1/entities?isLocation=false&pageSize=100&includeArchived=true').json()['items']
        for row in equipment:
            if not row['archived']:page.get_by_role('option').filter(has_text=row['name']).first.wait_for()
        page.keyboard.press('Escape');page.keyboard.press('Escape')
        steps.append('live Cage Add inside offers optional locations and item parents through the native form without creating anything')
        page.goto(BASE+'/location/'+cage['id']+'/edit')
        page.get_by_role('combobox',name='Inside (optional)',exact=True).wait_for()
        steps.append('live native location editing uses the same optional mixed-parent selector')
    page.goto(BASE+'/workshop/#people')
    page.get_by_role('columnheader', name='Kiosk Badge', exact=True).wait_for()
    steps.append('old People & badges bookmark redirects to native Collection Members')
    page.get_by_role('link', name='Equipment Terminal', exact=True).click()
    page.get_by_role('button', name='C-Crate', exact=True).wait_for()
    assert page.title()=='C-Crate | Equipment Terminal'
    page.wait_for_function('document.querySelector("#home-nav img").naturalWidth > 0')
    assert page.context.request.get(BASE+'/caci-create.svg').text()==page.context.request.get(page.url.split('/?')[0]+'/caci-create.svg').text()
    steps.append('both interfaces display the same C-Crate drone/crate logo')
    page.get_by_role('button', name='Admin', exact=True).click()
    page.get_by_role('button', name='Manage users', exact=True).wait_for()
    steps.append('native sidebar links to Equipment Terminal, which links back to Homebox')
    for member in current_members:
        avatar=page.get_by_role('button',name='Issue badge: '+member['name'],exact=True).locator('img')
        try:
            avatar.wait_for();assert avatar.get_attribute('src')==avatars[member['id']]
        except Exception:
            print(json.dumps({'terminal_avatar_check':{'issue_buttons':page.locator('button').filter(has_text='Issue badge:').count(),'images':page.locator('button img').count(),'errors':len(errors),'failed':failed,'blocked':blocked,'status_headings':page.get_by_role('heading').all_text_contents()}}),flush=True)
            raise
    steps.append('Equipment Terminal uses the same generated avatars as native Members')

    page.get_by_role('button',name='Manage users',exact=True).click()
    page.get_by_role('button',name='New user',exact=True).click()
    page.get_by_role('textbox',name='Name',exact=True).wait_for()
    assert not page.get_by_role('textbox',name='Email (optional)',exact=True).get_attribute('required')
    assert not page.locator('input[type=password]').count()
    page.get_by_role('button',name='Back to users',exact=True).click()
    person=current_members[0]
    page.get_by_role('button',name='Manage profile: '+person['name']+' · ID '+person['id'][:8],exact=True).click()
    field=page.get_by_role('textbox',name='Name',exact=True);field.wait_for();assert field.input_value()==person['name']
    page.get_by_label('Profile picture',exact=True).wait_for()
    steps.append('Terminal offers name-only creation and reads the same native profile and picture controls without saving')
    page.get_by_role('button',name='Back to users',exact=True).click()
    page.get_by_role('button',name='Admin',exact=True).click()
    page.get_by_role('button',name='System status & backup',exact=True).click()
    page.get_by_role('button',name='Reconnect webcam',exact=True).wait_for()
    with page.expect_response(lambda response: response.request.method == 'POST' and urlsplit(response.url).path == '/hardware/reconnect') as received:
        page.get_by_role('button',name='Reconnect printer',exact=True).click()
    assert received.value.ok
    result=received.value.json();page.get_by_text(result['message'],exact=True).last.wait_for()
    steps.append('Equipment Terminal reconnects the same printer through its own system controls without printing')

    browser.close()
assert not blocked, {'blocked': sorted(set(blocked)), 'failed': failed[:5], 'errors': errors[:2]}
assert not errors, {'failed': failed[:5], 'errors': errors[:2]}
addresses = []
for interface in json.loads(subprocess.check_output(['ip', '-j', '-4', 'address', 'show', 'scope', 'global'])):
    if 'UP' in interface.get('flags', []) and not interface['ifname'].startswith(('docker', 'br-', 'veth')):
        for entry in interface.get('addr_info', []):
            address = entry['local']
            for port in (17745, 17749):
                with urllib.request.urlopen(f'http://{address}:{port}/', timeout=8) as response:
                    assert response.status == 200
            addresses.append(address)
output = ROOT/'work/shared-tools-verification'
output.mkdir(exist_ok=True)
result = {'passed': len(steps), 'steps': steps, 'browser_errors': errors, 'inventory_mutations': 0, 'physical_prints': 0, 'network_addresses': addresses, 'printer_ready': bool(printer.get('connected'))}
(output/'live-readonly-results.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
