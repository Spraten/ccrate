/** Related create/link intents live apart from the main create's metadata steps. */
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
