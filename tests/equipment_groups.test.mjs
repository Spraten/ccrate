import assert from 'node:assert/strict';
import { test } from 'node:test';
import { projectEquipmentGroups, equipmentRecordLabel, groupHistoryMembers, groupHistoryBatches, loadGroupHistory, groupNotesPresentation } from '../homebox-ui/overlay/lib/equipment-groups.js';

const item = (id, extra = {}) => ({ id, name: `Unit ${id}`, assetId: `AS-${id}`, manufacturer: 'Acme', modelNumber: 'MX-1', serialNumber: `SN-${id}`, quantity: 1, condition: 'Ready', tags: [], ...extra });
const project = (items, options = {}) => projectEquipmentGroups(items, { loans: [], storagePath: () => '', ...options });

test('groupsSearchesModelManufacturerSerialAndStorage', () => {
  const rows = [item('a', { name: 'Camera' }), item('b', { manufacturer: 'Nikon', modelNumber: 'D750', serialNumber: 'ONLY-SERIAL' })];
  const options = { storagePath: row => row.id === 'a' ? 'Store / West shelf' : 'Store / East shelf' };
  for (const [query, expected] of [['camera', 'a'], ['AS-A', 'a'], ['west shelf', 'a'], ['nikon', 'b'], ['d750', 'b'], ['only-serial', 'b']]) {
    assert.deepEqual(project(rows, { ...options, query }).flatMap(group => group.items.map(row => row.id)), [expected], query);
  }
 });

test('groupsExactNormalizedManufacturerModelPairs', () => {
  const rows = [item('a', { manufacturer: '  ACME  Corp ', modelNumber: ' MX-1 ' }), item('b', { manufacturer: 'acme corp', modelNumber: 'mx-1' }), item('c', { manufacturer: '', modelNumber: 'MX-1' }), item('d', { manufacturer: 'Acme Corp', modelNumber: '' })];
  const groups = project(rows);
  assert.deepEqual(groups.map(group => group.items.map(row => row.id)), [['a', 'b'], ['c'], ['d']]);
  assert.equal(groups[0].kind, 'model');
  assert.equal(groups[1].kind, 'individual');
 });

test('groupsCustomMembershipOverridesDerivedModel', () => {
  const tag = { id: 'tag-1', name: 'C-Crate Product group: Field kit' };
  const groups = project([item('a', { tags: [tag] }), item('b'), item('c', { manufacturer: '', modelNumber: '', tags: [tag] })]);
  assert.deepEqual(groups.map(group => group.items.map(row => row.id)), [['a', 'c'], ['b']]);
  assert.equal(groups[0].kind, 'custom');
  assert.equal(groups[0].name, 'Field kit');
  assert.deepEqual(project([item('a', { tags: [tag] })], { query: 'field kit' }).flatMap(group => group.items.map(row => row.id)), ['a']);
 });

test('similarModelsStaySeparate', () => {
  const rows = [item('a', { modelNumber: 'MX-1' }), item('b', { modelNumber: 'MX 1' }), item('c', { modelNumber: 'MX–1' }), item('d', { manufacturer: 'Acmé' }), item('e', { manufacturer: 'Acmé' })];
  assert.equal(project(rows).length, 5);
 });

test('groupCountsPhysicalRecordsBySnapshotStatus', () => {
  const rows = [item('a', { quantity: 1 }), item('b', { quantity: 9 }), item('c', { blocker: 'Needs calibration' }), item('d', { archived: true }), item('e', { condition: 'Maintenance' })];
  const groups = project(rows, { loans: [{ entity_id: 'b' }] });
  assert.deepEqual(groups[0].counts, { available: 1, checkedOut: 1, blocked: 2, archived: 1 });
  assert.equal(groups[0].count, 5);
  assert.deepEqual(project(rows, { loans: [{ entity_id: 'b' }], filter: 'blocked' })[0].items.map(row => row.id), ['c', 'e']);
 });

test('equipment controls identify records with repeated names and codes', () => {
  const first = item('first', { name: 'Camera', assetId: 'CAM-1' });
  const second = item('second', { name: 'Camera', assetId: 'CAM-1' });
  assert.equal(equipmentRecordLabel(first), 'Camera · CAM-1 · first');
  assert.equal(equipmentRecordLabel(second), 'Camera · CAM-1 · second');
  assert.notEqual(equipmentRecordLabel(first), equipmentRecordLabel(second));
});

