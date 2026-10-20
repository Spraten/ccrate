import assert from 'node:assert/strict';
import test from 'node:test';
import { buildInventoryStoragePath, createInventoryNoteVersionGuard, groupInventoryItems, indexLatestInventoryNotes, inventoryNoteRequestKey, loadAllFilteredInventory, loadInventoryActionStatuses, mergeInventorySummaries } from '../homebox-ui/overlay/lib/child-item-groups.js';

const unit = (id, overrides = {}) => ({ id, name: 'DJI Air 2S', entityType: { id: 'drone', name: 'Drone' }, manufacturer: 'DJI', modelNumber: 'Air 2S', quantity: 1, ...overrides });
const path = item => item.parent?.name || 'Unassigned';

test('catalog product assignments group matching units across storage locations and count native records separately from quantity', () => {
  const items = [unit('a', { parent: { name: 'Room A' }, quantity: 2 }), unit('b', { parent: { name: 'Room B' } }), unit('c', { parent: { name: 'Workshop' } }), unit('d', { parent: { name: 'Shelf 1' } }), unit('e', { parent: { name: 'Shelf 2' } })];
  const groups = groupInventoryItems(items, { a: { product_id: 'product-1', display_id: 'DRONE-2S-1' }, b: { product_id: 'product-1', display_id: 'DRONE-2S-2' }, c: { product_id: 'product-1', display_id: 'DRONE-2S-3' }, d: { product_id: 'product-1', display_id: 'DRONE-2S-4' }, e: { product_id: 'product-1', display_id: 'DRONE-2S-5' } }, {
    storagePath: path,
    statuses: { a: { status: 'available' }, b: { status: 'checked_out' }, c: { status: 'blocked' }, d: { status: 'unknown' }, e: { status: 'available' } },
  });
  assert.equal(groups.length, 1);
  assert.equal(groups[0].recordCount, 5);
  assert.equal(groups[0].nativeQuantity, 6);
  assert.deepEqual(groups[0].statusCounts, { available: 2, checked_out: 1, blocked: 1, archived: 0, unknown: 1 });
  assert.deepEqual(groups[0].items.map(row => row.displayId), ['DRONE-2S-1', 'DRONE-2S-2', 'DRONE-2S-3', 'DRONE-2S-4', 'DRONE-2S-5']);
  assert.deepEqual(groups[0].items.map(row => row.storagePath), ['Room A', 'Room B', 'Workshop', 'Shelf 1', 'Shelf 2']);
  assert.equal(groups[0].locationSummary, 'Multiple locations');
});

test('Inventory status uses authoritative availability including recovery blockers and preserves unknown', async () => {
  const statuses = await loadInventoryActionStatuses(['recovery', 'ready', 'missing'], async ids => ({ items: ids.map(id => ({
    id, availability: id === 'recovery' ? 'blocked' : id === 'ready' ? 'available' : 'unknown',
    ...(id === 'recovery' ? { blocker: 'Checkout operation requires recovery (review)' } : {}),
  })) }));
  const [group] = groupInventoryItems([unit('recovery'), unit('ready'), unit('missing')], {}, { statuses });
  assert.equal(group.statusCounts.blocked, 1);
  assert.equal(group.statusCounts.available, 1);
  assert.equal(group.statusCounts.unknown, 1);
  assert.equal(group.items.find(row => row.id === 'recovery').statusDetails.blocker, 'Checkout operation requires recovery (review)');
});

test('Inventory action status batches at most 50 IDs and four requests and ignores stale identities', async () => {
  const ids = Array.from({ length: 206 }, (_, index) => `item-${index}`);
  let active = 0, maxActive = 0;
  const result = await loadInventoryActionStatuses(ids, async batch => {
    active++; maxActive = Math.max(active, maxActive);
    await new Promise(resolve => setTimeout(resolve, 1));
    active--;
    return { items: batch.map(id => ({ id, availability: 'available' })) };
  });
  assert.equal(Object.keys(result).length, ids.length);
  assert.ok(maxActive <= 4);
  let current = true;
  await assert.rejects(loadInventoryActionStatuses(['item-a'], async ids => {
    current = false;
    return { items: ids.map(id => ({ id, availability: 'available' })) };
  }, { isCurrent: () => current }), /stale/i);
});

