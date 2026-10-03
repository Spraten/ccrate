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
if __name__=='__main__':unittest.main()