test('custom and manufacturer-model equipment groups stay within the native type', () => {
  const tag = { id: 'tag-1', name: 'C-Crate Product group: Field kit' };
  const rows = [
    item('drone-tag', { tags: [tag], entityType: { id: 'drone' } }),
    item('drone-tag-peer', { tags: [tag], entityType: { id: 'drone' } }),
    item('camera-tag', { tags: [tag], entityType: { id: 'camera' } }),
    item('drone-model', { entityType: { id: 'drone' } }),
    item('camera-model', { entityType: { id: 'camera' } }),
  ];
  const groups = project(rows);
  assert.deepEqual(groups.map(group => group.items.map(row => row.id)), [
    ['drone-tag', 'drone-tag-peer'], ['camera-tag'], ['drone-model'], ['camera-model'],
  ]);
});


test('groupNotesAreOrderedAndCappedAtFive', () => {
  const members = [item('b'), item('a')];
  const rows = Array.from({ length: 7 }, (_, index) => ({ entity_id: index % 2 ? 'a' : 'b', text: `Note ${index}`, author: 'Staff', created_at: `2026-10-16T0${index}:00:00Z` }));
  const view = groupNotesPresentation(members, rows);
  assert.deepEqual(view.notes.map(row => row.text), ['Note 6', 'Note 5', 'Note 4', 'Note 3', 'Note 2']);
  assert.deepEqual(view.notes.map(row => row.source.id), ['b', 'a', 'b', 'a', 'b']);
  assert.equal(view.notes[0].source.serialNumber, 'SN-b');
  assert.equal(groupNotesPresentation(members, []).message, 'No return notes recorded for this group.');
  assert.deepEqual(groupHistoryMembers([item('z'), item('b'), item('a')]).map(row => row.id), ['a', 'b', 'z']);
  assert.equal(groupHistoryMembers(Array.from({length: 101}, (_, index) => item(String(index).padStart(3, '0')))).length, 101);
});

test('groupHistoryBatchesCoverEveryMemberWithoutExceedingEndpointLimit', () => {
  const members = Array.from({ length: 205 }, (_, index) => item(String(index).padStart(3, '0')));
  const batches = groupHistoryBatches(members);
  assert.deepEqual(batches.map(batch => batch.length), [100, 100, 5]);
  assert.deepEqual(batches.flat().map(row => row.id), members.map(row => row.id).sort());
});

test('groupNotesIncludeNewestNoteOnMember101', () => {
  const members = Array.from({ length: 101 }, (_, index) => item(String(index).padStart(3, '0')));
  const batches = groupHistoryBatches(members);
  assert.equal(batches[1][0].id, '100');
  const view = groupNotesPresentation(members, [{ entity_id: '100', text: 'Newest note', created_at: '2026-10-18T12:00:00Z' }]);
  assert.equal(view.notes[0].source.id, '100');
  assert.equal(view.notes[0].text, 'Newest note');
});

test('loadGroupHistoryRequestsEveryBatchAndMergesTheResponses', async () => {
  const members = Array.from({ length: 101 }, (_, index) => item(String(index).padStart(3, '0')));
  const requests = [];
  const result = await loadGroupHistory(members, async ids => {
    requests.push(ids);
    return ids.includes('100') ? [{ entity_id: '100', text: 'Newest note', created_at: '2026-10-18T12:00:00Z' }] : [];
  });
  assert.deepEqual(requests.map(ids => ids.length).sort((a, b) => b - a), [100, 1]);
  assert.equal(result.failed, false);
  assert.deepEqual(groupNotesPresentation(members, result.rows).notes.map(row => row.source.id), ['100']);
});

test('loadGroupHistoryRetainsSuccessfulBatchesWhenARequestFails', async () => {
  const members = Array.from({ length: 101 }, (_, index) => item(String(index).padStart(3, '0')));
  const result = await loadGroupHistory(members, async ids => {
    if (ids.includes('100')) throw new Error('unavailable');
    return [{ entity_id: '000', text: 'Loaded note', created_at: '2026-10-18T12:00:00Z' }];
  });
  assert.equal(result.failed, true);
  assert.equal(result.rows.length, 1);
  assert.equal(groupNotesPresentation(members, result.rows, result.failed).notes[0].text, 'Loaded note');
});

test('groupNotesPartialFailureKeepsLoadedNotesAndReportsIncompleteHistory', () => {
  const members = [item('a'), item('b')];
  const view = groupNotesPresentation(members, [{ entity_id: 'a', text: 'Loaded note', created_at: '2026-10-18T12:00:00Z' }], new Error('batch failed'));
  assert.equal(view.notes.length, 1);
  assert.equal(view.notes[0].source.id, 'a');
  assert.match(view.message, /could not load all/i);
});

test('groupNotesFailureKeepsMembers', () => {
  const members = [item('a'), item('b')];
  const view = groupNotesPresentation(members, null, new Error('History unavailable'));
  assert.deepEqual(view.members.map(row => row.id), ['a', 'b']);
  assert.deepEqual(view.notes, []);
  assert.match(view.message, /could not load/i);
});
