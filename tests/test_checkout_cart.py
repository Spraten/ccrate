import pathlib
import json
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

        self.assertEqual(cleared, {'revision': 2, 'items': [], 'notes': {}})

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

    def test_kiosk_edit_receipt_does_not_overwrite_a_newer_desk_cart_revision(self):
        saved = self.save([self.asset, self.other_asset])
        operation = self.ledger.begin(self.group, self.actor, 'check_out', [self.asset], ident(),
                                      context={'checkout_cart': {'revision': saved['revision'],
                                                                 'items': [self.asset],
                                                                 'original_items': saved['items']}})
        self.ledger.complete(operation['id'])
        newer = self.save([self.other_asset], revision=saved['revision'])

        result = self.cart.consume_completed_receipt(self.group, self.actor, operation['id'])

        self.assertTrue(result['cart_changed'])
        self.assertEqual(result['cart'], newer)

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

    def test_cart_notes_legacy_rows_and_payloads(self):
        with self.ledger.transaction() as db:
            db.execute('DROP TABLE checkout_carts')
            db.execute('''CREATE TABLE checkout_carts(group_id TEXT NOT NULL,actor_id TEXT NOT NULL,
              revision INTEGER NOT NULL,items TEXT NOT NULL,updated_at TEXT NOT NULL,
              PRIMARY KEY(group_id,actor_id))''')
            db.execute('INSERT INTO checkout_carts VALUES(?,?,?,?,?)',
                       (self.group, self.actor, 2, json.dumps([self.asset]), 'old'))
        migrated = CheckoutCart(self.ledger)
        self.assertEqual(migrated.get(self.group, self.actor),
                         {'revision': 2, 'items': [self.asset], 'notes': {}})
        first = migrated.save(self.group, self.actor, [self.asset, self.other_asset], 2, ident(),
                              {self.asset: 'measure first'})
        legacy_update = migrated.save(self.group, self.actor, [self.asset], first['revision'], ident())
        self.assertEqual(legacy_update['notes'], {self.asset: 'measure first'})
        self.assertNotIn(self.other_asset, legacy_update['notes'])

    def test_cart_notes_revision_and_replay(self):
        key = ident()
        first = self.cart.save(self.group, self.actor, [self.asset], 0, key,
                               {self.asset: 'measure before use'})
        self.assertEqual(self.cart.save(self.group, self.actor, [self.asset], 0, key,
                                        {self.asset: 'measure before use'}), first)
        with self.assertRaises(Conflict):
            self.cart.save(self.group, self.actor, [self.asset], 0, key,
                           {self.asset: 'different note'})
        with self.assertRaises(Conflict):
            self.cart.save(self.group, self.actor, [self.other_asset], 0, ident())
        self.assertEqual(self.cart.get(self.group, self.actor), first)

    def test_cart_note_limits_and_invalid_values_fail_without_saving(self):
        for note, expected in [('x' * 1001, ValueError), ('\ud800', ValueError)]:
            with self.assertRaises(expected):
                self.cart.save(self.group, self.actor, [self.asset], 0, ident(), {self.asset: note})
            self.assertEqual(self.cart.get(self.group, self.actor), {'revision': 0, 'items': [], 'notes': {}})
        with self.assertRaises(ValueError):
            self.cart.save(self.group, self.actor, [self.asset], 0, ident(), {self.other_asset: 'extra'})
        accepted = self.cart.save(self.group, self.actor, [self.asset], 0, ident(), {self.asset: 'x' * 1000})
        self.assertEqual(len(accepted['notes'][self.asset]), 1000)

    def test_cart_consumption_preserves_other_notes(self):
        saved = self.cart.save(self.group, self.actor, [self.asset, self.other_asset], 0, ident(),
                               {self.asset: 'for this checkout', self.other_asset: 'keep for later'})
        operation = self.ledger.begin(self.group, self.actor, 'check_out', [self.asset], ident(),
                                      context={'checkout_cart': {'revision': saved['revision'],
                                                                 'items': [self.asset, self.other_asset],
                                                                 'original_items': [self.asset, self.other_asset],
                                                                 'notes': saved['notes']}})
        self.ledger.complete(operation['id'])
        result = self.cart.consume_completed_receipt(self.group, self.actor, operation['id'])
        self.assertEqual(result['cart']['items'], [self.other_asset])
        self.assertEqual(result['cart']['notes'], {self.other_asset: 'keep for later'})


if __name__ == '__main__':
    unittest.main()
