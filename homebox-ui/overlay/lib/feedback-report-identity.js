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

export function persistFeedbackStatus(storage, key, draft, status) {
  try {
    if (status === "submitted") {
      storage.removeItem(key);
      return true;
    }
    storage.setItem(key, JSON.stringify(draft));
    return true;
  } catch {
    return false;
  }
}
