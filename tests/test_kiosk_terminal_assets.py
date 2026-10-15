"""Contracts for the extracted terminal shell assets."""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class KioskTerminalAssetTests(unittest.TestCase):
    def test_shell_references_existing_terminal_assets_and_keeps_dashboard_actions(self):
        page = (ROOT / 'kiosk/index.html').read_text(encoding='utf-8')
        css = ROOT / 'kiosk/terminal.css'
        script = ROOT / 'kiosk/terminal.js'

        self.assertIn('href="/terminal.css"', page)
        self.assertIn('src="/terminal.js"', page)
        self.assertTrue(css.is_file())
        self.assertTrue(script.is_file())
        source = script.read_text(encoding='utf-8')
        for label in ('Check Out', 'Return', 'Add Notes to Item', 'Find Item',
                      'Browse Stock', 'Workshop', 'Add Equipment'):
            self.assertRegex(source, rf"['\"]{re.escape(label)}['\"]")

    def test_static_server_registers_terminal_assets(self):
        server = (ROOT / 'deploy/kiosk-server.py').read_text(encoding='utf-8')
        for path, filename, mime in (
                ('/terminal.css', 'terminal.css', 'text/css'),
                ('/terminal.js', 'terminal.js', 'text/javascript')):
            with self.subTest(path=path):
                route = re.search(
                    rf"elif self\.path\s*==\s*['\"]{re.escape(path)}['\"]:(.*?)(?=\n\s*elif |\n\s*else:)",
                    server, re.S)
                self.assertIsNotNone(route, f'{path} route is missing')
                self.assertIn(filename, route.group(1))
                self.assertIn(mime, route.group(1))
