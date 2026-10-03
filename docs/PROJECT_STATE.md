# Project state

Authoritative project: /home/user/Desktop/inventory-system, tracked in Git with pinned unmodified Homebox v0.26.2 submodule. Ethernet SSH uses 192.168.1.62. Kiosk is loopback 17749; isolated Homebox demonstration instance is loopback 17745. This is a prototype, not the completed deployment.

## Verified

- Git clone and source are on the Pi desktop; fullscreen Equipment Terminal shortcut and touch Desktop exit are installed.
- Original printer and camera hardware tests accepted by user. On-demand camera QR decoding and browser start/cancel are integrated; physical integrated scanning acceptance remains unverified.
- Native inventory reads, Find Item, Browse Stock, touch search keyboard, asset details and native shelf display.
- Native Homebox accounts identify badge holders. Approved hashed random-token registry supports issuance and revocation. Open setup Admin is explicitly approved temporarily.
- Server-enforced two-minute badge inactivity timeout; touches/scans extend it, background polling does not. Expiry clears session and cart. Confirmation ends the session immediately.
- Eight approved states use native Equipment condition field and native archive flag. Unreviewed is blocked until Admin explicitly marks Ready. Only Ready is eligible. Native update metadata preservation and touch confirmation pass live integration.
- Individually tracked assets (quantity 1) can be checked out by badge, touch cart or scan and one confirmation. Native membership, condition and custody are revalidated. The ledger completes the cart atomically and idempotently. Native inventory is unchanged; borrower is resolved and displayed separately.
- 60 unit tests pass. Scanner/touch keyboard, conditions, checkout, return and map live Pi Chromium integration tests pass with no browser errors. Results are in corresponding docs/*-integration-results.json files.
- Routine return defaults to its current assigned parent; changed conditions/notes and scanned active destinations use journaled native writes. Any current badge holder can return. Admin can finish or safely cancel an interrupted operation; completed history is visible.
- Workshop room/object geometry is stored on native location fields. Touch steppers place/resize locations; Find Item highlights the exact native shelf. Removing a visual placement preserves the location. No real layout has been invented.
- Homebox cold backup/restore, attachment bytes and API-key continuity verified. Recovery helpers use correct relative storage prefix. External backup media and full deployment recovery remain incomplete.

## Current phase

Return, history and recovery are implemented. Native workshop map and touch placement are implemented. Native location management, problem reporting and kits are next. User delegated recommended choices; no pending question blocks development.

## Remaining work from the original plan

native user setup; badge/asset/location label design and printing; kits and nested contents; offline product catalog and enrollment; problem reports and maintenance; activity/history views; consistent companion backup and restore; runtime services/startup/offline hardening; production credentials/Admin access; bulk quantities; physical scanner/printer and user acceptance of the integrated workflows.

## Limits

The current account and assets are synthetic. Checkout and return proof assets remain archived to preserve native references in operational history. No real equipment has been checked out by these tests. Trashed retains an asset record. The return UI is live for synthetic individual assets. It keeps custody through uncertain native outcomes until Admin recovery verifies the saved plan. Native condition updates perform read/modify/PUT; concurrent edits made directly in Homebox cannot be made atomic with companion updates by this API. Production concurrency policy and configuration require later review.
