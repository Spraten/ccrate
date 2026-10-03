import unittest
from sessions import Session


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.session = Session(clock=lambda: self.now)
        self.session.start('native-user')

    def test_poll_does_not_extend_session(self):
        self.now = 119
        self.assertEqual(self.session.current(), 'native-user')
        self.now = 120
        self.assertIsNone(self.session.current())

    def test_touch_extends_session(self):
        self.now = 100
        self.session.current(activity=True)
        self.now = 219
        self.assertEqual(self.session.current(), 'native-user')
        self.now = 220
        self.assertIsNone(self.session.current())

    def test_activity_cannot_revive_expired_session(self):
        self.now = 120
        self.assertIsNone(self.session.current(activity=True))

    def test_end_and_new_badge(self):
        self.session.end()
        self.assertIsNone(self.session.current(activity=True))
        self.session.start('next-user')
        self.assertEqual(self.session.current(), 'next-user')

    def test_old_completion_cannot_end_a_new_badge_session(self):
        old_user, generation = self.session.snapshot()
        self.session.start('next-user')
        self.session.end(generation)
        self.assertEqual(self.session.current(), 'next-user')
        self.assertNotEqual(self.session.snapshot(), (old_user, generation))

    def test_same_badge_rescan_starts_a_distinct_session(self):
        old = self.session.snapshot()
        self.session.start('native-user')
        self.assertNotEqual(old, self.session.snapshot())

    def test_restart_has_distinct_instance(self):
        self.assertNotEqual(Session().instance, self.session.instance)


if __name__ == '__main__':
    unittest.main()
