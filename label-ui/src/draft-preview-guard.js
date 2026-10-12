export function isSameDocumentSnapshot(left, right) {
  return JSON.stringify(left) === JSON.stringify(right)
}

export function createDraftPreviewGuard() {
  let revision = 0
  return {
    begin() { return ++revision },
    invalidate() { revision++ },
    accepts(requestRevision, disposed = false) { return !disposed && requestRevision === revision },
  }
}
