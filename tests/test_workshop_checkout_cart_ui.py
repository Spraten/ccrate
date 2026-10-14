"""Native workshop checkout cart routing and server persistence contract."""
import pathlib
import re
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def function(source, name):
    match = re.search(r"(?:async\s+)?function\s+" + re.escape(name) + r"\s*\([^)]*\)\s*\{", source)
    if not match:
        raise AssertionError(f"missing function {name}")
    start = match.start()
    depth = 0
    for index in range(match.end() - 1, len(source)):
        depth += source[index] == "{"
        depth -= source[index] == "}"
        if depth == 0:
            return source[start:index + 1]
    raise AssertionError(f"unterminated function {name}")


class WorkshopCheckoutCartUiTests(unittest.TestCase):
    def test_manual_checkout_recovery_reports_receipt_asset_count_for_kits(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is unavailable for the checkout UI fixture")
        checkout = (ROOT / "kiosk/checkout-ui.js").read_text(encoding="utf-8")
        workflow = (ROOT / "kiosk/workflow-ui.js").read_text(encoding="utf-8")
        helpers = "\n".join(function(checkout, name) for name in ("checkoutAssetsForSelection", "checkoutReceiptAssetCount"))
        recover = function(workflow, "recoveryActions")
        script = helpers + "\n" + recover + r'''
let checkoutCartManaged=true,checkoutKitAssets={'kit':['kit','part']},checkoutCart=[{id:'kit'}],returnCart=[],routeRevision=1,identityGeneration=1,identityInstance='session',saved={status:'completed',count:3};
const buttons=[],counts=[];function node(){return {append(){}}}function primary(label,fn){buttons.push({label,fn});return {}};async function resolveTransaction(){return saved}async function transactionDone(mode,count){counts.push([mode,count])}
const shell={append(){}};
(async()=>{recoveryActions(shell,'request','checkout');await buttons.at(-2).fn();if(counts[0][1]!==3)throw Error('recovery ignored the actual receipt count');saved={status:'completed'};recoveryActions(shell,'request-2','checkout');await buttons.at(-2).fn();if(counts[1][1]!==2)throw Error('legacy fallback did not count kit assets')})().catch(error=>{console.error(error);process.exitCode=1});
'''
        subprocess.run([node, "-e", script], check=True, cwd=ROOT, capture_output=True, text=True)

    def test_kiosk_revision_reconciliation_keeps_local_additions_and_updates_to_saved_cart(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is unavailable for the checkout UI fixture")
        source = (ROOT / "kiosk/checkout-ui.js").read_text(encoding="utf-8")
        helper = function(source, "checkoutCartReconciliationIds")
        count_helper = function(source, "checkoutReceiptAssetCount")
        script = helper + r'''
const assert=(actual,expected,message)=>{if(JSON.stringify(actual)!==JSON.stringify(expected))throw Error(message+': '+JSON.stringify(actual))};
assert(checkoutCartReconciliationIds(['kit','desk-added'],['kit','desk-removed'],['kit','local-added']),['kit','desk-added','local-added'],'server additions and local additions survive while server removals are applied');
assert(checkoutCartReconciliationIds(['local-removed','kept','desk-added'],['local-removed','kept'],['kept']),['kept','desk-added'],'local removals are preserved alongside desk additions');
let checkoutCartManaged=true,checkoutKitAssets={'kit':['kit','component']};
const checkoutAssetsForSelection=items=>{const ids=new Set(items.map(item=>item.id));if(checkoutCartManaged)for(const [root,members] of Object.entries(checkoutKitAssets))if(ids.has(root))for(const id of members)ids.add(id);return [...ids]};
assert(checkoutReceiptAssetCount({count:3},[{id:'kit'}]),3,'completed receipt count is authoritative');
assert(checkoutReceiptAssetCount({status:'completed'},[{id:'kit'}]),2,'legacy completion fallback counts expanded kit assets rather than cart roots');
'''
        script = helper + "\n" + count_helper + script[len(helper) + 1:]
        subprocess.run([node, "-e", script], check=True, cwd=ROOT, capture_output=True, text=True)
        self.assertIn("checkoutCartNeedsReconcile", source)
        self.assertIn("Refresh saved cart", source)
        self.assertIn("Your local additions are kept", source)
        self.assertIn("checkoutReceiptAssetCount(saved,items)", source)
        self.assertIn("confirm.disabled=!!checkoutKey||checkoutCartNeedsReconcile", source)

        helper += "\n" + function(source, "reconcileCheckoutCart")
        script = helper + r'''
let checkoutCart=[{id:'keep',name:'Keep'},{id:'local-added',name:'Local addition'}],checkoutCartIds=new Set(['keep','desk-removed']),checkoutCartRevision=1,checkoutCartLoadedFor='1:session',checkoutCartLoading=false,checkoutCartManaged=true,checkoutCartNeedsReconcile=true,checkoutCartLoadError='',checkoutKitAssets={},checkoutKitEntities={},checkoutKitVersions={},checkoutFeedback='',checkoutMode=true,checkoutBusy=false,identityGeneration=1,identityInstance='session';
let rendered='';const renderCheckout=message=>{rendered=message};const refreshCheckoutAvailability=async()=>{};
const api=async path=>{if(path==='/checkout/cart')return {revision:2,items:['keep','desk-added']};throw Error('unexpected path '+path)};
const fetch=async url=>({ok:true,json:async()=>({entity:{id:'desk-added',name:'Desk addition'}})});
reconcileCheckoutCart().then(()=>{
 const assert=(value,message)=>{if(!value)throw Error(message)};
 assert(JSON.stringify(checkoutCart.map(item=>item.id))===JSON.stringify(['keep','desk-added','local-added']),'merged cart applies desk changes and keeps the local addition');
 assert(checkoutCart.find(item=>item.id==='local-added').name==='Local addition','local item details survive refresh');
 assert(checkoutCartRevision===2&&checkoutCartNeedsReconcile===false,'latest revision unlocks confirmation');
 assert(rendered.includes('Your local additions are kept'),'the refreshed list is explained before review');
}).catch(error=>{console.error(error);process.exitCode=1});
'''
        subprocess.run([node, "-e", script], check=True, cwd=ROOT, capture_output=True, text=True)

    def test_cart_page_is_valid_javascript(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is unavailable for the workshop cart fixture")
        source = (ROOT / "homebox-ui/overlay/lib/workshop-tools.js").read_text(encoding="utf-8")
        cart_page = function(source, "checkoutCartPage")
        result = subprocess.run(
            [node, "-e", "new Function(require('fs').readFileSync(0, 'utf8'))"],
            input=cart_page,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_cart_is_a_native_workshop_route_and_navigation_entry(self):
        page = (ROOT / "homebox-ui/overlay/pages/workshop/[tool].vue").read_text(encoding="utf-8")
        redirect = (ROOT / "homebox-ui/overlay/pages/workshop/index.vue").read_text(encoding="utf-8")
        tools = (ROOT / "homebox-ui/overlay/lib/workshop-tools.js").read_text(encoding="utf-8")
        self.assertIn('"checkout-cart"', page)
        self.assertIn('"checkout-cart"', redirect)
        self.assertRegex(tools, r"\['checkout-cart',\s*'Checkout cart'")
        self.assertIn("'checkout-cart':checkoutCartPage", tools)
        builder = (ROOT / "deploy/build-homebox-ui.py").read_text(encoding="utf-8")
        start = builder.index("const workshopLinks = computed")
        end = builder.index("]),", start) + 2
        self.assertIn('["checkout-cart", "Checkout cart"]', builder[start:end])
        cart_page = function(tools, "checkoutCartPage")
        self.assertIn("loadCheckoutCart()", cart_page)
        self.assertIn("button('Add'", cart_page)
        self.assertIn("button('Remove'", cart_page)
        self.assertIn("Remove unavailable or blocked items", cart_page)
        self.assertIn("view.append(search,content)", cart_page)
        self.assertIn("search.oninput=paint", cart_page)
        self.assertLess(cart_page.index("view.append(search,content)"), cart_page.index("function paint()"))

    def test_cart_reads_and_writes_the_revisioned_server_selection(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is unavailable for the workshop cart fixture")
        source = (ROOT / "homebox-ui/overlay/lib/workshop-tools.js").read_text(encoding="utf-8")
        helpers = "\n".join(function(source, name) for name in (
            "loadCheckoutCart", "saveCheckoutCart", "checkoutCartStatus", "checkoutCartReady", "checkoutCartReadyItems"))
        script = r'''
let context={identity:'user-a',group:{id:'group-a'},user:{id:'user-a'}},equipment=[],loans=[],busy=false;
const scope=()=>context.group.id+':'+context.user.id, uuid=()=> 'request-key';
let saved={revision:0,items:['missing','ready','held','blocked','multi']},calls=[],nativeIds=new Set(['ready','other','held','blocked','multi']);
async function api(path,data,identity){calls.push({path,data,identity});if(data){if(data.revision!==saved.revision)throw Error('stale revision');if(data.items.some(id=>!nativeIds.has(id)))throw Error('unknown equipment');saved={revision:saved.revision+1,items:[...data.items]};return saved}return {...saved,items:[...saved.items]}}
function equipmentBlocker(item){return item.blocker||item.checkout_blocker||''}
function held(id){return loans.find(row=>row.entity_id===id)}
'''+helpers+r'''
const assert=(value,message)=>{if(!value)throw Error(message)};
(async()=>{
  equipment=[{id:'ready',name:'Ready tool',condition:'Ready',quantity:1},{id:'other',name:'Second tool',condition:'Ready',quantity:1},{id:'blocked',name:'Blocked tool',condition:'Ready',blocker:'Needs inspection',quantity:1},{id:'held',name:'Loaned tool',condition:'Ready',quantity:1},{id:'multi',name:'Bulk tool',condition:'Ready',quantity:2}];
  loans=[{entity_id:'held',borrower:'Pat'}];
  assert(checkoutCartStatus('missing').reason==='Unavailable in this collection','missing assets remain visibly unavailable');
  assert(checkoutCartStatus('held').reason==='Checked out','currently loaned assets are blocked');
  assert(checkoutCartStatus('blocked').reason==='Needs inspection','inventory checkout blockers are reported');
  assert(checkoutCartStatus('multi').reason==='This workflow requires an individually tracked asset (quantity 1)','quantity greater than one is rejected by the kiosk');
  assert(checkoutCartReady(['ready']),'ready inventory can proceed to the existing kiosk flow');
  assert(!checkoutCartReady(['ready','held']),'a held asset prevents checkout');
  assert(JSON.stringify(checkoutCartReadyItems(['missing','ready','multi']))==='["ready"]','cleanup keeps only IDs accepted by checkout validation');
  assert(JSON.stringify(checkoutCartReadyItems(['held','multi']))==='[]','cleanup can clear a cart containing only invalid entries');
  let cart=await loadCheckoutCart();
  let staleRejected=false;try{await saveCheckoutCart(cart.items,cart.revision)}catch{staleRejected=true}
  assert(staleRejected,'a deleted native record prevents ordinary removal updates');
  cart=await saveCheckoutCart(checkoutCartReadyItems(cart.items),cart.revision);
  assert(saved.revision===1&&JSON.stringify(saved.items)==='["ready"]','cleanup persists only valid saved rows with a new revision');
  cart=await loadCheckoutCart();
  assert(cart.revision===1&&cart.items[0]==='ready','reload reads the saved cart from the server');
  cart=await saveCheckoutCart(['ready','other'],cart.revision);
  cart=await loadCheckoutCart();
  assert(cart.items.length===2,'adding an item persists across reload');
  cart=await saveCheckoutCart([],cart.revision);
  cart=await loadCheckoutCart();
  assert(cart.revision===3&&cart.items.length===0,'remove persists and stays removed after reload');
  cart=await saveCheckoutCart(checkoutCartReadyItems(['held','multi']),cart.revision);
  cart=await loadCheckoutCart();
  assert(cart.revision===4&&cart.items.length===0,'all-invalid cleanup persists an empty cart');
  assert(calls.every(call=>call.path==='checkout-cart'),'read and edit use the existing cart route');
  assert(calls[1].data.request_key==='request-key'&&calls[1].identity==='user-a','writes retain request identity and signed-in user scope');
  context={identity:'user-b',group:{id:'group-b'},user:{id:'user-b'}};
  await loadCheckoutCart();
  assert(calls.at(-1).identity==='user-b','reload uses the active native identity');
})().catch(error=>{console.error(error);process.exitCode=1});
'''
        result = subprocess.run([node, "-e", script], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
