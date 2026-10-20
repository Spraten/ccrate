"""Authenticated member action adapters against isolated native/ledger fixtures."""
import copy
import hashlib
import io
import json
import pathlib
import tempfile
import threading
import unittest
import urllib.error
from email.message import Message
from uuid import uuid4

import desktop_api
from checkout_cart import CheckoutCart
from ledger import Ledger
from native_jobs import NativeJobs
from web_item_actions import WebItemActions


def ident():
    return str(uuid4())


class NativeFixture:
    def __init__(self, group, actor, entities):
        self.group, self.actor, self.entities = group, actor, entities
        self.members = [{'id': actor, 'name': 'Fixture member'}]
        self.tenant = group
        self.maintenance = {key: [] for key in entities}
        self.writes = []

    def entity(self, entity_id):
        row = self.entities.get(str(entity_id))
        if self.tenant != self.group or row is None or row.get('groupId', self.group) != self.tenant:
            raise urllib.error.HTTPError('fixture', 404, 'missing', {}, None)
        return copy.deepcopy(row)

    def call(self, path, method='GET', data=None):
        if path == '/api/v1/users/self':
            return {'item': {'id': self.actor, 'name': 'Fixture member', 'email': '',
                             'defaultGroupId': self.group, 'groupIds': [self.group]}}
        if path == '/api/v1/groups':
            return {'item': {'id': self.group, 'name': 'Fixture collection'}}
        if path == '/api/v1/groups/members':
            return copy.deepcopy(self.members)
        prefix = '/api/v1/entities/'
        if path.startswith(prefix):
            tail = path[len(prefix):]
            if tail.endswith('/maintenance'):
                entity_id = tail[:-len('/maintenance')]
                self.entity(entity_id)
                rows = self.maintenance.setdefault(entity_id, [])
                if method == 'GET':
                    return copy.deepcopy(rows)
                if method == 'POST':
                    self.writes.append((method, path, copy.deepcopy(data)))
                    row = {'id': ident(), **copy.deepcopy(data)}
                    rows.append(row)
                    return copy.deepcopy(row)
            if method == 'PUT':
                current = self.entity(tail)
                self.writes.append((method, path, copy.deepcopy(data)))
                current.update(copy.deepcopy(data))
                current['parent'] = {'id': data['parentId']} if data.get('parentId') else None
                self.entities[tail] = current
                return copy.deepcopy(current)
        raise AssertionError(f'unexpected native call {method} {path}')


class Handler:
    def __init__(self, path, token, *, method='POST', body=None, query='', identity=''):
        self.path = '/workshop-api/' + path + (('?' + query) if query else '')
        self.command = method
        self.headers = Message()
        raw = json.dumps(body or {}).encode() if method == 'POST' else b''
        for key, value in {
            'Host': 'pi.fixture:17747', 'Origin': 'http://pi.fixture:17747',
            'Cookie': f'hb.auth.token={token}; hb.auth.remember=true',
            'X-Workshop-Identity': identity, 'Content-Type': 'application/json',
            'Content-Length': str(len(raw)),
        }.items():
            self.headers[key] = value
        self.rfile = io.BytesIO(raw)
        self.status = None
        self.result = None

    def reply_json(self, status, result):
        self.status, self.result = status, result


class MemberActionApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.group, self.actor = ident(), ident()
        self.item, self.second, self.destination = ident(), ident(), ident()
        def entity(entity_id, name, parent=None, group=None):
            return {'id': entity_id, 'groupId': group or self.group, 'name': name,
                    'quantity': 1, 'archived': False, 'parent': {'id': parent} if parent else None,
                    'entityType': {'id': ident(), 'isLocation': entity_id == self.destination},
                    'fields': [{'name': 'Equipment condition', 'type': 'text', 'textValue': 'Ready'}],
                    'tags': [], 'attachments': []}
        self.entities = {self.item: entity(self.item, 'Drill', self.destination),
                         self.second: entity(self.second, 'Saw'),
                         self.destination: entity(self.destination, 'Storage')}
        self.client = NativeFixture(self.group, self.actor, self.entities)
        self.token = 'fixture-token'
        self.ledger = Ledger(self.root / 'ledger.db')
        self.jobs = NativeJobs(self.ledger)
        self.cart = CheckoutCart(self.ledger)
        self.service = WebItemActions()
        self.lock = threading.RLock()
        self.deps = {'root': self.root, 'lock': self.lock, 'ledger': self.ledger,
                     'checkout_cart': self.cart, 'native_jobs': self.jobs,
                     'badges': object(), 'web_item_actions': self.service,
                     'homebox_factory': lambda cookie, base=None: self.client,
                     'native_base': 'http://127.0.0.1:17747', 'public_scheme': 'http'}
        self.identity = self._identity(self.actor)

    def tearDown(self):
        self.temp.cleanup()

    def _identity(self, actor):
        return hashlib.sha256(json.dumps([actor, self.group, self.token], separators=(',', ':')).encode()).hexdigest()

    def call(self, route, data=None, *, method='POST', query='', actor=None):
        actor = actor or self.actor
        if actor != self.client.actor:
            self.client.actor = actor
        handler = Handler(route, self.token, method=method, body=data, query=query, identity=self._identity(actor))
        self.assertTrue(desktop_api.handle(handler, self.deps))
        return handler

    def loan(self, entity_id, actor=None):
        operation = self.ledger.begin(self.group, actor or self.actor, 'check_out', [entity_id], ident())
        self.ledger.complete(operation['id'])
        return operation

    def manager(self, actor):
        path = self.root / 'work/ops/desktop-managers.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'managers': [{'user_id': actor, 'group_id': self.group}]}))
        if actor not in {row['id'] for row in self.client.members}:
            self.client.members.append({'id': actor, 'name': 'Fixture manager'})

    def test_member_note_uses_authenticated_author_and_rejects_browser_author(self):
        response = self.call('item-actions/note', {'entity_id': self.item, 'note': 'Check the latch.', 'request_key': ident()})
        self.assertEqual(response.status, 200, response.result)
        job = self.jobs.detail(self.group, response.result['id'])
        self.assertEqual(job['actor_id'], self.actor)
        verified = next(event['detail'] for event in self.jobs.events(self.group, response.result['id'])
                        if event['kind'] == 'note_verified')
        self.assertEqual(verified['author_name'], 'Fixture member')
        forged = self.call('item-actions/note', {'entity_id': self.item, 'note': 'Forged',
                                                 'request_key': ident(), 'author_name': 'Manager'})
        self.assertEqual(forged.status, 400)

    def test_member_checkin_only_allows_owned_loans_and_preserves_cart_notes(self):
        self.loan(self.item)
        self.loan(self.second, ident())
        before = len(self.ledger.unresolved())
        mixed = self.call('item-actions/checkin', {
            'targets': [{'entity_id': self.item}, {'entity_id': self.second}],
            'verified': [], 'kit_versions': {}, 'request_key': ident(),
        })
        self.assertEqual(mixed.status, 409, mixed.result)
        self.assertEqual(len(self.ledger.custody(self.group)), 2)
        self.assertEqual(len(self.ledger.unresolved()), before)
        own = self.call('item-actions/checkin', {
            'targets': [{'entity_id': self.item, 'return_note': 'Returned clean.'}],
            'verified': [], 'kit_versions': {}, 'request_key': ident(),
        })
        self.assertEqual(own.status, 200, own.result)
        self.assertEqual([row['entity_id'] for row in self.ledger.custody(self.group)], [self.second])
        self.assertEqual(self.ledger.history(self.group, self.item)[0]['return_notes'][0]['text'], 'Returned clean.')
        replay = self.call('item-actions/checkin', {
            'targets': [{'entity_id': self.item, 'return_note': 'Returned clean.'}],
            'verified': [], 'kit_versions': {}, 'request_key': self.ledger.detail(self.group, own.result['id'])['request_key'],
        })
        self.assertEqual(replay.status, 200, replay.result)
        self.assertEqual(replay.result['id'], own.result['id'])
        forbidden = self.call('item-actions/checkin', {
            'targets': [{'entity_id': self.second}], 'verified': [], 'kit_versions': {}, 'request_key': ident(),
        })
        self.assertEqual(forbidden.status, 409)
        manager = ident()
        self.manager(manager)
        allowed = self.call('item-actions/checkin', {
            'targets': [{'entity_id': self.second}], 'verified': [], 'kit_versions': {}, 'request_key': ident(),
        }, actor=manager)
        self.assertEqual(allowed.status, 200, allowed.result)
        self.assertEqual(self.ledger.custody(self.group), [])

    def test_checkin_validates_destination_and_problem_report_sets_block_with_separate_note(self):
        self.loan(self.item)
        foreign = ident()
        self.entities[foreign] = {'id': foreign, 'groupId': ident(), 'name': 'Foreign storage',
                                  'entityType': {'id': ident(), 'isLocation': True}, 'quantity': 1,
                                  'archived': False, 'fields': []}
        invalid = self.call('item-actions/checkin', {
            'targets': [{'entity_id': self.item, 'destination_id': foreign}],
            'verified': [], 'kit_versions': {}, 'request_key': ident(),
        })
        self.assertIn(invalid.status, (400, 404, 409))
        self.assertEqual(len(self.ledger.custody(self.group)), 1)
        self.assertEqual(self.client.writes, [])
        forged_condition = self.call('item-actions/checkin', {
            'targets': [{'entity_id': self.item, 'condition': 'Ready'}],
            'verified': [], 'kit_versions': {}, 'request_key': ident(),
        })
        self.assertEqual(forged_condition.status, 400)
        missing_description = self.call('item-actions/checkin', {
            'targets': [{'entity_id': self.item, 'problem_description': '  '}],
            'verified': [], 'kit_versions': {}, 'request_key': ident(),
        })
        self.assertEqual(missing_description.status, 400)
        report = self.call('item-actions/checkin', {
            'targets': [{'entity_id': self.item, 'problem_description': 'Loose trigger',
                         'return_note': 'Placed on the left shelf.'}],
            'verified': [], 'kit_versions': {}, 'request_key': ident(),
        })
        self.assertEqual(report.status, 200, report.result)
        fields = {field['name']: field['textValue'] for field in self.client.entity(self.item)['fields']}
        self.assertEqual(fields['Equipment condition'], 'Needs Attention')
        self.assertEqual(fields['Equipment condition note'], 'Loose trigger')
        history = self.ledger.history(self.group, self.item)[0]
        self.assertEqual(history['return_notes'][0]['text'], 'Placed on the left shelf.')

    def test_status_is_authoritative_and_reports_unknown_without_guessing(self):
        self.loan(self.item)
        self.client.entities[self.item]['fields'][0]['textValue'] = 'Broken'
        result = self.call('item-actions/status', method='GET', query='ids='+self.item+','+self.second+','+ident())
        self.assertEqual(result.status, 200, result.result)
        items = {item['id']: item for item in result.result['items']}
        self.assertEqual(items[self.item]['availability'], 'checked_out')
        self.assertEqual(items[self.item]['blocker'], 'Condition: Broken')
        self.assertTrue(items[self.item]['can_checkin'])
        self.assertEqual(items[self.second]['availability'], 'available')
        self.assertEqual(items[self.second]['can_add_note'], True)
        unknown = next(item for item in result.result['items'] if item['id'] not in self.entities)
        self.assertEqual(unknown['availability'], 'unknown')
        self.assertFalse(unknown['can_checkin'])

        no_condition = ident()
        self.entities[no_condition] = {'id': no_condition, 'groupId': self.group, 'name': 'Unreviewed item',
                                       'quantity': 1, 'archived': False, 'entityType': {'id': ident(), 'isLocation': False},
                                       'fields': [], 'tags': []}
        missing = self.call('item-actions/status', method='GET', query='ids='+no_condition)
        self.assertEqual(missing.result['items'][0]['availability'], 'unknown')

    def test_status_rejects_duplicate_and_oversized_id_lists(self):
        duplicate = self.call('item-actions/status', method='GET', query='ids='+self.item+','+self.item)
        self.assertEqual(duplicate.status, 400)
        oversized = self.call('item-actions/status', method='GET', query='ids='+','.join(ident() for _ in range(51)))
        self.assertEqual(oversized.status, 400)

    def test_unfinished_return_stays_checked_out_and_cannot_start_a_second_checkin(self):
        checkout = self.loan(self.item)
        pending = self.ledger.begin(self.group, self.actor, 'return', [self.item], ident())
        self.ledger.review(pending['id'], 'fixture interrupted return')
        result = self.call('item-actions/status', method='GET', query='ids='+self.item)
        item = result.result['items'][0]
        self.assertEqual(item['availability'], 'checked_out')
        self.assertFalse(item['can_checkin'])
        self.assertIn('recovery', item['blocker'].lower())
        self.assertEqual(self.ledger.custody(self.group)[0]['operation_id'], checkout['id'])

    def test_problem_resolution_route_remains_manager_only(self):
        self.loan(self.item)
        report = self.call('item-actions/checkin', {
            'targets': [{'entity_id': self.item, 'problem_description': 'Loose clamp'}],
            'verified': [], 'kit_versions': {}, 'request_key': ident(),
        })
        self.assertEqual(report.status, 200, report.result)
        blocked = self.call('item-actions/status', method='GET', query='ids='+self.item)
        self.assertEqual(blocked.result['items'][0]['availability'], 'blocked')
        self.assertEqual(blocked.result['items'][0]['blocker'], 'Condition: Needs Attention')
        member = self.call('condition', {'entity_id': self.item, 'state': 'Ready', 'request_key': ident()})
        self.assertEqual(member.status, 403)
        manager = ident()
        self.manager(manager)
        resolved = self.call('condition', {'entity_id': self.item, 'state': 'Ready', 'request_key': ident()}, actor=manager)
        self.assertEqual(resolved.status, 200, resolved.result)
        status = self.call('item-actions/status', method='GET', query='ids='+self.item)
        self.assertEqual(status.result['items'][0]['availability'], 'available')

    def test_cart_operation_status_is_actor_scoped_and_returns_saved_receipt(self):
        key = ident()
        saved = self.cart.save(self.group, self.actor, [self.item], 0, key)
        own = self.call('operation/status', {'request_key': key})
        self.assertEqual(own.status, 200, own.result)
        self.assertEqual(own.result['status'], 'completed')
        self.assertEqual(own.result['result'], saved)
        other = ident()
        self.client.members.append({'id': other, 'name': 'Other member'})
        self.client.actor = other
        hidden = self.call('operation/status', {'request_key': key}, actor=other)
        self.assertEqual(hidden.result['status'], 'not_started')

    def test_operation_status_hides_other_members_return_and_note_receipts(self):
        self.loan(self.item)
        return_key = ident()
        returned = self.call('item-actions/checkin', {
            'targets': [{'entity_id': self.item}], 'verified': [], 'kit_versions': {},
            'request_key': return_key,
        })
        self.assertEqual(returned.status, 200, returned.result)
        note_key = ident()
        note = self.call('item-actions/note', {
            'entity_id': self.second, 'note': 'Private receipt', 'request_key': note_key,
        })
        self.assertEqual(note.status, 200, note.result)

        other = ident()
        self.client.members.append({'id': other, 'name': 'Other member'})
        for key in (return_key, note_key):
            hidden = self.call('operation/status', {'request_key': key}, actor=other)
            self.assertEqual(hidden.result['status'], 'not_started')

        manager = ident()
        self.manager(manager)
        self.assertEqual(self.call('operation/status', {'request_key': return_key}, actor=manager).result['status'], 'completed')
        self.assertEqual(self.call('operation/status', {'request_key': note_key}, actor=manager).result['status'], 'completed')

    def test_removed_kit_manifest_blocks_checkin_even_with_prior_verified_versions(self):
        child = ident()
        child_entity = copy.deepcopy(self.entities[self.second])
        child_entity['id'], child_entity['name'] = child, 'Kit child'
        self.entities[child] = child_entity
        self.client.maintenance[child] = []
        manifest_field = {'name': 'Equipment kit manifest', 'type': 'text',
                          'textValue': json.dumps({'version': 1, 'members': [child]})}
        self.client.entities = self.entities
        self.entities[self.item]['fields'].append(manifest_field)
        from kits import manifest
        versions = manifest(self.client, self.item)['versions']
        self.loan(self.item)
        self.loan(child)
        self.entities[self.item]['fields'] = [field for field in self.entities[self.item]['fields']
                                               if field['name'] != 'Equipment kit manifest']

        response = self.call('item-actions/checkin', {
            'targets': [{'entity_id': self.item}, {'entity_id': child}],
            'verified': [self.item, child], 'kit_versions': versions,
            'request_key': ident(),
        })
        self.assertEqual(response.status, 409, response.result)
        self.assertEqual({row['entity_id'] for row in self.ledger.custody(self.group)}, {self.item, child})


if __name__ == '__main__':
    unittest.main()
