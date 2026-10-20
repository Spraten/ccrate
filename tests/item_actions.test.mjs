import assert from 'node:assert/strict';
import test from 'node:test';
import { createItemActionController, normalizeItemActionStatus } from '../homebox-ui/overlay/lib/item-actions.js';
import { recentItemNotes } from '../homebox-ui/overlay/lib/item-activity-notes.js';

const context = { identity: 'session-a', group: { id: 'group-a' }, user: { id: 'user-a' }, manager: false };
const item = '11111111-1111-4111-8111-111111111111';
const uuid = (() => { let n = 0; return () => `request-${++n}`; })();
function harness(routes = {}, contextRef = { value: context }) {
  const calls = [], changed = [];
  const values = new Map();
  const storage = { getItem: key => values.get(key) || null, setItem: (key, value) => values.set(key, value) };
  const request = async (path, body, identity) => {
    calls.push({ path, body, identity });
    const handler = routes[path];
    return handler ? handler(body) : {};
  };
  const controller = createItemActionController({ request, getContext: () => contextRef.value, uuid, storage, onChanged: value => changed.push(value) });
  return { controller, calls, changed, storage, contextRef };
}

test('checkout_badge_then_confirm uses exact item, one verification and stable request key', async () => {
  const h = harness({
    ['item-actions/status?ids=' + item]: async () => [{ id: item, availability: 'available', can_add_note: true }],
    'item-actions/verify-badge': async () => ({ verification_id: 'proof', required_items: [item], kit_versions: {} }),
    'item-actions/verify-item': async () => ({ verified_items: [item], required_items: [item] }),
    'item-actions/checkout': async () => ({ status: 'completed', id: 'receipt' }),
  });
  await h.controller.open({ kind: 'checkout', itemId: item, source: 'row' });
  await h.controller.verifyBadge('badge');
  await h.controller.verifyItem('asset-code');
  h.controller.setNote(item, 'Unicode 🎥');
  await h.controller.confirm();
  assert.deepEqual(h.calls.filter(row => row.path === 'item-actions/checkout')[0].body, {
    verification_id: 'proof', assets: [item], notes: { [item]: 'Unicode 🎥' }, request_key: 'request-2',
  });
  assert.equal(h.calls.filter(row => row.path === 'item-actions/verify-badge').length, 1);
  assert.ok(h.calls.filter(row => row.path.includes('item-actions/status')).every(row => row.identity === 'session-a'));
  assert.equal(h.changed[0].receiptId, 'receipt');
});

test('unknown_result_status_only checks status and never repeats the write', async () => {
  let checkoutCalls = 0;
  const h = harness({
    ['item-actions/status?ids=' + item]: async () => [{ id: item, availability: 'available' }],
    'item-actions/verify-badge': async () => ({ verification_id: 'proof', required_items: [item], kit_versions: {} }),
    'item-actions/verify-item': async () => ({ verified_items: [item], required_items: [item] }),
    'item-actions/checkout': async () => { checkoutCalls++; throw new Error('connection lost'); },
    'operation/status': async () => ({ status: 'pending' }),
  });
  await h.controller.open({ kind: 'checkout', itemId: item, source: 'row' });
  await h.controller.verifyBadge('badge');
  await h.controller.verifyItem('asset-code');
  await assert.rejects(h.controller.confirm());
  assert.equal(h.controller.state.phase, 'uncertain');
  await h.controller.reconcile();
  assert.equal(checkoutCalls, 1);
  assert.equal(h.calls.at(-1).path, 'operation/status');
});

test('a failed kit scan cannot reach confirmation', async () => {
  const h = harness({
    ['item-actions/status?ids=' + item]: async () => [{ id: item, availability: 'available' }],
    'item-actions/verify-badge': async () => ({ verification_id: 'proof', required_items: [item, 'child'], kit_versions: { [item]: 'v1' } }),
    'item-actions/verify-item': async () => { throw new Error('Kit changed. Review it again.'); },
  });
  await h.controller.open({ kind: 'checkout', itemId: item, source: 'row' });
  await h.controller.verifyBadge('badge');
  await assert.rejects(h.controller.verifyItem('wrong-code'));
  assert.equal(h.controller.state.phase, 'error');
  assert.equal(h.calls.some(row => row.path === 'item-actions/checkout'), false);
});

