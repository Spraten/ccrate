"""Terminal shelf-check regressions against the real kiosk UI and a local API fixture."""
from __future__ import annotations

import json
import os
import re
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
LOCATION = '11111111-1111-4111-8111-111111111111'
ASSET = '22222222-2222-4222-8222-222222222222'
GROUP = '33333333-3333-4333-8333-333333333333'
SERVICE_ACTOR = '44444444-4444-4444-8444-444444444444'
BADGE_ACTOR = '55555555-5555-4555-8555-555555555555'
READ_ONLY_MANAGER = '77777777-7777-4777-8777-777777777777'


class Fixture:
    """Small in-memory implementation of only the existing shelf-check routes."""
    def __init__(self):
        self.checks = {}
        self.requests = {}
        self.return_not_started = False
        self.calls = []
        self.forwarded = []
        self.drop_next_observe_response = False
        self.drop_next_cancel_response = False
        self.shared_user = 'alpha'
        self.decode_codes = []
        self.prints = []
        self.native_mutations = []
        self.read_only_manager = False
        self.suspended = False

    def check_count(self):
        return len(self.checks)

    def shape(self, check):
        return {
            'id': check['id'], 'group_id': GROUP, 'actor_id': SERVICE_ACTOR,
            'actor_label': 'Workshop service manager', 'location_id': LOCATION,
            'location_name': 'Rack A',
            'include_nested': False, 'started_at': '2026-10-09T12:00:00+00:00',
            'state': check['state'], 'revision': check['revision'],
            'original_snapshot': {'location': {'id': LOCATION, 'name': 'Rack A', 'path': []},
                                  'items': [{'id': ASSET, 'name': 'Camera', 'quantity': 3,
                                             'path': [{'id': LOCATION, 'name': 'Rack A'}]}]},
            'reviewed_snapshot': check.get('reviewed_snapshot'),
            'review_fingerprint': check['fingerprint'],
            'observations': list(check['observations']),
            'notes': check.get('notes', ''),
            'groups': {'observed_here': [], 'not_observed': [{'id': ASSET, 'name': 'Camera',
                       'quantity': 3, 'observed_quantity': None, 'path': [{'name': 'Rack A'}]}],
                       'checked_out': [{'id': ASSET, 'name': 'Camera', 'quantity': 3,
                       'observed_quantity': None, 'custody_conflict': True,
                       'path': [{'name': 'Rack A'}]}],
                       'unexpected_here': []},
            'changes': {'added': {'items': []}, 'removed': {'items': []},
                        'changed': {'items': []}, 'renamed': {'items': []}},
            'pending_operations': [], 'suspended_reason': 'Shelf location was deleted' if self.suspended else None, 'can_edit': not self.read_only_manager,
            'completed_at': '2026-10-09T12:01:00+00:00' if check['state'] == 'completed' else None,
            'cancelled_at': None, 'cancelled_by': None, 'cancel_reason': check.get('cancel_reason'), 'point_in_time': True,
        }

    def route(self, method, path, data):
        if path == '/workshop-api/context':
            if getattr(self, 'shared_context', None):
                return self.shared_context
            actor = READ_ONLY_MANAGER if self.read_only_manager else SERVICE_ACTOR
            return {'user': {'id': actor, 'name': 'Workshop manager'},
                    'group': {'id': GROUP, 'name': 'Workshop'}, 'manager': True,
                    'identity': 'fixture-manager-identity'}
        if path.startswith('/workshop-api/workshop/checks/'):
            path = path[len('/workshop-api'):]
        self.calls.append((method, path, data))
        check_id = data.get('id') or parse_qs(urlparse(path).query).get('id', [None])[0]
        if path.startswith('/api/session'):
            return {'user': {'id': BADGE_ACTOR, 'name': 'Badge user'}, 'instance': 'fixture-session',
                    'generation': 1, 'manager': True}
        if path.startswith('/api/inventory'):
            return []
        if path.startswith('/api/locations'):
            return [{'id': LOCATION, 'name': 'Rack A', 'isLocation': True, 'parent_id': None}]
        if path.startswith('/api/types'):
            return []
        if path.startswith(('/session/end', '/session/activity', '/scan/cancel')):
            return {'ok': True}
        if path.startswith('/workshop/get'):
            actor = READ_ONLY_MANAGER if self.read_only_manager else SERVICE_ACTOR
            return {'revision': 1, 'layout': None, 'document': {'version': 2, 'rooms': []},
                    'locations': [{'id': LOCATION, 'name': 'Rack A', 'parent_id': None, 'isLocation': True}],
                    'parents': [{'id': LOCATION, 'name': 'Rack A', 'parent_id': None,
                                 'isLocation': True}], 'counts': {}, 'types': [],
                    'workshop_context': {'group_id': GROUP, 'actor_id': actor,
                                         'group_label': 'Workshop', 'actor_label': 'Workshop manager'}}
        if path.startswith('/workshop/checks/start'):
            check = {'id': str(uuid4()), 'actor_id': SERVICE_ACTOR, 'state': 'draft', 'revision': 0, 'fingerprint': 'frozen-v0',
                     'observations': []}
            self.checks[check['id']] = check
            return self.shape(check)
        if path.startswith('/workshop/checks/list'):
            return [self.shape(check) for check in self.checks.values()]
        if path.startswith('/workshop/checks/get'):
            return self.shape(self.checks[check_id])
        if path.startswith('/workshop/checks/resolve'):
            if data.get('raw') == 'AMBIGUOUS-QR':
                return {'entity_id': None, 'message': 'Choose the matching equipment.',
                        'candidates': [{'id': ASSET, 'name': 'Camera one', 'path': []},
                                       {'id': '66666666-6666-4666-8666-666666666666',
                                        'name': 'Camera two', 'path': []}]}
            if data.get('raw') == LOCATION:
                return {'entity_id': None, 'message': 'Scan equipment, not a location.', 'candidates': []}
            return {'entity_id': ASSET, 'message': 'Camera', 'candidates': []}
        if path.startswith('/workshop/checks/observe'):
            check = self.checks[check_id]
            observation = {'entity_id': data['entity_id'], 'method': data['method'],
                           'observed_quantity': data.get('observed_quantity', 1),
                           'request_key': data['request_key']}
            check['observations'] = [observation]
            check['revision'] += 1
            self.requests[data['request_key']] = self.shape(check)
            if self.drop_next_observe_response:
                self.drop_next_observe_response = False
                raise ConnectionAbortedError('committed observation response deliberately dropped')
            return self.shape(check)
        if path.startswith('/workshop/checks/request'):
            if self.return_not_started:
                return {'status': 'not_started'}
            saved = self.requests[data['request_key']]
            return {'status': 'completed', 'action': 'observe', 'result': saved}
        if path.startswith('/workshop/checks/notes'):
            check = self.checks[check_id]
            check['notes'] = data['notes']
            check['revision'] += 1
            return self.shape(check)
        if path.startswith('/workshop/checks/refresh'):
            check = self.checks[check_id]
            check['revision'] += 1
            check['fingerprint'] = 'refreshed-v1'
            check['reviewed_snapshot'] = {'location': {'id': LOCATION, 'name': 'Rack A'},
                                          'items': [{'id': ASSET, 'name': 'Camera', 'quantity': 3}]}
            return self.shape(check)
        if path.startswith('/workshop/checks/finish'):
            check = self.checks[check_id]
            check['state'] = 'completed'
            check['revision'] += 1
            return self.shape(check)
        if path.startswith('/workshop/checks/cancel'):
            check = self.checks[check_id]
            check['state'] = 'cancelled'
            check['cancel_reason'] = data.get('reason')
            check['revision'] += 1
            return self.shape(check)
        if path == '/decode':
            codes, self.decode_codes = self.decode_codes, []
            return {'codes': codes, 'detections': [], 'width': 640, 'height': 480}
        raise AssertionError(f'Unexpected fixture route: {method} {path}')

