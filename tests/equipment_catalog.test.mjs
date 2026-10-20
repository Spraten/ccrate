import assert from 'node:assert/strict';
import test from 'node:test';
import {
  applyEquipmentTemplateDefaults,
  buildEquipmentTemplateUpdate,
  confirmNoMainCreate,
  createEquipmentCreationFlow,
  createEquipmentTemplateApplyFlow,
  createEquipmentTemplateLifecycleFlow,
  createEquipmentTemplateSaveFlow,
  equipmentTemplatePhotoFallback,
  equipmentTemplatePayload,
  saveEquipmentTemplate,
} from '../homebox-ui/overlay/lib/equipment-catalog.js';

function memoryStore(initial = null) {
  let value = initial;
  return { read: () => value, write: next => { value = next; }, clear: () => { value = null; } };
}

const template = {
  id: 'template-1', name: 'Camera kit', entity_type_id: 'type-1', manufacturer: 'Acme',
  model_number: 'MX-1', model_code: 'MX1', description: 'Shared description', tag_ids: ['tag-1'],
  photo_attachment_id: 'source-photo', serial_number: 'DO-NOT-COPY', location_id: 'DO-NOT-COPY',
};

test('template archive and restore retain the same request key until the server confirms', async () => {
  const store = memoryStore();
  const calls = [];
  let attempts = 0;
  const flow = createEquipmentTemplateLifecycleFlow({
    ...store,
    keyFactory: () => 'stable-lifecycle-key',
    request: async (action, templateId, requestKey) => {
      calls.push({ action, templateId, requestKey });
      attempts++;
      if (attempts === 1) throw new Error('connection lost');
      return { id: templateId, archived: action === 'archive' };
    },
  });
  await assert.rejects(flow.change('archive', 'template-1'), /connection lost/);
  assert.deepEqual(store.read(), { action: 'archive', template_id: 'template-1', request_key: 'stable-lifecycle-key' });
  assert.deepEqual(await flow.change('archive', 'template-1'), { id: 'template-1', archived: true });
  assert.deepEqual(calls[0], calls[1]);
  assert.equal(store.read(), null);
});

test('template defaults copy only shared fields and leave per-unit fields blank', () => {
  const defaults = applyEquipmentTemplateDefaults(template);
  assert.deepEqual(defaults, {
    name: 'Camera kit', manufacturer: 'Acme', modelNumber: 'MX-1', modelCode: 'MX1',
    description: 'Shared description', tagIds: ['tag-1'],
  });
  assert.equal('serialNumber' in defaults, false);
  assert.equal('location' in defaults, false);
  assert.equal('photo_attachment_id' in equipmentTemplatePayload({ ...defaults, entityTypeId: 'type-1' }), false);
});

test('template payload contains only shared API fields', () => {
  assert.deepEqual(equipmentTemplatePayload({
    name: 'Camera kit', entityTypeId: 'type-1', manufacturer: 'Acme', modelNumber: 'MX-1',
    modelCode: 'MX1', description: 'Shared description', tags: ['tag-1'], serialNumber: 'unit',
    location: { id: 'shelf' }, condition: 'Ready', status: 'checked_out', displayId: 'DRONE-X-1',
  }), {
    name: 'Camera kit', entity_type_id: 'type-1', manufacturer: 'Acme', model_number: 'MX-1',
    model_code: 'MX1', description: 'Shared description', tag_ids: ['tag-1'],
  });
});

test('template payload preserves normalized tag_ids when a saved request is replayed', () => {
  assert.deepEqual(equipmentTemplatePayload({ name: 'Drone', entityTypeId: 'type-1', tag_ids: ['tag-a', 'tag-b'] }).tag_ids, ['tag-a', 'tag-b']);
});

test('template photo fallback uses its verified owner and yields to an item photo', () => {
  const source = { photo_entity_id: 'source-native-uuid', photo_attachment_id: 'attachment-1' };
  assert.deepEqual(equipmentTemplatePhotoFallback(source), { entity_id: 'source-native-uuid', attachment_id: 'attachment-1' });
  assert.equal(equipmentTemplatePhotoFallback(source, true), null);
  assert.equal(equipmentTemplatePhotoFallback({ photo_attachment_id: 'orphan-attachment' }), null);
});