test('checkout kit mutation uses every server-required component while cart selection stays at the chosen root', async () => {
  const child = '22222222-2222-4222-8222-222222222222';
  const h = harness({
    ['item-actions/status?ids=' + item]: async () => [{ id: item, availability: 'available' }],
    ['item-actions/status?ids=' + encodeURIComponent(item + ',' + child)]: async () => [
      { id: item, availability: 'available' }, { id: child, availability: 'available' },
    ],
    'item-actions/verify-badge': async () => ({ verification_id: 'kit-proof', required_items: [item, child], kit_versions: { [item]: 'manifest-v1' } }),
    'item-actions/verify-item': async body => ({ verified_items: body.code === 'child-code' ? [item, child] : [item], required_items: [item, child] }),
    'item-actions/checkout': async body => ({ status: 'completed', id: body.request_key }),
  });
  await h.controller.open({ kind: 'checkout', itemId: item, source: 'row' });
  await h.controller.verifyBadge('badge');
  await h.controller.verifyItem('root-code');
  await h.controller.verifyItem('child-code');
  await h.controller.confirm();
  assert.deepEqual(h.calls.find(row => row.path === 'item-actions/checkout').body.assets, [item, child]);
  assert.deepEqual(h.changed[0].itemIds, [item, child], 'status/history refresh includes every kit member mutated by checkout');
});

test('check-in completion publishes the root and all verified kit components as changed IDs', async () => {
  const child = '22222222-2222-4222-8222-222222222222';
  const h = harness({
    ['item-actions/status?ids=' + item]: async () => [{ id: item, availability: 'checked_out', can_checkin: true }],
    ['kit?id=' + item]: async () => ({ kit: true, entities: [{ id: item }, { id: child }], versions: { [item]: 'v1' } }),
    'item-actions/checkin': async () => ({ status: 'completed', id: 'return-receipt' }),
  });
  await h.controller.open({ kind: 'checkin', itemId: item, source: 'row' });
  h.controller.setDraft({ kit_items: [{ id: item }, { id: child }], verified: [item, child], kit_versions: { [item]: 'v1' } });
  await h.controller.confirm();
  assert.deepEqual(h.changed[0].itemIds, [item, child]);
});

test('checkin uses owner authorization and return destination/problem fields without a badge', async () => {
  const h = harness({
    ['item-actions/status?ids=' + item]: async () => [{ id: item, availability: 'checked_out', can_checkin: true, loan: { borrower_id: 'user-a' } }],
    'item-actions/checkin': async body => ({ status: 'completed', id: body.request_key }),
  });
  await h.controller.open({ kind: 'checkin', itemId: item, source: 'detail' });
  h.controller.setDraft({ destination_id: 'location-b', return_note: 'Returned after use', problem: 'Loose hinge' });
  await h.controller.confirm();
  assert.equal(h.calls.some(row => row.path === 'item-actions/verify-badge'), false);
  assert.deepEqual(h.calls.find(row => row.path === 'item-actions/checkin').body.targets[0], {
    entity_id: item, destination_id: 'location-b', return_note: 'Returned after use', problem_description: 'Loose hinge',
  });
});

test('append_item_note requires text and uses trusted request key', async () => {
  const h = harness({
    ['item-actions/status?ids=' + item]: async () => [{ id: item, can_add_note: true }],
    'item-actions/note': async body => ({ status: 'completed', id: body.request_key }),
  });
  await h.controller.open({ kind: 'note', itemId: item, source: 'row' });
  h.controller.setDraft({ note: '   ' });
  await assert.rejects(h.controller.confirm(), /required/i);
  h.controller.setDraft({ note: 'Camera case latch repaired' });
  await h.controller.confirm();
  assert.equal(h.calls.find(row => row.path === 'item-actions/note').body.note, 'Camera case latch repaired');
});

test('cart checkout binds exact selection, revision and per-item notes to one proof', async () => {
  const h = harness({
    'checkout-cart': async () => ({ revision: 9, items: [item, '22222222-2222-4222-8222-222222222222'], notes: {} }),
    ['item-actions/status?ids=' + encodeURIComponent(item + ',22222222-2222-4222-8222-222222222222')]: async () => [
      { id: item, availability: 'available' }, { id: '22222222-2222-4222-8222-222222222222', availability: 'available' },
    ],
    'item-actions/verify-badge': async body => ({ verification_id: 'cart-proof', required_items: body.item_ids, kit_versions: {} }),
    'item-actions/verify-item': async body => ({ verified_items: [item, '22222222-2222-4222-8222-222222222222'], required_items: [item, '22222222-2222-4222-8222-222222222222'] }),
    'item-actions/checkout': async body => ({ status: 'completed', id: body.request_key }),
  });
  await h.controller.open({ kind: 'checkout', itemIds: [item, '22222222-2222-4222-8222-222222222222'], cartRevision: 9, source: 'cart' });
  await h.controller.verifyBadge('badge');
  await h.controller.verifyItem('item-code');
  h.controller.setNote(item, 'Lens cap');
  await h.controller.confirm();
  const payload = h.calls.find(row => row.path === 'item-actions/checkout').body;
  assert.deepEqual(payload.assets, [item, '22222222-2222-4222-8222-222222222222']);
  assert.deepEqual(payload.cart, { revision: 9, items: payload.assets, notes: { [item]: 'Lens cap' } });
});

