import test from 'node:test';
import assert from 'node:assert/strict';
import { PACKAGING_OPTIONS, createSuggestionLookup, selectSuggestion, validateCustomRows, buildNativeMetadataUpdate, nativeMetadataMatches } from '../homebox-ui/overlay/lib/item-create-fields.js';

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
