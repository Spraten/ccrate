const fold = value => String(value ?? '').trim().replace(/\s+/gu, ' ').toLocaleLowerCase();

/** Match custom field labels and values within already-projected native records. */
export function matchInventoryCustomFields(items = [], query = '') {
  const needle = fold(query);
  if (!needle) return [];
  return items.filter(item => (Array.isArray(item.fields) ? item.fields : []).some(field =>
    fold(field?.name).includes(needle) || fold(field?.textValue).includes(needle)
  ));
}

function groupTag(item) {
  const tag = (item.tags || []).find(value => typeof value?.name === 'string' && value.name.toLocaleLowerCase().startsWith('c-crate product group: '));
  return tag?.name.slice('C-Crate Product group: '.length).trim() || '';
}

/** Create a component-scoped, bounded detail hydrator. Successful metadata is cached by record version. */
export function createChildItemHydrator(fetchDetail, concurrency = 4) {
  const cache = new Map();
  const limit = Math.max(1, Math.floor(concurrency) || 1);
  let active = 0;
  const queue = [];
  function pump() {
    while (active < limit && queue.length) {
      const task = queue.shift();
      active++;
      task();
    }
  }
  function schedule(task) {
    return new Promise((resolve, reject) => {
      queue.push(async () => {
        try { resolve(await task()); }
        catch (error) { reject(error); }
        finally {
          active--;
          pump();
        }
      });
      pump();
    });
  }
  async function hydrate(items) {
    return Promise.all(items.map(async item => {
      const key = JSON.stringify([item.id, item.updatedAt || '']);
      let detailPromise = cache.get(key);
      if (!detailPromise) {
        detailPromise = schedule(async () => {
          const result = await fetchDetail(item.id);
          const detail = result?.data ?? result;
          if (result?.error || !detail || detail.id !== item.id) throw new Error('invalid detail response');
          return {
            manufacturer: typeof detail.manufacturer === 'string' ? detail.manufacturer : '',
            modelNumber: typeof detail.modelNumber === 'string' ? detail.modelNumber : '',
            serialNumber: typeof detail.serialNumber === 'string' ? detail.serialNumber : '',
          };
        });
        cache.set(key, detailPromise);
        detailPromise.catch(() => { if (cache.get(key) === detailPromise) cache.delete(key); });
      }
      try {
        const metadata = await detailPromise;
        return { ...item, ...metadata, metadataPending: false, metadataUnavailable: false };
      } catch {
        return { ...item, metadataPending: false, metadataUnavailable: true };
      }
    }));
  }
  return hydrate;
}

/** Group only records from one already-loaded location. */
export function groupChildItems(items) {
  const groups = new Map();
  for (const item of items) {
    if (item.metadataPending || item.metadataUnavailable) {
      const key = JSON.stringify(['individual', item.id]);
      groups.set(key, { key, kind: 'individual', name: item.name || 'Unnamed item', items: [item], quantity: Number(item.quantity) || 0 });
      continue;
    }
    const custom = groupTag(item);
    const manufacturer = String(item.manufacturer || '').trim();
    const model = String(item.modelNumber || '').trim();
    const type = fold(item.entityType?.id || item.entityType?.name || item.type?.id || item.type?.name);
    let kind, name, key;
    if (custom) {
      kind = 'product'; name = custom; key = JSON.stringify(['product', type, fold(custom)]);
    } else if (manufacturer && model) {
      kind = 'model'; name = `${manufacturer} · ${model}`; key = JSON.stringify(['model', type, fold(manufacturer), fold(model)]);
    } else {
      kind = 'name'; name = item.name || 'Unnamed item';
      // Keep known identity metadata in the key so same-name records with conflicting
      // known manufacturer/model data never get combined.
      key = JSON.stringify(['name', type, fold(name), fold(manufacturer), fold(model)]);
    }
    if (!groups.has(key)) groups.set(key, { key, kind, name, items: [], quantity: 0 });
    const group = groups.get(key);
    group.items.push(item);
    group.quantity += Number.isFinite(Number(item.quantity)) ? Number(item.quantity) : 0;
  }
  return [...groups.values()];
}

const inventoryStatusValues = new Set(['available', 'checked_out', 'blocked', 'archived', 'unknown']);

function productGroupTag(item) {
  const tag = (item.tags || []).find(value => typeof value?.name === 'string' && value.name.toLocaleLowerCase().startsWith('c-crate product group: '));
  return tag?.name.slice('C-Crate Product group: '.length).trim() || '';
}

function nativeType(item) {
  return fold(item.entityType?.id || item.entityType?.name || item.type?.id || item.type?.name);
}

