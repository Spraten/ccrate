"""Journaled standalone notes written only to a disposable native fixture."""
import copy
import hashlib
import pathlib
import tempfile
import unittest
import urllib.error
from uuid import uuid4

from item_notes import recover_note, submit_note
from ledger import Conflict, Ledger
from native_jobs import NativeJobs


def ident():
    return str(uuid4())


class FakeNative:
    def __init__(self, group, entity_id, *, location=False, archived=False):
        self.group = group
        self.tenant = group
        self.entity_id = entity_id
        self.item = {'id': entity_id, 'name': 'Fixture drill', 'archived': archived,
                     'notes': 'Preserve these native notes.',
                     'entityType': {'isLocation': location},
                     'fields': [{'name': 'Equipment condition', 'type': 'text', 'textValue': 'Ready'}]}
        self.entries = []
        self.calls = []
        self.after_post = None

    def entity(self, entity_id):
        if str(entity_id) != self.entity_id or self.tenant != self.group:
            raise urllib.error.HTTPError('native', 403, 'foreign', {}, None)
        return copy.deepcopy(self.item)

    def call(self, path, method='GET', data=None):
        self.calls.append((path, method, copy.deepcopy(data)))
        prefix = '/api/v1/entities/'+self.entity_id+'/maintenance'
        if path != prefix:
            raise AssertionError('Unexpected native path '+path)
        if method == 'GET':
            return copy.deepcopy(self.entries)
        if method != 'POST':
            raise AssertionError('Unexpected native method '+method)
        row = {'id': ident(), **copy.deepcopy(data)}
        self.entries.append(row)
        if self.after_post == 'duplicate':
            self.entries.append(dict(row, id=ident()))
        if self.after_post == 'edit':
            row['description'] += ' edited outside the journal'
        if self.after_post == 'lost_reply':
            self.after_post = None
            raise OSError('injected lost response after native commit')
        return {'item': copy.deepcopy(row)}

    @property
    def posts(self):
        return [call for call in self.calls if call[1] == 'POST']


class ItemNoteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(pathlib.Path(self.temp.name)/'ops.db')
        self.jobs = NativeJobs(self.ledger)
        self.group, self.actor, self.other_actor, self.entity = [ident() for _ in range(4)]
        self.client = FakeNative(self.group, self.entity)

    def tearDown(self):
        self.temp.cleanup()

    def submit(self, note='Check the handle before use.', key=None, client=None, actor=None, **extra):
        data = {'entity_id': self.entity, 'note': note, **extra}
        return submit_note(client or self.client, self.jobs, self.group, actor or self.actor,
                           key or ident(), data, 'Fixture Operator')

    def events(self, job_id):
        with self.ledger.connection() as db:
            return [dict(row) for row in db.execute(
                'SELECT kind,detail FROM native_job_events WHERE job_id=? ORDER BY sequence', (job_id,))]

    def journal_counts(self):
        with self.ledger.connection() as db:
            return tuple(db.execute('SELECT count(*) FROM '+table).fetchone()[0]
                         for table in ('native_jobs', 'native_job_events'))

    def test_completed_note_has_verified_native_reference_and_no_body_mirror(self):
        result = self.submit()
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len(self.client.posts), 1)
        entry = self.client.entries[0]
        self.assertEqual(entry['name'], 'Item note')
        self.assertEqual(entry['scheduledDate'], '')
        self.assertRegex(entry['completedDate'], r'^\d{4}-\d{2}-\d{2}$')
        self.assertEqual(entry['cost'], '0')
        self.assertTrue(entry['description'].endswith('[Kiosk note '+result['id']+']'))
        self.assertEqual(self.client.item['notes'], 'Preserve these native notes.')
        self.assertEqual(self.client.item['fields'][0]['textValue'], 'Ready')
        job = self.jobs.detail(self.group, result['id'])
        self.assertEqual((job['status'], job['result_id']), ('completed', self.entity))
        self.assertIsNone(job['payload']); self.assertEqual(job['context'], {})
        saved = [__import__('json').loads(e['detail']) for e in self.events(result['id']) if e['kind'] == 'note_verified'][-1:]
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]['maintenance_id'], entry['id'])
        self.assertEqual(saved[0]['entity_id'], self.entity)
        self.assertEqual(saved[0]['actor_id'], self.actor)
        self.assertEqual(saved[0]['author_name'], 'Fixture Operator')
        self.assertEqual(saved[0]['content_sha256'], hashlib.sha256(b'Check the handle before use.').hexdigest())
        self.assertNotIn('note', saved[0])

    def test_same_key_replay_is_idempotent_and_changed_body_conflicts(self):
        key = ident(); first = self.submit('First note', key)
        second = self.submit('First note', key)
        self.assertEqual(second, first)
        self.assertEqual(len(self.client.posts), 1)
        with self.assertRaises(Conflict):
            self.submit('Different note', key)
        self.assertEqual(len(self.client.posts), 1)

    def test_completed_key_returns_saved_result_without_revalidating_native_item_or_author(self):
        key = ident(); first = self.submit('Already saved', key)
        self.client.item['archived'] = True
        repeated = submit_note(self.client, self.jobs, self.group, self.actor, key,
                               {'entity_id': self.entity, 'note': 'Already saved'}, '')
        self.assertEqual(repeated, first)
        self.assertEqual(len(self.client.posts), 1)

    def test_unresolved_cross_key_guard_is_atomic_and_scoped_to_group_actor_item(self):
        first_key = ident(); payload = {'entity_id': self.entity, 'note': 'Uncertain'}
        self.jobs.prepare(self.group, self.actor, 'add_note', first_key, payload)
        with self.assertRaises(Conflict):
            self.jobs.prepare(self.group, self.actor, 'add_note', ident(), payload)
        other = self.jobs.prepare(self.group, self.other_actor, 'add_note', ident(), payload)
        self.assertEqual(other['actor_id'], self.other_actor)
        other_group = self.jobs.prepare(ident(), self.actor, 'add_note', ident(), payload)
        self.assertEqual(other_group['status'], 'prepared')

    def test_text_and_full_description_utf8_limits_are_exact_and_never_truncated(self):
        self.submit('x'*1000)
        self.assertEqual(len(self.client.posts), 1)
        before = len(self.jobs.unresolved(self.group))
        before_long_rejection = self.journal_counts()
        with self.assertRaises(ValueError):
            self.submit('x'*1001)
        self.assertEqual(len(self.client.posts), 1)
        self.assertLessEqual(len(self.jobs.unresolved(self.group)), before)
        self.assertEqual(self.journal_counts(), before_long_rejection)
        marker_bytes = len(('\n\n[Kiosk note '+str(uuid4())+']').encode())
        note_bytes = 2500-marker_bytes
        note = '😀'*(note_bytes//4)+'a'*(note_bytes%4)
        result = self.submit(note)
        self.assertEqual(len(self.client.posts), 2)
        self.assertEqual(len(self.client.entries[-1]['description'].encode('utf-8')), 2500)
        before_rows = self.journal_counts()
        with self.assertRaises(ValueError):
            self.submit(note+'a')
        self.assertEqual(len(self.client.posts), 2)
        self.assertEqual(self.journal_counts(), before_rows)

    def test_location_archived_and_foreign_items_are_rejected_without_post(self):
        before_rows = self.journal_counts()
        for client in (FakeNative(self.group, self.entity, location=True),
                       FakeNative(self.group, self.entity, archived=True)):
            with self.assertRaises(ValueError):
                self.submit(client=client)
            self.assertEqual(client.posts, [])
            self.assertEqual(self.journal_counts(), before_rows)
        foreign = FakeNative(self.group, self.entity); foreign.tenant = ident()
        with self.assertRaises(urllib.error.HTTPError):
            self.submit(client=foreign)
        self.assertEqual(foreign.posts, [])
        self.assertEqual(self.journal_counts(), before_rows)

    def test_lost_reply_recovers_exact_native_entry_without_reposting(self):
        self.client.after_post = 'lost_reply'
        with self.assertRaises(Conflict):
            self.submit('Lost reply note')
        job = self.jobs.unresolved(self.group)[0]
        self.assertEqual(job['status'], 'review')
        self.assertEqual(len(self.client.posts), 1)
        result = recover_note(self.client, self.jobs, self.group, job['id'], 'complete')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len(self.client.posts), 1)
        self.assertEqual(self.jobs.detail(self.group, job['id'])['status'], 'completed')

    def test_failed_completion_recording_recovers_without_second_post(self):
        original = self.jobs.complete
        calls = []
        def fail_once(*args):
            calls.append(1)
            if len(calls) == 1:
                raise OSError('injected journal completion failure')
            return original(*args)
        self.jobs.complete = fail_once
        with self.assertRaises(Conflict):
            self.submit('Journal completion failure')
        job = self.jobs.unresolved(self.group)[0]
        self.assertEqual(job['status'], 'review')
        self.assertEqual(len(self.client.posts), 1)
        recover_note(self.client, self.jobs, self.group, job['id'], 'complete')
        self.assertEqual(len(self.client.posts), 1)
        self.assertEqual(self.jobs.detail(self.group, job['id'])['status'], 'completed')

    def test_failed_completion_cannot_rebind_verified_note_to_replacement_uuid(self):
        original = self.jobs.complete
        def fail_once(*args):
            self.jobs.complete = original
            raise OSError('injected journal completion failure')
        self.jobs.complete = fail_once
        with self.assertRaises(Conflict):
            self.submit('Immutable maintenance provenance')
        job = self.jobs.unresolved(self.group)[0]
        original_metadata = next(event['detail'] for event in self.jobs.events(self.group, job['id'])
                                 if event['kind'] == 'note_verified')
        old_id = self.client.entries[0]['id']
        self.client.entries[0]['id'] = ident()
        with self.assertRaises(Conflict):
            recover_note(self.client, self.jobs, self.group, job['id'], 'complete')
        remaining = self.jobs.detail(self.group, job['id'])
        verified = [event['detail'] for event in self.jobs.events(self.group, job['id'])
                    if event['kind'] == 'note_verified']
        self.assertEqual(remaining['status'], 'review')
        self.assertEqual(verified, [original_metadata])
        self.assertEqual(original_metadata['maintenance_id'], old_id)
        self.assertEqual(len(self.client.posts), 1)

    def test_contradictory_verified_event_cannot_be_overwritten_on_recovery(self):
        original = self.jobs.complete
        def fail_once(*args):
            self.jobs.complete = original
            raise OSError('injected journal completion failure')
        self.jobs.complete = fail_once
        with self.assertRaises(Conflict):
            self.submit('Contradictory evidence')
        job = self.jobs.unresolved(self.group)[0]
        first = next(event['detail'] for event in self.jobs.events(self.group, job['id'])
                     if event['kind'] == 'note_verified')
        contradictory = dict(first, maintenance_id=ident())
        with self.ledger.transaction() as db:
            self.jobs.event(db, job['id'], 'note_verified', contradictory)
        with self.assertRaises(Conflict):
            recover_note(self.client, self.jobs, self.group, job['id'], 'complete')
        events = [event['detail'] for event in self.jobs.events(self.group, job['id'])
                  if event['kind'] == 'note_verified']
        self.assertEqual(events, [first, contradictory])
        self.assertEqual(self.jobs.detail(self.group, job['id'])['status'], 'review')
        self.assertEqual(len(self.client.posts), 1)

    def test_uncertain_cancel_readback_mismatch_and_duplicate_never_repost(self):
        self.client.after_post = 'lost_reply'
        with self.assertRaises(Conflict): self.submit('Do not cancel started note')
        job = self.jobs.unresolved(self.group)[0]
        with self.assertRaises(Conflict): recover_note(self.client, self.jobs, self.group, job['id'], 'cancel')
        self.assertEqual(len(self.client.posts), 1)

        for behavior in ('edit', 'duplicate'):
            client = FakeNative(self.group, self.entity); client.after_post = behavior
            jobs = NativeJobs(Ledger(pathlib.Path(self.temp.name)/(behavior+'.db')))
            with self.assertRaises(Conflict):
                submit_note(client, jobs, self.group, self.actor, ident(),
                            {'entity_id': self.entity, 'note': 'Readback must be exact'}, 'Fixture Operator')
            self.assertEqual(len(client.posts), 1)
            self.assertEqual(jobs.unresolved(self.group)[0]['status'], 'review')

    def test_unstarted_note_can_be_cancelled_but_marker_alone_cannot_confirm_it(self):
        key = ident(); job = self.jobs.prepare(self.group, self.actor, 'add_note', key,
                                             {'entity_id': self.entity, 'note': 'Forged'})
        from item_notes import marker
        self.client.entries.append({
            'id': ident(), 'name': 'Item note',
            'description': 'Forged\n\n'+marker(job['id']),
            'completedDate': '2026-01-01', 'scheduledDate': '', 'cost': '0',
        })
        with self.assertRaises(Conflict):
            recover_note(self.client, self.jobs, self.group, job['id'], 'complete')
        with self.assertRaises(Conflict):
            recover_note(self.client, self.jobs, self.group, job['id'], 'cancel')
        self.assertEqual(self.jobs.detail(self.group, job['id'])['status'], 'review')
        self.assertEqual(self.client.posts, [])

        clean_job = self.jobs.prepare(self.group, ident(), 'add_note', ident(),
                                      {'entity_id': self.entity, 'note': 'Unsent'})
        result = recover_note(self.client, self.jobs, self.group, clean_job['id'], 'cancel')
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual(self.client.posts, [])


if __name__ == '__main__':
    unittest.main()
