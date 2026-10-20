import test from 'node:test';
import assert from 'node:assert/strict';
import { PACKAGING_OPTIONS, createSuggestionLookup, selectSuggestion, validateCustomRows, buildNativeMetadataUpdate, nativeMetadataMatches, sameFieldNotes, persistFieldNotes } from '../homebox-ui/overlay/lib/item-create-fields.js';

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
