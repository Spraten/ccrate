"""Gateway boundaries with isolated HTTP services and temporary static files."""
import http.client
import importlib.util
import json
import pathlib
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
        self.send_response(200)
        self.send_header('Set-Cookie', 'hb.auth.token=fixture; Path=/; HttpOnly')
        self.send_header('Set-Cookie', 'hb.auth.remember=fixture; Path=/; HttpOnly')
        payload = b'<html><body>native inventory</body></html>' if self.path == '/home' else body or b'native'
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
        self.assertEqual(self.call('/workshop-api/badges/issue', 'POST', b'{}', {'Origin': 'http://attacker.invalid'})[0], 403)
        self.assertEqual(self.call('/workshop-api/context', headers={'Host': 'attacker.invalid:' + str(gateway.PORT)})[0], 421)
        self.assertEqual(len(Companion.hits), count)

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
