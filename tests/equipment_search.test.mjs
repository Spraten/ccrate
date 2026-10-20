import assert from 'node:assert/strict';
import test from 'node:test';
import { fetchAssignedDisplayIds, projectAssignedDisplayIds, resolveAssignedIdAfterNativeMiss } from '../homebox-ui/overlay/lib/equipment-search.js';
import { matchInventoryCustomFields } from '../homebox-ui/overlay/lib/child-item-groups.js';

test('custom field search matches names and values only among projected native items', () => {
  const loaded = [
    { id: 'loaded-1', fields: [{ name: 'Tracking code', value: 'ZX-42' }] },
    { id: 'loaded-2', fields: [{ name: 'Barcode', value: '12345' }] },
  ];
  const collectionRows = [...loaded, { id: 'hidden', fields: [{ name: 'Barcode', value: 'ZX-42' }] }];
  assert.deepEqual(matchInventoryCustomFields(loaded, 'ZX-42').map(item => item.id), ['loaded-1']);
  assert.deepEqual(matchInventoryCustomFields(loaded, 'barcode').map(item => item.id), ['loaded-2']);
  assert.deepEqual(matchInventoryCustomFields(loaded, 'ZX-42', collectionRows).map(item => item.id), ['loaded-1']);
});

test('assigned ID projection overrides only assigned rows and preserves legacy native IDs', () => {
  const assigned = { id: 'native-1', displayId: 'HB-104' };
  const legacy = { id: 'native-2', displayId: 'HB-105' };
  const result = projectAssignedDisplayIds([assigned, legacy], {
    'native-1': { display_id: 'DRONE-2S-6' },
  });
  assert.notEqual(result[0], assigned);
  assert.equal(result[0].displayId, 'DRONE-2S-6');
  assert.equal(result[1], legacy);
  assert.equal(result[1].displayId, 'HB-105');
});

test('exact generated ID miss resolves to the native UUID while native search results retain precedence', async () => {
  const calls = [];
  const resolve = async value => { calls.push(value); return value === 'DRONE-2S-6' ? { entity_id: 'native-1' } : null; };
  assert.equal(await resolveAssignedIdAfterNativeMiss('DRONE-2S-6', [], resolve), 'native-1');
  assert.equal(await resolveAssignedIdAfterNativeMiss('ordinary name', [], resolve), null);
  assert.equal(await resolveAssignedIdAfterNativeMiss('DRONE-2S-6', [{ id: 'native-native-search' }], resolve), null);
  assert.deepEqual(calls, ['DRONE-2S-6']);
});

test('unresolved assigned IDs do not produce a route or cross collection result', async () => {
  let calls = 0;
  const resolve = async () => { calls++; return null; };
  assert.equal(await resolveAssignedIdAfterNativeMiss('DRONE-2S-999', [], resolve), null);
  assert.equal(calls, 1);
});

test('a delayed exact-ID resolution is ignored after the search revision changes', async () => {
  let current = true;
  let finish;
  const pending = resolveAssignedIdAfterNativeMiss('DRONE-2S-6', [], () => new Promise(resolve => { finish = resolve; }), () => current);
  current = false;
  finish({ entity_id: 'native-1' });
  assert.equal(await pending, null);
});

test('assignment lookup splits result pages into authorized batches of at most 100', async () => {
  const batches = [];
  const result = await fetchAssignedDisplayIds(Array.from({ length: 203 }, (_, index) => `native-${index}`), async ids => {
    batches.push(ids.length);
    return Object.fromEntries(ids.map(id => [id, { display_id: `ID-${id}` }]));
  });
  assert.deepEqual(batches, [100, 100, 3]);
  assert.equal(Object.keys(result).length, 203);
});