test('unknown status blocks mutations and unknown never means available', async () => {
  const h = harness({ ['item-actions/status?ids=' + item]: async () => [{ id: item, availability: 'unknown' }] });
  await assert.rejects(h.controller.open({ kind: 'checkout', itemId: item, source: 'row' }), /unavailable|unknown/i);
  assert.equal(h.controller.state.status[0].availability, 'unknown');
  await assert.rejects(h.controller.verifyBadge('badge'), /unknown|reload|review/i);
  assert.equal(h.calls.some(row => row.path === 'item-actions/verify-badge'), false);
});

test('cancel untouched draft closes immediately; changed draft requires discard confirmation', async () => {
  const h = harness({ ['item-actions/status?ids=' + item]: async () => [{ id: item, availability: 'available' }] });
  await h.controller.open({ kind: 'cart', itemId: item, source: 'row' });
  assert.equal(h.controller.close(), true);
  await h.controller.open({ kind: 'cart', itemId: item, source: 'row' });
  h.controller.setDraft({ note: 'draft' });
  assert.equal(h.controller.close(), false);
  assert.equal(h.controller.state.discardPrompt, true);
  h.controller.discard();
  assert.equal(h.controller.state.phase, 'closed');
});

test('account/group change closes flow and clears verification without crossing identities', async () => {
  const contextRef = { value: context };
  const h = harness({ ['item-actions/status?ids=' + item]: async () => [{ id: item, availability: 'available' }] }, contextRef);
  await h.controller.open({ kind: 'cart', itemId: item, source: 'row' });
  h.controller.setDraft({ note: 'private cart note' });
  contextRef.value = { ...context, group: { id: 'group-b' }, identity: 'session-b' };
  h.controller.syncContext();
  assert.equal(h.controller.state.phase, 'closed');
  assert.equal(h.controller.state.verificationId, null);
});

test('changing the exact selection invalidates badge proof and request identity', async () => {
  const h = harness({
    ['item-actions/status?ids=' + item]: async () => [{ id: item, availability: 'available' }],
    'item-actions/status?ids=22222222-2222-4222-8222-222222222222': async () => [{ id: '22222222-2222-4222-8222-222222222222', availability: 'available' }],
    'item-actions/verify-badge': async () => ({ verification_id: 'proof', required_items: [], kit_versions: {} }),
  });
  await h.controller.open({ kind: 'checkout', itemId: item, source: 'row' });
  await h.controller.verifyBadge('badge');
  h.controller.state.requestKey = 'old-key';
  assert.equal(await h.controller.changeSelection(['22222222-2222-4222-8222-222222222222'], 3), true);
  assert.equal(h.controller.state.verificationId, null);
  assert.equal(h.controller.state.requestKey, null);
  assert.deepEqual(h.controller.state.itemIds, ['22222222-2222-4222-8222-222222222222']);
});

test('cart add uses the latest revision and preserves notes on retained items', async () => {
  const previous = '22222222-2222-4222-8222-222222222222';
  const h = harness({
    'checkout-cart': async body => body ? ({ revision: 5, items: [previous, item], notes: { [previous]: 'Already packed', [item]: 'Bring battery' } }) : ({ revision: 4, items: [previous], notes: { [previous]: 'Already packed' } }),
    ['item-actions/status?ids=' + encodeURIComponent(previous + ',' + item)]: async () => [
      { id: previous, availability: 'checked_out' }, { id: item, availability: 'available' },
    ],
  });
  await h.controller.open({ kind: 'cart', itemId: item, source: 'row' });
  await h.controller.setNote(item, 'Bring battery');
  await h.controller.confirm();
  const save = h.calls.find(row => row.path === 'checkout-cart' && row.body);
  assert.deepEqual(save.body, { items: [previous, item], revision: 4, request_key: save.body.request_key, notes: { [previous]: 'Already packed', [item]: 'Bring battery' } });
  assert.match(save.body.request_key, /^request-/);
});

test('cart_blocked_member_stops_whole_selection before badge scan', async () => {
  const second = '22222222-2222-4222-8222-222222222222';
  const h = harness({
    'checkout-cart': async () => ({ revision: 7, items: [item, second], notes: {} }),
    ['item-actions/status?ids=' + encodeURIComponent(item + ',' + second)]: async () => [
      { id: item, availability: 'available' }, { id: second, availability: 'blocked', blocker: 'Needs Attention' },
    ],
  });
  await assert.rejects(h.controller.open({ kind: 'checkout', itemIds: [item, second], cartRevision: 7, source: 'cart' }), /unavailable/i);
  assert.equal(h.calls.some(row => row.path === 'item-actions/verify-badge'), false);
});

