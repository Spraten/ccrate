import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('a confirmed-unsent Pi print unlocks after a fresh review, while unresolved matching prints stay locked', async () => {
  const component = await readFile(new URL('../homebox-ui/overlay/components/Workshop/PiPrint.vue', import.meta.url), 'utf8');
  assert.match(component, /getPiPrintRecoveryState/, 'PiPrint must use the tested request-state helper');
  assert.match(component, /getPiPrintRecoveryState\(workshop\.pending\(\), itemId\.value\)/, 'review must derive its lock from pending requests');
  assert.match(component, /preview\.value = null;\s*uncertain\.value = getPiPrintRecoveryState\(workshop\.pending\(\), entityId\)\.uncertain/, 'a failed print must require a fresh preview and retain a lock only when its request is still pending');
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

