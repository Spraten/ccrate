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

    def test_anonymous_return_scan_context_has_no_user_and_is_generation_scoped(self):
        generation = self.session.begin_anonymous_return()
        self.session.record_scan('asset')
        self.assertEqual(self.session.snapshot(), (None, generation))
        self.assertEqual(self.session.scans(generation), {'asset'})
        self.assertEqual(self.session.scans(generation - 1), set())

    def test_badge_start_and_end_clear_anonymous_return_context(self):
        generation = self.session.begin_anonymous_return()
        self.session.record_scan('asset')
        self.session.start('next-user')
        self.assertEqual(self.session.scans(generation), set())
        self.session.begin_anonymous_return()
        self.session.end()
        self.assertEqual(self.session.scans(self.session.snapshot()[1]), set())

    def test_anonymous_return_context_expires_without_becoming_identity(self):
        generation = self.session.begin_anonymous_return()
        self.now = 120
        self.assertEqual(self.session.scans(generation), set())
        self.assertNotEqual(self.session.snapshot()[1], generation)

    def test_late_scan_cannot_fill_replaced_anonymous_context(self):
        self.session.begin_anonymous_return()
        old_context = self.session.scan_context('scan-a')
        new_generation = self.session.begin_anonymous_return()
        self.assertFalse(self.session.record_scan('asset', old_context))
        self.assertEqual(self.session.scans(new_generation), set())

    def test_cancelled_scan_cannot_fill_active_anonymous_context(self):
        generation = self.session.begin_anonymous_return()
        context = self.session.scan_context('scan-a')
        self.session.cancel_scan('scan-a')
        self.assertFalse(self.session.record_scan('asset', context))
        self.assertEqual(self.session.scans(generation), set())

    def test_late_scan_cannot_fill_new_badge_session(self):
        self.session.begin_anonymous_return()
        context = self.session.scan_context('scan-a')
        self.session.start('next-user')
        self.assertFalse(self.session.record_scan('asset', context))
        self.assertEqual(self.session.scans(self.session.snapshot()[1]), set())


if __name__ == '__main__':
    unittest.main()
