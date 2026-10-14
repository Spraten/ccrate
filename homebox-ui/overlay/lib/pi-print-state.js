export function getPiPrintRecoveryState(pendingActions, subject) {
  const uncertain = Array.isArray(pendingActions) && pendingActions.some(action =>
    action?.path === 'labels/print' && action.subject === subject,
  );
  return { canReview: !uncertain, uncertain };
}

