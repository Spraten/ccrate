#!/usr/bin/env python3
"""Share native Homebox and the authenticated Workshop workspace on one address.

The native app remains at URL root. The local touchscreen API is never exposed.
"""
import base64
import binascii
import http.client
import ipaddress
import json
import mimetypes
import os
import pathlib
import socket
import stat
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit
import sys
CODE_ROOT = pathlib.Path(os.environ.get('WORKSHOP_CODE_ROOT', str(pathlib.Path(__file__).resolve().parents[1])))
ROOT = pathlib.Path(os.environ.get('WORKSHOP_ROOT', '/home/user/Desktop/inventory-system'))
NATIVE_PORT = int(os.environ.get('WORKSHOP_NATIVE_PORT', '17747'))
COMPANION_PORT = int(os.environ.get('WORKSHOP_COMPANION_PORT', '17749'))
PORT = int(os.environ.get('WORKSHOP_PORT', '17745'))
FIXTURE_PROCESS = os.environ.get('WORKSHOP_FIXTURE_PROCESS') == '1'
FIXTURE_ROOT = None
FIXTURE_READY = None
if FIXTURE_PROCESS:
    _raw_root = pathlib.Path(os.environ.get('WORKSHOP_ROOT', ''))
    _token = os.environ.get('WORKSHOP_FIXTURE_TOKEN', '')
    _ready = pathlib.Path(os.environ.get('WORKSHOP_FIXTURE_READY_FILE', ''))
    if ('..' in _raw_root.parts or _raw_root.is_symlink() or '..' in _ready.parts or not _ready.is_absolute()
            or os.environ.get('WORKSHOP_BIND_HOST') != '127.0.0.1'):
        raise RuntimeError('Fixture gateway refused before project imports or listener creation')
    FIXTURE_ROOT = _raw_root.resolve(strict=True)
    if _raw_root.absolute() != FIXTURE_ROOT:
        raise RuntimeError('Fixture gateway refused before project imports or listener creation')
    _marker = FIXTURE_ROOT / '.fixture-process-token'
    try:
        _marker_stat = _marker.lstat()
    except OSError as exc:
        raise RuntimeError('Fixture gateway refused before project imports or listener creation') from exc
    if (FIXTURE_ROOT.stat().st_uid != os.getuid() or (FIXTURE_ROOT.stat().st_mode & 0o777) != 0o700
            or not FIXTURE_ROOT.is_relative_to(pathlib.Path(tempfile.gettempdir()).resolve())
            or not stat.S_ISREG(_marker_stat.st_mode)
            or _marker_stat.st_nlink != 1 or _marker_stat.st_uid != os.getuid()
            or (_marker_stat.st_mode & 0o777) != 0o600 or len(_token) < 32
            or _marker.read_text() != _token
            or not _ready.resolve(strict=False).is_relative_to(FIXTURE_ROOT)
            or int(os.environ.get('WORKSHOP_PORT', '-1')) != 0
            or any(key.startswith('HBOX_') for key in os.environ)):
        raise RuntimeError('Fixture gateway refused before project imports or listener creation')
    FIXTURE_READY = _ready
    _ports = [int(os.environ.get(key, '0')) for key in ('WORKSHOP_NATIVE_PORT', 'WORKSHOP_COMPANION_PORT')]
    if len(set(_ports)) != 2 or any(not 32768 <= port <= 60999 for port in _ports):
        raise RuntimeError('Fixture gateway requires owned ephemeral native and companion ports')
sys.path.insert(0, str(CODE_ROOT / 'ops'))
from network_access import local_hosts, valid_native_host
HOP_HEADERS = {'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
               'te', 'trailer', 'transfer-encoding', 'upgrade'}
