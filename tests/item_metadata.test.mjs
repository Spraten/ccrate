import test from 'node:test';
import assert from 'node:assert/strict';
import { createRelatedItemFlow, relatedItemStorageKey } from '../homebox-ui/overlay/lib/item-metadata.js';
import { createEquipmentCreationFlow } from '../homebox-ui/overlay/lib/equipment-catalog.js';

const context = { group: { id: 'collection-a' }, user: { id: 'member-a' }, identity: 'session-a' };
function fixture() {
  let stored = null;
  const calls = [];
  let createResult = { data: { id: 'related-a' } };
  let createResults = null;
  let linkResult = null;
  let readResult = { relatedItems: [] };
  let currentContext = context;
  let sequence = 0;
  const flow = createRelatedItemFlow({
    read: () => structuredClone(stored),
    write: value => { stored = structuredClone(value); },
    context: async () => currentContext,
    expectedContext: context,
    createNative: async item => { calls.push(['create', item]); return createResults?.length ? createResults.shift() : createResult; },
    link: async (main, related, key) => { calls.push(['link', main, related, key]); return linkResult || { relatedItems: [related] }; },
    readLinks: async main => { calls.push(['read', main]); return readResult; },
    keyFactory: () => `key-${++sequence}`,
  });
  return { flow, calls, get stored() { return stored; }, set createResult(value) { createResult = value; }, set createResults(value) { createResults = value; }, set linkResult(value) { linkResult = value; }, set readResult(value) { readResult = value; }, set currentContext(value) { currentContext = value; } };
}

test('related native create waits for confirmed main and keeps an editable location', async () => {
  const f = fixture();
  const key = f.flow.stageRelated({ name: 'Battery', entityTypeId: 'type-a', parentId: 'location-other' });
  await assert.rejects(() => f.flow.resumeRelatedSteps(), /main item/i);
  assert.deepEqual(f.calls, []);
  f.flow.recordMainCreated('main-a');
  await f.flow.resumeRelatedSteps();
  assert.equal(f.calls[0][0], 'create');
  assert.equal(f.calls[0][1].parentId, 'location-other');
  assert.deepEqual(f.calls[1].slice(0, 3), ['link', 'main-a', 'related-a']);
  assert.equal(f.flow.pending().steps.find(step => step.key === key).state, 'completed');
  assert.equal(f.flow.pending().steps.find(step => step.kind === 'link').state, 'completed');
});

test('failed main native create leaves staged related native create unissued', async () => {
  const f = fixture();
  f.flow.stageRelated({ name: 'Battery', entityTypeId: 'type-a', parentId: 'location-a' });
  let mainIntent = null;
  const main = createEquipmentCreationFlow({
    read: () => mainIntent,
    write: value => { mainIntent = value; },
    clear: () => { mainIntent = null; },
    assignCreated: async () => ({}),
  });
  await assert.rejects(() => main.create(async () => { throw new Error('main create failed'); }, { modelCode: 'MAIN', groupId: 'collection-a', userId: 'member-a', identity: 'session-a' }), /main create failed/);
  await assert.rejects(() => f.flow.resumeRelatedSteps(), /main item/i);
  assert.deepEqual(f.calls, []);
});

test('lost related create response requires UUID reconciliation before link or retry', async () => {
  const f = fixture();
  const key = f.flow.stageRelated({ name: 'Battery', entityTypeId: 'type-a', parentId: 'location-a' });
  f.flow.recordMainCreated('main-a');
  f.createResult = { error: new Error('response lost') };
  await assert.rejects(() => f.flow.resumeRelatedSteps(), /response lost/);
  assert.equal(f.flow.pending().steps.find(step => step.key === key).state, 'uncertain');
  await assert.rejects(() => f.flow.retryRelatedStep(key), /reconcile/i);
  assert.equal(f.calls.filter(call => call[0] === 'create').length, 1);
  f.flow.reconcileRelatedCreate(key, 'related-found');
  await f.flow.resumeRelatedSteps();
  assert.equal(f.calls.filter(call => call[0] === 'create').length, 1);
  assert.deepEqual(f.calls.filter(call => call[0] === 'link')[0].slice(0, 3), ['link', 'main-a', 'related-found']);
});

