import test from 'node:test';
import assert from 'node:assert/strict';
import { PACKAGING_OPTIONS, createSuggestionLookup, selectSuggestion, validateCustomRows, buildNativeMetadataUpdate, nativeMetadataMatches, sameFieldNotes, persistFieldNotes } from '../homebox-ui/overlay/lib/item-create-fields.js';
import * as detailHelpers from '../homebox-ui/overlay/lib/item-metadata.js';
const { detailMetadataDraft, saveDetailMetadata, changeRelatedItem, searchRelatedItems } = detailHelpers;

test('detail draft loads packaging and Name, Value, Note from native item and metadata', () => {
  const item = { serialNumber: 'SN', fields: [{ id: 'p', name: 'Device Packaging', type: 'text', textValue: 'Bag' }, { id: 'f', name: 'Color', type: 'text', textValue: 'red' }] };
  assert.deepEqual(detailMetadataDraft(item, { fieldNotes: { color: 'shade' } }), { serialNumber: 'SN', packaging: 'Bag', rows: [{ id: 'f', name: 'Color', value: 'red', note: 'shade' }] });
});

test('detail draft reads canonical Notes keys for expanding Unicode field names', () => {
  assert.deepEqual(detailMetadataDraft({ fields: [{ name: 'Straße', type: 'text', textValue: 'A' }] }, { fieldNotes: { strasse: 'label' } }).rows, [{ name: 'Straße', value: 'A', note: 'label' }]);
});

test('renaming a detail custom field preserves its native field ID', async () => {
  const current = { id: 'a', parent: { id: 'loc' }, entityType: { id: 'type' }, tags: [], serialNumber: '', fields: [{ id: 'field-id', name: 'Color', type: 'text', textValue: 'red' }] };
  let stored = current;
  const api = { items: { get: async () => ({ data: stored }), update: async (_id, update) => { stored = { ...current, ...update }; return { data: stored }; } } };
  const workshop = { request: async () => ({ fieldNotes: { hue: 'shade' } }) };
  await saveDetailMetadata({ api, workshop, item: current, draft: { serialNumber: '', packaging: '', rows: [{ id: 'field-id', name: 'Hue', value: 'red', note: 'shade' }] }, identity: 'session', requestKey: 'key' });
  assert.deepEqual(stored.fields.map(field => [field.id, field.name]), [['field-id', 'Hue']]);
});

test('detail save keeps field IDs and unrelated fields, then saves Notes with confirmed readback', async () => {
  const calls = [];
  const item = { id: 'one', name: 'Camera', parent: { id: 'loc' }, entityType: { id: 'type' }, tags: [], serialNumber: 'old', fields: [{ id: 'p', name: 'Device Packaging', type: 'text', textValue: 'Bag' }, { id: 'f', name: 'Color', type: 'text', textValue: 'red' }, { id: 'u', name: 'Weight', type: 'number', numberValue: 4 }] };
  const draft = { serialNumber: 'new', packaging: 'HardCase', rows: [{ name: 'Color', value: 'blue', note: 'deep' }] };
  const updated = { ...item, serialNumber: 'new', fields: [{ ...item.fields[0], textValue: 'HardCase' }, { ...item.fields[1], textValue: 'blue' }, item.fields[2]] };
  let nativeSaved = false;
  const api = { items: { update: async (id, payload) => { calls.push(['native', id, payload]); nativeSaved = true; return { data: updated }; }, get: async () => ({ data: nativeSaved ? updated : item }) } };
  const workshop = { request: async (path, body) => { calls.push(['metadata', path, body]); return { fieldNotes: { color: 'deep' } }; } };
  await saveDetailMetadata({ api, workshop, item, draft, identity: 'session', requestKey: 'same-key' });
  assert.equal(calls[0][0], 'native');
  assert.deepEqual(calls[0][2].fields.map(field => field.id), ['p', 'f', 'u']);
  assert.equal(calls[0][2].parentId, 'loc');
  assert.equal(calls[1][1], 'item-metadata/field-notes');
  assert.equal(calls[1][2].request_key, 'same-key');
});