test('problem_description_required and return_elsewhere preserve separate return note', async () => {
  const h = harness({
    ['item-actions/status?ids=' + item]: async () => [{ id: item, availability: 'checked_out', can_checkin: true }],
    ['entity?id=' + item]: async () => ({ entity: { id: item, parent: { id: 'assigned-location' } } }),
    ['kit?id=' + item]: async () => ({ kit: false, versions: {} }),
    'item-actions/checkin': async body => ({ status: 'completed', id: body.request_key }),
  });
  await h.controller.open({ kind: 'checkin', itemId: item, source: 'row' });
  assert.equal(h.controller.state.draft.destination_id, 'assigned-location');
  h.controller.setDraft({ destination_id: 'other-location', return_note: 'Returned to stage', problem: '   ' });
  await assert.rejects(h.controller.confirm(), /problem/i);
  h.controller.setDraft({ problem: 'Loose hinge' });
  await h.controller.confirm();
  assert.deepEqual(h.calls.find(row => row.path === 'item-actions/checkin').body.targets[0], {
    entity_id: item, destination_id: 'other-location', return_note: 'Returned to stage', problem_description: 'Loose hinge',
  });
});

test('check-in kit requires exact scanned component IDs and current manifest versions', async () => {
  const child = '22222222-2222-4222-8222-222222222222';
  const h = harness({
    ['item-actions/status?ids=' + item]: async () => [{ id: item, availability: 'checked_out', can_checkin: true }],
    ['entity?id=' + item]: async () => ({ entity: { id: item, parent: { id: 'assigned' } } }),
    ['kit?id=' + item]: async () => ({ kit: true, versions: { [item]: 'kit-v2' }, entities: [{ id: item, name: 'Camera kit' }, { id: child, name: 'Lens' }] }),
    'workshop/resolve': async body => body.code === 'lens' ? ({ kind: 'entity', entity_id: child }) : body.code === 'root' ? ({ kind: 'entity', entity_id: item }) : ({ kind: 'unknown', entity_id: null }),
    'item-actions/checkin': async body => ({ status: 'completed', id: body.request_key }),
  });
  await h.controller.open({ kind: 'checkin', itemId: item, source: 'row' });
  await assert.rejects(h.controller.confirm(), /component/i);
  await assert.rejects(h.controller.verifyReturnItem('wrong-code'), /exact kit/i);
  await h.controller.verifyReturnItem('root');
  await h.controller.verifyReturnItem('lens');
  assert.deepEqual(h.controller.state.draft.verified, [item, child]);
  await h.controller.confirm();
  const payload = h.calls.find(row => row.path === 'item-actions/checkin').body;
  assert.deepEqual(payload.verified, [item, child]);
  assert.deepEqual(payload.kit_versions, { [item]: 'kit-v2' });
});

test('long_unicode_note allows 1000 code points and rejects 1001', async () => {
  const h = harness({ ['item-actions/status?ids=' + item]: async () => [{ id: item, availability: 'available' }] });
  await h.controller.open({ kind: 'cart', itemId: item, source: 'row' });
  const note = '🎥'.repeat(1000);
  assert.doesNotThrow(() => h.controller.setNote(item, note));
  assert.throws(() => h.controller.setNote(item, note + '🎥'), /1,000/);
});

test('pending action survives reload as status-only recovery scoped to the same account and collection', async () => {
  const first = harness({
    ['item-actions/status?ids=' + item]: async () => [{ id: item, availability: 'available' }],
    'item-actions/verify-badge': async () => ({ verification_id: 'proof', required_items: [item], kit_versions: {} }),
    'item-actions/verify-item': async () => ({ verified_items: [item], required_items: [item] }),
    'item-actions/checkout': async () => { throw new Error('connection lost'); },
  });
  await first.controller.open({ kind: 'checkout', itemId: item, source: 'row' });
  await first.controller.verifyBadge('badge'); await first.controller.verifyItem('asset-code');
  await assert.rejects(first.controller.confirm());
  const pending = first.controller.pendingActions();
  assert.equal(pending.length, 1);
  const foreignContext = { value: { ...context, user: { id: 'other-user' }, identity: 'other-session' } };
  const foreign = createItemActionController({ getContext: () => foreignContext.value, uuid, storage: first.storage, request: async () => ({ status: 'not_started' }) });
  assert.equal(foreign.pendingActions().length, 0);
  assert.throws(() => foreign.recoverPending(pending[0]), /different account or collection/i);
  assert.equal(first.controller.pendingActions().length, 1);
  const secondCalls = [];
  const recovered = createItemActionController({
    getContext: () => context,
    uuid,
    storage: first.storage,
    request: async (path, body) => { secondCalls.push({ path, body }); return { status: 'completed', id: 'saved-receipt' }; },
  });
  recovered.recoverPending(pending[0]);
  await recovered.reconcile();
  assert.deepEqual(secondCalls.map(row => row.path), ['operation/status']);
  assert.equal(recovered.pendingActions().length, 0);
  assert.equal(recovered.state.phase, 'closed');
});

