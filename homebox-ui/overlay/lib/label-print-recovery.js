export function pendingLabelPrint(actions) {
  return actions.some(action => action.path === 'labels/print');
}

export function labelPrintFailure(error, actions, requestKey, queue) {
  const detail = error?.message || String(error);
  const uncertain = pendingLabelPrint(actions) || /printer request is unresolved/i.test(detail);
  const state = {
    uncertain,
    locked: uncertain,
    invalidateReview: !uncertain,
    message: uncertain
      ? `${detail} The print may have reached the printer. Check Recovery and inspect the physical label before retrying.`
      : detail,
  };
  if (queue) {
    if (state.invalidateReview) {
      queue.printedEntityIds = [...new Set([
        ...(queue.printedEntityIds || []),
        ...(queue.reviews || []).filter(row => (queue.printedReviewIds || []).includes(row.review_id)).map(row => row.entity_id),
      ])];
      queue.reviews = [];
      queue.printedReviewIds = [];
    }
    queue.printLocked = state.locked;
    queue.printUncertain = state.uncertain;
    queue.printError = state.message;
  }
  return state;
}

export function labelReviewCanPrint(queue, entityId, reviewId) {
  return !queue.printLocked
    && !(queue.printedReviewIds || []).includes(reviewId)
    && !(queue.printedEntityIds || []).includes(entityId)
    && (queue.reviews || []).some(row => row.entity_id === entityId && row.review_id === reviewId);
}

export async function submitReviewedLabel(queue, entityId, reviewId, submit) {
  if (!labelReviewCanPrint(queue, entityId, reviewId)) {
    throw new Error('Review the current selection again before printing.');
  }
  if (await submit() === false) return false;
  queue.printedReviewIds.push(reviewId);
  queue.printedEntityIds.push(entityId);
  return true;
}

export function applyLabelPreview(queue, entityIds, result) {
  const reviews = result?.reviews || (result?.review_id ? [result] : []);
  if (reviews.length !== entityIds.length) {
    throw new Error('The complete label preview was not returned. Review the selected items again.');
  }
  queue.reviews = reviews.map((row, index) => ({ ...row, entity_id: entityIds[index] }));
  return queue.reviews;
}
