let memberDraft = null;
const memberBadgeActions = new Map();
let memberBadgeQrImage = null, memberBadgePrint = null;
let memberBadgeSessionHandoff = null;
let memberBadgeQrOwnership = null;

async function confirmMemberBadge(route, payload, key) {
  try { return await api(route, payload); }
  catch (error) {
    const saved = await resolveTransaction(key);
    return { ...(saved.result || {}), status: saved.status || 'unknown', error: error.message };
  }
}

function clearMemberBadgeQr() {
  if (memberBadgeQrImage) { memberBadgeQrImage.removeAttribute('src'); memberBadgeQrImage.remove(); }
  memberBadgeQrImage = null;
  if (memberBadgePrint) memberBadgePrint.code = '';
  memberBadgePrint = null;
  memberBadgeQrOwnership = null;
}

new MutationObserver(() => {
  if (memberBadgeSessionHandoff?.preserving) return;
  if (memberBadgeQrImage && !memberBadgeQrImage.isConnected) clearMemberBadgeQr();
  if (memberBadgeSessionHandoff && !memberBadgeSessionHandoff.panel.isConnected) memberBadgeSessionHandoff = null;
}).observe(view, { childList: true, subtree: true });

function preserveMemberBadgeSessionEnd(userId) {
  if (memberBadgeSessionHandoff?.memberId !== userId || !memberBadgeSessionHandoff.panel.isConnected) return null;
  memberBadgeSessionHandoff.preserving = true;
  memberBadgeSessionHandoff.sessionEnded = true;
  return memberBadgeSessionHandoff.panel;
}

function finishMemberBadgeSessionEnd(panel) {
  if (memberBadgeSessionHandoff?.panel === panel) memberBadgeSessionHandoff.preserving = false;
}

function clearMemberBadgeForIdentityChange(userId) {
  const ownership = memberBadgeQrOwnership;
  if ((ownership && (ownership.operatorId !== userId || ownership.generation !== identityGeneration || ownership.instance !== identityInstance)) ||
      (memberBadgeSessionHandoff && memberBadgeSessionHandoff.memberId !== userId)) {
    const handoffPanel = memberBadgeSessionHandoff?.panel;
    memberBadgeSessionHandoff = null;
    clearMemberBadgeQr();
    if (handoffPanel?.isConnected) handoffPanel.remove();
  }
}

