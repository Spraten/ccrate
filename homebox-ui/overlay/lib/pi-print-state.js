export function getPiPrintRecoveryState(pendingActions, subject) {
  const uncertain = Array.isArray(pendingActions) && pendingActions.some(action =>
    action?.path === 'labels/print' && action.subject === subject,
  );
  return { canReview: !uncertain, uncertain };
}

export function getPiPrintContextChange(next, previous) {
  const itemChanged = next.entityId !== previous.entityId;
  const accountChanged = next.identity !== previous.identity || next.groupId !== previous.groupId;
  return { changed: itemChanged || accountChanged, itemChanged, accountChanged };
}

export function isPiPrintOwnerCurrent(run, current) {
  return run.operationId === current.operationId
    && run.entityId === current.entityId
    && run.identity === current.identity
    && run.groupId === current.groupId;
}

