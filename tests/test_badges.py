import tempfile,pathlib,unittest
from uuid import uuid4
from ledger import Ledger
from badges import Badges
class BadgeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=pathlib.Path(self.temp.name)/'ops.db'
        self.group=str(uuid4());self.user=str(uuid4());self.badges=Badges(Ledger(self.path))
    def tearDown(self):self.temp.cleanup()
    def issue(self):return self.badges.issue(self.group,self.user,[self.user])
    def test_issue_resolve_and_revoke(self):
        badge=self.issue();self.assertEqual(self.badges.resolve(self.group,badge['code'],[self.user]),self.user)
        self.assertTrue(self.badges.revoke(self.group,badge['id']))
        self.assertIsNone(self.badges.resolve(self.group,badge['code'],[self.user]))
    def test_removed_member_is_rejected(self):
        badge=self.issue();self.assertIsNone(self.badges.resolve(self.group,badge['code'],[]))
    def test_group_isolation(self):
        badge=self.issue();other=str(uuid4());self.assertIsNone(self.badges.resolve(other,badge['code'],[self.user]))
        self.assertFalse(self.badges.revoke(other,badge['id']))
    def test_no_plaintext_token_in_database(self):
        badge=self.issue()
        with self.badges.ledger.connection() as db:
            row=dict(db.execute('SELECT * FROM badges').fetchone())
        self.assertNotIn(badge['code'][len(Badges.PREFIX):],str(row))
        self.assertNotIn('token_hash',self.badges.list(self.group)[0])
    def test_badge_survives_restart(self):
        badge=self.issue();other=Badges(Ledger(self.path))
        self.assertEqual(other.resolve(self.group,badge['code'],[self.user]),self.user)
    def test_nonmember_cannot_receive_badge(self):
        with self.assertRaises(ValueError):self.badges.issue(self.group,self.user,[])
    def test_malformed_and_unknown_badges_rejected(self):
        for code in [None,'LAB:U:short','LAB:U:'+'x'*43,'LAB:A:example']:
            self.assertIsNone(self.badges.resolve(self.group,code,[self.user]))
    def test_reprint_uses_same_code_after_restart_without_plaintext_storage(self):
        badge=self.issue();restarted=Badges(Ledger(self.path))
        self.assertEqual(restarted.print_code(self.group,badge['id'],[self.user]),badge['code'])
        self.assertEqual((self.path.parent/'badge-print.key').stat().st_mode&0o777,0o600)
        with self.badges.ledger.connection() as db:
            encrypted=db.execute('SELECT encrypted_code FROM badge_print_secrets').fetchone()[0]
        self.assertNotIn(badge['code'].encode(),encrypted)
        self.assertNotIn(badge['code'],str(self.badges.list(self.group)))
        self.assertTrue(self.badges.list(self.group)[0]['reprintable'])
    def test_reprint_rejects_revoked_foreign_and_removed_members(self):
        badge=self.issue()
        for group,members in [(str(uuid4()),[self.user]),(self.group,[])]:
            with self.assertRaises(ValueError):self.badges.print_code(group,badge['id'],members)
        self.badges.revoke(self.group,badge['id'])
        with self.assertRaises(ValueError):self.badges.print_code(self.group,badge['id'],[self.user])
    def test_missing_key_is_not_replaced(self):
        badge=self.issue();key=self.path.parent/'badge-print.key';key.unlink()
        with self.assertRaises(ValueError):self.badges.print_code(self.group,badge['id'],[self.user])
        with self.assertRaises(ValueError):self.issue()
        self.assertFalse(key.exists())
    def test_legacy_badge_is_explicitly_replaced_once(self):
        badge=self.issue()
        with self.badges.ledger.transaction() as db:db.execute('DELETE FROM badge_print_secrets')
        self.assertFalse(self.badges.list(self.group)[0]['reprintable'])
        with self.assertRaises(ValueError):self.badges.print_code(self.group,badge['id'],[self.user])
        replacement=self.badges.replace(self.group,badge['id'],[self.user])
        self.assertIsNone(self.badges.resolve(self.group,badge['code'],[self.user]))
        self.assertEqual(self.badges.resolve(self.group,replacement['code'],[self.user]),self.user)
        self.assertEqual(self.badges.print_code(self.group,replacement['id'],[self.user]),replacement['code'])
        with self.assertRaises(ValueError):self.badges.replace(self.group,badge['id'],[self.user])
    def test_private_key_permissions_are_required(self):
        badge=self.issue();(self.path.parent/'badge-print.key').chmod(0o644)
        with self.assertRaises(ValueError):self.badges.print_code(self.group,badge['id'],[self.user])
if __name__=='__main__':unittest.main()
