# C-Crate touchscreen UI review

Captured 2026-10-22 from the current kiosk UI in an isolated fixture. The fixture used synthetic session/member/item data. Transaction-confirmation endpoints were blocked; these captures do not prove a checkout or return was committed.

| State | Capture | Evidence |
|---|---|---|
| Home, Night theme | [01-home-night.png](01-home-night.png) | Large, touch-sized checkout and return entry points in the shared Homebox theme. |
| Checkout badge gate | [02-checkout-badge.png](02-checkout-badge.png) | Member scan starts the checkout flow. |
| Checkout item scan | [03-checkout-scan.png](03-checkout-scan.png) | Current session and item scan action are visible. |
| Checkout review | [04-checkout-review.png](04-checkout-review.png) | Item preview has a neutral no-photo fallback; review offers confirm and cancel/back actions. |
| Return item scan | [05-return-scan.png](05-return-scan.png) | Return scan state; Enter key on the Netum scanner now submits the scan for verification. |
| Return review | [05-return-review.png](05-return-review.png) | Item preview, return condition/note context, and review actions. |

The Enter behavior was verified synthetically by entering a fixture barcode and observing the “Physical scan verified” review state. This did not use physical hardware and did not invoke checkout or return confirmation. A receipt/success state and an uncertain-result recovery state were not captured in this pass; their existing transaction/recovery behavior remains subject to an operational review before release.
