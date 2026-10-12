"""Browser reconnect checks with intercepted HTTP and a synthetic camera."""
import json
import pathlib
import sys
from urllib.parse import urlsplit

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'work/hardware/python'))
from playwright.sync_api import sync_playwright

writes, errors, steps = [], [], []
user = {'id': '20000000-0000-4000-8000-000000000001', 'name': 'Fixture user'}
office={'id':'30000000-0000-4000-8000-000000000001','name':'Fixture office','archived':False,'entityType':{'isLocation':True},'parent':None}
box={'id':'30000000-0000-4000-8000-000000000002','name':'Fixture box','archived':False,'quantity':1,'assetId':'2','entityType':{'id':'40000000-0000-4000-8000-000000000001','name':'Equipment','isLocation':False},'parent':{'id':office['id'],'name':office['name']}}
shelf={'id':'30000000-0000-4000-8000-000000000003','name':'Fixture shelf','archived':False,'entityType':{'isLocation':True},'parent':{'id':box['id'],'name':box['name']}}
with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path='/usr/bin/chromium', headless=True,
        args=['--no-sandbox', '--use-fake-device-for-media-stream'])
    page = browser.new_page(viewport={'width': 1100, 'height': 850}, permissions=['camera'])
    page.set_default_timeout(20000)
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.add_init_script("""const original=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
      window.cameraOpens=0;window.failCamera=false;
      navigator.mediaDevices.getUserMedia=async options=>{window.cameraOpens++;if(window.failCamera){window.failCamera=false;throw new DOMException('Fixture denied','NotAllowedError')}return original(options)};""")
    def handle(route):
        request = route.request; path = urlsplit(request.url).path
        if path == '/': route.fulfill(content_type='text/html', body=(ROOT/'kiosk/index.html').read_text()); return
        if path in ('/caci-create.svg','/favicon.svg'): route.fulfill(content_type='image/svg+xml', body=(ROOT/'kiosk/branding'/path.lstrip('/')).read_text()); return
        if path.endswith('.js'): route.fulfill(content_type='application/javascript', body=(ROOT/'kiosk'/path.lstrip('/')).read_text()); return
        if request.method == 'POST': writes.append((path, request.post_data_json if path != '/decode' else None))
        if path == '/api/session': data = {'user': user, 'generation': 1, 'instance': 'fixture'}
        elif path == '/api/members': data = [user,{'id':'20000000-0000-4000-8000-000000000002','name':'Second fixture user'}]
        elif path == '/api/locations': data = [office,shelf]
        elif path == '/api/inventory': data = [box]
        elif path == '/api/types': data = [box['entityType']]
        elif path == '/workshop/get': data = {'locations':[{**e,'parent_id':(e.get('parent') or {}).get('id'),'kind':'Location'} for e in (office,shelf)],'parents':[{**e,'parent_id':(e.get('parent') or {}).get('id'),'kind':'Location' if e['entityType']['isLocation'] else 'Item'} for e in (office,box,shelf)],'layout':None,'counts':{},'storage_types':['Location'],'types':[]}
        elif path == '/api/system': data = {'homebox':'active','companion':'active','homebox_version':'fixture','printer':{'connected':False},'camera':{'connected':False},'camera_devices':0,'free_gb':10,'private_backups':0}
        elif path == '/hardware/reconnect':
            device = request.post_data_json['device']
            data = {'connected': device == 'printer', 'message': 'Fixture printer reconnected.' if device == 'printer' else 'Another application is using the device.',
                    'steps': ['Inspect any unconfirmed output in Recovery before printing another copy.'] if device == 'printer' else ['Close other camera previews or applications.']}
        elif path == '/decode': data = {'codes':[], 'detections':[]}
        else: data = [] if path in ('/api/inventory','/api/members','/api/custody','/api/stock') else {}
        route.fulfill(content_type='application/json', body=json.dumps(data))
    page.route('**/*', handle)
    page.goto('http://127.0.0.1:17749/?mode=editor')
    page.wait_for_function("typeof capturePhoto==='function' && identified")

    assert page.title()=='C-Crate | Equipment Terminal'
    page.get_by_role('button', name='Home', exact=True).get_by_text('C-Crate',exact=True).wait_for()
    page.wait_for_function('document.querySelector("#home-nav img").naturalWidth > 0')
    steps.append('Terminal displays C-Crate name, title and the shared drone/crate logo')

    page.get_by_role('button',name='Admin',exact=True).click()
    first_avatar=page.get_by_role('button',name='Issue badge: Fixture user',exact=True).locator('img')
    first_avatar.wait_for();source=first_avatar.get_attribute('src')
    assert source.startswith('data:image/svg+xml,')
    assert source!=page.get_by_role('button',name='Issue badge: Second fixture user',exact=True).locator('img').get_attribute('src')
    page.reload();page.wait_for_function('identified');page.get_by_role('button',name='Admin',exact=True).click()
    first_avatar.wait_for();assert first_avatar.get_attribute('src')==source
    steps.append('Terminal avatars are local, different by identity and stable across reloads')
    page.evaluate('showSystem()')
    page.get_by_role('button', name='Reconnect printer', exact=True).click()
    page.get_by_text('Fixture printer reconnected.', exact=True).wait_for()
    page.get_by_role('button', name='Reconnect webcam', exact=True).click()
    page.get_by_text('Close other camera previews or applications.', exact=True).wait_for()
    assert [data['device'] for path, data in writes if path == '/hardware/reconnect'] == ['printer','camera']
    steps.append('Terminal reconnect buttons show device-specific results without printing')

    page.evaluate('locationForm()')
    parent=page.get_by_role('combobox',name='Inside (optional)',exact=True)
    parent.select_option(box['id']);assert parent.input_value()==box['id']
    assert 'Fixture office / Fixture box' in parent.locator('option').all_text_contents()
    parent.select_option('');assert parent.input_value()==''
    page.evaluate('startEnrollment()')
    parent=page.get_by_role('combobox',name='Inside (optional)',exact=True);parent.wait_for()
    page.get_by_role('textbox',name='Equipment name',exact=True).fill('Fixture parentless equipment')
    page.get_by_role('button',name='Review equipment',exact=True).click()
    page.get_by_text('Top level / no parent',exact=True).wait_for()
    steps.append('Terminal creates optional parents and offers item containers with full mixed paths')
    page.evaluate('resetTask();workshopStorage()')
    page.get_by_role('button',name='Fixture office',exact=False).last.click()
    page.get_by_role('button',name='Fixture box',exact=False).last.click()
    page.get_by_role('button',name='Fixture shelf',exact=False).last.wait_for()
    page.get_by_role('button',name='Add equipment inside',exact=True).wait_for()
    steps.append('Storage browser keeps a location visible inside an item and provides Add inside actions')
    page.evaluate('resetTask()')

    page.evaluate("enrollment={name:'Saved draft',serial:'Saved serial',photos:['saved-photo']};scanPurpose='serial';document.querySelector('#scan').click()")
    page.wait_for_function('scanStream?.active && typeof scanStream.getVideoTracks()[0].onended==="function" && cameraOpens===1')
    page.evaluate('const track=scanStream.getVideoTracks()[0];track.stop();track.onended()')
    page.get_by_text('Webcam disconnected. Check its USB cable, then choose Reconnect webcam. Your current work is saved.', exact=True).wait_for()
    page.get_by_role('button', name='Reconnect webcam', exact=True).last.click()
    page.wait_for_function('scanStream?.active && typeof scanStream.getVideoTracks()[0].onended==="function" && cameraOpens===2')
    assert page.evaluate("scanPurpose==='serial' && enrollment.name==='Saved draft' && enrollment.serial==='Saved serial' && enrollment.photos[0]==='saved-photo' && identified")
    steps.append('Scan reconnect opens a fresh stream and preserves scan purpose, draft and session')

    page.evaluate("window.photoDraft={photos:['saved-photo']};capturePhoto(photoDraft,()=>{})")
    page.get_by_role('button', name='Capture photo', exact=True).wait_for()
    page.wait_for_function('photoStream?.active && !Array.from(document.querySelectorAll("button")).find(b=>b.textContent==="Capture photo").disabled')
    page.evaluate('const track=photoStream.getVideoTracks()[0];track.stop();track.onended()')
    page.get_by_role('button', name='Reconnect webcam', exact=True).last.click()
    page.wait_for_function('photoStream?.active && cameraOpens===4')
    assert page.evaluate("photoDraft.photos.length===1 && photoDraft.photos[0]==='saved-photo' && identified")
    steps.append('Photo reconnect opens a fresh stream without losing captured photos')

    page.evaluate("stopPhoto();window.failCamera=true;document.querySelector('#scan').click()")
    page.get_by_text('Allow camera permission for this site in the browser, then choose Reconnect webcam.', exact=True).wait_for()
    page.get_by_role('button', name='Reconnect webcam', exact=True).last.click()
    page.wait_for_function('scanStream?.active && typeof scanStream.getVideoTracks()[0].onended==="function" && cameraOpens===6')
    steps.append('Permission failures explain the next step and leave an explicit retry available')
    assert not errors, errors
    assert not any(path in ('/label/print','/badge/print','/enroll/confirm','/problem/confirm','/checkout/confirm','/return/confirm') for path, _ in writes)
    browser.close()
result = {'passed':len(steps),'steps':steps,'browser_errors':errors,'physical_prints':0,'live_inventory_mutations':0,'camera':'Synthetic Chromium device'}
(ROOT/'work/reconnect-terminal-results.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
