import assert from 'node:assert/strict';

const states = new Map();
globalThis.useState = (key, init) => {
  if (!states.has(key)) states.set(key, { value: init() });
  return states.get(key);
};
globalThis.useCollections = () => ({ selectedId: { value: 'group-1' } });
globalThis.useAuthContext = () => ({ user: { id: 'user-1', defaultGroupId: 'group-1' }, invalidateSession() {} });
globalThis.computed = fn => ({ get value() { return fn(); } });

const calls = [];
const storage = new Map();
globalThis.localStorage = {
  getItem: key => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, String(value)),
  removeItem: key => storage.delete(key),
};
globalThis.fetch = async (url, options) => {
  calls.push({ url, options });
  return { ok: true, status: 200, json: async () => ({}) };
};

const { useWorkshop } = await import('../homebox-ui/overlay/composables/use-workshop.ts');
const workshop = useWorkshop();
workshop.context.value = {
  identity: 'identity-7',
  user: { id: 'user-1', name: 'Test' },
  group: { id: 'group-1', name: 'Storage' },
  manager: true,
};

for (const path of [
  'workshop/checks/get?id=check-1',
  'workshop/checks/list?location_id=location-1',
]) {
  await workshop.request(path);
}

assert.equal(calls.length, 2);
for (const { url, options } of calls) {
  assert.match(url, /^\/workshop-api\/workshop\/checks\/(get|list)\?/);
  assert.equal(options.method, 'GET');
  assert.equal(options.headers['X-Workshop-Group'], 'group-1');
  assert.equal(options.headers['X-Workshop-Identity'], 'identity-7');
}

let failTemplateSave = true;
globalThis.fetch = async (url, options) => {
  calls.push({ url, options });
  if (url === '/workshop-api/context') return { ok: true, status: 200, json: async () => ({ ...workshop.context.value }) };
  if (url === '/workshop-api/labels/templates/save' && failTemplateSave) {
    failTemplateSave = false;
    throw new Error('save reply lost');
  }
  if (url === '/workshop-api/labels/templates/result') return { ok: true, status: 200, json: async () => ({ id: 'template-1', revision: 1 }) };
  return { ok: true, status: 200, json: async () => ({ id: 'template-1', revision: 2 }) };
};
const pendingKey = 'workshop-pending:group-1:user-1';
await assert.rejects(workshop.write('labels/templates/save', { request_key: 'template-save-1' }, 'Save label template', 'labels'), /save reply lost/);
assert.equal(JSON.parse(localStorage.getItem(pendingKey))[0].key, 'template-save-1', 'uncertain save keeps its request key');
const savedResult = await workshop.request('labels/templates/result', { request_key: 'template-save-1' }, 'identity-7');
assert.equal(savedResult.id, 'template-1');
assert.equal(workshop.confirmTemplateSave('template-save-1'), true, 'confirmed result reconciles the matching pending save');
assert.deepEqual(JSON.parse(localStorage.getItem(pendingKey)), []);
await workshop.write('labels/templates/save', { request_key: 'template-save-2' }, 'Save label template', 'labels');
assert.deepEqual(JSON.parse(localStorage.getItem(pendingKey)), [], 'the next template save is no longer blocked');
