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


    def test_kiosk_revision_reconciliation_and_receipt_asset_count(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js is unavailable for the checkout UI fixture')
        source = (ROOT/'kiosk/checkout-ui.js').read_text(encoding='utf-8')
        ids_start=source.index('function checkoutCartReconciliationIds(')
        ids_helper=source[ids_start:source.index('\n',ids_start)]
        count_start=source.index('function checkoutReceiptAssetCount(')
        count_helper=source[count_start:source.index('\n',count_start)]
        assets_start=source.index('function checkoutAssetsForSelection(')
        assets_helper=source[assets_start:source.index('\n',assets_start)]
        reconcile_start=source.index('async function reconcileCheckoutCart(')
        reconcile=source[reconcile_start:source.index('\nfunction removeCheckoutSelection',reconcile_start)]
        script='\n'.join([ids_helper,count_helper,assets_helper])+r'''
let checkoutCartManaged=true,checkoutKitAssets={'kit':['kit','component']};
const assert=(actual,expected,message)=>{if(JSON.stringify(actual)!==JSON.stringify(expected))throw Error(message+': '+JSON.stringify(actual))};
assert(checkoutCartReconciliationIds(['kit','desk-added'],['kit','desk-removed'],['kit','local-added']),['kit','desk-added','local-added'],'server and local additions survive while server removals apply');
assert(checkoutCartReconciliationIds(['local-removed','kept','desk-added'],['local-removed','kept'],['kept']),['kept','desk-added'],'local removals and desk additions reconcile');
assert(checkoutReceiptAssetCount({count:3},[{id:'kit'}]),3,'completed receipt count is authoritative');
assert(checkoutReceiptAssetCount({status:'completed'},[{id:'kit'}]),2,'kit fallback counts all assets');
let checkoutCart=[{id:'keep',name:'Keep'},{id:'local-added',name:'Local addition'}],checkoutCartIds=new Set(['keep','desk-removed']),checkoutCartRevision=1,checkoutCartLoadedFor='1:session',checkoutCartLoading=false,checkoutCartNeedsReconcile=true,checkoutCartLoadError='',checkoutKitEntities={},checkoutKitVersions={},checkoutFeedback='',checkoutMode=true,checkoutBusy=false,identityGeneration=1,identityInstance='session';
let rendered='';const renderCheckout=message=>{rendered=message};const refreshCheckoutAvailability=async()=>{};
const api=async path=>{if(path==='/checkout/cart')return {revision:2,items:['keep','desk-added']};throw Error('unexpected path '+path)};
const fetch=async url=>({ok:true,json:async()=>({entity:{id:'desk-added',name:'Desk addition'}})});
'''
        script += '\n' + reconcile + r'''
reconcileCheckoutCart().then(()=>{
 assert(JSON.stringify(checkoutCart.map(item=>item.id))===JSON.stringify(['keep','desk-added','local-added']),'refresh merges desk changes and keeps local additions');
 assert(checkoutCart.find(item=>item.id==='local-added').name==='Local addition','local data survives refresh');
 assert(checkoutCartRevision===2&&!checkoutCartNeedsReconcile,'latest revision unlocks confirmation');
 assert(rendered.includes('Your local additions are kept'),'updated list is explained before review');
}).catch(error=>{console.error(error);process.exitCode=1});
'''
        subprocess.run([node,'-e',script],check=True,cwd=ROOT,capture_output=True,text=True)
        self.assertIn('checkoutCartNeedsReconcile',source)
        self.assertIn('Refresh saved cart',source)
        self.assertIn('checkoutReceiptAssetCount(saved,items)',source)
        self.assertIn('confirm.disabled=!!checkoutKey||checkoutCartNeedsReconcile',source)


    def test_manual_checkout_recovery_uses_completed_receipt_asset_count(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js is unavailable for the checkout UI fixture')
        checkout = (ROOT/'kiosk/checkout-ui.js').read_text(encoding='utf-8')
        workflow = (ROOT/'kiosk/workflow-ui.js').read_text(encoding='utf-8')
        def function(source, name):
            start = source.index('function '+name+'(')
            ends = [value for value in (source.find('\nfunction ', start+1),
                                         source.find('\nasync function ', start+1)) if value >= 0]
            return source[start:min(ends) if ends else len(source)]
        helpers = function(checkout, 'checkoutAssetsForSelection')+'\n'+function(checkout, 'checkoutReceiptAssetCount')
        recovery = function(workflow, 'recoveryActions')
        script = helpers+'\n'+recovery+r'''
let checkoutCartManaged=true,checkoutKitAssets={'kit':['kit','part']},checkoutCart=[{id:'kit'}],returnCart=[],routeRevision=1,identityGeneration=1,identityInstance='session',saved={status:'completed',count:3};
const buttons=[],counts=[];function node(){return {append(){}}}function primary(label,fn){buttons.push({label,fn});return {}};async function resolveTransaction(){return saved}async function transactionDone(mode,count){counts.push([mode,count])}
const shell={append(){}};
(async()=>{recoveryActions(shell,'request','checkout');await buttons.at(-2).fn();if(counts[0][1]!==3)throw Error('recovery ignored receipt count');saved={status:'completed'};recoveryActions(shell,'request-2','checkout');await buttons.at(-2).fn();if(counts[1][1]!==2)throw Error('legacy fallback ignored kit assets')})().catch(error=>{console.error(error);process.exitCode=1});
'''
        subprocess.run([node, '-e', script], check=True, cwd=ROOT, capture_output=True, text=True)

if __name__ == '__main__':
    unittest.main()