test('uncertain link checks server state and replays only unresolved link with stable key', async () => {
  const f = fixture();
  f.flow.stageRelated({ name: 'Battery', entityTypeId: 'type-a', parentId: 'location-a' });
  f.flow.recordMainCreated('main-a');
  f.linkResult = { error: new Error('link response lost') };
  await assert.rejects(() => f.flow.resumeRelatedSteps(), /link response lost/);
  const key = f.flow.pending().steps.find(step => step.kind === 'link').request_key;
  f.linkResult = { relatedItems: ['related-a'] };
  await f.flow.resumeRelatedSteps();
  assert.equal(f.calls.filter(call => call[0] === 'create').length, 1);
  assert.deepEqual(f.calls.filter(call => call[0] === 'link').map(call => call[3]), [key, key]);
});

test('retrying one failed related create preserves other completed create and link steps', async () => {
  const f = fixture();
  f.flow.stageRelated({ name: 'Battery', entityTypeId: 'type-a', parentId: 'location-a' });
  const second = f.flow.stageRelated({ name: 'Case', entityTypeId: 'type-a', parentId: 'location-a' });
  f.flow.recordMainCreated('main-a');
  f.createResults = [{ data: { id: 'related-a' } }, { error: { status: 422, message: 'Invalid case' } }];
  await assert.rejects(() => f.flow.resumeRelatedSteps());
  assert.equal(f.flow.pending().steps.find(step => step.key === second).state, 'failed');
  f.createResult = { data: { id: 'related-b' } };
  await f.flow.retryRelatedStep(second);
  assert.equal(f.calls.filter(call => call[0] === 'create').length, 3);
  assert.equal(f.calls.filter(call => call[0] === 'link').length, 2);
});

test('identity change blocks resumed related mutation', async () => {
  const f = fixture();
  f.flow.stageRelated({ name: 'Battery', entityTypeId: 'type-a', parentId: null });
  f.flow.recordMainCreated('main-a');
  f.currentContext = { ...context, identity: 'session-b' };
  await assert.rejects(() => f.flow.resumeRelatedSteps(), /account or collection changed/i);
  assert.deepEqual(f.calls, []);
  assert.equal(relatedItemStorageKey(context), 'related-create:collection-a:member-a');
});

test('completed related records can be cleared before a new main create', async () => {
  const f = fixture();
  f.flow.stageRelated({ name: 'Battery', entityTypeId: 'type-a', parentId: null });
  f.flow.recordMainCreated('main-a');
  await f.flow.resumeRelatedSteps();
  f.flow.clearCompleted();
  assert.equal(f.flow.pending(), null);
  assert.doesNotThrow(() => f.flow.stageRelated({ name: 'Case', entityTypeId: 'type-a', parentId: null }));
});

test('retry of one failed create leaves later pending creates untouched', async () => {
  const f = fixture();
  f.flow.stageRelated({ name: 'Battery', entityTypeId: 'type-a', parentId: null });
  const second = f.flow.stageRelated({ name: 'Case', entityTypeId: 'type-a', parentId: null });
  f.flow.stageRelated({ name: 'Controller', entityTypeId: 'type-a', parentId: null });
  f.flow.recordMainCreated('main-a');
  f.createResults = [{ data: { id: 'related-a' } }, { error: { status: 422, message: 'Invalid case' } }];
  await assert.rejects(() => f.flow.resumeRelatedSteps());
  f.createResult = { data: { id: 'related-b' } };
  await f.flow.retryRelatedStep(second);
  assert.equal(f.calls.filter(call => call[0] === 'create').length, 3);
  assert.equal(f.flow.pending().steps.find(step => step.item?.name === 'Controller').state, 'pending');
});