test('editing a template sends its id and optimistic updated timestamp', async () => {
  const calls = [];
  const workshop = {
    refresh: async () => ({ identity: 'member' }),
    request: async (...args) => { calls.push(args); return { id: 'template-1' }; },
  };
  await saveEquipmentTemplate(workshop, { name: 'Tripod', entityTypeId: 'type-1' }, 'request-edit', undefined, {
    templateId: 'template-1', expectedUpdatedAt: '2026-10-19T12:00:00Z',
  });
  assert.equal(calls[0][0], 'equipment/templates/save');
  assert.deepEqual(calls[0][1], {
    request_key: 'request-edit', fields: equipmentTemplatePayload({ name: 'Tripod', entityTypeId: 'type-1' }),
    template_id: 'template-1', expected_updated_at: '2026-10-19T12:00:00Z',
  });
});

test('template save flow reuses the saved request key and payload after an ambiguous timeout', async () => {
  const store = memoryStore();
  const calls = [];
  let attempt = 0;
  const flow = createEquipmentTemplateSaveFlow({
    ...store, keyFactory: () => 'template-save-key',
    save: async intent => {
      calls.push(intent);
      if (attempt++ === 0) throw new Error('No confirmation received.');
      return { id: 'template-1', updated_at: 'now' };
    },
  });
  const input = { fields: { name: 'Drone', entityTypeId: 'type-1', modelCode: 'M4P' }, sourceEntityId: 'source-1' };
  await assert.rejects(flow.save(input), /No confirmation/);
  const stored = store.read();
  assert.equal(stored.request_key, 'template-save-key');
  const saved = await flow.resume();
  assert.equal(saved.id, 'template-1');
  assert.deepEqual(calls.map(row => [row.request_key, row.payload]), [
    [stored.request_key, stored.payload], [stored.request_key, stored.payload],
  ]);
  assert.equal(store.read(), null);
});

test('template save flow rejects changed intent while an earlier request is unconfirmed', async () => {
  const store = memoryStore();
  const flow = createEquipmentTemplateSaveFlow({ ...store, keyFactory: () => 'pending-key', save: async () => { throw new Error('timeout'); } });
  await assert.rejects(flow.save({ fields: { name: 'Drone', entityTypeId: 'type-1', modelCode: 'M4P' } }), /timeout/);
  await assert.rejects(flow.save({ fields: { name: 'Different', entityTypeId: 'type-1', modelCode: 'M4P' } }), /exact save/i);
});

test('definitive template rejection requires explicit review before corrected intent gets a new key', async () => {
  const store = memoryStore();
  let key = 0;
  const calls = [];
  const flow = createEquipmentTemplateSaveFlow({
    ...store, keyFactory: () => `save-${++key}`,
    save: async intent => {
      calls.push(intent);
      if (intent.payload.fields.model_code === 'BAD') throw Object.assign(new Error('invalid model code'), { status: 400 });
      return { id: 'template-1' };
    },
  });
  await assert.rejects(flow.save({ fields: { name: 'Drone', entityTypeId: 'type-1', modelCode: 'BAD' } }), /invalid model code/);
  assert.equal(store.read().rejected, true);
  await assert.rejects(flow.resume(), /explicitly discard/i);
  assert.equal(calls.length, 1);
  await assert.rejects(flow.save({ fields: { name: 'Drone', entityTypeId: 'type-1', modelCode: 'GOOD' } }), /explicitly discard/i);
  assert.equal(calls[0].request_key, 'save-1');
  flow.discardRejected();
  await flow.save({ fields: { name: 'Drone', entityTypeId: 'type-1', modelCode: 'GOOD' } });
  assert.equal(calls[1].request_key, 'save-2');
});

