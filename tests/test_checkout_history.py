import pathlib
import tempfile
import unittest
from uuid import uuid4
import hashlib

from checkout_cart import CheckoutCart
from desktop_api import history
from ledger import Ledger
from native_jobs import NativeJobs


def ident():
    return str(uuid4())


class HistoryClient:
    def __init__(self, actor, entity):
        self.actor, self.entity_row = actor, entity

    def call(self, path, method='GET', data=None):
        if path == '/api/v1/groups/members':
            return [{'id': self.actor, 'name': 'Current member name'}]
        raise AssertionError(path)

    def entities(self, archived=False):
        return [self.entity_row]

    def entity(self, entity_id):
        if entity_id != self.entity_row['id']:
            raise AssertionError(entity_id)
        return self.entity_row


class CheckoutHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(pathlib.Path(self.temp.name) / 'ledger.db')
        self.jobs = NativeJobs(self.ledger)
        self.group, self.actor, self.asset = ident(), ident(), ident()
        self.client = HistoryClient(self.actor, {'id': self.asset, 'name': 'Fixture item'})

    def tearDown(self):
        self.temp.cleanup()

    def test_checkout_history_uses_journal_actor_and_confirmation_time(self):
        note = 'Use the short clamp.'
        component = ident()
        operation = self.ledger.begin(self.group, self.actor, 'check_out', [self.asset, component], ident(),
                                      context={'checkout_notes': {self.asset: note}},
                                      intent={'checkout_notes': {self.asset: note}})
        self.ledger.complete(operation['id'])
        result = history({'client': self.client, 'group': self.group},
                         {'ledger': self.ledger, 'native_jobs': self.jobs}, self.asset)
        checkout = next(row for row in result if row['id'] == operation['id'])
        self.assertEqual(checkout['checkout_notes'], [{'entity_id': self.asset, 'text': note,
                                                       'author': 'Current member name',
                                                       'created_at': checkout['confirmed_at']}])

    def test_old_checkout_receipts_project_an_empty_notes_list(self):
        operation = self.ledger.begin(self.group, self.actor, 'check_out', [self.asset], ident())
        self.ledger.complete(operation['id'])
        result = history({'client': self.client, 'group': self.group},
                         {'ledger': self.ledger, 'native_jobs': self.jobs}, self.asset)
        checkout = next(row for row in result if row['id'] == operation['id'])
        self.assertEqual(checkout['checkout_notes'], [])

    def test_history_offset_pages_past_real_store_limits(self):
        for index in range(106):
            action = 'check_out' if index % 2 == 0 else 'return'
            operation = self.ledger.begin(self.group, self.actor, action, [self.asset], ident())
            self.ledger.complete(operation['id'])
        for _ in range(106):
            job = self.jobs.prepare(self.group, self.actor, 'create_asset', ident(), {})
            self.jobs.sent(self.group, job['id'])
            self.jobs.bind(self.group, job['id'], self.asset)
            self.jobs.complete(self.group, job['id'])
        deps = {'ledger': self.ledger, 'native_jobs': self.jobs}
        ctx = {'client': self.client, 'group': self.group}
        first = history(ctx, deps, self.asset)
        second = history(ctx, deps, self.asset, 100)
        third = history(ctx, deps, self.asset, 200)
        self.assertEqual(len(first), 100)
        self.assertEqual(len(second), 100)
        self.assertEqual(len(third), 12)
        pages = first + second + third
        self.assertEqual(len({row['id'] for row in pages}), 212)

    def test_offset_history_enriches_only_rows_on_the_requested_page(self):
        entity = self.asset
        rows, maintenance, verified = [], [], {}
        for index in range(106):
            job_id = ident()
            note = f'note {index}'
            marker = f'[Kiosk note {job_id}]'
            rows.append({'id': job_id, 'actor_id': self.actor, 'action': 'add_note',
                         'status': 'completed', 'created_at': f'2026-10-19T00:{index:02d}:00Z',
                         'assets': [entity], 'confirmed_at': f'2026-10-19T00:{index:02d}:00Z',
                         'source': 'native_job'})
            metadata = {'maintenance_id': ident(), 'entity_id': entity, 'actor_id': self.actor,
                        'author_name': 'Current member name',
                        'content_sha256': hashlib.sha256(note.encode()).hexdigest(), 'marker': marker}
            verified[job_id] = metadata
            maintenance.append({'id': metadata['maintenance_id'],
                                'description': note+'\n\n'+marker})

        class Rows:
            def history(_self, _group, _entity=None, limit=100, offset=0):
                return rows[offset:offset+limit]

        class Jobs(Rows):
            def events(_self, _group, job_id):
                return [{'kind': 'note_verified', 'detail': verified[job_id]}]

        class EmptyLedger:
            def history(_self, _group, _entity=None, limit=100, offset=0):
                return []

        class Client(HistoryClient):
            def __init__(_self):
                super().__init__(self.actor, {'id': entity, 'name': 'Fixture item'})
                _self.maintenance_reads = 0

            def call(_self, path, method='GET', data=None):
                if path.endswith('/maintenance'):
                    _self.maintenance_reads += 1
                    return maintenance
                return super().call(path, method, data)

        client = Client()
        result = history({'client': client, 'group': self.group},
                         {'ledger': EmptyLedger(), 'native_jobs': Jobs()}, entity, 100)
        self.assertEqual(len(result), 6)
        self.assertEqual(client.maintenance_reads, 6)

    def test_legacy_cart_request_receipt_gets_notes_default(self):
        cart = CheckoutCart(self.ledger)
        request_key = ident()
        result = cart.save(self.group, self.actor, [self.asset], 0, request_key)
        self.assertEqual(cart.save(self.group, self.actor, [self.asset], 0, request_key), result)
        self.assertEqual(cart.get(self.group, self.actor)['notes'], {})


if __name__ == '__main__':
    unittest.main()