test('explicit product group tags outrank metadata while same-name conflicting models remain separate', () => {
  const grouped = groupInventoryItems([
    unit('a', { tags: [{ name: 'C-Crate Product group: Red fleet' }], manufacturer: 'Maker A', modelNumber: 'Model A' }),
    unit('b', { tags: [{ name: 'C-Crate Product group: Red fleet' }], manufacturer: 'Maker B', modelNumber: 'Model B' }),
    unit('c', { name: 'Tripod', manufacturer: 'Maker', modelNumber: 'Tall' }),
    unit('d', { name: 'Tripod', manufacturer: 'Maker', modelNumber: 'Short' }),
  ], {}, {});
  assert.equal(grouped.length, 3);
  assert.equal(grouped[0].items.length, 2);
  assert.notEqual(grouped.find(row => row.items.some(item => item.id === 'c')).key, grouped.find(row => row.items.some(item => item.id === 'd')).key);
});

test('custom product groups and assignment aliases stay within the native item type', () => {
  const tag = { name: 'C-Crate Product group: Red fleet' };
  const groups = groupInventoryItems([
    unit('drone-assigned', { tags: [tag], entityType: { id: 'drone', name: 'Drone' } }),
    unit('drone-legacy', { tags: [tag], entityType: { id: 'drone', name: 'Drone' } }),
    unit('camera-legacy', { tags: [tag], entityType: { id: 'camera', name: 'Camera' } }),
  ], { 'drone-assigned': { product_id: 'drone-product' } });
  assert.equal(groups.length, 2);
  assert.deepEqual(groups.find(group => group.productId === 'drone-product').items.map(row => row.id), ['drone-assigned', 'drone-legacy']);
  assert.deepEqual(groups.find(group => group.items.some(row => row.id === 'camera-legacy')).items.map(row => row.id), ['camera-legacy']);
});

test('normalized manufacturer and model identity is stable and incomplete metadata uses conservative exact-name identity', () => {
  const grouped = groupInventoryItems([
    unit('a', { manufacturer: 'DJI', modelNumber: 'Air 2S' }),
    unit('b', { manufacturer: ' dji ', modelNumber: ' AIR   2s ' }),
    unit('c', { name: 'Tripod', manufacturer: '', modelNumber: '' }),
    unit('d', { name: ' Tripod ', manufacturer: '', modelNumber: '' }),
    unit('e', { name: 'Tripod', manufacturer: 'Maker', modelNumber: 'Tall' }),
  ], {}, {});
  assert.equal(grouped.length, 3);
  assert.deepEqual(grouped.map(row => row.recordCount), [2, 2, 1]);
});

test('searching for a unit ID retains its whole product group and exposes unit status, native ID, and location', () => {
  const items = [unit('a', { serialNumber: 'SN-A' }), unit('b', { serialNumber: 'SN-B' }), unit('c', { serialNumber: 'SN-C' })];
  const groups = groupInventoryItems(items, {
    a: { product_id: 'product-1', display_id: 'DRONE-2S-1' },
    b: { product_id: 'product-1', display_id: 'DRONE-2S-2' },
    c: { product_id: 'product-1', display_id: 'DRONE-2S-3' },
  }, {
    query: 'DRONE-2S-2',
    storagePath: item => `Room for ${item.id}`,
    statuses: { a: { status: 'available' }, b: { status: 'checked_out' }, c: { status: 'unknown' } },
  });
  assert.equal(groups.length, 1);
  assert.equal(groups[0].items.length, 3);
  assert.deepEqual(groups[0].items.map(row => row.id), ['a', 'b', 'c']);
  assert.equal(groups[0].items[1].displayId, 'DRONE-2S-2');
  assert.equal(groups[0].items[1].status, 'checked_out');
  assert.equal(groups[0].items[1].storagePath, 'Room for b');
});