test('stale template version conflict can only be replaced after refreshing and confirming latest review', async () => {
  const store = memoryStore();
  let key = 0;
  const calls = [];
  const flow = createEquipmentTemplateSaveFlow({
    ...store, keyFactory: () => `version-${++key}`,
    save: async intent => {
      calls.push(intent);
      if (intent.request_key === 'version-1') throw Object.assign(new Error('Template changed since it was read'), { status: 409 });
      return { id: 'template-1' };
    },
  });
  await assert.rejects(flow.save({ fields: { name: 'Drone', entityTypeId: 'type-1', modelCode: 'M4P' }, templateId: 'template-1', expectedUpdatedAt: 'old' }), /Template changed/);
  assert.equal(store.read().stale_version_conflict, true);
  await assert.rejects(flow.save({ fields: { name: 'Latest drone', entityTypeId: 'type-1', modelCode: 'M4P' }, templateId: 'template-1', expectedUpdatedAt: 'new' }), /refresh and review/i);
  assert.equal(calls.length, 1);
  assert.throws(() => flow.discardStaleConflict(), /review the latest template/i);
  flow.discardStaleConflict(true);
  await flow.save({ fields: { name: 'Latest drone', entityTypeId: 'type-1', modelCode: 'M4P' }, templateId: 'template-1', expectedUpdatedAt: 'new' });
  assert.equal(calls[1].request_key, 'version-2');
  assert.equal(calls[1].payload.expected_updated_at, 'new');
});

test('request-key 409 remains an unresolved replay conflict, not a stale-version correction', async () => {
  const store = memoryStore();
  let calls = 0;
  const flow = createEquipmentTemplateSaveFlow({
    ...store, keyFactory: () => 'replay-conflict',
    save: async () => { calls++; throw Object.assign(new Error('Request key was already used for another request'), { status: 409 }); },
  });
  await assert.rejects(flow.save({ fields: { name: 'Drone', entityTypeId: 'type-1', modelCode: 'M4P' } }), /already used/);
  assert.equal(store.read().stale_version_conflict, undefined);
  assert.equal(store.read().rejected, undefined);
  await assert.rejects(flow.save({ fields: { name: 'Other', entityTypeId: 'type-1', modelCode: 'M4P' } }), /exact save/i);
  assert.equal(calls, 1);
});

test('shared template update uses the supported full Homebox payload and preserves per-unit values', () => {
  const current = {
    id: 'unit-1', name: 'Old name', manufacturer: 'Unit maker', modelNumber: 'Unit model', description: 'Unit detail',
    serialNumber: 'SERIAL-1', parent: { id: 'shelf-9' }, entityType: { id: 'type-1' }, tags: [{ id: 'tag-old' }],
    fields: [{ name: 'per-unit', textValue: 'preserve' }], notes: 'Unit note', status: 'checked_out',
  };
  const update = buildEquipmentTemplateUpdate(current, {
    name: 'New name', manufacturer: 'New maker', modelNumber: 'New model', description: 'new',
    tagIds: ['new-tag'], serialNumber: 'SHOULD-NOT-COPY', parentId: 'wrong', status: 'available', displayId: 'WRONG',
  }, ['name', 'manufacturer', 'modelNumber', 'description', 'tagIds']);
  assert.equal(update.id, 'unit-1');
  assert.equal(update.entityTypeId, 'type-1');
  assert.equal(update.parentId, 'shelf-9');
  assert.equal(update.serialNumber, 'SERIAL-1');
  assert.equal(update.notes, 'Unit note');
  assert.equal(update.status, 'checked_out');
  assert.deepEqual(update.fields, current.fields);
  assert.equal(update.name, 'New name');
  assert.deepEqual(update.tagIds, ['new-tag']);
  assert.equal('displayId' in update, false);
  assert.throws(() => buildEquipmentTemplateUpdate(current, {}, ['serialNumber']), /shared field/i);
});

