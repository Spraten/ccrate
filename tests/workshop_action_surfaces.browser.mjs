import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { chromium } from '../work/homebox-ui-dev/node_modules/.pnpm/@playwright+test@1.60.0/node_modules/@playwright/test/index.mjs';
import { transform } from '../work/homebox-ui-dev/node_modules/.pnpm/esbuild@0.27.7/node_modules/esbuild/lib/main.js';

const root = new URL('..', import.meta.url);
const read = async path => readFile(new URL(path, root), 'utf8');
const groups = (await read('homebox-ui/overlay/lib/equipment-groups.js')).replace(/^export (async )?function /gm, '$1function ');
const catalog = (await read('homebox-ui/overlay/lib/workshop-object-catalog.js')).replace(/^export const /gm, 'const ').replace(/^export function /gm, 'function ');
const recovery = (await read('homebox-ui/overlay/lib/label-print-recovery.js')).replace(/^export (async )?function /gm, '$1function ');
const source = (await read('homebox-ui/overlay/lib/workshop-tools.js'))
  .replace('import { mountLabelDesigner, exportReviewedPaper, createLabelDesignerSaveHandlers } from "./label-editor.js";\n', 'const mountLabelDesigner=()=>{}; const exportReviewedPaper=()=>{}; const createLabelDesignerSaveHandlers=()=>({});\n')
  .replace('import { projectEquipmentGroups, equipmentRecordLabel, groupHistoryMembers, loadGroupHistory, groupNotesPresentation } from "./equipment-groups.js";\n', groups + '\n')
  .replace('import { workshopObjectPresets, workshopPresetForDrawing } from "./workshop-object-catalog.js";\n', catalog + '\n')
  .replace('import { labelPrintFailure, labelReviewCanPrint, pendingLabelPrint, submitReviewedLabel, applyLabelPreview } from "./label-print-recovery.js";\n', recovery + '\n')
  .replace('export function mountWorkshopTools', 'function mountWorkshopTools')
  + '\nwindow.mountWorkshopTools=mountWorkshopTools;';
const workshopUUID = (await read('homebox-ui/overlay/lib/workshop-uuid.js')).replace(/^export function /, 'function ');
const composableSource = (await read('homebox-ui/overlay/composables/use-workshop.ts'))
  .replace('export { workshopUUID } from "~/lib/workshop-uuid";\nimport { workshopUUID } from "~/lib/workshop-uuid";', workshopUUID)
  .replace('export function useWorkshop()', 'function useWorkshop()')
  + '\nwindow.useWorkshop=useWorkshop;';
const durableWorkshopSource = (await transform(composableSource, { loader: 'ts', format: 'iife', target: 'es2020' })).code;

