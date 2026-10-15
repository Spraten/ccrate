import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('a confirmed-unsent Pi print unlocks after a fresh review, while unresolved matching prints stay locked', async () => {
  const component = await readFile(new URL('../homebox-ui/overlay/components/Workshop/PiPrint.vue', import.meta.url), 'utf8');
  assert.match(component, /getPiPrintRecoveryState/, 'PiPrint must use the tested request-state helper');
  assert.match(component, /getPiPrintRecoveryState\(workshop\.pending\(\), itemId\.value\)/, 'review must derive its lock from pending requests');
  assert.match(component, /preview\.value = null;\s*uncertain\.value = getPiPrintRecoveryState\(workshop\.pending\(\), run\.entityId\)\.uncertain/, 'a failed print must require a fresh preview and retain a lock only when its request is still pending');
  const { getPiPrintRecoveryState } = await import('../homebox-ui/overlay/lib/pi-print-state.js');

  let state = { preview: null, uncertain: true };
  state = { ...state, ...getPiPrintRecoveryState([], 'item-1') };
  assert.deepEqual(state, { preview: null, uncertain: false, canReview: true }, 'after a confirmed-unsent failure, a new review clears the stale lock and permits a fresh preview');

  state = { ...state, ...getPiPrintRecoveryState([
    { path: 'labels/print', subject: 'item-1' },
  ], 'item-1') };
  assert.equal(state.uncertain, true, 'an unresolved print for this item must remain locked');
  assert.equal(state.canReview, false, 'a fresh preview must not be offered while the outcome is unresolved');

  state = { ...state, ...getPiPrintRecoveryState([
    { path: 'labels/print', subject: 'item-2' },
    { path: 'workshop/save', subject: 'item-1' },
  ], 'item-1') };
  assert.equal(state.uncertain, false, 'unrelated pending operations must not lock this item');
  assert.equal(state.canReview, true);
});

test('an in-flight Pi print callback is current only for the captured item and account context', async () => {
  const component = await readFile(new URL('../homebox-ui/overlay/components/Workshop/PiPrint.vue', import.meta.url), 'utf8');
  assert.equal((component.match(/if \(!isCurrentPrintOwner\(run\)\) return;/g) || []).length, 2, 'print success and failure must remain visible for the submitted item/account operation');
  assert.match(component, /current !== generation/, 'preview callbacks remain guarded by preview generation');
  assert.match(component, /finally\s*\{\s*if \(isCurrentPrintOwner\(run\)\) sending\.value = false;/, 'an obsolete completion must not unlock a newer print');
  assert.match(component, /watch\(\(\) => \[itemId\.value, workshop\.context\.value\?\.identity, workshop\.context\.value\?\.group\.id\], contextChanged\)/, 'the watcher must compare effective item and account values');
  assert.match(component, /if \(!change\.changed\) return;/, 'replacing context with an equivalent object must not invalidate an in-flight print');
  assert.match(component, /finally\s*\{\s*if \(isCurrentPrintOwner\(run\)\) sending\.value = false;/, 'template or review generation changes must not strand the owned print in a sending state');
  const { getPiPrintContextChange, isPiPrintOwnerCurrent } = await import('../homebox-ui/overlay/lib/pi-print-state.js');
  const run = { generation: 4, entityId: 'item-1', identity: 'account-A', groupId: 'group-A' };

  const sameValuesAfterRefresh = { ...run };
  const refreshChange = getPiPrintContextChange(sameValuesAfterRefresh, run);
  assert.equal(refreshChange.changed, false, 'fresh context objects with equal effective values must leave the print current');
  for (const change of [
    { entityId: 'item-2' },
    { identity: 'account-B' },
    { groupId: 'group-B' },
  ]) {
    const contextChange = getPiPrintContextChange({ ...run, ...change }, run);
    assert.equal(contextChange.changed, true, 'actual context changes must invalidate the callback');
  }

  const pendingPrint = { operationId: 8, ...run };
  const templateChangedWhilePending = { ...run, generation: run.generation + 1 };
  assert.notEqual(pendingPrint.generation, templateChangedWhilePending.generation, 'template changes advance preview generation');
  assert.equal(isPiPrintOwnerCurrent(pendingPrint, { ...templateChangedWhilePending, operationId: 8 }), true, 'a template switch must preserve the submitted print outcome');
  let sending = true;
  await assert.rejects(async () => {
    try {
      await Promise.reject(new Error('context refresh failed'));
    } finally {
      if (isPiPrintOwnerCurrent(pendingPrint, { ...templateChangedWhilePending, operationId: 8 })) sending = false;
    }
  }, /context refresh failed/);
  assert.equal(sending, false, 'the owning failed refresh must still release sending after a template change');
  assert.equal(isPiPrintOwnerCurrent(pendingPrint, { ...templateChangedWhilePending, operationId: 9 }), false, 'an old completion must not release a newer print');
  assert.equal(isPiPrintOwnerCurrent(pendingPrint, { ...templateChangedWhilePending, identity: 'account-B', operationId: 8 }), false, 'an account change invalidates print ownership');
  assert.equal(isPiPrintOwnerCurrent(pendingPrint, { ...templateChangedWhilePending, entityId: 'item-2', operationId: 8 }), false, 'an item change suppresses the submitted print result');
  assert.equal(isPiPrintOwnerCurrent(pendingPrint, { ...templateChangedWhilePending, groupId: 'group-B', operationId: 8 }), false, 'a collection change suppresses the submitted print result');
});

