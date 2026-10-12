#!/usr/bin/env python3
"""Run shelf-check desktop browser checks against a disposable local fixture."""
from __future__ import annotations

import argparse
import http.server
import json
import os
import pathlib
import socket
import subprocess
import sys
import threading
import urllib.request
from uuid import uuid4
from urllib.parse import urlsplit


class DesktopFixture:
    """The API test harness owns an isolated Ledger and fake native service."""
    def __init__(self, source: pathlib.Path):
        sys.path[:0] = [str(source / name) for name in ('ops', 'kiosk', 'work/hardware/python', 'tests')]
        from test_shelf_checks_api import Request, ShelfCheckApiTests
        self.Request = Request
        self.api_case = ShelfCheckApiTests('test_nonmanager_private_check_list')
        self.api_case.setUp()
        self.root = self.api_case.root
        self.api = __import__('desktop_api')
        self.api_case.manager2 = str(uuid4())
        self.api_case.users['manager2'] = {'id': self.api_case.manager2, 'name': 'Second Manager',
            'email': 'second@example.invalid', 'defaultGroupId': self.api_case.group,
            'groupIds': [self.api_case.group]}
        manager_file = self.root / 'work/ops/desktop-managers.json'
        managers = json.loads(manager_file.read_text())['managers']
        managers.append({'user_id': self.api_case.manager2, 'group_id': self.api_case.group})
        manager_file.write_text(json.dumps({'managers': managers}))
        self.api_case.shelf = '11111111-1111-4111-8111-111111111111'
        self.api_case.asset = '22222222-2222-4222-8222-222222222222'
        self.api_case.entities = {
            self.api_case.shelf: {'id': self.api_case.shelf, 'name': 'the Cage', 'archived': False,
                'quantity': 0, 'entityType': {'id': self.api_case.kind, 'isLocation': True}, 'parent': None},
            self.api_case.asset: {'id': self.api_case.asset, 'name': 'Camera', 'assetId': 'CAM-9',
                'quantity': 1, 'archived': False,
                'entityType': {'id': self.api_case.kind, 'isLocation': False},
                'parent': {'id': self.api_case.shelf}, 'fields': [], 'tags': []},
        }
        from datetime import datetime, timezone
        operation = str(uuid4())
        created = datetime.now(timezone.utc).isoformat()
        with self.api_case.ledger.connection() as db:
            db.execute('INSERT INTO operations VALUES(?,?,?,?,?,?,?,?)',
                (operation, self.api_case.group, self.api_case.manager, 'check_out', str(uuid4()),
                 'fixture-only', 'completed', created))
            db.execute('INSERT INTO operation_assets VALUES(?,?)', (operation, self.api_case.asset))
            db.execute('INSERT INTO custody VALUES(?,?,?,?)',
                (self.api_case.group, self.api_case.asset, self.api_case.manager, operation))
        self.manager2_context = self.api_case.request('context', headers={
            'Cookie': 'hb.auth.token=manager2; hb.auth.remember=true'}).result
        self.manager1_context = self.api_case.request('context').result

    def check_count(self) -> int:
        with self.api_case.ledger.connection() as db:
            return db.execute('SELECT COUNT(*) FROM shelf_checks').fetchone()[0]

    @property
    def requests(self) -> list[dict]:
        with self.api_case.ledger.connection() as db:
            rows = db.execute('''SELECT request_key,action,actor_id,intent_sha256,result_json
                FROM shelf_check_requests ORDER BY sequence''').fetchall()
        return [{'request_key': row['request_key'], 'action': row['action'],
                 'actor_id': row['actor_id'], 'intent_sha256': row['intent_sha256'],
                 'result': json.loads(row['result_json'])} for row in rows]

    def dispatch(self, path: str, method: str, body: dict | None, host: str,
                 identity: str = '', token: str = 'alpha'):
        headers = {'X-Workshop-Identity': identity, 'Host': host,
                   'Cookie': f'hb.auth.token={token}; hb.auth.remember=true'}
        if method == 'POST':
            headers['Origin'] = 'http://' + host
        request = self.Request(path.removeprefix('/workshop-api/'), method,
                                        body, headers)
        self.api.handle(request, self.api_case.deps)
        return request.status, request.result

    def close(self):
        self.api_case.temp.cleanup()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def browser_python() -> str:
    if os.environ.get('PLAYWRIGHT_PYTHON'):
        return os.environ['PLAYWRIGHT_PYTHON']
    try:
        import playwright.sync_api  # noqa: F401
        return sys.executable
    except ImportError:
        candidate = pathlib.Path('/home/user/Desktop/inventory-system/work/task6-playwright-venv/bin/python')
        if candidate.is_file():
            return str(candidate)
        raise RuntimeError('Playwright is unavailable; set PLAYWRIGHT_PYTHON to the installed browser environment.')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interface', choices=('desktop', 'terminal'), default='desktop')
    parser.add_argument('--root', type=pathlib.Path, required=True)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--fixture-port', type=int, default=0)
    args = parser.parse_args()
    source = args.root.resolve(strict=True)
    if not (source / 'ops/shelf_checks.py').is_file() or not (source / 'deploy/verify-shelf-checks.py').is_file():
        raise SystemExit('--root must be the isolated shelf-check candidate repository.')
    parsed = urlsplit(args.base_url)
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
        raise SystemExit('--base-url must be an explicit http://127.0.0.1[:port] fixture endpoint.')
    if args.fixture_port != 0 and not 32768 <= args.fixture_port <= 60999:
        raise SystemExit('--fixture-port must be zero or an unprivileged ephemeral port.')
    requested_port = parsed.port or 0
    if requested_port and args.fixture_port and requested_port != args.fixture_port:
        raise SystemExit('--base-url and --fixture-port must select the same endpoint.')
    port = args.fixture_port or requested_port or free_port()
    if not 32768 <= port <= 60999:
        port = free_port()
    host = f'127.0.0.1:{port}'
    fixture = DesktopFixture(source)

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_OPTIONS(self): self.send_cors(204)
        def do_GET(self): self.respond()
        def do_POST(self): self.respond()
        def log_message(self, *_args): pass
        def send_cors(self, status):
            self.send_response(status)
            self.send_header('Access-Control-Allow-Origin', 'https://fixture.invalid')
            self.send_header('Access-Control-Allow-Credentials', 'true')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type,X-Workshop-Identity,X-Fixture-User')
            self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
            self.send_header('Content-Length', '0')
            self.end_headers()
        def respond(self):
            body = None
            if self.command == 'POST':
                body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))))
            if self.path == '/__fixture__/state':
                result = {'check_count': fixture.check_count(), 'requests': fixture.requests,
                          'manager1_context': fixture.manager1_context,
                          'manager2_context': fixture.manager2_context}
                status = 200
            elif self.path == '/__fixture__/suspend-shelf' and self.command == 'POST':
                fixture.api_case.entities.pop(fixture.api_case.shelf, None)
                result = {'suspended': True}
                status = 200
            else:
                status, result = fixture.dispatch(self.path, self.command, body, host,
                    self.headers.get('X-Workshop-Identity', ''),
                    self.headers.get('X-Fixture-User', 'alpha'))
            payload = json.dumps(result).encode()
            self.send_response(status or 500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', 'https://fixture.invalid')
            self.send_header('Access-Control-Allow-Credentials', 'true')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = http.server.ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    endpoint = f'http://{host}'
    print('Disposable shelf-check fixture: ' + endpoint, flush=True)
    try:
        env = dict(os.environ)
        env['PYTHONPATH'] = os.pathsep.join(str(source / item) for item in
            ('ops', 'kiosk', 'work/hardware/python', 'tests'))
        env['SHELF_CHECKS_FIXTURE_URL'] = endpoint
        if args.interface == 'desktop':
            for case in ('desktop_uncertain_reopen', 'desktop_observe_refresh_finish_history'):
                command = [browser_python(), '-m', 'unittest', 'discover', '-s', 'tests',
                           '-p', 'test_workshop_browser.py', '-k', case, '-v']
                result = subprocess.run(command, cwd=source, env=env, check=False)
                if result.returncode:
                    return result.returncode
                if any(client.writes for client in fixture.api_case.native_clients):
                    raise AssertionError('The desktop fixture attempted a native write.')
                print(f'PASS {case}: {fixture.check_count()} persisted check(s), '
                      f'{len(fixture.requests)} Ledger request(s)', flush=True)
                fixture.close()
                fixture = DesktopFixture(source)
        else:
            terminal_cases = (
                'fixture_fails_closed_and_intercepts_print_and_native_requests',
                'terminal_history_failure_after_route_change_is_ignored',
                'terminal_legacy_observation_metadata_recovers_by_owner',
                'test_other_manager_cancel_recovers_dropped_committed_result',
                'terminal_not_started_recovery_keeps_key_until_acknowledged',
                'terminal_open_clears_old_check_while_context_loads',
                'terminal_preserves_independent_drafts_and_confirms_history_reopen',
                'terminal_requires_explicit_quantity_and_ignores_stale_open',
                'terminal_touch_keyboard_camera_and_cancel',
                'terminal_uncertain_reopen',
            )
            for case in terminal_cases:
                if case == 'terminal_touch_keyboard_camera_and_cancel':
                    fixture.api_case.entities[fixture.api_case.asset]['fields'] = [
                        {'name': 'Manufacturer QR code', 'textValue': 'AMBIGUOUS-QR'}]
                    duplicate_id = '66666666-6666-4666-8666-666666666666'
                    fixture.api_case.entities[duplicate_id] = {
                        'id': duplicate_id, 'name': 'Camera duplicate', 'assetId': 'CAM-10',
                        'quantity': 1, 'archived': False,
                        'entityType': {'id': fixture.api_case.kind, 'isLocation': False},
                        'parent': {'id': fixture.api_case.shelf},
                        'fields': [{'name': 'Manufacturer QR code', 'textValue': 'AMBIGUOUS-QR'}],
                        'tags': []}
                command = [browser_python(), '-m', 'unittest', 'discover', '-s', 'tests',
                           '-p', 'test_terminal_shelf_checks_browser.py', '-k', case, '-v']
                result = subprocess.run(command, cwd=source, env=env, check=False)
                if result.returncode:
                    return result.returncode
                if any(client.writes for client in fixture.api_case.native_clients):
                    raise AssertionError('The Terminal fixture attempted a native write.')
                print(f'PASS {case}: {fixture.check_count()} persisted check(s), '
                      f'{len(fixture.requests)} Ledger request(s), no native writes', flush=True)
                fixture.close()
                fixture = DesktopFixture(source)
    finally:
        server.shutdown()
        server.server_close()
        fixture.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
