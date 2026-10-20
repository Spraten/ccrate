/** Shared catalog fields and recoverable create/assignment flow for CreateEntity. */
export function applyEquipmentTemplateDefaults(template) {
  return {
    name: String(template?.name || ''),
    manufacturer: String(template?.manufacturer || ''),
    modelNumber: String(template?.model_number || ''),
    modelCode: String(template?.model_code || ''),
    description: String(template?.description || ''),
    tagIds: Array.isArray(template?.tag_ids) ? [...template.tag_ids] : [],
  };
}

export function equipmentTemplatePayload(fields) {
  const payload = {
    name: String(fields?.name || ''),
    entity_type_id: String(fields?.entityTypeId || fields?.entity_type_id || ''),
    manufacturer: String(fields?.manufacturer || ''),
    model_number: String(fields?.modelNumber || fields?.model_number || ''),
    model_code: String(fields?.modelCode || fields?.model_code || ''),
    description: String(fields?.description || ''),
    tag_ids: Array.isArray(fields?.tags) ? [...fields.tags] : Array.isArray(fields?.tagIds) ? [...fields.tagIds] : Array.isArray(fields?.tag_ids) ? [...fields.tag_ids] : [],
  };
  if (fields?.photo_attachment_id) payload.photo_attachment_id = String(fields.photo_attachment_id);
  if (fields?.photo_entity_id) payload.photo_entity_id = String(fields.photo_entity_id);
  return payload;
}

const SHARED_UPDATE_FIELDS = new Set(['name', 'manufacturer', 'modelNumber', 'description', 'tagIds']);

/** Return only the template-owned attachment pair; an item's own photo wins. */
export function equipmentTemplatePhotoFallback(template, hasOwnPhoto = false) {
  if (hasOwnPhoto || !template?.photo_entity_id || !template?.photo_attachment_id) return null;
  return { entity_id: template.photo_entity_id, attachment_id: template.photo_attachment_id };
}

/** Build a Homebox PUT payload from the latest native item, changing only shared fields. */
export function buildEquipmentTemplateUpdate(current, fields, selectedFields) {
  const selected = [...new Set(selectedFields || [])];
  const unsupported = selected.filter(field => !SHARED_UPDATE_FIELDS.has(field));
  if (unsupported.length) throw new Error(`Only shared fields can be applied: ${unsupported.join(', ')}`);
  if (!current?.id || !current?.entityType?.id) throw new Error('A current native item is required.');
  const update = {
    ...current,
    id: current.id,
    parentId: current.parent?.id || null,
    entityTypeId: current.entityType.id,
    tagIds: Array.isArray(current.tags) ? current.tags.map(tag => tag.id) : [],
    fields: Array.isArray(current.fields) ? current.fields.map(field => ({ ...field })) : [],
    syncChildEntityLocations: Boolean(current.syncChildEntityLocations),
  };
  for (const field of selected) {
    if (field === 'tagIds') update.tagIds = Array.isArray(fields?.tagIds) ? [...fields.tagIds] : [];
    else update[field] = String(fields?.[field] || '');
  }
  return update;
}

function errorStatus(error) {
  return Number(error?.status || error?.statusCode || error?.response?.status || 0);
}

function isStaleTemplateVersionConflict(error) {
  return errorStatus(error) === 409 && /template changed since it was read/i.test(String(error?.message || error));
}