test('status filters include only matching units and aggregate archived, blocked, and unknown without assuming availability', () => {
  const items = [unit('a'), unit('b'), unit('c'), unit('d'), unit('e')];
  const statuses = { a: { status: 'available' }, b: { status: 'checked_out' }, c: { status: 'blocked' }, d: { status: 'archived' } };
  const all = groupInventoryItems(items, {}, { statuses });
  assert.deepEqual(all[0].statusCounts, { available: 1, checked_out: 1, blocked: 1, archived: 1, unknown: 1 });
  const blocked = groupInventoryItems(items, {}, { statuses, filters: { status: 'blocked' } });
  assert.deepEqual(blocked[0].items.map(item => item.id), ['c']);
});

test('native archived state takes precedence over an available action-status projection', () => {
  const groups = groupInventoryItems([unit('retired', { archived: true })], {}, {
    statuses: { retired: { availability: 'available' } },
  });
  assert.deepEqual(groups[0].statusCounts, { available: 0, checked_out: 0, blocked: 0, archived: 1, unknown: 0 });
  assert.equal(groups[0].items[0].status, 'archived');
});

test('unavailable identity metadata remains singleton unless catalog assignment provides stable identity', () => {
  const items = [unit('a', { manufacturer: '', modelNumber: '', metadataUnavailable: true }), unit('b', { manufacturer: '', modelNumber: '', metadataUnavailable: true })];
  assert.equal(groupInventoryItems(items).length, 2);
  assert.equal(groupInventoryItems(items, { a: { product_id: 'p' }, b: { product_id: 'p' } }).length, 1);
});

test('assigned and legacy records with matching full metadata share one product identity', () => {
  const groups = groupInventoryItems([
    unit('legacy', { name: 'Camera body' }),
    unit('assigned', { name: 'Camera body' }),
  ], { assigned: { product_id: 'catalog-camera', display_id: 'CAM-1' } });
  assert.equal(groups.length, 1);
  assert.equal(groups[0].recordCount, 2);
  assert.equal(groups[0].productId, 'catalog-camera');
});

test('explicit group tags prevent metadata aliases from crossing product groups', () => {
  const groups = groupInventoryItems([
    unit('assigned-red', { tags: [{ name: 'C-Crate Product group: Red fleet' }] }),
    unit('legacy-blue', { tags: [{ name: 'C-Crate Product group: Blue fleet' }] }),
  ], { 'assigned-red': { product_id: 'red', display_id: 'DRONE-1' } });
  assert.equal(groups.length, 2);
  assert.equal(groups.find(group => group.items.some(item => item.id === 'legacy-blue')).productId, null);
});

test('legacy aliases inherit product thumbnail metadata but preserve their native visible ID', () => {
  const groups = groupInventoryItems([
    unit('assigned', { imageId: 'photo-assigned' }),
    unit('legacy', { assetId: 'NATIVE-77' }),
  ], { assigned: { product_id: 'p', display_id: 'DRONE-1' } }, {
    templateThumbnails: { p: { entity_id: 'assigned', attachment_id: 'template-photo' } },
  });
  const legacy = groups[0].items.find(item => item.id === 'legacy');
  assert.equal(legacy.productId, 'p');
  assert.equal(legacy.thumbnail.attachment_id, 'template-photo');
  assert.equal(legacy.displayId, 'NATIVE-77');
  assert.equal(legacy.assetId, 'NATIVE-77');
});

test('missing full detail marks metadata unavailable to keep same-name records separate', () => {
  const merged = mergeInventorySummaries([{ id: 'a', name: 'Tripod' }, { id: 'b', name: 'Tripod' }], []);
  assert.deepEqual(groupInventoryItems(merged).map(group => group.items.map(item => item.id)), [['a'], ['b']]);
});

test('note request keys bind the exact sorted native UUID membership', () => {
  assert.equal(inventoryNoteRequestKey('product', ['b', 'a']), inventoryNoteRequestKey('product', ['a', 'b']));
  assert.notEqual(inventoryNoteRequestKey('product', ['a']), inventoryNoteRequestKey('product', ['a', 'b']));
});

test('native search matches are expanded as complete groups without reimplementing Homebox description or note matching', () => {
  const items = [unit('matched', { description: 'a unique repair phrase' }), unit('peer', { description: 'no phrase' })];
  const groups = groupInventoryItems(items, { matched: { product_id: 'p' }, peer: { product_id: 'p' } }, {
    query: 'unique repair phrase', matchedEntityIds: ['matched'],
  });
  assert.equal(groups.length, 1);
  assert.deepEqual(groups[0].items.map(item => item.id), ['matched', 'peer']);
});

