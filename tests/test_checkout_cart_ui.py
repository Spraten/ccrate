import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]

class CheckoutCartUiTests(unittest.TestCase):
    def test_touchscreen_loads_scan_verified_checkout_flow(self):
        html=(ROOT/'kiosk/touchscreen.html').read_text()
        flow=(ROOT/'kiosk/checkout-ui.js').read_text()
        self.assertIn('id="checkout-ui"',html)
        self.assertIn('src="/checkout-ui.js"',html)
        for name in ('beginCheckout','addCheckoutItem','reviewCheckout','confirmCheckout','recoverCheckout'):
            self.assertIn('function '+name,flow)
        self.assertIn("'/scan'",flow)
        self.assertIn("'/checkout/availability?ids='",flow)
        self.assertIn("'/checkout/confirm'",flow)
        self.assertIn("'/operation/status'",flow)

if __name__=='__main__': unittest.main()
