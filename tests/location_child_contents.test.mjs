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
