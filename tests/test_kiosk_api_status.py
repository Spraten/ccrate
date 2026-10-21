import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class KioskApiStatusTests(unittest.TestCase):
    def test_scoped_return_availability_does_not_expose_custody_rows(self):
        source=(ROOT/'deploy/kiosk-server.py').read_text()
        route=source[source.index("if urlsplit(self.path).path == '/return/availability':"):source.index("terminal_path=urlsplit(self.path)")]
        for token in ('self.session.snapshot()', 'ledger.custody(group)', 'checkout_blocker(item)', 'returns.parent_id(item)', 'condition(item)', '1<=len(ids)<=50', "'items':rows"):
            self.assertIn(token,route)
        for token in ('ledger.unresolved()', "if not actor", 'len(ids)!=len(set(ids))', 'client.entity(item_id)', 'self.session.snapshot()!=(actor,generation)', "'Item is not currently checked out'", "'An operation needs staff review'"):
            self.assertIn(token,route)
        self.assertNotIn("'borrower'",route);self.assertNotIn('reply_json(200,ledger.custody',route)
        self.assertNotIn("'actor':",route)

    def test_return_availability_is_bound_and_selected_only(self):
        source=(ROOT/'deploy/kiosk-server.py').read_text()
        route=source[source.index("if urlsplit(self.path).path == '/return/availability':"):source.index('terminal_path=urlsplit(self.path)')]
        self.assertIn("if not actor",route);self.assertIn('parse_qs',route);self.assertIn('len(ids)!=len(set(ids))',route)
        self.assertIn("{'id':item_id,'eligible':reason is None,'reason':reason,'condition':condition(item),'location':location}",route)


if __name__ == '__main__':
    unittest.main()
