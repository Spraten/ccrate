export function pendingLabelPrint(actions) {
  return actions.some(action => action.path === 'labels/print');
}

export function labelPrintFailure(error, actions, requestKey) {
  const uncertain = actions.some(action => action.key === requestKey && action.path === 'labels/print');
  const detail = error?.message || String(error);
  return {
    uncertain,
    locked: uncertain,
    message: uncertain
      ? `${detail} The print may have reached the printer. Check Recovery and inspect the physical label before retrying.`
      : detail,
  };
}
