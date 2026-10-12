#!/usr/bin/env python3
"""Verify Workshop map interfaces against a fresh native Homebox fixture.

Every database, manager record and served asset root is temporary. This verifier
never connects to an installed service and never performs physical outputs.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import importlib.util
import json
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlsplit
from http.server import ThreadingHTTPServer
from uuid import UUID, uuid4
from io import BytesIO

SOURCE = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SOURCE / 'ops'), str(SOURCE / 'kiosk'), str(SOURCE / 'work/hardware/python')]
from PIL import Image
from attachments import upload as upload_attachment
import badges
from homebox import Homebox
from ledger import Ledger
from native_jobs import NativeJobs
from native_fields import update_payload
from setup_native import submit
import hardware
import labels
from playwright.sync_api import sync_playwright


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print('PASS ' + message, flush=True)


def validate_ports(*ports: int) -> None:
    if any(not isinstance(port, int) or not 32768 <= port <= 60999 for port in ports):
        raise ValueError('Verifier ports must be in the unprivileged ephemeral range 32768–60999.')
    if len(set(ports)) != len(ports):
        raise ValueError('Choose distinct ephemeral ports.')


def validate_fixture_boundary(root: pathlib.Path, native: str, native_port: int) -> None:
    source = SOURCE.resolve(strict=True)
    script = pathlib.Path(__file__).resolve(strict=True)
    if not script.is_relative_to(source):
        raise RuntimeError('Verifier script is outside its explicit candidate source root.')
    app_modules = {sys.modules[item.__module__] for item in (Homebox, Ledger, NativeJobs, update_payload, submit)}
    app_modules.update((hardware, labels, badges, sys.modules[upload_attachment.__module__]))
    for module in app_modules:
        origin = pathlib.Path(module.__file__).resolve(strict=True)
        if not origin.is_relative_to(source):
            raise RuntimeError('A verifier application module is outside the candidate source root.')
    temporary_root = pathlib.Path(tempfile.gettempdir()).resolve(strict=True)
    resolved_root = root.resolve(strict=True)
    if root.is_symlink() or not resolved_root.is_relative_to(temporary_root) or resolved_root == temporary_root:
        raise RuntimeError('The verifier data root is not a fresh directory under the system temporary root.')
    parsed = urlsplit(native)
    if (parsed.scheme, parsed.hostname, parsed.port, parsed.path) != ('http', '127.0.0.1', native_port, ''):
        raise RuntimeError('Native fixture base does not match the selected loopback port.')

    def refuse_physical_output(*_args, **_kwargs):
        raise RuntimeError('Physical printer and camera operations are disabled in this verifier.')

    labels.probe = refuse_physical_output
    labels.print_label = refuse_physical_output
    labels.print_badge = refuse_physical_output
    labels.reprint_badge = refuse_physical_output
    hardware.probe = refuse_physical_output
    hardware.camera_status = refuse_physical_output
    hardware.reconnect = refuse_physical_output
    if any(getattr(module, name) is not refuse_physical_output
           for module, name in ((labels, 'probe'), (labels, 'print_label'), (labels, 'print_badge'),
                               (labels, 'reprint_badge'), (hardware, 'probe'),
                               (hardware, 'camera_status'), (hardware, 'reconnect'))):
        raise RuntimeError('Physical-operation refusal could not be installed.')


def run_checks(*, interface: str, port: int = 0, native_port: int = 0, outputs: str = 'disabled') -> None:
    if interface not in ('desktop', 'both') or outputs != 'disabled':
        raise ValueError('Use the isolated desktop or both interfaces with outputs disabled.')
    if port and not 32768 <= port <= 60999 or native_port and not 32768 <= native_port <= 60999:
        raise ValueError('Explicit verifier ports must be in the unprivileged ephemeral range 32768–60999.')
    port = port or free_port()
    native_port = native_port or free_port()
    companion_port = 0
    validate_ports(port, native_port)
    build = SOURCE / 'work/homebox-ui-build/.output/public'
    if not (build / 'index.html').is_file():
        raise RuntimeError('Build the current isolated Homebox UI before running this verifier.')
    binary = SOURCE / 'work/homebox-bin/homebox'
    if not binary.is_file():
        raise RuntimeError('The preserved disposable-fixture Homebox binary is unavailable.')

    with tempfile.TemporaryDirectory(prefix='workshop-map-disposable-') as temporary:
        root = pathlib.Path(temporary)
        native = f'http://127.0.0.1:{native_port}'
        gateway_base = f'http://127.0.0.1:{port}'
        (root / 'data').mkdir()
        (root / 'work/ops').mkdir(parents=True)
        (root / 'work/baseline').mkdir(parents=True)
        (root / 'work/kiosk-ui-current').symlink_to(SOURCE / 'kiosk', target_is_directory=True)
        (root / 'work/homebox-ui-current').mkdir()
        for name in ('ops', 'kiosk', 'program-files', 'label-ui'):
            (root / name).symlink_to(SOURCE / name, target_is_directory=True)
        import shutil
        shutil.copytree(build, root / 'work/homebox-ui-current', dirs_exist_ok=True)
        (root / 'desktop').symlink_to(SOURCE / 'desktop', target_is_directory=True)
        env = dict(os.environ, HBOX_WEB_HOST='127.0.0.1', HBOX_WEB_PORT=str(native_port),
                   WORKSHOP_NATIVE_BASE=native, WORKSHOP_NATIVE_PORT=str(native_port),
                   HBOX_STORAGE_PREFIX_PATH=str(root / 'data'),
                   HBOX_DATABASE_SQLITE_PATH=str(root / 'data/homebox.db') + '?_pragma=busy_timeout=999&_pragma=journal_mode=WAL&_fk=1&_time_format=sqlite',
                   HBOX_AUTH_API_KEY_PEPPER=str(uuid4()), HBOX_OPTIONS_ALLOW_REGISTRATION='true',
                   HBOX_OPTIONS_GITHUB_RELEASE_CHECK='false', HBOX_OPTIONS_ALLOW_ANALYTICS='false')
        validate_fixture_boundary(root, native, native_port)
        log = (root / 'native.log').open('w')
        native_process = subprocess.Popen([str(binary)], cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT)
        companion = gateway_server = None
        companion_log = None
        previous_env = {key: os.environ.get(key) for key in ('WORKSHOP_NATIVE_BASE', 'WORKSHOP_PORT',
                                                               'WORKSHOP_NATIVE_PORT', 'WORKSHOP_COMPANION_PORT',
                                                               'HOMEBOX_UI_ROOT')}
        try:
            os.environ.update({'WORKSHOP_NATIVE_BASE': native, 'WORKSHOP_PORT': str(port),
                               'WORKSHOP_NATIVE_PORT': str(native_port), 'WORKSHOP_COMPANION_PORT': str(companion_port),
                               'HOMEBOX_UI_ROOT': str(build)})
            for _ in range(150):
                if native_process.poll() is not None:
                    raise RuntimeError('Disposable native Homebox exited before readiness was requested.')
                try:
                    urllib.request.urlopen(native + '/api/v1/status', timeout=1).close()
                    break
                except OSError:
                    time.sleep(.1)
            else:
                raise RuntimeError('Disposable native Homebox startup timed out.')

            account = {'email': 'map-manager@fixture.invalid', 'name': 'Map Fixture Manager',
                       'password': 'isolated-fixture-password'}
            with urllib.request.urlopen(urllib.request.Request(native + '/api/v1/users/register',
                    data=json.dumps(account).encode(), headers={'Content-Type': 'application/json'}), timeout=15):
                pass
            (root / 'work/baseline/test-account.json').write_text(json.dumps(account))
            client = Homebox(root, base=native)
            jobs = NativeJobs(Ledger(root / 'work/ops/ledger.db'))
            manager = client.call('/api/v1/users/self')['item']
            group = manager['defaultGroupId']
            (root / 'work/ops/desktop-managers.json').write_text(json.dumps({'managers': [{'user_id': manager['id'], 'group_id': group}]}))
            client.call('/api/v1/entity-types', 'POST', {'name': 'Fixture tool', 'isLocation': False, 'icon': ''})
            type_id = next(row['id'] for row in client.call('/api/v1/entity-types') if row['name'] == 'Fixture tool')
            location = submit(client, jobs, group, manager['id'], 'create_location', str(uuid4()),
                              {'name': 'Fixture Storage Room', 'storage_kind': 'Rack', 'storage_code': 'MAP-1'})
            location_id = location['entity_id']
            tool = submit(client, jobs, group, manager['id'], 'create_asset', str(uuid4()),
                          {'name': 'Fixture Camera', 'location_id': location_id, 'type_id': type_id, 'reviewed': True})
            tool_id = tool['entity_id']
            child_result = submit(client, jobs, group, manager['id'], 'create_location', str(uuid4()),
                                  {'name': 'Fixture Shelf', 'storage_kind': 'Shelf', 'parent_id': location_id})
            shelf_id = child_result['entity_id']
            photo_bytes = BytesIO()
            Image.new('RGB', (2, 2), (24, 86, 120)).save(photo_bytes, format='JPEG')
            upload_attachment(client, location_id, 'Disposable native map photo.jpg', photo_bytes.getvalue())
            photo = next(row for row in client.entity(location_id)['attachments']
                         if row.get('title') == 'Disposable native map photo.jpg')
            check(bool(photo.get('id')), 'native photo fixture belongs to the selected temporary location')

            token = uuid4().hex + uuid4().hex
            (root / '.fixture-process-token').write_text(token)
            os.chmod(root / '.fixture-process-token', 0o600)
            ready_path = root / 'work/companion-ready.json'
            fixture_env = {key: value for key, value in os.environ.items()
                           if not key.startswith('HBOX_')}
            python_paths = [SOURCE / 'ops', SOURCE / 'kiosk',
                            SOURCE / 'program-files/runtime/hardware/python']
            python_paths.extend(pathlib.Path(item or '.').resolve() for item in
                                os.environ.get('PYTHONPATH', '').split(os.pathsep) if item)
            fixture_env.update({
                'WORKSHOP_ROOT': str(root), 'WORKSHOP_CODE_ROOT': str(root),
                'WORKSHOP_FIXTURE_PROCESS': '1', 'WORKSHOP_FIXTURE_TOKEN': token,
                'WORKSHOP_FIXTURE_READY_FILE': str(ready_path),
                'WORKSHOP_BIND_HOST': '127.0.0.1', 'WORKSHOP_COMPANION_PORT': '0',
                'WORKSHOP_NATIVE_BASE': native, 'HOMEBOX_UI_ROOT': str(root / 'work/homebox-ui-current'),
                'PYTHONPATH': os.pathsep.join(map(str, python_paths)),
            })
            companion_log = (root / 'companion.log').open('w')
            companion = subprocess.Popen([sys.executable, str(SOURCE / 'deploy/kiosk-server.py')],
                cwd=root, env=fixture_env, stdout=companion_log, stderr=subprocess.STDOUT)
            for _ in range(100):
                if companion.poll() is not None:
                    raise RuntimeError('Disposable companion exited before fixture readiness.')
                if ready_path.is_file():
                    readiness = json.loads(ready_path.read_text())
                    break
                time.sleep(.05)
            else:
                raise RuntimeError('Disposable companion fixture readiness timed out.')
            companion_port = readiness.get('port', 0)
            if (readiness.get('mode') != 'fixture-process' or readiness.get('pid') != companion.pid or
                    readiness.get('host') != '127.0.0.1' or
                    not isinstance(companion_port, int) or not 32768 <= companion_port <= 60999):
                raise RuntimeError('Disposable companion readiness did not prove its owned loopback listener.')

            gateway_spec = importlib.util.spec_from_file_location('disposable_workshop_gateway', SOURCE / 'deploy/workshop-gateway.py')
            gateway = importlib.util.module_from_spec(gateway_spec)
            gateway_spec.loader.exec_module(gateway)
            gateway.ROOT = root
            gateway.NATIVE_PORT = native_port
            gateway.COMPANION_PORT = companion_port
            gateway.PORT = port
            class TimedGatewayHandler(gateway.Handler):
                def send_response(self, code, message=None):
                    self._response_status = code
                    return super().send_response(code, message)

                def do_GET(self):
                    started = time.monotonic()
                    try:
                        return super().do_GET()
                    finally:
                        path = self.path.split('?', 1)[0]
                        if path.startswith(('/location/', '/item/', '/workshop-api/', '/api/v1/')):
                            print('GATEWAY GET', path, getattr(self, '_response_status', 'no-status'),
                                  round((time.monotonic() - started) * 1000), 'ms', flush=True)

            gateway_server = ThreadingHTTPServer(('127.0.0.1', port), TimedGatewayHandler)
            threading.Thread(target=gateway_server.serve_forever, daemon=True).start()

            jar = http.cookiejar.CookieJar()
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
            login = urllib.request.Request(gateway_base + '/api/v1/users/login',
                data=json.dumps({'username': account['email'], 'password': account['password']}).encode(),
                headers={'Content-Type': 'application/json', 'Origin': gateway_base})
            with opener.open(login, timeout=15) as response:
                login_result = json.loads(response.read())
                check(response.status == 200, 'native manager login uses only the temporary Homebox database')

            identity = None
            def api(path):
                headers = {'Origin': gateway_base}
                if identity:
                    headers['X-Workshop-Identity'] = identity
                request = urllib.request.Request(gateway_base + '/workshop-api/' + path,
                    headers=headers)
                with opener.open(request, timeout=20) as response:
                    return json.loads(response.read())

            context = api('context')
            identity = context['identity']
            check(context['manager'] and context['user']['id'] == manager['id'], 'desktop map receives the native manager identity')
            layout = api('workshop')
            check(any(row['id'] == location_id and row['name'] == 'Fixture Storage Room' for row in layout['locations']),
                  'desktop map reads native locations and preserves native UUIDs')
            view = api('workshop/view?id=' + tool_id + '&nested=0')
            check(view['path'][-1]['id'] == tool_id and view['path'][-1]['name'] == 'Fixture Camera',
                  'desktop view resolves the selected native item through its location path')
            drawing_id = str(uuid4())
            saved_document = {'version': 2, 'rooms': [{'id': str(uuid4()), 'location_id': location_id,
                'name': 'Fixture floor', 'width': 14, 'height': 20, 'unit': 'ft', 'approximate': False,
                'objects': [{'id': drawing_id, 'name': 'Original shelf label', 'kind': 'Rack',
                             'x': 1, 'y': 2, 'width': 3, 'height': 2, 'rotation': 0,
                             'location_id': shelf_id}]}]}
            save_request = urllib.request.Request(gateway_base + '/workshop-api/workshop/save',
                data=json.dumps({'schema_version': 2, 'revision': layout['revision'],
                                 'document': saved_document, 'request_key': str(uuid4())}).encode(),
                headers={'Content-Type': 'application/json', 'Origin': gateway_base,
                         'X-Workshop-Identity': identity, 'X-Workshop-Group': group,
                         'X-Workshop-Actor': manager['id']})
            try:
                with opener.open(save_request, timeout=20) as response:
                    saved = json.loads(response.read())
            except urllib.error.HTTPError as error:
                raise RuntimeError(f'Workshop save returned HTTP {error.code}: {error.read().decode(errors="replace")}') from error
            changed = client.entity(location_id)
            rename_payload = update_payload(changed); rename_payload['name'] = 'Fixture Storage Room renamed'
            client.call('/api/v1/entities/' + location_id, 'PUT', rename_payload)
            moved = client.entity(tool_id); move_payload = update_payload(moved); move_payload['parentId'] = shelf_id
            client.call('/api/v1/entities/' + tool_id, 'PUT', move_payload)
            refreshed_map = api('workshop')
            refreshed_view = api('workshop/view?id=' + tool_id + '&nested=0')
            shelf_view = api('workshop/view?id=' + shelf_id + '&nested=0')
            drawing = next(row for room in refreshed_map['document']['rooms'] for row in room['objects']
                           if row['id'] == drawing_id)
            check(refreshed_map['revision'] == saved['revision'] and (drawing['x'], drawing['y']) == (1, 2),
                  'native rename and move refresh do not alter saved drawing geometry or base revision')
            check(refreshed_view['selection']['matches'][0]['name'] == 'Fixture Shelf' and
                  refreshed_view['selection']['matches'][0]['root_name'] == 'Fixture Storage Room renamed' and
                  refreshed_view['path'][-2]['id'] == shelf_id,
                  'native linked drawing names and moved native parent paths refresh from Homebox')
            check(shelf_view['selection']['target_id'] == shelf_id and shelf_view['path'][-1]['id'] == shelf_id,
                  'desktop view resolves a directly selected child location')
            body = {'code': tool_id}
            resolve_request = urllib.request.Request(gateway_base + '/workshop-api/workshop/resolve',
                data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'Origin': gateway_base,
                                                         'X-Workshop-Identity': identity})
            with opener.open(resolve_request, timeout=20) as response:
                resolved = json.loads(response.read())
            check(resolved['entity_id'] == tool_id, 'manual native resolution returns the same selected UUID')
            document_started = time.monotonic()
            with urllib.request.urlopen(gateway_base + '/location/' + location_id, timeout=15) as response:
                document_status, document_body = response.status, response.read()
            index_body = (build / 'index.html').read_bytes()
            document_hash = __import__('hashlib').sha256(document_body).hexdigest()
            print('GATEWAY DOCUMENT', document_status, len(document_body), document_hash,
                  round((time.monotonic() - document_started) * 1000), 'ms', flush=True)
            check(document_status == 200 and document_body == index_body,
                  'isolated gateway serves the built index for a native detail route')

            with sync_playwright() as pw:
                browser = pw.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
                try:
                    page = browser.new_page(viewport={'width': 1280, 'height': 900})
                    browser_origin_failures = []
                    def desktop_origin_guard(route):
                        parsed = urlsplit(route.request.url)
                        if (parsed.scheme, parsed.hostname, parsed.port) == ('http', '127.0.0.1', port):
                            route.continue_()
                        else:
                            browser_origin_failures.append((route.request.method, parsed.netloc, parsed.path))
                            route.abort()
                    page.context.route('**/*', desktop_origin_guard)
                    page.set_default_timeout(15000)
                    browser_errors = []
                    page.on('pageerror', lambda error: browser_errors.append(str(error)))
                    page.on('console', lambda message: browser_errors.append('console: ' + message.text) if message.type == 'error' else None)
                    page.on('response', lambda response: browser_errors.append('HTTP ' + str(response.status) + ' ' + response.url) if '/workshop-api/' in response.url and response.status >= 400 else None)
                    browser_request_events = []
                    browser_request_records = {}
                    browser_request_ids = {}
                    next_browser_request_id = 0
                    navigation_started = time.monotonic()
                    gateway_origin = urlsplit(gateway_base)

                    def safe_fixture_route(value):
                        if not isinstance(value, str) or not value:
                            return None
                        try:
                            parsed = urlsplit(value)
                            if (parsed.scheme, parsed.hostname, parsed.port) != (
                                    gateway_origin.scheme, gateway_origin.hostname, gateway_origin.port):
                                return None
                            if parsed.username is not None or parsed.password is not None or parsed.fragment:
                                return None
                            query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
                            if parsed.path == '/workshop/map':
                                if set(query) - {'id', 'drawing_id'}:
                                    return None
                                safe_query = {}
                                for key, values in query.items():
                                    if len(values) != 1 or str(UUID(values[0])) != values[0]:
                                        return None
                                    safe_query[key] = values[0]
                            elif parsed.path == '/':
                                if query:
                                    return None
                                safe_query = {}
                            else:
                                parts = parsed.path.strip('/').split('/')
                                if (query or len(parts) not in (2, 3) or
                                        parts[0] not in ('item', 'location') or
                                        len(parts) == 3 and (parts[0] != 'location' or parts[2] != 'edit') or
                                        str(UUID(parts[1])) != parts[1]):
                                    return None
                                safe_query = {}
                            return {'scheme': parsed.scheme, 'host': parsed.hostname,
                                    'port': parsed.port, 'path': parsed.path,
                                    'query': safe_query}
                        except (ValueError, TypeError):
                            return None

                    def route_key(route):
                        return (route['path'], tuple(sorted(route['query'].items())))

                    def browser_event(name, request, status=None):
                        nonlocal next_browser_request_id
                        object_key = id(getattr(request, '_impl_obj', request))
                        if object_key not in browser_request_ids:
                            next_browser_request_id += 1
                            request_id = 'browser-%04d' % next_browser_request_id
                            browser_request_ids[object_key] = request_id
                            parsed_request = urlsplit(request.url)
                            query = parse_qs(parsed_request.query)
                            referer = safe_fixture_route(request.headers.get('referer'))
                            browser_request_records[request_id] = {
                                'id': request_id, 'method': request.method, 'path': parsed_request.path,
                                'query': {key: values[-1] for key, values in query.items()
                                          if key in ('id', 'nested') and values},
                                'referer': referer,
                                'resource_type': request.resource_type, 'request': request,
                                'events': [], 'response_status': None, 'finished': False,
                            }
                        request_id = browser_request_ids[object_key]
                        record = browser_request_records[request_id]
                        record['events'].append(name)
                        if status is not None:
                            record['response_status'] = status
                        if name == 'finished' or name.startswith('failed'):
                            record['finished'] = True
                        browser_request_events.append({
                            'id': request_id, 'event': name,
                            'ms': round((time.monotonic() - navigation_started) * 1000),
                            'method': record['method'], 'path': record['path'],
                            'query': record['query'], 'status': status,
                        })
                    page.on('request', lambda request: browser_event('request', request))
                    page.on('requestfinished', lambda request: browser_event('finished', request))
                    page.on('requestfailed', lambda request: browser_event('failed', request))
                    page.on('response', lambda response: browser_event('response', response.request,
                                                                        response.status))
                    page.context.add_cookies([{'name': cookie.name, 'value': cookie.value, 'url': gateway_base,
                                               'httpOnly': cookie.has_nonstandard_attr('HttpOnly')} for cookie in jar])
                    page.context.add_cookies([{'name': 'hb.auth.session', 'value': 'true', 'url': gateway_base},
                                              {'name': 'hb.auth.attachment_token', 'value': login_result['attachmentToken'], 'url': gateway_base}])
                    try:
                        page.goto(gateway_base + '/location/' + location_id, wait_until='domcontentloaded', timeout=15000)
                    except Exception:
                        print('BROWSER NAVIGATION DEBUG', page.url, repr(browser_request_events[-60:]),
                              repr(browser_errors), flush=True)
                        raise
                    map_link = page.get_by_role('link', name='Show on map', exact=True)
                    try:
                        map_link.wait_for()
                    except Exception:
                        print('BROWSER DEBUG title=' + page.title() + ' url=' + page.url + ' body=' + page.locator('body').inner_text()[:1200] + ' html=' + page.locator('body').inner_html()[:1200] + ' errors=' + repr(browser_errors), flush=True)
                        raise
                    check(map_link.get_attribute('href') == '/workshop/map?id=' + location_id,
                          'compiled native location page links to the UUID-specific Workshop map route')
                    map_link.click()
                    page.get_by_role('heading', name='Workshop & storage').wait_for(timeout=15000)
                    check('workshop/map?id=' + location_id in page.url,
                          'current compiled route initializes from the native location link')
                    initial_projection = page.evaluate("""async args => {
                      const response = await fetch('/workshop-api/workshop/view?id=' + encodeURIComponent(args.id) + '&nested=0',
                        {headers: {'X-Workshop-Identity': args.identity}});
                      return await response.json();
                    }""", {'id': location_id, 'identity': identity})
                    print('BROWSER ROOT VIEW SELECTION', repr(initial_projection.get('selection')),
                          'LINKS', page.locator('.workshop-selection a').evaluate_all("rows => rows.map(a => [a.textContent, a.getAttribute('href')])"), flush=True)
                    page.get_by_text('Show wider native coverage and search', exact=True).click()
                    search = page.get_by_role('searchbox', name='Search native equipment and storage')
                    search.fill('Fixture Shelf')
                    search_result = page.locator('.workshop-search-results button').filter(has_text=shelf_id)
                    try:
                        search_result.wait_for(timeout=10000)
                    except Exception:
                        print('SEARCH DEBUG', page.locator('.workshop-search-results').inner_text(), repr(browser_errors), flush=True)
                        raise
                    print('SEARCH RESULT ACCESSIBLE NAME', search_result.get_attribute('aria-label'), flush=True)
                    selected_reads_before = {event['id'] for event in browser_request_events
                                             if event['event'] == 'request' and
                                             event['path'].endswith('/workshop-api/workshop/view')}
                    search_result.click()
                    page.wait_for_url('**/workshop/map?id=' + shelf_id, timeout=15000)
                    check('id=' + shelf_id in page.url,
                          'native shelf drill-down updates the bookmarkable selected identity (' + page.url + '; ' + repr(browser_errors) + ')')
                    page.wait_for_function("id => document.querySelector('.workshop-selection')?.innerText.includes(id)",
                                            arg=shelf_id, timeout=15000)
                    coverage = page.locator('details.planner-coverage')
                    selection_link = page.locator('.workshop-selection a[href="/location/' + shelf_id + '"]')
                    selection_link.wait_for(state='attached', timeout=15000)
                    check(selection_link.get_attribute('href') == '/location/' + shelf_id,
                          'selected shelf resolves to its native record route')
                    page.wait_for_timeout(100)
                    selected_reads_after = {event['id'] for event in browser_request_events
                                            if event['event'] == 'request' and
                                            event['path'].endswith('/workshop-api/workshop/view')}
                    check(len(selected_reads_after - selected_reads_before) == 1,
                          'host-originated route update refreshes the selection exactly once')
                    view_projection = page.evaluate("""async args => {
                      const response = await fetch('/workshop-api/workshop/view?id=' + encodeURIComponent(args.id) + '&nested=0',
                        {headers: {'X-Workshop-Identity': args.identity}});
                      return await response.json();
                    }""", {'id': shelf_id, 'identity': identity})
                    print('BROWSER VIEW SELECTION', repr(view_projection.get('selection')), flush=True)
                    edit_photos = page.locator('.workshop-selection a[href="/location/' + shelf_id + '/edit"]')
                    edit_photos.wait_for(state='attached', timeout=15000)
                    photo_route = edit_photos.get_attribute('href')
                    check(photo_route == '/location/' + shelf_id + '/edit',
                          'selected shelf photo action retains the native UUID route')
                    page.goto(gateway_base + photo_route, wait_until='domcontentloaded', timeout=15000)
                    page.wait_for_url('**/location/' + shelf_id + '/edit', timeout=15000)
                    page.go_back(wait_until='domcontentloaded')
                    page.get_by_role('heading', name='Workshop & storage').wait_for(timeout=15000)
                    check('workshop/map?id=' + shelf_id in page.url,
                          'native photo-editor return restores the later selected shelf')
                    selected_record_link = page.locator('.workshop-selection a[href="/location/' + shelf_id + '"]')
                    selected_record_link.wait_for(state='attached', timeout=15000)
                    check(selected_record_link.count() == 1,
                          'selected native record link targets the shelf UUID exactly once')
                    page.goto(gateway_base + selected_record_link.get_attribute('href'),
                              wait_until='domcontentloaded', timeout=15000)
                    page.wait_for_url('**/location/' + shelf_id, timeout=15000)
                    page.go_back(wait_until='domcontentloaded')
                    page.get_by_role('heading', name='Workshop & storage').wait_for(timeout=15000)
                    check('workshop/map?id=' + shelf_id in page.url,
                          'native record return preserves the same selected shelf')
                    item_case_floor_ids = set(browser_request_records)
                    current_document_route = safe_fixture_route(page.url)
                    if current_document_route is None:
                        raise AssertionError('The item case started from an unrecognized same-origin document route.')
                    known_outgoing_routes = {route_key(current_document_route)}
                    for record in browser_request_records.values():
                        # SPA route changes do not create document requests. Preserve
                        # every validated Referer already observed, as well as document
                        # URLs, so late completions from visited views remain attributable.
                        route = record['referer'] or safe_fixture_route(record['request'].url)
                        if route is not None:
                            known_outgoing_routes.add(route_key(route))
                    projection_suffixes = ('/workshop-api/context', '/workshop-api/workshop',
                                           '/workshop-api/workshop/view', '/workshop-api/entity',
                                           '/workshop-api/loans', '/api/entity', '/api/loans',
                                           '/workshop-api/api/entity', '/workshop-api/api/loans')
                    prior_document_trace = [
                        {key: record[key] for key in ('id', 'method', 'path', 'query', 'referer', 'events',
                                                      'response_status', 'finished')}
                        for record in browser_request_records.values()
                        if record['id'] in item_case_floor_ids and
                        record['path'].endswith(projection_suffixes) and not record['finished']]
                    print('PRIOR PROJECTION LIFECYCLE AT ITEM CASE BOUNDARY',
                          repr(prior_document_trace), flush=True)
                    current_item_route = safe_fixture_route(gateway_base + '/item/' + tool_id)
                    if current_item_route is None:
                        raise AssertionError('The selected item document route is not a valid fixture UUID route.')
                    current_document_routes = {route_key(current_item_route)}
                    item_document_response = page.goto(gateway_base + '/item/' + tool_id,
                                                       wait_until='domcontentloaded', timeout=15000)
                    item_document_error = item_document_response.finished() if item_document_response else 'no response'
                    item_documents = [record for record in browser_request_records.values()
                                      if record['id'] not in item_case_floor_ids and
                                      record['path'] == '/item/' + tool_id and
                                      record['request'].resource_type == 'document']
                    check(item_document_response is not None and item_document_response.status == 200 and
                          item_document_error is None and bool(item_documents) and
                          item_documents[-1]['response_status'] == 200 and item_documents[-1]['finished'],
                          'the isolated item document completed successfully inside the declared query-proof case')
                    item_map_link = page.get_by_role('link', name='Show on map', exact=True)
                    item_map_link.wait_for(timeout=15000)
                    check(item_map_link.get_attribute('href') == '/workshop/map?id=' + tool_id,
                          'compiled native item page links to the UUID-specific Workshop map route')
                    item_map_link.click()
                    page.get_by_role('heading', name='Workshop & storage').wait_for(timeout=15000)
                    current_map_tool_route = safe_fixture_route(gateway_base + '/workshop/map?id=' + tool_id)
                    if current_map_tool_route is None:
                        raise AssertionError('The selected Workshop map route is not a valid fixture UUID route.')
                    current_document_routes.add(route_key(current_map_tool_route))
                    item_path = page.locator('.workshop-selection').get_by_text(
                        'Full native path: Fixture Storage Room renamed / Fixture Shelf / Fixture Camera', exact=True)
                    item_path.wait_for(state='attached', timeout=15000)
                    item_record_link = page.locator('.workshop-selection > a[href="/item/' + tool_id + '"]')
                    item_record_link.wait_for(state='attached', timeout=15000)
                    check('workshop/map?id=' + tool_id in page.url and item_record_link.count() == 1,
                          'compiled Workshop route initializes selected native item from the item detail link')
                    page.get_by_role('button', name='Edit', exact=True).click()
                    page.get_by_role('button', name='Inspector', exact=True).click()
                    page.get_by_role('button', name='Room settings', exact=True).click()
                    page.get_by_label('Room title').fill('Router draft')
                    page.get_by_role('button', name='Apply room changes').click()
                    def map_view_records():
                        return [record for record in browser_request_records.values()
                                if record['path'].endswith('/workshop-api/workshop/view')]

                    def map_read_records():
                        suffixes = ('/workshop-api/context', '/workshop-api/workshop',
                                    '/workshop-api/workshop/view', '/workshop-api/entity',
                                    '/workshop-api/loans', '/api/entity', '/api/loans',
                                    '/workshop-api/api/entity', '/workshop-api/api/loans')
                        return [record for record in browser_request_records.values()
                                if record['path'].endswith(suffixes)]

                    def wait_for_map_reads_to_settle(after_ids, description):
                        deadline = time.monotonic() + 8
                        previous_ids = None
                        while time.monotonic() < deadline:
                            records = []
                            outgoing = []
                            for record in map_read_records():
                                if after_ids is not None and record['id'] in after_ids:
                                    continue
                                referer = record['referer']
                                if referer is None:
                                    raise AssertionError('Map read has missing or invalid Referer metadata; request=' +
                                                         repr({key: record[key] for key in
                                                               ('id', 'method', 'path', 'query', 'events',
                                                                'response_status', 'finished')}))
                                key = route_key(referer)
                                is_current = key in current_document_routes
                                is_outgoing = key in known_outgoing_routes
                                if is_current and is_outgoing:
                                    raise AssertionError('Map read Referer is ambiguous between current and outgoing documents; '
                                                         'request=' + repr({key: record[key] for key in
                                                         ('id', 'method', 'path', 'query', 'referer', 'events',
                                                          'response_status', 'finished')}))
                                if is_current:
                                    records.append(record)
                                elif is_outgoing:
                                    outgoing.append(record)
                                else:
                                    raise AssertionError('Map read Referer is outside the declared fixture document routes; '
                                                         'request=' + repr({key: record[key] for key in
                                                         ('id', 'method', 'path', 'query', 'referer', 'events',
                                                          'response_status', 'finished')}))
                            pending = [record['id'] for record in records if not record['finished']]
                            current_ids = tuple(sorted(record['id'] for record in records))
                            if not pending and current_ids == previous_ids:
                                outgoing_trace = [{key: record[key] for key in
                                                   ('id', 'method', 'path', 'query', 'referer', 'events',
                                                    'response_status', 'finished')}
                                                  for record in outgoing]
                                print('KNOWN OUTGOING PROJECTION LIFECYCLE', repr(outgoing_trace), flush=True)
                                return records
                            previous_ids = current_ids if not pending else None
                            page.wait_for_timeout(20)
                        trace = [{key: record[key] for key in ('id', 'method', 'path', 'query',
                                                               'referer', 'events', 'response_status', 'finished')}
                                 for record in records]
                        outgoing_trace = [{key: record[key] for key in
                                           ('id', 'method', 'path', 'query', 'referer', 'events',
                                            'response_status', 'finished')}
                                          for record in map_read_records()
                                          if record['referer'] is not None and
                                          route_key(record['referer']) in known_outgoing_routes]
                        raise AssertionError(description + '; pending request ids=' + repr(pending) +
                                             '; lifecycle=' + repr(trace) +
                                             '; known outgoing lifecycle=' + repr(outgoing_trace))

                    # Finish any prior native projections before opening the counter
                    # boundary, including context/workshop precursors that can start
                    # a later view request. The selected item path/anchor above must
                    # already be rendered before this quiescent read boundary.
                    selected_tool_views = [record for record in map_view_records()
                                           if record['id'] not in item_case_floor_ids and
                                           record['referer'] is not None and
                                           route_key(record['referer']) in current_document_routes and
                                           record['method'] == 'GET' and
                                           record['query'] == {'id': tool_id, 'nested': '0'} and
                                           record['response_status'] == 200 and record['finished']]
                    check(bool(selected_tool_views) and
                          selected_tool_views[-1]['request'].response().json()
                          .get('selection', {}).get('target_id') == tool_id,
                          'the selected native item projection is complete before measuring the external query')
                    wait_for_map_reads_to_settle(item_case_floor_ids,
                                                 'Current item document map/context projections did not settle')
                    baseline_read_ids = {record['id'] for record in map_read_records()}
                    baseline_view_ids = {record['id'] for record in map_view_records()}
                    external_map_route = safe_fixture_route(
                        gateway_base + '/workshop/map?id=' + location_id +
                        '&drawing_id=' + saved_document['rooms'][0]['objects'][0]['id'])
                    if external_map_route is None:
                        raise AssertionError('The external query target is not a valid root/drawing fixture route.')
                    current_document_routes.add(route_key(external_map_route))
                    page.evaluate("""async args => {
                      const root=document.querySelector('#__nuxt');
                      const router=root?.__vue_app__?.config?.globalProperties?.$router;
                      if(!router)throw new Error('Nuxt router is not exposed for this disposable verification.');
                      await router.push({path:'/workshop/map',query:{id:args.locationId,drawing_id:args.drawingId}});
                    }""", {'locationId': location_id, 'drawingId': saved_document['rooms'][0]['objects'][0]['id']})
                    page.wait_for_url('**/workshop/map?id=' + location_id + '&drawing_id=' + saved_document['rooms'][0]['objects'][0]['id'], timeout=15000)
                    target_view = None
                    target_deadline = time.monotonic() + 15
                    while time.monotonic() < target_deadline:
                        stage_views = [record for record in map_view_records()
                                       if record['id'] not in baseline_view_ids and
                                       record['referer'] is not None and
                                       route_key(record['referer']) in current_document_routes]
                        target_view = next((record for record in stage_views
                                            if record['method'] == 'GET' and
                                            record['query'] == {'id': location_id, 'nested': '0'} and
                                            record['response_status'] == 200 and record['finished']), None)
                        if target_view:
                            break
                        page.wait_for_timeout(20)
                    if not target_view:
                        trace = [{key: record[key] for key in ('id', 'method', 'path', 'query',
                                                               'referer', 'events', 'response_status', 'finished')}
                                 for record in stage_views]
                        raise AssertionError('External selection did not complete a successful exact-root view; '
                                             'stage views=' + repr(trace))
                    target_response = target_view['request'].response()
                    target_projection = target_response.json()
                    check(target_projection.get('selection', {}).get('target_id') == location_id,
                          'external query receives a successful native view for the exact root UUID')
                    check(page.get_by_role('button', name='Save all room changes', exact=True).is_visible() and
                          'Router draft' in page.locator('.room-planner').inner_text(),
                          'query-only router update keeps the dirty room and full map draft mounted')
                    stage_reads = wait_for_map_reads_to_settle(
                        baseline_read_ids, 'External query read chain did not settle')
                    stage_views = [record for record in stage_reads
                                   if record['path'].endswith('/workshop-api/workshop/view') and
                                   record['referer'] is not None and
                                   route_key(record['referer']) in current_document_routes]
                    stage_trace = [{key: record[key] for key in ('id', 'method', 'path', 'query',
                                                                 'referer', 'events', 'response_status', 'finished')}
                                   for record in stage_views]
                    check(len(stage_views) == 1 and stage_views[0]['id'] == target_view['id'],
                          'external query-only update makes exactly one distinct view request; trace=' +
                          repr(stage_trace))
                    with page.expect_request(lambda request: request.url.endswith('/workshop-api/workshop/save')) as save_event:
                        page.get_by_role('button', name='Save all room changes', exact=True).click()
                    saved_request = json.loads(save_event.value.post_data or '{}')
                    page.locator('[data-room-save-state]').get_by_text('All room changes saved', exact=True).wait_for(timeout=15000)
                    expected_draft = json.loads(json.dumps(saved_document))
                    expected_draft['rooms'][0]['name'] = 'Router draft'
                    check(saved_request.get('schema_version') == 2 and
                          saved_request.get('revision') == saved['revision'] and
                          saved_request.get('document') == expected_draft,
                          'query-only update preserves the original base revision and entire geometry payload')
                    check(not browser_origin_failures,
                          'compiled Desktop requests remain confined to the disposable gateway origin')
                finally:
                    browser.close()

            if interface == 'both':
                badge = badges.Badges(jobs.ledger).issue(group, manager['id'], [manager['id']])
                companion_base = f'http://127.0.0.1:{companion_port}'
                with sync_playwright() as pw:
                    terminal_browser = pw.chromium.launch(executable_path='/usr/bin/chromium', headless=True,
                                                          args=['--no-sandbox'])
                    try:
                        terminal = terminal_browser.new_page(viewport={'width': 800, 'height': 480},
                                                             is_mobile=True, has_touch=True)
                        camera_focus_attempts = []
                        browser_origin_failures = []
                        def terminal_origin_guard(route):
                            parsed = urlsplit(route.request.url)
                            if parsed.path in ('/camera/focus', '/api/v1/camera/focus'):
                                camera_focus_attempts.append((route.request.method, parsed.path))
                                route.abort()
                            elif (parsed.scheme, parsed.hostname, parsed.port) in {
                                    ('http', '127.0.0.1', port),
                                    ('http', '127.0.0.1', companion_port)}:
                                route.continue_()
                            else:
                                browser_origin_failures.append((route.request.method, parsed.netloc, parsed.path))
                                route.abort()
                        terminal.context.route('**/*', terminal_origin_guard)
                        terminal.context.add_init_script("Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{getUserMedia:async()=>{throw new Error('Disposable verifier camera access is disabled.')}}})")
                        terminal.set_default_timeout(10000)
                        terminal_errors = []
                        terminal_requests = []
                        terminal_file_responses = []
                        terminal.on('pageerror', lambda error: terminal_errors.append(str(error)))
                        terminal.on('console', lambda message: terminal_errors.append(message.text)
                                    if message.type == 'error' else None)
                        terminal.on('request', lambda request: terminal_requests.append(
                            (request.method, urlsplit(request.url).port, urlsplit(request.url).path)))
                        terminal.on('response', lambda response: terminal_file_responses.append(
                            (response.status, response.headers.get('content-type', ''), response.url))
                            if urlsplit(response.url).path == '/api/file' else None)
                        terminal.context.add_cookies([{'name': cookie.name, 'value': cookie.value, 'url': gateway_base,
                                                       'httpOnly': cookie.has_nonstandard_attr('HttpOnly')} for cookie in jar])
                        terminal.context.add_cookies([{'name': 'hb.auth.session', 'value': 'true', 'url': gateway_base},
                                                      {'name': 'hb.auth.attachment_token',
                                                       'value': login_result['attachmentToken'], 'url': gateway_base}])
                        # The application hardcodes its normal native origin. Rewrite only this
                        # disposable browser context to the already-running temporary gateway.
                        def fixture_native_origin(route):
                            parsed = urlsplit(route.request.url)
                            allowed_paths = {
                                '/location/' + location_id,
                                '/location/' + location_id + '/edit',
                                '/item/' + tool_id,
                            }
                            if ((parsed.scheme, parsed.hostname, parsed.port) != ('http', '127.0.0.1', 17745) or
                                    route.request.method != 'GET' or parsed.path not in allowed_paths or parsed.query):
                                browser_origin_failures.append((route.request.method, parsed.netloc, parsed.path))
                                route.abort()
                                return
                            route.fulfill(status=302, headers={'Location': gateway_base + parsed.path,
                                                               'Cache-Control': 'no-store'}, body='')
                        terminal.context.route('http://127.0.0.1:17745/**', fixture_native_origin)
                        terminal.goto(companion_base + '/', wait_until='load', timeout=15000)
                        terminal.wait_for_function("document.querySelector('#identity')?.textContent === 'Scan badge to identify yourself'",
                                                   timeout=10000)
                        terminal.evaluate("async code=>routeScan(code)", badge['code'])
                        terminal.wait_for_function("document.querySelector('#identity')?.textContent === 'Map Fixture Manager'",
                                                   timeout=10000)
                        generic_scans_before_map = sum(1 for method, _, path in terminal_requests
                                                       if method == 'POST' and path == '/scan')
                        map_scan_result = terminal.evaluate(
                            "async id=>{scanPurpose='workshop_map';return await routeScan(id)}", location_id)
                        check(map_scan_result is True,
                              'Terminal map scan completes after opening the editor and selects the resolved UUID')
                        terminal.get_by_role('heading', name='Native browse and storage').wait_for(timeout=15000)
                        terminal.locator('.workshop-native-details').get_by_text(
                            'Full path: Fixture Storage Room renamed', exact=True).wait_for(timeout=15000)
                        photo_image = terminal.get_by_role('img', name='Disposable native map photo.jpg')
                        photo_image.wait_for(timeout=15000)
                        decoded_size = photo_image.evaluate("img=>img.decode().then(()=>[img.naturalWidth,img.naturalHeight])")
                        check(decoded_size == [2, 2],
                              'Terminal decodes both dimensions of the owned temporary native image')
                        file_url = urlsplit(photo_image.get_attribute('src'))
                        file_query = parse_qs(file_url.query, strict_parsing=True)
                        photo_responses = [entry for entry in terminal_file_responses
                                           if urlsplit(entry[2]).path == '/api/file']
                        check(file_query == {'entity': [location_id], 'attachment': [photo['id']]} and
                              any(status == 200 and content_type.startswith('image/') and
                                  parse_qs(urlsplit(url).query, strict_parsing=True) == file_query
                                  for status, content_type, url in photo_responses),
                              'Terminal decodes the actual temporary native photo by selected entity and attachment UUID')
                        check(any(method == 'POST' and path == '/workshop/resolve'
                                  for method, _, path in terminal_requests),
                              'Terminal map scan resolves through the read-only native UUID endpoint')
                        check(any(method == 'POST' and path == '/workshop/view'
                                  for method, _, path in terminal_requests),
                              'Terminal native details load through the selected UUID view')
                        generic_scans_after_map = sum(1 for method, _, path in terminal_requests
                                                       if method == 'POST' and path == '/scan')
                        check(generic_scans_after_map == generic_scans_before_map,
                              'Map-purpose scanning does not enter generic badge scan handling')
                        native_link = terminal.get_by_role('link', name='Open native record', exact=True)
                        check(native_link.is_visible(), 'Local Terminal exposes the selected native record link')
                        with terminal.expect_popup() as popup_info:
                            native_link.click()
                        native_popup = popup_info.value
                        native_popup.wait_for_url('**/location/' + location_id, timeout=15000)
                        check(urlsplit(native_popup.url).port == port,
                              'Terminal native links are confined to the disposable gateway origin')
                        native_popup.close()
                        check(not camera_focus_attempts,
                              'Terminal verifier never requests camera focus or physical camera access')
                        check(not browser_origin_failures,
                              'Terminal requests and native popups remain within disposable origins')
                        check(not terminal_errors, 'Terminal map verification has no browser errors')
                    finally:
                        terminal_browser.close()
        except Exception:
            log.flush()
            log_text = (root / 'native.log').read_text(errors='replace')[-6000:]
            print('DISPOSABLE VERIFIER FAILURE; native log tail:\n' + log_text, flush=True)
            raise
        finally:
            if gateway_server:
                gateway_server.shutdown(); gateway_server.server_close()
            if companion:
                companion.terminate()
                try:
                    companion.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    companion.kill(); companion.wait(timeout=5)
            if companion_log:
                companion_log.close()
            native_process.terminate()
            try:
                native_process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                native_process.kill(); native_process.wait(timeout=5)
            log.close()
            for key, value in previous_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--interface', choices=('desktop', 'both'), required=True)
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--native-port', type=int, default=0)
    parser.add_argument('--outputs', choices=('disabled',), default='disabled')
    args = parser.parse_args()
    run_checks(interface=args.interface, port=args.port, native_port=args.native_port, outputs=args.outputs)
    print('PASS disposable ' + args.interface + ' Workshop map verification', flush=True)


if __name__ == '__main__':
    main()
