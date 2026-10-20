const GENERATED_ID_PATTERN = /^[A-Z0-9][A-Z0-9_-]*-[1-9][0-9]*$/i;

/** Copy persisted display IDs onto assigned rows; leave native-only legacy rows intact. */
export function projectAssignedDisplayIds(items, assignments) {
  return (items || []).map(item => {
    const assignment = assignments?.[item?.id];
    if (!assignment || typeof assignment.display_id !== 'string' || !assignment.display_id) return item;
    return { ...item, displayId: assignment.display_id };
  });
}

/** Fetch scoped assignment mappings in the API's maximum batch size. */
export async function fetchAssignedDisplayIds(entityIds, fetchBatch, batchSize = 100) {
  if (!Number.isInteger(batchSize) || batchSize < 1 || batchSize > 100) throw new Error('Assignment batches must contain 1 to 100 UUIDs.');
  const ids = [...new Set((entityIds || []).filter(id => typeof id === 'string' && id))];
  const assignments = {};
  for (let start = 0; start < ids.length; start += batchSize) {
    const batch = await fetchBatch(ids.slice(start, start + batchSize));
    if (batch && typeof batch === 'object') Object.assign(assignments, batch);
  }
  return assignments;
}

/** Resolve only an exact generated-ID miss, preserving Homebox search precedence. */
export async function resolveAssignedIdAfterNativeMiss(query, nativeItems, resolve, isCurrent = () => true) {
  if (Array.isArray(nativeItems) && nativeItems.length) return null;
  if (!isCurrent()) return null;
  const displayId = String(query || '').trim();
  if (!GENERATED_ID_PATTERN.test(displayId)) return null;
  try {
    const result = await resolve(displayId);
    if (!isCurrent()) return null;
    return typeof result?.entity_id === 'string' && result.entity_id ? result.entity_id : null;
  } catch {
    return null;
  }
}
