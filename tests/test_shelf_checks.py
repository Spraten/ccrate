import pathlib
import json
import sqlite3
import tempfile
import threading
import unittest
from uuid import uuid4
from datetime import datetime, timezone

from ledger import Conflict, Ledger
from shelf_checks import CheckAccessDenied, ShelfChecks


class NativeFixtureClient:
    def __init__(self):
        self.nodes = {}
        self.writes = []
        self.mutations = []
        self.physical_outputs = []
        self.reads = 0
        self.base = 'https://native.example'
        self.members = []
        self.owner_id = None
        self.location_id = None
        self.required_lock = None

    def add(self, name, *, location=False, parent=None, archived=False, quantity=1,
            asset_id='', serial='', fields=None):
        entity_id = str(uuid4())
        entity = {'id': entity_id, 'name': name,
                  'entityType': {'id': str(uuid4()), 'isLocation': location},
                  'parent': {'id': parent} if parent else None,
                  'archived': archived, 'quantity': quantity, 'assetId': asset_id,
                  'serialNumber': serial, 'fields': list(fields or [])}
        self.nodes[entity_id] = entity
        return entity_id

    def entity(self, entity_id):
        if self.required_lock is not None and not self.required_lock.locked():
            raise AssertionError('native reread occurred outside the caller-held application lock')
        self.reads += 1
        if entity_id not in self.nodes:
            raise KeyError(entity_id)
        return dict(self.nodes[entity_id])

    def entities(self, locations=False):
        if self.required_lock is not None and not self.required_lock.locked():
            raise AssertionError('native reread occurred outside the caller-held application lock')
        self.reads += 1
        return [dict(row) for row in self.nodes.values()
                if row['entityType']['isLocation'] is locations]

    def call(self, path, method='GET', **kwargs):
        if path == '/api/v1/groups/members':
            return [dict(member) for member in self.members]
        raise ValueError('Unexpected synthetic native call')

    def remove_location_and_owner(self):
        self.nodes.pop(self.location_id, None)
        self.members = [member for member in self.members if member['id'] != self.owner_id]


class ShelfCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ledger = Ledger(pathlib.Path(self.temp.name) / 'ledger.db')
        self.group = str(uuid4())
        self.actor = str(uuid4())
        self.other_manager_actor = str(uuid4())
        self.asset = str(uuid4())
        self.ctx = self.context()
        self.store = ShelfChecks(self.ledger)
        self.client = NativeFixtureClient()
        self.other_cage = self.client.add('The Cage', location=True)
        self.cage = self.client.add('The Cage', location=True)
        self.rack = self.client.add('Rack', location=True, parent=self.cage)
        self.shelf = self.client.add('Shelf', location=True, parent=self.rack)
        self.client.location_id = self.shelf
        self.client.owner_id = self.actor
        self.client.members = [{'id': self.actor, 'name': 'Shelf manager'},
                               {'id': self.other_manager_actor, 'name': 'Other manager'}]
        self.box = self.client.add('Box', parent=self.shelf)
        self.asset = self.client.add('Drill', parent=self.shelf, quantity=1,
                                     asset_id='123-456', serial='SERIAL-DRILL')
        self.nested_asset = self.client.add('Nested drill', parent=self.box, quantity=2,
                                            asset_id='123-457', serial='SERIAL-NESTED')
        self.other_shelf = self.client.add('Other shelf', location=True, parent=self.other_cage)
        self.unexpected_asset = self.client.add('Unexpected drill', parent=self.other_shelf)
        self.inaccessible_foreign_asset = str(uuid4())
        self.archived_asset = self.client.add('Archived drill', parent=self.shelf, archived=True)
        self.other_manager_ctx = self.context(actor=self.other_manager_actor)

    def start_fixture(self, *, quantity: int = 1, include_nested=False, request_key=None):
        self.client.nodes[self.asset]['quantity'] = quantity
        return self.store.start(self.client, self.ctx, location_id=self.shelf,
                                 include_nested=include_nested,
                                 request_key=request_key or self.new_key())

    def observe_fixture(self, check: dict, *, observed_quantity=None, entity_id=None,
                        method='scan', request_key=None):
        return self.store.observe(
            self.client, self.ctx, check['id'], revision=check['revision'],
            entity_id=entity_id or self.asset, method=method,
            observed_quantity=observed_quantity, request_key=request_key or self.new_key())

    def finish_fixture(self, check: dict):
        return self.store.finish(self.client, self.ctx, check['id'],
                                 revision=check['revision'],
                                 review_fingerprint=check['review_fingerprint'],
                                 request_key=self.new_key())

    def assert_common_check_shape(self, check):
        self.assertTrue({'id', 'group_id', 'actor_id', 'actor_label', 'location_id',
                         'include_nested', 'started_at', 'state', 'revision',
                         'original_snapshot', 'reviewed_snapshot', 'review_fingerprint',
                         'observations', 'notes', 'groups', 'changes', 'pending_operations',
                         'suspended_reason', 'can_edit', 'completed_at', 'cancelled_at',
                         'cancelled_by', 'point_in_time'} <= set(check))

    def context(self, *, group=None, actor=None, manager=True):
        return {'group': group or self.group, 'actor': actor or self.actor, 'manager': manager}

    @staticmethod
    def new_key():
        return str(uuid4())

    def change(self, ctx, *, check_id=None, state='draft', revision=1):
        check_id = check_id or str(uuid4())

        def mutation(db):
            now = '2026-10-09T12:00:00+00:00'
            db.execute('''INSERT INTO shelf_checks
                (id,group_id,actor_id,location_id,include_nested,started_at,state,revision,
                 original_snapshot_json,notes,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                (check_id, ctx['group'], ctx['actor'], self.asset, 0, now, state, revision,
                 '{"items":[]}', '', now, now))
            return {'id': check_id, 'revision': revision, 'state': state}
        return mutation

    def test_atomic_result_restart_replay_and_changed_intent(self):
        key = self.new_key()
        intent = {'value': 1, 'nested': {'b': 2, 'a': 1}}
        result = self.store._apply(self.ctx, 'fixture', intent, key, self.change(self.ctx))
        with self.ledger.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM shelf_checks').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM shelf_check_events').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM shelf_check_requests').fetchone()[0], 1)

        reopened = ShelfChecks(Ledger(self.ledger.path))
        self.assertEqual(reopened.request(self.ctx, key),
                         {'status': 'completed', 'action': 'fixture', 'result': result})
        replay = reopened._apply(self.ctx, 'fixture', {'nested': {'a': 1, 'b': 2}, 'value': 1}, key,
                                 lambda db: self.fail('replayed mutation callback was called'))
        self.assertEqual(replay, result)
        calls = []
        with self.assertRaises(Conflict):
            reopened._apply(self.ctx, 'fixture', {'value': 2}, key,
                            lambda db: calls.append(True))
        self.assertEqual(calls, [])
        with self.ledger.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM shelf_checks').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM shelf_check_events').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM shelf_check_requests').fetchone()[0], 1)

    def test_current_access_actor_and_group_are_checked_before_replay(self):
        key = self.new_key()
        self.store._apply(self.ctx, 'fixture', {'value': 1}, key, self.change(self.ctx))
        calls = []
        with self.assertRaises(CheckAccessDenied):
            self.store._apply(self.context(manager=False), 'fixture', {'value': 1}, key,
                              lambda db: calls.append('denied manager'))
        with self.assertRaises(Conflict):
            self.store._apply(self.context(actor=self.other_manager_actor), 'fixture',
                              {'value': 1}, key,
                              lambda db: calls.append('changed manager'))

        other_group = str(uuid4())
        self.assertEqual(self.store.request(self.context(group=other_group), key),
                         {'status': 'not_started'})
        with self.assertRaises(CheckAccessDenied):
            self.store._apply(self.context(group=other_group), 'fixture', {'value': 1}, key,
                              lambda db: calls.append('changed group'))
        self.assertEqual(calls, [])

    def test_request_access_denial_does_not_disclose_saved_result(self):
        key = self.new_key()
        result = self.store._apply(self.ctx, 'fixture', {'value': 1}, key, self.change(self.ctx))
        with self.assertRaises(CheckAccessDenied):
            self.store.request(self.context(manager=False), key)
        with self.assertRaises(CheckAccessDenied):
            self.store.request(self.context(actor=str(uuid4())), key)
        self.assertEqual(self.store.request(self.ctx, key)['result'], result)

    def test_result_insert_failure_rolls_back_check_and_event(self):
        key = self.new_key()
        with self.ledger.connection() as db:
            db.execute('''CREATE TRIGGER fail_shelf_request BEFORE INSERT ON shelf_check_requests
                BEGIN SELECT RAISE(ABORT,'injected shelf request failure'); END''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'injected shelf request failure'):
            self.store._apply(self.ctx, 'fixture', {'value': 1}, key, self.change(self.ctx))
        with self.ledger.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM shelf_checks').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM shelf_check_events').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM shelf_check_requests').fetchone()[0], 0)

    def test_direct_and_nested_mixed_scope_preserves_quantities(self):
        direct = self.start_fixture(quantity=3)
        direct_rows = direct['original_snapshot']['items']
        self.assertEqual({row['id'] for row in direct_rows}, {self.box, self.asset})
        self.assertEqual(next(row for row in direct_rows if row['id'] == self.asset)['quantity'], 3)
        self.assertTrue(all(any(path_row['id'] == self.cage for path_row in row['path'])
                            for row in direct_rows))
        self.assertFalse(any(path_row['id'] == self.other_cage for row in direct_rows
                             for path_row in row['path']))
        self.client.nodes[self.asset]['quantity'] = 9
        self.assertEqual(next(row for row in direct_rows if row['id'] == self.asset)['quantity'], 3)
        nested = self.start_fixture(quantity=3, include_nested=True)
        nested_rows = nested['original_snapshot']['items']
        self.assertEqual({row['id'] for row in nested_rows},
                         {self.box, self.asset, self.nested_asset})
        self.assertEqual(len(nested_rows), len({row['id'] for row in nested_rows}))
        self.assertEqual(next(row for row in nested_rows if row['id'] == self.nested_asset)['quantity'], 2)

    def test_start_and_observation_replay_return_exact_result_without_native_reads(self):
        start_key = self.new_key()
        started = self.start_fixture(request_key=start_key)
        native_reads = self.client.reads
        self.client.nodes[self.asset]['archived'] = True
        replayed_start = self.store.start(
            self.client, self.ctx, location_id=self.shelf, include_nested=False,
            request_key=start_key)
        self.assertEqual(replayed_start, started)
        self.assertEqual(self.client.reads, native_reads)
        self.client.nodes[self.asset]['archived'] = False

        observation_key = self.new_key()
        observed = self.observe_fixture(started, request_key=observation_key)
        native_reads = self.client.reads
        replayed_observation = self.observe_fixture(started, request_key=observation_key)
        self.assertEqual(replayed_observation, observed)
        self.assertEqual(self.client.reads, native_reads)
        with self.ledger.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM shelf_checks').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM shelf_check_observations').fetchone()[0], 1)

    def test_ambiguous_code_and_location_scan_are_read_only(self):
        check = self.start_fixture(include_nested=True)
        self.client.nodes[self.asset]['fields'] = [{'name': 'Manufacturer QR code',
                                                    'textValue': 'https://maker.example/item/one'}]
        self.client.nodes[self.nested_asset]['fields'] = [{'name': 'Manufacturer QR code',
                                                          'textValue': 'https://maker.example/item/one'}]
        before = self.client.nodes.copy()
        with self.ledger.connection() as db:
            journal_before = tuple(db.execute('''SELECT
                (SELECT count(*) FROM shelf_check_events),
                (SELECT count(*) FROM shelf_check_requests),
                (SELECT count(*) FROM shelf_check_observations)''').fetchone())
        ambiguous = self.store.resolve(self.client, self.ctx, check['id'],
                                       raw='https://maker.example/item/one')
        self.assertIsNone(ambiguous['entity_id'])
        self.assertEqual({row['id'] for row in ambiguous['candidates']},
                         {self.asset, self.nested_asset})
        selected = self.store.resolve(self.client, self.ctx, check['id'],
                                      raw='https://maker.example/item/one',
                                      selected_entity_id=self.asset)
        self.assertEqual(selected['entity_id'], self.asset)
        with self.assertRaises(ValueError):
            self.store.resolve(self.client, self.ctx, check['id'],
                               raw='https://maker.example/item/one',
                               selected_entity_id=self.inaccessible_foreign_asset)
        location = self.store.resolve(self.client, self.ctx, check['id'], raw=self.shelf)
        self.assertIsNone(location['entity_id'])
        self.assertEqual(location['candidates'], [])
        self.assertIn('location', location['message'])
        with self.ledger.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM shelf_check_observations').fetchone()[0], 0)
            journal_after = tuple(db.execute('''SELECT
                (SELECT count(*) FROM shelf_check_events),
                (SELECT count(*) FROM shelf_check_requests),
                (SELECT count(*) FROM shelf_check_observations)''').fetchone())
            current = db.execute('SELECT location_id,revision,state FROM shelf_checks WHERE id=?',
                                  (check['id'],)).fetchone()
            self.assertEqual(tuple(current), (self.shelf, check['revision'], 'draft'))
        self.assertEqual(journal_after, journal_before)
        self.assertEqual(self.client.nodes, before)
        self.assertEqual(self.client.writes, [])
        self.assertEqual(self.client.mutations, [])
        self.assertEqual(self.client.physical_outputs, [])

    def test_quantity_three_requires_explicit_integer_tally(self):
        check = self.start_fixture(quantity=3)
        with self.ledger.connection() as db:
            before = tuple(db.execute('''SELECT
                (SELECT count(*) FROM shelf_check_events),
                (SELECT count(*) FROM shelf_check_requests),
                (SELECT count(*) FROM shelf_check_observations)''').fetchone())
        for tally in (None, -1, 1.5, True, '3'):
            with self.subTest(tally=tally):
                with self.assertRaises(ValueError):
                    self.observe_fixture(check, observed_quantity=tally)
        with self.ledger.connection() as db:
            after_invalid = tuple(db.execute('''SELECT
                (SELECT count(*) FROM shelf_check_events),
                (SELECT count(*) FROM shelf_check_requests),
                (SELECT count(*) FROM shelf_check_observations)''').fetchone())
        self.assertEqual(after_invalid, before)
        saved = self.observe_fixture(check, observed_quantity=2)
        self.assertEqual(saved['observations'][0]['observed_quantity'], 2)
        self.assertEqual(next(row for row in saved['original_snapshot']['items']
                              if row['id'] == self.asset)['quantity'], 3)
        self.assertEqual(self.client.mutations, [])
        self.assertEqual(self.client.physical_outputs, [])

    def test_repeat_uuid_and_foreign_archived_unknown(self):
        check = self.start_fixture()
        self.client.nodes[self.asset]['archived'] = True
        with self.assertRaises(ValueError):
            self.observe_fixture(check)
        self.client.nodes[self.asset]['archived'] = False
        first = self.observe_fixture(check)
        self.assertEqual(first['revision'], check['revision'] + 1)
        with self.assertRaises(Conflict):
            self.observe_fixture(check)
        second = self.observe_fixture(first)
        self.assertEqual(len(second['observations']), 1)
        self.assertEqual(second['observations'][0]['observed_quantity'], 1)
        self.assertEqual(second['revision'], first['revision'] + 1)
        for entity_id in (self.inaccessible_foreign_asset, self.archived_asset, str(uuid4()), self.shelf):
            with self.subTest(entity_id=entity_id):
                with self.assertRaises(ValueError):
                    self.observe_fixture(second, entity_id=entity_id)
        with self.ledger.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM shelf_check_observations').fetchone()[0], 1)

    def test_unexpected_same_tenant_observation_keeps_snapshot_and_path(self):
        check = self.start_fixture()
        original = check['original_snapshot']
        resolved = self.store.resolve(self.client, self.ctx, check['id'],
                                      raw=self.unexpected_asset)
        self.assertEqual(resolved['entity_id'], self.unexpected_asset)
        self.assertFalse(resolved['candidates'][0]['expected'])
        before = self.client.mutations[:]
        observed = self.observe_fixture(check, entity_id=self.unexpected_asset)
        unexpected = next(row for row in observed['observations']
                          if row['entity_id'] == self.unexpected_asset)
        self.assertFalse(unexpected['expected'])
        self.assertEqual(unexpected['status'], 'unexpected_here')
        self.assertEqual([row['id'] for row in unexpected['current_path']],
                         [self.other_cage, self.other_shelf, self.unexpected_asset])
        self.assertEqual(observed['original_snapshot'], original)
        self.assertNotIn(self.unexpected_asset,
                         {row['id'] for row in observed['original_snapshot']['items']})
        self.assertEqual(self.client.mutations, before)

        self.client.nodes[self.asset]['parent'] = {'id': self.other_shelf}
        moved = self.observe_fixture(observed, entity_id=self.asset)
        moved_observation = next(row for row in moved['observations']
                                 if row['entity_id'] == self.asset)
        self.assertEqual([row['id'] for row in moved_observation['current_path']],
                         [self.other_cage, self.other_shelf, self.asset])
        self.assertTrue(moved_observation['expected'])
        self.assertEqual(moved['original_snapshot'], original)
        with self.ledger.connection() as db:
            self.assertEqual(db.execute('''SELECT count(*) FROM shelf_check_observations
                WHERE check_id=? AND entity_id=?''', (check['id'], self.unexpected_asset)).fetchone()[0], 1)
            before_journal = tuple(db.execute('''SELECT
                (SELECT count(*) FROM shelf_check_events),
                (SELECT count(*) FROM shelf_check_requests),
                (SELECT count(*) FROM shelf_check_observations)''').fetchone())
        with self.assertRaises(ValueError):
            self.observe_fixture(moved, entity_id=self.inaccessible_foreign_asset)
        unknown_resolution = self.store.resolve(self.client, self.ctx, check['id'],
                                                raw=self.inaccessible_foreign_asset)
        self.assertIsNone(unknown_resolution['entity_id'])
        self.assertEqual(unknown_resolution['candidates'], [])
        with self.ledger.connection() as db:
            after_journal = tuple(db.execute('''SELECT
                (SELECT count(*) FROM shelf_check_events),
                (SELECT count(*) FROM shelf_check_requests),
                (SELECT count(*) FROM shelf_check_observations)''').fetchone())
        self.assertEqual(after_journal, before_journal)

    def test_start_freezes_native_parent_version_and_transaction_custody(self):
        checkout = self.ledger.begin(self.group, self.actor, 'check_out', [self.asset],
                                     self.new_key(), intent={'fixture': 'snapshot custody'})
        self.ledger.complete(checkout['id'])
        self.client.nodes[self.asset]['updatedAt'] = 'native-v1'
        self.client.nodes[self.asset]['version'] = 17
        check = self.start_fixture()
        item = next(row for row in check['original_snapshot']['items']
                    if row['id'] == self.asset)
        self.assertEqual(item['parent_id'], self.shelf)
        self.assertFalse(item['archived'])
        self.assertEqual(item['native_updated_at'], 'native-v1')
        self.assertEqual(item['native_version'], 17)
        self.assertEqual(item['custody'], {'checked_out': True, 'actor_id': self.actor,
                                           'operation_id': checkout['id']})

        self.client.nodes[self.asset]['parent'] = {'id': self.box}
        self.client.nodes[self.asset]['archived'] = True
        self.client.nodes[self.asset]['updatedAt'] = 'native-v2'
        returned = self.ledger.begin(self.group, self.actor, 'return', [self.asset],
                                     self.new_key(), intent={'fixture': 'changed after snapshot'})
        self.ledger.complete(returned['id'])
        with self.ledger.connection() as db:
            persisted = db.execute('SELECT original_snapshot_json FROM shelf_checks WHERE id=?',
                                   (check['id'],)).fetchone()[0]
        self.assertEqual(json.loads(persisted), check['original_snapshot'])

    def test_observe_rejects_archived_deleted_or_broken_target_ancestry(self):
        failures = ('archived shelf', 'deleted shelf', 'archived ancestor')
        for failure in failures:
            with self.subTest(failure=failure):
                check = self.start_fixture()
                if failure == 'archived shelf':
                    self.client.nodes[self.shelf]['archived'] = True
                elif failure == 'deleted shelf':
                    shelf_before = self.client.nodes[self.shelf].copy()
                    del self.client.nodes[self.shelf]
                else:
                    self.client.nodes[self.rack]['archived'] = True
                with self.ledger.connection() as db:
                    before = tuple(db.execute('''SELECT
                        (SELECT count(*) FROM shelf_check_events),
                        (SELECT count(*) FROM shelf_check_requests),
                        (SELECT count(*) FROM shelf_check_observations)''').fetchone())
                try:
                    with self.assertRaises(ValueError):
                        self.observe_fixture(check)
                finally:
                    if failure == 'archived shelf':
                        self.client.nodes[self.shelf]['archived'] = False
                    elif failure == 'deleted shelf':
                        self.client.nodes[self.shelf] = shelf_before
                    else:
                        self.client.nodes[self.rack]['archived'] = False
                with self.ledger.connection() as db:
                    after = tuple(db.execute('''SELECT
                        (SELECT count(*) FROM shelf_check_events),
                        (SELECT count(*) FROM shelf_check_requests),
                        (SELECT count(*) FROM shelf_check_observations)''').fetchone())
                self.assertEqual(after, before)

    def test_observation_replay_precedes_terminal_and_fresh_write_checks(self):
        check = self.start_fixture()
        request_key = self.new_key()
        observed = self.observe_fixture(check, request_key=request_key)
        with self.ledger.connection() as db:
            db.execute("UPDATE shelf_checks SET state='completed' WHERE id=?", (check['id'],))
            before = tuple(db.execute('''SELECT
                (SELECT count(*) FROM shelf_check_events),
                (SELECT count(*) FROM shelf_check_requests),
                (SELECT count(*) FROM shelf_check_observations)''').fetchone())
        replayed = self.observe_fixture(check, request_key=request_key)
        self.assertEqual(replayed, observed)
        with self.assertRaises(Conflict):
            self.observe_fixture(check)
        with self.ledger.connection() as db:
            after = tuple(db.execute('''SELECT
                (SELECT count(*) FROM shelf_check_events),
                (SELECT count(*) FROM shelf_check_requests),
                (SELECT count(*) FROM shelf_check_observations)''').fetchone())
        self.assertEqual(after, before)

    def test_invalid_revision_shapes_rejected_without_journal_writes(self):
        check = self.start_fixture()
        with self.ledger.connection() as db:
            before = tuple(db.execute('''SELECT
                (SELECT count(*) FROM shelf_check_events),
                (SELECT count(*) FROM shelf_check_requests),
                (SELECT count(*) FROM shelf_check_observations)''').fetchone())
        for revision in (None, True, -1):
            with self.subTest(revision=revision):
                with self.assertRaises(ValueError):
                    self.store.observe(
                        self.client, self.ctx, check['id'], revision=revision,
                        entity_id=self.asset, method='scan', request_key=self.new_key())
        with self.ledger.connection() as db:
            after = tuple(db.execute('''SELECT
                (SELECT count(*) FROM shelf_check_events),
                (SELECT count(*) FROM shelf_check_requests),
                (SELECT count(*) FROM shelf_check_observations)''').fetchone())
        self.assertEqual(after, before)

    def test_refresh_preserves_original_and_observations(self):
        check = self.start_fixture(include_nested=True)
        observed = self.observe_fixture(check)
        original = observed['original_snapshot']
        self.client.nodes[self.asset]['parent'] = {'id': self.other_shelf}
        self.client.nodes[self.box]['quantity'] = 4
        self.client.nodes[self.nested_asset]['archived'] = True
        added = self.client.add('New expected drill', parent=self.shelf, quantity=2)
        checkout = self.ledger.begin(self.group, self.actor, 'check_out', [self.box],
                                     self.new_key(), intent={'fixture': 'custody changed'})
        self.ledger.complete(checkout['id'])
        with self.assertRaises(Conflict):
            self.store.finish(self.client, self.ctx, check['id'], revision=observed['revision'],
                              review_fingerprint=check['review_fingerprint'],
                              request_key=self.new_key())

        refreshed = self.store.refresh(self.client, self.ctx, check['id'],
                                       revision=observed['revision'], request_key=self.new_key())
        self.assertEqual(refreshed['original_snapshot'], original)
        self.assertEqual(refreshed['observations'], observed['observations'])
        changes = {row['kind']: row for row in refreshed['changes']}
        self.assertIn(self.nested_asset, {row['id'] for row in changes['removed']['items']})
        self.assertIn(added, {row['id'] for row in changes['added']['items']})
        changed_box = next(row for row in changes['changed']['items'] if row['id'] == self.box)
        self.assertIn('custody', changed_box['fields'])
        refreshed_again = self.store.refresh(self.client, self.ctx, check['id'],
                                             revision=refreshed['revision'], request_key=self.new_key())
        changes_again = {row['kind']: row for row in refreshed_again['changes']}
        self.assertIn(self.nested_asset, {row['id'] for row in changes_again['removed']['items']})
        finished = self.store.finish(self.client, self.ctx, check['id'],
                                     revision=refreshed_again['revision'],
                                     review_fingerprint=refreshed_again['review_fingerprint'],
                                     request_key=self.new_key())
        self.assertEqual(finished['state'], 'completed')
        self.assertTrue(finished['point_in_time'])
        self.assertEqual(finished['original_snapshot'], original)
        self.assertEqual(finished['observations'], observed['observations'])
        self.assertEqual(self.client.mutations, [])
        self.assertEqual(self.client.physical_outputs, [])

    def test_review_fingerprint_tracks_observed_unexpected_and_location_path(self):
        check = self.start_fixture()
        observed = self.observe_fixture(check, entity_id=self.unexpected_asset)
        refreshed = self.store.refresh(self.client, self.ctx, check['id'],
                                       revision=observed['revision'], request_key=self.new_key())
        self.assertIn(self.unexpected_asset, {row['id'] for change in refreshed['changes']
                                              if change['kind'] == 'observed'
                                              for row in change['items']})
        self.client.nodes[self.unexpected_asset]['quantity'] = 7
        live = self.store.get(self.client, self.ctx, check['id'])
        changed_observed = next(row for change in live['changes'] if change['kind'] == 'observed'
                                for row in change['items'] if row['id'] == self.unexpected_asset)
        self.assertIn('quantity', changed_observed['fields'])
        with self.ledger.connection() as db:
            before_failure = tuple(db.execute('SELECT state,revision FROM shelf_checks WHERE id=?',
                                              (check['id'],)).fetchone()) + tuple(db.execute('''SELECT
                (SELECT count(*) FROM shelf_check_events WHERE check_id=?),
                (SELECT count(*) FROM shelf_check_requests WHERE group_id=?)''',
                (check['id'], self.group)).fetchone())
        with self.assertRaises(Conflict):
            self.store.finish(self.client, self.ctx, check['id'], revision=refreshed['revision'],
                              review_fingerprint=refreshed['review_fingerprint'],
                              request_key=self.new_key())
        with self.ledger.connection() as db:
            after_failure = tuple(db.execute('SELECT state,revision FROM shelf_checks WHERE id=?',
                                             (check['id'],)).fetchone()) + tuple(db.execute('''SELECT
                (SELECT count(*) FROM shelf_check_events WHERE check_id=?),
                (SELECT count(*) FROM shelf_check_requests WHERE group_id=?)''',
                (check['id'], self.group)).fetchone())
        self.assertEqual(after_failure, before_failure)
        saved_unexpected = dict(self.client.nodes[self.unexpected_asset])
        self.client.nodes.pop(self.unexpected_asset)
        with self.assertRaises(Conflict):
            self.store.finish(self.client, self.ctx, check['id'], revision=refreshed['revision'],
                              review_fingerprint=refreshed['review_fingerprint'],
                              request_key=self.new_key())
        self.client.nodes[self.unexpected_asset] = saved_unexpected
        refreshed = self.store.refresh(self.client, self.ctx, check['id'],
                                       revision=refreshed['revision'], request_key=self.new_key())
        self.client.nodes[self.unexpected_asset]['archived'] = True
        with self.assertRaises(Conflict):
            self.store.finish(self.client, self.ctx, check['id'], revision=refreshed['revision'],
                              review_fingerprint=refreshed['review_fingerprint'],
                              request_key=self.new_key())
        self.client.nodes[self.unexpected_asset]['archived'] = False
        refreshed = self.store.refresh(self.client, self.ctx, check['id'],
                                       revision=refreshed['revision'], request_key=self.new_key())
        self.client.nodes[self.unexpected_asset]['parent'] = {'id': self.shelf}
        with self.assertRaises(Conflict):
            self.store.finish(self.client, self.ctx, check['id'], revision=refreshed['revision'],
                              review_fingerprint=refreshed['review_fingerprint'],
                              request_key=self.new_key())

        self.client.nodes[self.unexpected_asset]['parent'] = {'id': self.other_shelf}
        refreshed = self.store.refresh(self.client, self.ctx, check['id'],
                                       revision=refreshed['revision'], request_key=self.new_key())
        custody = self.ledger.begin(self.group, self.actor, 'check_out', [self.unexpected_asset],
                                    self.new_key(), intent={'fixture': 'unexpected custody'})
        self.ledger.complete(custody['id'])
        with self.assertRaises(Conflict):
            self.store.finish(self.client, self.ctx, check['id'], revision=refreshed['revision'],
                              review_fingerprint=refreshed['review_fingerprint'],
                              request_key=self.new_key())

        empty_location = self.client.add('Empty shelf', location=True, parent=self.rack)
        location_check = self.store.start(self.client, self.ctx, location_id=empty_location,
                                          request_key=self.new_key())
        location_review = self.store.refresh(self.client, self.ctx, location_check['id'],
                                             revision=location_check['revision'],
                                             request_key=self.new_key())
        self.client.nodes[self.rack]['parent'] = {'id': self.other_cage}
        with self.assertRaises(Conflict):
            self.store.finish(self.client, self.ctx, location_check['id'],
                              revision=location_review['revision'],
                              review_fingerprint=location_review['review_fingerprint'],
                              request_key=self.new_key())
        location_refreshed = self.store.refresh(self.client, self.ctx, location_check['id'],
                                                revision=location_review['revision'],
                                                request_key=self.new_key())
        self.assertTrue(any(row['kind'] == 'location' for row in location_refreshed['changes']))
        location_finished = self.store.finish(self.client, self.ctx, location_check['id'],
                                              revision=location_refreshed['revision'],
                                              review_fingerprint=location_refreshed['review_fingerprint'],
                                              request_key=self.new_key())
        self.assertEqual(location_finished['state'], 'completed')

    def test_latest_review_membership_and_common_mutation_read_shape(self):
        check = self.start_fixture()
        self.assert_common_check_shape(check)
        self.assertTrue(check['can_edit'])
        added = self.client.add('Added after start', parent=self.shelf, quantity=3)
        observed = self.store.observe(self.client, self.ctx, check['id'], revision=check['revision'],
                                      entity_id=self.asset, method='visual', request_key=self.new_key())
        self.assert_common_check_shape(observed)
        live = self.store.get(self.client, self.ctx, check['id'])
        self.assertIn(added, {row['id'] for change in live['changes'] if change['kind'] == 'added'
                              for row in change['items']})
        refreshed = self.store.refresh(self.client, self.ctx, check['id'],
                                       revision=observed['revision'], request_key=self.new_key())
        self.assert_common_check_shape(refreshed)
        view = self.store.get(self.client, self.ctx, check['id'])
        self.assert_common_check_shape(view)
        self.assertTrue(view['can_edit'])
        self.assertIn(added, {row['id'] for row in view['groups']['not_observed']})
        other_view = self.store.get(self.client, self.other_manager_ctx, check['id'])
        self.assert_common_check_shape(other_view)
        self.assertFalse(other_view['can_edit'])
        self.client.nodes.pop(added)
        refreshed_again = self.store.refresh(self.client, self.ctx, check['id'],
                                             revision=refreshed['revision'], request_key=self.new_key())
        self.assertIn(added, {row['id'] for change in refreshed_again['changes']
                              if change['kind'] == 'removed' for row in change['items']})
        noted = self.store.save_notes(self.client, self.ctx, check['id'], revision=refreshed_again['revision'],
                                      notes='reviewed', request_key=self.new_key())
        self.assert_common_check_shape(noted)
        finished = self.store.finish(self.client, self.ctx, check['id'],
                                     revision=noted['revision'],
                                     review_fingerprint=noted['review_fingerprint'],
                                     request_key=self.new_key())
        self.assert_common_check_shape(finished)

    def test_removed_observation_keeps_current_path_and_custody_grouping(self):
        check = self.start_fixture()
        observed = self.observe_fixture(check)
        checkout = self.ledger.begin(self.group, self.actor, 'check_out', [self.asset],
                                     self.new_key(), intent={'fixture': 'observed item loan'})
        self.ledger.complete(checkout['id'])
        self.client.nodes[self.asset]['parent'] = {'id': self.other_shelf}
        view = self.store.get(self.client, self.ctx, check['id'])
        row = next(item for item in view['groups']['observed_here'] if item['id'] == self.asset)
        self.assertNotIn(self.asset, {item['id'] for item in view['groups']['unexpected_here']})
        self.assertTrue(row['available'])
        self.assertTrue(row['custody_conflict'])
        self.assertEqual(row['current_path'][-1]['id'], self.asset)
        self.assertEqual(view['observations'][0]['last_observed_at'],
                         observed['observations'][0]['last_observed_at'])

    def test_checked_out_unexpected_observation_is_grouped_once_as_observed(self):
        check = self.start_fixture()
        self.observe_fixture(check, entity_id=self.unexpected_asset)
        checkout = self.ledger.begin(self.group, self.actor, 'check_out', [self.unexpected_asset],
                                     self.new_key(), intent={'fixture': 'unexpected checked out'})
        self.ledger.complete(checkout['id'])
        view = self.store.get(self.client, self.ctx, check['id'])
        observed_rows = [row for row in view['groups']['observed_here']
                         if row['id'] == self.unexpected_asset]
        unexpected_ids = {row['id'] for row in view['groups']['unexpected_here']}
        self.assertEqual(len(observed_rows), 1)
        self.assertTrue(observed_rows[0]['custody_conflict'])
        self.assertNotIn(self.unexpected_asset, unexpected_ids)

    def test_save_notes_refuses_suspended_draft_without_journal_changes(self):
        check = self.start_fixture()
        self.client.nodes.pop(self.shelf)
        with self.ledger.connection() as db:
            before = tuple(db.execute('SELECT state,revision,notes FROM shelf_checks WHERE id=?',
                                      (check['id'],)).fetchone()) + tuple(db.execute('''SELECT
                (SELECT count(*) FROM shelf_check_events WHERE check_id=?),
                (SELECT count(*) FROM shelf_check_requests WHERE group_id=?)''',
                (check['id'], self.group)).fetchone())
        with self.assertRaises(Conflict):
            self.store.save_notes(self.client, self.ctx, check['id'], revision=check['revision'],
                                  notes='must not save while suspended', request_key=self.new_key())
        with self.ledger.connection() as db:
            after = tuple(db.execute('SELECT state,revision,notes FROM shelf_checks WHERE id=?',
                                     (check['id'],)).fetchone()) + tuple(db.execute('''SELECT
                (SELECT count(*) FROM shelf_check_events WHERE check_id=?),
                (SELECT count(*) FROM shelf_check_requests WHERE group_id=?)''',
                (check['id'], self.group)).fetchone())
        self.assertEqual(after, before)

    def test_loan_groups_and_pending_native_operations(self):
        checkout = self.ledger.begin(self.group, self.actor, 'check_out', [self.asset],
                                     self.new_key(), intent={'fixture': 'checked out at start'})
        self.ledger.complete(checkout['id'])
        pending = self.ledger.begin(self.group, self.actor, 'check_out', [self.nested_asset],
                                    self.new_key(), intent={'fixture': 'pending'})
        foreign_pending = self.ledger.begin(str(uuid4()), self.actor, 'check_out', [self.unexpected_asset],
                                            self.new_key(), intent={'fixture': 'other group'})
        check = self.start_fixture(include_nested=True)
        observed = self.observe_fixture(check, entity_id=self.box)
        observed_checkout = self.ledger.begin(self.group, self.actor, 'check_out', [self.box],
                                              self.new_key(), intent={'fixture': 'observed loan conflict'})
        self.ledger.complete(observed_checkout['id'])
        view = self.store.get(self.client, self.ctx, check['id'])
        self.assertIn(self.box, {row['id'] for row in view['groups']['observed_here']})
        observed_box = next(row for row in view['groups']['observed_here'] if row['id'] == self.box)
        self.assertTrue(observed_box['custody_conflict'])
        self.assertNotIn(self.box, {row['id'] for row in view['groups']['checked_out']})
        self.assertIn(self.asset, {row['id'] for row in view['groups']['checked_out']})
        self.assertIn(self.nested_asset, {row['id'] for row in view['groups']['not_observed']})
        operation_ids = {row['id'] for row in view['pending_operations']}
        self.assertIn(pending['id'], operation_ids)
        self.assertNotIn(foreign_pending['id'], operation_ids)
        self.assertEqual(view['pending_operations'][0]['status'], 'pending')
        self.assertEqual(observed['revision'], check['revision'] + 1)

    def test_history_is_location_and_collection_scoped(self):
        first = self.start_fixture()
        second = self.store.start(self.client, self.ctx, location_id=self.other_shelf,
                                  request_key=self.new_key())
        foreign_ctx = self.context(group=str(uuid4()), actor=str(uuid4()))
        foreign = self.store.start(self.client, foreign_ctx, location_id=self.shelf,
                                   request_key=self.new_key())
        all_rows = self.store.history(self.client, self.ctx)
        self.assertEqual({row['id'] for row in all_rows}, {first['id'], second['id']})
        filtered = self.store.history(self.client, self.ctx, location_id=self.shelf, limit=1)
        self.assertEqual([row['id'] for row in filtered], [first['id']])
        self.assertNotIn(foreign['id'], {row['id'] for row in all_rows})
        for limit in (0, 101, True):
            with self.assertRaises(ValueError):
                self.store.history(self.client, self.ctx, limit=limit)

    def test_deleted_shelf_and_former_owner_remain_reviewable(self):
        check = self.start_fixture()
        self.client.remove_location_and_owner()
        read = self.store.get(self.client, self.other_manager_ctx, check['id'])
        self.assertTrue(read['suspended_reason'])
        self.assertEqual(read['actor_label'], 'Former C-Crate member')
        self.assertFalse(read['can_edit'])
        self.assert_common_check_shape(read)
        owner_suspended = self.store.get(self.client, self.ctx, check['id'])
        self.assertFalse(owner_suspended['can_edit'])
        self.assertTrue(owner_suspended['suspended_reason'])
        with self.assertRaises(Conflict):
            self.finish_fixture(check)
        with self.assertRaises(ValueError):
            self.store.cancel(self.client, self.other_manager_ctx, check['id'],
                              revision=check['revision'], confirmed=False,
                              reason='Owner unavailable', request_key=self.new_key())
        cancelled = self.store.cancel(self.client, self.other_manager_ctx, check['id'],
                                      revision=check['revision'], confirmed=True,
                                      reason='Owner unavailable', request_key=self.new_key())
        self.assertEqual(cancelled['cancelled_by'], self.other_manager_ctx['actor'])
        self.assert_common_check_shape(cancelled)
        self.assertFalse(cancelled['can_edit'])
        self.assertEqual(cancelled['original_snapshot'], check['original_snapshot'])
        self.assertEqual(self.store.get(self.client, self.other_manager_ctx, check['id'])['cancel_reason'],
                         'Owner unavailable')

    def test_rename_only_and_terminal_immutability(self):
        check = self.start_fixture()
        observed = self.observe_fixture(check)
        self.client.nodes[self.asset]['name'] = 'Renamed drill'
        self.client.nodes[self.asset]['updatedAt'] = 'native-v2'
        self.client.nodes[self.asset]['version'] = 2
        self.client.nodes[self.rack]['name'] = 'Renamed rack'
        refreshed = self.store.refresh(self.client, self.ctx, check['id'],
                                       revision=observed['revision'], request_key=self.new_key())
        self.assertEqual(refreshed['observations'], observed['observations'])
        self.assertEqual(refreshed['original_snapshot'], check['original_snapshot'])
        renamed = next(row for row in refreshed['reviewed_snapshot']['items'] if row['id'] == self.asset)
        self.assertEqual(renamed['name'], 'Renamed drill')
        self.assertEqual(refreshed['review_fingerprint'], check['review_fingerprint'])
        self.assertIn(self.asset, {row['id'] for change in refreshed['changes']
                                   if change['kind'] == 'renamed' for row in change['items']})
        self.assertNotIn(self.asset, {row['id'] for change in refreshed['changes']
                                      if change['kind'] == 'changed' for row in change['items']})
        with self.assertRaises(CheckAccessDenied):
            self.store.refresh(self.client, self.other_manager_ctx, check['id'],
                               revision=refreshed['revision'], request_key=self.new_key())
        with self.assertRaises(CheckAccessDenied):
            self.store.finish(self.client, self.other_manager_ctx, check['id'],
                              revision=refreshed['revision'],
                              review_fingerprint=refreshed['review_fingerprint'],
                              request_key=self.new_key())
        with self.assertRaises(CheckAccessDenied):
            self.store.observe(self.client, self.other_manager_ctx, check['id'],
                               revision=refreshed['revision'], entity_id=self.asset,
                               method='scan', request_key=self.new_key())
        finished = self.store.finish(self.client, self.ctx, check['id'],
                                     revision=refreshed['revision'],
                                     review_fingerprint=refreshed['review_fingerprint'],
                                     request_key=self.new_key())
        self.assertEqual(finished['state'], 'completed')
        self.assertFalse(finished['can_edit'])
        reviewed_at_finish = finished['reviewed_snapshot']
        self.client.nodes[self.asset]['name'] = 'Changed after completion'
        self.assertEqual(self.store.get(self.client, self.ctx, check['id'])['reviewed_snapshot'],
                         reviewed_at_finish)
        for mutation in (
            lambda: self.store.refresh(self.client, self.ctx, check['id'],
                                       revision=finished['revision'], request_key=self.new_key()),
            lambda: self.store.finish(self.client, self.ctx, check['id'],
                                      revision=finished['revision'],
                                      review_fingerprint=finished['review_fingerprint'],
                                      request_key=self.new_key()),
            lambda: self.store.cancel(self.client, self.ctx, check['id'],
                                      revision=finished['revision'], confirmed=True,
                                      reason='Too late', request_key=self.new_key()),
        ):
            with self.assertRaises(Conflict):
                mutation()
        self.assertEqual(self.client.mutations, [])
        self.assertEqual(self.client.physical_outputs, [])

    def test_companion_lock_and_point_in_time_versions(self):
        check = self.start_fixture()
        lock = threading.Lock()
        self.client.required_lock = lock
        with lock:
            refreshed = self.store.refresh(self.client, self.ctx, check['id'],
                                           revision=check['revision'], request_key=self.new_key())
        with lock:
            finished = self.store.finish(self.client, self.ctx, check['id'],
                                         revision=refreshed['revision'],
                                         review_fingerprint=refreshed['review_fingerprint'],
                                         request_key=self.new_key())
        self.assertTrue(finished['point_in_time'])
        self.assertIsNotNone(finished['completed_at'])
        self.assertEqual(datetime.fromisoformat(finished['completed_at']).utcoffset(),
                         timezone.utc.utcoffset(None))
        current_item = next(row for row in finished['reviewed_snapshot']['items']
                            if row['id'] == self.asset)
        self.assertEqual(current_item['native_updated_at'], self.client.nodes[self.asset].get('updatedAt'))
        self.assertEqual(current_item['native_version'], self.client.nodes[self.asset].get('version'))
        self.assertEqual(self.client.mutations, [])
        self.assertEqual(self.client.physical_outputs, [])

    def test_zero_tally_notes_and_stale_revision(self):
        check = self.start_fixture()
        zero = self.observe_fixture(check, observed_quantity=0, method='visual')
        self.assertEqual(zero['observations'][0]['observed_quantity'], 0)
        self.assertEqual(zero['observations'][0]['status'], 'not_observed')
        with self.assertRaises(Conflict):
            self.store.save_notes(self.client, self.ctx, check['id'], revision=check['revision'],
                                  notes='stale', request_key=self.new_key())
        with self.assertRaises(ValueError):
            self.store.save_notes(self.client, self.ctx, check['id'], revision=zero['revision'],
                                  notes='x' * 1001, request_key=self.new_key())
        noted = self.store.save_notes(self.client, self.ctx, check['id'], revision=zero['revision'],
                                      notes='Plain text note', request_key=self.new_key())
        self.assertEqual(noted['notes'], 'Plain text note')
        self.assertEqual(noted['revision'], zero['revision'] + 1)

    def test_replace_cannot_rewrite_terminal_check_events_or_request_results(self):
        key = self.new_key()
        check_id = str(uuid4())
        result = self.store._apply(
            self.ctx, 'fixture', {'value': 'original'}, key,
            self.change(self.ctx, check_id=check_id, state='completed', revision=7))
        with self.ledger.connection() as db:
            original_check = tuple(db.execute(
                'SELECT * FROM shelf_checks WHERE id=?', (check_id,)).fetchone())
            original_event = tuple(db.execute(
                'SELECT * FROM shelf_check_events').fetchone())
            original_request = tuple(db.execute(
                'SELECT * FROM shelf_check_requests').fetchone())

            with self.assertRaisesRegex(sqlite3.IntegrityError, 'immutable'):
                db.execute('''INSERT OR REPLACE INTO shelf_checks
                    (id,group_id,actor_id,location_id,include_nested,started_at,state,revision,
                     original_snapshot_json,reviewed_snapshot_json,review_fingerprint,notes,
                     completed_at,cancelled_at,cancelled_by,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (check_id, self.group, self.actor, str(uuid4()), 1, 'later', 'draft', 0,
                     '{"items":["replacement"]}', None, None, 'replacement', None, None,
                     None, 'later', 'later'))
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'append-only'):
                db.execute('''INSERT OR REPLACE INTO shelf_check_events
                    (sequence,check_id,group_id,actor_id,action,intent_sha256,revision,created_at)
                    VALUES(?,?,?,?,?,?,?,?)''',
                    (original_event[0], check_id, self.group, self.actor, 'replacement',
                     '0' * 64, 0, 'later'))
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'immutable'):
                db.execute('''INSERT OR REPLACE INTO shelf_check_requests
                    (sequence,group_id,request_key,actor_id,action,intent_sha256,result_json,created_at)
                    VALUES(?,?,?,?,?,?,?,?)''',
                    (original_request[0], self.group, key, self.actor, 'replacement',
                     '0' * 64, '{"replacement":true}', 'later'))
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'immutable'):
                db.execute('''INSERT OR REPLACE INTO shelf_check_requests
                    (group_id,request_key,actor_id,action,intent_sha256,result_json,created_at)
                    VALUES(?,?,?,?,?,?,?)''',
                    (self.group, key, self.actor, 'replacement', '0' * 64,
                     '{"replacement":true}', 'later'))

            self.assertEqual(tuple(db.execute(
                'SELECT * FROM shelf_checks WHERE id=?', (check_id,)).fetchone()), original_check)
            self.assertEqual(tuple(db.execute(
                'SELECT * FROM shelf_check_events').fetchone()), original_event)
            self.assertEqual(tuple(db.execute(
                'SELECT * FROM shelf_check_requests').fetchone()), original_request)
        self.assertEqual(self.store.request(self.ctx, key)['result'], result)

    def test_schema_is_idempotent_and_preserves_existing_custody_and_history(self):
        operation = self.ledger.begin(self.group, self.actor, 'check_out', [self.asset],
                                      self.new_key(), intent={'fixture': 'existing history'})
        self.ledger.complete(operation['id'])
        with self.ledger.connection() as db:
            prior_version = db.execute('PRAGMA user_version').fetchone()[0]
            prior_events = db.execute('SELECT * FROM events ORDER BY sequence').fetchall()
            prior_custody = db.execute('SELECT * FROM custody ORDER BY group_id,entity_id').fetchall()

        ShelfChecks(self.ledger)
        reopened_ledger = Ledger(self.ledger.path)
        ShelfChecks(reopened_ledger)
        with reopened_ledger.connection() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], prior_version)
            names = {row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            self.assertTrue({'shelf_checks', 'shelf_check_observations', 'shelf_check_events',
                             'shelf_check_requests', 'shelf_check_schema_meta'} <= names)
            self.assertEqual(db.execute('SELECT version FROM shelf_check_schema_meta WHERE singleton=1').fetchone()[0], 2)
            self.assertEqual(db.execute('SELECT * FROM events ORDER BY sequence').fetchall(), prior_events)
            self.assertEqual(db.execute('SELECT * FROM custody ORDER BY group_id,entity_id').fetchall(), prior_custody)

    def test_task1_schema_migrates_observations_with_empty_current_path(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        legacy = Ledger(pathlib.Path(temp.name) / 'legacy.db')
        with legacy.connection() as db:
            db.execute('''CREATE TABLE shelf_check_observations(
                check_id TEXT NOT NULL,group_id TEXT NOT NULL,entity_id TEXT NOT NULL,
                method TEXT NOT NULL,observed_quantity INTEGER NOT NULL,
                first_observed_at TEXT NOT NULL,last_observed_at TEXT NOT NULL,
                PRIMARY KEY(check_id,entity_id))''')
            db.execute('''INSERT INTO shelf_check_observations VALUES(?,?,?,?,?,?,?)''',
                       ('check', 'group', 'entity', 'scan', 1, 'first', 'last'))
            db.execute('''CREATE TABLE shelf_check_schema_meta(
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),version INTEGER NOT NULL)''')
            db.execute('INSERT INTO shelf_check_schema_meta VALUES(1,1)')

        ShelfChecks(legacy)
        with legacy.connection() as db:
            columns = {row['name'] for row in db.execute(
                'PRAGMA table_info(shelf_check_observations)')}
            self.assertIn('current_path_json', columns)
            self.assertEqual(db.execute('SELECT version FROM shelf_check_schema_meta').fetchone()[0], 2)
            row = db.execute('SELECT * FROM shelf_check_observations').fetchone()
            self.assertEqual(row['observed_quantity'], 1)
            self.assertEqual(row['current_path_json'], '[]')


if __name__ == '__main__':
    unittest.main()
