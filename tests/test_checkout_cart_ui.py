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
        server = (ROOT/'deploy/kiosk-server.py').read_text()
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
        self.assertNotIn('This item is not in your saved checkout cart', source)
        self.assertIn('Current availability', source)
        self.assertIn('checkout-available', source)
        self.assertIn("'/checkout/availability?ids='", source)
        self.assertIn('refreshCheckoutAvailability([root],generation,instance)', source)
        self.assertIn('await refreshCheckoutAvailability(checkoutCart,generation,instance)', source)
        self.assertIn('await refreshCheckoutAvailability([checkoutCart.find(a=>a.id===e.id)])', source)
        self.assertIn('checkoutAvailabilityLabel', source)
        self.assertNotIn('issubset(saved[\'items\'])', server)
        self.assertIn("'original_items':saved['items']", server)
        self.assertIn('checkout_availability(client,ledger,group,ids)', server)

        script = '''
let checkoutCart=[{id:'kit-root'}],checkoutCartManaged=true,checkoutCartIds=new Set(['kit-root']),checkoutAvailability=new Map(),checkoutMode=false,checkoutFeedback='',identityGeneration=1,identityInstance='session',checkoutAvailabilityRequest=0;
let checkoutKitVersions={},checkoutKitAssets={},checkoutKitEntities={},checkoutKey='pending';
function renderCheckout(){}
let availabilityError='',lastAvailabilityPath='';async function api(path){if(availabilityError)throw Error(availabilityError);lastAvailabilityPath=path;const ids=decodeURIComponent(path.split('ids=')[1]||'').split(',');return ids.map(id=>({id,name:id==='kit-part'?'Part':'Kit',reason:id==='kit-part'?'Checkout operation requires recovery (pending)':null}))}
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

checkoutCartManaged=true;checkoutCartIds=new Set(['kit-root']);

checkoutCartManaged=false;checkoutCart=[root,child];checkoutKitAssets={'kit-root':['kit-root','kit-part']};
removeCheckoutSelection(child);
assert(checkoutCart.length===1&&checkoutCart[0].id==='kit-root','ordinary cart displays only the remaining root after child removal');
assert(JSON.stringify(checkoutAssetsForSelection(checkoutCart))===JSON.stringify(['kit-root']),'ordinary cart never submits an invisible removed kit child');
'''
        script = script.replace("function renderCheckout(){}", "function renderCheckout(){}\n"+function('checkoutAvailabilityLabel')+"\nasync "+function('refreshCheckoutAvailability'))
        script += "\n(async()=>{await refreshCheckoutAvailability([root,child]);assert(checkoutAvailability.get('kit-root')==='Available','refresh returns root status');assert(checkoutAvailability.get('kit-part')==='Checkout operation requires recovery (pending)','refresh returns unresolved operation blocker');checkoutKitAssets={'kit-root':['kit-root','kit-part']};checkoutKitEntities={'kit-root':[root,child]};await refreshCheckoutAvailability([root]);assert(decodeURIComponent(lastAvailabilityPath.split('ids=')[1])==='kit-root,kit-part','verified kit refresh includes every member');assert(checkoutAvailabilityLabel(root)==='Kit component Part: Checkout operation requires recovery (pending)','verified kit summary names blocked components');availabilityError='Availability service unavailable';await refreshCheckoutAvailability([root]);assert(checkoutAvailability.get('kit-root')==='Could not refresh availability: Availability service unavailable','refresh error is attached to the affected item')})().catch(error=>{console.error(error);process.exitCode=1});\n"
        subprocess.run([node, '-e', script], check=True, cwd=ROOT, capture_output=True, text=True)


if __name__ == '__main__':
    unittest.main()
