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

    def test_checkout_and_return_styles_are_owned_by_terminal_stylesheet(self):
        css = (ROOT / 'kiosk/terminal.css').read_text(encoding='utf-8')
        checkout = (ROOT / 'kiosk/checkout-ui.js').read_text(encoding='utf-8')
        returns = (ROOT / 'kiosk/return-ui.js').read_text(encoding='utf-8')
        workflow = (ROOT / 'kiosk/workflow-ui.js').read_text(encoding='utf-8')

        for selector in ('.checkout-shell', '.checkout-body', '.checkout-bottom',
                         '.checkout-button', '.return-row', '.return-controls',
                         '.workflow-dialog', '.workflow-message'):
            with self.subTest(selector=selector):
                self.assertIn(selector, css)
        self.assertIn('.workflow-focus-slider', css)
        self.assertIn('.item-note-textarea', css)
        self.assertIn("className='workflow-focus-slider'", workflow)
        self.assertIn("className='item-note-textarea'", workflow)
        self.assertNotRegex(workflow, r"(?:slider|textarea)\.style\s*=")
        for source in (checkout, returns):
            with self.subTest(source='runtime style injection'):
                self.assertNotRegex(source, r"node\(['\"]style['\"]\)")
                self.assertNotIn('document.head.append(', source)

    def test_support_workflow_static_styles_are_defined_in_terminal_css(self):
        css = (ROOT / 'kiosk/terminal.css').read_text(encoding='utf-8')
        workshop = (ROOT / 'kiosk/workshop-ui.js').read_text(encoding='utf-8')
        imports = (ROOT / 'kiosk/import-ui.js').read_text(encoding='utf-8')
        users = (ROOT / 'kiosk/users-ui.js').read_text(encoding='utf-8')
        labels = (ROOT / 'kiosk/label-editor.js').read_text(encoding='utf-8')

        class_sources = {
            '.workshop-button': workshop, '.workshop-native-link': workshop,
            '.workshop-native-photo': workshop, '.task5-input': workshop,
            '.task5-label': workshop, '.task5-location-select': workshop,
            '.import-select': imports, '.import-file': imports,
            '.import-row-checkbox': imports, '.import-label-preview': imports,
            '.member-badge-qr': users, '.member-badge-revoke': users,
            '.member-avatar-small': users, '.member-loan-card': users,
            '.member-loan-image': users, '.member-profile-picture': users,
            '.label-designer-frame': labels,
            '.reviewed-paper-export-frame': labels,
        }
        for selector, source in class_sources.items():
            with self.subTest(selector=selector):
                self.assertIn(selector, css)
                self.assertIn(selector[1:], source)

        for source in (workshop, imports, users, labels):
            with self.subTest(source='static inline presentation'):
                static_styles = source.replace("svg.style.height=`${Math.max(170,scroll.clientHeight-8)}px`", '').replace("iframe.style.height = `${Math.max(390, Math.min(900, available))}px`", '')
                self.assertNotRegex(static_styles, r"\.style(?:\.[\w]+)?\s*=")
                self.assertNotRegex(source, r"node\(['\"]style['\"]\)")
                self.assertNotIn('document.head.append(', source)
                self.assertNotIn('cssText =', source)

    def test_terminal_visual_tokens_and_dashboard_touch_targets_are_static(self):
        css = (ROOT / 'kiosk/terminal.css').read_text(encoding='utf-8')
        for contract in (
                '--terminal-deep-blue: #17384b',
                '--terminal-workshop-yellow: #f3c94e',
                'header {',
                'button:focus-visible',
                '.dashboard-actions .action',
                'min-height: 44px',
                '@media (max-width: 600px)'):
            with self.subTest(contract=contract):
                self.assertIn(contract, css)