function memberBadgeAction(action, member, badge = null, returnAction = null) {
  const target = action === 'issue' ? member.id : badge.id;
  const actionId = action+':'+target;
  let savedAction = memberBadgeActions.get(actionId);
  if (!savedAction) {
    savedAction = { key: crypto.randomUUID(), status: 'ready' };
    memberBadgeActions.set(actionId, savedAction);
  }
  const name = member.name || 'Former member', shortId = target.slice(0, 8);
  const payload = () => action === 'issue'
    ? { user_id: member.id, request_key: savedAction.key }
    : action === 'revoke' ? { id: badge.id, request_key: savedAction.key }
      : { badge_id: badge.id, request_key: savedAction.key };

  const actionName = { issue: 'badge issuance', revoke: 'badge revocation', reprint: 'badge reprint', replace: 'badge replacement' }[action];
  heading('Confirm '+actionName);
  const revision = routeRevision, panel = node('div', undefined, 'notice'); view.append(panel);
  const returnTo = () => {
    if (savedAction.status === 'completed') memberBadgeActions.delete(actionId);
    returnAction ? returnAction() : document.querySelector('#admin').click();
  };
  const refreshBadges = async () => { try { await api('/api/badges'); } catch (_) {} };

  const finish = async (result) => {
    savedAction.status = result.status || 'unknown';
    savedAction.error = result.error || '';
    if (action === 'replace' && memberBadgeSessionHandoff?.panel === panel &&
        (savedAction.status !== 'completed' || !result.qr || !result.code)) memberBadgeSessionHandoff = null;
    if (savedAction.status === 'completed') await refreshBadges();
    const expectedSessionHandoff = action === 'replace' && memberBadgeSessionHandoff?.panel === panel &&
      memberBadgeSessionHandoff.memberId === member.id && memberBadgeSessionHandoff.sessionEnded && panel.isConnected;
    if ((revision !== routeRevision && !expectedSessionHandoff) || !panel.isConnected) return;
    panel.replaceChildren(node('h2', (action === 'issue' ? 'Issue badge: ' : action === 'revoke' ? 'Revoke badge: ' : action === 'reprint' ? 'Reprint badge: ' : 'Replace badge: ')+name+' · ID '+shortId));
    if (savedAction.status === 'completed') {
      panel.append(node('p', action === 'issue'
        ? result.qr ? 'Badge issued for this C-Crate member.' : 'Badge issuance completed. Its QR was shown once or is no longer available; no second badge was issued.'
        : action === 'revoke' ? 'Badge revoked. Existing sessions for this member have ended.'
          : action === 'reprint' ? 'Badge reprinted.'
            : 'Replacement badge issued. The older badge is revoked; printing is a separate confirmation.'));
      if (savedAction.error) panel.append(node('p', savedAction.error));
      if (['issue', 'replace'].includes(action) && result.qr && result.code) {
        const image = node('img'); image.src = result.qr; image.alt = 'Person badge QR'; image.style = 'width:220px;height:220px';
        memberBadgeQrImage = image; memberBadgePrint = { badgeId: result.id, code: result.code, key: crypto.randomUUID() };
        memberBadgeQrOwnership = { recipientId: member.id, operatorId: identityUserId, generation: identityGeneration, instance: identityInstance };
        panel.append(image, printButton());
        if (action === 'replace' && identityUserId === member.id) {
          const sessionEnded = memberBadgeSessionHandoff?.panel === panel && memberBadgeSessionHandoff.sessionEnded;
          memberBadgeSessionHandoff = { memberId: member.id, panel, preserving: false, sessionEnded: !!sessionEnded };
        }
      }
      panel.append(primary(returnAction ? 'Return to Manage badges' : 'Return to Administration', returnTo));
      return;
    }
    if (['not_started', 'cancelled'].includes(savedAction.status)) {
      panel.append(node('p', savedAction.error || 'No badge change was made.'));
      panel.append(primary('Start a new confirmation', () => {
        savedAction.key = crypto.randomUUID(); savedAction.status = 'ready'; savedAction.error = '';
        draw();
      }));
    } else {
      savedAction.status = savedAction.status || 'unknown';
      panel.append(node('p', 'The result is unresolved. Keep this confirmation blocked.'),
        primary('Check saved result', checkSaved), primary('Open recovery', () => window.showRecovery()));
    }
    panel.append(primary('Cancel', returnTo));
  };

  const checkSaved = async () => {
    const saved = await resolveTransaction(savedAction.key);
    if (revision !== routeRevision || !panel.isConnected) return;
    if (saved.status === 'completed') await finish({ ...(saved.result || {}), status: 'completed' });
    else if (['not_started', 'cancelled'].includes(saved.status)) await finish({ status: saved.status });
    else {
      savedAction.status = saved.status || 'unknown';
      panel.append(node('p', 'The result is still unresolved. Keep the same key and review Recovery.'));
    }
  };

  function draw() {
    const panelTitle = { issue: 'Issue badge: ', revoke: 'Revoke badge: ', reprint: 'Reprint badge: ', replace: 'Replace badge: ' }[action];
    panel.replaceChildren(node('h2', panelTitle+name+' · ID '+shortId));
    if (savedAction.status === 'completed') {
      const completedText = {
        issue: 'This badge issuance already completed. No second badge was issued.',
        revoke: 'This badge revocation already completed.',
        reprint: 'This badge reprint already completed. No second copy was printed.',
        replace: 'This badge replacement already completed. Printing is a separate confirmation.',
      }[action];
      panel.append(node('p', completedText));
    } else if (savedAction.status === 'pending' || savedAction.status === 'uncertain' || savedAction.status === 'review' || savedAction.status === 'unknown' || savedAction.status === 'sending') {
      panel.append(node('p', 'This confirmation is blocked while its result is unresolved.'));
      panel.append(primary('Check saved result', checkSaved), primary('Open recovery', () => window.showRecovery()));
    } else if (['not_started', 'cancelled'].includes(savedAction.status)) {
      panel.append(node('p', 'No change was made.'));
      panel.append(primary('Start a new confirmation', () => {
        savedAction.key = crypto.randomUUID(); savedAction.status = 'ready'; draw();
      }));
    } else {
      const descriptions = {
        issue: 'Confirm once to create a badge for this native member. Printing is a separate confirmation.',
        revoke: 'Confirm once to revoke this badge and end the member’s Terminal sessions.',
        reprint: 'Print one more copy of this member’s existing badge. Both copies identify the same person.',
        replace: 'The original QR was not saved for this older badge. Create a replacement first, then print it. Replacing it disables the old badge and ends its active kiosk sessions.',
      };
      panel.append(node('p', descriptions[action]));
      const titles = { issue: 'Confirm badge issue', revoke: 'Confirm badge revoke', reprint: 'Confirm reprint', replace: 'Confirm replacement' };
      const paths = { issue: '/badge/issue', revoke: '/badge/revoke', reprint: '/badge/reprint', replace: '/badge/replace' };
      const confirm = primary(titles[action], async () => {
        if (savedAction.status !== 'ready') return;
        savedAction.status = 'sending'; confirm.disabled = true;
        if (action === 'replace' && identityUserId === member.id) {
          const sessionEnded = memberBadgeSessionHandoff?.panel === panel && memberBadgeSessionHandoff.sessionEnded;
          memberBadgeSessionHandoff = { memberId: member.id, panel, preserving: false, sessionEnded: !!sessionEnded };
        }
        const result = await confirmMemberBadge(paths[action], payload(), savedAction.key);
        await finish(result);
      });
      panel.append(confirm, primary('Cancel', () => {
        if (savedAction.status === 'ready') memberBadgeActions.delete(actionId);
        returnTo();
      }));
    }
  }

  function printButton() {
    const button = primary('Confirm print one badge', async () => {
      const print = memberBadgePrint;
      if (!print?.code || print.status) return;
      print.status = 'sending'; button.disabled = true;
      const printed = await confirmMemberBadge('/badge/print', {
        badge_id: print.badgeId, code: print.code, request_key: print.key,
      }, print.key);
      const expectedSessionHandoff = memberBadgeSessionHandoff?.panel === panel &&
        memberBadgeSessionHandoff.memberId === member.id && memberBadgeSessionHandoff.sessionEnded && panel.isConnected;
      if ((revision !== routeRevision && !expectedSessionHandoff) || !panel.isConnected) return;
      print.status = printed.status || 'unknown';
      if (print.status === 'completed') { panel.append(node('p', 'Print completed.')); clearMemberBadgeQr(); memberBadgeSessionHandoff = null; }
      else if (['not_started', 'cancelled'].includes(print.status)) {
        panel.append(node('p', printed.error || 'No print completed.'));
        const retry = primary('Start a new print confirmation', () => {
          if (!memberBadgePrint?.code) return;
          memberBadgePrint.key = crypto.randomUUID(); memberBadgePrint.status = '';
          retry.remove(); panel.append(printButton());
        });
        retry.classList.add('member-print-retry'); panel.append(retry);
      } else panel.append(node('p', 'Print outcome is unresolved. Do not print again until Recovery is reviewed.'),
        primary('Open recovery', () => window.showRecovery()));
    });
    return button;
  }

  draw();
}

