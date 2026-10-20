import assert from 'node:assert/strict';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { createServer } from '../work/homebox-ui-dev/node_modules/vite/dist/node/index.js';
import vue from '../work/homebox-ui-dev/node_modules/.pnpm/@vitejs+plugin-vue@6.0.7_vite@7.3.5_@types+node@25.9.3_jiti@1.21.7_terser@5.48.0_yaml@2_67e8ab11f94c3b8609189be60bcd60d1/node_modules/@vitejs/plugin-vue/dist/index.mjs';
import { chromium } from '../work/homebox-ui-dev/node_modules/.pnpm/@playwright+test@1.60.0/node_modules/@playwright/test/index.mjs';

const repo = path.resolve(new URL('..', import.meta.url).pathname);
const overlay = path.join(repo, 'homebox-ui/overlay');
const fixtureRoot = await mkdtemp(path.join(os.tmpdir(), 'item-actions-sfc-'));
const entry = path.join(fixtureRoot, 'main.js');
const html = path.join(fixtureRoot, 'index.html');
await writeFile(html, '<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><div id="app"></div><script type="module" src="/main.js"></script>');
await writeFile(entry, `
  import { createApp, reactive, ref, shallowRef, watch, computed, onMounted, onBeforeUnmount } from 'vue';
  import ItemQuickActions from ${JSON.stringify(pathToFileURL(path.join(overlay, 'components/Workshop/ItemQuickActions.vue')).href)};
  import ItemActionHost from ${JSON.stringify(pathToFileURL(path.join(overlay, 'components/Workshop/ItemActionHost.vue')).href)};
  import InventoryGroups from ${JSON.stringify(pathToFileURL(path.join(overlay, 'components/InventoryGroups.vue')).href)};
  import InventoryUnitActionLinks from ${JSON.stringify(pathToFileURL(path.join(overlay, 'components/InventoryUnitActionLinks.vue')).href)};
  import ChildContents from ${JSON.stringify(pathToFileURL(path.join(overlay, 'components/Location/ChildContents.vue')).href)};
  import EquipmentTemplateApply from ${JSON.stringify(pathToFileURL(path.join(overlay, 'components/Workshop/EquipmentTemplateApply.vue')).href)};
  import EquipmentTemplatePanel from ${JSON.stringify(pathToFileURL(path.join(overlay, 'components/Workshop/EquipmentTemplatePanel.vue')).href)};
  import { useItemActions } from ${JSON.stringify(pathToFileURL(path.join(overlay, 'composables/use-item-actions.ts')).href)};
  window.__paths = []; window.__writes = []; window.__noteLoads = []; window.__statusActive = 0; window.__statusMaxActive = 0; window.__holdStatus = false; window.__releaseStatus = null;
  window.__selectedCollection = ref('collection'); window.__authenticatedUser = reactive({ id:'member', defaultGroupId:'collection' });
  Object.assign(window, { reactive, ref, shallowRef, watch, computed, onMounted, onBeforeUnmount, useId:()=> 'fixture-id', useNuxtApp: () => window.__nuxtApp,
    useCollections: () => ({ selectedId: window.__selectedCollection }),
    useAuthContext: () => ({ user: window.__authenticatedUser, invalidateSession(){} }),
    useUserApi: () => window.__api, useWorkshop: () => window.__workshop, useItemActions: () => useItemActions() });
  const mutated = new Set();
  window.__mutated = mutated;
  const rowIds = ['11111111-1111-4111-8111-111111111111', ...Array.from({length:19}, (_,index)=>'11111111-1111-4111-8111-'+String(index+2).padStart(12,'0'))];
  const nativeRows = rowIds.map((id,index)=>({id,name:'Camera',assetId:'CAM-'+(index+1),manufacturer:'Northwind',modelNumber:'Cam-X',serialNumber:'SN-'+(index+1),condition:'Ready',quantity:1,updatedAt:'v1',entityType:{id:'type-1'},parent:{id:'22222222-2222-4222-8222-222222222222'}}));
  window.__nativeRows=nativeRows; window.__rowId=rowIds[0];
  window.__templates=[{id:'template-archived',name:'Archived drone',entity_type_id:'type-1',manufacturer:'Maker',model_number:'Air 2S',model_code:'M4P',description:'Reusable',tag_ids:[],archived:true},{id:'template-pending',name:'Pending drone',entity_type_id:'type-1',manufacturer:'Maker',model_number:'Air 3S',model_code:'M3',description:'Reusable',tag_ids:[],archived:true}]; window.__templateHistory=[]; window.__entityGets=[]; window.__holdGetId=null; window.__releaseHeldGet=null;
  window.__itemUpdates=[];
  window.__api = { authURL:path=>path, items:{ getAll:async({parentIds}={})=>{const rows=parentIds?nativeRows.filter(item=>parentIds.includes(item.parent.id)):nativeRows; return {data:{total:rows.length,items:rows}}}, get:async id=>{window.__entityGets.push(id); const row=nativeRows.find(item=>item.id===id); if(id===window.__holdGetId)return await new Promise(resolve=>{window.__releaseHeldGet=()=>resolve({data:{...row,manufacturer:'Northwind',modelNumber:'Cam-X',serialNumber:'SN-'+(rowIds.indexOf(id)+1)}})}); return {data:{...row,manufacturer:'Northwind',modelNumber:'Cam-X',serialNumber:'SN-'+(rowIds.indexOf(id)+1)}}}, update:async(id,payload)=>{window.__itemUpdates.push({id,payload}); return {data:{id,...payload}}}, getLocation:async()=>({data:{children:[]}}) } };
  window.__nuxtApp = {};
  window.__workshop = { context: ref({user:{id:'member',name:'Member'},group:{id:'collection',name:'Collection'},identity:'native-session'}), refresh: async()=>window.__workshop.context.value, request:(path,body)=>window.__request(path,body) };
  localStorage.setItem('equipment-template-lifecycle:collection:member:native-session', JSON.stringify({action:'restore',template_id:'template-pending',request_key:'pending-restore-key'}));
  localStorage.setItem('equipment-template-save:collection:member', JSON.stringify({request_key:'pending-save-key',payload:{fields:{name:'Archived drone',entity_type_id:'type-1'},source_entity_id:null,template_id:'template-archived',expected_updated_at:null},digest:'pending-save-digest',group_id:'collection',user_id:'member',identity:'native-session'}));
  localStorage.setItem('workshop-item-action:collection:member', JSON.stringify([{path:'item-actions/note',request_key:'recover-key',kind:'note',item_ids:['11111111-1111-4111-8111-111111111111'],identity:'native-session',group_id:'collection',user_id:'member',payload:{entity_id:'11111111-1111-4111-8111-111111111111',note:'saved'}}]));
  window.__request = async (path, body) => {
    window.__paths.push(path); if (body !== undefined) window.__writes.push({path,body});
    if (path.startsWith('equipment/templates?include_archived=true') || path === 'equipment/templates') return window.__templates.map(item=>({...item}));
    if (path === 'equipment/templates/save') return {...window.__templates.find(item=>item.id===body.template_id)};
    if (path === 'equipment/templates/archive' || path === 'equipment/templates/restore') { const intent=body; const prior=window.__templateHistory.find(row=>row.request_key===intent.request_key); if (!prior) { const row=window.__templates.find(item=>item.id===intent.template_id); row.archived=path.endsWith('/archive'); window.__templateHistory.push({...intent,action:row.archived?'archived':'restored'}); } return {...window.__templates.find(item=>item.id===intent.template_id)}; }
    if (path.startsWith('item-actions/status')) {
      window.__statusActive++;
      window.__statusMaxActive = Math.max(window.__statusMaxActive, window.__statusActive);
      await (window.__holdStatus ? new Promise(resolve => { window.__releaseStatus = resolve; }) : new Promise(resolve => setTimeout(resolve, 10)));
      const ids = new URLSearchParams(path.split('?')[1]).get('ids').split(',');
      window.__statusActive--;
      return {items:ids.map(id=>({id,availability:mutated.has(id)?'checked_out':'available',can_checkin:mutated.has(id),can_add_note:true,name:'Camera'}))};
    }
    if (path.startsWith('entity?id=')) { const id=path.slice('entity?id='.length); const row=nativeRows.find(item=>item.id===id); return {entity:row?{...row}:id==='33333333-3333-4333-8333-333333333333'?{id,name:'Return shelf'}:id==='22222222-2222-4222-8222-222222222222'?{id,name:'Camera bins'}:null}; }
    if (path.startsWith('kit?id=')) return {kit:false,versions:{}};
    if (path === 'item-actions/verify-badge') return {verification_id:'proof',required_items:body.item_ids,kit_versions:{}};
    if (path === 'item-actions/verify-item') return {verified_items:body.code==='CAM-2'?[body.code?rowIds[1]:rowIds[0]]:[rowIds[0]],required_items:[body.code==='CAM-2'?rowIds[1]:rowIds[0]]};
    if (path === 'item-actions/checkout') { body.assets.forEach(id=>mutated.add(id)); return {status:'completed',id:'receipt'}; }
    if (path === 'item-actions/checkin') { for (const target of body.targets) { const row=nativeRows.find(item=>item.id===target.entity_id); if (row) row.parent={id:target.destination_id||'22222222-2222-4222-8222-222222222222'}; mutated.delete(target.entity_id); } return {status:'completed',id:'return-receipt'}; }
    if (path.startsWith('history?entity=')) return [{action:'add_note',entity_id:new URLSearchParams(path.split('?')[1]).get('entity'),note_text:'Recent service note',created_at:'2026-10-19T12:00:00Z'}];
    if (path === 'operation/status') return {status:'completed',result:{status:'completed',id:'saved-receipt'}};
    return {};
  };
  const groups=[{key:'camera',name:'Northwind · Cam-X',items:nativeRows.slice(0,2).map(item=>({...item,status:'available',displayId:'ITEM-'+item.assetId})),recordCount:2,nativeQuantity:2,statusCounts:{available:2,checked_out:0,blocked:0,archived:0,unknown:0},thumbnail:null,locationSummary:'Bins'},{key:'archived-camera',name:'Archived Camera',items:[{id:'archived-unit',name:'Archived Camera',archived:true,status:'archived',quantity:1}],recordCount:1,nativeQuantity:1,statusCounts:{available:0,checked_out:0,blocked:0,archived:1,unknown:0},thumbnail:null,locationSummary:'Archive'}];
  const locations=[{id:'22222222-2222-4222-8222-222222222222',name:'Camera bins',itemCount:20},{id:'33333333-3333-4333-8333-333333333333',name:'Return shelf',itemCount:0}];
  createApp({ components: { ItemQuickActions, ItemActionHost, InventoryGroups, InventoryUnitActionLinks, ChildContents, EquipmentTemplateApply, EquipmentTemplatePanel }, setup:()=>{window.__actions=useItemActions(); const showDelayedMenu=ref(false); const templateModel=ref('template-archived'); const templateApplyCount=ref(0); window.__showDelayedMenu=showDelayedMenu; window.__templateModel=templateModel; window.__templateApplyCount=templateApplyCount; return {rowIds,groups,locations,showDelayedMenu,templateFields:{name:'Template name'},templateModel,templateApplied:()=>templateApplyCount.value++,loadGroupNotes:request=>window.__noteLoads.push(request),refreshItems:()=>{window.__refreshItems=(window.__refreshItems||0)+1;}};}, template: '<main><div v-for="id in rowIds" :key="id" class="inventory-unit"><ItemQuickActions :item-id="id" /></div><ItemQuickActions v-if="showDelayedMenu" :item-id="rowIds[0]" compact /><InventoryGroups :groups="groups" :page="1" :page-size="10" @load-notes="loadGroupNotes" @refresh-items="refreshItems" /><div data-child-view><ChildContents :locations="locations" direct-only /></div><EquipmentTemplateApply template-id="template-1" entity-type-id="type-1" :fields="templateFields" /><EquipmentTemplatePanel entity-type-id="type-1" :fields="templateFields" v-model="templateModel" @apply="templateApplied" /><ItemActionHost /></main>' })
    .component('InventoryUnitActionLinks', InventoryUnitActionLinks)
    .component('NuxtLink', { props: ['to'], template: '<a :href="to"><slot /></a>' }).component('Button', { props:['disabled'], template:'<button :disabled="disabled"><slot /></button>' }).mount('#app');
`);
const doublesPath = path.join(fixtureRoot, 'doubles.js');
const doubles = `
  import { defineComponent, h, ref } from 'vue';
  export function workshopUUID() { return crypto.randomUUID(); }
  export function useWorkshop() { const context=ref({user:{id:'member',name:'Member'},group:{id:'collection',name:'Collection'},identity:'native-session'}); return { context, refresh: async()=>context.value, request: (path,body) => window.__request(path,body) }; }
  export const Button = defineComponent({ props:['disabled','type','variant','ariaLabel'], setup(props,{slots,attrs}) { return () => h('button',{...attrs,disabled:props.disabled},slots.default?.()); } });
  export const Label = defineComponent({ setup(_, {slots,attrs}) { return () => h('label',attrs,slots.default?.()); } });
  export const Textarea = defineComponent({ props:['id','modelValue','maxlength'], emits:['update:modelValue'], setup(props,{emit,attrs}) { return () => h('textarea',{...attrs,id:props.id,value:props.modelValue,maxlength:props.maxlength,onInput:e=>emit('update:modelValue',e.target.value)}); } });
  export const LocationSelector = defineComponent({ props:['modelValue'], template:'<div data-testid="location-selection">{{ modelValue?.name || modelValue?.id || "Top level" }}</div>' });
  export const toast = { success(){} };
  export default LocationSelector;
`;
await writeFile(doublesPath, doubles);
const server = await createServer({
  configFile: false,
  root: fixtureRoot,
  plugins: [vue()],
  optimizeDeps: { noDiscovery: true, include: [] },
  resolve: { alias: [
    { find: /^vue$/, replacement: path.join(repo, 'work/homebox-ui-dev/node_modules/vue/dist/vue.esm-browser.js') },
    { find: /^@\/composables\/use-workshop$/, replacement: doublesPath },
    { find: /^@\/components\/(ui\/(button|label|textarea|sonner)|Location\/Selector\.vue)$/, replacement: doublesPath },
    { find: /^@\/components\/ui\/dialog$/, replacement: path.join(repo, 'work/homebox-ui-dev/components/ui/dialog/index.ts') },
    { find: /^@\/lib\/utils$/, replacement: path.join(repo, 'work/homebox-ui-dev/lib/utils.ts') },
    { find: /^@\/components\/ui\//, replacement: path.join(repo, 'work/homebox-ui-dev/components/ui/') },
    { find: /^reka-ui$/, replacement: path.join(repo, 'work/homebox-ui-dev/node_modules/reka-ui/dist/index.js') },
    { find: /^lucide-vue-next$/, replacement: path.join(repo, 'work/homebox-ui-dev/node_modules/lucide-vue-next/dist/esm/lucide-vue-next.js') },
    { find: /^@\/lib\/utils$/, replacement: path.join(repo, 'work/homebox-ui-dev/lib/utils.ts') },
    { find: /^~~\//, replacement: overlay + '/' }, { find: '@', replacement: overlay }, { find: '~', replacement: overlay },
  ] },
  server: { host: '127.0.0.1', port: 44000 + Math.floor(Math.random() * 15000), strictPort: true },
});
const browser = await chromium.launch({ headless: true, executablePath: '/usr/bin/chromium', args: ['--no-sandbox'] });
try {
  await server.listen();
  const address = server.httpServer.address();
  const transformed = await server.transformRequest('/main.js');
  if (!transformed) throw new Error('Vite did not transform the component fixture entry.');
  const page = await browser.newPage({ viewport: { width: 800, height: 600 } });
  page.setDefaultTimeout(5000); page.setDefaultNavigationTimeout(20000);
  page.on('console', message => console.error(`browser ${message.type()}: ${message.text()}`));
  page.on('response', response => { if (response.status() >= 400) console.error(`HTTP ${response.status()} ${response.url()}`); });
  page.on('pageerror', error => console.error(error.message));
  const navigation = await page.goto(`http://127.0.0.1:${address.port}/index.html`, { waitUntil: 'domcontentloaded' });
  if (navigation?.status() !== 200) throw new Error(`Component fixture returned HTTP ${navigation?.status()}.`);
  console.log('mounted actual components including EquipmentTemplateApply');
  await page.evaluate(() => { window.__actions.changed.value={kind:'checkin',itemIds:['archived-unit']}; });
  await page.waitForFunction(() => window.__paths.some(path => path.startsWith('item-actions/status?ids=') && new URLSearchParams(path.split('?')[1]).get('ids') === 'archived-unit'));
  await page.waitForTimeout(30);
  const archivedCard = page.locator('[aria-label="Grouped inventory"] article').filter({hasText:'Archived Camera'});
  assert.match(await archivedCard.innerText(), /0 available · 0 checked out · 0 blocked · 1 archived · 0 unknown/);
  await archivedCard.getByRole('button', {name:/Archived Camera/}).click();
  assert.match(await archivedCard.innerText(), /No assigned ID · Archived/);
  await archivedCard.getByRole('button', {name:/Archived Camera/}).click();
  await page.getByRole('button', { name: 'Apply to existing items' }).click();
  await page.getByText('Native items in this collection').waitFor();
  await page.locator('fieldset input[type="checkbox"]').first().check();
  await page.getByText('Preview · 1 selected').waitFor();
  await page.evaluate(() => { window.__holdGetId=window.__rowId; });
  await page.getByRole('button', { name: 'Confirm and apply' }).click();
  await page.waitForFunction(() => typeof window.__releaseHeldGet === 'function');
  await page.evaluate(() => { window.__selectedCollection.value='changed-collection'; window.__holdGetId=null; const release=window.__releaseHeldGet; window.__releaseHeldGet=null; release(); });
  await page.waitForTimeout(100);
  assert.equal(await page.evaluate(() => window.__itemUpdates.length), 0, 'changing selected collection while Workshop context is stale prevents a native update');
  await page.evaluate(() => { window.__selectedCollection.value='collection'; });
  await page.getByRole('button', { name: 'Close unit apply' }).click();
  const templateSelect=page.locator('#equipment-template-select');
  await templateSelect.waitFor();
  await page.waitForFunction(() => window.__templateModel.value === null);
  await page.getByRole('button', {name:'Retry pending template save'}).click();
  await page.getByText('was saved, but a collection member archived it before confirmation').waitFor();
  assert.equal(await page.evaluate(() => window.__templateModel.value), null);
  assert.equal(await page.evaluate(() => window.__templateApplyCount.value), 0, 'a pending save replay does not select or apply a template another member archived');
  await page.getByRole('button', {name:'Retry restore'}).waitFor();
  await page.getByRole('button', {name:'Retry restore'}).click();
  await page.waitForFunction(() => document.querySelectorAll('#equipment-template-select option[value="template-pending"]').length === 1);
  assert.equal(await templateSelect.locator('option[value="template-archived"]').count(), 0, 'archived templates are excluded from new-item selection');
  await page.getByRole('button', { name: /View archived templates/ }).click();
  await page.getByRole('button', { name: 'Restore Archived drone' }).click();
  await page.waitForFunction(() => document.querySelectorAll('#equipment-template-select option[value="template-archived"]').length === 1);
  await templateSelect.selectOption('template-archived');
  await page.getByRole('button', { name: 'Archive selected template' }).click();
  await templateSelect.locator('option[value="template-archived"]').waitFor({state:'detached'});
  assert.equal(await page.evaluate(() => window.__templateModel.value), null, 'archiving a selected template clears the active item selection');
  assert.deepEqual(await page.evaluate(() => window.__templateHistory.map(row=>row.action)), ['restored','restored','archived']);
  await page.evaluate(() => { window.__actions.invalidateStatus([window.__rowId]); window.__holdStatus=true; window.__showDelayedMenu.value=true; });
  await page.waitForFunction(() => typeof window.__releaseStatus === 'function');
  assert.equal(await page.locator('details').count(), 0, 'the action menu remains closed while its status request is pending');
  await page.evaluate(() => { window.__holdStatus=false; window.__releaseStatus(); });
  const delayedMenu = page.locator('details').first();
  await delayedMenu.waitFor();
  await delayedMenu.locator('summary').click();
  await delayedMenu.getByTestId('item-action-checkout').waitFor();
  await delayedMenu.locator('summary').click();
  console.log('closed menu status load completed and actions render on reopen');
  await page.getByTestId('item-action-resume').waitFor({ timeout: 5000 });
  await page.getByTestId('item-action-resume').click();
  await page.getByTestId('item-action-reconcile').click();
  await page.getByRole('dialog').waitFor({ state: 'detached', timeout: 5000 });
  await page.getByTestId('item-action-resume').waitFor({ state: 'detached', timeout: 5000 });
  console.log('reconciled pending action');
  console.log('recovery cleared, selecting first mounted row');
  const firstCheckout = page.locator('.inventory-unit').first().getByTestId('item-action-checkout');
  await firstCheckout.waitFor({ timeout: 5000 });
  await page.locator('.inventory-unit [data-testid="item-action-checkout"]').nth(19).waitFor({ timeout: 5000 });
  const statusCalls = await page.evaluate(() => window.__paths.filter(value => value.startsWith('item-actions/status?ids=') && new URLSearchParams(value.split('?')[1]).get('ids').split(',').some(id => window.__nativeRows.some(row => row.id === id))));
  assert.ok(statusCalls.length <= 4, '20 mounted rows are batched and use at most four requests');
  assert.ok(statusCalls.every(path => new URLSearchParams(path.split('?')[1]).get('ids').split(',').length <= 50));
  assert.ok(await page.evaluate(() => window.__statusMaxActive) <= 4, 'status request concurrency is bounded at four');
  await firstCheckout.click();
  await page.getByTestId('item-action-badge').fill('discarded badge');
  await page.getByTestId('item-action-verify-badge').click();
  await page.getByTestId('item-action-scan').fill('discarded item');
  await page.getByTestId('item-action-cancel').click();
  await page.getByRole('dialog').waitFor({ state: 'detached' });
  await firstCheckout.click();
  await page.getByTestId('item-action-badge').fill('badge');
  await page.getByTestId('item-action-verify-badge').click();
  assert.equal(await page.getByTestId('item-action-scan').inputValue(), '', 'closing clears item scan text before the next owner action');
  await page.getByTestId('item-action-cancel').click();
  await page.getByRole('dialog').waitFor({ state: 'detached' });
  assert.equal(await page.locator('[data-testid="item-action-checkin"]').count(), 0);
  await firstCheckout.click({ timeout: 3000 });
  await page.getByRole('dialog', { name: 'Check out equipment' }).waitFor();
  assert.ok(await page.evaluate(() => document.activeElement?.closest('[role="dialog"]') !== null));
  await page.keyboard.press('Escape');
  await page.getByRole('dialog', { name: 'Check out equipment' }).waitFor({ state: 'detached' });
  await page.waitForFunction(() => document.activeElement?.getAttribute('data-testid') === 'item-action-checkout');
  await firstCheckout.click();
  await page.getByRole('dialog', { name: 'Check out equipment' }).waitFor();
  await page.getByTestId('item-action-badge').fill('badge');
  await page.getByTestId('item-action-verify-badge').click();
  await page.getByTestId('item-action-scan').fill('CAM-1');
  await page.getByTestId('item-action-verify-item').click();
  await page.locator('#checkout-note-11111111-1111-4111-8111-111111111111').fill('Actual component note');
  await page.getByTestId('item-action-confirm').click();
  await page.getByRole('dialog', { name: 'Check out equipment' }).waitFor({ state: 'detached' });
  await page.waitForTimeout(200);
  await page.waitForFunction(() => document.activeElement?.hasAttribute('data-item-action-focus-fallback'));
  console.log('first checkout complete');
  assert.equal(await page.locator('.inventory-unit [data-testid="item-action-checkout"]').count(), 19);
  assert.ok((await page.evaluate(() => window.__paths)).some(value => value.startsWith('item-actions/status?ids=')));
  const checkout = await page.evaluate(() => window.__writes.find(row => row.path === 'item-actions/checkout'));
  assert.deepEqual(checkout.body.assets, ['11111111-1111-4111-8111-111111111111']);
  assert.deepEqual(checkout.body.notes, { '11111111-1111-4111-8111-111111111111': 'Actual component note' });
  const secondId = '11111111-1111-4111-8111-000000000002';
  const groupCard = page.locator('[aria-label="Grouped inventory"] article').first();
  await groupCard.getByRole('button', { name: /Northwind · Cam-X/ }).click();
  await page.waitForFunction(() => window.__noteLoads.some(row => row.entityIds?.length === 2));
  assert.equal(await page.evaluate(() => window.__noteLoads.find(row => row.entityIds?.length === 2).entityIds.length), 2, 'expanded InventoryGroups requests notes for its exact units');
  const secondUnitActions = page.locator(`[data-native-item-id="${secondId}"]`);
  await secondUnitActions.getByText('Actions', { exact: true }).click();
  await secondUnitActions.getByTestId('item-action-checkout').click();
  await page.getByRole('dialog', { name: 'Check out equipment' }).waitFor();
  await page.getByTestId('item-action-badge').fill('badge');
  await page.getByTestId('item-action-verify-badge').click();
  await page.getByTestId('item-action-scan').fill('CAM-2');
  await page.getByTestId('item-action-verify-item').click();
  await page.getByTestId('item-action-confirm').click();
  await page.getByRole('dialog', { name: 'Check out equipment' }).waitFor({ state: 'detached' });
  await page.waitForFunction(() => document.querySelector('[aria-label="Grouped inventory"]')?.textContent.includes('2 checked out'));
  await page.locator('[data-child-view]').getByRole('button', { name: /Expand Northwind · Cam-X, 20 items/ }).click();
  await page.waitForFunction(() => [...document.querySelectorAll('li')].some(row => row.textContent.includes('CAM-2') && row.textContent.includes('Checked out')));
  const writes = await page.evaluate(() => window.__writes.filter(row => row.path === 'item-actions/checkout'));
  assert.deepEqual(writes[1].body.assets, [secondId], 'expanded grouped row checkout preserves exact unit selection');
  const childView = page.locator('[data-child-view]');
  const childSecondRow = childView.locator('li').filter({ hasText: 'CAM-2' }).last();
  await childSecondRow.locator('summary').click();
  await childSecondRow.getByTestId('item-action-checkin').click();
  await page.getByRole('dialog', { name: 'Check in equipment' }).waitFor();
  await page.evaluate(() => window.__actions.setDraft({ destination_id: '33333333-3333-4333-8333-333333333333' }));
  await page.getByTestId('location-selection').getByText('Return shelf').waitFor();
  await page.getByTestId('item-action-confirm').click();
  await page.getByRole('dialog', { name: 'Check in equipment' }).waitFor({ state: 'detached' });
  const firstReturn = await page.evaluate(() => window.__writes.filter(row => row.path === 'item-actions/checkin').at(-1));
  assert.equal(firstReturn.body.targets[0].destination_id, '33333333-3333-4333-8333-333333333333', 'Return shelf shown in the selector is the submitted destination for the first returned item');
  await page.waitForFunction(() => window.__noteLoads.some(row => row.refresh && row.entityIds?.includes('11111111-1111-4111-8111-000000000002')));
  assert.ok(await page.evaluate(() => window.__refreshItems > 0), 'InventoryGroups requests a filtered snapshot refresh after location changes');
  await page.waitForFunction(() => [...document.querySelectorAll('[data-child-view] li')].some(row => row.textContent.includes('CAM-2') && row.querySelector('a[href*="33333333-3333-4333-8333-333333333333"]')));
  assert.ok(await page.evaluate(() => [...document.querySelectorAll('[data-child-view] li')].some(row => row.textContent.includes('CAM-2') && row.querySelector('a[href*="33333333-3333-4333-8333-333333333333"]'))), 'alternate-destination check-in moves the exact row under the loaded destination location');
  await page.waitForFunction(() => [...document.querySelectorAll('[data-child-view] li')].some(row => row.textContent.includes('Recent service note')));
  const firstId = '11111111-1111-4111-8111-111111111111', thirdId = '11111111-1111-4111-8111-000000000003';
  await page.evaluate(async id => { window.__mutated.add(id); await window.__actions.open({ kind: 'checkin', itemId: id }); }, thirdId);
  await page.getByRole('dialog', { name: 'Check in equipment' }).waitFor();
  await page.evaluate(() => window.__actions.setDraft({ destination_id: '22222222-2222-4222-8222-222222222222' }));
  await page.getByTestId('location-selection').getByText('Camera bins').waitFor();
  await page.getByTestId('item-action-confirm').click();
  await page.getByRole('dialog', { name: 'Check in equipment' }).waitFor({ state: 'detached' });
  const secondReturn = await page.evaluate(() => window.__writes.filter(row => row.path === 'item-actions/checkin').at(-1));
  assert.equal(secondReturn.body.targets[0].destination_id, '22222222-2222-4222-8222-222222222222');
  assert.equal(await page.getByTestId('location-selection').count(), 0, 'the selector closes with the completed return before a consecutive distinct-destination return');
  await page.evaluate(({ firstId, thirdId }) => {
    window.__entityGets=[]; window.__holdGetId=firstId;
    window.__nativeRows[0].parent={id:'33333333-3333-4333-8333-333333333333'};
    window.__actions.changed.value={kind:'checkin',itemIds:[firstId]};
  }, { firstId, thirdId });
  await page.waitForFunction(() => typeof window.__releaseHeldGet === 'function');
  await page.evaluate(thirdId => { window.__actions.changed.value={kind:'note',itemIds:[thirdId]}; }, thirdId);
  await page.waitForFunction(thirdId => window.__entityGets.includes(thirdId), thirdId);
  await page.evaluate(() => { window.__holdGetId=null; window.__releaseHeldGet(); });
  const destinationArticle = childView.locator('article').last();
  await destinationArticle.getByRole('button', { name: /Expand Northwind · Cam-X, 2 items/ }).waitFor();
  await destinationArticle.getByRole('button', { name: /Expand Northwind · Cam-X, 2 items/ }).click();
  await page.waitForFunction(() => [...document.querySelectorAll('[data-child-view] li')].some(row => row.textContent.includes('CAM-1') && row.querySelector('a[href*="33333333-3333-4333-8333-333333333333"]')));
  assert.ok(true, 'an unrelated action completion does not cancel the held unit reparent refresh');
  console.log('PASS actual ItemQuickActions, ItemActionHost, useItemActions, InventoryGroups, ChildContents and ActionDialog mounts; controller batching and row-level status/count refresh verified.');
} finally {
  await browser.close();
  await server.close();
  await rm(fixtureRoot, { recursive: true, force: true });
}
