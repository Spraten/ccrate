"""Gateway boundaries with isolated HTTP services and temporary static files."""
import http.client
import importlib.util
import base64
import hashlib
import json
import pathlib
import socket
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SOURCE = pathlib.Path(__file__).resolve().parents[1] / 'deploy/workshop-gateway.py'
spec = importlib.util.spec_from_file_location('workshop_gateway', SOURCE)
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)


class Native(BaseHTTPRequestHandler):
    hits = []

    def log_message(self, *args):
        pass

    def serve(self):
        body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        self.hits.append((self.path, dict(self.headers), body))
        self.send_response(401 if self.path == '/api/v1/ws/events' else 200)
        self.send_header('Set-Cookie', 'hb.auth.token=fixture; Path=/; HttpOnly')
        self.send_header('Set-Cookie', 'hb.auth.remember=fixture; Path=/; HttpOnly')
        payload = (b'<html><body>native inventory</body></html>' if self.path == '/home' else
                   b'native sign-in required' if self.path == '/api/v1/ws/events' else body or b'native')
        if self.path == '/home':
            self.send_header('Content-Type', 'text/html')
            self.send_header('ETag', 'old-html')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = serve
    do_POST = serve


class Companion(Native):
    hits = []


class NativeWebSocket:
    def __init__(self):
        self.server = socket.socket()
        self.server.bind(('127.0.0.1', 0))
        self.server.listen()
        self.port = self.server.getsockname()[1]
        self.closed = threading.Event()
        self.ready = threading.Event()
        self.request = None
        self.frame = None
        self.error = None
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        try:
            client, _ = self.server.accept()
            with client:
                client.settimeout(3)
                request = b''
                while b'\r\n\r\n' not in request:
                    request += client.recv(4096)
                header = request.split(b'\r\n\r\n', 1)[0].decode('latin-1')
                self.request = dict(line.split(': ', 1) for line in header.split('\r\n')[1:])
                key = self.request['Sec-WebSocket-Key']
                accept = base64.b64encode(hashlib.sha1(
                    (key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest())
                # Keep the first server frame in the same TCP write as the 101 headers.
                client.sendall(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n'
                               b'Connection: Upgrade\r\nSec-WebSocket-Accept: ' + accept +
                               b'\r\n\r\n\x81\x01S')
                self.ready.set()
                frame = b''
                while len(frame) < 7:
                    frame += client.recv(7 - len(frame))
                self.frame = frame
                client.sendall(b'\x81\x01R')
                while client.recv(4096):
                    pass
        except Exception as error:
            self.error = error
        finally:
            self.closed.set()
            self.server.close()


class GatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        gateway.ROOT = pathlib.Path(cls.tmp.name)
        (gateway.ROOT / 'work/homebox-ui-current/_nuxt').mkdir(parents=True)
        (gateway.ROOT / 'work/homebox-ui-current/index.html').write_text('native integrated frontend')
        (gateway.ROOT / 'work/homebox-ui-current/_nuxt/app.js').write_text('compiled fixture')
        (gateway.ROOT / 'secret').write_text('never expose')
        cls.native = ThreadingHTTPServer(('127.0.0.1', 0), Native)
        cls.companion = ThreadingHTTPServer(('127.0.0.1', 0), Companion)
        gateway.NATIVE_PORT = cls.native.server_port
        gateway.COMPANION_PORT = cls.companion.server_port
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), gateway.Handler)
        gateway.PORT = cls.server.server_port
        for server in (cls.native, cls.companion, cls.server):
            threading.Thread(target=server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        for server in (cls.server, cls.native, cls.companion):
            server.shutdown()
            server.server_close()
        cls.tmp.cleanup()

    def call(self, path, method='GET', body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        connection.request(method, path, body, headers or {})
        response = connection.getresponse()
        result = response.status, response.getheaders(), response.read()
        connection.close()
        return result

    def test_native_paths_remain_native_and_cookies_survive(self):
        status, headers, body = self.call('/api/system')
        self.assertEqual((status, body), (200, b'native'))
        self.assertEqual(len([h for h in headers if h[0].lower() == 'set-cookie']), 2)
        self.assertEqual(Native.hits[-1][0], '/api/system')

    def test_desktop_namespace_only_and_original_identity(self):
        status, headers, body = self.call('/workshop-api/context', headers={'Cookie': 'hb.auth.token=fixture'})
        self.assertEqual(status, 200)
        self.assertEqual(Companion.hits[-1][1]['Cookie'], 'hb.auth.token=fixture')
        self.assertIn(('Cache-Control', 'no-store'), headers)

    def test_cross_origin_and_untrusted_host_never_reach_backend(self):
        count = len(Companion.hits)
        self.assertEqual(self.call('/workshop-api/badges/issue', 'POST', b'{}', {
            'Origin': 'http://attacker.invalid', 'Connection': 'close'})[0], 403)
        self.assertEqual(self.call('/workshop-api/context', headers={
            'Host': 'attacker.invalid:' + str(gateway.PORT), 'Connection': 'close'})[0], 421)
        self.assertEqual(len(Companion.hits), count)

    def test_websocket_rejects_foreign_hosts_and_companion_upgrades(self):
        count = len(Companion.hits)
        headers = {'Host': 'attacker.invalid:' + str(gateway.PORT), 'Connection': 'Upgrade',
                   'Upgrade': 'websocket', 'Sec-WebSocket-Key': 'dGhlIHNhbXBsZSBub25jZQ==',
                   'Sec-WebSocket-Version': '13', 'Origin': 'http://attacker.invalid'}
        self.assertEqual(self.call('/api/v1/ws/events', headers=headers)[0], 421)
        headers['Host'] = '127.0.0.1:' + str(gateway.PORT)
        self.assertEqual(self.call('/api/v1/ws/events', headers=headers)[0], 403)
        headers['Origin'] = 'http://' + headers['Host']
        self.assertEqual(self.call('/workshop-api/context', headers=headers)[0], 400)
        self.assertEqual(len(Companion.hits), count)

    def test_native_websocket_preserves_handshake_frames_and_closes_on_disconnect(self):
        native = NativeWebSocket()
        old_port = gateway.NATIVE_PORT
        gateway.NATIVE_PORT = native.port
        client = socket.create_connection(('127.0.0.1', self.server.server_port), timeout=3)
        client.settimeout(3)
        stream = client.makefile('rb')
        key = base64.b64encode(b'0123456789abcdef').decode()
        try:
            client.sendall((f'GET /api/v1/ws/events HTTP/1.1\r\nHost: 127.0.0.1:{gateway.PORT}\r\n'
                            f'Origin: http://127.0.0.1:{gateway.PORT}\r\nCookie: hb.auth.token=fixture\r\n'
                            'Connection: keep-alive, Upgrade\r\nUpgrade: websocket\r\n'
                            f'Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
            status = stream.readline()
            response_headers = {}
            while True:
                line = stream.readline()
                if line == b'\r\n':
                    break
                name, value = line.decode('latin-1').split(':', 1)
                response_headers[name.lower()] = value.strip()
            self.assertIn(b' 101 ', status)
            self.assertEqual(response_headers['upgrade'], 'websocket')
            self.assertIn('upgrade', response_headers['connection'].lower())
            self.assertEqual(response_headers['sec-websocket-accept'], base64.b64encode(
                hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode())
            self.assertEqual(stream.read(3), b'\x81\x01S')
            self.assertTrue(native.ready.wait(1), native.error)
            self.assertEqual(native.request['Cookie'], 'hb.auth.token=fixture')
            self.assertEqual(native.request['Origin'], f'http://127.0.0.1:{gateway.PORT}')
            self.assertEqual(native.request['Host'], f'127.0.0.1:{gateway.PORT}')
            self.assertEqual(native.request['Upgrade'], 'websocket')
            self.assertIn('upgrade', native.request['Connection'].lower())
            mask = b'\x01\x02\x03\x04'
            client.sendall(b'\x81\x81' + mask + bytes([ord('C') ^ mask[0]]))
            self.assertEqual(stream.read(3), b'\x81\x01R')
            self.assertEqual(native.frame, b'\x81\x81' + mask + bytes([ord('C') ^ mask[0]]))
        finally:
            stream.close()
            client.close()
            gateway.NATIVE_PORT = old_port
        self.assertTrue(native.closed.wait(2), native.error)

    def test_native_websocket_forwards_non_upgrade_responses(self):
        status, _, body = self.call('/api/v1/ws/events', headers={
            'Origin': 'http://127.0.0.1:' + str(gateway.PORT), 'Cookie': 'hb.auth.token=fixture',
            'Connection': 'Upgrade', 'Upgrade': 'websocket',
            'Sec-WebSocket-Key': 'dGhlIHNhbXBsZSBub25jZQ==', 'Sec-WebSocket-Version': '13'})
        self.assertEqual((status, body), (401, b'native sign-in required'))
        self.assertEqual(Native.hits[-1][1]['Cookie'], 'hb.auth.token=fixture')

    def test_same_origin_write_and_native_upload_bytes(self):
        self.assertEqual(self.call('/workshop-api/return', 'POST', b'{}', {'Origin': 'http://127.0.0.1:' + str(gateway.PORT)})[0], 200)
        image = b'\x00\xfffixture image\n'
        self.assertEqual(self.call('/api/v1/entities/fixture/attachments', 'POST', image)[2], image)

    def test_static_no_traversal(self):
        self.assertEqual(self.call('/workshop')[2], b'native integrated frontend')
        self.assertEqual(self.call('/%2e%2e/%2e%2e/secret')[0], 404)
        self.assertEqual(self.call('/workshop-api/context', 'DELETE')[0], 405)
        self.assertEqual(self.call('/_nuxt/app.js')[2], b'compiled fixture')
        self.assertEqual(self.call('/_nuxt/missing.js')[0], 404)
        self.assertEqual(self.call('/workshop/loans')[2], b'native integrated frontend')

    def test_worker_has_no_navigation_fallback_or_private_cache(self):
        status, headers, body = self.call('/sw.js')
        self.assertEqual(status, 200)
        self.assertIn(b"caches.delete", body)
        self.assertNotIn(b"registerRoute", body)
        self.assertNotIn(b"addEventListener('fetch'", body)

    def test_native_html_uses_integrated_build_without_injection(self):
        status, headers, body = self.call('/home')
        self.assertEqual(status, 200)
        self.assertNotIn(b'/workshop/homebox-tools.js', body)
        self.assertEqual(body, b'native integrated frontend')
        self.assertEqual([value for key, value in headers if key.lower() == 'content-length'], [str(len(body))])
        self.assertFalse(any(key.lower() == 'etag' for key, _ in headers))

    def test_native_fallback_preserves_original_html_without_overlay(self):
        root = gateway.ROOT
        gateway.ROOT = root / 'absent-build'
        try:
            status, _, body = self.call('/home')
            self.assertEqual(status, 200)
            self.assertIn(b'native inventory', body)
            self.assertNotIn(b'homebox-tools.js', body)
        finally:
            gateway.ROOT = root

    def test_backend_outage_clear_response(self):
        port = gateway.COMPANION_PORT
        gateway.COMPANION_PORT = 1
        try:
            status, _, body = self.call('/workshop-api/context')
            self.assertEqual(status, 503)
            self.assertIn('do not repeat', json.loads(body)['error'])
        finally:
            gateway.COMPANION_PORT = port
