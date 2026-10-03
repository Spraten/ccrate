# Current Phase

Phase 2 baseline completed; Phase 3 kiosk shell prototype ready for user review, 2026-10-02.

# Working

- Hardware checkpoint accepted by user.
- Unmodified Homebox v0.26.2 on loopback 17745; pinned submodule.
- Nine demo locations and six demo assets created through native API.
- Cold storage backup restored on separate loopback instance; all 27 entity IDs match. Restore instance stopped; original baseline restarted.
- Approved six-button shell on loopback 17749, shown in Pi Chromium.
- Live read-only inventory search, browse and item summaries. Browser DOM reports Homebox connected with eight item entities, including older recon assets.
- Source and reports on Pi desktop in /home/user/Desktop/inventory-system.

# Decisions Waiting

- User shell review before scanning infrastructure.
- Identity, timeout, QR routing/labels and production deployment policies remain undecided.
- Companion interaction layer and six-button layout approved; extra inventory database not approved.

# Known Problems / Limits

- Previous intermittent SSH/webcam USB failures; long-duration reliability unproven.
- Physical QR acceptance user-reported; no decoded scan recorded in diagnostic telemetry.
- Shell workflow previews do not change inventory. Session and scanner policies are pending.
- Backup test does not yet cover attachments/API-key continuity or independent media.
- No RTC, offline timekeeping unresolved.

# Resume

Ports: Homebox 17745, hardware UI 17746, shell 17749. Demo credentials/pepper are private in restricted work/baseline. Backup/restore artifacts under ignored work/. deploy/complete-baseline.py seeds idempotently but creates a fresh backup each run. deploy/kiosk-server.py serves kiosk/index.html and reads Homebox via API. See 04-homebox-baseline.md for recovery configuration. No boot services installed.


# Desktop shortcut

Equipment Terminal.desktop opens the prototype in a dedicated Chromium app window at full screen. deploy/open-kiosk.sh starts the shell server if needed. It does not configure boot startup or restart Homebox.

Touch-only exit: Desktop button with large confirmation controls closes only the dedicated kiosk browser. Reopen using desktop shortcut. No keyboard required.

Scan infrastructure started: native Homebox /a/{asset_id} normalization and GTIN checksum validation, six unit tests passed. Scanned URLs are parsed as identifiers and never navigated. Camera integration and badge namespace remain pending.


# Current follow-up

Ethernet active at 192.168.1.62; use known host key alias 192.168.1.61 when connecting. Wi-Fi remains 192.168.1.61. Reboot completed. Desktop launcher now restarts existing Homebox baseline before opening shell; it never creates accounts or seeds data. Scanner integrated and live tests passed: real decoder/native asset resolution plus Pi Chromium with synthetic camera. Evidence docs/scan-integration-results.json. Physical camera scan acceptance is pending; demo QR in work/demo-drone-qr.png. Full-screen app reopened; camera permission scoped to loopback port 17749.

Badge-only and Scan-button behaviors approved. User choice pending: Homebox accounts versus borrower records. Production custody/history persistence remains unapproved. No inventory mutation workflows enabled.