function inventoryMetadataKey(item) {
  const manufacturer = fold(item.manufacturer), model = fold(item.modelNumber), type = nativeType(item);
  return manufacturer && model ? JSON.stringify(['model', type, manufacturer, model]) : '';
}

function inventoryIdentity(item, assignment, productAliases = new Map()) {
  const type = nativeType(item);
  const productId = assignment?.product_id || assignment?.productId;
  const custom = productGroupTag(item);
  if (custom && productAliases.has(JSON.stringify(['group', type, fold(custom)]))) {
    const aliasProductId = productAliases.get(JSON.stringify(['group', type, fold(custom)]));
    return { kind: 'product', key: JSON.stringify(['product', type, aliasProductId]), productId: productId || aliasProductId };
  }
  if (productId) return { kind: 'product', key: JSON.stringify(['product', type, productId]), productId };
  // An explicit different group tag is authoritative; do not alias it by model metadata.
  if (custom) return { kind: 'group', key: JSON.stringify(['group', type, fold(custom)]), productId: null };
  const modelKey = inventoryMetadataKey(item);
  if (modelKey && productAliases.has(modelKey)) {
    const aliasProductId = productAliases.get(modelKey);
    return { kind: 'product', key: JSON.stringify(['product', type, aliasProductId]), productId: aliasProductId };
  }
  if (item.metadataUnavailable || item.metadataPending) return { kind: 'individual', key: JSON.stringify(['individual', item.id]), productId: null };
  const manufacturer = fold(item.manufacturer), model = fold(item.modelNumber);
  if (manufacturer && model) return { kind: 'model', key: JSON.stringify(['model', type, manufacturer, model]) };
  // Unknown identity fields remain part of this fallback key, so partial metadata
  // cannot silently merge two native records with conflicting known values.
  return { kind: 'name', key: JSON.stringify(['name', type, fold(item.name || 'Unnamed item'), manufacturer, model]) };
}

function inventoryStatus(item, statusRow) {
  if (item.archived) return 'archived';
  const value = statusRow?.status || statusRow?.availability || statusRow?.equipment_status || item.equipmentStatus || (item.archived ? 'archived' : 'unknown');
  const normalized = String(value).replace(/[A-Z]/gu, letter => `_${letter.toLowerCase()}`).toLocaleLowerCase().replace(/^_/, '');
  return inventoryStatusValues.has(normalized) ? normalized : 'unknown';
}

/** Load the same authoritative action status used by item action controls. */
export async function loadInventoryActionStatuses(entityIds, request, options = {}) {
  const ids = [...new Set((entityIds || []).filter(id => typeof id === 'string' && id))];
  const isCurrent = typeof options.isCurrent === 'function' ? options.isCurrent : () => true;
  const concurrency = Math.max(1, Math.min(4, Math.floor(Number(options.concurrency) || 4)));
  const chunks = [];
  for (let index = 0; index < ids.length; index += 50) chunks.push(ids.slice(index, index + 50));
  const results = new Array(chunks.length);
  let next = 0, failure = null;
  async function worker() {
    while (!failure) {
      if (!isCurrent()) throw new Error('Inventory status result is stale');
      const index = next++;
      if (index >= chunks.length) return;
      try {
        const raw = await request(chunks[index]);
        if (!isCurrent()) throw new Error('Inventory status result is stale');
        const rows = Array.isArray(raw) ? raw : raw?.items;
        if (!Array.isArray(rows) || rows.length !== chunks[index].length
          || rows.some((row, rowIndex) => row?.id !== chunks[index][rowIndex])) {
          throw new Error('Inventory status response did not match the requested records');
        }
        results[index] = rows;
      } catch (error) { failure = error; }
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, chunks.length) }, worker));
  if (failure) throw failure;
  if (!isCurrent()) throw new Error('Inventory status result is stale');
  return Object.fromEntries(results.flat().map(row => [row.id, row]));
}

function nativePhoto(item) {
  if (item.imageId || item.thumbnailId) return { entity_id: item.id, attachment_id: item.thumbnailId || item.imageId };
  const attachments = Array.isArray(item.attachments) ? item.attachments.filter(row => row?.type === 'photo' && row.id) : [];
  const photo = attachments.find(row => row.primary) || attachments[0];
  return photo ? { entity_id: item.id, attachment_id: photo.id, thumbnail_id: photo.thumbnail?.id } : null;
}

