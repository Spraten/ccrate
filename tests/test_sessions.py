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


if __name__ == '__main__':
    unittest.main()