class Handler(SimpleHTTPRequestHandler):
    fixture = None
    shared_endpoint = None
    shared_identity = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / 'kiosk'), **kwargs)

    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path.startswith(('/api/', '/workshop/', '/workshop-api/')):
            return self.respond_api('GET')
        super().do_GET()

    def do_POST(self):
        return self.respond_api('POST')

    def respond_api(self, method):
        length = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(length) if length else b''
        path = urlparse(self.path).path
        data = json.loads(raw or b'{}') if method == 'POST' and path != '/decode' else {}
        if path.startswith('/api/v1/'):
            self.fixture.native_mutations.append((method, self.path, data))
            value, status = {'error': 'Native requests are blocked in the shelf-check fixture.'}, 501
        elif path.rstrip('/') in ('/label/print', '/badge/print'):
            self.fixture.prints.append((method, self.path, data))
            value, status = {'error': 'Print requests are blocked in the shelf-check fixture.'}, 501
        else:
            value = None
            status = 200
        if value is not None:
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        route_path = path.removeprefix('/workshop-api')
        if self.shared_endpoint and route_path.startswith('/workshop/checks/'):
            self.fixture.calls.append((method, self.path, data))
            request_path = self.path if path.startswith('/workshop-api/') else '/workshop-api' + self.path
            request = Request(self.shared_endpoint + request_path, data=raw if method == 'POST' else None,
                              headers={'Content-Type': 'application/json', 'X-Workshop-Identity': self.shared_identity,
                                       'X-Fixture-User': self.fixture.shared_user, 'Origin': 'http://' + self.headers['Host']},
                              method=method)
            try:
                with urlopen(request, timeout=10) as response:
                    body = response.read()
                    status = response.status
            except Exception as error:
                body = json.dumps({'error': str(error)}).encode()
                status = getattr(error, 'code', 502)
            self.fixture.forwarded.append((self.path, status, body.decode(errors='replace')))
            if route_path.startswith('/workshop/checks/observe') and self.fixture.drop_next_observe_response:
                self.fixture.drop_next_observe_response = False
                self.close_connection = True
                return
            if route_path.startswith('/workshop/checks/cancel') and self.fixture.drop_next_cancel_response:
                self.fixture.drop_next_cancel_response = False
                self.close_connection = True
                return
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        try:
            value = self.fixture.route(method, self.path, data)
        except ConnectionAbortedError:
            self.close_connection = True
            return
        if self.shared_endpoint and path == '/workshop/get':
            context = self.fixture.shared_context
            value['workshop_context'].update({'group_id': context['group']['id'],
                'actor_id': context['user']['id'], 'group_label': context['group'].get('name', 'Workshop'),
                'actor_label': context['user'].get('name', 'Workshop manager')})
        body = json.dumps(value).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class TerminalShelfChecksBrowserTests(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture()
        endpoint = os.environ.get('SHELF_CHECKS_FIXTURE_URL')
        identity = None
        self.shared_baseline = None
        if endpoint:
            with urlopen(endpoint + '/__fixture__/state', timeout=5) as response:
                self.shared_baseline = json.loads(response.read())
                identity = self.shared_baseline['manager1_context']['identity']
            ctx = self.shared_baseline['manager1_context']
            self.fixture.shared_context = ctx
        handler = type('FixtureHandler', (Handler,), {'fixture': self.fixture,
            'shared_endpoint': endpoint, 'shared_identity': identity})
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.server.server_close)
        self.playwright = sync_playwright().start()
        self.addCleanup(self.playwright.stop)
        self.browser = self.playwright.chromium.launch(headless=True, executable_path='/usr/bin/chromium')
        self.addCleanup(self.browser.close)
        self.context = self.browser.new_context(viewport={'width': 800, 'height': 480}, is_mobile=True, has_touch=True)
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.set_default_timeout(3000)
        self.page.set_default_navigation_timeout(10000)
        self.page.add_init_script('''if(!navigator.mediaDevices)Object.defineProperty(navigator,'mediaDevices',{value:{}});
            navigator.mediaDevices.enumerateDevices=async()=>[];
            navigator.mediaDevices.getUserMedia=async()=>{
              const canvas=document.createElement('canvas');canvas.width=640;canvas.height=480;
              const stream=canvas.captureStream(15);window.syntheticCameraStream=stream;return stream;
            };
            Object.defineProperty(HTMLVideoElement.prototype,'readyState',{get(){return this.srcObject?2:0}});
            Object.defineProperty(HTMLVideoElement.prototype,'videoWidth',{get(){return 640}});
            Object.defineProperty(HTMLVideoElement.prototype,'videoHeight',{get(){return 480}});
            window.print=()=>{window.__printAttemptCount=(window.__printAttemptCount||0)+1};
            const draw=CanvasRenderingContext2D.prototype.drawImage;
            CanvasRenderingContext2D.prototype.drawImage=function(source,...args){
              if(source instanceof HTMLVideoElement){this.fillStyle='#ffffff';this.fillRect(0,0,this.canvas.width,this.canvas.height);return}
              return draw.call(this,source,...args);
            };
        ''')
        self.page.goto(f'http://127.0.0.1:{self.server.server_port}/index.html', wait_until='domcontentloaded')
        self.page.wait_for_function("document.querySelector('#status')?.textContent.includes('connected')")
        self.initial_check_count = self.check_count()

    def check_count(self):
        endpoint = os.environ.get('SHELF_CHECKS_FIXTURE_URL')
        if not endpoint:
            return self.fixture.check_count()
        with urlopen(endpoint + '/__fixture__/state', timeout=5) as response:
            return json.loads(response.read())['check_count']

    def check_record(self, check_id):
        if check_id in self.fixture.checks:
            return self.fixture.checks[check_id]
        endpoint = os.environ['SHELF_CHECKS_FIXTURE_URL']
        with urlopen(endpoint + '/__fixture__/state', timeout=5) as response:
            state = json.loads(response.read())
        return next(row['result'] for row in reversed(state['requests']) if row.get('result', {}).get('id') == check_id)

    def test_map_editor_controls_fit_terminal_width_without_wrapping(self):
        self.page.evaluate('workshopOpen()')
        self.page.locator('.task5-toolbar').wait_for()
        self.page.get_by_role('button', name='Edit', exact=True).click()
        self.page.get_by_role('button', name='New room', exact=True).click()
        metrics = self.page.locator('.task5-view-tools').evaluate('''element => ({
            toolsWidth: element.clientWidth,
            toolsScrollWidth: element.scrollWidth,
            toolbarWidth: element.parentElement.querySelector('.task5-toolbar').clientWidth,
            toolbarScrollWidth: element.parentElement.querySelector('.task5-toolbar').scrollWidth,
            height: element.getBoundingClientRect().height,
            snapHeight: element.querySelector('[aria-label="Snap to quarter-foot grid"]')
                .parentElement.getBoundingClientRect().height
        })''')
        self.assertLessEqual(metrics['toolsScrollWidth'], metrics['toolsWidth'] + 1, metrics)
        self.assertLessEqual(metrics['toolbarScrollWidth'], metrics['toolbarWidth'] + 1, metrics)
        self.assertGreater(metrics['height'], 0, metrics)
        self.assertLess(metrics['snapHeight'], 40, metrics)

    def open_check(self, location=LOCATION, check_id=None):
        self.page.evaluate('''([locationId, checkId]) => {
            if(typeof workshopCheckOpen !== 'function') throw new Error('Terminal shelf-check workflow is missing');
            return workshopCheckOpen(locationId, checkId);
        }''', [location, check_id])

    def test_terminal_uncertain_reopen(self):
        self.fixture.drop_next_observe_response = True
        self.page.evaluate('''() => {
            if(typeof workshopCheckOpen !== 'function') throw new Error('Terminal shelf-check workflow is missing');
            return workshopCheckOpen(''' + json.dumps(LOCATION) + ''');
        }''')
        self.page.get_by_role('button', name='Start shelf check').click()
        self.page.get_by_role('button', name='Record observed quantity').click()
        check_id = self.page.evaluate('terminalCheck.id')
        self.page.evaluate("document.querySelector('[aria-label=\\\"Observed quantity\\\"]').click()")
        self.page.get_by_role('dialog', name='Touchscreen search keyboard').get_by_role('button', name='Key 2').click()
        self.page.get_by_role('button', name='Use tally').click()
        self.page.get_by_role('button', name='Save observation').click()
        self.page.get_by_text('result is uncertain', exact=False).wait_for()
        pending = json.loads(self.page.evaluate('''() => localStorage.getItem(terminalCheckPendingKey(terminalCheckContext))'''))
        self.assertTrue(pending['request_key'])
        self.page.wait_for_function('!terminalCheckBusy')
        self.page.get_by_role('button', name='Pause check').click()
        self.page.reload()
        self.page.wait_for_function("document.querySelector('#status')?.textContent.includes('connected')")
        self.open_check(check_id=check_id)
        self.page.get_by_role('button', name='Check saved result').click()
        self.page.get_by_text('observed 2', exact=False).first.wait_for()
        self.page.get_by_text('observed 2 · expected', exact=False).first.wait_for()
        self.assertEqual(self.check_count(), self.initial_check_count + 1)
        check_id = pending['check_id']
        record = self.check_record(check_id)
        self.assertEqual(record['revision'], 1)
        self.assertNotEqual(record['actor_id'], BADGE_ACTOR)
        if getattr(self.fixture, 'shared_context', None):
            self.assertEqual(record['group_id'], self.fixture.shared_context['group']['id'])
            self.assertEqual(record['actor_id'], self.fixture.shared_context['user']['id'])
        if os.environ.get('SHELF_CHECKS_FIXTURE_URL'):
            with urlopen(os.environ['SHELF_CHECKS_FIXTURE_URL'] + '/__fixture__/state', timeout=5) as response:
                current_requests = json.loads(response.read())['requests']
            actions = [row['action'] for row in current_requests]
            prior = [row['action'] for row in self.shared_baseline['requests']]
            self.assertEqual(actions.count('observe') - prior.count('observe'), 1)
            self.assertEqual(actions.count('request') - prior.count('request'), 0)
        else:
            self.assertEqual(sum(path.startswith('/workshop/checks/observe') for _, path, _ in self.fixture.calls), 1)
            self.assertEqual(sum(path.startswith('/workshop/checks/request') for _, path, _ in self.fixture.calls), 1)
        self.assertEqual(self.page.get_by_text('Revision 1', exact=False).count(), 1)
        self.assertEqual(self.errors, [])
        self.page.evaluate('window.confirm=()=>true')
        self.page.get_by_role('button', name='Refresh live review').click()
        self.page.wait_for_function('terminalCheck.revision===2 && !terminalCheckBusy')
        self.page.get_by_role('button', name='Finish shelf check').click()
        self.page.get_by_role('button', name='Confirm finish shelf check').click()
        self.page.wait_for_function("terminalCheck.state==='completed' && !terminalCheckBusy")
        self.page.get_by_text('Shelf check completed.', exact=False).wait_for()

    def test_other_manager_cancel_recovers_dropped_committed_result(self):
        endpoint = os.environ.get('SHELF_CHECKS_FIXTURE_URL')
        if not endpoint:
            self.skipTest('Requires the real disposable ShelfChecks API and Ledger fixture.')
        self.open_check(location=LOCATION)
        self.page.get_by_role('button', name='Start shelf check').click()
        self.page.wait_for_function('terminalCheck?.id && !terminalCheckBusy')
        check_id = self.page.evaluate('terminalCheck.id')
        owner_id = self.page.evaluate('terminalCheck.actor_id')
        suspend = Request(endpoint + '/__fixture__/suspend-shelf', data=b'{}',
                          headers={'Content-Type': 'application/json'}, method='POST')
        with urlopen(suspend, timeout=5) as response:
            self.assertTrue(json.loads(response.read())['suspended'])
        with urlopen(endpoint + '/__fixture__/state', timeout=5) as response:
            state = json.loads(response.read())
        manager_b = state['manager2_context']
        self.fixture.shared_context = manager_b
        self.fixture.shared_user = 'manager2'
        self.server.RequestHandlerClass.shared_identity = manager_b['identity']
        self.page.evaluate('''([locationId, checkId]) => workshopCheckOpen(locationId, checkId)''', [LOCATION, check_id])
        self.page.wait_for_function('terminalCheck?.id && !terminalCheckBusy')
        self.assertFalse(self.page.evaluate('terminalCheck.can_edit'))
        self.assertTrue(self.page.evaluate('terminalCheck.suspended_reason'))
        self.assertEqual(self.page.evaluate('terminalCheckContext.actor_id'), manager_b['user']['id'])
        self.page.evaluate('window.confirm=()=>true; window.prompt=()=>"Manager B cancellation"')
        self.fixture.drop_next_cancel_response = True
        self.page.get_by_role('button', name='Cancel shelf check').click()
        self.page.get_by_text('result is uncertain', exact=False).wait_for()
        pending = self.page.evaluate('''() => JSON.parse(localStorage.getItem(terminalCheckPendingKey(terminalCheckContext)))''')
        self.assertEqual(pending['action'], 'cancel')
        self.assertTrue(pending['request_key'])
        self.page.get_by_role('button', name='Check saved result').click()
        self.page.get_by_text('Recovered the exact saved shelf-check result', exact=False).wait_for()
        self.page.get_by_text('cancelled', exact=False).first.wait_for()
        self.assertEqual(self.page.evaluate('terminalCheck.state'), 'cancelled')
        self.assertIsNone(self.page.evaluate('localStorage.getItem(terminalCheckPendingKey(terminalCheckContext))'))
        with urlopen(endpoint + '/__fixture__/state', timeout=5) as response:
            recovered = json.loads(response.read())
        row = next(row for row in recovered['requests'] if row['request_key'] == pending['request_key'])
        self.assertEqual(row['action'], 'cancel')
        self.assertEqual(row['result']['actor_id'], owner_id)
        self.assertEqual(row['result']['cancelled_by'], manager_b['user']['id'])
        self.assertEqual(row['result']['state'], 'cancelled')
        self.assertEqual(sum(path.split('?')[0].endswith('/checks/cancel') for path, _, _ in self.fixture.forwarded), 1)
        self.assertEqual(sum(path.split('?')[0].endswith('/checks/request') for path, _, _ in self.fixture.forwarded), 1)
        self.assertEqual(self.errors, [])

    def test_terminal_touch_keyboard_camera_and_cancel(self):
        self.open_check(location=LOCATION)
        self.page.get_by_role('button', name='Start shelf check').click()
        self.page.get_by_role('button', name=re.compile('^Record observed quantity · Camera$')).click() if os.environ.get('SHELF_CHECKS_FIXTURE_URL') else self.page.get_by_role('button', name='Record observed quantity').click()
        self.assertIn('Service manager:', self.page.locator('main').inner_text())
        self.assertIn('Not observed', self.page.locator('main').inner_text())
        self.assertIn('Observed here', self.page.locator('main').inner_text())
        boxes = self.page.locator('main button, main input, main select').evaluate_all(
            "nodes => nodes.filter(n => n.getClientRects().length).map(n => n.getBoundingClientRect().toJSON())")
        self.assertTrue(boxes)
        self.assertTrue(all(box['height'] >= 44 for box in boxes), boxes)
        self.page.get_by_label('Observed quantity').focus()
        self.assertTrue(self.page.evaluate('document.activeElement.getAttribute("aria-label") === "Observed quantity"'))
        self.page.get_by_label('Observed quantity').click()
        self.page.get_by_role('dialog', name='Touchscreen search keyboard').get_by_role('button', name='Key 1').click()
        self.page.get_by_role('button', name='Use tally').click()
        self.page.get_by_role('button', name='Save observation').click()
        self.page.get_by_text('Observation saved at revision 1.', exact=False).wait_for()
        self.page.get_by_role('button', name='Refresh live review').click()
        self.page.get_by_text('Live shelf contents refreshed.', exact=False).wait_for()
        self.assertIn('Custody conflict', self.page.locator('main').inner_text())
        self.fixture.decode_codes = [LOCATION, 'AMBIGUOUS-QR']
        self.page.wait_for_function("!terminalCheckBusy && ![...document.querySelectorAll('.terminal-check-control')].find(button => button.textContent === 'Scan equipment')?.disabled")
        self.page.get_by_role('button', name='Scan equipment').click()
        self.page.wait_for_function("window.syntheticCameraStream?.getTracks()[0]?.readyState === 'live'")
        self.page.wait_for_function("terminalCheckMessage.includes('active shelf remains unchanged')")
        self.assertEqual(self.page.evaluate('terminalCheck.location_id'), LOCATION)
        try:
            self.page.get_by_text('Select the matching native record.' if os.environ.get('SHELF_CHECKS_FIXTURE_URL') else 'Choose the matching equipment.', exact=False).wait_for()
        except Exception as error:
            self.fail(f'ambiguous shared resolve did not reach UI: {error}; message={self.page.evaluate("terminalCheckMessage")}; errors={self.errors}; calls={self.fixture.calls}; responses={self.fixture.forwarded}')
        self.page.get_by_role('button', name='Cancel scan').click()
        self.page.wait_for_function("window.syntheticCameraStream?.getTracks()[0]?.readyState === 'ended'")
        self.assertEqual(self.page.evaluate('scanPurpose'), None)
        check_id = self.page.evaluate('terminalCheck.id')
        self.assertEqual(self.check_record(check_id)['revision'], 2)
        self.page.get_by_role('button', name='Refresh live review').click()
        self.page.get_by_text('Live shelf contents refreshed.', exact=False).wait_for()
        self.page.get_by_role('button', name='Finish shelf check').click()
        self.page.get_by_role('button', name='Confirm finish shelf check').click()
        self.page.get_by_text('Shelf check completed.', exact=False).wait_for()
        self.page.get_by_role('button', name='Check history').click()
        self.page.get_by_role('button', name=re.compile('completed · revision 4')).wait_for()
        self.assertEqual(self.check_count(), self.initial_check_count + 1)
        check_calls = [row for row in self.fixture.calls if urlparse(row[1]).path.removeprefix('/workshop-api').startswith('/workshop/checks/')]
        self.assertTrue(check_calls)
        self.assertTrue(all('actor_id' not in data and 'group_id' not in data for _, _, data in check_calls))
        self.assertEqual(self.fixture.prints, [])
        self.assertEqual(self.fixture.native_mutations, [])
        self.assertEqual(self.errors, [])

    def test_terminal_requires_explicit_quantity_and_ignores_stale_open(self):
        self.open_check(location=LOCATION)
        self.page.get_by_role('button', name='Start shelf check').click()
        self.page.get_by_role('button', name='Record observed quantity').click()
        check_id = self.page.evaluate('terminalCheck.id')
        self.page.get_by_role('button', name='Save observation').click()
        self.page.get_by_text('Enter an explicit whole number', exact=False).wait_for()
        self.assertEqual(self.check_record(check_id)['revision'], 0)
        self.page.evaluate('terminalCheck.can_edit=false; terminalCheckRender()')
        self.page.evaluate("terminalCheckObserve({id:'22222222-2222-4222-8222-222222222222',name:'Camera'},'1')")
        self.page.get_by_text('read-only or has a request awaiting resolution', exact=False).wait_for()
        self.assertEqual(self.check_record(check_id)['revision'], 0)
        self.page.evaluate('terminalCheck.can_edit=true; terminalCheckRender()')
        self.page.evaluate('''async () => {
          localStorage.removeItem(terminalCheckMetaKey(terminalCheckContext)); terminalCheck=null;
          const original=terminalCheckApi;
          terminalCheckApi=async(path,data)=>path.startsWith('/workshop/checks/list')
            ? await new Promise(resolve=>window.releaseTerminalList=resolve)
            : original(path,data);
          window.openingTerminalCheck=workshopCheckOpen(''' + json.dumps(LOCATION) + ''');
        }''')
        self.page.wait_for_function('typeof window.releaseTerminalList === "function"')
        self.page.evaluate("routeRevision++; routeTitle='Storage'; window.releaseTerminalList([])")
        self.page.evaluate('window.openingTerminalCheck')
        self.assertEqual(self.page.evaluate('routeTitle'), 'Storage')
        self.assertIsNone(self.page.evaluate('terminalCheck'))
        self.assertEqual(self.errors, [])
        self.open_check(check_id=check_id)
        self.page.evaluate("window.confirm=()=>true; window.prompt=()=> 'Duplicate check'")
        self.page.get_by_role('button', name='Cancel shelf check').click()
        self.page.get_by_text('Shelf check cancelled.', exact=False).wait_for()
        self.assertEqual(self.check_record(check_id)['state'], 'cancelled')
        self.assertEqual(self.check_record(check_id).get('cancel_reason'), 'Duplicate check')

    def test_terminal_not_started_recovery_keeps_key_until_acknowledged(self):
        self.open_check(location=LOCATION)
        key = str(uuid4())
        self.fixture.return_not_started = True
        self.page.evaluate('''key => {
          localStorage.setItem(terminalCheckPendingKey(terminalCheckContext), JSON.stringify({request_key:key,
            action:'start',check_id:null,group_id:terminalCheckContext.group_id,actor_id:terminalCheckContext.actor_id}));
          terminalCheckRender();
        }''', key)
        self.page.get_by_role('button', name='Check saved result').click()
        self.page.get_by_text('server confirms this request did not start', exact=False).wait_for()
        pending = self.page.evaluate('localStorage.getItem(terminalCheckPendingKey(terminalCheckContext))')
        self.assertIsNotNone(pending)
        self.page.get_by_role('button', name='Acknowledge no request started').click()
        self.assertIsNone(self.page.evaluate('localStorage.getItem(terminalCheckPendingKey(terminalCheckContext))'))
        self.assertEqual(self.errors, [])

    def test_terminal_legacy_observation_metadata_recovers_by_owner(self):
        self.fixture.drop_next_observe_response = True
        self.open_check(location=LOCATION)
        self.page.get_by_role('button', name='Start shelf check').click()
        self.page.wait_for_function('terminalCheck?.id && !terminalCheckBusy')
        check_id = self.page.evaluate('terminalCheck.id')
        self.page.evaluate("terminalCheckSelected={id:'" + ASSET + "',name:'Camera',method:'visual'}; terminalCheck.tally_draft='2'; terminalCheckObserve(terminalCheckSelected,'2')")
        self.page.get_by_text('result is uncertain', exact=False).wait_for()
        self.page.evaluate("pending=JSON.parse(localStorage.getItem(terminalCheckPendingKey(terminalCheckContext))); delete pending.action; delete pending.intent; localStorage.setItem(terminalCheckPendingKey(terminalCheckContext),JSON.stringify(pending))")
        self.page.get_by_role('button', name='Check saved result').click()
        self.page.get_by_text('Recovered the exact saved shelf-check result', exact=False).wait_for()
        self.assertEqual(self.page.evaluate('terminalCheck.id'), check_id)
        self.assertEqual(self.page.evaluate('terminalCheck.revision'), 1)
        self.assertIsNone(self.page.evaluate('localStorage.getItem(terminalCheckPendingKey(terminalCheckContext))'))

    def test_terminal_history_failure_after_route_change_is_ignored(self):
        self.open_check(location=LOCATION)
        self.page.get_by_role('button', name='Start shelf check').click()
        try:
            self.page.wait_for_function('terminalCheck?.id && !terminalCheckBusy')
        except Exception as error:
            self.fail(f'shared shelf-check start failed: {error}; message={self.page.evaluate("terminalCheckMessage")}; '
                      f'errors={self.errors}; calls={self.fixture.calls}; responses={self.fixture.forwarded}')
        self.page.evaluate('''() => {
          const original=terminalCheckApi;
          terminalCheckApi=async(path,data)=>path.startsWith('/workshop/checks/list')
            ? await new Promise((_,reject)=>window.rejectTerminalHistory=reject)
            : original(path,data);
          window.historyLoad=terminalCheckHistory();
        }''')
        self.page.wait_for_function('typeof window.rejectTerminalHistory === "function"')
        self.page.evaluate("routeRevision++; routeTitle='Storage'; window.rejectTerminalHistory(new Error('late history failure'))")
        self.page.evaluate('window.historyLoad')
        self.assertEqual(self.page.evaluate('routeTitle'), 'Storage')
        self.assertEqual(self.page.locator('.terminal-check-panel').count(), 1)
        self.assertNotIn('late history failure', self.page.locator('main').inner_text())

    def test_terminal_open_clears_old_check_while_context_loads(self):
        self.open_check(location=LOCATION)
        self.page.get_by_role('button', name='Start shelf check').click()
        self.page.wait_for_function('terminalCheck?.id && !terminalCheckBusy')
        old_check = self.page.evaluate('terminalCheck.id')
        self.page.evaluate('''() => {
          const originalFetch=window.fetch, originalApi=api;
          window.fetch=(path,options)=>path==='/workshop-api/context'
            ? new Promise(resolve=>window.releaseDesktopContext=resolve)
            : originalFetch(path,options);
          api=async(path,data,headers)=>path==='/workshop/get'
            ? await new Promise(resolve=>window.releaseWorkshopContext=resolve)
            : originalApi(path,data,headers);
          window.contextLoad=workshopCheckOpen(''' + json.dumps(LOCATION) + ''');
        }''')
        self.page.wait_for_function('typeof window.releaseDesktopContext === "function"')
        self.assertIsNone(self.page.evaluate('terminalCheck'))
        self.assertNotIn(old_check, self.page.locator('main').inner_text())
        self.page.evaluate('''() => window.releaseDesktopContext(new Response(JSON.stringify({manager:true,
          identity:'new-identity',user:{id:'new-actor',name:'New manager'},group:{id:'new-group',name:'New group'}}),
          {status:200,headers:{'Content-Type':'application/json'}}))''')
        self.page.wait_for_function('typeof window.releaseWorkshopContext === "function"')
        self.page.evaluate("window.releaseWorkshopContext({workshop_context:{group_id:'new-group',actor_id:'service'},locations:[]})")
        self.page.evaluate('window.contextLoad')
        self.assertEqual(self.page.evaluate('terminalCheckContext.group_id'), 'new-group')
        self.assertIsNone(self.page.evaluate('terminalCheck'))

    def test_terminal_preserves_independent_drafts_and_confirms_history_reopen(self):
        self.open_check(location=LOCATION)
        self.page.get_by_role('button', name='Start shelf check').click()
        self.page.wait_for_function('terminalCheck?.id && !terminalCheckBusy')
        check_id = self.page.evaluate('terminalCheck.id')
        self.page.evaluate("terminalCheck.notes_draft='unsaved note'; terminalCheck.tally_draft='7'; terminalCheckSaveMeta({notes_draft:'unsaved note',tally_draft:'7'})")
        self.page.evaluate("terminalCheckSaveNotes('saved note')")
        self.page.wait_for_function("terminalCheck.revision===1")
        self.assertEqual(self.page.evaluate('terminalCheck.notes_draft'), 'saved note')
        self.assertEqual(self.page.evaluate('terminalCheck.tally_draft'), '7')
        self.page.evaluate("terminalCheckObserve({id:'" + ASSET + "',name:'Camera',method:'visual'},'2')")
        self.page.wait_for_function("terminalCheck.revision===2")
        self.assertEqual(self.page.evaluate('terminalCheck.notes_draft'), 'saved note')
        self.assertIsNone(self.page.evaluate('terminalCheck.tally_draft'))
        self.page.evaluate("terminalCheck.notes_draft='another unsaved note'; terminalCheck.tally_draft='9'; window.confirm=()=>false")
        old_revision = self.page.evaluate('terminalCheck.revision')
        self.page.evaluate("workshopCheckOpen('" + LOCATION + "','different-check')")
        self.assertEqual(self.page.evaluate('terminalCheck.id'), check_id)
        self.assertEqual(self.page.evaluate('terminalCheck.revision'), old_revision)
        self.assertEqual(self.page.evaluate('terminalCheck.notes_draft'), 'another unsaved note')
        self.assertEqual(self.page.evaluate('terminalCheck.tally_draft'), '9')

    def test_fixture_fails_closed_and_intercepts_print_and_native_requests(self):
        with self.assertRaises(AssertionError):
            self.fixture.route('GET', '/unexpected-fixture-route', {})
        statuses = self.page.evaluate("Promise.all([fetch('/api/v1/entities/'+" + json.dumps(ASSET) + ").then(r=>r.status),fetch('/label/print?variant=standard',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({entity_id:" + json.dumps(ASSET) + ",request_key:'label-key'})}).then(r=>r.status),fetch('/badge/print/',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({badge_id:'badge-id',code:'sensitive-code',request_key:'badge-key'})}).then(r=>r.status)])")
        self.assertEqual(statuses, [501, 501, 501])
        self.page.evaluate('window.print()')
        self.assertEqual(self.page.evaluate('window.__printAttemptCount'), 1)
        self.assertTrue(self.fixture.native_mutations)
        blocked_prints = {urlparse(row[1]).path.rstrip('/'): row[2] for row in self.fixture.prints}
        self.assertEqual(set(blocked_prints), {'/label/print', '/badge/print'})
        self.assertEqual(blocked_prints['/label/print']['entity_id'], ASSET)
        self.assertEqual(blocked_prints['/badge/print']['badge_id'], 'badge-id')

    def test_check_flow_never_calls_terminal_physical_print_endpoints(self):
        self.open_check(LOCATION)
        self.page.get_by_role('button', name='Start shelf check').click()
        try:
            self.page.wait_for_function('terminalCheck?.id && !terminalCheckBusy')
        except Exception as error:
            self.fail(f'check flow did not open: {error}; message={self.page.evaluate("terminalCheckMessage")}; '
                      f'errors={self.errors}; calls={self.fixture.calls}')
        self.assertEqual(self.fixture.prints, [])
        self.assertFalse(any(urlparse(path).path.rstrip('/') in ('/label/print', '/badge/print')
                             for _, path, _ in self.fixture.calls))

    def test_same_collection_manager_can_read_other_owner_check_but_not_edit(self):
        created = self.fixture.route('POST', '/workshop/checks/start',
                                     {'location_id': LOCATION, 'request_key': str(uuid4())})
        self.fixture.read_only_manager = True
        self.fixture.suspended = True
        self.open_check(check_id=created['id'])
        self.page.wait_for_function("terminalCheck?.id === " + json.dumps(created['id']))
        self.assertEqual(self.page.evaluate('terminalCheck.actor_id'), SERVICE_ACTOR)
        self.assertEqual(self.page.evaluate('terminalCheck.group_id'), GROUP)
        self.assertFalse(self.page.evaluate('terminalCheck.can_edit'))
        self.assertIn('Shelf location was deleted', self.page.locator('main').inner_text())
        notes = self.page.get_by_role('textbox', name='Shelf check notes')
        self.assertIsNotNone(notes.get_attribute('readonly'))
        self.assertTrue(self.page.get_by_role('button', name='Save notes').is_disabled())
        self.assertTrue(self.page.get_by_role('button', name='Refresh live review').is_disabled())
        self.assertTrue(self.page.get_by_role('button', name='Cancel shelf check').is_visible())
        self.assertFalse(self.page.evaluate('editorMode'))
        reason = 'Suspended draft cleanup'
        self.page.evaluate("""reason => {
          const send=terminalCheckApi;
          terminalCheckApi=async(path,data)=>{
            if(path.endsWith('/cancel')){
              window.cancelPostData=data;
              return await new Promise((resolve,reject)=>{window.releaseCancel=()=>send(path,data).then(resolve,reject)});
            }
            return send(path,data);
          };
          window.confirm=()=>true;window.prompt=()=>reason;
        }""", reason)
        self.page.get_by_role('button', name='Cancel shelf check').click()
        self.page.wait_for_function('typeof window.releaseCancel === "function"')
        pending = json.loads(self.page.evaluate('localStorage.getItem(terminalCheckPendingKey(terminalCheckContext))'))
        self.assertEqual(pending['request_key'], self.page.evaluate('window.cancelPostData.request_key'))
        self.assertEqual(pending['check_id'], created['id'])
        self.assertEqual(pending['group_id'], GROUP)
        self.assertEqual(pending['actor_id'], READ_ONLY_MANAGER)
        self.assertEqual(pending['action'], 'cancel')
        self.assertNotIn(reason, json.dumps(pending))
        self.assertEqual(self.page.evaluate('window.cancelPostData.reason'), reason)
        self.page.evaluate('window.releaseCancel()')
        self.page.get_by_text('Shelf check cancelled.', exact=False).wait_for()
        self.assertEqual(self.fixture.checks[created['id']]['state'], 'cancelled')
        self.assertEqual(self.fixture.prints, [])

    def test_terminal_reopen_scrubs_legacy_pending_intent_before_recovery(self):
        created = self.fixture.route('POST', '/workshop/checks/start',
                                     {'location_id': LOCATION, 'request_key': str(uuid4())})
        key = str(uuid4())
        legacy = {'request_key': key, 'action': 'cancel', 'check_id': created['id'],
                  'location_id': LOCATION, 'group_id': GROUP, 'actor_id': SERVICE_ACTOR,
                  'reason': 'legacy private reason', 'notes': 'legacy private notes',
                  'notes_draft': 'legacy draft note', 'intent': {'reason': 'nested private reason'},
                  'request_hash': 'legacy hash'}
        self.page.evaluate("""value => localStorage.setItem(
          'terminal-shelf-check:' + value.group_id + ':' + value.actor_id + ':pending',
          JSON.stringify(value))""", legacy)
        self.open_check(check_id=created['id'])
        self.page.wait_for_function('terminalCheck?.id && !terminalCheckBusy')
        stored = json.loads(self.page.evaluate('localStorage.getItem(terminalCheckPendingKey(terminalCheckContext))'))
        self.assertEqual(stored, {key: legacy[key] for key in ('request_key', 'action', 'check_id', 'location_id', 'group_id', 'actor_id')})
        self.page.evaluate("""() => {
          const send=terminalCheckApi;
          terminalCheckApi=async(path,data)=>path.startsWith('/workshop/checks/request')
            ? {status:'completed',action:'cancel',result:{...structuredClone(terminalCheck),state:'cancelled',cancelled_at:'2026-10-09T12:01:00+00:00',cancelled_by:terminalCheckContext.actor_id}}
            : send(path,data);
        }""")
        self.page.get_by_role('button', name='Check saved result').click()
        self.page.get_by_text('Recovered the exact saved shelf-check result.', exact=False).wait_for()
        self.assertIsNone(self.page.evaluate('localStorage.getItem(terminalCheckPendingKey(terminalCheckContext))'))
        self.assertEqual(self.page.evaluate('terminalCheck.id'), created['id'])
        self.assertEqual(self.errors, [])

    def test_terminal_notes_are_memory_only_and_pause_warns_before_discard(self):
        self.page.goto(self.page.url + '?mode=editor', wait_until='domcontentloaded')
        self.page.wait_for_function("document.querySelector('#status')?.textContent.includes('connected')")
        self.open_check(location=LOCATION)
        self.page.get_by_role('button', name='Start shelf check').click()
        self.page.wait_for_function('terminalCheck?.id && !terminalCheckBusy')
        note = 'private unsaved shelf note 9f321'
        self.page.get_by_role('textbox', name='Shelf check notes').fill(note)
        self.assertEqual(self.page.evaluate('terminalCheck.notes_draft'), note)
        saved = self.page.evaluate('JSON.stringify(Object.keys(localStorage).map(key=>localStorage.getItem(key)))')
        self.assertNotIn(note, saved)
        self.page.evaluate("note=>{terminalCheckApi=async()=>{throw Error('dropped note save reply')};return terminalCheckMutation('notes',{id:terminalCheck.id,revision:terminalCheck.revision,notes:note})}", note)
        self.page.wait_for_function('!terminalCheckBusy')
        pending = self.page.evaluate('localStorage.getItem(terminalCheckPendingKey(terminalCheckContext))')
        self.assertNotIn(note, pending)
        self.assertTrue(self.page.evaluate("() => {const event=new Event('beforeunload',{cancelable:true});window.dispatchEvent(event);return event.defaultPrevented}"))
        self.page.evaluate('window.confirmMessages=[];window.confirm=message=>{window.confirmMessages.push(message);return false}')
        self.page.get_by_role('button', name='Pause check').click()
        self.assertTrue(self.page.evaluate('window.confirmMessages.some(message=>String(message||"").includes("unsaved notes"))'))
        self.assertEqual(self.page.get_by_role('textbox', name='Shelf check notes').input_value(), note)
        self.page.evaluate('window.confirm=()=>true')
        self.page.get_by_role('button', name='Pause check').click()
        self.page.locator('.terminal-check-panel').wait_for(state='detached')
        self.assertNotIn(note, self.page.evaluate('JSON.stringify(Object.keys(localStorage).map(key=>localStorage.getItem(key)))'))
        self.assertEqual(self.errors, [])

    def test_terminal_review_shows_inventory_changes_and_pending_operations(self):
        self.open_check(location=LOCATION)
        self.page.get_by_role('button', name='Start shelf check').click()
        self.page.wait_for_function('terminalCheck?.id && !terminalCheckBusy')
        self.page.evaluate("""() => {
          terminalCheck.changes=[{kind:'changed',items:[{id:'22222222-2222-4222-8222-222222222222',name:'Camera',before:{quantity:1,path:[{name:'Old shelf'}],custody:{checked_out:false}},after:{quantity:2,path:[{name:'New shelf'}],custody:{checked_out:true}}}]}];
          terminalCheck.pending_operations=[{id:'operation-1',group_id:terminalCheckContext.group_id,actor_id:terminalCheckContext.actor_id,action:'check_out',request_key:'request-secret',request_hash:'hash-secret',status:'review',created_at:'2026-10-09T12:00:00Z'}];
          terminalCheck.groups.unexpected_here=[{id:'99999999-9999-4999-8999-999999999999',name:'Tripod',expected_quantity:0,observed_quantity:1,original_path:[{name:'Old storage'}],current_path:[{name:'Rack A'}]}];
          terminalCheckRender();
        }""")
        for evidence in ('Changed inventory', 'Camera', '1', '2', 'Old shelf', 'New shelf',
                         'Pending native operations', 'check out', 'review', 'operation-1',
                         'Old storage', 'Rack A'):
            self.page.get_by_text(evidence, exact=False).first.wait_for()
        text = self.page.locator('main').inner_text()
        self.assertNotIn('request-secret', text)
        self.assertNotIn('hash-secret', text)

    def test_stale_authenticated_context_cannot_replace_newer_manager_context(self):
        result = self.page.evaluate('''async () => {
          const originalFetch=window.fetch;window.contextReleases=[];
          window.fetch=(path,options)=>path==='/workshop-api/context'
            ? new Promise(resolve=>window.contextReleases.push(resolve))
            : originalFetch(path,options);
          const context=(actor,identity)=>new Response(JSON.stringify({manager:true,identity,
            user:{id:actor,name:'Manager'},group:{id:'33333333-3333-4333-8333-333333333333',name:'Workshop'}}),
            {status:200,headers:{'Content-Type':'application/json'}});
          window.staleContextLoad=terminalCheckLoadContext();
          terminalCheckGeneration++;
          window.currentContextLoad=terminalCheckLoadContext();
          window.contextReleases[1](context('77777777-7777-4777-8777-777777777777','current-identity'));
          await window.currentContextLoad;
          window.contextReleases[0](context('88888888-8888-4888-8888-888888888888','stale-identity'));
          let staleRejected=false;
          try{await window.staleContextLoad}catch(error){staleRejected=/context changed/i.test(error.message)}
          return {actor:terminalCheckContext.actor_id,identity:terminalCheckDesktopIdentity,staleRejected};
        }''')
        self.assertTrue(result['staleRejected'])
        self.assertEqual(result['actor'], READ_ONLY_MANAGER)
        self.assertEqual(result['identity'], 'current-identity')


if __name__ == '__main__':
    unittest.main()