test('failed Notes save leaves native item saved and retry reuses request key', async () => {
  let writes = 0; let fail = true;
  const item = { id: 'one', parent: { id: 'loc' }, entityType: { id: 'type' }, tags: [], serialNumber: '', fields: [] };
  const draft = { serialNumber: '', packaging: 'Bag', rows: [{ name: 'Color', value: 'red', note: 'shade' }] };
  const saved = { ...item, fields: [{ name: 'Device Packaging', type: 'text', textValue: 'Bag' }, { name: 'Color', type: 'text', textValue: 'red' }] };
  const api = { items: { update: async () => { writes++; return { data: saved }; }, get: async () => ({ data: writes ? saved : item }) } };
  const keys = [];
  const workshop = { request: async (path, body) => { if (path === 'item-metadata/field-notes') { keys.push(body.request_key); if (fail) { fail = false; throw Error('Notes unavailable'); } } return { fieldNotes: { color: 'shade' } }; } };
  await assert.rejects(() => saveDetailMetadata({ api, workshop, item, draft, identity: 'session', requestKey: 'same-key' }), /Notes unavailable/);
  await saveDetailMetadata({ api, workshop, item: saved, draft, identity: 'session', requestKey: 'same-key' });
  assert.equal(writes, 1); assert.deepEqual(keys, ['same-key', 'same-key']);
});

test('detail save rejects a Notes readback that omits a requested note', async () => {
  const item = { id: 'a', parent: { id: 'loc' }, entityType: { id: 'type' }, tags: [], serialNumber: '', fields: [{ id: 'f', name: 'Color', type: 'text', textValue: 'red' }] };
  const api = { items: { get: async () => ({ data: item }), update: async () => { throw Error('native update should be skipped'); } } };
  const workshop = { request: async () => ({ fieldNotes: {} }) };
  await assert.rejects(() => saveDetailMetadata({ api, workshop, item, draft: { serialNumber: '', packaging: '', rows: [{ id: 'f', name: 'Color', value: 'red', note: 'shade' }] }, identity: 'session', requestKey: 'key' }), /notes were not confirmed/i);
});

test('related mutations are collection scoped, symmetric and never update parent', async () => {
  const relations = new Set(); const paths = [];
  const workshop = { request: async (path, body) => { paths.push([path, body]); if (path.endsWith('/add')) relations.add(['a', 'b'].sort().join(':')); if (path.endsWith('/remove')) relations.clear(); return { relatedItems: [...relations].map(() => ({ id: body.entity_id === 'a' ? 'b' : 'a' })) }; } };
  await changeRelatedItem(workshop, 'a', 'b', 'add', 'key-add', 'session');
  assert.equal(relations.size, 1);
  await changeRelatedItem(workshop, 'b', 'a', 'remove', 'key-remove', 'session');
  assert.equal(relations.size, 0);
  assert.deepEqual(paths.map(row => row[0]), ['item-metadata/related/add', 'item-metadata/related/remove']);
  assert.ok(paths.every(row => !('parentId' in row[1]) && !('locationId' in row[1])));
});

test('related search accepts authenticated native UUID results and excludes current item', async () => {
  const args = [];
  const api = { items: { getAll: async query => { args.push(query); return { data: { items: [{ id: 'a', name: 'Self' }, { id: 'b', name: 'Battery' }] } }; } } };
  assert.deepEqual(await searchRelatedItems(api, 'bat', 'a'), [{ id: 'b', name: 'Battery' }]);
  assert.equal(args[0].q, 'bat');
});

test('explicit suggestion selection copies shared values and clears serial', () => {
  const form = { name: 'typed', manufacturer: '', modelNumber: '', modelCode: '', tags: [], serialNumber: 'old', description: 'mine', location: { id: 'loc' }, packaging: '' };
  selectSuggestion(form, { name: 'Camera', manufacturer: 'Acme', modelNumber: 'X2', modelCode: 'CAM', tagIds: ['t1'], serialNumber: 'source', description: 'source description', parentId: 'other' });
  assert.deepEqual({ name: form.name, manufacturer: form.manufacturer, modelNumber: form.modelNumber, modelCode: form.modelCode, tags: form.tags, serialNumber: form.serialNumber }, { name: 'Camera', manufacturer: 'Acme', modelNumber: 'X2', modelCode: 'CAM', tags: ['t1'], serialNumber: '' });
  assert.equal(form.description, 'mine'); assert.equal(form.location.id, 'loc');
});

test('lookup ignores stale query and type responses', async () => {
  const pending = [];
  const lookup = createSuggestionLookup((type, query) => new Promise(resolve => pending.push({ type, query, resolve })));
  const first = lookup.search('type-a', 'cam');
  const second = lookup.search('type-b', 'lens');
  pending[0].resolve([{ name: 'stale' }]);
  pending[1].resolve([{ name: 'fresh' }]);
  assert.deepEqual(await first, []);
  assert.deepEqual(await second, [{ name: 'fresh' }]);
});

test('packaging options and custom rows validate normalized unique names', () => {
  assert.deepEqual(PACKAGING_OPTIONS, ['Original Packaging', 'No Packaging', 'HardCase', 'Softcase', 'Bag', 'Misc']);
  assert.deepEqual(validateCustomRows([{ name: ' Color ', value: 'red', note: 'photo' }]), [{ name: 'Color', value: 'red', note: 'photo' }]);
  assert.throws(() => validateCustomRows([{ name: 'Color', value: 'red' }, { name: ' color ', value: 'blue' }]), /duplicate/i);
});

