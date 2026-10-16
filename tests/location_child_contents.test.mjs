import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const component = readFileSync(new URL('../homebox-ui/overlay/components/Location/ChildContents.vue', import.meta.url), 'utf8');

function componentFunction(start, end, declaration, dependencies, values) {
  const body = component.split(start)[1]?.split(end)[0];
  assert.ok(body, `${declaration} exists in ChildContents.vue`);
  return new Function(...dependencies, `${declaration}${body.replace('[] as EntitySummary[]', '[]')}\nreturn ${declaration.match(/function (\w+)/)[1]};`)(...values);
}

test('filter finds a native modelNumber', () => {
  const matchesItem = componentFunction('  function matchesItem(item: EntitySummary) {', '  function visibleItems(',
    'function matchesItem(item) {', ['searchTerm'], [{ value: 'zx-400' }]);
  assert.equal(matchesItem({ name: 'Camera', modelNumber: 'ZX-400', serialNumber: 'SN-1' }), true);
});

function nestedFixture({ failPage = 0 } = {}) {
  let failingPage = failPage;
  const state = { expanded: true, loading: false, loaded: false, items: [], children: [], error: '' };
  const calls = [];
  const items = Array.from({ length: 137 }, (_, i) => ({
    id: `item-${i}`, parent: { id: 'nested' }, archived: i === 136,
  }));
  const api = { items: {
    getLocation: async id => ({ data: { id, children: [{ id: 'deeper', name: 'Deeper', itemCount: 0 }] } }),
    getAll: async query => {
      calls.push(query);
      if (query.page === failingPage) return { error: 'fixture page failure' };
      return { data: { total: items.length, items: items.slice((query.page - 1) * query.pageSize, query.page * query.pageSize) } };
    },
  } };
  const loadDetail = componentFunction('  async function loadDetail(locationId: string) {', '  function toggle(',
    'async function loadDetail(locationId) {', ['stateFor', 'api', 'isRoot'], [() => state, api, false]);
  return { state, calls, loadDetail, setFailurePage: page => { failingPage = page; } };
}

test('nested expansion fetches all direct items including archived records', async () => {
  const fixture = nestedFixture();
  assert.equal(fixture.calls.length, 0);
  await fixture.loadDetail('nested');
  assert.deepEqual(fixture.calls.map(query => query.page), [1, 2]);
  assert.ok(fixture.calls.every(query => query.parentIds?.[0] === 'nested' && query.pageSize === 100 && query.includeArchived === true));
  assert.equal(fixture.state.items.length, 137);
  assert.equal(fixture.state.items[136].archived, true);
  assert.equal(fixture.state.children[0].id, 'deeper');
  assert.equal(fixture.state.loaded, true);
});

test('nested page failure preserves returned rows and permits retry', async () => {
  const fixture = nestedFixture({ failPage: 2 });
  await fixture.loadDetail('nested');
  assert.equal(fixture.state.items.length, 100);
  assert.match(fixture.state.error, /incomplete/i);
  assert.equal(fixture.state.loaded, false);
  assert.equal(fixture.state.loading, false);
  assert.equal(fixture.state.children[0].id, 'deeper');
  fixture.setFailurePage(0);
  await fixture.loadDetail('nested');
  assert.deepEqual(fixture.calls.map(query => query.page), [1, 2, 1, 2]);
  assert.equal(fixture.state.items.length, 137);
  assert.equal(fixture.state.error, '');
  assert.equal(fixture.state.loaded, true);
});


