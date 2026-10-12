#!/usr/bin/env python3
"""Browser fixture for the built C-Crate header and isolated Pi probes."""
import http.cookiejar
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from uuid import uuid4

SOURCE = pathlib.Path(__file__).resolve().parents[1]
LIVE = pathlib.Path('/home/user/Desktop/inventory-system')
for directory in (SOURCE/'ops', SOURCE/'kiosk', LIVE/'work/hardware/python'):
    sys.path.insert(0, str(directory))
from playwright.sync_api import sync_playwright
import hardware

NATIVE, BASE, COMPANION = 'http://127.0.0.1:17767', 'http://127.0.0.1:17765', 'http://127.0.0.1:17769'
BINARY = pathlib.Path(os.environ.get('HOMEBOX_VERIFY_NATIVE_BINARY', str(LIVE/'work/homebox-bin/homebox')))


def wait_for(url, process):
    for _ in range(150):
        try:
            urllib.request.urlopen(url, timeout=1).close()
            return
        except OSError:
            if process.poll() is not None:
                raise RuntimeError('Isolated fixture service exited before starting')
            time.sleep(.1)
    raise RuntimeError('Isolated fixture service startup timed out')


def response(base, path, method='GET', data=None, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer '+token
    req = urllib.request.Request(base+path, method=method, data=json.dumps(data).encode() if data is not None else None, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as result:
        body = result.read()
        return json.loads(body) if body else None


fixture = {
    'printer': {'device': 'printer', 'connected': True, 'reason': 'ready', 'message': 'SUPVAN printer ready.', 'steps': ['The Pi probe completed.']},
    'camera': {'device': 'camera', 'connected': False, 'reason': 'disconnected', 'message': 'The C920 webcam was not found.', 'steps': ['Connect the original C920 webcam to the Pi.']},
    'actions': {}, 'calls': [], 'hold_next_probe': False,
    'probe_started': threading.Event(), 'probe_release': threading.Event(),
    'probe_lock': threading.Lock(), 'active_probes': 0, 'max_active_probes': 0,
}


def reconnect(device):
    with fixture['probe_lock']:
        fixture['calls'].append(('POST', device))
        fixture['active_probes'] += 1
        fixture['max_active_probes'] = max(fixture['max_active_probes'], fixture['active_probes'])
        hold = fixture['hold_next_probe']
        if hold:
            fixture['hold_next_probe'] = False
    try:
        if hold:
            fixture['probe_started'].set()
            if not fixture['probe_release'].wait(15):
                raise TimeoutError('Deferred fixture probe was not released')
        return dict(fixture['actions'].get(device, fixture[device]))
    finally:
        with fixture['probe_lock']:
            fixture['active_probes'] -= 1


def camera_status():
    return dict(fixture['camera'])


hardware.reconnect = reconnect
hardware.camera_status = camera_status

with tempfile.TemporaryDirectory(prefix='device-status-fixture-') as directory:
    root = pathlib.Path(directory)
    (root/'data').mkdir()
    (root/'work/baseline').mkdir(parents=True)
    (root/'desktop').symlink_to(SOURCE/'desktop', target_is_directory=True)
    env = dict(os.environ, HBOX_WEB_HOST='127.0.0.1', HBOX_WEB_PORT='17767', HBOX_STORAGE_PREFIX_PATH=str(root/'data'),
               HBOX_DATABASE_SQLITE_PATH=str(root/'data/homebox.db')+'?_pragma=busy_timeout=999&_pragma=journal_mode=WAL&_fk=1&_time_format=sqlite',
               HBOX_AUTH_API_KEY_PEPPER=str(uuid4()), HBOX_OPTIONS_ALLOW_REGISTRATION='true',
               HBOX_OPTIONS_GITHUB_RELEASE_CHECK='false', HBOX_OPTIONS_ALLOW_ANALYTICS='false',
               WORKSHOP_ROOT=str(root), WORKSHOP_NATIVE_BASE=NATIVE,
               WORKSHOP_NATIVE_PORT='17767', WORKSHOP_COMPANION_PORT='17769', WORKSHOP_PORT='17765',
               HOMEBOX_UI_ROOT=str(SOURCE/'work/homebox-ui-build/.output/public'))
    (root/'work/ops').mkdir(parents=True)
    native_log = (root/'native.log').open('w')
    native_proc = subprocess.Popen([str(BINARY)], cwd=root, env=env, stdout=native_log, stderr=subprocess.STDOUT)
    companion = gateway = None
    try:
        wait_for(NATIVE+'/api/v1/status', native_proc)
        account = {'email': 'manager@fixture.invalid', 'name': 'Fixture Manager', 'password': 'fixture-only-password'}
        response(NATIVE, '/api/v1/users/register', 'POST', account)
        native_jar = http.cookiejar.CookieJar()
        native_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(native_jar))
        native_login = urllib.request.Request(NATIVE+'/api/v1/users/login', data=json.dumps({'username': account['email'], 'password': account['password']}).encode(), headers={'Content-Type': 'application/json'})
        with native_opener.open(native_login, timeout=15) as result:
            login = json.loads(result.read())
        token = next((cookie.value for cookie in native_jar if cookie.name == 'hb.auth.token'), None)
        if not token:
            raise RuntimeError('The isolated native login did not return an auth token')
        manager = response(NATIVE, '/api/v1/users/self', token=token)['item']
        group = manager['defaultGroupId']
        second = response(NATIVE, '/api/v1/groups', 'POST', {'name': 'Fixture second collection'}, token)
        second = second.get('item', second)
        other_group = second['id']

        def native_settings(method='GET', values=None):
            req = urllib.request.Request(NATIVE+'/api/v1/users/self/settings', method=method,
                data=json.dumps(values).encode() if values is not None else None,
                headers={'Content-Type': 'application/json'})
            with native_opener.open(req, timeout=15) as result:
                body = json.loads(result.read())
                return body.get('item', body)

        def save_fixture_preferences(**values):
            native_settings('PUT', values)
            saved = native_settings()
            assert all(saved.get(key) == value for key, value in values.items()), saved
            print('FIXTURE PREFERENCE READBACK', {key: saved.get(key) for key in values}, flush=True)

        save_fixture_preferences(displayLegacyHeader=False, collectionId=group)
        (root/'work/ops/desktop-managers.json').write_text(json.dumps({'managers': [
            {'user_id': manager['id'], 'group_id': group}, {'user_id': manager['id'], 'group_id': other_group},
        ]}))

        os.environ['WORKSHOP_NATIVE_BASE'] = NATIVE
        server_source = (SOURCE/'deploy/kiosk-server.py').read_text()
        server_source = server_source.replace("ROOT=pathlib.Path('/home/user/Desktop/inventory-system')", 'ROOT=pathlib.Path('+repr(str(root))+')')
        server_source = server_source[:server_source.index("print('Homebox companion listening")]
        scope = {}
        exec(compile(server_source, 'device-status-companion-fixture.py', 'exec'), scope)
        scope['BASE'] = NATIVE
        scope['same_origin'] = lambda origin, host: origin == BASE and host == '127.0.0.1:17765'
        companion = ThreadingHTTPServer(('127.0.0.1', 17769), scope['Handler'])
        threading.Thread(target=companion.serve_forever, daemon=True).start()

        import importlib.util
        spec = importlib.util.spec_from_file_location('device_status_gateway', SOURCE/'deploy/workshop-gateway.py')
        gateway_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gateway_module)
        gateway_module.ROOT = root
        gateway_module.NATIVE_PORT, gateway_module.COMPANION_PORT, gateway_module.PORT = 17767, 17769, 17765
        (root/'work/homebox-ui-current').symlink_to(SOURCE/'work/homebox-ui-build/.output/public', target_is_directory=True)
        gateway = ThreadingHTTPServer(('127.0.0.1', 17765), gateway_module.Handler)
        threading.Thread(target=gateway.serve_forever, daemon=True).start()

        latest_build = json.loads((SOURCE/'work/homebox-ui-build/.output/public/_nuxt/builds/latest.json').read_text())
        manifest_paths = ['_nuxt/builds/latest.json', f"_nuxt/builds/meta/{latest_build['id']}.json"]
        for relative in manifest_paths:
            with urllib.request.urlopen(BASE+'/'+relative, timeout=10) as served:
                served_body = served.read()
                local_body = (SOURCE/'work/homebox-ui-build/.output/public'/relative).read_bytes()
                print('FIXTURE ASSET', served.status, '/'+relative, len(served_body), hashlib.sha256(served_body).hexdigest(), 'exact=', served_body == local_body, flush=True)
                assert served_body == local_body

        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        request = urllib.request.Request(BASE+'/api/v1/users/login', data=json.dumps({'username': account['email'], 'password': account['password']}).encode(), headers={'Content-Type': 'application/json', 'Origin': BASE})
        with opener.open(request, timeout=15) as result:
            browser_login = json.loads(result.read())
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
            context = browser.new_context(viewport={'width': 1440, 'height': 900}, service_workers='block')
            context.add_cookies([{'name': cookie.name, 'value': cookie.value, 'url': BASE, 'httpOnly': True} for cookie in jar])
            context.add_cookies([
                {'name': 'hb.auth.session', 'value': 'true', 'url': BASE},
                {'name': 'hb.auth.attachment_token', 'value': browser_login['attachmentToken'], 'url': BASE},
            ])
            page = context.new_page()
            page_errors, requests, response_events, failures = [], [], [], {'next': False, 'denied_status': False, 'context': False}
            page.on('pageerror', lambda error: page_errors.append(str(error)))
            page.on('request', lambda request: requests.append(request))
            def log_response(result):
                path = '/' + '/'.join(result.url.split('/')[3:]).split('?')[0]
                response_events.append((path, result.status))
                if result.status >= 400 or '/_nuxt/builds/' in result.url:
                    print('BROWSER RESPONSE', result.status, path, flush=True)
            page.on('response', log_response)
            page.set_default_timeout(60000)
            page.on('console', lambda message: print('BROWSER', message.type, message.text, flush=True) if message.type == 'error' else None)
            page.on('requestfailed', lambda request: print('REQUEST FAILED', request.url, request.failure, flush=True))
            def fail_one(route):
                if failures['denied_status']:
                    failures['denied_status'] = False
                    route.fulfill(status=403, content_type='application/json', body='{"error":"manager access revoked in fixture"}')
                elif failures['next']:
                    failures['next'] = False
                    route.fulfill(status=503, content_type='application/json', body='{"error":"fixture probe failure"}')
                else:
                    route.continue_()
            def fail_context(route):
                if failures['context']:
                    failures['context'] = False
                    route.fulfill(status=503, content_type='application/json', body='{"error":"fixture context confirmation unavailable"}')
                else:
                    route.continue_()
            page.route('**/workshop-api/hardware/status', fail_one)
            page.route('**/workshop-api/context', fail_context)
            page.add_init_script("""
              const prefKey = 'homebox/preferences/location';
              const prefs = JSON.parse(localStorage.getItem(prefKey) || '{}');
              if (!prefs.theme) prefs.theme = 'light';
              localStorage.setItem(prefKey, JSON.stringify(prefs));
              window.__fixtureIntervals = [];
              const nativeInterval = window.setInterval.bind(window);
              window.setInterval = (callback, delay, ...args) => { window.__fixtureIntervals.push({callback, delay}); return nativeInterval(callback, delay, ...args); };
              window.__fixtureVisibility = 'visible';
              Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => window.__fixtureVisibility });
            """)
            page.goto(BASE+'/home', wait_until='domcontentloaded')
            page.wait_for_function("document.title.includes('C-Crate')")
            assert page.title().startswith('C-Crate')
            page.locator('a[href="/home"]').filter(has=page.get_by_text('C-Crate', exact=True)).first.wait_for()
            assert page.get_by_role('img', name='C-Crate logo: drone flying out of a crate', exact=True).count() == 1
            manifest = context.request.get(BASE+'/manifest.webmanifest').json()
            assert manifest['name'] == manifest['short_name'] == 'C-Crate'
            anonymous = browser.new_context()
            sign_in = anonymous.new_page()
            sign_in.goto(BASE+'/', wait_until='domcontentloaded')
            sign_in.locator('#login-username').wait_for()
            sign_in.get_by_role('heading', name='C-Crate', exact=True).wait_for()
            anonymous.close()
            print('PASS native sign-in, navigation, page title, manifest and drone/crate logo use C-Crate', flush=True)
            printer = page.get_by_role('button', name='SUPVAN printer (Pi): Connected. Show device details')
            camera = page.get_by_role('button', name='C920 camera (Pi): Disconnected. Show device details')
            printer.wait_for()
            camera.wait_for()
            assert page.locator('.device-status').count() == 1
            camera.click()
            panel = page.locator('[role="dialog"][aria-label="C920 camera (Pi) details"]')
            panel.get_by_text('Connect the original C920 webcam to the Pi.', exact=True).wait_for()
            page.screenshot(path=str(SOURCE/'work/device-status-desktop.png'), full_page=True)
            assert any('/workshop-api/hardware/status' in request.url and request.response() and request.response().status == 200 for request in requests)
            fixture['actions']['camera'] = {'device': 'camera', 'connected': True, 'reason': 'ready', 'message': 'C920 webcam ready.', 'steps': []}
            panel.get_by_text('Test connection', exact=True).click()
            panel.get_by_text('Connection test passed.', exact=True).wait_for()
            assert fixture['calls'][-1] == ('POST', 'camera')
            assert not any('/labels/print' in request.url for request in requests)
            print('PASS initial ready/disconnected states, Pi-specific labels, details and mocked Test connection without print', flush=True)

            fixture['actions']['printer'] = {'device': 'printer', 'connected': True, 'reason': 'ready', 'message': 'ready', 'steps': []}
            printer.click()
            ppanel = page.locator('[role="dialog"][aria-label="SUPVAN printer (Pi) details"]')
            ppanel.get_by_text('Reconnect', exact=True).click()
            ppanel.get_by_text('Reconnected and ready.', exact=True).wait_for()
            assert fixture['calls'][-1] == ('POST', 'printer')
            fixture['actions']['printer'] = {'device': 'printer', 'connected': False, 'reason': 'not_ready', 'message': 'Printer cover is open.', 'steps': ['Close the printer cover.']}
            ppanel.get_by_text('Test connection', exact=True).click()
            ppanel.get_by_text('Printer cover is open.', exact=True).wait_for()
            assert fixture['calls'][-1] == ('POST', 'printer')
            fixture['actions'].pop('printer', None)
            print('PASS Reconnect and failed connection actions use the authenticated probe endpoint only', flush=True)

            failures['next'] = True
            page.evaluate("window.dispatchEvent(new Event('focus'))")
            page.get_by_role('button', name='SUPVAN printer (Pi): Unavailable / Unknown. Show device details').wait_for()
            page.get_by_role('button', name='C920 camera (Pi): Unavailable / Unknown. Show device details').wait_for()
            print('PASS global probe failures clear stale green device states', flush=True)

            page.get_by_role('button', name='C920 camera (Pi): Unavailable / Unknown. Show device details').click()
            page.locator('[role="dialog"][aria-label="C920 camera (Pi) details"]').wait_for()
            calls_before_denial = len(fixture['calls'])
            failures['denied_status'] = True
            failures['context'] = True
            with page.expect_response(lambda result: '/workshop-api/hardware/status' in result.url and result.status == 403, timeout=30000):
                page.evaluate("window.dispatchEvent(new Event('focus'))")
            with page.expect_response(lambda result: '/workshop-api/context' in result.url and result.status == 503, timeout=30000):
                page.wait_for_timeout(100)
            page.wait_for_timeout(300)
            assert page.locator('.device-status').count() == 0, 'denied device access with failed context confirmation left manager controls visible'
            assert page.locator('[role="dialog"][aria-label="C920 camera (Pi) details"]').count() == 0, 'authorization denial left the details panel open'
            assert len(fixture['calls']) == calls_before_denial, 'a denied request triggered another hardware probe before identity confirmation'
            recovery_events_start = len(response_events)
            with page.expect_response(lambda result: '/workshop-api/context' in result.url and result.status == 200, timeout=30000):
                with page.expect_response(lambda result: '/workshop-api/hardware/status' in result.url and result.status == 200, timeout=30000):
                    page.evaluate("window.dispatchEvent(new Event('focus'))")
                    page.get_by_role('button', name='SUPVAN printer (Pi): Connected. Show device details').wait_for()
            recovery_events = response_events[recovery_events_start:]
            context_confirmed_at = next(i for i, event in enumerate(recovery_events) if '/workshop-api/context' in event[0] and event[1] == 200)
            status_recovered_at = next(i for i, event in enumerate(recovery_events) if '/workshop-api/hardware/status' in event[0] and event[1] == 200)
            assert context_confirmed_at < status_recovered_at, recovery_events
            assert page.locator('.device-status').count() == 1
            print('PASS denied probe clears controls/panel until context confirmation and focus recovers status', flush=True)

            status_count = lambda: sum('/workshop-api/hardware/status' in request.url for request in requests)
            before = status_count()
            page.evaluate("window.__fixtureVisibility='hidden'; document.dispatchEvent(new Event('visibilitychange'))")
            page.evaluate("window.__fixtureIntervals.find(entry => entry.delay === 30000).callback()")
            page.wait_for_timeout(150)
            assert status_count() == before
            page.evaluate("window.__fixtureVisibility='visible'; document.dispatchEvent(new Event('visibilitychange'))")
            page.wait_for_function("window.__fixtureIntervals.some(entry => entry.delay === 30000)")
            page.wait_for_function("document.querySelector('[aria-label^=\"SUPVAN printer (Pi):\"]')?.getAttribute('aria-label').includes('Connected')")
            assert status_count() > before
            before = status_count()
            page.evaluate("window.__fixtureIntervals.find(entry => entry.delay === 30000).callback()")
            page.wait_for_function(f"document.querySelector('[aria-label^=\"SUPVAN printer (Pi):\"]') && true")
            page.wait_for_timeout(150)
            assert status_count() > before
            print('PASS 30-second timer registration, visible polling and focus/visibility refresh handling', flush=True)

            trigger = page.get_by_role('button', name='SUPVAN printer (Pi): Connected. Show device details')
            trigger.focus(); page.keyboard.press('Enter')
            page.locator('[role="dialog"][aria-label="SUPVAN printer (Pi) details"]').wait_for()
            page.keyboard.press('Escape')
            page.locator('[role="dialog"][aria-label="SUPVAN printer (Pi) details"]').wait_for(state='hidden')
            print('PASS keyboard opens and dismisses the native Popover details panel', flush=True)

            for width in (1440, 900, 390):
                page.set_viewport_size({'width': width, 'height': 900})
                page.wait_for_timeout(100)
                header = page.locator('.sticky.top-0').first
                assert header.evaluate('(el) => el.scrollWidth <= el.clientWidth'), f'header overflow at {width}px'
                assert page.get_by_role('searchbox').is_visible()
                assert page.get_by_role('button', name='SUPVAN printer (Pi): Connected. Show device details').is_visible()
                assert page.locator('.device-status__name').all_text_contents() == ['Printer', 'Camera'], f'device names were not visible at {width}px'
                assert page.locator('.device-status__name').evaluate_all('els => els.every(el => { const s=getComputedStyle(el), r=el.getBoundingClientRect(); return s.visibility === "visible" && s.display !== "none" && s.position !== "absolute" && s.clip === "auto" && r.width >= 20 && r.height >= 10; })'), f'device names were visually hidden or clipped at {width}px'
                assert page.locator('.device-status__trigger').evaluate_all("els => els.every(el => getComputedStyle(el).whiteSpace === 'nowrap' && el.getBoundingClientRect().height <= 40)"), f'device labels wrapped at {width}px'
            page.screenshot(path=str(SOURCE/'work/device-status-mobile.png'), full_page=True)
            print('PASS desktop, tablet and mobile header layout keeps search and device controls usable', flush=True)

            pref_key = 'homebox/preferences/location'
            save_fixture_preferences(displayLegacyHeader=True, collectionId=group)
            page.evaluate("key => { const p=JSON.parse(localStorage.getItem(key)||'{}'); p.displayLegacyHeader=true; localStorage.setItem(key,JSON.stringify(p)); }", pref_key)
            page.set_viewport_size({'width': 900, 'height': 900})
            page.reload(wait_until='domcontentloaded')
            page.get_by_role('button', name='SUPVAN printer (Pi): Connected. Show device details').wait_for()
            page.wait_for_timeout(150)
            fixture['probe_started'].clear(); fixture['probe_release'].clear()
            fixture['max_active_probes'] = 0
            fixture['hold_next_probe'] = True
            before_remount = status_count()
            page.evaluate("window.dispatchEvent(new Event('focus'))")
            deadline = time.monotonic() + 10
            while not fixture['probe_started'].is_set() and time.monotonic() < deadline:
                page.wait_for_timeout(50)
            if not fixture['probe_started'].is_set():
                raise AssertionError('The focused production hardware/status request never reached the mocked hardware boundary')
            page.wait_for_function(f"document.querySelectorAll('.device-status__trigger').length === 2")
            assert status_count() == before_remount + 1, f'expected one held status request; got {status_count() - before_remount}'
            page.set_viewport_size({'width': 1440, 'height': 900})
            page.locator('.device-status.absolute').wait_for()
            page.wait_for_timeout(300)
            assert status_count() == before_remount + 1, f'a remounted instance sent a second status request while the first was pending: {status_count() - before_remount}'
            assert fixture['max_active_probes'] == 1
            with page.expect_request(lambda request: '/workshop-api/hardware/status' in request.url, timeout=30000) as current_check:
                fixture['probe_release'].set()
            assert current_check.value
            page.wait_for_function(f"window.__fixtureIntervals.some(entry => entry.delay === 30000)")
            deadline = time.monotonic() + 30
            while status_count() <= before_remount + 1 and time.monotonic() < deadline:
                page.wait_for_timeout(50)
            assert status_count() > before_remount + 1, 'the remounted instance did not make a current status check after settlement'
            page.get_by_role('button', name='SUPVAN printer (Pi): Connected. Show device details').wait_for()
            assert fixture['max_active_probes'] == 1, f'overlapping mocked hardware probes: {fixture["max_active_probes"]}'
            page.evaluate("localStorage.removeItem('__fixtureLegacyRemount')")
            print('PASS focused held probe survives breakpoint remount and sends a current check after settlement', flush=True)
            page.get_by_role('button', name='SUPVAN printer (Pi): Connected. Show device details').wait_for()
            page.wait_for_function("document.querySelector('.device-status')?.classList.contains('absolute')")
            assert page.locator('.device-status').count() == 1
            assert page.locator('.device-status').evaluate('(el) => { const r=el.getBoundingClientRect(); return r.width>0 && r.height>0; }')
            assert 'absolute' in page.locator('.device-status').get_attribute('class')
            page.set_viewport_size({'width': 900, 'height': 900})
            assert page.locator('.device-status').count() == 1
            print('PASS legacy header has exactly one active status instance on desktop and tablet', flush=True)

            save_fixture_preferences(displayLegacyHeader=False, collectionId=group)
            page.evaluate("([key, group]) => { const p=JSON.parse(localStorage.getItem(key)||'{}'); p.displayLegacyHeader=false; p.collectionId=group; localStorage.setItem(key,JSON.stringify(p)); }", [pref_key, group])
            page.reload(wait_until='domcontentloaded')
            page.get_by_role('button', name='SUPVAN printer (Pi): Connected. Show device details').wait_for()
            save_fixture_preferences(displayLegacyHeader=False, collectionId=other_group)
            transition_start = len(requests)
            try:
                with page.expect_response(lambda result: '/workshop-api/hardware/status' in result.url and result.request.headers.get('x-workshop-group') == other_group, timeout=30000) as group_probe:
                    page.get_by_role('combobox', name='Select Collection', exact=True).click()
                    page.get_by_role('option', name='Fixture second collection', exact=False).click()
            except Exception:
                print('COLLECTION TRACE', [(request.url.split('workshop-api/', 1)[-1].split('?', 1)[0], request.headers.get('x-workshop-group'), request.response().status if request.response() else None) for request in requests[transition_start:] if '/workshop-api/' in request.url], flush=True)
                raise
            assert group_probe.value.status == 200
            page.get_by_role('button', name='SUPVAN printer (Pi): Connected. Show device details').wait_for()
            assert 'Fixture second collection' in page.get_by_role('combobox', name='Select Collection', exact=True).inner_text()
            print('PASS collection transition refreshes device status for the selected collection', flush=True)

            page.evaluate("key => { const p=JSON.parse(localStorage.getItem(key)||'{}'); p.collectionId=null; localStorage.setItem(key,JSON.stringify(p)); }", pref_key)
            outsider = {'email': 'member@fixture.invalid', 'name': 'Fixture Member', 'password': 'fixture-only-password'}
            response(NATIVE, '/api/v1/users/register', 'POST', outsider)
            outsider_jar = http.cookiejar.CookieJar()
            outsider_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(outsider_jar))
            outsider_request = urllib.request.Request(BASE+'/api/v1/users/login', data=json.dumps({'username': outsider['email'], 'password': outsider['password']}).encode(), headers={'Content-Type': 'application/json', 'Origin': BASE})
            with outsider_opener.open(outsider_request, timeout=15) as result:
                outsider_login = json.loads(result.read())
            context.clear_cookies()
            context.add_cookies([{'name': cookie.name, 'value': cookie.value, 'url': BASE, 'httpOnly': True} for cookie in outsider_jar])
            context.add_cookies([{'name':'hb.auth.session','value':'true','url':BASE}, {'name':'hb.auth.attachment_token','value':outsider_login['attachmentToken'],'url':BASE}])
            with page.expect_response(lambda result: '/workshop-api/context' in result.url, timeout=30000) as outsider_context:
                page.reload(wait_until='domcontentloaded')
            assert outsider_context.value.status == 200
            page.get_by_text('Welcome, Fixture Member', exact=True).wait_for()
            assert page.locator('.device-status').count() == 0
            print('PASS account/manager identity transition clears trusted status and actions', flush=True)
            assert not page_errors, page_errors
            browser.close()
    finally:
        fixture['probe_release'].set()
        if gateway:
            gateway.shutdown(); gateway.server_close()
        if companion:
            companion.shutdown(); companion.server_close()
        native_proc.terminate()
        try:
            native_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            native_proc.kill()
        native_log.close()
