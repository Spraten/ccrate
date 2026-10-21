# Task 3: Scan verified touchscreen checkout

Implemented a checkout surface in the Task 2 touchscreen shell. Lookup results only populate the scan input; checkout items enter the batch only after `/scan` returns an equipment entity, which records the physical scan server side. Kit manifests retain their version map and require every listed component to be present in the server's current verified scan list. The batch checks availability, rejects duplicate root IDs, retains per-item notes, enforces a 50 distinct entity limit, and requires review before confirmation.

Confirmation sends a single request with the stable request key and captured session generation/instance. Network uncertainty preserves the key and exposes a manual `/operation/status` action without retrying confirmation. Completed receipts remain visible until Done.

Added the `/checkout-ui.js` static asset route needed by the shell and a badge-scoped `POST /checkout/cart` companion route for saved checkout-list updates. The route uses the existing `CheckoutCart.save` storage service and enforces active badge, generation/instance, collection membership, revision, and idempotency checks. The server already records scans and enforces scan, session, kit-version, and checkout rules.

## Verification

- `python3 -m unittest discover -s tests -p 'test_checkout_cart_ui.py' -v` — passed.
- `python3 -m unittest discover -s tests -p 'test_touchscreen_checkout.py' -v` — passed.
- `git diff --check` — passed.

The tests here are focused source/fixture contracts; no live Homebox or browser/device operation was performed.

## Review fixes

- Search now reads the companion `/api/inventory` route and filters candidate records locally. Selecting a result leaves the physical scan input empty; the subsequently scanned entity must match the selected candidate before being added.
- The touchscreen flow loads the member's saved checkout cart, exposes save-list behavior through the existing `/checkout/cart` POST API, and supplies the saved revision/item context when the batch consists of saved roots. Saved item notes are restored when rescanned.
- Updated regression assertions for supported inventory search, no candidate-to-scan prefill, scan/candidate match, and saved-cart context.

Focused checkout tests and `git diff --check` pass after these fixes.

## Badge-bound saved-cart endpoint

Added `POST /checkout/cart` to the companion route allowlist. It requires an active badge session, exact generation and instance from the request, current collection membership, and a still-current session after acquiring the shared lock. The route delegates item, note, revision, and request-key validation/idempotency to the existing `CheckoutCart.save` service. It uses the existing companion and storage service, with no added dependency or manager route change. The touchscreen Save action now submits generation and instance.

Exact route evidence: `python3 -m unittest tests.test_terminal_members.TerminalMemberTests.test_badge_bound_checkout_cart_save_requires_session_and_is_idempotent -v` passed. This fixture verifies a valid saved cart, same-key idempotent replay, stale revision conflict, stale session conflict, and unauthenticated denial. UI request contract: `python3 -m unittest discover -s tests -p 'test_checkout_cart_ui.py' -v` passed. Checkout flow: `python3 -m unittest discover -s tests -p 'test_touchscreen_checkout.py' -v` passed. `git diff --check` passed.

## Recovery and completion review

The existing uncertain-outcome recovery action remains available after an ambiguous confirmation. Added a Node DOM fixture that drives the real UI: it verifies one confirm attempt, a rendered Check saved result button, one status request with no second confirm, and a completed receipt. The receipt's Done action now signals the shell's existing Done handler, which ends the captured generation/instance and returns the shell home; a shell fixture verifies the request payload and resulting visibility state. Inventory search now indicates when no records match and tells users to refine when results exceed the 12 shown.

Verification: checkout cart UI suite passed; touchscreen checkout suite passed (including the recovery and Done behavioral tests); badge-bound cart route fixture passed; `git diff --check` passed.
