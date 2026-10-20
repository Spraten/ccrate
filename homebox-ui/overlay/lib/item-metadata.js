/** Related create/link intents live apart from the main create's metadata steps. */
import { PACKAGING_OPTIONS, buildNativeMetadataUpdate, nativeMetadataMatches, persistFieldNotes, validateCustomRows } from './item-create-fields.js';

const fieldKey = name => String(name || '').trim().replace(/\s+/g, ' ').toLocaleLowerCase().replace(/ß/g, 'ss');

export function detailMetadataDraft(item, metadata = {}) {
  const fields = Array.isArray(item?.fields) ? item.fields : [];
  const packaging = fields.find(field => fieldKey(field.name) === 'device packaging' && field.type === 'text');
  return {
    serialNumber: String(item?.serialNumber || ''),
    packaging: PACKAGING_OPTIONS.includes(packaging?.textValue) ? packaging.textValue : '',
    rows: fields.filter(field => field.type === 'text' && fieldKey(field.name) !== 'device packaging').map(field => ({
      ...(field.id ? { id: field.id } : {}), name: field.name, value: String(field.textValue || ''), note: String(metadata.fieldNotes?.[fieldKey(field.name)] || ''),
    })),
  };
}

function detailNativeMatches(item, draft) {
  const packaging = (item.fields || []).find(field => fieldKey(field.name) === 'device packaging');
  const desired = draft.packaging || '';
  if (String(packaging?.textValue || '') !== desired) return false;
  const names = new Set(validateCustomRows(draft.rows).map(row => fieldKey(row.name)));
  if ((item.fields || []).some(field => field.type === 'text' && fieldKey(field.name) !== 'device packaging' && !names.has(fieldKey(field.name)))) return false;
  return nativeMetadataMatches(item, draft);
}

/** Native Homebox owns the field records; Notes is committed only after native readback. */
export async function saveDetailMetadata({ api, workshop, item, draft, identity, requestKey }) {
  const rows = validateCustomRows(draft.rows);
  if (!requestKey) throw new Error('A stable save request key is required.');
  if (draft.packaging && !PACKAGING_OPTIONS.includes(draft.packaging)) throw new Error('Choose a listed packaging value.');
  const currentResponse = await api.items.get(item.id);
  if (currentResponse.error || !currentResponse.data) throw currentResponse.error || new Error('Item could not be loaded.');
  let current = currentResponse.data;
  if (!detailNativeMatches(current, draft)) {
    const update = buildNativeMetadataUpdate(current, { ...draft, rows: [] });
    const selected = new Set();
    const additions = [];
    rows.forEach((row, index) => {
      const id = draft.rows[index]?.id;
      const field = id ? update.fields.find(candidate => candidate.id === id) : update.fields.find(candidate => fieldKey(candidate.name) === fieldKey(row.name));
      if (id && !field) throw new Error(`Custom field ${row.name} changed. Reload before saving.`);
      if (field && (field.type !== 'text' || fieldKey(field.name) === 'device packaging' || selected.has(field))) throw new Error(`Custom field ${row.name} needs review.`);
      if (field) { field.name = row.name; field.textValue = row.value; selected.add(field); }
      else additions.push({ name: row.name, type: 'text', textValue: row.value, numberValue: 0, booleanValue: false });
    });
    update.fields = update.fields.filter(field => field.type !== 'text' || fieldKey(field.name) === 'device packaging' || selected.has(field)).concat(additions);
    const packaging = update.fields.find(field => fieldKey(field.name) === 'device packaging');
    if (packaging && !draft.packaging) packaging.textValue = '';
    const response = await api.items.update(item.id, update);
    if (response.error) throw response.error;
    const confirmed = await api.items.get(item.id);
    if (confirmed.error || !confirmed.data || !detailNativeMatches(confirmed.data, draft)) throw new Error('Native item fields were not confirmed. Reload and retry.');
    current = confirmed.data;
  }
  const fieldNotes = await persistFieldNotes(workshop, { entity_id: item.id, identity }, { request_key: requestKey, fields: rows.map(row => ({ name: row.name, note: row.note })) });
  const expectedNotes = Object.fromEntries(rows.filter(row => row.note.trim()).map(row => [fieldKey(row.name), row.note.trim()]));
  if (JSON.stringify(Object.entries(fieldNotes).sort()) !== JSON.stringify(Object.entries(expectedNotes).sort())) throw new Error('Custom field notes were not confirmed.');
  return { item: current, fieldNotes };
}

