export function feedbackActionIsCurrent(capture, current) {
  return !!capture?.actorId && capture.actorId === current.actorId &&
    capture.draftKey === current.draftKey && capture.requestId === current.requestId;
}

export function writeFeedbackDraft(storage, key, draft) {
  try {
    storage.setItem(key, JSON.stringify(draft));
    return true;
  } catch {
    return false;
  }
}