async function issueMemberBadge(member) {
  if (workflowBusy()) { workflowMessage('Wait for the current confirmation to finish.'); return; }
  memberBadgeAction('issue', member);
}
async function revokeMemberBadge(member, badge, returnAction = null) {
  if (workflowBusy()) { workflowMessage('Wait for the current confirmation to finish.'); return; }
  memberBadgeAction('revoke', member, badge, returnAction);
}

async function userBadges(member) {
  if (workflowBusy()) { workflowMessage('Wait for the current confirmation to finish.'); return; }
  heading('Manage badges: '+member.name+' · ID '+member.id.slice(0, 8));
  const revision = routeRevision, panel = node('div', undefined, 'notice'); view.append(panel);
  try {
    const badges = (await api('/api/badges')).filter(row => row.user_id === member.id);
    if (revision !== routeRevision) return;
    if (!badges.length) panel.append(node('p', 'No badges have been issued for this member.'));
    for (const badge of badges) {
      const row = node('div', undefined, 'badge-row');
      const date = badge.created_at ? new Date(badge.created_at).toLocaleString() : 'Earlier badge';
      row.append(node('p', 'Issued '+date+' · ID '+badge.id.slice(0, 8)+' · '+(badge.revoked ? 'Revoked' : 'Active')+(badge.reprintable ? ' · Reprintable' : ' · Older QR not saved')));
      if (!badge.revoked) {
        const revoke = node('button', 'Revoke badge');
        revoke.style = 'background:#245c89;color:white;padding:0 18px;margin:8px 10px 8px 0';
        revoke.onclick = () => revokeMemberBadge(member, badge, () => userBadges(member));
        row.append(revoke);
      }
      panel.append(row);
    }
    const active = badges.filter(row => !row.revoked);
    const select = node('select'); select.setAttribute('aria-label', 'Badge to manage');
    select.append(new Option(active.length > 1 ? 'Choose an active badge' : 'Choose a badge', ''));
    for (const badge of active) select.append(new Option('Issued '+(badge.created_at ? new Date(badge.created_at).toLocaleString() : 'Earlier')+' · ID '+badge.id.slice(0, 8), badge.id));
    if (active.length === 1) select.value = active[0].id;
    panel.append(select);
    const choice = () => active.find(row => row.id === select.value);
    const action = primary('Reprint badge', () => {
      const badge = choice(); if (badge) memberBadgeAction(badge.reprintable ? 'reprint' : 'replace', member, badge, () => userBadges(member));
    });
    const update = () => {
      const badge = choice(); action.textContent = badge && !badge.reprintable ? 'Replace older badge' : 'Reprint badge';
      action.disabled = !badge || workflowBusy();
    };
    select.onchange = update; update(); panel.append(action);
  } catch (error) { if (revision === routeRevision) panel.append(node('p', error.message)); }
  panel.append(primary('Return to Administration', () => document.querySelector('#admin').click()));
}

