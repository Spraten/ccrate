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
let failTemplateSaveConflict = false;
globalThis.fetch = async (url, options) => {
  calls.push({ url, options });
  if (url === '/workshop-api/context') return { ok: true, status: 200, json: async () => ({ ...workshop.context.value }) };
  if (url === '/workshop-api/labels/templates/save' && failTemplateSave) {
    failTemplateSave = false;
    throw new Error('save reply lost');
  }
  if (url === '/workshop-api/labels/templates/save' && failTemplateSaveConflict) return { ok: false, status: 409, json: async () => ({ error: 'revision conflict' }) };
  if (url === '/workshop-api/labels/templates/result') return { ok: true, status: 200, json: async () => ({ id: 'template-1', revision: 1 }) };
  return { ok: true, status: 200, json: async () => ({ id: 'template-1', revision: 2 }) };
};
const pendingKey = 'workshop-pending:group-1:user-1';
const savePayload = { request_key: 'template-save-1', id: null, revision: 0, profile: 'supvan', name: 'Bench label', document: { name: 'Bench label' } };
await assert.rejects(workshop.write('labels/templates/save', savePayload, 'Save label template', 'labels'), /save reply lost/);
assert.equal(JSON.parse(localStorage.getItem(pendingKey))[0].key, 'template-save-1', 'uncertain save keeps its request key');
const persistedSave = workshop.pendingTemplateSave();
assert.deepEqual(persistedSave.intent, savePayload, 'uncertain save persists the exact request payload');
assert.equal(persistedSave.identity, 'identity-7');
assert.equal(persistedSave.group_id, 'group-1');
assert.equal(persistedSave.user_id, 'user-1');
assert.equal(useWorkshop().pendingTemplateSave().key, 'template-save-1', 'a remounted workshop composable restores the scoped pending action');
workshop.context.value = { ...workshop.context.value, identity: 'identity-changed' };
assert.equal(workshop.pendingTemplateSave(), null, 'a pending save is not exposed to a different identity');
workshop.context.value = { ...workshop.context.value, identity: 'identity-7' };
const savedResult = await workshop.request('labels/templates/result', { request_key: 'template-save-1' }, 'identity-7');
assert.equal(savedResult.id, 'template-1');
assert.equal(workshop.confirmTemplateSave('template-save-1'), true, 'confirmed result reconciles the matching pending save');
assert.deepEqual(JSON.parse(localStorage.getItem(pendingKey)), []);
failTemplateSaveConflict = true;
await assert.rejects(workshop.write('labels/templates/save', { request_key: 'template-save-2' }, 'Save label template', 'labels'), /revision conflict/);
assert.equal(workshop.pendingTemplateSave(), null, 'an authoritative 409 clears only the matching scoped save intent');
assert.equal(calls.filter(call => call.url === '/workshop-api/operation/status').length, 0, 'label saves are never resolved through unrelated operation status');
await assert.rejects(workshop.write('labels/templates/save', { request_key: 'template-save-3' }, 'Save label template', 'labels'), /revision conflict/);
assert.equal(calls.filter(call => call.url === '/workshop-api/labels/templates/save').length, 3, 'a later user-initiated save is allowed after the authoritative rejection clears the matching intent');
assert.equal(workshop.pendingTemplateSave(), null);

localStorage.setItem(pendingKey, JSON.stringify([{ key: 'legacy-save-key', path: 'labels/templates/save', label: 'Save label template', subject: 'labels', at: '2026-10-14T00:00:00Z' }]));
assert.equal(workshop.pendingTemplateSave().key, 'legacy-save-key', 'legacy key-only rows in the current group/user storage scope remain visible for recovery');
assert.equal(workshop.pendingTemplateSave().intent, undefined);
assert.equal(workshop.confirmTemplateSave('legacy-save-key'), true, 'a found status result can clear a matching legacy row');
