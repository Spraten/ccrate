import copy
import hashlib
import io
import json
import pathlib
import tempfile
import threading
import unittest
from email.message import Message
from uuid import uuid4

import desktop_api
from ledger import Ledger
from web_item_actions import WebItemActions


def ident():
    return str(uuid4())


class NativeFixture:
    def __init__(self, actor, group, entities):
        self.actor, self.group, self.entities = actor, group, entities
        self.tenant = None

    def call(self, path, method='GET', data=None):
        if path == '/api/v1/users/self':
            return {'item': {'id': self.actor, 'name': 'Fixture member', 'email': 'member@example.invalid',
                             'defaultGroupId': self.group, 'groupIds': [self.group]}}
        if path == '/api/v1/groups':
            return {'item': {'id': self.group, 'name': 'Fixture collection'}}
        if path == '/api/v1/groups/members':
            return [{'id': self.actor, 'name': 'Fixture member'}]
        raise AssertionError(f'unexpected native call {path}')

    def entity(self, entity_id):
        if self.tenant != self.group or entity_id not in self.entities:
            raise AssertionError('native entity read escaped the authenticated collection')
        return copy.deepcopy(self.entities[entity_id])


class BadgeFixture:
    def __init__(self, actor):
        self.actor = actor
        self.revoked = False

    def resolve(self, group, code, members):
        return self.actor if code == 'fixture-badge' and not self.revoked and self.actor in members else None


class Handler:
    def __init__(self, path, body, token, identity=''):
        self.path = '/workshop-api/' + path
        self.command = 'POST'
        self.headers = Message()
        raw = json.dumps(body).encode()
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


class WebItemActionApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.group, self.actor, self.item = ident(), ident(), ident()
        self.entity = {'id': self.item, 'name': 'Fixture drill', 'assetId': '001-001', 'barcode': '001-001',
                       'quantity': 1, 'archived': False, 'entityType': {'isLocation': False},
                       'fields': [{'name': 'Equipment condition', 'type': 'text', 'textValue': 'Ready'}]}
        self.client = NativeFixture(self.actor, self.group, {self.item: self.entity})
        self.token = 'fixture-token'
        self.ledger = Ledger(self.root / 'ledger.db')
        self.badges = BadgeFixture(self.actor)
        self.service = WebItemActions()
        self.deps = {
            'root': self.root, 'lock': threading.RLock(), 'ledger': self.ledger,
            'badges': self.badges, 'native_jobs': None, 'web_item_actions': self.service,
            'homebox_factory': lambda cookie, base=None: self.client,
            'native_base': 'http://127.0.0.1:17747', 'public_scheme': 'http',
        }
        self.identity = hashlib.sha256(json.dumps([self.actor, self.group, self.token], separators=(',', ':')).encode()).hexdigest()

    def tearDown(self):
        self.temp.cleanup()

    def post(self, route, data, *, identity=None):
        handler = Handler(route, data, self.token, self.identity if identity is None else identity)
        handled = desktop_api.handle(handler, self.deps)
        self.assertTrue(handled)
        return handler

    def test_authenticated_routes_recheck_badge_and_commit_only_the_reviewed_fixture_checkout(self):
        verified = self.post('item-actions/verify-badge', {
            'attempt_id': ident(), 'badge_code': 'fixture-badge', 'item_ids': [self.item],
        })
        self.assertEqual(verified.status, 200, verified.result)
        self.assertEqual(verified.result['borrower']['id'], self.actor)
        verification_id = verified.result['verification_id']

        scanned = self.post('item-actions/verify-item', {'verification_id': verification_id, 'code': '001-001'})
        self.assertEqual(scanned.status, 200)
        self.assertEqual(scanned.result['verified_items'], [self.item])

        receipt = self.post('item-actions/checkout', {
            'verification_id': verification_id, 'assets': [self.item], 'notes': {}, 'request_key': ident(),
        })
        self.assertEqual(receipt.status, 200, receipt.result)
        self.assertEqual(receipt.result['status'], 'completed')
        self.assertEqual(self.ledger.custody(self.group)[0]['actor_id'], self.actor)

    def test_routes_reject_identity_mismatch_and_browser_supplied_actor_fields(self):
        wrong_identity = self.post('item-actions/verify-badge', {
            'attempt_id': ident(), 'badge_code': 'fixture-badge', 'item_ids': [self.item],
        }, identity='wrong-account')
        self.assertEqual(wrong_identity.status, 409)
        forged_actor = self.post('item-actions/verify-badge', {
            'attempt_id': ident(), 'badge_code': 'fixture-badge', 'item_ids': [self.item], 'actor': self.actor,
        })
        self.assertEqual(forged_actor.status, 400)


if __name__ == '__main__':
    unittest.main()
