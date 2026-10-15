import test from 'node:test';
import assert from 'node:assert/strict';
import { labelPrintFailure, pendingLabelPrint, labelReviewCanPrint, submitReviewedLabel, applyLabelPreview } from '../homebox-ui/overlay/lib/label-print-recovery.js';

test('confirmed-not-started print failure surfaces the error and allows retry', () => {
  const state = labelPrintFailure(new Error('Printer is unavailable.'), [], 'request-a');
  assert.deepEqual(state, { uncertain: false, locked: false, invalidateReview: true, message: 'Printer is unavailable.' });
});

test('uncertain print failure stays locked and exposes recovery guidance', () => {
  const saved = [{ key: 'request-a', path: 'labels/print' }];
  const state = labelPrintFailure(new Error('No confirmation received.'), saved, 'request-a');
  assert.equal(state.uncertain, true);
  assert.equal(state.locked, true);
  assert.equal(state.invalidateReview, false);
  assert.match(state.message, /may have reached the printer/i);
  assert.equal(pendingLabelPrint(saved), true);
});

test('other saved workshop actions do not lock the label print queue', () => {
  assert.equal(pendingLabelPrint([{ key: 'request-b', path: 'workshop/save' }]), false);
});

test('confirmed-unsent retry requires a fresh preview while keeping successful labels suppressed', async () => {
  const queue = { reviews: [{ entity_id: 'A', review_id: 'a-old' }, { entity_id: 'B', review_id: 'b-old' }], printedReviewIds: ['a-old'], printedEntityIds: [] };
  const printed = [];
  queue.printedEntityIds.push('A');
  const failed = labelPrintFailure(new Error('Printer unavailable'), [], 'b-request', queue);
  assert.equal(failed.invalidateReview, true);
  assert.deepEqual(queue.reviews, []);
  assert.deepEqual(queue.printedEntityIds, ['A']);
  await assert.rejects(submitReviewedLabel(queue, 'B', 'b-old', async () => printed.push('B')));
  let previewCalls = 0;
  const freshPreview = async () => {
    previewCalls++;
    return applyLabelPreview(queue, ['A', 'B'], { reviews: [{ review_id: 'a-new' }, { review_id: 'b-new' }] });
  };
  await freshPreview();
  assert.equal(previewCalls, 1);
  await assert.rejects(submitReviewedLabel(queue, 'A', 'a-new', async () => printed.push('A')));
  await submitReviewedLabel(queue, 'B', 'b-new', async () => printed.push('B'));
  assert.deepEqual(printed, ['B']);
  assert.equal(labelReviewCanPrint(queue, 'B', 'b-new'), false);
});

test('uncertain failure keeps the queue locked and cannot reuse a review', async () => {
  const queue = { reviews: [{ entity_id: 'B', review_id: 'b-old' }], printedReviewIds: [], printedEntityIds: [] };
  const failed = labelPrintFailure(new Error('No response'), [{ key: 'b-request', path: 'labels/print' }], 'b-request', queue);
  assert.equal(failed.locked, true);
  await assert.rejects(submitReviewedLabel(queue, 'B', 'b-old', async () => {}));
  assert.equal(queue.reviews[0].review_id, 'b-old');
});
