const GROUP_PREFIX = 'C-Crate Product group: ';

export function equipmentRecordLabel(item) {
  return `${item.name || 'Unnamed equipment'} · ${item.assetId || 'No asset code'} · ${item.id}`;
}
const fold = value => String(value ?? '').trim().replace(/\s+/gu, ' ').toLowerCase().replace(/[ßẞ]/gu, 'ss').replace(/ς/gu, 'σ');

function customGroup(item) {
  const tag = (item.tags || []).find(tag => typeof tag.name === 'string' && tag.name.toLowerCase().startsWith(GROUP_PREFIX.toLowerCase()));
  return tag ? { name: tag.name.slice(GROUP_PREFIX.length).trim(), tagId: tag.id } : null;
}

function status(item, loanIds) {
  if (item.archived) return 'archived';
  if (loanIds.has(item.id)) return 'checkedOut';
  if (item.blocker || item.checkout_blocker || item.condition !== 'Ready' || item.quantity !== 1) return 'blocked';
  return 'available';
}

/** Project native equipment records from one loaded inventory and loan snapshot. */
export function projectEquipmentGroups(items, { loans = [], storagePath = () => '', query = '', filter = '' } = {}) {
  const needle = fold(query), loanIds = new Set(loans.map(loan => loan.entity_id)), groups = new Map();
  for (const item of items) {
    const custom = customGroup(item), manufacturer = String(item.manufacturer ?? '').trim().replace(/\s+/gu, ' '), model = String(item.modelNumber ?? '').trim().replace(/\s+/gu, ' ');
    const type = fold(item.entityType?.id || item.entityType?.name || item.type?.id || item.type?.name);
    const kind = custom ? 'custom' : manufacturer && model ? 'model' : 'individual';
    const name = custom?.name || (kind === 'model' ? `${manufacturer} · ${model}` : item.name || 'Unnamed equipment');
    const key = kind === 'custom' ? JSON.stringify([kind, type, fold(custom.name)]) : kind === 'model' ? JSON.stringify([kind, type, fold(manufacturer), fold(model)]) : JSON.stringify([kind, type, item.id]);
    const rowStatus = status(item, loanIds);
    if (filter && filter !== rowStatus && !(filter === 'loan' && rowStatus === 'checkedOut')) continue;
    if (needle && !fold([item.name, item.assetId, storagePath(item), item.manufacturer, item.modelNumber, item.serialNumber, custom?.name].join(' ')).includes(needle)) continue;
    if (!groups.has(key)) groups.set(key, { key, kind, name, tagId: custom?.tagId || null, items: [], counts: { available: 0, checkedOut: 0, blocked: 0, archived: 0 }, count: 0 });
    const group = groups.get(key);
    group.items.push(item);
    group.counts[rowStatus]++;
    group.count++;
  }
  return [...groups.values()];
}

export function groupHistoryMembers(members) {
  return [...members].sort((a, b) => a.id.localeCompare(b.id));
}

export function groupHistoryBatches(members) {
  const sorted = groupHistoryMembers(members), batches = [];
  for (let index = 0; index < sorted.length; index += 100) batches.push(sorted.slice(index, index + 100));
  return batches;
}

export async function loadGroupHistory(members, requestBatch) {
  const results = await Promise.allSettled(groupHistoryBatches(members).map(batch => requestBatch(batch.map(item => item.id))));
  const rows = [];
  let failed = false;
  for (const result of results) {
    if (result.status === 'rejected') failed = true;
    else if (Array.isArray(result.value)) rows.push(...result.value);
    else failed = true;
  }
  return { rows, failed };
}

export function groupNotesPresentation(members, rows, error = null) {
  const byId = new Map(members.map(item => [item.id, item]));
  const notes = (Array.isArray(rows) ? rows : [])
    .filter(row => byId.has(row.entity_id))
    .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
    .slice(0, 5)
    .map(row => ({ ...row, source: byId.get(row.entity_id) }));
  return { members, notes, message: error ? 'Could not load all return notes for this group. Some history may be missing.' : notes.length ? '' : 'No return notes recorded for this group.' };
}