test('status envelope is normalized for open, selection refresh, confirm preflight and row lookup contract', async () => {
  const second = '22222222-2222-4222-8222-222222222222';
  const h = harness({
    ['item-actions/status?ids=' + item]: async () => ({ items: [{ id: item, availability: 'available' }] }),
    ['item-actions/status?ids=' + second]: async () => ({ items: [{ id: second, availability: 'available' }] }),
    ['item-actions/status?ids=' + encodeURIComponent(item + ',' + second)]: async () => ({ items: [
      { id: item, availability: 'available' }, { id: second, availability: 'available' },
    ] }),
    'item-actions/verify-badge': async () => ({ verification_id: 'proof', required_items: [item, second] }),
    'item-actions/verify-item': async () => ({ verified_items: [item, second] }),
    'item-actions/checkout': async () => ({ status: 'completed', id: 'receipt' }),
  });
  await h.controller.open({ kind: 'checkout', itemId: item, source: 'row' });
  assert.deepEqual(normalizeItemActionStatus({ items: [{ id: item }] }), [{ id: item }]);
  assert.equal(h.controller.state.status[0].availability, 'available');
  await h.controller.changeSelection([second], 1);
  await h.controller.verifyBadge('badge'); await h.controller.verifyItem('both');
  await h.controller.confirm();
  assert.equal(h.controller.state.phase, 'closed');
});

test('kit check-in applies the verified root and every current manifest component', async () => {
  const child = '22222222-2222-4222-8222-222222222222';
  const h = harness({
    ['item-actions/status?ids=' + item]: async () => ({ items: [{ id: item, availability: 'checked_out', can_checkin: true }] }),
    ['entity?id=' + item]: async () => ({ entity: { id: item } }),
    ['kit?id=' + item]: async () => ({ kit: true, versions: { [item]: 'manifest-2' }, entities: [{ id: item, name: 'Case' }, { id: child, name: 'Lens' }] }),
    'workshop/resolve': async body => ({ kind: 'entity', entity_id: body.code === 'root-code' ? item : child }),
    'item-actions/checkin': async () => ({ status: 'completed' }),
  });
  await h.controller.open({ kind: 'checkin', itemId: item, source: 'row' });
  h.controller.setDraft({ destination_id: 'new-root-location', return_note: 'Root return note', problem: 'Root-only problem' });
  await h.controller.verifyReturnItem('root-code'); await h.controller.verifyReturnItem('lens-code');
  await h.controller.confirm();
  const targets = h.calls.find(row => row.path === 'item-actions/checkin').body.targets;
  assert.deepEqual(targets, [
    { entity_id: item, destination_id: 'new-root-location', return_note: 'Root return note', problem_description: 'Root-only problem' },
    { entity_id: child },
  ]);
});

test('unresolved action blocks new opens and cannot discard an uncertain note intent', async () => {
  let writes = 0;
  const h = harness({
    ['item-actions/status?ids=' + item]: async () => ({ items: [{ id: item, can_add_note: true }] }),
    'item-actions/note': async () => { writes++; throw new Error('connection lost'); },
    'operation/status': async () => ({ status: 'review' }),
  });
  await h.controller.open({ kind: 'note', itemId: item, source: 'row' });
  h.controller.setDraft({ note: 'Keep this note intent' });
  await assert.rejects(h.controller.confirm());
  const key = h.controller.state.requestKey;
  assert.equal(h.controller.close(), false);
  await assert.rejects(h.controller.open({ kind: 'note', itemId: item, source: 'row' }), /unresolved/i);
  await h.controller.reconcile();
  assert.equal(h.controller.state.phase, 'uncertain');
  assert.equal(h.controller.state.requestKey, key);
  assert.equal(writes, 1);
});