export function buildInventoryStoragePath(item, records = []) {
  const byId = records instanceof Map ? records : new Map((records || []).map(row => [row.id, row]));
  let parent = item?.parent || byId.get(item?.parentId);
  const parts = [], seen = new Set();
  while (parent && parent.id && !seen.has(parent.id)) {
    seen.add(parent.id);
    const full = byId.get(parent.id) || parent;
    if (full.name) parts.unshift(full.name);
    parent = full.parent || byId.get(full.parentId);
  }
  return parts.join(' / ');
}

export function mergeInventorySummaries(summaries = [], fullRecords = []) {
  const byId = fullRecords instanceof Map ? fullRecords : new Map((fullRecords || []).map(row => [row.id, row]));
  return (summaries || []).map(summary => {
    const full = byId.get(summary.id);
    return full ? { ...summary, ...full, metadataUnavailable: false } : { ...summary, metadataUnavailable: true };
  });
}

/** Fetch matching native records and only the ancestors needed for storage paths. */
export async function loadScopedInventoryDetails(summaries, fetchDetail, options = {}) {
  const isCurrent = typeof options.isCurrent === 'function' ? options.isCurrent : () => true;
  const concurrency = Math.max(1, Math.min(4, Math.floor(Number(options.concurrency) || 4)));
  const records = new Map();
  const attempted = new Set();
  let pending = [...new Set((summaries || []).map(item => item?.id).filter(Boolean))];
  while (pending.length) {
    if (!isCurrent()) throw new Error('Inventory detail load is stale');
    const batch = pending.filter(id => !attempted.has(id));
    batch.forEach(id => attempted.add(id));
    let next = 0;
    await Promise.all(Array.from({ length: Math.min(concurrency, batch.length) }, async () => {
      while (next < batch.length) {
        if (!isCurrent()) return;
        const id = batch[next++];
        try {
          const detail = await fetchDetail(id);
          if (detail?.id === id) records.set(id, detail);
        } catch { /* Keep the native summary when optional detail is unavailable. */ }
      }
    }));
    if (!isCurrent()) throw new Error('Inventory detail load is stale');
    pending = [...new Set([...(summaries || []), ...records.values()]
      .map(item => item.parent?.id || item.parentId).filter(id => id && !attempted.has(id)))];
  }
  return [...records.values()];
}

export function inventoryNoteRequestKey(groupKey, entityIds = []) {
  return JSON.stringify([groupKey, [...new Set(entityIds)].sort()]);
}

/** Track mixed-history requests by native unit so overlapping scopes cannot overwrite newer notes. */
export function createInventoryNoteVersionGuard() {
  const versions = new Map();
  return {
    begin(entityIds = []) {
      const snapshot = new Map();
      for (const id of new Set(entityIds)) {
        const version = (versions.get(id) || 0) + 1;
        versions.set(id, version);
        snapshot.set(id, version);
      }
      return snapshot;
    },
    isCurrent(snapshot, entityId) { return snapshot?.get(entityId) === versions.get(entityId); },
  };
}

export function indexLatestInventoryNotes(rows = []) {
  const result = {};
  for (const row of [...rows].sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))) {
    if (typeof row?.entity_id === 'string' && typeof row?.text === 'string' && row.text.trim() && !result[row.entity_id]) result[row.entity_id] = row;
  }
  return result;
}

/**
 * Group one complete, already Homebox-filtered inventory result. Search and
 * status filters choose matching units, then search includes their peers
 * within that result so the matching unit stays visible in its group.
 */