test('native update preserves unrelated fields and verifies serial packaging and custom value', () => {
  const current = { id: 'i', name: 'Camera', parent: { id: 'loc' }, entityType: { id: 'type' }, tags: [{ id: 'tag' }], fields: [{ id: 'old', name: 'Condition', type: 'text', textValue: 'Ready' }], serialNumber: '', displayId: 'CAM-001' };
  const draft = { serialNumber: 'SN-1', packaging: 'No Packaging', rows: [{ name: 'Color', value: 'red', note: 'shade' }] };
  const update = buildNativeMetadataUpdate(current, draft);
  assert.equal(update.parentId, 'loc'); assert.equal(update.entityTypeId, 'type'); assert.deepEqual(update.tagIds, ['tag']);
  assert.equal(update.fields.find(f => f.name === 'Condition').textValue, 'Ready');
  assert.equal(update.fields.find(f => f.name === 'Device Packaging').textValue, 'No Packaging');
  assert.equal(update.fields.find(f => f.name === 'Color').textValue, 'red');
  assert.equal(update.displayId, undefined);
  assert.equal(nativeMetadataMatches({ ...current, fields: update.fields, serialNumber: 'SN-1' }, draft), true);
  assert.equal(nativeMetadataMatches(current, draft), false);
});

test('native metadata rejects duplicate or non-text names without changing source', () => {
  const base = { id: 'i', entityType: { id: 'type' }, parent: { id: 'loc' }, tags: [], serialNumber: '', fields: [{ id: 'f', name: 'Color', type: 'number', numberValue: 1 }] };
  const before = JSON.stringify(base);
  assert.throws(() => buildNativeMetadataUpdate(base, { serialNumber: '', packaging: '', rows: [{ name: ' color ', value: 'red' }] }), /not a text field/i);
  assert.equal(JSON.stringify(base), before);
  assert.throws(() => buildNativeMetadataUpdate({ ...base, fields: [{ name: 'Color', type: 'text' }, { name: ' color ', type: 'text' }] }, { serialNumber: '', packaging: '', rows: [] }), /duplicate native field/i);
});

test('readback requires a native text field even for an empty custom value with Note', () => {
  const draft = { serialNumber: '', packaging: '', rows: [{ name: 'Color', value: '', note: 'not recorded' }] };
  const item = { serialNumber: '', fields: [] };
  assert.equal(nativeMetadataMatches(item, draft), false);
  assert.equal(nativeMetadataMatches({ ...item, fields: [{ name: 'Color', type: 'number', textValue: '' }] }, draft), false);
  assert.equal(nativeMetadataMatches({ ...item, fields: [{ name: 'Color', type: 'text', textValue: '' }] }, draft), true);
});

test('custom field names exceeding Notes API 120 characters fail before native create', () => {
  assert.throws(() => validateCustomRows([{ name: 'x'.repeat(121), value: 'value', note: '' }]), /120/);
  assert.doesNotThrow(() => validateCustomRows([{ name: 'x'.repeat(120), value: 'value', note: '' }]));
  assert.doesNotThrow(() => validateCustomRows([{ name: 'ß'.repeat(120), value: 'value', note: 'label' }]));
  assert.throws(() => validateCustomRows([{ name: 'ß'.repeat(121), value: 'value', note: '' }]), /120/);
});

test('lost Notes response replays same key and confirms canonical Straße key', async () => {
  const calls = [];
  let saved = null;
  let loseResponse = true;
  const workshop = { request: async (path, body) => {
    calls.push({ path, body });
    if (path === 'item-metadata/field-notes') {
      saved = { strasse: 'German label' };
      if (loseResponse) { loseResponse = false; throw new Error('response lost'); }
      return { fieldNotes: saved };
    }
    if (path === 'item-metadata?entity_id=item-1') return { fieldNotes: saved };
    throw new Error(`Unexpected path: ${path}`);
  } };
  const intent = { entity_id: 'item-1', identity: 'session' };
  const step = { request_key: 'same-key', fields: [{ name: 'Straße', note: 'German label' }] };
  await assert.rejects(() => persistFieldNotes(workshop, intent, step), /response lost/);
  await assert.doesNotReject(() => persistFieldNotes(workshop, intent, step));
  assert.deepEqual(calls.filter(call => call.path === 'item-metadata/field-notes').map(call => call.body.request_key), ['same-key', 'same-key']);
  assert.equal(sameFieldNotes({ strasse: 'German label' }, { strasse: 'German label' }), true);
});