test('expired badge proof can be renewed without losing checkout note', async () => {
  let proofs = 0;
  const h = harness({
    ['item-actions/status?ids=' + item]: async () => ({ items: [{ id: item, availability: 'available' }] }),
    'item-actions/verify-badge': async () => ({ verification_id: `proof-${++proofs}`, required_items: [item] }),
    'item-actions/verify-item': async () => { throw Object.assign(new Error('Proof expired'), { status: 409 }); },
  });
  await h.controller.open({ kind: 'checkout', itemId: item, source: 'row' });
  h.controller.setNote(item, 'preserve draft');
  await h.controller.verifyBadge('badge');
  await assert.rejects(h.controller.verifyItem('code'));
  await h.controller.verifyBadge('badge-again');
  assert.equal(h.controller.state.phase, 'review');
  assert.equal(h.controller.state.draft.notes[item], 'preserve draft');
  assert.equal(h.controller.state.verificationId, 'proof-2');
});

test('only completed receipts succeed; definitive 409 clears stale intent for re-review', async () => {
  const h = harness({
    ['item-actions/status?ids=' + item]: async () => ({ items: [{ id: item, availability: 'available' }] }),
    'item-actions/verify-badge': async () => ({ verification_id: 'proof', required_items: [item] }),
    'item-actions/verify-item': async () => ({ verified_items: [item] }),
    'item-actions/checkout': async () => ({ status: 'review' }),
    'operation/status': async () => ({ status: 'review' }),
  });
  await h.controller.open({ kind: 'checkout', itemId: item, source: 'row' });
  await h.controller.verifyBadge('badge'); await h.controller.verifyItem('code');
  await assert.rejects(h.controller.confirm(), /needs review|not confirmed/i);
  assert.equal(h.controller.state.phase, 'uncertain');
  await h.controller.reconcile();
  assert.equal(h.controller.state.phase, 'uncertain');
  const conflict = harness({
    ['item-actions/status?ids=' + item]: async () => ({ items: [{ id: item, availability: 'available' }] }),
    'item-actions/verify-badge': async () => ({ verification_id: 'proof-2', required_items: [item] }),
    'item-actions/verify-item': async () => ({ verified_items: [item] }),
    'item-actions/checkout': async () => { throw Object.assign(new Error('Request key conflicts with a different intent'), { status: 409 }); },
    'operation/status': async () => ({ status: 'not_started' }),
  });
  await conflict.controller.open({ kind: 'checkout', itemId: item, source: 'row' });
  await conflict.controller.verifyBadge('badge'); await conflict.controller.verifyItem('code');
  await assert.rejects(conflict.controller.confirm());
  assert.equal(conflict.controller.pendingActions().length, 0);
  assert.equal(conflict.controller.state.phase, 'review');
  assert.equal(conflict.controller.state.verificationId, null);
});

test('cart note for a newly added unit stays attached to that unit, not the existing first row', async () => {
  const existing = '22222222-2222-4222-8222-222222222222';
  const h = harness({
    'checkout-cart': async body => body ? ({ revision: 4, items: [existing, item], notes: { [existing]: 'Keep A draft', [item]: 'For B' } }) : ({ revision: 3, items: [existing], notes: { [existing]: 'Keep A draft' } }),
    ['item-actions/status?ids=' + encodeURIComponent(existing + ',' + item)]: async () => ({ items: [
      { id: existing, availability: 'available' }, { id: item, availability: 'available' },
    ] }),
  });
  await h.controller.open({ kind: 'cart', itemId: item, source: 'row' });
  h.controller.setNote(item, 'For B');
  await h.controller.confirm();
  assert.deepEqual(h.calls.find(row => row.path === 'checkout-cart' && row.body).body.notes, { [existing]: 'Keep A draft', [item]: 'For B' });
});

test('checked-out or blocked equipment remains eligible for non-reserving cart planning with a private note', async () => {
  const h = harness({
    'checkout-cart': async body => body ? ({ revision: 5, items: body.items, notes: body.notes }) : ({ revision: 4, items: [], notes: {} }),
    ['item-actions/status?ids=' + item]: async () => [{ id: item, availability: 'blocked', blocker: 'Needs inspection' }],
  });
  await h.controller.open({ kind: 'cart', itemId: item, source: 'cart' });
  assert.equal(h.controller.state.phase, 'review');
  h.controller.setNote(item, 'Check the cracked handle');
  await h.controller.confirm();
  const saved = h.calls.filter(row => row.path === 'checkout-cart' && row.body)[0];
  assert.deepEqual(saved.body.items, [item]);
  assert.deepEqual(saved.body.notes, { [item]: 'Check the cracked handle' });
});

