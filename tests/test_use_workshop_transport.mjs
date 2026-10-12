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