test('template application selects exact units, reports partial outcomes, and never retries uncertain patches', async () => {
  const store = memoryStore();
  const patched = [];
  const entities = Object.fromEntries(['unit-ok', 'unit-rejected', 'unit-timeout', 'unit-unselected'].map(id => [id, {
    id, name: 'Old name', manufacturer: 'Unit maker', modelNumber: 'Unit model', description: 'Unit detail',
    serialNumber: id, parent: { id: `shelf-${id}` }, entityType: { id: 'type-1' }, tags: [], fields: [], notes: 'unit note',
  }]));
  const events = [];
  const nativeItemsApi = {
    async get(id) { events.push(['GET', id]); return { data: entities[id] }; },
    async update(id, update) {
      events.push(['PUT', id]);
      patched.push(id);
      assert.equal(update.id, id);
      assert.equal(update.serialNumber, id);
      assert.equal(update.parentId, `shelf-${id}`);
      assert.equal(update.entityTypeId, 'type-1');
      if (id === 'unit-timeout') throw new Error('connection lost');
      if (id === 'unit-rejected') return { error: Object.assign(new Error('native rejected'), { status: 400 }) };
      entities[id] = { ...entities[id], name: update.name, manufacturer: update.manufacturer };
      return { data: update };
    },
    async patch() { assert.fail('The native EntityPatch API does not support shared-field updates.'); },
  };
  const flow = createEquipmentTemplateApplyFlow({
    ...store,
    getItem: id => nativeItemsApi.get(id),
    updateItem: (id, update) => nativeItemsApi.update(id, update),
  });
  await flow.apply({
    selectedEntityIds: ['unit-ok', 'unit-rejected', 'unit-timeout'],
    fields: { name: 'New name', manufacturer: 'New maker', serialNumber: 'wrong' },
    selectedFields: ['name', 'manufacturer'],
  });
  assert.deepEqual(store.read().units.map(row => [row.entity_id, row.status]), [
    ['unit-ok', 'succeeded'], ['unit-rejected', 'failed'], ['unit-timeout', 'uncertain'],
  ]);
  assert.deepEqual(patched, ['unit-ok', 'unit-rejected', 'unit-timeout']);
  assert.deepEqual(events.slice(0, 3), [['GET', 'unit-ok'], ['PUT', 'unit-ok'], ['GET', 'unit-ok']]);
  await flow.resume();
  assert.deepEqual(patched, ['unit-ok', 'unit-rejected', 'unit-timeout']);
});

test('ambiguous server failure after a shared-field PUT is uncertain and cannot auto-repeat', async () => {
  const store = memoryStore();
  let puts = 0;
  const item = { id: 'unit-1', entityType: { id: 'type-1' }, name: 'Old' };
  const flow = createEquipmentTemplateApplyFlow({
    ...store, getItem: async () => item,
    updateItem: async () => { puts++; return { error: Object.assign(new Error('server disconnected'), { status: 500 }) }; },
  });
  const result = await flow.apply({ selectedEntityIds: ['unit-1'], fields: { name: 'New' }, selectedFields: ['name'] });
  assert.equal(result.units[0].status, 'uncertain');
  await flow.resume();
  assert.equal(puts, 1);
});

test('an interrupted in-flight template patch is recovered as uncertain without a repeat call', async () => {
  const store = memoryStore({ fields: { name: 'Target' }, selected_fields: ['name'], units: [{ entity_id: 'unit-1', status: 'in_flight' }] });
  let patches = 0;
  const flow = createEquipmentTemplateApplyFlow({
    ...store, getItem: async id => ({ id, name: 'Current' }),
    updateItem: async () => { patches++; return {}; },
  });
  assert.equal(flow.recover().units[0].status, 'uncertain');
  await flow.resume();
  assert.equal(patches, 0);
});

test('uncertain apply results require explicit reconciliation and are never reissued', async () => {
  const store = memoryStore({ fields: { name: 'Target' }, selected_fields: ['name'], units: [{ entity_id: 'unit-1', status: 'uncertain' }] });
  let puts = 0;
  const flow = createEquipmentTemplateApplyFlow({
    ...store, getItem: async id => ({ id, entityType: { id: 'type-1' }, name: 'Target' }),
    updateItem: async () => { puts++; return {}; },
  });
  await assert.rejects(flow.apply({ selectedEntityIds: ['unit-1'], fields: { name: 'Target' }, selectedFields: ['name'] }), /manual review/i);
  flow.resolveUncertain('unit-1', 'succeeded');
  assert.equal(store.read().units[0].status, 'succeeded');
  await flow.resume();
  assert.equal(puts, 0);
});

test('template apply stops before another native write when account or collection changes during revalidation', async () => {
  const store = memoryStore();
  let binding = 'account-a:collection-a';
  const writes = [];
  const flow = createEquipmentTemplateApplyFlow({
    ...store,
    isCurrent: () => binding === 'account-a:collection-a',
    getItem: async id => { binding = 'account-b:collection-b'; return { id, name: 'Current' }; },
    updateItem: async id => { writes.push(id); return { data: { id } }; },
  });
  const result = await flow.apply({ selectedEntityIds: ['unit-1', 'unit-2'], fields: { name: 'Target' }, selectedFields: ['name'],
    scope: { identity: 'session-a', group_id: 'collection-a', user_id: 'account-a' } });
  assert.deepEqual(writes, [], 'the current item is revalidated but no write starts after the owner changes');
  assert.deepEqual(result.units.map(row => row.status), ['pending', 'pending']);
});

