"""Browser selection contract for saved kit checkout carts."""
import pathlib
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class CheckoutCartUiTests(unittest.TestCase):
    def test_saved_kit_can_be_rescanned_removed_and_readded_as_a_root_selection(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js is unavailable for the checkout UI fixture')
        source = (ROOT/'kiosk/checkout-ui.js').read_text()
        page = (ROOT/'kiosk/index.html').read_text()

        def function(name):
            start = source.index('function '+name+'(')
            ends = [value for value in (source.find('\nfunction ', start+1),
                                         source.find('\nasync function ', start+1)) if value >= 0]
            return source[start:min(ends) if ends else len(source)]

        add_start = page.index('async function addCheckout(e){')
        add_end = page.index('\nasync function confirmCheckout', add_start)
        add = page[add_start:add_end]
        render_kit_start = page.index("function renderKit(message=''){")
        render_kit_end = page.index('\nasync function kitManager', render_kit_start)
        render_kit = page[render_kit_start:render_kit_end]
        self.assertLess(add.index('await maybeKit(e,\'checkout\')'), add.index('checkoutCart.some(a=>a.id===e.id)'))
        self.assertIn('useVerifiedCheckoutKit(draft)', render_kit)

        script = '''
let checkoutCart=[{id:'kit-root'}],checkoutCartManaged=true,checkoutCartIds=new Set(['kit-root']);
let checkoutKitVersions={},checkoutKitAssets={},checkoutKey='pending';
function renderCheckout(){}
'''+function('checkoutAssetsForSelection')+'\n'+function('removeCheckoutSelection')+'\n'+function('useVerifiedCheckoutKit')+'''
const assert=(value,message)=>{if(!value)throw Error(message)};
const root={id:'kit-root',name:'Kit'},child={id:'kit-part',name:'Part'};
const draft={root,entities:[root,child],versions:{'kit-root':'current'}};
useVerifiedCheckoutKit(draft);
assert(checkoutCart.length===1&&checkoutCart[0].id==='kit-root','managed cart keeps the saved kit as one editable root selection');
assert(new Set(checkoutAssetsForSelection(checkoutCart)).size===2,'checkout assets expand to include the verified component');
assert(checkoutKitVersions['kit-root']==='current','verification captures the current kit revision');
removeCheckoutSelection(root);
assert(checkoutCart.length===0&&!checkoutKitAssets['kit-root']&&!checkoutKitVersions['kit-root'],'removing the root clears its expansion and verification');
assert(checkoutAssetsForSelection(checkoutCart).length===0,'removed roots do not contribute checkout assets');
useVerifiedCheckoutKit(draft);
assert(checkoutCart.length===1&&checkoutCart[0].id==='kit-root','rescanning can re-add the saved root');
assert(new Set(checkoutAssetsForSelection(checkoutCart)).has('kit-part'),'re-added root restores the expanded asset subset');
'''
        subprocess.run([node, '-e', script], check=True, cwd=ROOT, capture_output=True, text=True)


if __name__ == '__main__':
    unittest.main()
