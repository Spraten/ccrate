# Task 3: Scan verified touchscreen checkout

Implemented a checkout surface in the Task 2 touchscreen shell. Lookup results only populate the scan input; checkout items enter the batch only after `/scan` returns an equipment entity, which records the physical scan server side. Kit manifests retain their version map and require every listed component to be present in the server's current verified scan list. The batch checks availability, rejects duplicate root IDs, retains per-item notes, enforces a 50 distinct entity limit, and requires review before confirmation.

Confirmation sends a single request with the stable request key and captured session generation/instance. Network uncertainty preserves the key and exposes a manual `/operation/status` action without retrying confirmation. Completed receipts remain visible until Done.

Added the `/checkout-ui.js` static asset route needed by the shell. No server checkout/cart mutation was introduced. The server already records scans and enforces scan, session, kit-version, and checkout rules.

## Verification

- `python3 -m unittest discover -s tests -p 'test_checkout_cart_ui.py' -v` — passed.
- `python3 -m unittest discover -s tests -p 'test_touchscreen_checkout.py' -v` — passed.
- `git diff --check` — passed.

The tests here are focused source/fixture contracts; no live Homebox or browser/device operation was performed.
