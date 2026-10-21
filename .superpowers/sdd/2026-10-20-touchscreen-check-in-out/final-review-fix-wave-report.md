# Final review fix wave report — 2026-10-21

## Findings addressed

- Added kiosk-only server enforcement that every selected asset has physical scan proof, including expanded kit components; desktop callers keep the default behavior.
- Allowed transaction notes for all selected expanded assets while retaining root-only saved-cart note validation.
- Distinguished definite HTTP 400/409 validation rejections from transport/ambiguous outcomes. Definite rejection and `not_started` recovery clear the old request key, invalidate review, show guidance, and permit a new key only after re-review.
- Preserved completed checkout and return receipts through the 120-second auth expiry; the receipt remains until Done.
- Deferred saved checkout cart reads until authentication and reload on identity changes, with epoch/session checks preventing stale member responses from overwriting the current cart.

## Verification

Red-first regressions covered scan enforcement, kit component notes, definite checkout/return rejection and fresh request keys, receipt expiry, and member cart identity races. Focused checkout/return ops suites passed (20 and 37 tests); touchscreen checkout/return/shell suites passed (17 tests); manager access passed (6 tests); kiosk API status passed (3 tests). `PYTHONPATH=ops:kiosk` is required for the manager suite because its fixture imports `scan_codes` from the kiosk directory.

`python3 deploy/verify-checkout-redesign.py` passed synthetic checkout and return flows at 800×480 with no network access or Homebox requests. Both screenshots were visually inspected: `/tmp/ccrate-checkout-review-800x480.png` and `/tmp/ccrate-return-review-800x480.png`.

No live service, deployment, hardware, or dependencies were used. Full repository suite and physical Pi acceptance were not run in this fix wave.

## Scoped re-review follow-up — 2026-10-21

Changed the kiosk clients to treat HTTP 409 as uncertain by default. This keeps the request key and routes the user to status-only recovery, including for `Operation requires explicit reconciliation`; HTTP 400 validation errors still show the actionable correction and require a fresh review/key. Added executable checkout and return regressions that assert one confirm request, retained key, and one matching status request. The checkout module's changed CRLF lines were also adjusted so `git diff --check` is clean.

Verification: checkout UI/return UI/shell suites passed (19 tests), checkout ops passed (20), return ops passed (37), synthetic browser verifier passed, Python/Node syntax checks passed, and `git diff --check` passed.
