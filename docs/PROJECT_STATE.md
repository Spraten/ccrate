# Current Phase

Phase 0 reconnaissance and initial architecture checkpoint, 2026-10-02.

# Working

- SSH key authentication to user@192.168.1.61, with intermittent connection failures.
- Pinned unmodified Homebox v0.26.2 source and checksum-verified ARM64 binary on Pi.
- Isolated loopback baseline at 127.0.0.1:17745; health and web entrypoint returned 200.
- Synthetic registration and login succeed; unauthenticated entity requests rejected.
- DSI display detected at 800 by 480; Chromium installed.
- SUPVAN 1820:207f and webcam 0c45:636b detected after user attached them.
- Source/API and printer feasibility reports prepared.

# In Progress

- Complete authenticated live API probe; first API-key probe had duplicated Bearer-prefix handling, revised probe normalizes it.
- Copy final reports and probe evidence into Pi docs folder.

# Decisions Waiting on User

- DEC P001 companion architecture versus upstream fork.
- DEC P002 operational/map persistence.
- DEC P003 final deployment approach; hardware checks can begin without boot-service installation.

# Known Problems

- SSH intermittently times out; cause unknown.
- No camera capture, QR decode, touch input or test print has been verified.
- Printer ARM64 build is plausible from source, but unproven.
- Published schema differs from actual source routes.
- Homebox retail barcode lookup requires Internet; offline catalog remains future custom work.
- No RTC detected; offline timekeeping remains unresolved.

# Next

Present the initial architecture checkpoint and await feedback. Then perform Phase 1 hardware proof. No checkout implementation yet.

# Resume Information

Pi folder `/home/user/Desktop/inventory-system`; source commit `e01dd737238a3fa7e1a6454b37de6c6fc88c86e4`. Baseline process PID, log, pepper and synthetic test credentials live under `work/baseline` with restrictive permissions. This is a test process, not a boot service. Never paste the private test credentials or pepper into reports.
