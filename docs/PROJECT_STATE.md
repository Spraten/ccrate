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
- 39 unit tests pass. Scanner/touch keyboard, conditions and checkout live Pi Chromium integration tests pass with no browser errors. Results are in corresponding docs/*-integration-results.json files.
- Homebox cold backup/restore, attachment bytes and API-key continuity verified. Recovery helpers use correct relative storage prefix. External backup media and full deployment recovery remain incomplete.

## Current decision needed

May any badge holder return another person's equipment, or must it be the borrower? A clickable question is open. Routine return defaults to assigned shelf; a location scan is needed only for a different destination.

## Remaining work from the original plan

Live return and alternate-destination mutation/recovery; return condition workflow; Admin unresolved-operation recovery; native user setup; badge/asset/location label design and printing; kits and nested contents; maps and navigation; offline product catalog and enrollment; problem reports and maintenance; activity/history views; consistent companion backup and restore; runtime services/startup/offline hardening; production credentials/Admin access; bulk quantities; physical scanner/printer and user acceptance of the integrated workflows.

## Limits

The current account and assets are synthetic. Two checkout proof assets remain archived to preserve native references in operational history. No real equipment has been checked out by these tests. Trashed retains an asset record. The return UI is still a preview. Native condition updates perform read/modify/PUT; concurrent edits made directly in Homebox cannot be made atomic with companion updates by this API. Production concurrency policy and configuration require later review.