export function groupInventoryItems(items, productAssignments = {}, options = {}) {
  const query = fold(options.query), statusFilter = options.filters?.status || '';
  const storagePath = typeof options.storagePath === 'function' ? options.storagePath : () => '';
  const statuses = options.statuses || {};
  const templateThumbnails = options.templateThumbnails || {};
  const matchedIds = options.matchedEntityIds ? new Set(options.matchedEntityIds) : null;
  const aliasCandidates = new Map();
  for (const native of items || []) {
    const assignment = productAssignments?.[native.id];
    const productId = assignment?.product_id || assignment?.productId;
    if (!productId) continue;
    const keys = [inventoryMetadataKey(native)];
    const custom = productGroupTag(native);
    if (custom) keys.push(JSON.stringify(['group', nativeType(native), fold(custom)]));
    for (const key of keys.filter(Boolean)) {
      if (!aliasCandidates.has(key)) aliasCandidates.set(key, new Set());
      aliasCandidates.get(key).add(productId);
    }
  }
  const productAliases = new Map([...aliasCandidates].filter(([, ids]) => ids.size === 1).map(([key, ids]) => [key, [...ids][0]]));
  const groups = new Map();
  for (const native of items || []) {
    const assignment = productAssignments?.[native.id] || null;
    const identity = inventoryIdentity(native, assignment, productAliases);
    const statusRow = statuses[native.id] || null;
    const status = inventoryStatus(native, statusRow);
    if (statusFilter && statusFilter !== status) continue;
    const unit = {
      ...native,
      productId: identity.productId || null,
      displayId: assignment?.display_id || assignment?.displayId || native.displayId || native.assetId || '',
      status,
      statusDetails: statusRow,
      storagePath: storagePath(native) || '',
      thumbnail: nativePhoto(native),
      recentNote: options.recentNotes?.[native.id] || null,
    };
    unit.thumbnail ||= templateThumbnails[unit.productId] || null;
    const searchText = fold([
      native.name, native.assetId, native.serialNumber, native.manufacturer, native.modelNumber,
      unit.displayId, unit.storagePath, productGroupTag(native),
    ].join(' '));
    const matchesQuery = !query || (matchedIds ? matchedIds.has(native.id) || fold(unit.displayId).includes(query) : searchText.includes(query));
    if (!groups.has(identity.key)) groups.set(identity.key, {
      key: identity.key,
      kind: identity.kind,
      name: productGroupTag(native) || (native.manufacturer && native.modelNumber ? `${native.manufacturer} · ${native.modelNumber}` : native.name || 'Unnamed item'),
      productId: unit.productId,
      items: [],
      recordCount: 0,
      nativeQuantity: 0,
      statusCounts: { available: 0, checked_out: 0, blocked: 0, archived: 0, unknown: 0 },
      thumbnail: null,
      locations: [],
      queryMatch: false,
    });
    const group = groups.get(identity.key);
    if (!group.productId && unit.productId) group.productId = unit.productId;
    group.items.push(unit);
    group.recordCount++;
    const quantity = Number(native.quantity);
    group.nativeQuantity += Number.isFinite(quantity) ? quantity : 0;
    group.statusCounts[status]++;
    if (unit.storagePath && !group.locations.includes(unit.storagePath)) group.locations.push(unit.storagePath);
    group.queryMatch ||= matchesQuery;
    if (!group.thumbnail && unit.thumbnail) group.thumbnail = unit.thumbnail;
  }
  return [...groups.values()].filter(group => !query || group.queryMatch).map(({ queryMatch, ...group }) => ({
    ...group,
    locationSummary: group.locations.length > 1 ? 'Multiple locations' : group.locations[0] || 'Location unknown',
  }));
}

/** Fetch every page of an already-filtered native result, publishing nothing on partial failure. */
export async function loadAllFilteredInventory(fetchPage, options = {}) {
  const pageSize = Math.max(1, Math.floor(Number(options.pageSize) || 100));
  const concurrency = Math.max(1, Math.min(4, Math.floor(Number(options.concurrency) || 4)));
  const isCurrent = typeof options.isCurrent === 'function' ? options.isCurrent : () => true;
  const checkCurrent = () => { if (!isCurrent()) throw new Error('Inventory page load is stale'); };
  checkCurrent();
  const first = await fetchPage(1, pageSize);
  checkCurrent();
  if (!first || !Array.isArray(first.items) || !Number.isFinite(Number(first.total))) throw new Error('Invalid inventory page response');
  const total = Math.max(0, Math.floor(Number(first.total)));
  const pageCount = Math.ceil(total / pageSize);
  if (first.items.length !== Math.min(total, pageSize)) throw new Error('Incomplete inventory page response');
  const validateIds = items => {
    const ids = items.map(item => item?.id).filter(value => typeof value === 'string' && value);
    if (ids.length !== items.length || new Set(ids).size !== ids.length) throw new Error('Inventory pages contain missing or duplicate entity UUIDs');
    return items;
  };
  if (pageCount <= 1) return validateIds(first.items);
  const pages = new Array(pageCount);
  pages[0] = first.items;
  let next = 2;
  let failure = null;
  async function worker() {
    while (!failure) {
      checkCurrent();
      const page = next++;
      if (page > pageCount) return;
      try {
        const result = await fetchPage(page, pageSize);
        checkCurrent();
      const expected = Math.min(pageSize, total - (page - 1) * pageSize);
        if (!result || !Array.isArray(result.items) || Number(result.total) !== total || result.items.length !== expected) throw new Error('Incomplete inventory page response');
        pages[page - 1] = result.items;
      } catch (error) { failure = error; }
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, pageCount - 1) }, worker));
  checkCurrent();
  if (failure) throw failure;
  const items = pages.flat();
  if (items.length !== total) throw new Error('Incomplete inventory result');
  return validateIds(items);
}