test('journaled HTTP 409 preserves original note request key when operation status is review', async () => {
  let writes = 0;
  const h = harness({
    ['item-actions/status?ids=' + item]: async () => ({ items: [{ id: item, can_add_note: true }] }),
    'item-actions/note': async () => { writes++; throw Object.assign(new Error('Native write needs review'), { status: 409 }); },
    'operation/status': async () => ({ status: 'review' }),
  });
  await h.controller.open({ kind: 'note', itemId: item, source: 'row' });
  h.controller.setDraft({ note: 'Journaled note' });
  await assert.rejects(h.controller.confirm(), /review/i);
  const key = h.controller.state.requestKey;
  assert.equal(h.controller.state.phase, 'uncertain');
  assert.equal(h.controller.pendingActions()[0].request_key, key);
  await assert.rejects(h.controller.open({ kind: 'note', itemId: item, source: 'row' }), /unresolved/i);
  await h.controller.reconcile();
  assert.equal(h.controller.state.requestKey, key);
  assert.equal(h.controller.pendingActions()[0].request_key, key);
  assert.equal(writes, 1);
  assert.ok(h.calls.filter(row => row.path === 'operation/status').length >= 2);
});

test('HTTP 409 plus operation not_started safely returns to review without resubmitting', async () => {
  let writes = 0;
  const h = harness({
    ['item-actions/status?ids=' + item]: async () => ({ items: [{ id: item, availability: 'available' }] }),
    'item-actions/verify-badge': async () => ({ verification_id: 'proof', required_items: [item] }),
    'item-actions/verify-item': async () => ({ verified_items: [item] }),
    'item-actions/checkout': async () => { writes++; throw Object.assign(new Error('Request rejected'), { status: 409 }); },
    'operation/status': async () => ({ status: 'not_started' }),
  });
  await h.controller.open({ kind: 'checkout', itemId: item, source: 'row' });
  await h.controller.verifyBadge('badge'); await h.controller.verifyItem('code');
  await assert.rejects(h.controller.confirm());
  const key = h.calls.find(row => row.path === 'item-actions/checkout').body.request_key;
  assert.equal(h.controller.state.phase, 'review');
  assert.equal(h.controller.state.requestKey, null);
  assert.equal(h.controller.state.verificationId, null);
  assert.equal(h.controller.pendingActions().length, 0);
  assert.equal(writes, 1);
  assert.ok(h.calls.some(row => row.path === 'operation/status' && row.body.request_key === key));
});

test('reloaded checkout not_started refreshes status and preserves draft for a reviewed retry', async () => {
  const h = harness({
    ['item-actions/status?ids=' + item]: async () => ({ items: [{ id: item, availability: 'available' }] }),
    'operation/status': async () => ({ status: 'not_started' }),
    'item-actions/verify-badge': async () => ({ verification_id: 'fresh-proof', required_items: [item] }),
  });
  const row = { path:'item-actions/checkout', request_key:'reload-key', kind:'checkout', item_ids:[item], identity:'session-a', group_id:'group-a', user_id:'user-a', payload:{notes:{[item]:'Keep my checkout note'}} };
  h.storage.setItem('workshop-item-action:group-a:user-a', JSON.stringify([row]));
  h.controller.recoverPending(row);
  assert.equal(h.controller.state.status[0].availability, 'unknown');
  await h.controller.reconcile();
  assert.equal(h.controller.state.phase, 'review');
  assert.equal(h.controller.state.status[0].availability, 'available');
  assert.equal(h.controller.state.draft.notes[item], 'Keep my checkout note');
  assert.equal(h.controller.state.dirty, true);
  assert.equal(h.controller.close(), false);
  await h.controller.verifyBadge('badge');
  assert.equal(h.controller.state.verificationId, 'fresh-proof');
  assert.equal(h.controller.state.draft.notes[item], 'Keep my checkout note');
});

test('corrupt or unavailable pending storage fails closed without overwriting or mutating', async () => {
  const cases = [
    { storage: { raw: '{broken', writes: 0, getItem() { return this.raw; }, setItem() { this.writes++; throw new Error('must not overwrite'); } }, snapshot: value => value.raw },
    { storage: { writes: 0, getItem() { throw new Error('storage unavailable'); }, setItem() { this.writes++; throw new Error('storage unavailable'); } }, snapshot: value => { try { return value.getItem(); } catch { return 'unavailable'; } } },
  ];
  for (const { storage, snapshot } of cases) {
    const initial = snapshot(storage);
    let requests = 0;
    const request = async () => { requests++; return {}; };
    const controller = createItemActionController({ getContext: () => context, uuid, storage, request });
    await assert.rejects(controller.open({ kind: 'note', itemId: item, source: 'row' }), /storage|saved|pending/i);
    assert.equal(requests, 0);
    assert.equal(storage.writes, 0);
    assert.equal(snapshot(storage), initial);
    assert.match(controller.pendingError(), /storage/i);
  }
});

