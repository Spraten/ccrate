import pathlib
import tempfile
import unittest
from uuid import uuid4

from checkout_cart import CheckoutCart
from ledger import Conflict, Ledger


def ident():
    return str(uuid4())


class CheckoutCartTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).resolve().parent)
        self.path = pathlib.Path(self.temp.name) / 'ledger.db'
        self.ledger = Ledger(self.path)
        self.cart = CheckoutCart(self.ledger)
        self.group, self.other_group, self.actor, self.other_actor = [ident() for _ in range(4)]
        self.asset, self.other_asset = ident(), ident()

    def tearDown(self):
        self.temp.cleanup()

    def save(self, items, revision=0, key=None, group=None, actor=None):
        return self.cart.save(group or self.group, actor or self.actor, items, revision, key or ident())

    def test_draft_persists_without_reserving_or_changing_custody(self):
        saved = self.save([self.asset])

        reopened = CheckoutCart(Ledger(self.path))
        self.assertEqual(reopened.get(self.group, self.actor), saved)
        self.assertEqual(self.ledger.unresolved(), [])
        self.assertEqual(self.ledger.custody(self.group), [])

    def test_update_replay_returns_original_result_and_changed_replay_conflicts(self):
        key = ident()
        first = self.save([self.asset], key=key)
        self.save([self.other_asset], revision=first['revision'])

        self.assertEqual(self.save([self.asset], key=key), first)
        with self.assertRaises(Conflict):
            self.save([self.other_asset], key=key)

    def test_stale_revision_conflicts_without_replacing_current_cart(self):
        current = self.save([self.asset])

        with self.assertRaises(Conflict):
            self.save([self.other_asset], revision=0)

        self.assertEqual(self.cart.get(self.group, self.actor), current)

    def test_member_can_clear_the_cart_with_an_empty_revisioned_update(self):
        saved = self.save([self.asset])

        cleared = self.save([], revision=saved['revision'])

        self.assertEqual(cleared, {'revision': 2, 'items': []})

    def test_actor_and_group_scopes_are_independent(self):
        self.save([self.asset])
        self.save([self.other_asset], group=self.other_group)
        self.save([self.other_asset], actor=self.other_actor)

        self.assertEqual(self.cart.get(self.group, self.actor)['items'], [self.asset])
        self.assertEqual(self.cart.get(self.other_group, self.actor)['items'], [self.other_asset])
        self.assertEqual(self.cart.get(self.group, self.other_actor)['items'], [self.other_asset])

    def test_only_a_completed_receipt_for_same_actor_and_group_consumes_selected_cart_items(self):
        saved = self.save([self.asset, self.other_asset])
        operation = self.ledger.begin(self.group, self.actor, 'check_out', [self.asset], ident(),
                                      context={'checkout_cart': {'revision': saved['revision'], 'items': saved['items']}})
        with self.assertRaises(Conflict):
            self.cart.consume_completed_receipt(self.group, self.actor, operation['id'])
        self.ledger.complete(operation['id'])

        result = self.cart.consume_completed_receipt(self.group, self.actor, operation['id'])

        self.assertEqual(result['consumed'], [self.asset])
        self.assertEqual(result['cart']['items'], [self.other_asset])
        self.assertEqual(result, self.cart.consume_completed_receipt(self.group, self.actor, operation['id']))

    def test_receipt_cannot_consume_another_actors_or_groups_cart(self):
        saved = self.save([self.asset])
        operation = self.ledger.begin(self.group, self.actor, 'check_out', [self.asset], ident(),
                                      context={'checkout_cart': {'revision': saved['revision'], 'items': saved['items']}})
        self.ledger.complete(operation['id'])

        with self.assertRaises(Conflict):
            self.cart.consume_completed_receipt(self.other_group, self.actor, operation['id'])
        with self.assertRaises(Conflict):
            self.cart.consume_completed_receipt(self.group, self.other_actor, operation['id'])
        self.assertEqual(self.cart.get(self.group, self.actor)['items'], [self.asset])


if __name__ == '__main__':
    unittest.main()