test('recent note preview is attached to the corresponding expanded unit', () => {
  const groups = groupInventoryItems([unit('a')], {}, { recentNotes: { a: { text: 'Returned with a cracked latch', author: 'Member' } } });
  assert.deepEqual(groups[0].items[0].recentNote, { text: 'Returned with a cracked latch', author: 'Member' });
});

test('storage path follows item containers through their location ancestors', () => {
  const item = { id: 'tool', parent: { id: 'case', name: 'Camera case' } };
  const records = [
    { id: 'case', parentId: 'room', name: 'Camera case' },
    { id: 'room', parentId: 'floor', name: 'Equipment room' },
    { id: 'floor', name: 'Second floor' },
  ];
  assert.equal(buildInventoryStoragePath(item, records), 'Second floor / Equipment room / Camera case');
});

test('full collection records enrich summaries with product and unit identity metadata', () => {
  const merged = mergeInventorySummaries([{ id: 'a', name: 'Camera' }], [{
    id: 'a', manufacturer: 'Maker', modelNumber: 'M-1', serialNumber: 'SN-1', description: 'Full detail',
  }]);
  assert.equal(merged[0].manufacturer, 'Maker');
  assert.equal(merged[0].modelNumber, 'M-1');
  assert.equal(merged[0].serialNumber, 'SN-1');
  assert.equal(merged[0].description, 'Full detail');
});

test('recent note index keeps the newest return note per native unit', () => {
  const notes = indexLatestInventoryNotes([
    { entity_id: 'a', text: 'older', created_at: '2026-01-01T00:00:00Z' },
    { entity_id: 'a', text: 'newest', created_at: '2026-02-01T00:00:00Z' },
    { entity_id: 'b', text: 'other unit', created_at: '2026-01-15T00:00:00Z' },
  ]);
  assert.equal(notes.a.text, 'newest');
  assert.equal(notes.b.text, 'other unit');
});

test('per-unit note versions reject stale results across overlapping group and single-unit refreshes', () => {
  const versions = createInventoryNoteVersionGuard();
  const groupRequest = versions.begin(['A', 'B']);
  const refreshA = versions.begin(['A']);
  const notes = {};
  if (versions.isCurrent(refreshA, 'A')) notes.A = 'new A';
  for (const [id, text] of [['A', 'old A'], ['B', 'old B']]) {
    if (versions.isCurrent(groupRequest, id)) notes[id] = text;
  }
  assert.deepEqual(notes, { A: 'new A', B: 'old B' }, 'the older group request may update B but cannot overwrite the newer A refresh');
});

test('loads the complete native filtered result across pages before group projection', async () => {
  const all = Array.from({ length: 5 }, (_, i) => unit(String(i)));
  const requests = [];
  const rows = await loadAllFilteredInventory(async (page, pageSize) => {
    requests.push([page, pageSize]);
    return { items: all.slice((page - 1) * pageSize, page * pageSize), total: all.length };
  }, { pageSize: 2, concurrency: 2 });
  assert.equal(rows.length, 5);
  assert.deepEqual(requests.sort((a, b) => a[0] - b[0]), [[1, 2], [2, 2], [3, 2]]);
  assert.equal(new Set(rows.map(row => row.id)).size, 5);
  assert.equal(groupInventoryItems(rows, Object.fromEntries(rows.map((row, i) => [row.id, { product_id: 'p', display_id: `P-${i}` }])))[0].recordCount, 5);
});

test('failed or stale page loads never return a partial inventory result', async () => {
  await assert.rejects(loadAllFilteredInventory(async page => {
    if (page === 1) throw new Error('page failed');
    return { items: [unit('a')], total: 3 };
  }, { pageSize: 1, concurrency: 1 }));
  await assert.rejects(loadAllFilteredInventory(async () => ({ items: [unit('a')], total: 2 }), { pageSize: 1, isCurrent: () => false }), /stale/i);
  await assert.rejects(loadAllFilteredInventory(async page => ({ items: [unit(page === 1 ? 'a' : 'a')], total: 2 }), { pageSize: 1 }), /duplicate entity UUIDs/i);
});
