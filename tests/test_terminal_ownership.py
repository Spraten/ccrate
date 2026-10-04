import unittest
from sessions import Sessions, Session


class TerminalOwnershipTests(unittest.TestCase):
    def test_two_clients_have_independent_identity_scan_and_end(self):
        sessions=Sessions();pi=sessions.get('pi');laptop=sessions.get('laptop')
        generation=pi.start('alice');pi.record_scan('tool')
        laptop.start('bob');laptop.end()
        self.assertEqual(pi.snapshot(),('alice',generation))
        self.assertEqual(pi.scans(generation),{'tool'})
        self.assertNotEqual(pi.instance,laptop.instance)
        self.assertIsNone(laptop.current())

    def test_cancel_before_badge_response_prevents_start(self):
        session=Session();session.cancel_scan('pending-token')
        self.assertIsNone(session.start('alice','pending-token'))
        self.assertIsNone(session.current())

    def test_cancel_after_response_ends_only_matching_scan(self):
        session=Session();session.start('alice','first');session.start('bob','second')
        session.cancel_scan('first');self.assertEqual(session.current(),'bob')
        session.cancel_scan('second');self.assertIsNone(session.current())

    def test_revocation_ends_only_affected_users_across_clients(self):
        sessions=Sessions();a=sessions.get('a');b=sessions.get('b');c=sessions.get('c')
        a.start('alice');b.start('alice');c.start('bob');sessions.revoke_user('alice')
        self.assertIsNone(a.current());self.assertIsNone(b.current())
        self.assertEqual(c.current(),'bob')

    def test_abandoned_client_cleanup_does_not_evict_active_terminal(self):
        sessions=Sessions();active=sessions.get('active');active.start('alice')
        for i in range(300):sessions.get(str(i))
        self.assertIs(sessions.get('active'),active)
        self.assertEqual(active.current(),'alice')

if __name__=='__main__':unittest.main()