test('filter retains loaded ancestor paths and reveals collapsed matching descendants', () => {
  const states = new Map([
    ['cabinet', { expanded: false, loaded: true, items: [], children: [{ id: 'bin', name: 'Upper bin' }] }],
    ['bin', { expanded: false, loaded: true, items: [], children: [{ id: 'tray', name: 'Inner tray' }] }],
    ['tray', { expanded: false, loaded: true, items: [{ name: 'Hidden torque wrench' }], children: [] }],
  ]);
  const stateFor = id => states.get(id) || { expanded: false, loaded: false, items: [], children: [] };
  const searchTerm = { value: 'torque' };
  const matchesItem = item => item.name.toLowerCase().includes(searchTerm.value);
  const matchesLocationName = location => location.name.toLowerCase().includes(searchTerm.value);
  const directItems = new Map([['cabinet', []]]);
  const itemsFor = componentFunction('  function itemsFor(location: LocationNode, nested = false): EntitySummary[] {', '  function matchesItem(',
    'function itemsFor(location, nested = false) {', ['isRoot', 'directItems', 'stateFor'], [true, directItems, stateFor]);
  const hasLoadedMatch = componentFunction('  function hasLoadedMatch(location: LocationNode, nested = false) {', '  function filteredLocations(',
    'function hasLoadedMatch(location, nested = false) {', ['matchesLocationName', 'itemsFor', 'matchesItem', 'stateFor'],
    [matchesLocationName, itemsFor, matchesItem, stateFor]);
  const filteredLocations = componentFunction('  function filteredLocations() {', '  function isExpandedForDisplay(',
    'function filteredLocations() {', ['searchTerm', 'props', 'hasLoadedMatch'],
    [searchTerm, { locations: [{ id: 'cabinet', name: 'Cabinet' }] }, hasLoadedMatch]);
  const isExpandedForDisplay = componentFunction('  function isExpandedForDisplay(location: LocationNode) {', '  function isForcedOpenByFilter(',
    'function isExpandedForDisplay(location) {', ['stateFor', 'searchTerm', 'hasLoadedMatch'],
    [stateFor, searchTerm, hasLoadedMatch]);
  assert.deepEqual(filteredLocations().map(location => location.id), ['cabinet']);
  assert.equal(isExpandedForDisplay({ id: 'cabinet', name: 'Cabinet' }), true);
  assert.equal(isExpandedForDisplay({ id: 'bin', name: 'Upper bin' }), true);
  searchTerm.value = '';
  assert.equal(stateFor('cabinet').expanded, false);
  assert.equal(stateFor('tray').loaded, true);
  assert.equal(isExpandedForDisplay({ id: 'cabinet', name: 'Cabinet' }), false);
});

test('matching unloaded bin cannot be toggled or collapsed until filter clears', () => {
  const location = { id: 'unloaded', name: 'Torque bin' };
  const state = { expanded: false, loaded: false, items: [], children: [] };
  const stateFor = () => state;
  const searchTerm = { value: 'torque' };
  const isForcedOpenByFilter = componentFunction('  function isForcedOpenByFilter(location: LocationNode) {', '  function locationPath(',
    'function isForcedOpenByFilter(location) {', ['searchTerm', 'hasLoadedMatch'],
    [searchTerm, row => row.name.toLowerCase().includes(searchTerm.value)]);
  const canCollapseAll = componentFunction('  function canCollapseAll() {', '  function locationPath(',
    'function canCollapseAll() {', ['searchTerm', 'filteredLocations'],
    [searchTerm, () => searchTerm.value ? [location] : []]);
  let loads = 0;
  const loadDetail = () => { loads++; };
  const props = { locations: [location] };
  const allExpanded = { value: false };
  const toggle = componentFunction('  function toggle(location: LocationNode) {', '  function setAllExpanded(',
    'function toggle(location) {', ['isForcedOpenByFilter', 'stateFor', 'allExpanded', 'props', 'isRoot', 'loadDetail'],
    [isForcedOpenByFilter, stateFor, allExpanded, props, false, loadDetail]);
  const setAllExpanded = componentFunction('  function setAllExpanded(expanded: boolean) {', '  function retryBatch(',
    'function setAllExpanded(expanded) {', ['canCollapseAll', 'allExpanded', 'props', 'stateFor', 'loadDetail'],
    [canCollapseAll, allExpanded, props, stateFor, loadDetail]);
  assert.equal(isForcedOpenByFilter(location), true);
  assert.equal(canCollapseAll(), false);
  toggle(location);
  assert.equal(state.expanded, false);
  assert.equal(loads, 0);
  state.expanded = true;
  setAllExpanded(false);
  assert.equal(state.expanded, true);
  assert.equal(loads, 0);
  searchTerm.value = '';
  assert.equal(isForcedOpenByFilter(location), false);
  assert.equal(canCollapseAll(), true);
  setAllExpanded(false);
  assert.equal(state.expanded, false);
  toggle(location);
  assert.equal(state.expanded, true);
  assert.equal(loads, 1);
});