test('template apply marks the in-progress unit uncertain and stops the write loop after identity changes during a write', async () => {
  const store = memoryStore();
  let binding = 'account-a:collection-a';
  const writes = [];
  const flow = createEquipmentTemplateApplyFlow({
    ...store,
    isCurrent: () => binding === 'account-a:collection-a',
    getItem: async id => ({ id, entityType: { id: 'type-1' }, name: 'Current' }),
    updateItem: async id => { writes.push(id); binding = 'account-b:collection-b'; return { data: { id } }; },
  });
  const result = await flow.apply({ selectedEntityIds: ['unit-1', 'unit-2'], fields: { name: 'Target' }, selectedFields: ['name'],
    scope: { identity: 'session-a', group_id: 'collection-a', user_id: 'account-a' } });
  assert.deepEqual(writes, ['unit-1']);
  assert.deepEqual(result.units.map(row => row.status), ['uncertain', 'pending']);
});

test('duplicate create submissions invoke native creation once', async () => {
  const store = memoryStore();
  let release;
  let creates = 0;
  const flow = createEquipmentCreationFlow({ ...store, keyFactory: () => 'request-1', assignCreated: async () => ({ display_id: 'DRONE-X-1' }) });
  const create = () => flow.create(async () => {
    creates++;
    await new Promise(resolve => { release = resolve; });
    return { id: 'native-1' };
  }, { modelCode: 'X' });
  const first = create();
  await new Promise(resolve => setImmediate(resolve));
  await assert.rejects(create(), /already in progress/i);
  release();
  await first;
  assert.equal(creates, 1);
});

test('assignment retry reuses entity UUID and request key without creating another native item', async () => {
  const store = memoryStore();
  let attempts = 0;
  const calls = [];
  const flow = createEquipmentCreationFlow({ ...store, keyFactory: () => 'request-stable', assignCreated: async intent => {
    calls.push(intent);
    attempts++;
    if (attempts === 1) throw new Error('assignment timeout');
    return { display_id: 'DRONE-X-1' };
  } });
  let creates = 0;
  await assert.rejects(flow.create(async () => { creates++; return { id: 'native-1' }; }, { templateId: 'template-1' }), /assignment timeout/);
  const result = await flow.resumeAssignment();
  assert.equal(result.entity_id, 'native-1');
  assert.deepEqual(calls.map(row => [row.entity_id, row.request_key]), [
    ['native-1', 'request-stable'], ['native-1', 'request-stable'],
  ]);
  assert.equal(creates, 1);
  assert.equal(store.read(), null);
});

test('assignment retry completes queued photo uploads once before assigning and never recreates native item', async () => {
  const store = memoryStore();
  const events = [];
  let assignmentAttempt = 0;
  const flow = createEquipmentCreationFlow({
    ...store, keyFactory: () => 'photo-request',
    completePostCreate: async (intent, step) => { events.push(`photo:${intent.entity_id}:${step.key}`); return {}; },
    assignCreated: async intent => {
      events.push(`assign:${intent.entity_id}:${intent.request_key}`);
      if (assignmentAttempt++ === 0) throw new Error('assignment timeout');
      return { display_id: 'DRONE-M4P-1' };
    },
  });
  let nativeCreates = 0;
  await assert.rejects(flow.create(async () => { nativeCreates++; return { id: 'native-1' }; }, {
    templateId: 'template-1', postCreateSteps: [{ key: 'photo-a', name: 'front.jpg', size: 123 }],
  }), /assignment timeout/);
  await flow.resumeAssignment();
  assert.equal(nativeCreates, 1);
  assert.deepEqual(events, [
    'photo:native-1:photo-a', 'assign:native-1:photo-request', 'assign:native-1:photo-request',
  ]);
});

