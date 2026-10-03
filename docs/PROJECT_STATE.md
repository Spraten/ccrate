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
- 95 unit tests pass. Scanner/touch keyboard, conditions, checkout, return and map live Pi Chromium integration tests pass with no browser errors. Results are in corresponding docs/*-integration-results.json files.
- Routine return defaults to its current assigned parent; changed conditions/notes and scanned active destinations use journaled native writes. Any current badge holder can return. Admin can finish or safely cancel an interrupted operation; completed history is visible.
- Workshop room/object geometry is stored on native location fields. Touch steppers place/resize locations; Find Item highlights the exact native shelf. Removing a visual placement preserves the location. No real layout has been invented.
- Homebox cold backup/restore, attachment bytes and API-key continuity verified. Recovery helpers use correct relative storage prefix. Complete deployment recovery passed in isolation; external backup media remains pending approval.

## Current phase

Core prototype implementation and engineering verification complete, subject to the outstanding physical and human acceptance gates. Fullscreen boot, kernel-isolated offline operation, actual webcam streaming, forced process crash recovery and final private archive restoration passed. Find Item supports serial, model, manufacturer, category, tags and description. System Status warns below 2 GiB or 10% free; below 512 MiB is critical. Simulated low-space, printer disconnect and missing-camera feedback passed without disturbing real hardware.

## Remaining requirements from the original core plan

Physical label readability and orientation, physical badge/asset/location scans, printer reconnection, abrupt power-loss recovery and uncoached user testing cannot be proved remotely while nobody is at the Pi. Real users, equipment and workshop geometry require actual setup information. Admin remains temporarily open by user choice. No real inventory has been invented. A private off-Pi backup copy awaits explicit approval after automatic review rejected transfer of credentials and private data. The public visual report is on the desktop and in docs/report.

Consumables/bulk stock, reservations and other section75 future features are excluded by the original handoff's explicit "Do Not Build Yet" rule.

## Limits

The current account and assets are synthetic. Checkout and return proof assets remain archived to preserve native references in operational history. No real equipment has been checked out by these tests. Trashed retains an asset record. The return UI is live for synthetic individual assets. It keeps custody through uncertain native outcomes until Admin recovery verifies the saved plan. Native condition updates perform read/modify/PUT; concurrent edits made directly in Homebox cannot be made atomic with companion updates by this API. Production concurrency policy and configuration require later review.

Native setup evidence: docs/enrollment-integration-results.json and docs/problem-integration-results.json. The schema-v2 migration has a verified consistent pre-migration operational backup. Native problem lost-response recovery produces one maintenance entry per report. Confirmation identifies both badge generation and server process instance.

Core evidence added: account, kit, photo, label and admin-stock integration results; deployment-restore-results.json. User services are active and lingering is enabled. The complete private backup restored native records, all operational tables, runtime hashes and a native attachment in isolation.
