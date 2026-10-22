(() => {
  const host = document.querySelector('#return-ui');
  if (!host) return;

  const state = {
    items: [], key: null, reviewed: false, sending: false, uncertain: false, cancelled: false,
    receipt: null, receiptSession: null, operationSession: null, epoch: 0, preserved: false, reviewView: false
  };
  const el = (tag, text = '') => { const node = document.createElement(tag); node.textContent = text; return node; };
  function addItemPreview(container,item){const attachment=item?.thumbnailId||item?.imageId;const preview=el('div',attachment?'':'No photo');preview.className='item-preview'+(attachment?'':' item-preview-empty');if(attachment){const image=document.createElement('img');image.src=`/api/file?entity=${encodeURIComponent(item.id)}&attachment=${encodeURIComponent(attachment)}`;image.alt=`Photo of ${item.name||'item'}`;image.loading='lazy';image.addEventListener('error',()=>{preview.replaceChildren(el('span','No photo'));preview.classList.add('item-preview-empty');},{once:true});preview.append(image);}container.append(preview);}
  const context = () => ({
    generation: window.checkoutSession?.generation ?? null,
    instance: window.checkoutSession?.instance ?? null,
    authenticated: window.checkoutSession?.authenticated ?? (window.checkoutSession?.generation != null)
  });
  const sameSession = captured => captured?.generation != null && captured.generation === context().generation && captured.instance === context().instance;
  const valid = captured => Boolean(captured?.authenticated && sameSession(captured) && context().authenticated);
  const current = (captured, epoch, allowEnded = false) => epoch === state.epoch && sameSession(captured) &&
    (valid(captured) || (allowEnded && state.preserved));
  const request = async (path, body) => {
    const response = await fetch(path, {
      method: body ? 'POST' : 'GET',
      headers: {
        'X-Homebox-Client': window.touchscreenClientId || localStorage.getItem('ccrate-touchscreen-client'),
        ...(body ? { 'Content-Type': 'application/json' } : {})
      },
      body: body ? JSON.stringify(body) : undefined
    });
    const data = await response.json();
    if (!response.ok) { const reference = typeof data.request_id === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(data.request_id) ? ` · Reference: ${data.request_id}` : ''; const error = Error((data.error || data.reason || 'Request failed') + reference); error.status = response.status; throw error; }
    return data;
  };

  function button(label, action) {
    const node = el('button', label);
    node.type = 'button';
    node.addEventListener('click', action);
    host.append(node);
    return node;
  }

  function render(message = '') {
    host.replaceChildren();
    if (state.receipt) {
      host.append(el('h3', 'Return complete'), el('p', `Receipt ${state.receipt.id || ''} · ${state.receipt.count ?? state.items.length} item(s)`));
      button('Done', () => window.dispatchEvent(new CustomEvent('ccrate-flow-done', { detail: state.receiptSession })));
      return;
    }
    host.append(el('h3', 'Return equipment'));
    if (state.cancelled) { host.append(el('p', 'Cancelling…')); return; }
    const captured = state.operationSession;
    const allowed = valid(context()) || (state.preserved && sameSession(captured));
    if (!allowed) { host.append(el('p', 'Scan your member badge first.')); return; }
    if (state.reviewView) {
      host.append(el('h3', 'Review return')); if (message) host.append(el('p', message));
      for (const item of state.items) { const summary = el('article'), details=el('div'); summary.className='item-preview-card'; details.className='item-preview-details'; addItemPreview(summary,item.root); details.append(el('strong', item.root.name || item.root.id)); if (item.manifest?.length) details.append(el('p', 'Kit manifest: ' + item.manifest.join(', '))); details.append(el('p', `Condition: ${item.condition || 'Keep recorded condition'} · Return location: ${item.availability.get(item.root.id)?.location?.name || 'Assigned location'}`)); if (item.issueNote) details.append(el('p', `Issue note: ${item.issueNote}`)); if (item.note) details.append(el('p', `Return note: ${item.note}`)); for (const [id,note] of Object.entries(item.componentNotes||{})) details.append(el('p', `Component note (${id}): ${note}`)); summary.append(details); host.append(summary); }
      if (state.uncertain) { host.append(el('p', 'Outcome uncertain. Check status; do not confirm again.')); button('Check saved result', recoverReturn); window.setKioskCancelAllowed?.('return',false); } else { if (state.sending) host.append(el('p', 'Saving return…')); else button('Back to items', () => { state.epoch++; state.reviewView = false; render(); }); const confirm = button('Confirm return', confirmReturn); confirm.disabled = state.sending; window.setKioskCancelAllowed?.('return',!state.sending&&!state.cancelled); }
      return;
    }
    window.setKioskCancelAllowed?.('return',!state.sending&&!state.uncertain&&!state.cancelled);

    const status = el('p', message);
    host.append(status);
    const search = el('input'); search.placeholder = 'Search by name or full ID'; search.setAttribute('aria-label', 'Search inventory'); host.append(search);
    let candidate = null, lookupEpoch = 0, searchTimer = null;
    const searchStatus = el('p'); searchStatus.setAttribute('role', 'status'); host.append(searchStatus);
    const results = el('div'); host.append(results);
    search.addEventListener('input', () => {
      const q = search.value.trim(), lookup = ++lookupEpoch, session = context(), epoch = state.epoch;
      candidate = null;
      clearTimeout(searchTimer);
      if (q.length < 2 || !valid(session)) { results.replaceChildren(); searchStatus.textContent = q ? 'Enter at least two characters to search.' : ''; return; }
      searchStatus.textContent = 'Searching…';
      searchTimer = setTimeout(async () => { try {
        const data = await request('/api/inventory?q=' + encodeURIComponent(q));
        if (lookup !== lookupEpoch || !current(session, epoch)) return;
        const items = Array.isArray(data) ? data : data.items || [];
        const matches = items.filter(item => !item.archived && !item.archivedAt && !item.isLocation);
        results.replaceChildren();
        if (!matches.length) { searchStatus.textContent = 'No matching equipment.'; return; }
        searchStatus.textContent = `${Math.min(matches.length, 10)} result(s) shown.`;
        for (const item of matches.slice(0, 10)) {
          const choice = el('button', item.name || item.id); choice.type = 'button';
          choice.addEventListener('click', () => {
            if (lookup !== lookupEpoch || !current(session, epoch)) return;
            candidate = item; search.value = `${item.name || item.id} — scan physical code`; results.replaceChildren();
            searchStatus.textContent = 'Candidate selected. Scan its physical code.';
          });
          results.append(choice);
        }
        if (matches.length > 10) searchStatus.textContent = 'Showing 10 results. Refine your search to see more.';
      } catch (error) { if (lookup === lookupEpoch && current(session, epoch)) searchStatus.textContent = 'Search unavailable: ' + error.message; } }, 200);
    });

    const scan = el('input'); scan.placeholder = 'Scan item barcode'; scan.setAttribute('aria-label', 'Scan item barcode');
    const add = el('button', 'Verify scan and add'); add.type = 'button';
    scan.addEventListener('keydown', event => {
      if (event.key === 'Enter') { event.preventDefault(); add.click(); }
    });
    add.addEventListener('click', async () => {
      const session = context(), epoch = state.epoch, code = scan.value.trim();
      if (!code || !valid(session)) { status.textContent = 'Scan your badge and the physical item code'; return; }
      try {
        const result = await request('/scan', { code });
        if (!current(session, epoch)) return;
        const root = result.entity || result.code?.entity;
        if (!root || result.kind === 'user' || result.kind === 'invalid') throw Error('Scan an equipment code');
        if (candidate && candidate.id !== root.id) throw Error('Scanned item does not match selected candidate');
        candidate = null;
        const kit = await request('/api/kit?id=' + encodeURIComponent(root.id));
        if (!current(session, epoch)) return;
        let entities = [root], versions = {}, manifest = [], retainedItems = state.items, componentNotes = {};
        if (kit.kit) {
          if (state.items.some(item => item.root.id === root.id)) throw Error('This item is already in the batch');
          entities = kit.entities || [root]; versions = kit.versions || {};
          manifest = entities.map(item => item.name || item.id);
          for (const part of entities.slice(1)) {
            if (!(kit.verified || []).includes(part.id)) throw Error(`Scan kit component ${part.name || part.id} separately`);
          }
          const kitIds = new Set(entities.map(item => item.id));
          const overlaps = state.items.filter(item => item.entities.some(entity => kitIds.has(entity.id)));
          const merged = overlaps.filter(item => kitIds.has(item.root.id) && item.entities.every(entity => kitIds.has(entity.id)));
          if (merged.length !== overlaps.length) throw Error('A scanned item overlaps this kit; remove it and scan the complete kit again');
          for (const prior of merged) {
            if (prior.root.id !== root.id && prior.note) componentNotes[prior.root.id] = prior.note;
            Object.assign(componentNotes, prior.componentNotes || {});
          }
          retainedItems = state.items.filter(item => !merged.includes(item));
        } else if (state.items.some(item => item.entities.some(entity => entity.id === root.id))) throw Error('This item is already in the batch');
        if (new Set([...retainedItems.flatMap(item => item.entities.map(entity => entity.id)), ...entities.map(entity => entity.id)]).size > 50) throw Error('A return can contain at most 50 distinct items');
        const availability = await request('/return/availability?ids=' + encodeURIComponent(entities.map(item => item.id).join(',')));
        if (!current(session, epoch)) return;
        const byId = new Map(availability.items.map(item => [item.id, item]));
        if (entities.some(item => !byId.has(item.id) || !byId.get(item.id).eligible)) throw Error(entities.map(item => byId.get(item.id)?.reason || 'Item is not eligible').join('; '));
        state.items = [...retainedItems, { root, entities, versions, manifest, componentNotes, availability: byId, note: '', condition: '', issueNote: '' }];
        state.reviewed = false; scan.value = ''; search.value = ''; candidate = null;
        render('Physical scan verified.');
      } catch (error) { if (current(session, epoch)) status.textContent = error.message; }
    });
    host.append(scan, add);

    let confirmButton = null;
    for (const item of state.items) {
      const card = el('article'), available = item.availability.get(item.root.id), details = el('div'); card.className='item-preview-card';
      details.className='item-preview-details'; addItemPreview(card,item.root);
      details.append(el('strong', item.root.name || item.root.id));
      if (item.manifest.length) details.append(el('p', 'Kit manifest: ' + item.manifest.join(', ')));
      details.append(el('p', `Recorded condition: ${available.condition || 'Unknown'} · Return location: ${available.location?.name || 'Assigned location'}`));
      const condition = document.createElement('select');
      condition.setAttribute('aria-label', `Condition for ${item.root.name || item.root.id}`);
      condition.append(new Option('Keep recorded condition', ''), ...['Needs Attention', 'Maintenance', 'Quarantined', 'Broken'].map(value => new Option(value, value)));
      condition.value = item.condition;
      condition.addEventListener('change', () => { item.condition = condition.value; state.reviewed = false; if (confirmButton) confirmButton.disabled = true; });
      details.append(condition);
      const issue = el('input'); issue.placeholder = 'Required note if condition changed'; issue.value = item.issueNote;
      issue.addEventListener('input', () => { item.issueNote = issue.value; state.reviewed = false; if (confirmButton) confirmButton.disabled = true; }); details.append(issue);
      const note = el('input'); note.placeholder = 'Optional return note'; note.value = item.note;
      note.addEventListener('input', () => { item.note = note.value; state.reviewed = false; if (confirmButton) confirmButton.disabled = true; }); details.append(note);
      const remove = el('button', 'Remove'); remove.type = 'button';
      remove.addEventListener('click', () => { state.items = state.items.filter(entry => entry !== item); state.reviewed = false; render(); }); details.append(remove); card.append(details);
      host.append(card);
    }
    const review = button('Review return', reviewReturn);
    const actions = el('div'); actions.className = 'flow-actions'; actions.setAttribute('aria-label', 'Return actions'); host.append(actions); actions.append(review);
    if (state.uncertain) { host.append(el('p', 'Outcome uncertain. Check status; do not confirm again.')); button('Check saved result', recoverReturn); window.setKioskCancelAllowed?.('return',false); }
  }

  async function beginReturn() {
    Object.assign(state, { items: [], key: null, reviewed: false, sending: false, uncertain: false, cancelled: false, receipt: null, receiptSession: null, operationSession: null, preserved: false, reviewView: false, epoch: state.epoch + 1 });
    window.returnReceiptPreserved = false;
    render();
  }
  async function addReturnItem(item) { if (!item?.scanEvidence || !valid(item)) throw Error('A current physical scan is required'); }
  async function reviewReturn() {
    if (!valid(context()) || !state.items.length) return;
    if (state.items.some(item => item.condition && !item.issueNote.trim())) { render('Add an issue note for every changed condition.'); return; }
    state.reviewed = true; state.reviewView = true; render('Review complete. Confirm once to record these returns.');
  }
  async function confirmReturn() {
    const captured = context(), epoch = state.epoch;
    if (!state.reviewed || state.sending || state.uncertain || state.cancelled || !valid(captured)) return;
    state.key ||= crypto.randomUUID(); state.operationSession = captured; state.sending = true; state.reviewView = true; state.preserved = true; window.returnReceiptPreserved = true; render(); window.setKioskCancelAllowed?.('return',false);
    const targetsById = new Map();
    for (const item of state.items) for (const entity of item.entities) targetsById.set(entity.id, { entity_id: entity.id, ...(item.condition ? { condition: item.condition, note: item.issueNote } : {}), return_note: item.componentNotes?.[entity.id] ?? item.note });
    try {
      const result = await request('/return/confirm', {
        targets: [...targetsById.values()],
        kit_versions: Object.assign({}, ...state.items.map(item => item.versions)), request_key: state.key,
        session_generation: captured.generation, session_instance: captured.instance
      });
      if (!current(captured, epoch, true)) return;
      state.receipt = result; state.receiptSession = captured; state.sending = false; state.uncertain = false; render();
    } catch (error) {
      if (!current(captured, epoch, true)) return;
      state.sending = false;
      if (error.status === 400 && !/(interrupted|admin recovery|needs staff review|requires recovery|reconciliation)/i.test(error.message)) {
        state.uncertain = false; state.key = null; state.operationSession = null; state.preserved = false; window.returnReceiptPreserved = false; state.reviewed = false; state.reviewView = false; render(error.message); return;
      }
      state.uncertain = true; state.reviewView = true; render(error.message); window.setKioskCancelAllowed?.('return',false);
    }
  }
  async function recoverReturn() {
    const captured = state.operationSession, epoch = state.epoch, key = state.key;
    if (!key || !captured || !current(captured, epoch, true)) return;
    try {
      const result = await request('/operation/status', { request_key: key });
      if (!current(captured, epoch, true)) return;
      if (result.status === 'completed') { state.receipt = result; state.receiptSession = captured; state.uncertain = false; render(); }
      else if (result.status === 'not_started') { state.uncertain = false; state.key = null; state.operationSession = null; state.preserved = false; window.returnReceiptPreserved = false; state.reviewed = false; state.reviewView = false; render('No return was recorded. Review the updated items before trying again.'); }
      else render('No completed return is recorded. Ask staff to check before starting another return.');
    } catch (error) { if (current(captured, epoch, true)) render('Could not check status. Ask staff to verify before another return.'); }
  }

  window.beginReturn = beginReturn; window.addReturnItem = addReturnItem; window.reviewReturn = reviewReturn;
  window.confirmReturn = confirmReturn; window.recoverReturn = recoverReturn;
  window.addEventListener('ccrate-cancel-intent', event => { if (event.detail?.flow !== 'return') return; state.cancelled = true; state.epoch++; render('Cancelling…'); });
  window.addEventListener('ccrate-session-change', () => {
    const captured = state.operationSession;
    if (state.preserved && !state.cancelled && sameSession(captured)) { render(); return;}
    Object.assign(state, { items: [], key: null, reviewed: false, sending: false, uncertain: false, cancelled: false, receipt: null, receiptSession: null, operationSession: null, preserved: false, reviewView: false, epoch: state.epoch + 1 });
    window.returnReceiptPreserved = false; render();
  });
  window.addEventListener('ccrate-flow-done', event => {
    if (!event.detail?.cleanupAcknowledged || !state.preserved || !sameSession(event.detail)) return;
    state.preserved = false;
    Object.assign(state, { items: [], key: null, reviewed: false, sending: false, uncertain: false, cancelled: false, receipt: null, receiptSession: null, operationSession: null, epoch: state.epoch + 1 });
    render();
  });
})();