test('uncertain photo upload blocks assignment and later steps until reviewed', async () => {
  let intent = null;
  const events = [];
  const flow = createEquipmentCreationFlow({
    read: () => intent,
    write: value => { intent = structuredClone(value); },
    clear: () => { intent = null; },
    completePostCreate: async (_intent, step) => {
      events.push(`upload:${step.key}`);
      if (step.key === 'first') throw new Error('connection lost');
      return {};
    },
    assignCreated: async () => { events.push('assign'); return { display_id: 'DRONE-1' }; },
  });
  flow.begin({ modelCode: 'M-1', postCreateSteps: [{ key: 'first' }, { key: 'second' }] });
  flow.recordCreated('native-1');
  await assert.rejects(flow.resumeAssignment(), /connection lost/);
  assert.deepEqual(events, ['upload:first']);
  assert.equal(intent.post_create_steps[0].status, 'uncertain');
  assert.equal(intent.post_create_steps[1].status, 'pending');
  assert.equal(intent.state, 'assignment_pending');

  flow.reconcilePostCreateStep('first', true);
  await flow.resumeAssignment();
  assert.deepEqual(events, ['upload:first', 'upload:second', 'assign']);
  assert.equal(intent, null);
});

test('uncertain native create can be reconciled to its found UUID or explicitly cleared after review', async () => {
  const store = memoryStore();
  const flow = createEquipmentCreationFlow({ ...store, assignCreated: async () => ({ display_id: 'DRONE-M4P-1' }) });
  await assert.rejects(flow.create(async () => { throw new Error('lost response'); }, { modelCode: 'M4P' }));
  flow.reconcileCreated('native-found');
  assert.equal(store.read().entity_id, 'native-found');
  assert.equal(store.read().state, 'assignment_pending');
  await flow.resumeAssignment();
  await assert.rejects(flow.create(async () => { throw new Error('lost response'); }, { modelCode: 'M4P' }));
  flow.confirmNoNativeCreate();
  assert.equal(store.read(), null);
});

test('a persisted pending native create recovers as uncertain and supports manual reconciliation', () => {
  const store = memoryStore({ state: 'native_create_pending', request_key: 'create-1', entity_type_id: 'type-1' });
  const flow = createEquipmentCreationFlow({ ...store, assignCreated: async () => ({}) });
  const recovered = flow.recover();
  assert.equal(recovered.state, 'native_create_uncertain');
  assert.equal(flow.reconcileCreated('found-native-1').entity_id, 'found-native-1');
});

test('saved assignment intent survives flow reconstruction after modal interruption', async () => {
  const store = memoryStore({
    state: 'assignment_pending', request_key: 'request-after-reload',
    template_id: 'template-1', model_code: null, entity_id: 'native-created-before-reload',
  });
  const calls = [];
  const flow = createEquipmentCreationFlow({ ...store, assignCreated: async intent => {
    calls.push(intent);
    return { display_id: 'DRONE-X-1' };
  } });
  const result = await flow.resumeAssignment();
  assert.equal(result.entity_id, 'native-created-before-reload');
  assert.deepEqual(calls.map(row => [row.entity_id, row.request_key]), [
    ['native-created-before-reload', 'request-after-reload'],
  ]);
  assert.equal(store.read(), null);
});

test('uncertain native creation blocks a second create until manually reviewed', async () => {
  const store = memoryStore();
  let creates = 0;
  const flow = createEquipmentCreationFlow({ ...store, keyFactory: () => 'request-1', assignCreated: async () => ({}) });
  await assert.rejects(flow.create(async () => { creates++; throw new Error('native response lost'); }, { modelCode: 'X' }), /native response lost/);
  assert.equal(store.read().state, 'native_create_uncertain');
  await assert.rejects(flow.create(async () => { creates++; return { id: 'duplicate' }; }, { modelCode: 'X' }), /review.*before creating/i);
  assert.equal(creates, 1);
});

test('creation without a saved template requires a model code before native create', async () => {
  const store = memoryStore();
  const flow = createEquipmentCreationFlow({ ...store, keyFactory: () => 'request-1', assignCreated: async () => ({}) });
  let creates = 0;
  await assert.rejects(flow.create(async () => { creates++; return { id: 'native-1' }; }, {}), /model code/i);
  assert.equal(creates, 0);
});
