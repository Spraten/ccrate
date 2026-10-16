import ast
import io
import json
import pathlib
import unittest
from contextlib import nullcontext
from urllib.parse import parse_qs, urlsplit

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_get_route():
    source_path = ROOT / 'deploy/kiosk-server.py'
    source = source_path.read_text(encoding='utf-8')
    tree = ast.parse(source)
    handler = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Handler')
    method = next(node for node in handler.body if isinstance(node, ast.FunctionDef) and node.name == 'do_GET')
    namespace = {
        'desktop_handle': lambda *_args: False,
        'ROOT': ROOT,
        'lock': nullcontext(), 'ledger': object(), 'shelf_checks': object(), 'badges': object(),
        'checkout_cart': object(), 'native_jobs': object(), 'imports': object(), 'workshop': object(),
        'sessions': object(), 'label_layouts': object(), 'LABEL_ASSET_ROOT': ROOT,
        'urlsplit': urlsplit, 'parse_qs': parse_qs, 'json': json,
        'inventory': lambda *_args: [],
    }
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source_path), 'exec'), namespace)

    class Request:
        def __init__(self, path):
            self.path = path
            self.headers = {}
            self.wfile = io.BytesIO()
            self.response = None
            self.response_headers = {}

        def send_response(self, code):
            self.response = code

        def send_header(self, name, value):
            self.response_headers[name] = value

        def end_headers(self):
            pass

        def send_error(self, code, *_args):
            self.response = code

        def reply_json(self, code, data):
            body = json.dumps(data).encode()
            self.send_response(code)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        @property
        def session(self):
            class AnonymousSession:
                def snapshot(self):
                    return None, 0
            return AnonymousSession()

    return namespace['do_GET'], Request


class CompanionRouteTests(unittest.TestCase):
    def test_terminal_root_and_static_assets_are_unavailable_but_api_routes_remain(self):
        do_get, request_type = load_get_route()
        for path in ('/', '/terminal.css', '/terminal.js', '/checkout-ui.js', '/scanner_input.js'):
            with self.subTest(path=path):
                request = request_type(path)
                do_get(request)
                self.assertEqual(request.response, 404)

        inventory = request_type('/api/inventory')
        do_get(inventory)
        self.assertEqual(inventory.response, 200)
        self.assertEqual(json.loads(inventory.wfile.getvalue()), [])

        checkout = request_type('/checkout/cart')
        do_get(checkout)
        self.assertEqual(checkout.response, 401)
        self.assertEqual(json.loads(checkout.wfile.getvalue())['error'], 'Scan your badge first')


if __name__ == '__main__':
    unittest.main()
