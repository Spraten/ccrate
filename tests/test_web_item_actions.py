import copy
import pathlib
import tempfile
import unittest
from uuid import uuid4
from unittest.mock import patch

from ledger import Conflict, Ledger
from checkout_cart import CheckoutCart
from badges import Badges
from web_item_actions import WebItemActions


def ident():
    return str(uuid4())


class FixtureClient:
    def __init__(self, actor, assets):
        self.actor, self.assets = actor, assets
        self.members = [{'id': actor, 'name': 'Fixture member'}]
        self.tenant = None
        self.entity_hook = None

    def call(self, path, method='GET', data=None):
        if path == '/api/v1/groups/members':
            return copy.deepcopy(self.members)
        raise AssertionError(f'unexpected native call: {path}')

    def entity(self, entity_id):
        if self.entity_hook:
            self.entity_hook(entity_id)
        return copy.deepcopy(self.assets[entity_id])


class FixtureBadges:
    def __init__(self, actor):
        self.actor = actor
        self.revoked = False
        self.codes = {'fixture-badge': actor, 'other-person-badge': ident()}

    def resolve(self, group, code, member_ids):
        return self.codes.get(code) if not self.revoked and self.codes.get(code) in member_ids else None


class WebItemActionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(pathlib.Path(self.temp.name) / 'ledger.db')
        self.group, self.actor, self.item = ident(), ident(), ident()
        self.entity = {
            'id': self.item, 'name': 'Fixture drill', 'assetId': '001-001', 'quantity': 1,
            'archived': False, 'barcode': '001-001', 'entityType': {'isLocation': False}, 'fields': [
                {'name': 'Equipment condition', 'type': 'text', 'textValue': 'Ready'},
            ],
        }
        self.client = FixtureClient(self.actor, {self.item: self.entity})
        self.badges = FixtureBadges(self.actor)
        self.now = [100.0]
        self.service = WebItemActions(clock=lambda: self.now[0])
        self.ctx = {'client': self.client, 'group': self.group, 'actor': self.actor,
                    'identity': 'cookie-bound-account-a', 'manager': True}
        self.verify = {'attempt_id': ident(), 'badge_code': 'fixture-badge', 'item_ids': [self.item]}

    def tearDown(self):
        self.temp.cleanup()

    def verified(self):
        return self.service.verify_badge(self.ctx, self.badges, self.verify)

    def test_web_proofs_are_isolated_by_account_collection_and_attempt_selection(self):
        proof = self.verified()
        same = self.service.verify_badge(self.ctx, self.badges, self.verify)
        self.assertEqual(same['verification_id'], proof['verification_id'])
        other = dict(self.ctx, identity='cookie-bound-account-b')
        with self.assertRaises(Conflict):
            self.service.verify_item(other, {'verification_id': proof['verification_id'], 'code': '001-001'})
        other_collection = dict(self.ctx, group=ident())
        with self.assertRaises(Conflict):
            self.service.verify_item(other_collection, {'verification_id': proof['verification_id'], 'code': '001-001'})
        with self.assertRaises(Conflict):
            self.service.verify_badge(self.ctx, self.badges, dict(self.verify, attempt_id=ident(), badge_code='other-person-badge'))
        changed = dict(self.verify, item_ids=[ident()])
        with self.assertRaises(Conflict):
            self.service.verify_badge(self.ctx, self.badges, changed)

    def test_changed_same_owner_selection_invalidates_attempt_but_other_owner_cannot(self):
        proof = self.verified()
        self.service.verify_item(self.ctx, {'verification_id': proof['verification_id'], 'code': '001-001'})
        other_identity = dict(self.ctx, identity='different-account-cookie')
        with self.assertRaises(Conflict):
            self.service.verify_badge(other_identity, self.badges, dict(self.verify, item_ids=[ident()]))
        self.assertEqual(self.service.verify_item(self.ctx, {
            'verification_id': proof['verification_id'], 'code': '001-001',
        })['verified_items'], [self.item])

        with self.assertRaises(Conflict):
            self.service.verify_badge(self.ctx, self.badges, dict(self.verify, item_ids=[ident()]))
        with self.assertRaises(Conflict):
            self.service.checkout(self.ctx, self.ledger, {
                'verification_id': proof['verification_id'], 'assets': [self.item],
                'notes': {}, 'request_key': ident(),
            })

    def test_expiry_revocation_and_matching_account_are_rechecked_at_checkout(self):
        proof = self.verified()
        self.now[0] += 121
        with self.assertRaises(Conflict):
            self.service.verify_item(self.ctx, {'verification_id': proof['verification_id'], 'code': '001-001'})

        proof = self.verified()
        self.service.verify_item(self.ctx, {'verification_id': proof['verification_id'], 'code': '001-001'})
        self.badges.revoked = True
        with self.assertRaises(Conflict):
            self.service.checkout(self.ctx, self.ledger, {
                'verification_id': proof['verification_id'], 'assets': [self.item],
                'notes': {}, 'request_key': ident(),
            })

    def test_checkout_requires_exact_server_scan_evidence_and_no_manager_bypass(self):
        proof = self.verified()
        request = {'verification_id': proof['verification_id'], 'assets': [self.item], 'notes': {}, 'request_key': ident()}
        with patch.object(self.service, 'checkout_operation') as confirm:
            confirm.return_value = {'id': ident(), 'status': 'completed', 'action': 'check_out', 'count': 1}
            with self.assertRaises(Conflict):
                self.service.checkout(self.ctx, self.ledger, request)
            confirm.assert_not_called()
            self.service.verify_item(self.ctx, {'verification_id': proof['verification_id'], 'code': '001-001'})
            result = self.service.checkout(self.ctx, self.ledger, request)
            self.assertEqual(result['status'], 'completed')
            args = confirm.call_args.args
            self.assertEqual(args[4], [self.item])
            self.assertEqual(args[7], {self.item})
            self.assertTrue(args[6]())

    def test_cancel_only_revokes_this_popup_proof(self):
        first = self.verified()
        second_data = dict(self.verify, attempt_id=ident())
        second = self.service.verify_badge(self.ctx, self.badges, second_data)
        self.service.cancel(self.ctx, {'verification_id': first['verification_id']})
        with self.assertRaises(Conflict):
            self.service.verify_item(self.ctx, {'verification_id': first['verification_id'], 'code': '001-001'})
        self.assertEqual(self.service.verify_item(self.ctx, {'verification_id': second['verification_id'], 'code': '001-001'})['verified_items'], [self.item])

    def test_proof_registry_is_bounded_without_evicting_an_active_popup(self):
        proofs = [self.service.verify_badge(self.ctx, self.badges, dict(self.verify, attempt_id=ident())) for _ in range(4)]
        with self.assertRaises(Conflict):
            self.service.verify_badge(self.ctx, self.badges, dict(self.verify, attempt_id=ident()))
        result = self.service.verify_item(self.ctx, {'verification_id': proofs[0]['verification_id'], 'code': '001-001'})
        self.assertEqual(result['verified_items'], [self.item])

    def test_duplicate_native_asset_code_is_ambiguous_within_selected_records(self):
        other = ident()
        duplicate = copy.deepcopy(self.entity)
        duplicate.update(id=other, name='Second drill', barcode='001-001')
        self.client.assets[other] = duplicate
        proof = self.service.verify_badge(self.ctx, self.badges, dict(self.verify, item_ids=[self.item, other]))
        with self.assertRaisesRegex(Conflict, 'more than one selected record'):
            self.service.verify_item(self.ctx, {'verification_id': proof['verification_id'], 'code': '001-001'})

    def test_real_badge_registry_rechecks_revocation_without_persisting_web_proof(self):
        badge_service = Badges(self.ledger)
        issued = badge_service.issue(self.group, self.actor, [self.actor])
        proof = self.service.verify_badge(self.ctx, badge_service, {
            'attempt_id': ident(), 'badge_code': issued['code'], 'item_ids': [self.item],
        })
        self.service.verify_item(self.ctx, {'verification_id': proof['verification_id'], 'code': self.item})
        self.client.members = []
        self.assertTrue(badge_service.revoke(self.group, issued['id']))
        with self.assertRaises(Conflict):
            self.service.checkout(self.ctx, self.ledger, {
                'verification_id': proof['verification_id'], 'assets': [self.item], 'notes': {}, 'request_key': ident(),
            })
        with self.ledger.connection() as db:
            tables = {row['name'] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn('web_item_action_proofs', tables)

    def test_kit_requires_scanning_every_server_resolved_manifest_member(self):
        child = ident()
        child_entity = copy.deepcopy(self.entity)
        child_entity.update(id=child, name='Fixture bit', assetId='001-002', barcode='001-002')
        self.client.assets[child] = child_entity
        self.client.assets[self.item]['fields'].append({
            'name': 'Equipment kit manifest', 'type': 'text',
            'textValue': __import__('json').dumps({'version': 1, 'members': [child]}),
        })
        proof = self.verified()
        self.assertEqual(proof['required_items'], sorted([self.item, child]))
        self.service.verify_item(self.ctx, {'verification_id': proof['verification_id'], 'code': '001-001'})
        request = {'verification_id': proof['verification_id'], 'assets': sorted([self.item, child]), 'notes': {}, 'request_key': ident()}
        with patch.object(self.service, 'checkout_operation') as confirm:
            confirm.return_value = {'id': ident(), 'status': 'completed', 'action': 'check_out', 'count': 2}
            with self.assertRaises(Conflict):
                self.service.checkout(self.ctx, self.ledger, request)
            scanned = self.service.verify_item(self.ctx, {'verification_id': proof['verification_id'], 'code': child})
            self.assertEqual(scanned['verified_items'], sorted([self.item, child]))
            self.service.checkout(self.ctx, self.ledger, request)
            self.assertEqual(confirm.call_args.args[7], {self.item, child})

    def test_removed_kit_manifest_invalidates_proof_before_no_cart_checkout(self):
        child = ident()
        child_entity = copy.deepcopy(self.entity)
        child_entity.update(id=child, name='Fixture bit', assetId='001-002', barcode='001-002')
        manifest_field = {'name': 'Equipment kit manifest', 'type': 'text',
                          'textValue': __import__('json').dumps({'version': 1, 'members': [child]})}
        self.client.assets[child] = child_entity
        self.client.assets[self.item]['fields'].append(copy.deepcopy(manifest_field))
        proof = self.verified()
        self.service.verify_item(self.ctx, {'verification_id': proof['verification_id'], 'code': '001-001'})
        self.service.verify_item(self.ctx, {'verification_id': proof['verification_id'], 'code': '001-002'})
        self.client.assets[self.item]['fields'] = [field for field in self.client.assets[self.item]['fields']
                                                    if field['name'] != 'Equipment kit manifest']
        self.service.checkout_operation = __import__('checkout').confirm_checkout
        request = {'verification_id': proof['verification_id'], 'assets': sorted([self.item, child]),
                   'notes': {}, 'request_key': ident()}
        with self.assertRaises(Conflict):
            self.service.checkout(self.ctx, self.ledger, request)
        self.client.assets[self.item]['fields'].append(manifest_field)
        with self.assertRaises(Conflict):
            self.service.checkout(self.ctx, self.ledger, request)
        self.assertEqual(self.ledger.custody(self.group), [])

    def test_changed_kit_membership_invalidates_proof_before_checkout(self):
        first_child, second_child = ident(), ident()
        for child, name, code in ((first_child, 'First bit', '001-002'), (second_child, 'Second bit', '001-003')):
            entity = copy.deepcopy(self.entity)
            entity.update(id=child, name=name, assetId=code, barcode=code)
            self.client.assets[child] = entity
        kit_field = {'name': 'Equipment kit manifest', 'type': 'text',
                     'textValue': __import__('json').dumps({'version': 1, 'members': [first_child]})}
        self.client.assets[self.item]['fields'].append(kit_field)
        proof = self.verified()
        self.service.verify_item(self.ctx, {'verification_id': proof['verification_id'], 'code': '001-001'})
        self.service.verify_item(self.ctx, {'verification_id': proof['verification_id'], 'code': '001-002'})
        self.client.assets[self.item]['fields'] = [field for field in self.client.assets[self.item]['fields']
                                                    if field['name'] != 'Equipment kit manifest']
        self.client.assets[self.item]['fields'].append({
            'name': 'Equipment kit manifest', 'type': 'text',
            'textValue': __import__('json').dumps({'version': 1, 'members': [second_child]}),
        })
        self.service.checkout_operation = __import__('checkout').confirm_checkout
        with self.assertRaises(Conflict):
            self.service.checkout(self.ctx, self.ledger, {
                'verification_id': proof['verification_id'], 'assets': sorted([self.item, first_child]),
                'notes': {}, 'request_key': ident(),
            })
        self.assertEqual(self.ledger.custody(self.group), [])

    def test_expiry_during_final_manifest_read_fails_checkout(self):
        proof = self.verified()
        self.service.verify_item(self.ctx, {'verification_id': proof['verification_id'], 'code': '001-001'})
        reads = [0]

        def expire_during_final_read(_entity_id):
            reads[0] += 1
            # Verification and checkout preflight each read once; advance time
            # during the last entity read in the checkout validation path.
            if reads[0] == 3:
                self.now[0] += 121

        self.client.entity_hook = expire_during_final_read
        with self.assertRaises(Conflict):
            self.service.checkout(self.ctx, self.ledger, {
                'verification_id': proof['verification_id'], 'assets': [self.item],
                'notes': {}, 'request_key': ident(),
            })
        self.assertEqual(self.ledger.custody(self.group), [])

    def test_asset_selection_mismatch_consumes_proof_so_original_selection_cannot_reuse_scans(self):
        proof = self.verified()
        self.service.verify_item(self.ctx, {'verification_id': proof['verification_id'], 'code': '001-001'})
        with patch.object(self.service, 'checkout_operation') as confirm:
            with self.assertRaises(Conflict):
                self.service.checkout(self.ctx, self.ledger, {
                    'verification_id': proof['verification_id'], 'assets': [ident()], 'notes': {}, 'request_key': ident(),
                })
            confirm.assert_not_called()
            with self.assertRaises(Conflict):
                self.service.checkout(self.ctx, self.ledger, {
                    'verification_id': proof['verification_id'], 'assets': [self.item], 'notes': {}, 'request_key': ident(),
                })

    def test_completed_matching_request_replays_after_proof_expiry_without_new_scan(self):
        key = ident()
        operation = self.ledger.begin(self.group, self.actor, 'check_out', [self.item], key)
        self.ledger.complete(operation['id'])
        self.now[0] += 121
        receipt = self.service.checkout(self.ctx, self.ledger, {
            'verification_id': ident(), 'assets': [self.item], 'notes': {}, 'request_key': key,
        })
        self.assertEqual(receipt, {'id': operation['id'], 'status': 'completed', 'action': 'check_out', 'count': 1})
        with self.assertRaises(Conflict):
            self.service.checkout(self.ctx, self.ledger, {
                'verification_id': ident(), 'assets': [self.item], 'notes': {self.item: 'changed'}, 'request_key': key,
            })

    def test_cart_notes_are_journaled_and_only_consumed_by_a_completed_checkout(self):
        cart_store = CheckoutCart(self.ledger)
        saved = cart_store.save(self.group, self.actor, [self.item], 0, ident(), {self.item: 'Keep the bit with the drill.'})
        proof = self.verified()
        self.service.verify_item(self.ctx, {'verification_id': proof['verification_id'], 'code': '001-001'})
        result = self.service.checkout(self.ctx, self.ledger, {
            'verification_id': proof['verification_id'], 'assets': [self.item], 'request_key': ident(),
            'cart': {'revision': saved['revision'], 'items': [self.item], 'notes': saved['notes']},
        })
        self.assertEqual(result['cart_consumption']['consumed'], [self.item])
        detail = self.ledger.detail(self.group, result['id'])
        self.assertEqual(detail['context']['checkout_notes'], {self.item: 'Keep the bit with the drill.'})
        self.assertEqual(cart_store.get(self.group, self.actor)['notes'], {})


if __name__ == '__main__':
    unittest.main()
