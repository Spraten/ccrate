import ast
import io
import pathlib
import unittest
from urllib.parse import parse_qs, urlsplit

ROOT = pathlib.Path(__file__).resolve().parents[1]


class KioskStaticAssetTests(unittest.TestCase):
    def test_scanner_input_script_is_served_with_javascript_mime_type(self):
        source_path = ROOT / 'deploy/kiosk-server.py'
        tree = ast.parse(source_path.read_text(encoding='utf-8'))
        handler = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Handler')
        method = next(node for node in handler.body if isinstance(node, ast.FunctionDef) and node.name == 'do_GET')
        namespace = {
            'desktop_handle': lambda *_args: False,
            'ROOT': ROOT,
            'lock': object(), 'ledger': object(), 'shelf_checks': object(), 'badges': object(),
            'native_jobs': object(), 'imports': object(), 'workshop': object(), 'sessions': object(),
            'label_layouts': object(), 'LABEL_ASSET_ROOT': ROOT,
            'urlsplit': urlsplit, 'parse_qs': parse_qs,
            'terminal_assets': lambda: ROOT / 'kiosk',
        }
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(source_path), 'exec'), namespace)

        class Request:
            def __init__(self):
                self.path = '/scanner_input.js'
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

        request = Request()
        namespace['do_GET'](request)

        self.assertEqual(request.response, 200)
        self.assertEqual(request.response_headers['Content-Type'], 'text/javascript; charset=utf-8')
        self.assertEqual(request.wfile.getvalue(), (ROOT / 'kiosk/scanner_input.js').read_bytes())


if __name__ == '__main__':
    unittest.main()