function stableJSON(value) {
  if (Array.isArray(value)) return `[${value.map(stableJSON).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${stableJSON(value[key])}`).join(',')}}`;
  return JSON.stringify(value);
}

function normalizedFieldValue(item, field) {
  if (field === 'tagIds') return (item.tagIds || item.tags?.map(tag => tag.id) || []).slice().sort();
  return String(item[field] || '');
}

function unitMatchesExpected(item, fields, selectedFields) {
  return selectedFields.every(field => JSON.stringify(normalizedFieldValue(item, field)) === JSON.stringify(normalizedFieldValue(fields, field)));
}

/** Sequential, persisted apply flow. An interrupted in-flight native patch is never repeated. */
export function createEquipmentTemplateApplyFlow({ read, write, clear, getItem, updateItem, isCurrent = () => true }) {
  async function resume() {
    let state = read();
    if (!state) return { units: [] };
    state.units = state.units.map(unit => unit.status === 'in_flight' ? { ...unit, status: 'uncertain' } : unit);
    write(state);
    for (let index = 0; index < state.units.length; index++) {
      if (state.units[index].status !== 'pending') continue;
      const unit = state.units[index];
      if (!isCurrent(state.scope)) break;
      state.units[index] = { ...unit, status: 'in_flight' };
      write(state);
      try {
        const current = await getItem(unit.entity_id);
        if (!isCurrent(state.scope)) {
          state.units[index] = { ...unit, status: 'pending', error: 'The account or collection changed before this item was updated.' };
          write(state);
          break;
        }
        const item = current?.data ?? current;
        if (!item || item.id !== unit.entity_id) throw new Error('Native item could not be revalidated.');
        const update = buildEquipmentTemplateUpdate(item, state.fields, state.selected_fields);
        const result = await updateItem(unit.entity_id, update);
        if (!isCurrent(state.scope)) {
          state.units[index] = { ...unit, status: 'uncertain', error: 'The account or collection changed while the update was in progress; verify this item before continuing.' };
          write(state);
          break;
        }
        if (result?.error) {
          const status = errorStatus(result.error);
          const outcome = status >= 400 && status < 500 && ![408, 409, 429].includes(status) ? 'failed' : 'uncertain';
          state.units[index] = { ...unit, status: outcome, error: String(result.error.message || result.error) };
          write(state);
          if (outcome === 'uncertain') break;
          continue;
        }
        const verifiedResponse = await getItem(unit.entity_id);
        if (!isCurrent(state.scope)) {
          state.units[index] = { ...unit, status: 'uncertain', error: 'The account or collection changed before the update could be verified.' };
          write(state);
          break;
        }
        const verified = verifiedResponse?.data ?? verifiedResponse;
        if (!verified || verified.id !== unit.entity_id || !unitMatchesExpected(verified, state.fields, state.selected_fields)) {
          state.units[index] = { ...unit, status: 'uncertain', error: 'Homebox did not confirm the selected shared fields.' };
        } else state.units[index] = { ...unit, status: 'succeeded' };
        write(state);
      } catch (error) {
        const status = errorStatus(error);
        const outcome = status >= 400 && status < 500 && ![408, 409, 429].includes(status) ? 'failed' : 'uncertain';
        state.units[index] = { ...unit, status: outcome, error: String(error?.message || error) };
        write(state);
        if (outcome === 'uncertain') break;
      }
    }
    return state;
  }

  return {
    pending: read,
    recover() {
      const state = read();
      if (!state) return state;
      state.units = state.units.map(unit => unit.status === 'in_flight' ? { ...unit, status: 'uncertain' } : unit);
      write(state);
      return state;
    },
    resolveUncertain(entityId, outcome) {
      if (!['succeeded', 'failed'].includes(outcome)) throw new Error('Choose whether the item update succeeded or did not apply.');
      const state = read();
      const index = state?.units?.findIndex(unit => unit.entity_id === entityId && unit.status === 'uncertain') ?? -1;
      if (index < 0) throw new Error('No uncertain item update matches this UUID.');
      state.units[index] = { ...state.units[index], status: outcome, error: undefined };
      write(state);
      return state;
    },
    async apply(input) {
      const { selectedEntityIds, fields, selectedFields } = input || {};
      const ids = [...new Set(selectedEntityIds || [])].map(value => String(value || '').trim()).filter(Boolean);
      const selected = [...new Set(selectedFields || [])];
      if (!ids.length) throw new Error('Select at least one exact item.');
      if (!selected.length) throw new Error('Select at least one shared field to apply.');
      if (!selected.every(field => SHARED_UPDATE_FIELDS.has(field))) throw new Error('Only shared fields can be applied.');
      const prior = read();
      if (prior?.units?.some(unit => unit.status === 'uncertain' || unit.status === 'in_flight')) {
        throw new Error('An item update has an uncertain result and needs manual review.');
      }
      write({ fields: { ...fields, tagIds: Array.isArray(fields.tagIds) ? [...fields.tagIds] : [] }, selected_fields: selected, scope: input.scope, units: ids.map(entity_id => ({ entity_id, status: 'pending' })) });
      return resume();
    },
    resume,
  };
}

export async function listEquipmentTemplates(workshop, includeArchived = false) {
  const context = await workshop.refresh();
  const path = includeArchived ? 'equipment/templates?include_archived=true' : 'equipment/templates';
  return workshop.request(path, undefined, context.identity);
}

export async function saveEquipmentTemplate(workshop, fields, requestKey, sourceEntityId, edit = {}, expected = {}) {
  const context = await workshop.refresh();
  if ((expected.group_id && context.group.id !== expected.group_id) || (expected.user_id && context.user.id !== expected.user_id) || (expected.identity && context.identity !== expected.identity)) {
    throw new Error('The account or collection changed. Switch back to the original context to resume this template save.');
  }
  const body = { request_key: requestKey, fields: equipmentTemplatePayload(fields) };
  if (sourceEntityId) body.source_entity_id = sourceEntityId;
  if (edit.templateId) {
    body.template_id = edit.templateId;
    body.expected_updated_at = edit.expectedUpdatedAt;
  }
  return workshop.request('equipment/templates/save', body, context.identity);
}

/** Preserve a save key and immutable payload until the server confirms the replay. */
export function createEquipmentTemplateSaveFlow({ read, write, clear, save, keyFactory = () => crypto.randomUUID() }) {
  async function resume() {
    const intent = read();
    if (!intent) throw new Error('There is no pending template save.');
    if (intent.rejected) throw new Error('This template save was definitively rejected. Review and explicitly discard it before submitting corrected fields.');
    if (intent.stale_version_conflict) throw new Error('This template changed on the server. Refresh and review the latest template, then explicitly discard this stale save before composing a new one.');
    try {
      const result = await save(intent);
      if (result?.error) throw result.error;
      clear();
      return result;
    } catch (error) {
      const status = errorStatus(error);
      if (isStaleTemplateVersionConflict(error)) {
        write({ ...intent, stale_version_conflict: true, stale_version_message: String(error?.message || error) });
      } else if (status >= 400 && status < 500 && ![408, 409, 429].includes(status)) {
        write({ ...intent, rejected: true, rejection: { status, message: String(error?.message || error) } });
      }
      throw error;
    }
  }
  return {
    pending: read,
    async save(input) {
      const payload = {
        fields: equipmentTemplatePayload(input.fields),
        source_entity_id: input.sourceEntityId || null,
        template_id: input.templateId || null,
        expected_updated_at: input.expectedUpdatedAt || null,
      };
      const digest = stableJSON(payload);
      const previous = read();
      if (previous?.rejected) throw new Error('A template save was definitively rejected. Review the rejection and explicitly discard it before saving corrected fields.');
      if (previous?.stale_version_conflict) throw new Error('A template changed on the server. Refresh and review the latest version, then explicitly discard the stale save first.');
      if (previous && previous.digest !== digest) throw new Error('A template save is awaiting confirmation. Retry or reconcile that exact save first.');
      if (!previous) write({ request_key: keyFactory(), payload, digest, ...(input.scope || {}) });
      return resume();
    },
    resume,
    discardRejected() {
      const pending = read();
      if (!pending?.rejected) throw new Error('Only a definitively rejected template save can be discarded after review.');
      clear();
    },
    discardStaleConflict(confirmedLatestReview = false) {
      const pending = read();
      if (!pending?.stale_version_conflict || confirmedLatestReview !== true) {
        throw new Error('Refresh and review the latest template before discarding a stale-version conflict.');
      }
      clear();
    },
    clearAfterReview() { clear(); },
  };
}

export async function assignCreatedEquipment(workshop, intent) {
  const context = await workshop.refresh();
  if ((intent.group_id && context.group.id !== intent.group_id) || (intent.user_id && context.user.id !== intent.user_id) || (intent.identity && context.identity !== intent.identity)) {
    throw new Error('The account or collection changed. Switch back to the original context to resume this equipment assignment.');
  }
  const body = { request_key: intent.request_key, entity_id: intent.entity_id };
  if (intent.template_id) body.template_id = intent.template_id;
  else body.model_code = intent.model_code;
  return workshop.request('equipment/ids/assign', body, context.identity);
}

export function equipmentTemplateStorageKey(context) {
  return `equipment-create:${context.group.id}:${context.user.id}`;
}

export function equipmentTemplateSaveStorageKey(context) {
  return `equipment-template-save:${context.group.id}:${context.user.id}`;
}

/**
 * Persist intent before native creation. After a successful native response, keep
 * its UUID and assignment key until assignment is confirmed. An uncertain native
 * response stays locked because its UUID is not safe to recreate automatically.
 */
export function createEquipmentCreationFlow({ read, write, clear, assignCreated, completePostCreate = async (_intent, _step) => ({}), keyFactory = () => crypto.randomUUID() }) {
  let creating = false;
  let assigning = false;

  async function resumeAssignment() {
    if (assigning) throw new Error('Equipment ID assignment is already in progress.');
    const intent = read();
    if (!intent || intent.state !== 'assignment_pending' || !intent.entity_id) {
      throw new Error('This native create needs manual review before another item can be created.');
    }
    assigning = true;
    try {
      let state = read();
      state.post_create_steps = state.post_create_steps || [];
      state.post_create_steps = state.post_create_steps.map(step => step.status === 'in_flight' ? { ...step, status: 'uncertain' } : step);
      write(state);
      if (state.post_create_steps.some(step => step.status === 'uncertain')) {
        throw new Error('A photo upload has an uncertain result and needs manual review before continuing.');
      }
      for (let index = 0; index < state.post_create_steps.length; index++) {
        if (state.post_create_steps[index].status !== 'pending') continue;
        const step = state.post_create_steps[index];
        state.post_create_steps[index] = { ...step, status: 'in_flight' };
        write(state);
        try {
          const result = await completePostCreate(state, step);
          if (result?.deferred) {
            state.post_create_steps[index] = { ...step, status: 'pending', error: result.message };
            write(state);
            throw new Error(result.message || 'A queued post-create step needs its original input.');
          }
          if (result?.error) {
            const status = errorStatus(result.error);
            const outcome = status >= 400 && status < 500 && ![408, 409, 429].includes(status) ? 'failed' : 'uncertain';
            state.post_create_steps[index] = { ...step, status: outcome, error: String(result.error.message || result.error) };
            write(state);
            if (outcome === 'uncertain') break;
          } else {
            state.post_create_steps[index] = { ...step, status: 'succeeded', error: undefined };
            write(state);
          }
        } catch (error) {
          if (state.post_create_steps[index].status === 'pending') throw error;
          const status = errorStatus(error);
          const outcome = status >= 400 && status < 500 && ![408, 409, 429].includes(status) ? 'failed' : 'uncertain';
          state.post_create_steps[index] = { ...step, status: outcome, error: String(error?.message || error) };
          write(state);
          if (outcome === 'uncertain') break;
        }
      }
      state = read();
      const incomplete = state.post_create_steps.find(step => step.status !== 'succeeded');
      if (incomplete) throw new Error(incomplete.error || `Post-create step “${incomplete.name || incomplete.key}” needs review.`);
      const assignment = await assignCreated(intent);
      clear();
      return { entity_id: intent.entity_id, assignment };
    } finally {
      assigning = false;
      creating = false;
    }
  }

  function begin({ templateId, modelCode, groupId, userId, identity, entityTypeId, postCreateSteps } = {}) {
    if (creating) throw new Error('Equipment creation is already in progress.');
    if (read()) throw new Error('Review the pending equipment create before creating another item.');
    if (!templateId && !String(modelCode || '').trim()) throw new Error('Enter a model code before creating equipment without a template.');
    creating = true;
    const intent = {
      state: 'native_create_pending', request_key: keyFactory(),
      template_id: templateId || null, model_code: templateId ? null : String(modelCode).trim(),
      group_id: groupId || null, user_id: userId || null, identity: identity || null,
      entity_type_id: entityTypeId || null,
      post_create_steps: (postCreateSteps || []).map(step => ({ ...step, status: 'pending' })),
    };
    write(intent);
    return intent;
  }

  function markNativeUncertain() {
    const intent = read();
    if (intent?.state === 'native_create_pending') write({ ...intent, state: 'native_create_uncertain' });
    creating = false;
  }

  function markNativeRejected(error) {
    const status = errorStatus(error);
    if (status >= 400 && status < 500 && ![408, 409, 429].includes(status)) {
      clear();
      creating = false;
      return null;
    }
    markNativeUncertain();
    return read();
  }

  function recordCreated(entityId) {
    const intent = read();
    if (!intent || intent.state !== 'native_create_pending' || !entityId) {
      throw new Error('The native create intent is missing; review inventory before continuing.');
    }
    write({ ...intent, state: 'assignment_pending', entity_id: entityId });
  }

  function reconcileCreated(entityId) {
    const intent = read();
    if (!intent || intent.state !== 'native_create_uncertain' || !String(entityId || '').trim()) {
      throw new Error('Confirm an uncertain native create and provide the found item UUID.');
    }
    write({ ...intent, state: 'assignment_pending', entity_id: String(entityId).trim() });
    return read();
  }

  function confirmNoNativeCreate() {
    const intent = read();
    if (!intent || intent.state !== 'native_create_uncertain') throw new Error('Only an uncertain native create can be cleared after review.');
    clear();
  }

  function recover() {
    const intent = read();
    if (intent?.state === 'native_create_pending') {
      const recovered = { ...intent, state: 'native_create_uncertain' };
      write(recovered);
      creating = false;
      return recovered;
    }
    return intent;
  }

  function reconcilePostCreateStep(stepKey, uploaded) {
    const state = read();
    const index = state?.post_create_steps?.findIndex(step => step.key === stepKey && step.status === 'uncertain') ?? -1;
    if (index < 0) throw new Error('No uncertain post-create step matches this item.');
    state.post_create_steps[index] = { ...state.post_create_steps[index], status: uploaded ? 'succeeded' : 'failed', error: undefined };
    write(state);
    return state;
  }

  async function retryFailedPostCreate() {
    const state = read();
    if (!state || state.state !== 'assignment_pending') throw new Error('There is no created item awaiting completion.');
    write({ ...state, post_create_steps: state.post_create_steps.map(step => step.status === 'failed' ? { ...step, status: 'pending', error: undefined } : step) });
    return resumeAssignment();
  }

  return {
    pending: read,
    recover,
    begin,
    markNativeUncertain,
    markNativeRejected,
    recordCreated,
    reconcileCreated,
    confirmNoNativeCreate,
    reconcilePostCreateStep,
    retryFailedPostCreate,
    resumeAssignment,
    async create(createNative, product) {
      const intent = begin(product);
      try {
        let entity;
        try {
          entity = await createNative();
        } catch (error) {
          markNativeUncertain();
          throw error;
        }
        if (!entity?.id) {
          markNativeUncertain();
          throw new Error('The native create response did not include an item ID. Review inventory before continuing.');
        }
        recordCreated(entity.id);
        const result = await resumeAssignment();
        return { entity, ...result };
      } finally {
        creating = false;
      }
    },
  };
}


/** Stable, retryable archive/restore requests. The server records the lifecycle request key. */
export function createEquipmentTemplateLifecycleFlow({ read, write, clear, request, keyFactory = () => crypto.randomUUID() }) {
  async function resume() {
    const intent = read();
    if (!intent) throw new Error('There is no pending template archive or restore.');
    const result = await request(intent.action, intent.template_id, intent.request_key);
    if (result?.error) throw result.error;
    clear();
    return result;
  }
  return {
    pending: read,
    resume,
    async change(action, templateId) {
      if (!['archive', 'restore'].includes(action)) throw new Error('Choose archive or restore.');
      const current = read();
      if (current && (current.action !== action || current.template_id !== templateId)) {
        throw new Error('A different template lifecycle request is awaiting confirmation. Retry it first.');
      }
      if (!current) write({ action, template_id: templateId, request_key: keyFactory() });
      return resume();
    },
  };
}