export async function changeRelatedItem(workshop, entityId, relatedId, action, requestKey, identity) {
  if (!['add', 'remove'].includes(action) || !entityId || !relatedId || entityId === relatedId || !requestKey) throw new Error('Choose a different collection item.');
  const result = await workshop.request(`item-metadata/related/${action}`, { request_key: requestKey, entity_id: entityId, related_entity_id: relatedId }, identity);
  const listed = Array.isArray(result?.relatedItems) && result.relatedItems.some(row => (typeof row === 'string' ? row : row.id) === relatedId);
  if ((action === 'add' && !listed) || (action === 'remove' && listed)) throw new Error('Related item change was not confirmed.');
  return result;
}

export async function searchRelatedItems(api, query, currentId) {
  if (!String(query || '').trim()) return [];
  const response = await api.items.getAll({ q: String(query).trim(), page: 1, pageSize: 20, includeArchived: false });
  if (response.error || !response.data) throw response.error || new Error('Items could not be searched.');
  return (response.data.items || []).filter(item => item.id && item.id !== currentId && !item.isLocation && !item.entityType?.isLocation).map(item => ({ id: item.id, name: item.name }));
}

export function relatedItemStorageKey(context) {
  return `related-create:${context.group.id}:${context.user.id}`;
}

function definitive(error) {
  const status = Number(error?.status || error?.statusCode || error?.response?.status || 0);
  return status >= 400 && status < 500 && ![408, 409, 429].includes(status);
}

function linked(result, id) {
  return Array.isArray(result?.relatedItems) && result.relatedItems.some(item => (typeof item === 'string' ? item : item?.id) === id);
}

