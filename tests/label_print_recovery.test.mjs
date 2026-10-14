import test from 'node:test';
import assert from 'node:assert/strict';
import { labelPrintFailure, pendingLabelPrint } from '../homebox-ui/overlay/lib/label-print-recovery.js';

test('confirmed-not-started print failure surfaces the error and allows retry', () => {
  const state = labelPrintFailure(new Error('Printer is unavailable.'), [], 'request-a');
  assert.deepEqual(state, { uncertain: false, locked: false, message: 'Printer is unavailable.' });
});

test('uncertain print failure stays locked and exposes recovery guidance', () => {
  const saved = [{ key: 'request-a', path: 'labels/print' }];
  const state = labelPrintFailure(new Error('No confirmation received.'), saved, 'request-a');
  assert.equal(state.uncertain, true);
  assert.equal(state.locked, true);
  assert.match(state.message, /may have reached the printer/i);
  assert.equal(pendingLabelPrint(saved), true);
});

test('other saved workshop actions do not lock the label print queue', () => {
  assert.equal(pendingLabelPrint([{ key: 'request-b', path: 'workshop/save' }]), false);
});