async function userManager() {
  heading('Manage users'); const revision = routeRevision;
  view.append(primary('New user', () => {
    memberDraft = { id: crypto.randomUUID(), name: '', email: '', avatar: '', notes: '', mode: 'badge-only', editable: true };
    userForm(true);
  }));
  try {
    const members = await api('/api/members'), { memberAvatar } = await import('/member-avatar.js');
    if (revision !== routeRevision) return;
    let loans = null, loanError = false;
    try { loans = await api('/api/member-loans'); }
    catch (_) { loanError = true; }
    if (revision !== routeRevision) return;
    const search = node('input'); search.setAttribute('aria-label', 'Find a user'); search.placeholder = 'Name, email or user ID';
    const results = node('div'); view.append(search, results);
    const loanItems = new Map();
    const elapsed = value => {
      const parsed = Date.parse(value || '');
      if (!Number.isFinite(parsed)) return 'Duration unavailable';
      const minutes = Math.max(0, Math.floor((Date.now() - parsed) / 60000));
      if (minutes < 1) return 'Less than a minute';
      if (minutes < 60) return minutes+' '+(minutes === 1 ? 'minute' : 'minutes');
      const hours = Math.floor(minutes / 60), days = Math.floor(hours / 24);
      return days ? days+' '+(days === 1 ? 'day' : 'days')+', '+(hours % 24)+' hr' : hours+' hr, '+(minutes % 60)+' min';
    };
    const date = value => Number.isFinite(Date.parse(value || '')) ? new Date(value).toLocaleString() : 'Checkout date unavailable';
    const refreshElapsed = () => {
      if (revision !== routeRevision) { clearInterval(timer); return; }
      for (const [details, entries] of loanItems) if (details.open)
        for (const [value, target] of entries) target.textContent = elapsed(value);
    };
    const timer = setInterval(refreshElapsed, 60000);
    const render = () => {
      loanItems.clear();
      results.replaceChildren();
      for (const member of members.filter(row => `${row.name} ${row.email || ''} ${row.id}`.toLowerCase().includes(search.value.toLowerCase()))) {
        const button = primary('Manage profile: '+member.name+' · ID '+member.id.slice(0, 8), () => userProfile(member.id));
        const picture = node('img'); picture.src = member.avatar || memberAvatar(member.id); picture.alt = ''; picture.width = 40; picture.height = 40; picture.style = 'vertical-align:middle;margin-right:12px;border-radius:6px'; button.prepend(picture); results.append(button);
        results.append(primary('Manage badges: '+member.name+' · ID '+member.id.slice(0, 8), () => userBadges(member)));
        const owned = loans?.filter(row => row.actor_id === member.id) || [];
        const details = node('details'), summary = node('summary');
        summary.textContent = loanError ? 'Items unavailable' : owned.length+' '+(owned.length === 1 ? 'item' : 'items')+' checked out';
        details.append(summary);
        const elapsedRows = [];
        if (loanError) {
          details.append(node('p', 'Items unavailable'));
          details.append(primary('Reload items', userManager));
        } else {
          for (const item of owned) {
            const card = node('div', undefined, 'notice'); card.style = 'display:flex;gap:12px;align-items:flex-start;margin:8px 0';
            if (item.imageId) {
              const image = node('img'); image.src = '/api/file?entity='+encodeURIComponent(item.entity_id)+'&attachment='+encodeURIComponent(item.imageId);
              image.alt = 'Preview of '+(item.entity_name || 'unavailable item'); image.loading = 'lazy'; image.style = 'width:64px;height:64px;object-fit:contain;flex:none';
              image.onerror = () => { const placeholder = node('div', 'Photo unavailable', 'notice'); placeholder.setAttribute('role', 'img'); placeholder.setAttribute('aria-label', 'Photo unavailable for '+(item.entity_name || 'item')); image.replaceWith(placeholder); };
              card.append(image);
            } else {
              const placeholder = node('div', 'No photo available', 'notice'); placeholder.setAttribute('role', 'img'); placeholder.setAttribute('aria-label', 'No photo for '+(item.entity_name || 'item')); card.append(placeholder);
            }
            const text = node('div'); text.append(node('strong', item.entity_name || 'Native equipment unavailable'));
            if (item.assetId) text.append(node('p', item.assetId));
            const time = node('time', date(item.checked_out_at)); if (item.checked_out_at) time.dateTime = item.checked_out_at;
            text.append(node('p', 'Checked out: '), time);
            const duration = node('span', elapsed(item.checked_out_at)); text.append(node('p', 'Out for: '), duration);
            card.append(text); details.append(card); elapsedRows.push([item.checked_out_at, duration]);
          }
          if (!owned.length) details.append(node('p', 'No items checked out.'));
        }
        details.addEventListener('toggle', refreshElapsed);
        loanItems.set(details, elapsedRows); results.append(details);
      }
    };
    search.oninput = render; render();
  } catch (error) { if (revision === routeRevision) view.append(node('p', error.message), primary('Reload users', userManager)); }
}

