# Current Phase

Scanner integration complete technically; physical camera acceptance pending. Badge and checkout implementation await user decisions, 2026-10-02.

# Working

- Pi desktop project, pinned unmodified Homebox v0.26.2 submodule.
- Homebox loopback 17745, hardware diagnostic 17746, kiosk 17749.
- Approved six-button home, touch Desktop exit, full-screen desktop shortcut.
- Shortcut starts existing baseline after reboot without registering or seeding data.
- Native read-only search/browse/details and on-demand camera scanner.
- Real QR decoding/native asset resolution passed; Pi browser tests passed with a synthetic camera and no JavaScript errors.
- Nine demo locations and six demo assets; 27 total entities including previous recon data.
- Native group member lookup verified.
- Cold backup restore verifies entity identities, attachment bytes and API-key continuity. Relative blob storage prefix fixed; original synthetic files preserved.

# Confirmed Decisions

- Unmodified Homebox with companion interaction layer; native inventory authority.
- Six large home buttons.
- Badge only, no PIN, for prototype.
- Scan button; camera stops on cancel or resolved item.

# Required User Decisions

- Badge people: Homebox accounts or borrower records.
- Checkout persistence: limited event ledger, native fields with reduced accountability scope, or defer.
- Physical scanner acceptance still awaiting user result.

# Not Implemented

Badge enrollment/session, custody operations, condition workflow, kits, map, catalog, enrollment/label workflow, administration/permissions, independent backup media, final deployment and offline/recovery/user acceptance remain in original plan. No ledger or duplicate inventory database created. Future product decisions will be asked at the relevant phase.

# Known Limits

Earlier Wi-Fi/USB instability; long-duration hardware reliability unproven. No RTC. Source/API schema drift. Offline timekeeping unresolved. No boot services installed. Independent media and abrupt power loss recovery untested.

# Resume

Ethernet 192.168.1.62; Wi-Fi 192.168.1.61. SSH HostKeyAlias=192.168.1.61 verifies the known Pi key over Ethernet. Folder /home/user/Desktop/inventory-system. Private credentials/pepper under restricted work/baseline; never expose them. Artifacts under ignored work/. deploy/start-baseline.py starts only the existing demo; deploy/complete-baseline.py seeds and creates a new backup, so do not rerun unnecessarily. docs/05-scan-integration.md and docs/06-native-accountability-gap.md contain evidence and the storage proposal. Latest recovery evidence in recovery-verification-results.json.