test('expanding name Notes persist and reconcile use canonical API keys', async () => {
  const canonical = 'ss'.repeat(120);
  let stored = {};
  const workshop = { request: async (path, body) => {
    if (path === 'item-metadata/field-notes') {
      assert.equal(body.fields[0].name, 'ß'.repeat(120));
      stored = { [canonical]: body.fields[0].note };
      return { fieldNotes: stored };
    }
    if (path.startsWith('item-metadata?')) return { fieldNotes: stored };
    throw new Error(`Unexpected path ${path}`);
  } };
  const intent = { entity_id: 'item-1', identity: 'session' };
  const step = { request_key: 'same-key', fields: [{ name: 'ß'.repeat(120), note: 'label' }] };
  assert.deepEqual(await persistFieldNotes(workshop, intent, step), { [canonical]: 'label' });
  assert.deepEqual(await persistFieldNotes(workshop, intent, step), { [canonical]: 'label' });
});

test('mounted generated create form supports keyboard selection, field rows, and OCR launcher', async () => {
  const { mkdtemp, rm, readFile, writeFile, access } = await import('node:fs/promises');
  const { spawnSync } = await import('node:child_process');
  const os = await import('node:os');
  const path = await import('node:path');
  const { pathToFileURL, fileURLToPath } = await import('node:url');
  const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
  const candidates = [repo, path.resolve(repo, '../..')];
  let cache;
  for (const candidate of candidates) {
    try { await access(path.join(candidate, 'work/homebox-ui-dev/node_modules/vite/dist/node/index.js')); cache = candidate; break; } catch {}
  }
  if (!cache) throw new Error('The existing Homebox UI browser fixture toolchain is unavailable.');
  const fixtureRoot = await mkdtemp(path.join(os.tmpdir(), 'item-create-sfc-'));
  const python = `import importlib.util,pathlib,sys\nrepo=pathlib.Path(sys.argv[1]); out=pathlib.Path(sys.argv[2]); source=pathlib.Path(sys.argv[3])\ns=importlib.util.spec_from_file_location('builder',repo/'deploy/build-homebox-ui.py'); b=importlib.util.module_from_spec(s); s.loader.exec_module(b)\nimport homebox_patchset\nhomebox_patchset.materialize=lambda _root: source\nb.BUILD=out; b.prepare()\n`;
  const prepared = spawnSync('python', ['-c', python, repo, fixtureRoot, path.join(cache, 'work/homebox-source-patched')], { encoding: 'utf8' });
  if (prepared.status !== 0) throw new Error(`Generated builder fixture failed: ${prepared.stdout}${prepared.stderr}`);
  const stripImports = source => source.replace(/(^\s*import\b[\s\S]*?;\s*\n)/gm, '');
  const modal = path.join(fixtureRoot, 'components/Entity/CreateModal.vue');
  const ocr = path.join(fixtureRoot, 'components/Workshop/OcrPopover.vue');
  const layout = await readFile(path.join(fixtureRoot, 'layouts/default.vue'), 'utf8');
  assert.match(layout, /setTimeout\(resolve, 0\)/, 'generated layout waits for modal teleport before routing OCR launcher');
  assert.match(layout, /#orc-launcher-create/, 'generated layout routes OCR to create modal');
  await writeFile(modal, stripImports(await readFile(modal, 'utf8')));
  await writeFile(ocr, stripImports(await readFile(ocr, 'utf8')));
  await writeFile(path.join(fixtureRoot, 'tsconfig.json'), '{"compilerOptions":{"target":"ESNext"}}');
  await writeFile(path.join(fixtureRoot, 'index.html'), '<!doctype html><div id="app"></div><script type="module" src="/main.js"></script>');
  await writeFile(path.join(fixtureRoot, 'main.js'), `
import { createApp, defineComponent, h, ref, reactive, computed, watch, onMounted, onBeforeUnmount, onUnmounted, nextTick } from 'vue';
import CreateModal from './components/Entity/CreateModal.vue';
import OcrPopover from './components/Workshop/OcrPopover.vue';
import { PACKAGING_OPTIONS, createSuggestionLookup, selectSuggestion, validateCustomRows, buildNativeMetadataUpdate, nativeMetadataMatches, persistFieldNotes } from './lib/item-create-fields.js';
import { assignCreatedEquipment, createEquipmentCreationFlow, equipmentTemplateStorageKey } from './lib/equipment-catalog.js';
import { createRelatedItemFlow, relatedItemStorageKey } from './lib/item-metadata.js';
Object.assign(window, { PACKAGING_OPTIONS, createSuggestionLookup, selectSuggestion, validateCustomRows, buildNativeMetadataUpdate, nativeMetadataMatches, persistFieldNotes, assignCreatedEquipment, createEquipmentCreationFlow, equipmentTemplateStorageKey, createRelatedItemFlow, relatedItemStorageKey, ref, reactive, computed, watch, onMounted, onBeforeUnmount, onUnmounted, nextTick });
window.DialogID={CreateEntity:'create',Scanner:'scanner'};
window.__activeDialog=ref(null);
window.useDialog=()=>({activeDialog:window.__activeDialog,openDialog:id=>window.__activeDialog.value=id,closeDialog:()=>window.__activeDialog.value=null,registerOpenDialogCallback:(_id,fn)=>{window.__openCreate=fn;return ()=>{};}});
window.useDialogHotkey=()=>{};
window.useI18n=()=>({t:key=>key});
window.useEntityTypeStore=()=>({allTypes:[{id:'type-1',name:'Camera',isLocation:false}]});
window.useLocationStore=()=>({allLocations:[]});
window.useTagStore=()=>({tags:[]});
window.useRoute=()=>({fullPath:'/items',params:{}});
window.useItemSearch=()=>({query:ref(''),results:ref([]),isLoading:ref(false),triggerSearch:()=>{}});
window.useMagicKeys=()=>({shift:ref(false)});
window.useCollections=()=>({selectedId:ref('collection')});
window.useAuthContext=()=>({user:{id:'member',defaultGroupId:'collection'}});
window.useUserApi=()=>({items:{get:async()=>({data:null}),create:async()=>({data:{id:'new-item'}}),attachments:{add:async()=>({})}}});
window.__suggestions=[{id:'a',name:'Camera A',manufacturer:'Maker A',modelNumber:'A1',modelCode:'CAM',tagIds:['tag-a']},{id:'b',name:'Camera B',manufacturer:'Maker B',modelNumber:'B2',modelCode:'CAM',tagIds:['tag-b']}];
window.__paths=[];
window.useWorkshop=()=>({refresh:async()=>({group:{id:'collection'},user:{id:'member'},identity:'session'}),request:async path=>{window.__paths.push(path);return path.startsWith('equipment/suggestions?')?window.__suggestions:[];}});
window.toast={success(){},error(){},info(){},warning(){}};
window.navigateTo=()=>{};
window.AttachmentTypes={Photo:'photo'};
window.clampOcrPopoverPosition=position=>position;
window.nextOcrPopoverState=(state,action)=>action==='toggle-enabled'?{enabled:!state.enabled,open:false}:action==='open'?{enabled:true,open:true}:{enabled:state.enabled,open:false};
window.applyInitialBarcodeParamAfterContext=()=>{};
const TextField=defineComponent({inheritAttrs:false,props:['modelValue','label','type'],emits:['update:modelValue'],setup(props,{emit,attrs}){return()=>h('label',[props.label,h('input',{...attrs,type:props.type||'text',value:props.modelValue,onInput:event=>emit('update:modelValue',event.target.value)})]);}});
const TextArea=defineComponent({props:['modelValue','label'],emits:['update:modelValue'],setup(props,{emit}){return()=>h('label',[props.label,h('textarea',{value:props.modelValue,onInput:event=>emit('update:modelValue',event.target.value)})]);}});
const Button=defineComponent({props:['type','disabled'],setup(props,{attrs,slots}){return()=>h('button',{...attrs,type:props.type||'button',disabled:props.disabled},slots.default?.());}});
const BaseModal=defineComponent({setup(_, {slots}){return()=>window.__activeDialog.value==='create'?h('div',{role:'dialog'},[slots.title?.(),slots['header-actions']?.(),slots.default?.()]):null;}});
const Empty=defineComponent({setup(_, {slots}){return()=>h('div',slots.default?.());}});
const app=createApp({components:{CreateModal,OcrPopover},setup(){const target=ref('#orc-launcher-toolbar');watch(window.__activeDialog,async()=>{await new Promise(resolve=>setTimeout(resolve,0));target.value=window.__activeDialog.value==='create'?'#orc-launcher-create':'#orc-launcher-toolbar';},{immediate:true,flush:'post'});return{target};},template:'<div id="orc-launcher-toolbar"></div><CreateModal/><OcrPopover :launcher-target="target" />'});
app.config.globalProperties.DialogID=window.DialogID; app.config.globalProperties.$t=key=>key; app.config.globalProperties.PACKAGING_OPTIONS=PACKAGING_OPTIONS;
for(const name of ['FormTextField'])app.component(name,TextField);
app.component('FormTextArea',TextArea).component('BaseModal',BaseModal).component('Button',Button);
for(const name of ['ButtonGroup','TooltipProvider','Tooltip','TooltipTrigger','TooltipContent','EntitySelector','LocationSelector','TagSelector','PhotoUploader','PhotoUploaderPreview'])app.component(name,Empty);
for(const name of ['ScanText','Camera','Copy','Minus','X','MdiBarcodeScan','MdiBarcode','MdiLoading','MdiPackageVariant','MdiPackageVariantClosed'])app.component(name,Empty);
app.mount('#app');
window.__activeDialog.value='create';
await nextTick();
await window.__openCreate({baseType:'item'});
`);
  const vite = await import(pathToFileURL(path.join(cache, 'work/homebox-ui-dev/node_modules/vite/dist/node/index.js')).href);
  const plugin = await import(pathToFileURL(path.join(cache, 'work/homebox-ui-dev/node_modules/.pnpm/@vitejs+plugin-vue@6.0.7_vite@7.3.5_@types+node@25.9.3_jiti@1.21.7_terser@5.48.0_yaml@2_67e8ab11f94c3b8609189be60bcd60d1/node_modules/@vitejs/plugin-vue/dist/index.mjs')).href);
  const { chromium } = await import(pathToFileURL(path.join(cache, 'work/homebox-ui-dev/node_modules/.pnpm/@playwright+test@1.60.0/node_modules/@playwright/test/index.mjs')).href);
  const server = await vite.createServer({ configFile:false, root:fixtureRoot, plugins:[plugin.default()], optimizeDeps:{noDiscovery:true,include:[]}, resolve:{alias:[{find:/^vue$/,replacement:path.join(cache,'work/homebox-ui-dev/node_modules/vue/dist/vue.esm-browser.js')}]}, server:{host:'127.0.0.1',port:44000+Math.floor(Math.random()*15000),strictPort:true} });
  const browser = await chromium.launch({headless:true,executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
  try {
    await server.listen();
    const page = await browser.newPage();
    page.setDefaultTimeout(5000);
    page.on('pageerror', error => console.error('Browser error:', error.stack));
    page.on('console',message=>{if(message.type()==='warning'||message.type()==='error')console.error('Browser console:',message.text());});
    await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/index.html`);
    await page.getByRole('dialog').waitFor();
    const name = page.locator('form input').first();
    await name.fill('Cam');
    await page.getByRole('option', {name:/Camera B/}).waitFor();
    assert.equal(await page.getByLabel('Manufacturer serial number').inputValue(), '', 'typing alone does not copy model data');
    await name.press('ArrowDown');
    await page.waitForFunction(() => document.querySelector('[role="listbox"] [aria-selected="true"]')?.textContent.includes('Camera B'));
    await name.press('Enter');
    await page.getByRole('option', {name:/Camera B/}).waitFor({state:'detached'});
    assert.equal(await name.inputValue(),'Camera B');
    assert.equal(await page.getByLabel('Manufacturer serial number').inputValue(),'');
    await page.getByRole('button',{name:'Add field'}).click();
    await page.getByLabel('Custom field name').fill('Color');
    await page.getByLabel('Custom field value').fill('red');
    await page.getByLabel('Custom field note').fill('shade');
    assert.equal(await page.getByLabel('Custom field note').inputValue(),'shade');
    await page.getByRole('button',{name:'Remove'}).click();
    assert.equal(await page.getByLabel('Custom field name').count(),0);
    await page.getByRole('button',{name:'Stage related item'}).click();
    await page.getByLabel('Related item name').fill('Battery');
    assert.equal(await page.getByLabel('Related item name').inputValue(), 'Battery');
    assert.equal(await page.getByLabel('Related item location').count(), 1, 'related location can be edited independently');
    await page.locator('#orc-launcher-create').getByRole('button',{name:'Enable text capture'}).click();
    await page.getByRole('button',{name:'Open text capture'}).waitFor();
    await page.getByRole('button',{name:'Open text capture'}).click();
    await page.getByRole('region',{name:'Text capture'}).waitFor();
    await page.getByRole('button',{name:/Scan photo/}).waitFor();
    await page.getByLabel('Editable recognized text').fill('OCR label text');
    assert.equal(await name.inputValue(),'Camera B', 'OCR editing does not write into create form');
    assert.equal(await page.getByRole('button',{name:'Copy text'}).isEnabled(),true);
    await page.evaluate(()=>Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{window.__copiedText=text;}}}));
    await page.getByRole('button',{name:'Copy text'}).click();
    assert.equal(await page.evaluate(()=>window.__copiedText),'OCR label text');
  } finally { await browser.close(); await server.close(); await rm(fixtureRoot,{recursive:true,force:true}); }
});

test('mounted generated detail panel edits fields, links both sides, and hides inaccessible targets', async () => {
  const { mkdtemp, rm, readFile, writeFile, access } = await import('node:fs/promises');
  const { spawnSync } = await import('node:child_process');
  const os = await import('node:os');
  const path = await import('node:path');
  const { pathToFileURL, fileURLToPath } = await import('node:url');
  const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
  const cache = path.resolve(repo, '../..');
  await access(path.join(cache, 'work/homebox-ui-dev/node_modules/vite/dist/node/index.js'));
  const root = await mkdtemp(path.join(os.tmpdir(), 'item-detail-sfc-'));
  const python = `import importlib.util,pathlib,sys\nrepo=pathlib.Path(sys.argv[1]); out=pathlib.Path(sys.argv[2]); source=pathlib.Path(sys.argv[3])\ns=importlib.util.spec_from_file_location('builder',repo/'deploy/build-homebox-ui.py'); b=importlib.util.module_from_spec(s); s.loader.exec_module(b)\nimport homebox_patchset\nhomebox_patchset.materialize=lambda _root: source\nb.BUILD=out; b.prepare()\n`;
  const prepared = spawnSync('python', ['-c', python, repo, root, path.join(cache, 'work/homebox-source-patched')], { encoding: 'utf8' });
  if (prepared.status !== 0) throw new Error(`Generated detail fixture failed: ${prepared.stdout}${prepared.stderr}`);
  const detailPage = await readFile(path.join(root, 'pages/item/[id]/index.vue'), 'utf8');
  assert.match(detailPage, /ItemMetadataPanel v-if="!hasNested && item" :item="item" @changed="refresh"/);
  const panel = path.join(root, 'components/Workshop/ItemMetadataPanel.vue');
  await writeFile(panel, (await readFile(panel, 'utf8')).replace(/(^\s*import\b[\s\S]*?;\s*\n)/gm, ''));
  await writeFile(path.join(root, 'tsconfig.json'), '{"compilerOptions":{"target":"ESNext"}}');
  await writeFile(path.join(root, 'index.html'), '<!doctype html><div id="app"></div><script type="module" src="/main.js"></script>');
  await writeFile(path.join(root, 'main.js'), `
import { createApp, defineComponent, h, ref, watch, onMounted, computed, nextTick } from 'vue';
import Panel from './components/Workshop/ItemMetadataPanel.vue';
import { PACKAGING_OPTIONS, buildNativeMetadataUpdate, nativeMetadataMatches, persistFieldNotes, validateCustomRows } from './lib/item-create-fields.js';
import { changeRelatedItem, detailMetadataDraft, saveDetailMetadata, searchRelatedItems } from './lib/item-metadata.js';
Object.assign(window,{ref,watch,onMounted,computed,PACKAGING_OPTIONS,buildNativeMetadataUpdate,nativeMetadataMatches,persistFieldNotes,validateCustomRows,changeRelatedItem,detailMetadataDraft,saveDetailMetadata,searchRelatedItems});
window.__items={a:{id:'a',name:'Camera',parent:{id:'loc'},entityType:{id:'type'},tags:[],serialNumber:'SN',fields:[{id:'p',name:'Device Packaging',type:'text',textValue:'Bag'},{id:'f',name:'Color',type:'text',textValue:'red'},{id:'u',name:'Weight',type:'number',numberValue:4}]},b:{id:'b',name:'Battery',parent:{id:'loc2'},entityType:{id:'type'},tags:[],serialNumber:'',fields:[]},c:{id:'c',name:'Lens',parent:{id:'loc3'},entityType:{id:'type'},tags:[],serialNumber:'',fields:[]}};
window.__links=new Set();window.__notes={a:{color:'shade'},b:{}};window.__calls=[];window.__failNotes=false;
window.__id=ref('a');window.__item=ref(window.__items.a);window.__switch=id=>{window.__id.value=id;window.__item.value=window.__items[id];};
window.useUserApi=()=>({items:{get:async id=>({data:structuredClone(window.__items[id])}),update:async(id,payload)=>{window.__calls.push(['native',id,payload]);window.__items[id]={...window.__items[id],...payload};return{data:window.__items[id]};},getAll:async({q})=>({data:{items:Object.values(window.__items).filter(item=>item.name.toLowerCase().includes(q.toLowerCase()))}})}});
window.useWorkshop=()=>({refresh:async()=>({group:{id:'group'},user:{id:'user'},identity:'session'}),request:async(path,body)=>{window.__calls.push(['metadata',path,body]);if(path.startsWith('item-metadata?')){const id=new URLSearchParams(path.split('?')[1]).get('entity_id');return{fieldNotes:window.__notes[id],relatedItems:[...window.__links].filter(pair=>pair.includes(id)).map(pair=>{const other=pair.find(value=>value!==id);return other==='stale'?{unavailable:true}:{id:other,name:window.__items[other].name,unavailable:false};})};}if(path==='item-metadata/field-notes'){if(window.__failNotes){window.__failNotes=false;throw Error('Notes unavailable');}window.__notes[body.entity_id]=Object.fromEntries(body.fields.map(field=>[field.name.toLowerCase(),field.note]));return{fieldNotes:window.__notes[body.entity_id]};}if(path.endsWith('/add'))window.__links.add([body.entity_id,body.related_entity_id].sort());if(path.endsWith('/remove')){for(const pair of window.__links)if(pair.includes(body.entity_id)&&pair.includes(body.related_entity_id))window.__links.delete(pair);}return{relatedItems:[...window.__links].filter(pair=>pair.includes(body.entity_id)).map(pair=>({id:pair.find(value=>value!==body.entity_id)}))};}});
window.useCollections=()=>({selectedId:ref('group')});window.useAuthContext=()=>({user:{id:'user'}});
const Link=defineComponent({props:['to'],setup(props,{slots}){return()=>h('a',{href:props.to},slots.default?.());}});
const app=createApp({components:{Panel},setup(){return{item:window.__item};},template:'<Panel :item="item" />'});app.config.globalProperties.PACKAGING_OPTIONS=PACKAGING_OPTIONS;app.component('NuxtLink',Link).mount('#app');await nextTick();
`);
  const vite = await import(pathToFileURL(path.join(cache, 'work/homebox-ui-dev/node_modules/vite/dist/node/index.js')).href);
  const plugin = await import(pathToFileURL(path.join(cache, 'work/homebox-ui-dev/node_modules/.pnpm/@vitejs+plugin-vue@6.0.7_vite@7.3.5_@types+node@25.9.3_jiti@1.21.7_terser@5.48.0_yaml@2_67e8ab11f94c3b8609189be60bcd60d1/node_modules/@vitejs/plugin-vue/dist/index.mjs')).href);
  const { chromium } = await import(pathToFileURL(path.join(cache, 'work/homebox-ui-dev/node_modules/.pnpm/@playwright+test@1.60.0/node_modules/@playwright/test/index.mjs')).href);
  const server = await vite.createServer({configFile:false,root,plugins:[plugin.default()],optimizeDeps:{noDiscovery:true,include:[]},resolve:{alias:[{find:/^vue$/,replacement:path.join(cache,'work/homebox-ui-dev/node_modules/vue/dist/vue.esm-browser.js')}]},server:{host:'127.0.0.1',port:44000+Math.floor(Math.random()*15000),strictPort:true}});
  const browser = await chromium.launch({headless:true,executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
  try {
    await server.listen();
    const page = await browser.newPage();page.setDefaultTimeout(5000);
    page.on('pageerror',error=>console.error('Detail browser error:',error.stack));
    await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/index.html`);
    await page.getByLabel('Device Packaging').selectOption('HardCase');
    assert.equal(await page.getByLabel('Custom field note').inputValue(),'shade');
    await page.getByLabel('Custom field value').fill('blue');
    await page.getByLabel('Custom field note').fill('deep');
    await page.evaluate(()=>window.__failNotes=true);
    await page.getByRole('button',{name:'Save fields'}).click();
    await page.getByRole('alert',{name:''}).filter({hasText:'Notes unavailable'}).waitFor();
    await page.getByRole('button',{name:'Retry metadata save'}).click();
    await page.getByRole('status').filter({hasText:'Packaging and custom fields saved.'}).waitFor();
    assert.equal(await page.evaluate(()=>window.__calls.filter(call=>call[0]==='native').length),1);
    assert.deepEqual(await page.evaluate(()=>window.__items.a.fields.map(field=>field.id)),['p','f','u']);
    await page.getByLabel('Find an existing item').fill('Bat');
    await page.getByLabel('Search results').selectOption('b');
    await page.getByRole('button',{name:'Link existing item'}).click();
    await page.getByRole('link',{name:'Battery'}).waitFor();
    await page.evaluate(()=>window.__switch('b'));
    await page.getByRole('link',{name:'Camera'}).waitFor();
    await page.getByRole('button',{name:'Remove link'}).click();
    await page.getByText('No related items.').waitFor();
    await page.evaluate(()=>{window.__links.add(['b','stale']);window.__links.add(['b','c']);window.__switch('a');});
    await page.getByText('No related items.').waitFor();
    await page.evaluate(()=>window.__switch('b'));
    await page.getByText('Unavailable item').waitFor();
    await page.getByRole('link',{name:'Lens'}).waitFor();
    assert.equal(await page.getByRole('link',{name:'stale'}).count(),0);
    assert.equal(await page.getByRole('button',{name:'Remove link'}).count(),1);
  } finally {await browser.close();await server.close();await rm(root,{recursive:true,force:true});}
});
