# Phase 1 Hardware Proof

Date: 2026-10-02. Prototype diagnostics; inventory workflows are not implemented.

## Verified

- DSI display is 800 by 480. Headless Chromium screenshot visually inspected at that resolution: all controls fit. All five targets registered pointer events reported as mouse; physical touchscreen confirmation remains pending.
- Synthetic QR HARDWARE-PROOF:QR:001 decoded successfully with zxing-cpp.
- After webcam reconnection, FFmpeg captured a valid 640 by 480 JPEG (16,143 bytes) and streamed 50 frames over 5.104 seconds, approximately 9.8 FPS, at maximum RSS 68,016 KiB. This is a short diagnostic, not a sustained benchmark.
- Webcam subsequently disconnected again. It is absent from lsusb and capture devices; kernel logs show descriptor/enumeration error -71. Cause remains unknown. Browser recorded NotFoundError. User reported difficult camera permission interaction and an insecure-connection indication.
- Dedicated diagnostic Chromium profile restarted with device scale factor 1 at http://127.0.0.1:17746. Camera permission saved only for that loopback origin. No global security bypass was enabled; resulting user experience remains to verify.
- SUPVAN 1820:207f accessed through a temporary user ACL on hidraw0. No permanent permission rule; device recreation/reboot removes access.
- Unmodified printer source pinned at 9fd7af09580c3e710202e5471e77e0b88db0e3bb. ARM64 supvan-cli release build succeeded with isolated dependencies and checksum-verified official Rust components. No system packages installed.
- Printer reported installed 40 by 30 mm labels, 3 mm gap, and no material errors. One built-in test-pattern command completed successfully at density 4; remaining labels decreased from 221 to 220. Immediate post-print status still reported busy. Physical legibility awaits user confirmation. This test pattern is not a QR label.
- Diagnostic Python wheels preserved for zxing-cpp 3.1.1, qrcode 8.2, Pillow 12.3.0 and websocket-client 1.9.2. Production scanner and printer service remain undecided.

## Files and Runtime

Local-only proof UI: deploy/hardware-proof-server.py, port 17746. Camera test: deploy/camera-proof.py. JSON evidence is in docs/camera-proof-results.json and docs/hardware-proof-results.json. Browser profile, captured frame, pinned driver source, toolchain and logs remain under ignored work/ on the Pi desktop. No camera frames are saved by the browser decoder endpoint.

## Remaining Acceptance

1. Confirm physical test-label legibility and five finger taps.
2. Restore reliable webcam connectivity, verify browser preview and decode a physical QR.
3. Measure physical scan latency and assess reconnect/reboot behavior.
4. Review hardware checkpoint before implementing workflows or choosing permanent deployment/permissions.

Homebox remains unmodified. No additional inventory database or checkout implementation has been introduced.

## Follow-up, October 2 evening

User confirmed the single test label printed clearly. A subsequent probe confirmed printer idle with no reported errors and 220 labels remaining. After webcam reconnection, its capture node changed to video1; diagnostics now use the persistent USB by-id link instead of assuming video0. Fresh capture succeeded (640 by 480, 20,432 bytes), and the five-second stream delivered 50 frames at approximately 9.8 FPS. The test UI status endpoint reports camera present. Old frames are no longer counted after failed captures; UI distinguishes disconnected camera and incorrect browser origin. Browser preview and physical QR result await user confirmation.


## Hardware checkpoint accepted

On October 2 the user confirmed: "all test are good". Browser settings confirm 640 by 480 at 10 FPS. Touch and clear print accepted; camera/QR acceptance is user-reported. The recorded scans array remains empty, so a physical decoder result was not captured in telemetry. Earlier camera_error is historical. Long-duration stability and reboot recovery remain future checks.