WORKER = b'''// Workshop gateway: native network requests must not cache identity data.
self.addEventListener('install', event => {self.skipWaiting();});
self.addEventListener('activate', event => {event.waitUntil((async () => {
  for (const key of await caches.keys()) {
    if (key === 'api-cache' || key.startsWith('workbox-')) await caches.delete(key);
  }
  await self.clients.claim();
})());});
// Deliberately no fetch handler: Homebox and Workshop load from this Pi.
'''
def valid_host(value):
    return valid_native_host(value, PORT, local_hosts())


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'WorkshopGateway'

    def log_message(self, *args):
        # Native auth query strings and invitation links must not enter logs.
        pass

    def send_bytes(self, status, body, kind='application/json', extra=None):
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'same-origin')
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != 'HEAD':
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True

    def error(self, status, text):
        self.send_bytes(status, json.dumps({'error': text}).encode())

    def dispatch(self):
        connection_tokens = {value.strip().lower() for value in self.headers.get('Connection', '').split(',')}
        websocket = (self.headers.get('Upgrade') or 'upgrade' in connection_tokens
                     or self.headers.get('Sec-WebSocket-Key'))
        if not valid_host(self.headers.get('Host', '')):
            if websocket:
                self.close_connection = True
            self.error(421, 'Use the Pi network address or localhost with the Workshop port.')
            return
        path = urlsplit(self.path).path
        if websocket:
            if (path != '/api/v1/ws/events' or self.command != 'GET'
                    or self.headers.get('Upgrade', '').lower() != 'websocket'
                    or 'upgrade' not in connection_tokens
                    or self.headers.get('Sec-WebSocket-Version') != '13'):
                self.close_connection = True
                self.error(400, 'Only the native events WebSocket is available.')
                return
            key = self.headers.get('Sec-WebSocket-Key', '')
            try:
                if len(base64.b64decode(key, validate=True)) != 16:
                    raise ValueError
            except (binascii.Error, ValueError):
                self.close_connection = True
                self.error(400, 'Invalid WebSocket handshake.')
                return
            if self.headers.get('Origin') != 'http://' + self.headers['Host']:
                self.close_connection = True
                self.error(403, 'Open Workshop on this Pi address before connecting.')
                return
            self.websocket_proxy(connection_tokens)
            return
        if path == '/sw.js':
            self.send_bytes(200, WORKER, 'application/javascript', {'Service-Worker-Allowed': '/'})
            return
        desktop = path == '/workshop-api' or path.startswith('/workshop-api/')
        if desktop and self.command not in ('GET', 'POST'):
            self.error(405, 'Workshop accepts GET and POST only.')
            return
        if desktop and self.command == 'POST' and self.headers.get('Origin') != 'http://' + self.headers['Host']:
            self.error(403, 'Open Workshop on this Pi address before submitting a change.')
            return
        if not desktop and not (path == '/api' or path.startswith('/api/')) and self.frontend(path):
            return
        self.proxy(COMPANION_PORT if desktop else NATIVE_PORT, desktop)

    def frontend(self, path):
        directory = pathlib.Path(os.environ.get('HOMEBOX_UI_ROOT', str(ROOT / 'work/homebox-ui-current'))).resolve()
        if not (directory / 'index.html').is_file():
            return False
        if self.command not in ('GET', 'HEAD'):
            self.error(405, 'This page accepts GET only.')
            return True
        relative = unquote(path).lstrip('/')
        target = (directory / relative).resolve()
        if target != directory and directory not in target.parents:
            self.error(404, 'Page not found.')
            return True
        if target.is_dir():
            target = target / 'index.html'
        if not target.is_file():
            if pathlib.PurePosixPath(relative).suffix or relative.startswith('_nuxt/'):
                self.error(404, 'File not found.')
                return True
            target = directory / 'index.html'
        self.send_bytes(200, target.read_bytes(), mimetypes.guess_type(str(target))[0] or 'application/octet-stream', {'X-Frame-Options': 'SAMEORIGIN'})
        return True

    def proxy(self, port, desktop):
        connection = None
        try:
            if self.headers.get('Transfer-Encoding'):
                self.error(411, 'Send a Content-Length for uploads.')
                return
            length = int(self.headers.get('Content-Length', '0'))
            if length < 0 or length > (1024 * 1024 if desktop else 64 * 1024 * 1024):
                self.error(413, 'Request is too large.')
                return
            self.connection.settimeout(20)
            body = self.rfile.read(length) if length else None
            if body is not None and len(body) != length:
                self.error(400, 'Upload was interrupted.')
                return
            headers = {key: value for key, value in self.headers.items()
                       if key.lower() not in HOP_HEADERS and not key.lower().startswith(('x-forwarded-', 'x-workshop-gateway'))}
            headers['Connection'] = 'close'
            headers['Accept-Encoding'] = 'identity'
            # A single local connection preserves cookies and the checked external Host.
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=75)
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            self.send_response(response.status)
            for key, value in response.getheaders():
                if key.lower() not in HOP_HEADERS and (not desktop or key.lower() != 'cache-control'):
                    self.send_header(key, value)
            if desktop:
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.close_connection = True
            if self.command != 'HEAD':
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (ValueError, OSError, http.client.HTTPException):
            if not self.close_connection:
                self.error(503, 'The Pi service is unavailable. Your submitted change may need inspection in Recovery; do not repeat it automatically.')
        finally:
            if connection:
                connection.close()

    def websocket_proxy(self, connection_tokens):
        connection = None
        response = None
        try:
            headers = {key: value for key, value in self.headers.items()
                       if key.lower() not in HOP_HEADERS and key.lower() not in connection_tokens
                       and not key.lower().startswith(('x-forwarded-', 'x-workshop-gateway'))}
            headers.update({'Connection': 'Upgrade', 'Upgrade': 'websocket',
                            'Accept-Encoding': 'identity'})
            connection = http.client.HTTPConnection('127.0.0.1', NATIVE_PORT, timeout=75)
            connection.request('GET', self.path, headers=headers)
            response = connection.getresponse()
            if response.status != 101:
                self.send_response(response.status)
                for key, value in response.getheaders():
                    if key.lower() not in HOP_HEADERS:
                        self.send_header(key, value)
                self.send_header('Connection', 'close')
                self.end_headers()
                self.close_connection = True
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                return
            upstream = connection.sock
            if (response.getheader('Upgrade', '').lower() != 'websocket'
                    or 'upgrade' not in {value.strip().lower() for value in
                                         response.getheader('Connection', '').split(',')}
                    or upstream is None or response.fp is None):
                self.close_connection = True
                self.error(502, 'The native service returned an invalid WebSocket handshake.')
                return
            self.send_response_only(101)
            for key, value in response.getheaders():
                if key.lower() not in HOP_HEADERS or key.lower() in ('connection', 'upgrade'):
                    self.send_header(key, value)
            self.end_headers()
            self.close_connection = True
            self.connection.settimeout(None)
            upstream.settimeout(None)
            stop = threading.Event()

            def relay(read, write):
                try:
                    while not stop.is_set():
                        chunk = read()
                        if not chunk:
                            break
                        write.sendall(chunk)
                except OSError:
                    pass
                finally:
                    stop.set()
                    for sock in (self.connection, upstream):
                        try:
                            sock.shutdown(socket.SHUT_RDWR)
                        except OSError:
                            pass

            up = threading.Thread(target=relay,
                                  args=(lambda: response.fp.read1(65536), self.connection))
            down = threading.Thread(target=relay,
                                    args=(lambda: self.connection.recv(65536), upstream))
            up.start()
            down.start()
            up.join()
            down.join()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (ValueError, OSError, http.client.HTTPException):
            if not self.close_connection:
                self.error(503, 'The Pi service is unavailable. Your submitted change may need inspection in Recovery; do not repeat it automatically.')
        finally:
            if response:
                response.close()
            if connection:
                connection.close()

    do_GET = dispatch
    do_HEAD = dispatch
    do_POST = dispatch
    do_PUT = dispatch
    do_PATCH = dispatch
    do_DELETE = dispatch
    do_OPTIONS = dispatch


if __name__ == '__main__':
    host = '127.0.0.1' if FIXTURE_PROCESS else '0.0.0.0'
    if FIXTURE_PROCESS:
        ui_root = pathlib.Path(os.environ.get('HOMEBOX_UI_ROOT', '')).resolve(strict=True)
        if not ui_root.is_relative_to(pathlib.Path(CODE_ROOT).resolve()):
            raise RuntimeError('Fixture gateway refused a static root outside its selected package')
    server = ThreadingHTTPServer((host, PORT), Handler)
    PORT = server.server_address[1]
    if FIXTURE_PROCESS:
        FIXTURE_READY.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        FIXTURE_READY.write_text(json.dumps({'mode': 'fixture-process', 'pid': os.getpid(),
            'host': host, 'port': PORT, 'code_root': str(pathlib.Path(CODE_ROOT).resolve()),
            'static_root': str(ui_root)}, sort_keys=True))
    server.serve_forever()
