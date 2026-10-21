import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]

class TouchscreenCheckoutTests(unittest.TestCase):
    def test_checkout_requires_scan_and_review_and_has_manual_recovery(self):
        source=(ROOT/'kiosk/checkout-ui.js').read_text()
        self.assertIn("request('/scan'",source)
        self.assertIn('Physical scan verified',source)
        self.assertIn('This item is already in the batch',source)
        self.assertIn('at most 50 distinct items',source)
        self.assertIn("request('/checkout/availability?ids='",source)
        self.assertIn('Optional note for this item',source)
        self.assertIn('Confirm checkout',source)
        self.assertIn("request('/operation/status'",source)
        self.assertIn("state.uncertain=true",source)
        self.assertIn('session_generation:saved.generation',source)
        self.assertIn('session_instance:saved.instance',source)

    def test_page_serves_the_flow_script(self):
        server=(ROOT/'deploy/kiosk-server.py').read_text()
        self.assertIn("'/checkout-ui.js': 'checkout-ui.js'",server)

if __name__=='__main__': unittest.main()