export function createRelatedItemFlow({ read, write, context, createNative, link, readLinks, keyFactory = () => crypto.randomUUID(), expectedContext }) {
  const expected = expectedContext;
  let busy = false;
  const state = () => read();
  function save(value) { write(value); return value; }
  function requireState() {
    const value = state();
    if (!value) throw new Error('There are no staged related items.');
    return value;
  }
  async function checkIdentity(value) {
    const current = await context();
    if (current.group?.id !== value.group_id || current.user?.id !== value.user_id || current.identity !== value.identity) {
      throw new Error('The account or collection changed. Switch back to the original context to resume related items.');
    }
  }
  function stageRelated(item) {
    if (!expected?.group?.id || !expected?.user?.id || !expected.identity) throw new Error('Refresh the account and collection before staging related items.');
    const prior = state();
    if (prior && (prior.group_id !== expected.group.id || prior.user_id !== expected.user.id || prior.identity !== expected.identity)) {
      throw new Error('The account or collection changed.');
    }
    if (prior?.main_entity_id) throw new Error('Finish the current related items before staging another item.');
    const record = prior || { group_id: expected.group.id, user_id: expected.user.id, identity: expected.identity, main_entity_id: null, steps: [] };
    const existingId = String(item.entityId || '').trim();
    if (!existingId && (!String(item.name || '').trim() || !String(item.entityTypeId || '').trim())) throw new Error('A related item needs a name and type.');
    const key = keyFactory();
    if (!existingId) record.steps.push({ key, request_key: key, kind: 'create', state: 'pending', item: structuredClone(item), entity_id: null, main_entity_id: null });
    const linkKey = keyFactory();
    record.steps.push({ key: linkKey, request_key: linkKey, kind: 'link', source_key: existingId ? null : key, entity_id: existingId || null, main_entity_id: null, state: 'pending' });
    save(record);
    return existingId ? linkKey : key;
  }
  function recordMainCreated(entityId) {
    const record = requireState();
    const id = String(entityId || '').trim();
    if (!id) throw new Error('Confirm the main item UUID before creating related items.');
    if (record.main_entity_id && record.main_entity_id !== id) throw new Error('Related items already belong to a different main item.');
    record.main_entity_id = id;
    record.steps = record.steps.map(step => ({ ...step, main_entity_id: id }));
    return save(record);
  }
  function clearBeforeMain() {
    const record = state();
    if (record?.main_entity_id) throw new Error('A confirmed main item still has related steps.');
    write(null);
  }
  function clearCompleted() {
    const record = state();
    if (record && record.steps.some(step => step.state !== 'completed')) throw new Error('Finish the pending related steps first.');
    write(null);
  }
  function reconcileRelatedCreate(stepKey, entityId) {
    const record = requireState();
    const step = record.steps.find(row => row.key === stepKey && row.kind === 'create');
    const id = String(entityId || '').trim();
    if (!step || step.state !== 'uncertain' || !id) throw new Error('Reconcile an uncertain related create with its confirmed item UUID.');
    step.entity_id = id;
    step.state = 'completed';
    const linkStep = record.steps.find(row => row.kind === 'link' && row.source_key === stepKey);
    if (linkStep) linkStep.entity_id = id;
    return save(record);
  }
  async function resumeRelatedSteps(onlyKeys = null) {
    if (busy) throw new Error('Related item follow-up is already running.');
    const initial = requireState();
    if (!initial.main_entity_id) throw new Error('Confirm the main item before creating related items.');
    await checkIdentity(initial);
    busy = true;
    try {
      let record = state();
      for (const step of record.steps) {
        if (onlyKeys && !onlyKeys.has(step.key)) continue;
        if (step.state === 'completed') continue;
        await checkIdentity(record);
        if (step.kind === 'create') {
          if (step.state === 'uncertain') throw new Error(`Related item “${step.item.name}” has an uncertain create. Reconcile its UUID before retrying.`);
          if (step.state === 'failed') throw new Error(`Related item “${step.item.name}” failed: ${step.error || 'review and retry this step'}`);
          // Commit uncertainty before the native request. Reloads cannot issue it again.
          step.state = 'uncertain'; save(record);
          try {
            const result = await createNative(step.item);
            if (result?.error) throw result.error;
            const id = String(result?.data?.id || result?.id || '').trim();
            if (!id) throw new Error('The related create returned no UUID. Reconcile it before retrying.');
            step.entity_id = id;
            step.state = 'completed';
            const linkStep = record.steps.find(row => row.kind === 'link' && row.source_key === step.key);
            if (linkStep) linkStep.entity_id = id;
            save(record);
          } catch (error) {
            step.state = definitive(error) ? 'failed' : 'uncertain';
            step.error = String(error?.message || error);
            save(record);
            throw error;
          }
        } else {
          if (!step.entity_id) throw new Error('Confirm the related item before linking it.');
          if (step.state === 'failed') throw new Error(`Link for related item ${step.entity_id} failed: ${step.error || 'review and retry this step'}`);
          if (step.state === 'uncertain') {
            const current = await readLinks(record.main_entity_id);
            if (linked(current, step.entity_id)) { step.state = 'completed'; step.error = undefined; save(record); continue; }
          }
          await checkIdentity(record);
          step.state = 'uncertain'; save(record);
          try {
            const result = await link(record.main_entity_id, step.entity_id, step.request_key);
            if (result?.error) throw result.error;
            if (!linked(result, step.entity_id)) throw new Error('The relation was not confirmed; check it before retrying.');
            step.state = 'completed'; step.error = undefined; save(record);
          } catch (error) {
            step.state = definitive(error) ? 'failed' : 'uncertain';
            step.error = String(error?.message || error);
            save(record);
            throw error;
          }
        }
      }
      return record;
    } finally { busy = false; }
  }
  async function retryRelatedStep(stepKey) {
    const record = requireState();
    await checkIdentity(record);
    const step = record.steps.find(row => row.key === stepKey);
    if (!step) throw new Error('The related step was not found.');
    if (step.state === 'uncertain' && step.kind === 'create') throw new Error('Reconcile the uncertain native create before retrying.');
    if (step.state === 'completed') return record;
    if (step.state === 'failed') { step.state = 'pending'; step.error = undefined; save(record); }
    const onlyKeys = new Set([step.key]);
    if (step.kind === 'create') {
      const dependent = record.steps.find(row => row.kind === 'link' && row.source_key === step.key);
      if (dependent) onlyKeys.add(dependent.key);
    }
    return resumeRelatedSteps(onlyKeys);
  }
  return { pending: state, stageRelated, recordMainCreated, clearBeforeMain, clearCompleted, resumeRelatedSteps, reconcileRelatedCreate, retryRelatedStep };
}