test('late badge proof after same-user native identity rotation cannot revive closed flow', async () => {
  const contextRef = { value: context };
  let resolveProof;
  const h = harness({
    ['item-actions/status?ids=' + item]: async () => ({ items: [{ id: item, availability: 'available' }] }),
    'item-actions/verify-badge': async () => new Promise(resolve => { resolveProof = resolve; }),
  }, contextRef);
  await h.controller.open({ kind: 'checkout', itemId: item, source: 'row' });
  const pending = h.controller.verifyBadge('badge');
  contextRef.value = { ...context, identity: 'rotated-native-token' };
  h.controller.syncContext();
  resolveProof({ verification_id: 'old-proof', required_items: [item] });
  await pending;
  assert.equal(h.controller.state.phase, 'closed');
  assert.equal(h.controller.state.verificationId, null);
});

test('stale pending receipt cannot be recovered after reconciliation cleared its durable row', async () => {
  const first = harness({
    ['item-actions/status?ids=' + item]: async () => ({ items: [{ id: item, availability: 'available' }] }),
    'item-actions/verify-badge': async () => ({ verification_id: 'proof', required_items: [item] }),
    'item-actions/verify-item': async () => ({ verified_items: [item] }),
    'item-actions/checkout': async () => { throw new Error('connection lost'); },
  });
  await first.controller.open({ kind: 'checkout', itemId: item, source: 'row' });
  await first.controller.verifyBadge('badge'); await first.controller.verifyItem('code'); await assert.rejects(first.controller.confirm());
  const stale = first.controller.pendingActions()[0];
  const recovered = createItemActionController({ getContext: () => context, uuid, storage: first.storage, request: async () => ({ status: 'completed', result: { status: 'completed' } }) });
  recovered.recoverPending(stale);
  await recovered.reconcile();
  assert.throws(() => recovered.recoverPending(stale), /no longer|saved action|stored/i);
});

test('mixed item activity notes show the latest five and ignore other units in kit history', () => {
  const notes = recentItemNotes([
    { action: 'check_out', checkout_notes: [{ entity_id: item, text: 'checkout', author: 'A', created_at: '2026-10-01T00:00:00Z' }, { entity_id: 'other', text: 'other checkout', created_at: '2026-10-04T00:00:00Z' }] },
    { action: 'return', return_notes: [{ entity_id: item, text: 'return', created_at: '2026-10-02T00:00:00Z' }, { entity_id: 'other', text: 'other return', created_at: '2026-10-05T00:00:00Z' }] },
    { action: 'add_note', note_text: 'standalone', note_author: 'B', note_state: 'current', note_current_text_attribution: 'journaled', created_at: '2026-10-03T00:00:00Z' },
    { action: 'add_note', note_text: 'externally edited', note_state: 'edited', note_current_text_attribution: 'unknown', created_at: '2026-10-07T00:00:00Z' },
    ...[4, 5, 6].map(day => ({ action: 'add_note', note_text: `note-${day}`, created_at: `2026-10-0${day}T00:00:00Z` })),
  ], item);
  assert.deepEqual(notes.map(note => note.text), ['note-6', 'note-5', 'note-4', 'standalone', 'return']);
  assert.ok(notes.every(note => note.note_state !== 'edited' && note.note_current_text_attribution !== 'unknown'), 'unattributed externally edited native text must not appear as an authored note');
  assert.deepEqual(notes.map(note => note.kind), ['item', 'item', 'item', 'item', 'return']);
  assert.equal(recentItemNotes([
    { action: 'check_out', checkout_notes: [{ entity_id: item, text: 'checkout', created_at: '2026-10-01T00:00:00Z' }] },
    { action: 'return', return_notes: [{ entity_id: item, text: 'return', created_at: '2026-10-02T00:00:00Z' }] },
    { action: 'add_note', note_text: 'standalone', created_at: '2026-10-03T00:00:00Z' },
    ...[4,5,6,7].map(day => ({ action: 'add_note', note_text: `older-${day}`, created_at: `2026-10-0${day}T00:00:00Z` })),
  ], item, 1).length, 1, 'compact rows show one latest note');
  assert.equal(notes.length, 5, 'item details show five recent notes');
  assert.equal(recentItemNotes([
    { action: 'check_out', checkout_notes: [{ entity_id: item, text: 'checkout', created_at: '2026-10-01T00:00:00Z' }] },
    { action: 'return', return_notes: [{ entity_id: item, text: 'return', created_at: '2026-10-02T00:00:00Z' }] },
    { action: 'add_note', note_text: 'standalone', created_at: '2026-10-03T00:00:00Z' },
    ...[4,5,6,7].map(day => ({ action: 'add_note', note_text: `older-${day}`, created_at: `2026-10-0${day}T00:00:00Z` })),
  ], item, Infinity).length, 7, 'the full activity route can render note text older than the compact five-row preview');
});
