import assert from 'node:assert/strict';
import test from 'node:test';
import {
  buildLocationTree,
  getLocationLabel,
  getVisibleLocationTree,
  handleLocationTreeButtonKeydown,
  toggleLocationExpanded,
} from '../homebox-ui/overlay/lib/location-selector-tree.js';

const rows = [
  { id: 'north', name: 'North', archived: false },
  { id: 'north-rack', name: 'Rack', archived: false, parent: { id: 'north' } },
  { id: 'north-shelf', name: 'Shelf', archived: false, parent: { id: 'north-rack' } },
  { id: 'north-camera', name: 'Camera', archived: false, isLocation: false, parent: { id: 'north-shelf' } },
  { id: 'south', name: 'South', archived: false },
  { id: 'south-rack', name: 'Rack', archived: false, parent: { id: 'south' } },
  { id: 'south-shelf', name: 'Shelf', archived: false, parent: { id: 'south-rack' } },
  { id: 'archive', name: 'Archived', archived: true },
];

test('location tree indentation collapses children and restores them after expansion', () => {
  const tree = buildLocationTree(rows);
  let expanded = new Set();
  assert.deepEqual(getVisibleLocationTree(tree, expanded).map(row => row.id), ['north', 'south']);

  expanded = toggleLocationExpanded(expanded, 'north');
  assert.deepEqual(getVisibleLocationTree(tree, expanded).map(row => row.id), ['north', 'north-rack', 'south']);
  expanded = toggleLocationExpanded(expanded, 'north-rack');
  assert.deepEqual(getVisibleLocationTree(tree, expanded).map(row => row.id), ['north', 'north-rack', 'north-shelf', 'south']);
  expanded = toggleLocationExpanded(expanded, 'north');
  assert.deepEqual(getVisibleLocationTree(tree, expanded).map(row => row.id), ['north', 'south']);
});

test('tree includes selectable item parents and labels duplicate selections with their full paths', () => {
  const tree = buildLocationTree(rows);
  const item = tree.find(row => row.id === 'north-camera');
  assert.equal(item.treeString, 'North / Rack / Shelf / Camera');
  assert.equal(item.parentId, 'north-shelf');
  assert.equal(getLocationLabel(tree, 'north-shelf'), 'North / Rack / Shelf');
  assert.equal(getLocationLabel(tree, 'south-shelf'), 'South / Rack / Shelf');
  assert.equal(getLocationLabel(tree, 'north-rack'), 'North / Rack');
});

test('search results stay visible through collapsed ancestors and match full paths', () => {
  const tree = buildLocationTree(rows);
  const matchingRows = tree.filter(row => row.treeString.toLowerCase().includes('north / rack / shelf'));
  assert.deepEqual(
    getVisibleLocationTree(matchingRows, new Set(), true).map(row => row.id),
    ['north-shelf', 'north-camera'],
  );
});

test('exclusions and current location remove their subtrees, and archived or cyclic rows are omitted', () => {
  const cyclicRows = [
    ...rows,
    { id: 'excluded-root', name: 'Excluded root', archived: false },
    { id: 'excluded-child', name: 'Excluded child', archived: false, parent: { id: 'excluded-root' } },
    { id: 'cycle-a', name: 'Cycle A', archived: false, parent: { id: 'cycle-b' } },
    { id: 'cycle-b', name: 'Cycle B', archived: false, parent: { id: 'cycle-a' } },
    { id: 'cycle-child', name: 'Cycle child', archived: false, parent: { id: 'cycle-a' } },
  ];
  const tree = buildLocationTree(cyclicRows, {
    excludeIds: ['excluded-root'],
    currentLocation: { id: 'north-rack' },
  });
  const ids = tree.map(row => row.id);
  assert.ok(!ids.includes('north-rack'));
  assert.ok(!ids.includes('north-shelf'));
  assert.ok(!ids.includes('north-camera'));
  assert.ok(!ids.includes('excluded-root'));
  assert.ok(!ids.includes('excluded-child'));
  assert.ok(!ids.includes('archive'));
  assert.ok(!ids.includes('cycle-a'));
  assert.ok(!ids.includes('cycle-b'));
  assert.ok(!ids.includes('cycle-child'));
  assert.ok(ids.includes('south-rack'));
});

test('identical full paths include stable IDs in both visible and selected labels', () => {
  const duplicatePaths = [
    { id: 'root-a', name: 'Workshop', archived: false },
    { id: 'root-b', name: 'Workshop', archived: false },
    { id: 'shelf-a', name: 'Shelf', archived: false, parent: { id: 'root-a' } },
    { id: 'shelf-b', name: 'Shelf', archived: false, parent: { id: 'root-a' } },
  ];
  const tree = buildLocationTree(duplicatePaths);
  assert.equal(tree.find(row => row.id === 'shelf-a').treeString, 'Workshop / Shelf [shelf-a]');
  assert.equal(tree.find(row => row.id === 'shelf-b').treeString, 'Workshop / Shelf [shelf-b]');
  assert.equal(getLocationLabel(tree, 'shelf-a'), 'Workshop / Shelf [shelf-a]');
  assert.equal(getLocationLabel(tree, 'shelf-b'), 'Workshop / Shelf [shelf-b]');
});

test('tree expand buttons stop activation keys but let Escape dismiss the popover', () => {
  for (const key of ['Enter', ' ']) {
    const state = { stopped: false, prevented: false, closed: false };
    handleLocationTreeButtonKeydown({ key, stopPropagation() { state.stopped = true; }, preventDefault() { state.prevented = true; } }, () => { state.closed = true; });
    assert.equal(state.stopped, true, `${JSON.stringify(key)} should not activate the parent row`);
    assert.equal(state.prevented, false);
    assert.equal(state.closed, false);
  }
  const escape = { stopped: false, prevented: false, closed: false };
  handleLocationTreeButtonKeydown({ key: 'Escape', stopPropagation() { escape.stopped = true; }, preventDefault() { escape.prevented = true; } }, () => { escape.closed = true; });
  assert.deepEqual(escape, { stopped: true, prevented: true, closed: true });

  const arrow = { stopped: false, prevented: false, closed: false };
  handleLocationTreeButtonKeydown({ key: 'ArrowRight', stopPropagation() { arrow.stopped = true; }, preventDefault() { arrow.prevented = true; } }, () => { arrow.closed = true; });
  assert.deepEqual(arrow, { stopped: false, prevented: false, closed: false });
});