const browser = await chromium.launch({ headless: true, executablePath: '/usr/bin/chromium', args: ['--no-sandbox'] });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  page.on('pageerror', error => console.error(error.message));
  await page.setContent('<!doctype html><main id="root" class="workshop-native"><div id="view" tabindex="-1"></div><dialog id="dialog" aria-labelledby="dialog-title"><h2 id="dialog-title"></h2><button id="dialog-close">Close</button><div id="dialog-body"></div></dialog></main>');
  await page.addScriptTag({ content: source });
  await page.addStyleTag({ content: await read('homebox-ui/overlay/assets/css/workshop.css') });
  const rows = Array.from({ length: 20 }, (_, index) => ({
    id: `a0000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`,
    name: `Camera bin ${index + 1}`, assetId: `CAM-${index + 1}`, manufacturer: 'Northwind', modelNumber: 'Cam-X',
    serialNumber: `SN-${index + 1}`, condition: 'Ready', quantity: 1,
    parent: { id: '11111111-1111-4111-8111-111111111111' },
  }));
  await page.evaluate(items => {
    window.requests = [];
    const context = { value: { user: { id: 'member', name: 'Member' }, group: { id: 'collection', name: 'Collection' }, manager: false, identity: 'session' } };
    window.fixtureContext = context;
    window.fixtureWorkshop = {
      context,
      refresh: async () => context.value,
      pending: () => [],
      request: async (path, body) => {
        window.requests.push([path, body]);
        const route = path.split('?')[0];
        if (route === 'equipment') return structuredClone(items);
        if (route === 'locations') return [{ id: '11111111-1111-4111-8111-111111111111', name: 'Bins', isLocation: true }];
        if (route === 'loans') return [];
        if (route === 'history') return [];
        if (route === 'history/group') return { rows: [] };
        if (route === 'checkout-cart') return { revision: 7, items: ['a0000000-0000-4000-8000-000000000020'], notes: {} };
        if (route === 'kit') return { kit: false, entities: [] };
        if (route === 'checkout-availability') return new URLSearchParams(path.split('?')[1]).get('ids').split(',').map(id => ({ id, reason: 'Checked out' }));
        if (route === 'item-actions/status') {
          const id = new URLSearchParams(path.split('?')[1]).get('ids');
          return { items: [{ id, availability: 'available', can_checkin: false, can_add_note: true }] };
        }
        if (route === 'workshop') return { revision: 1, document: { version: 2, rooms: [{ id: 'room-1', name: 'Test room', width: 20, height: 16, unit: 'ft', objects: [{ id: 'drawing-1', name: 'Camera 20', kind: 'equipment', location_id: 'a0000000-0000-4000-8000-000000000020', x: 1, y: 1, width: 2, height: 2 }] }] }, locations: [{ id: 'a0000000-0000-4000-8000-000000000020', name: 'Camera bin 20', isLocation: false }], parents: items, types: [] };
        if (route === 'workshop/view') return { path: [{ id: 'a0000000-0000-4000-8000-000000000020', name: 'Camera bin 20', is_location: false }], selection: { target_id: 'a0000000-0000-4000-8000-000000000020', kind: 'exact', matches: [{ room_id: 'room-1', drawing_id: 'drawing-1', location_id: 'a0000000-0000-4000-8000-000000000020' }] }, contents: [] };
        return {};
      },
    };
    window.itemActionRequests = [];
    window.instance = window.mountWorkshopTools(document.querySelector('#root'), 'equipment', window.fixtureWorkshop, path => window.navigation.push(path), () => {}, { entityId: null, drawingId: null, roomId: null }, undefined, (request, trigger) => window.itemActionRequests.push({ request, trigger: trigger?.dataset.workshopActionItem }));
    window.navigation = [];
  }, rows);
  await page.getByRole('heading', { name: 'Equipment', exact: true }).waitFor();
  const group = page.locator('details.equipment-group');
  assert.equal(await group.count(), 1);
  assert.equal(await page.getByText('Add to cart', { exact: true }).first().isVisible(), false, 'collapsed group exposes no unit action');
  await group.locator(':scope > summary.equipment-group-summary').click();
  assert.equal(await page.locator('.equipment-member').count(), 20, 'all twenty units are available after expanding the group');
  await page.getByLabel('Search equipment').fill('Camera bin 20');
  assert.equal(await page.locator('.equipment-member').count(), 1, 'filter preserves only the matching unit');
  const unit = page.locator('.equipment-member').filter({ hasText: 'Camera bin 20' });
  await page.evaluate(() => {
    const original = window.fixtureWorkshop.request;
    window.actionStatusCalls = 0;
    window.fixtureWorkshop.request = async (path, body) => {
      if (path.startsWith('item-actions/status?ids=')) {
        window.actionStatusCalls++;
        if (window.actionStatusCalls === 1) return new Promise(resolve => { window.releaseClosedStatus = () => resolve({ items: [{ id: new URLSearchParams(path.split('?')[1]).get('ids'), availability: 'available', can_checkin: false, can_add_note: true }] }); });
      }
      return original(path, body);
    };
  });
  const actionSummary = unit.getByText('Item actions', { exact: true });
  await actionSummary.click();
  await page.waitForFunction(() => window.actionStatusCalls === 1);
  await page.evaluate(() => { const menu=document.querySelector('.workshop-item-actions'); menu.open=false; menu.dispatchEvent(new Event('toggle')); });
  await page.evaluate(() => window.releaseClosedStatus());
  await page.waitForTimeout(25);
  await page.evaluate(() => { const menu=document.querySelector('.workshop-item-actions'); menu.open=true; menu.dispatchEvent(new Event('toggle')); });
  await unit.getByRole('button', { name: 'Add note', exact: true }).waitFor();
  assert.equal(await page.evaluate(() => window.actionStatusCalls), 1, 'the resolved page-local status is reused after close and reopen');
  assert.equal(await unit.getByRole('button', { name: 'Check in', exact: true }).count(), 0, 'check-in is hidden unless the authoritative status grants permission');
  await unit.getByRole('button', { name: 'Add note', exact: true }).click();
  assert.deepEqual(await page.evaluate(() => window.itemActionRequests[0]), {
    request: { kind: 'note', itemId: 'a0000000-0000-4000-8000-000000000020', source: 'workshop' },
    trigger: 'a0000000-0000-4000-8000-000000000020',
  });
  assert.equal(await page.getByLabel('Search equipment').inputValue(), 'Camera bin 20');
  assert.deepEqual(await page.evaluate(() => window.navigation), []);

  await page.evaluate(() => { window.originalRequestBeforeProducts=window.fixtureWorkshop.request; window.instance.dispose(); });
  await page.addScriptTag({ content: durableWorkshopSource });
  await page.evaluate(() => {
    const memoryStorage=new Map();Object.defineProperty(window,'localStorage',{configurable:true,value:{getItem:key=>memoryStorage.get(key)||null,setItem:(key,value)=>memoryStorage.set(key,String(value)),removeItem:key=>memoryStorage.delete(key)}});
    const states = new Map(); window.useState = (key, init) => { if(!states.has(key)) states.set(key,{value:init()}); return states.get(key); };
    window.useCollections = () => ({selectedId:{value:'collection'}});
    window.useAuthContext = () => ({user:{id:'member',defaultGroupId:'collection'},invalidateSession(){}});
    window.computed = fn => ({get value(){return fn()}});
    window.durableCalls=[]; window.durableSaves=0; window.durableProducts=[{id:'prod-1',type_prefix:'DRONE',manufacturer:'Northwind',model_number:'Cam-X',model_code:'CX',updated_at:'v1',next_number:8,active_item_count:2,active_assigned_count:1,assignments:[{entity_id:'item-1',display_id:'CX-0007'}]},{id:'prod-2',type_prefix:'DRONE',manufacturer:'Acme',model_number:'Widget-Z',model_code:'WZ',updated_at:'w1',next_number:3,active_item_count:1,active_assigned_count:1,assignments:[{entity_id:'item-2',display_id:'WZ-0002'}]}];
    window.durableContext={user:{id:'member',name:'Member'},group:{id:'collection',name:'Collection'},identity:'member-session',manager:false};
    window.fetch=async(url,options={})=>{
      const path=url.replace('/workshop-api/',''); window.durableCalls.push({path,body:options.body?JSON.parse(options.body):null});
      const ok=(value,status=200)=>({ok:status<400,status,json:async()=>value});
      if(path==='context') return ok({...window.durableContext});
      if(path==='equipment/products') { if(window.durableLoadFail){window.durableLoadFail=false;return ok({error:'fixture load failure'},503)} return ok(window.emptyProductList?[]:structuredClone(window.durableProducts)); }
      if(path==='operation/status') { const key=JSON.parse(options.body).request_key; if(key===window.durableHistoricalKey)return ok({status:'completed',action:'equipment_product_model_code',result:{...structuredClone(window.durableProducts[0]),model_code:'CX2',updated_at:'v2'}}); return ok(key===window.durableConflictKey||key===window.durableNoStartKey?{status:'not_started'}:{status:'completed',action:'equipment_product_model_code',result:structuredClone(window.durableProducts[0])}); }
      if(path==='equipment/products/code') { const payload=JSON.parse(options.body); if(payload.model_code==='DUP'){window.durableConflictKey=payload.request_key;return ok({error:'Model code conflicts with another product'},409)} window.durableSaves++; const index=window.durableProducts.findIndex(product=>product.id===payload.product_id); window.durableProducts[index]={...window.durableProducts[index],model_code:payload.model_code,updated_at:'v'+(window.durableSaves+1)}; if(window.durableSaves===1) throw new Error('fixture lost committed response'); return ok(structuredClone(window.durableProducts[index])); }
      return ok({});
    };
    window.realWorkshop=window.useWorkshop(); window.realWorkshop.context.value=structuredClone(window.durableContext);
    window.instance=window.mountWorkshopTools(document.querySelector('#root'),'equipment-ids',window.realWorkshop,()=>{},()=>{}, {entityId:null,drawingId:null,roomId:null});
  });
  await page.addScriptTag({ content: durableWorkshopSource });
  await page.getByRole('heading', { name: 'Equipment ID codes', exact: true }).waitFor();
  assert.equal(await page.getByText('Next ID preview — not assigned: DRONE-CX-8').count(),1,'list preview shows the complete tentative ID');
  const productSearch = page.getByLabel('Search by model, model code, or assigned ID');
  const editButtons = page.getByRole('button', { name: 'Edit model code' });
  assert.equal(await editButtons.count(),2,'both distinguishable products start visible');
  await productSearch.fill('Northwind');
  assert.equal(await editButtons.count(),1,'manufacturer search filters out the other product');
  await productSearch.fill('Cam-X');
  assert.equal(await editButtons.count(),1,'model search filters by model number');
  await productSearch.fill('CX');
  assert.equal(await editButtons.count(),1,'model-code search filters by code');
  await productSearch.fill('CX-0007');
  assert.equal(await editButtons.count(),1,'assigned ID search narrows products');
  await productSearch.fill('missing-product');
  assert.equal(await editButtons.count(),0,'nonmatching search removes every product');
  assert.equal(await page.getByText('No equipment products match this search.').count(),1,'empty search results explain why the list has no rows');
  await productSearch.fill('');
  const northwindCard = page.locator('section').filter({hasText:'Northwind Cam-X'}).filter({hasText:'Model code:'}).first();
  await northwindCard.getByRole('button', { name: 'Edit model code' }).click();
  const codeDraft = page.getByRole('textbox', { name: 'Model code' });
  await codeDraft.fill('CX2');
  assert.equal(await page.getByText('Next ID preview — not assigned: DRONE-CX2-8').count(),1,'edit preview updates from the draft code');
  await page.getByRole('button', { name: 'Confirm model code change' }).click();
  await page.getByRole('alert').waitFor();
  assert.equal(await page.evaluate(() => window.durableSaves), 1, 'the real durable write helper must reach the API for an ordinary member');
  const pendingCodeEdit = await page.evaluate(() => JSON.parse(localStorage.getItem('workshop-pending:collection:member')||'[]')[0]);
  assert.ok(pendingCodeEdit?.key, 'the real helper records the uncertain request key');
  assert.deepEqual(pendingCodeEdit.intent, {product_id:'prod-1',model_code:'CX2',expected_updated_at:'v1',request_key:pendingCodeEdit.key});
  await page.evaluate(() => { window.instance.dispose(); window.instance=window.mountWorkshopTools(document.querySelector('#root'),'equipment-ids',window.realWorkshop,()=>{},()=>{}, {entityId:null,drawingId:null,roomId:null}); });
  await page.getByRole('button', { name: 'Check saved code update' }).click();
  await page.waitForFunction(() => window.durableCalls.some(call=>call.path==='operation/status'));
  assert.equal(await page.evaluate(key=>window.durableCalls.find(call=>call.path==='operation/status')?.body?.request_key===key,pendingCodeEdit.key),true,'status lookup reuses the original request identity');
  assert.equal(await page.evaluate(() => JSON.parse(localStorage.getItem('workshop-pending:collection:member')||'[]').length), 0, 'receipt reconciliation clears the original pending key after a remount');
  await northwindCard.getByRole('button', { name: 'Edit model code' }).click();
  await page.getByRole('textbox', { name: 'Model code' }).fill('CX3');
  await page.getByRole('button', { name: 'Confirm model code change' }).click();
  await page.waitForFunction(() => window.durableCalls.filter(call=>call.path==='equipment/products/code').length===2);
  const firstConsecutiveSave = await page.evaluate(() => window.durableCalls.filter(call=>call.path==='equipment/products/code')[1].body);
  assert.equal(firstConsecutiveSave.expected_updated_at, 'v2', 'first post-recovery edit uses the receipt version');
  await northwindCard.getByRole('button', { name: 'Edit model code' }).click();
  await page.getByRole('textbox', { name: 'Model code' }).fill('CX4');
  await page.getByRole('button', { name: 'Confirm model code change' }).click();
  await page.waitForFunction(() => window.durableCalls.filter(call=>call.path==='equipment/products/code').length===3);
  const secondConsecutiveSave = await page.evaluate(() => window.durableCalls.filter(call=>call.path==='equipment/products/code')[2].body);
  assert.equal(secondConsecutiveSave.expected_updated_at, 'v3', 'second consecutive edit uses the version returned by the first save without remount');
  assert.equal(await page.getByText('Model code: CX4').count(), 1);
  await page.evaluate(() => {
    window.instance.dispose(); window.durableHistoricalKey='historical-code-recovery';
    const payload={product_id:'prod-1',model_code:'CX2',expected_updated_at:'v1',request_key:window.durableHistoricalKey};
    localStorage.setItem('workshop-pending:collection:member',JSON.stringify([{key:window.durableHistoricalKey,path:'equipment/products/code',label:'Update model code',subject:'prod-1',at:new Date().toISOString(),intent:payload,identity:'member-session',group_id:'collection',user_id:'member'}]));
    window.instance=window.mountWorkshopTools(document.querySelector('#root'),'equipment-ids',window.realWorkshop,()=>{},()=>{}, {entityId:null,drawingId:null,roomId:null});
  });
  await page.getByRole('button', { name: 'Check saved code update' }).click();
  await page.waitForFunction(() => window.durableCalls.filter(call=>call.path==='operation/status').length>=2);
  assert.equal(await page.getByText('Model code: CX4').count(),1,'a historical receipt cannot overwrite the newer product summary loaded on remount');
  await northwindCard.getByRole('button', { name: 'Edit model code' }).click();
  await page.getByRole('textbox', { name: 'Model code' }).fill('DUP');
  await page.getByRole('button', { name: 'Confirm model code change' }).click();
  await page.getByRole('alert').filter({hasText:'Model code conflicts with another product'}).waitFor();
  assert.equal(await page.getByRole('textbox', { name: 'Model code' }).inputValue(), 'DUP', 'typed conflicts preserve the draft');
  await page.evaluate(() => {
    window.instance.dispose(); window.durableNoStartKey='stable-code-retry';
    const payload={product_id:'prod-1',model_code:'CX5',expected_updated_at:'v4',request_key:window.durableNoStartKey};
    localStorage.setItem('workshop-pending:collection:member',JSON.stringify([{key:window.durableNoStartKey,path:'equipment/products/code',label:'Update model code',subject:'prod-1',at:new Date().toISOString(),intent:payload,identity:'member-session',group_id:'collection',user_id:'member'}]));
    window.instance=window.mountWorkshopTools(document.querySelector('#root'),'equipment-ids',window.realWorkshop,()=>{},()=>{}, {entityId:null,drawingId:null,roomId:null});
  });
  await page.getByRole('button', { name: 'Check saved code update' }).click();
  await page.getByRole('button', { name: 'Retry same code edit' }).click();
  await page.waitForFunction(() => window.durableProducts[0].model_code==='CX5');
  const retryRequests=await page.evaluate(()=>window.durableCalls.filter(call=>call.path==='equipment/products/code').map(call=>call.body));
  assert.equal(retryRequests.at(-1).request_key,'stable-code-retry','a safe retry reuses the saved request key');
  await page.evaluate(() => { window.durableLoadFail=true; window.instance.dispose(); window.instance=window.mountWorkshopTools(document.querySelector('#root'),'equipment-ids',window.realWorkshop,()=>{},()=>{}, {entityId:null,drawingId:null,roomId:null}); });
  await page.getByRole('heading', { name: 'Could not load this page', exact: true }).waitFor();
  await page.getByRole('button', { name: 'Try loading again' }).click();
  await page.getByRole('heading', { name: 'Equipment ID codes', exact: true }).waitFor();
  await page.evaluate(() => { window.emptyProductList=true; window.instance.dispose(); window.instance=window.mountWorkshopTools(document.querySelector('#root'),'equipment-ids',window.realWorkshop,()=>{},()=>{}, {entityId:null,drawingId:null,roomId:null}); });
  await page.getByText('No equipment products are available yet.').waitFor();
  await page.evaluate(() => { window.emptyProductList=false; window.instance.dispose(); });

  await page.evaluate(() => {
    window.instance.dispose();
    window.fixtureLoans = [{ entity_id: 'a0000000-0000-4000-8000-000000000020', entity_name: 'Camera bin 20', borrower: 'Member' }];
    const originalRequest = window.originalRequestBeforeProducts;
    window.fixtureWorkshop.request = async (path, body) => path === 'loans' ? structuredClone(window.fixtureLoans) : originalRequest(path, body);
    window.instance = window.mountWorkshopTools(document.querySelector('#root'), 'loans', window.fixtureWorkshop, path => window.navigation.push(path), () => {}, { entityId: null, drawingId: null, roomId: null }, undefined, (request, trigger) => window.itemActionRequests.push({ request, trigger: trigger?.dataset.workshopActionItem }));
  });
  await page.getByRole('heading', { name: 'Loans & notes', exact: true }).waitFor();
  const loanAction = page.locator('.workshop-item-actions summary[aria-label="Actions for Camera bin 20"]');
  assert.equal(await loanAction.count(), 1, 'current-loan row exposes an action for that loaned entity');
  await loanAction.click();
  await page.getByRole('button', { name: 'Add note', exact: true }).last().click();
  assert.equal((await page.evaluate(() => window.itemActionRequests.at(-1))).request.itemId, 'a0000000-0000-4000-8000-000000000020');

  await page.evaluate(() => {
    window.instance.dispose();
    window.instance = window.mountWorkshopTools(document.querySelector('#root'), 'checkout-cart', window.fixtureWorkshop, path => window.navigation.push(path), () => {}, { entityId: null, drawingId: null, roomId: null }, undefined, (request, trigger) => window.itemActionRequests.push({ request, trigger: trigger?.dataset.workshopActionItem }));
  });
  await page.getByRole('heading', { name: 'Checkout cart', exact: true }).waitFor();
  assert.equal(await page.getByRole('button', { name: 'Check out with badge' }).isDisabled(), true, 'a checked-out item blocks checkout but remains planned');
  assert.equal(await page.getByRole('button', { name: 'Edit private note' }).count(), 1, 'saved cart item retains private note editing');
  await page.getByRole('button', { name: 'Edit private note' }).click();
  assert.deepEqual((await page.evaluate(() => window.itemActionRequests.at(-1))).request, { kind: 'cart', itemId: 'a0000000-0000-4000-8000-000000000020', source: 'cart' });

  await page.evaluate(() => {
    window.instance.dispose();
    const originalRequest = window.fixtureWorkshop.request;
    window.fixtureWorkshop.request = async (path, body) => {
      window.requests.push([path, body]);
      if (path.startsWith('workshop/view')) {
        const target = new URLSearchParams(path.split('?')[1]).get('id');
        return { path: [{ id: target, name: 'Bins', is_location: true }], selection: { target_id: target, kind: 'exact', matches: [] }, contents: [] };
      }
      return originalRequest(path, body);
    };
    window.fixtureWorkshop.context.value.manager = true;
    window.instance = window.mountWorkshopTools(document.querySelector('#root'), 'workshop', window.fixtureWorkshop, path => window.navigation.push(path), () => {}, { entityId: '11111111-1111-4111-8111-111111111111', drawingId: null, roomId: 'room-1' }, undefined, (request, trigger) => window.itemActionRequests.push({ request, trigger: trigger?.dataset.workshopActionItem }));
  });
  await page.getByRole('region', { name: 'Workshop inspector' }).waitFor();
  const beforeMapRefresh = await page.evaluate(() => window.requests.filter(([path]) => path.startsWith('workshop/view?id=')).length);
  await page.evaluate(() => window.instance.refreshItemAction({ kind: 'checkin', itemIds: ['a0000000-0000-4000-8000-000000000020'] }));
  const mapRefreshes = await page.evaluate(() => window.requests.filter(([path]) => path.startsWith('workshop/view?id=')).map(([path]) => path));
  assert.ok(mapRefreshes.length > beforeMapRefresh, 'a returned child refreshes the selected map location even when its ID differs');
  assert.ok(mapRefreshes.at(-1).includes('11111111-1111-4111-8111-111111111111'));

  await page.evaluate(() => {
    window.instance.dispose();
    window.instance = window.mountWorkshopTools(document.querySelector('#root'), 'equipment', window.fixtureWorkshop, () => {}, () => {}, { entityId: null, drawingId: null, roomId: null });
  });
  await page.getByRole('heading', { name: 'Equipment', exact: true }).waitFor();
  assert.equal(await page.locator('.workshop-item-actions').count(), 0, 'the original seven-argument call remains supported and omits action menus');
  console.log('PASS Workshop equipment, loan, and cart surfaces use exact unit IDs; permissions gate actions, blocked carts remain plannable with private-note editing, filters persist, and seven-argument mounts remain compatible.');
} finally {
  await browser.close();
}
