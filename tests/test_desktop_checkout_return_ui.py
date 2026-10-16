"""Contracts for completing checkout and return from Workshop management."""
import pathlib
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class DesktopCheckoutReturnTests(unittest.TestCase):
    def test_management_checkout_and_return_use_journaled_api_operations(self):
        desktop = (ROOT / 'desktop/desktop.js').read_text(encoding='utf-8')
        api = (ROOT / 'ops/desktop_api.py').read_text(encoding='utf-8')

        self.assertIn("button('Confirm checkout'", desktop)
        self.assertIn('async function checkoutConfirmDialog(', desktop)
        self.assertIn("write('checkout'", desktop)
        self.assertIn('request_key:uuid()', desktop)
        self.assertIn("api('operation/status',{request_key:key}", desktop)
        self.assertIn('No automatic retry', desktop)

        self.assertIn("if route == 'checkout':", api)
        self.assertIn('confirm_checkout(', api)
        self.assertIn("if route == 'return':", api)
        self.assertIn('confirm_return(', api)

    def test_checkout_cart_page_has_no_terminal_completion_link(self):
        desktop = (ROOT / 'desktop/desktop.js').read_text(encoding='utf-8')
        start = desktop.index('async function checkoutCartPage(')
        end = desktop.index('\nasync function equipmentPage(', start)
        page = desktop[start:end]
        self.assertNotIn('17749', page)
        self.assertNotIn('kiosk', page.lower())
        self.assertIn('checkoutConfirmDialog(state)', page)

    def test_uncertain_return_checks_status_without_resubmitting(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js is unavailable for the management UI fixture')
        desktop = (ROOT / 'desktop/desktop.js').read_text(encoding='utf-8')
        start = desktop.index('async function unresolvedOperation(')
        helper = desktop[start:desktop.index('\n', start)]
        script = r'''
const calls=[],buttons=[];let opened;
const node=(tag,text)=>({tag,text,children:[],append(...items){this.children.push(...items)},replaceChildren(...items){this.children=items}});
const button=(label,fn)=>{const value={label,fn};buttons.push(value);return value};
const openDialog=(_title,body)=>{opened=body};const closeDialog=()=>{};const go=()=>{};const toast=()=>{};
const api=async(path,data)=>{calls.push({path,data});return {status:'review'}};
'''+helper+r'''
(async()=>{const error=new Error('connection lost');error.request_key='stable-key';await unresolvedOperation(error,'Return');await buttons[0].fn();
if(calls.length!==1||calls[0].path!=='operation/status'||calls[0].data.request_key!=='stable-key')throw Error('uncertain return did not check its saved status exactly once');
if(JSON.stringify(calls).includes('return/confirm'))throw Error('uncertain return was resubmitted');
})().catch(error=>{console.error(error);process.exitCode=1});
'''
        result = subprocess.run([node, '-e', script], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
