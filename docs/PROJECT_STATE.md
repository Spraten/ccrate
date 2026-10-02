# Current Phase

Phase 1 hardware proof in progress, 2026-10-02. Companion interaction-layer boundary approved.

# Working

- SSH key authentication to user@192.168.1.61, with intermittent connection failures.
- Pinned unmodified Homebox v0.26.2 source and checksum-verified ARM64 binary on Pi.
- Isolated loopback baseline at 127.0.0.1:17745; health and web entrypoint returned 200.
- Synthetic registration/login, API keys and revocation, entities, locations, metadata/custom fields, QR/label rendering and dated maintenance creation verified through live API probes.
- Project on Pi desktop, tracked with Git; upstream Homebox preserved as pinned submodule.
- DSI display detected at 800 by 480; Chromium installed.
- SUPVAN 1820:207f and webcam 0c45:636b detected after user attached them.
- Source/API and printer feasibility reports prepared.

# In Progress

- Printer ARM64 CLI built successfully; one 40 by 30 mm test label completed. Physical legibility awaits confirmation.
- Diagnostic UI running; five targets registered. Browser scaling and local camera permission adjusted; physical QR test pending.
- Latest evidence in docs/03-hardware-proof.md and hardware JSON reports.

# Decisions Waiting on User

- DEC P001 resolved: approved unmodified Homebox plus companion interaction layer (DEC 003).
- No blanket Ops database approval; evaluate native capabilities and review specific storage gaps when relevant.
- DEC P003 final deployment approach; hardware checks can begin without boot-service installation.

# Known Problems

- SSH intermittently times out; cause unknown.
- Webcam captured valid 640 by 480 frames at approximately 9.8 FPS after reconnect, then disconnected again with USB error -71. Browser preview and physical QR decoding remain unverified.
- Printer build, device probe and one-label command succeeded; physical print quality remains unverified.
- Published schema differs from actual source routes.
- Maintenance requires a completed or scheduled date; missing both produces 500 rather than a useful validation status.
- Printer access temporarily granted by a scoped user ACL; no persistent permission rule.
- Homebox retail barcode lookup requires Internet; offline catalog remains future custom work.
- No RTC detected; offline timekeeping remains unresolved.

# Next

SSH recovered; user confirmed address 192.168.1.61. Await webcam reconnect and physical test-label feedback, verify browser preview and physical QR scanning, then review the hardware checkpoint. Keep data native to Homebox where supported. No checkout implementation yet.

# Resume Information

Pi folder `/home/user/Desktop/inventory-system`; source commit `e01dd737238a3fa7e1a6454b37de6c6fc88c86e4`. Baseline process PID, log, pepper and synthetic test credentials live under `work/baseline` with restrictive permissions. This is a test process, not a boot service. Never paste the private test credentials or pepper into reports. `deploy/probe_homebox.py` reproduces the API checks with synthetic assets; each run adds test entities, so use only the isolated test database. The original handoff is preserved at `docs/PROJECT_HANDOFF.md`.