async function userProfile(id) {
  heading('Manage profile'); const revision = routeRevision;
  try {
    const profile = await api('/api/user-profile?id='+encodeURIComponent(id));
    if (revision !== routeRevision) return;
    memberDraft = profile; userForm(false);
  } catch (error) { if (revision === routeRevision) view.append(node('p', error.message), primary('Back to users', userManager)); }
}

async function userForm(isNew) {
  const draft = memberDraft;
  heading(isNew ? 'Create user' : 'Manage profile'); const revision = routeRevision, panel = node('div', undefined, 'notice'); view.append(panel);
  const { memberAvatar, prepareMemberAvatar } = await import('/member-avatar.js');
  if (revision !== routeRevision || draft !== memberDraft) return;
  const picture = node('img'); picture.width = 80; picture.height = 80; picture.style = 'border-radius:8px';
  const renderPicture = () => { picture.src = draft.avatar || memberAvatar(draft.id); picture.alt = (draft.avatar ? 'Profile picture for ' : 'Generated avatar for ')+(draft.name || 'New user'); };
  renderPicture(); panel.append(picture, node('p', draft.mode === 'badge-only' ? 'Badge-only person' : 'Existing web account'));
  const name = touchField(panel, 'Name', draft, 'name'); name.maxLength = 255;
  const contact = touchField(panel, draft.mode === 'badge-only' ? 'Email (optional)' : 'Sign-in email', draft, 'email'); contact.type = 'email'; contact.maxLength = 255;
  let uploading = false, uncertain = false;
  if (!isNew) {
    panel.append(node('p', 'User ID: '+draft.id));
    const label = node('label', 'Profile picture'), file = node('input'); file.type = 'file'; file.accept = 'image/png,image/jpeg,image/webp'; file.setAttribute('aria-label', 'Profile picture'); label.append(file); panel.append(label);
    file.onchange = async () => {
      if (!file.files[0]) return;
      uploading = true; save.disabled = true;
      try { const value = await prepareMemberAvatar(file.files[0]); if (revision === routeRevision && draft === memberDraft) { draft.avatar = value; formDirty = true; renderPicture(); } }
      catch (error) { if (revision === routeRevision) panel.append(node('p', error.message)); }
      finally { uploading = false; file.value = ''; save.disabled = uncertain; }
    };
    panel.append(primary('Use generated picture', () => { draft.avatar = ''; formDirty = true; renderPicture(); }));
    touchField(panel, 'Other details (optional)', draft, 'notes').maxLength = 1000;
  } else panel.append(node('p', 'Only a name is needed. After creating the user, you can change their picture or issue a badge from Admin.'));
  if (!draft.editable) { for (const input of panel.querySelectorAll('input,button')) input.disabled = true; panel.append(node('p', "This profile is managed in the person's primary collection.")); }
  if (draft.protected && draft.mode !== 'badge-only') { contact.disabled = true; panel.append(node('p', "The collection owner's sign-in details are protected here.")); }
  const key = isNew ? draft.id : crypto.randomUUID();
  const save = primary(isNew ? 'Create user' : 'Save profile', async () => {
    if (uploading || uncertain) return;
    const controls = [...panel.querySelectorAll('input,button')].map(control => [control, control.disabled]);
    controls.forEach(([control]) => control.disabled = true); writeCount++;
    try {
      const result = await api(isNew ? '/accounts/create' : '/accounts/update', { ...draft, user_id: draft.id, request_key: key });
      formDirty = false; await userProfile(result.id); status.textContent = isNew ? 'User created. Issue a badge from Admin when ready.' : 'Profile saved.';
    } catch (error) {
      panel.append(node('p', error.message));
      const saved = await resolveTransaction(key);
      if (saved.status === 'completed' && saved.result?.id) { formDirty = false; await userProfile(saved.result.id); return; }
      uncertain = !['not_started', 'cancelled'].includes(saved.status); save.disabled = uncertain;
      if (uncertain) panel.append(node('p', 'Check Recovery before another confirmation.'), primary('Open recovery', showRecovery));
    } finally {
      writeCount--; controls.forEach(([control, disabled]) => control.disabled = uncertain || disabled); save.disabled = uncertain || !draft.editable;
    }
  });
  save.disabled = !draft.editable;
  panel.append(save, primary('Back to users', () => leaveTask(userManager)));
}

const resetMemberTask = resetTask;
resetTask = function() { memberDraft = null; return resetMemberTask(); };
