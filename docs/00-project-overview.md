# Offline Equipment Kiosk Project Overview

Date: 2026-10-02. Phase 0 reconnaissance for the scanner-first equipment kiosk described in the supplied handoff. This report distinguishes verified observations, source findings, and proposals. Product workflows remain subject to user decisions.

## Scope

The product is a touchscreen equipment terminal backed by Homebox, with fast badge identification, batch checkout, return, condition reporting, equipment search, visual location maps, enrollment, and labels. Runtime must work without Internet access. Product catalog records identify product types; inventory entities identify owned physical assets.

This phase establishes an unmodified Homebox baseline, investigates integration and hardware, and proposes architecture. Checkout, badges, maps, catalog imports, and printer integration have not been implemented.

## Verified Environment

| Component | Observation |
|---|---|
| SSH target | user@192.168.1.61; key authentication succeeded |
| Hostname | pi-Homebox |
| Hardware | Raspberry Pi 4 Model B Rev 1.4, rather than the Pi 3 anticipated by the handoff |
| Architecture | Linux aarch64 |
| Operating system | Debian 13 trixie; VERSION_ID 13; PRETTY_NAME Debian GNU/Linux 13 |
| Memory | 3.7 GiB total; approximately 327 MiB used at initial inspection |
| Swap | 2.0 GiB configured; unused at initial inspection |
| Root filesystem | 29 GiB filesystem, approximately 21 GiB available; physical SD capacity was not measured |
| Display | DSI-1, 800 by 480, approximately 154 by 86 mm |
| Browser | Chromium 152.0.7977.82 |
| Printer | SUPVAN USB device 1820:207f, detected after user connected it |
| Webcam | Microdia USB camera 0c45:636b; video0 and video1 detected |
| Clock | America/New_York; synchronized by NTP; no RTC reported |
| Existing software | No Homebox service, Docker, Podman, Node.js, Codex CLI, or Go found in initial checks |

No Git project was found under /home/user, /opt, or /srv within the inspected depth of four. This is a bounded search, not proof that no files exist elsewhere. No existing experiments or inventory databases were altered.

## Baseline Location

Reconnaissance folder on Pi: `/home/user/Desktop/inventory-system`.

- Unmodified pinned source: `upstream/homebox`.
- Downloaded release and checksum list: `work`.
- Extracted executable: `work/homebox-bin/homebox`.
- Isolated test data, credentials, pepper, logs and PID: `work/baseline`.
- Baseline listens on Pi loopback port 17745, not a LAN-facing production endpoint.

The baseline is a temporary user process, not an installed boot service. Final deployment and service management are still decisions. Test credentials are restricted on the Pi and excluded from deliverables.

## Acceptance Limits

USB detection does not prove camera capture, QR decoding, printing, touch events, or sustained kiosk performance. Those are Phase 1 tests. SSH intermittently timed out during reconnaissance, and no cause has been established. This should be reproduced and resolved before relying on unattended remote administration.

## Next Checkpoint

Review the architecture proposal, then perform hardware proof at the actual 800 by 480 resolution. Defer badge policy, return policy, map editor behavior, kit verification, permanent QR namespace, condition vocabulary, session timeout, and backup retention until their phases.
