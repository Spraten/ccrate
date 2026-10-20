const clone = value => JSON.parse(JSON.stringify(value));

export function normalizeItemActionStatus(result) {
  const rows = Array.isArray(result) ? result : result?.items;
  if (!Array.isArray(rows)) throw new Error('Equipment status could not be confirmed.');
  return rows;
}

export function createItemActionState() {
  return {
    phase: 'closed', request: null, itemIds: [], status: [], draft: {}, error: '', discardPrompt: false,
    verificationId: null, requiredItems: [], verifiedItems: [], kitVersions: {}, requestKey: null,
    owner: null, dirty: false, receipt: null,
  };
}

export function createItemActionController({ request: transport, getContext, uuid, onChanged = () => {}, storage = globalThis.localStorage, state: sharedState }) {
  const state = sharedState || createItemActionState();
  let origin = null;
  let originFallback = null;
  let onState = () => {};
  let generation = 0;
  let pendingFailure = '';
  const snapshot = () => clone(state);
  const publish = () => onState(snapshot());
  const owner = context => context ? `${context.group.id}:${context.user.id}:${context.identity}` : '';
  const current = (ticket, expectedOwner) => ticket === generation && state.owner === expectedOwner && owner(getContext()) === expectedOwner;
  function pendingStorageKey(ctx) { return `workshop-item-action:${ctx.group.id}:${ctx.user.id}`; }
  function pendingRows(ctx) {
    if (!storage || typeof storage.getItem !== 'function' || typeof storage.setItem !== 'function') {
      pendingFailure = 'Saved item-action storage is unavailable. Recovery is required before starting or confirming actions.';
      throw new Error(pendingFailure);
    }
    try {
      const raw = storage.getItem(pendingStorageKey(ctx));
      if (raw === null || raw === '') { pendingFailure = ''; return []; }
      const rows = JSON.parse(raw);
      if (!Array.isArray(rows) || rows.some(row => !row || typeof row !== 'object' || typeof row.request_key !== 'string')) throw new Error('Saved item-action storage is malformed.');
      pendingFailure = '';
      return rows;
    } catch (error) {
      pendingFailure = `Saved item-action storage could not be read safely: ${error.message || 'invalid data'}`;
      throw new Error(pendingFailure);
    }
  }
  function savePending(intent) {
    const ctx = getContext();
    if (!ctx) throw new Error('Reload before continuing this action.');
    const rows = pendingRows(ctx).filter(row => row.request_key !== intent.request_key);
    rows.push({ ...clone(intent), identity: ctx.identity, group_id: ctx.group.id, user_id: ctx.user.id });
    try { storage.setItem(pendingStorageKey(ctx), JSON.stringify(rows)); }
    catch (error) { pendingFailure = `Saved item-action storage could not be updated: ${error.message || 'unavailable'}`; throw new Error(pendingFailure); }
  }
  function clearPending(key) {
    const ctx = getContext();
    if (!ctx) return;
    try { storage.setItem(pendingStorageKey(ctx), JSON.stringify(pendingRows(ctx).filter(row => row.request_key !== key))); }
    catch (error) { pendingFailure = `Saved item-action storage could not be updated: ${error.message || 'unavailable'}`; throw new Error(pendingFailure); }
  }
  function pendingActions() {
    const ctx = getContext();
    if (!ctx) return [];
    try { return pendingRows(ctx).filter(row => row.identity === ctx.identity && row.group_id === ctx.group.id && row.user_id === ctx.user.id); }
    catch { return []; }
  }
  function pendingError() { const ctx = getContext(); if (!ctx) return ''; try { pendingRows(ctx); return ''; } catch { return pendingFailure; } }
  function resetSensitive() {
    generation++;
    Object.assign(state, {
      phase: 'closed', request: null, itemIds: [], status: [], draft: {}, error: '', discardPrompt: false,
      verificationId: null, requiredItems: [], verifiedItems: [], kitVersions: {}, requestKey: null,
      owner: null, dirty: false, receipt: null,
    });
    origin = null;
    publish();
  }
  function bindContext(ctx) {
    if (state.owner && state.owner !== owner(ctx)) {
      resetSensitive();
      return false;
    }
    return true;
  }
  async function open(actionRequest, trigger = null) {
    const ctx = getContext();
    if (!ctx) throw new Error('Sign in and select a collection before using item actions.');
    const existing = pendingRows(ctx).filter(row => row.identity === ctx.identity && row.group_id === ctx.group.id && row.user_id === ctx.user.id);
    if (existing.length) throw new Error('An earlier item action is unresolved. Check its saved result before starting another action.');
    const ids = actionRequest.kind === 'checkout' && Array.isArray(actionRequest.itemIds)
      ? [...new Set(actionRequest.itemIds)] : actionRequest.itemId ? [actionRequest.itemId] : [];
    if (!ids.length || ids.length > 50) throw new Error('Choose between 1 and 50 exact equipment items.');
    const ticket = ++generation, expectedOwner = owner(ctx);
    Object.assign(state, { phase: 'loading', request: clone(actionRequest), itemIds: ids, status: [], draft: {}, error: '', discardPrompt: false,
      verificationId: null, requiredItems: [], verifiedItems: [], kitVersions: {}, requestKey: null, owner: expectedOwner, dirty: false, receipt: null });
    origin = trigger || (typeof document !== 'undefined' ? document.activeElement : null);
    originFallback = origin?.closest?.("[data-item-action-focus-fallback]") || null;
    publish();
    try {
      if (actionRequest.kind === 'cart') {
        const cart = await api('checkout-cart');
        if (!current(ticket, expectedOwner)) return false;
        state.itemIds = [...new Set([...(cart.items || []), ...ids])];
        if (state.itemIds.length > 50) throw new Error('A cart can contain at most 50 items.');
        state.request.cartRevision = cart.revision;
        state.draft.notes = { ...(cart.notes || {}) };
      } else if (actionRequest.source === 'cart' || actionRequest.cartRevision !== undefined) {
        const cart = await api('checkout-cart');
        if (!current(ticket, expectedOwner)) return false;
        if (cart.revision !== actionRequest.cartRevision || JSON.stringify(cart.items) !== JSON.stringify(ids)) throw new Error('Your cart changed. Review its exact selection before continuing.');
        state.draft.notes = clone(cart.notes || {});
      }
      const rows = normalizeItemActionStatus(await api(`item-actions/status?ids=${encodeURIComponent(state.itemIds.join(','))}`));
      if (!current(ticket, expectedOwner)) return false;
      if (rows.length !== state.itemIds.length || rows.some((row, index) => row.id !== state.itemIds[index])) throw new Error('Equipment status could not be confirmed.');
      state.status = rows;
      if (actionRequest.kind === 'checkin') {
        const [entityResult, kitResult] = await Promise.all([
          api(`entity?id=${encodeURIComponent(ids[0])}`), api(`kit?id=${encodeURIComponent(ids[0])}`),
        ]);
        if (!current(ticket, expectedOwner)) return false;
        const entity = entityResult?.entity || entityResult;
        state.draft.destination_id = entity?.parent?.id || '';
        state.draft.kit_versions = kitResult?.versions || {};
        state.draft.verified = kitResult?.kit ? [] : [...ids];
        state.draft.kit_items = kitResult?.kit ? (kitResult.entities || []).map(row => ({ id: row.id, name: row.name, parent_id: row.parent?.id || row.parent_id || '' })) : [];
      }
      if (actionRequest.kind === 'checkout' && rows.some(row => row.availability !== 'available')) {
        throw new Error('One or more selected items are unavailable or have unknown status. Review the whole selection.');
      }
      if (actionRequest.kind === 'checkin' && rows.some(row => row.availability !== 'checked_out' || !row.can_checkin)) {
        throw new Error('You are not authorized to return every selected item, or its loan status changed.');
      }
      state.phase = 'review';
      publish();
    } catch (error) {
      if (!current(ticket, expectedOwner)) return false;
      state.phase = 'error'; state.error = error.message || 'The action could not be loaded.'; publish();
      throw error;
    }
  }
  async function api(path, body) {
    const ctx = getContext();
    if (!bindContext(ctx)) throw new Error('Your account or collection changed.');
    return transport(path, body, ctx.identity);
  }
  async function verifyBadge(badgeCode) {
    if (!['review', 'error'].includes(state.phase) || state.request?.kind !== 'checkout') throw new Error('Review checkout before scanning a badge.');
    if (state.status.some(row => row.availability !== 'available')) throw new Error('Unknown or unavailable status blocks checkout.');
    const ticket = ++generation, expectedOwner = state.owner;
    state.phase = 'verifying'; state.error = ''; publish();
    try {
      const proof = await api('item-actions/verify-badge', { attempt_id: uuid(), badge_code: badgeCode, item_ids: state.itemIds });
      if (!current(ticket, expectedOwner)) return null;
      state.verificationId = proof.verification_id; state.requiredItems = proof.required_items || []; state.verifiedItems = [];
      state.kitVersions = proof.kit_versions || {}; state.phase = 'review'; publish(); return proof;
    } catch (error) {
      if (!current(ticket, expectedOwner)) return null;
      if (error.status === 409 && state.verificationId) {
        state.verificationId = null; state.requiredItems = []; state.verifiedItems = []; state.kitVersions = {};
        state.phase = 'review'; state.error = error.message || 'Badge proof expired. Scan the badge again.';
      } else { state.phase = 'error'; state.error = error.message; }
      publish(); throw error;
    }
  }
  async function verifyItem(code) {
    if (!state.verificationId) throw new Error('Scan the matching badge first.');
    const ticket = ++generation, expectedOwner = state.owner;
    state.phase = 'verifying'; publish();
    try {
      const result = await api('item-actions/verify-item', { verification_id: state.verificationId, code });
      if (!current(ticket, expectedOwner)) return null;
      state.verifiedItems = result.verified_items || [];
      state.requiredItems = result.required_items || state.requiredItems;
      state.phase = 'review'; state.error = ''; publish(); return result;
    } catch (error) {
      if (!current(ticket, expectedOwner)) return null;
      if (error.status === 409) {
        state.verificationId = null; state.requiredItems = []; state.verifiedItems = []; state.kitVersions = {};
        state.phase = 'review'; state.error = error.message || 'The proof expired or the kit changed. Scan a fresh badge and verify the current items.';
      } else { state.phase = 'error'; state.error = error.message; }
      publish(); throw error;
    }
  }
  async function verifyReturnItem(code) {
    if (state.request?.kind !== 'checkin' || !state.draft.kit_items?.length) throw new Error('No kit scan is required for this return.');
    if (!String(code || '').trim()) throw new Error('Scan a native kit component code.');
    const ticket = ++generation, expectedOwner = state.owner;
    state.phase = 'verifying'; state.error = ''; publish();
    try {
      const result = await api('workshop/resolve', { code });
      if (!current(ticket, expectedOwner)) return null;
      const id = result?.entity_id;
      if (result?.kind !== 'entity' || !state.draft.kit_items.some(row => row.id === id)) throw new Error('Scan a component from this exact kit.');
      const verified = new Set(state.draft.verified || []); verified.add(id);
      state.draft.verified = [...verified]; state.dirty = true; state.phase = 'review'; publish();
      return result;
    } catch (error) { if (!current(ticket, expectedOwner)) return null; state.phase = 'error'; state.error = error.message; publish(); throw error; }
  }
  function setNote(itemId, value) {
    if (!state.itemIds.includes(itemId)) throw new Error('Notes must belong to a selected item.');
    if (Array.from(String(value)).length > 1000) throw new Error('Notes must be at most 1,000 characters.');
    state.draft.notes ||= {}; state.draft.notes[itemId] = value; state.dirty = true; publish();
  }
  function setDraft(values) { Object.assign(state.draft, clone(values)); state.dirty = true; publish(); }
  async function changeSelection(ids, revision) {
    if (!['review', 'error'].includes(state.phase)) throw new Error('Selection can change only while reviewing this action.');
    const next = [...new Set(ids)];
    if (!next.length || next.length > 50) throw new Error('Choose between 1 and 50 exact equipment items.');
    const changed = next.length !== state.itemIds.length || next.some((id, index) => id !== state.itemIds[index]) || revision !== state.request?.cartRevision;
    let ticket = generation, expectedOwner = state.owner;
    if (changed) {
      const previousProof = state.verificationId;
      if (previousProof) void api('item-actions/cancel', { verification_id: previousProof }).catch(() => {});
      state.itemIds = next;
      state.request.cartRevision = revision;
      state.verificationId = null; state.requiredItems = []; state.verifiedItems = []; state.kitVersions = {};
      state.requestKey = null; state.dirty = true; state.phase = 'review';
      state.status = next.map(id => ({ id, availability: 'unknown' }));
      ticket = ++generation; expectedOwner = state.owner;
    }
    publish();
    if (changed) {
      state.phase = 'loading'; publish();
      try {
        const rows = normalizeItemActionStatus(await api(`item-actions/status?ids=${encodeURIComponent(next.join(','))}`));
        if (!current(ticket, expectedOwner)) return changed;
        if (!Array.isArray(rows) || rows.length !== next.length || rows.some((row, index) => row.id !== next[index])) throw new Error('The selected equipment could not be confirmed.');
        state.status = rows; state.phase = 'review'; state.error = '';
        if (state.request?.kind === 'checkout' && rows.some(row => row.availability !== 'available')) state.error = 'One or more selected items are unavailable or have unknown status.';
      } catch (error) { if (!current(ticket, expectedOwner)) return changed; state.phase = 'error'; state.error = error.message; }
      publish();
    }
    return changed;
  }
  function normalizedNotes() {
    const source = state.draft.notes || (state.draft.note ? { [state.request?.itemId || state.itemIds[0]]: state.draft.note } : {});
    return Object.fromEntries(Object.entries(source).filter(([id, value]) => state.itemIds.includes(id) && typeof value === 'string' && value.trim()).map(([id, value]) => [id, value.trim()]));
  }
  function affectedItemIds(payload = null) {
    const ids = [...state.itemIds];
    if (state.request?.kind === 'checkout') ids.push(...(state.requiredItems || []), ...(payload?.assets || []));
    if (state.request?.kind === 'checkin') {
      ids.push(...(state.draft.kit_items || []).map(row => row.id));
      ids.push(...(payload?.targets || []).map(row => row.entity_id));
    }
    return [...new Set(ids.filter(id => typeof id === 'string' && id))];
  }
  function actionIntent() {
    const key = state.requestKey || uuid(); state.requestKey = key;
    const action = state.request?.kind;
    if (action === 'checkout') {
      if (!state.verificationId) throw new Error('Scan the matching badge before confirming checkout.');
      if (state.requiredItems.some(id => !state.verifiedItems.includes(id))) throw new Error('Physically verify every required item and kit component.');
      const payload = { verification_id: state.verificationId, assets: state.requiredItems, notes: normalizedNotes(), request_key: key };
      if (state.request.cartRevision !== undefined) payload.cart = { revision: state.request.cartRevision, items: state.itemIds, notes: normalizedNotes() };
      return ['item-actions/checkout', payload];
    }
    if (action === 'checkin') {
      if (state.draft.kit_items?.some(row => !(state.draft.verified || []).includes(row.id))) throw new Error('Physically verify every component in the current kit.');
      if (state.draft.problem && !String(state.draft.problem).trim()) throw new Error('Describe the problem before reporting it.');
      const returnIds = state.draft.kit_items?.length ? [...new Set(state.draft.kit_items.map(row => row.id))] : state.itemIds;
      const targets = returnIds.map(entity_id => entity_id === state.itemIds[0] ? ({ entity_id,
        ...(state.draft.destination_id ? { destination_id: state.draft.destination_id } : {}),
        ...(state.draft.return_note?.trim() ? { return_note: state.draft.return_note.trim() } : {}),
        ...(state.draft.problem?.trim() ? { problem_description: state.draft.problem.trim() } : {}),
      }) : ({ entity_id }));
      return ['item-actions/checkin', { targets, verified: state.draft.verified || [], kit_versions: state.draft.kit_versions || {}, request_key: key }];
    }
    if (action === 'note') {
      const note = String(state.draft.note || '').trim();
      if (!note) throw new Error('A note is required.');
      return ['item-actions/note', { entity_id: state.itemIds[0], note, request_key: key }];
    }
    if (action === 'cart') {
      return ['checkout-cart', { items: state.itemIds, revision: state.request.cartRevision ?? 0, request_key: key, notes: normalizedNotes() }];
    }
    throw new Error('Choose a supported item action.');
  }
  async function confirm() {
    if (!['review', 'error'].includes(state.phase)) throw new Error('Wait for the current action to finish.');
    const [path, payload] = actionIntent();
    const intent = { path, request_key: payload.request_key, payload, kind: state.request.kind, item_ids: [...state.itemIds] };
    const ticket = ++generation, expectedOwner = state.owner;
    try { savePending(intent); }
    catch (error) { state.phase = 'error'; state.error = error.message; publish(); throw error; }
    state.phase = 'submitting'; state.error = ''; publish();
    let writeStarted = false;
    try {
      if (state.request.kind === 'checkout' || state.request.kind === 'checkin') {
        const idsToRefresh = state.request.kind === 'checkout' ? state.requiredItems : state.itemIds;
        const fresh = normalizeItemActionStatus(await api(`item-actions/status?ids=${encodeURIComponent(idsToRefresh.join(','))}`));
        if (!current(ticket, expectedOwner)) return null;
        if (fresh.length !== idsToRefresh.length || fresh.some((row, index) => row.id !== idsToRefresh[index] || row.availability !== (state.request.kind === 'checkout' ? 'available' : 'checked_out'))) {
          throw Object.assign(new Error('Equipment status changed. Review the entire selection.'), { status: 409, definitive: true });
        }
        state.status = fresh;
      }
      writeStarted = true;
      const result = await api(path, payload);
      if (!current(ticket, expectedOwner)) return null;
      const cartReceipt = state.request.kind === 'cart' && Number.isSafeInteger(result?.revision) && Array.isArray(result?.items) && result?.notes && typeof result.notes === 'object';
      if (!cartReceipt && !['completed', 'confirmed', 'succeeded'].includes(result?.status)) {
        throw new Error(result?.status === 'review' ? 'The action needs review. Check its saved result before continuing.' : 'The action did not return a confirmed receipt. Check its saved result before continuing.');
      }
      clearPending(payload.request_key);
      state.verificationId = null;
      state.receipt = result; state.phase = 'success'; state.dirty = false; publish();
      const itemIds = affectedItemIds(payload);
      onChanged({ kind: state.request.kind, itemIds, receiptId: result.id || result.operation_id, cartRevision: result.cart?.revision ?? (cartReceipt ? result.revision : undefined) });
      close(true);
      return result;
    } catch (error) {
      if (!current(ticket, expectedOwner)) return null;
      const conflict = error.status === 409;
      if (conflict && writeStarted) {
        state.phase = 'loading'; state.error = ''; publish();
        let journal;
        try { journal = await api('operation/status', { request_key: payload.request_key }); }
        catch { if (!current(ticket, expectedOwner)) return null; state.phase = 'uncertain'; state.error = error.message || 'The saved result is unresolved.'; publish(); throw error; }
        if (!current(ticket, expectedOwner)) return null;
        if (['completed', 'confirmed', 'succeeded'].includes(journal?.status)) {
          clearPending(payload.request_key); state.receipt = journal.result || journal; state.phase = 'success'; state.dirty = false; publish();
          onChanged({ kind: state.request.kind, itemIds: affectedItemIds(payload), receiptId: journal.id || journal.result?.id }); close(true);
          return journal.result || journal;
        }
        if (journal?.status !== 'not_started') {
          state.phase = 'uncertain'; state.error = journal?.message || error.message || 'The saved result is still unresolved. Do not submit again.'; publish(); throw error;
        }
        clearPending(payload.request_key);
        state.requestKey = null; state.verificationId = null; state.requiredItems = []; state.verifiedItems = []; state.kitVersions = {};
        state.phase = 'loading'; publish();
        try {
          const latest = normalizeItemActionStatus(await api(`item-actions/status?ids=${encodeURIComponent(state.itemIds.join(','))}`));
          if (!current(ticket, expectedOwner)) return null;
          if (latest.length !== state.itemIds.length || latest.some((row, index) => row.id !== state.itemIds[index])) throw new Error('The selected equipment status could not be refreshed.');
          state.status = latest;
        } catch { if (!current(ticket, expectedOwner)) return null; state.status = state.itemIds.map(id => ({ id, availability: 'unknown' })); }
        state.phase = 'review';
      } else if (conflict && error.definitive && !writeStarted) {
        clearPending(payload.request_key);
        state.requestKey = null; state.verificationId = null; state.requiredItems = []; state.verifiedItems = []; state.kitVersions = {};
        try {
          const latest = normalizeItemActionStatus(await api(`item-actions/status?ids=${encodeURIComponent(state.itemIds.join(','))}`));
          if (!current(ticket, expectedOwner)) return null;
          if (latest.length !== state.itemIds.length || latest.some((row, index) => row.id !== state.itemIds[index])) throw new Error('The selected equipment status could not be refreshed.');
          state.status = latest;
        } catch { if (!current(ticket, expectedOwner)) return null; state.status = state.itemIds.map(id => ({ id, availability: 'unknown' })); }
        state.phase = 'review';
      } else {
        if (error.definitive || [400,403,404].includes(error.status)) clearPending(payload.request_key);
        state.phase = error.definitive || [400,403,404].includes(error.status) ? 'error' : 'uncertain';
      }
      state.error = error.message || 'No confirmation received. Check the saved result before continuing.'; publish(); throw error;
    }
  }
  async function reconcile() {
    const ctx = getContext();
    const row = pendingRows(ctx).find(value => value.request_key === state.requestKey && value.identity === ctx.identity && value.group_id === ctx.group.id && value.user_id === ctx.user.id);
    if (!row) throw new Error('No saved request is available for this account and collection.');
    const ticket = ++generation, expectedOwner = state.owner;
    state.phase = 'loading'; state.error = ''; publish();
    try {
      const result = await api('operation/status', { request_key: row.request_key });
      if (!current(ticket, expectedOwner)) return null;
      if (['completed', 'confirmed', 'succeeded'].includes(result.status)) {
        clearPending(row.request_key); state.receipt = result.result || result; state.phase = 'success'; state.dirty = false; publish();
        onChanged({ kind: state.request?.kind || 'checkout', itemIds: affectedItemIds(row.payload), receiptId: result.id }); close(true);
      } else if (result.status === 'not_started') {
        clearPending(row.request_key); state.requestKey = null; state.verificationId = null; state.requiredItems = []; state.verifiedItems = []; state.kitVersions = {};
        // A reload recovery starts with unknown status. Refresh the selected
        // units before making a retry available, while retaining the user's
        // draft so they can review and resubmit it deliberately.
        try {
          const rows = normalizeItemActionStatus(await api(`item-actions/status?ids=${encodeURIComponent(state.itemIds.join(','))}`));
          if (!current(ticket, expectedOwner)) return null;
          if (rows.length !== state.itemIds.length || rows.some((value, index) => value.id !== state.itemIds[index])) throw new Error('Equipment status could not be confirmed.');
          state.status = rows;
          state.phase = 'review';
          state.error = result.message || 'The server confirmed the action did not start. Review current status before making a new request.';
        } catch (refreshError) {
          if (!current(ticket, expectedOwner)) return null;
          state.status = state.itemIds.map(id => ({ id, availability: 'unknown' }));
          state.phase = 'review';
          state.error = `The action did not start, but current equipment status could not be confirmed: ${refreshError.message || 'unknown error'}`;
        }
        state.dirty = true; publish();
      } else { state.phase = 'uncertain'; state.error = result.message || 'The saved result is still unresolved. Do not submit again.'; publish(); }
      return result;
    } catch (error) { if (!current(ticket, expectedOwner)) return null; state.phase = 'uncertain'; state.error = error.message; publish(); throw error; }
  }
  function recoverPending(row) {
    const ctx = getContext();
    if (!ctx || !row || row.identity !== ctx.identity || row.group_id !== ctx.group.id || row.user_id !== ctx.user.id || !row.request_key || !Array.isArray(row.item_ids)) {
      throw new Error('This saved action belongs to a different account or collection.');
    }
    const stored = pendingRows(ctx).find(value => value.request_key === row.request_key && value.identity === ctx.identity && value.group_id === ctx.group.id && value.user_id === ctx.user.id);
    if (!stored) throw new Error('This saved action is no longer stored. Refresh recovery before continuing.');
    row = stored;
    const kind = row.kind;
    if (!['checkout', 'checkin', 'cart', 'note'].includes(kind)) throw new Error('This saved action has an unsupported type.');
    state.phase = 'uncertain';
    state.request = { kind, itemIds: [...row.item_ids], source: 'recovery', ...(row.payload?.cart ? { cartRevision: row.payload.cart.revision } : {}) };
    state.itemIds = [...row.item_ids]; state.status = state.itemIds.map(id => ({ id, availability: 'unknown' }));
    state.draft = kind === 'checkout' || kind === 'cart' ? { notes: clone(row.payload?.notes || {}) }
      : kind === 'note' ? { note: row.payload?.note || '' }
        : kind === 'checkin' ? {
          destination_id: row.payload?.targets?.[0]?.destination_id || '',
          return_note: row.payload?.targets?.[0]?.return_note || '',
          problem: row.payload?.targets?.[0]?.problem_description || '',
          verified: clone(row.payload?.verified || []), kit_versions: clone(row.payload?.kit_versions || {}),
        } : {};
    state.requestKey = row.request_key; state.owner = owner(ctx); state.verificationId = null;
    state.requiredItems = []; state.verifiedItems = []; state.kitVersions = {}; state.dirty = true;
    state.error = 'This action has no confirmed result yet. Check its saved result before continuing.';
    state.receipt = null; state.discardPrompt = false; origin = null; originFallback = null; publish();
  }
  function close(force = false) {
    if (state.phase === 'submitting' || state.phase === 'verifying') return false;
    if (state.phase === 'uncertain') return false;
    if (!force && state.dirty) { state.discardPrompt = true; publish(); return false; }
    const trigger = origin;
    const fallback = originFallback;
    generation++;
    const proofId = state.verificationId;
    if (proofId && state.phase !== 'uncertain' && state.phase !== 'submitting') void api('item-actions/cancel', { verification_id: proofId }).catch(() => {});
    Object.assign(state, { phase: 'closed', request: null, itemIds: [], status: [], draft: {}, error: '', discardPrompt: false,
      verificationId: null, requiredItems: [], verifiedItems: [], kitVersions: {}, requestKey: null, owner: null, dirty: false, receipt: null });
    origin = null; originFallback = null; publish();
    queueMicrotask(() => {
      const target = trigger?.isConnected ? trigger : fallback;
      if (target?.isConnected && typeof target.focus === 'function') target.focus();
    });
    return true;
  }
  function discard() { state.dirty = false; state.discardPrompt = false; return close(true); }
  function syncContext() { return bindContext(getContext()); }
  return { state, snapshot, open, verifyBadge, verifyItem, verifyReturnItem, setNote, setDraft, changeSelection, confirm, reconcile, recoverPending, pendingActions, pendingError, close, discard, syncContext, resetContext: resetSensitive, setStateListener(listener) { onState = listener || (() => {}); } };
}
