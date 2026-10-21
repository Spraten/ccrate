# Printer recovery fix

## Root cause

`ops/labels.py` selected the adapter beneath `WORKSHOP_ROOT`, but the running service uses that variable for its writable data directory. Investigation confirmed the adapter executable was physically absent under both the runtime data root and the code root. Resolving against `WORKSHOP_CODE_ROOT` fixes the lookup when deployed with the adapter; explicit missing/non-executable detection now reports the actual software gap. `ops/hardware.py` classified every `FileNotFoundError` as a disconnected printer and advised USB reconnect steps.

## Changes

- Resolve adapter path using `WORKSHOP_PRINTER_ADAPTER`, then `WORKSHOP_CODE_ROOT`, then legacy `WORKSHOP_ROOT` fallback.
- Check adapter existence and executability before enumerating hidraw, identifying missing software as `adapter_missing`.
- Return actionable admin restore/rebuild guidance without cable or unplug advice for missing adapter software.
- Add `deploy/restore-printer-adapter.sh`, which checks for Rust 1.88+ and liblzma development files, prints exact official Debian Trixie backports setup guidance when prerequisites are missing/too old, verifies the pinned source checkout using a full untracked-file status, builds into a persistent separate Cargo target cache, and atomically replaces the output after success. It does not install packages, print, or restart services.
- Render `adapter_missing` in DeviceStatus as “Software setup needed”. Reconnect remains a fresh, read-only probe and never prints or retries a print.

## Verification

`PYTHONPATH=ops:tests python -m unittest test_restore_printer_adapter test_labels.PrinterAdapterResolutionTests test_hardware.HardwareTests` — 8 tests passed, including script preflight, dirty-checkout refusal, adapter path precedence, and missing-adapter detection before USB discovery and subprocess launch. `sh -n deploy/restore-printer-adapter.sh` also passed.

The coding worker performed no physical printer action, service restart, deployment, or toolchain installation. The coordinator subsequently restarted ccrate-local-test.service to apply the backend diagnostics; service startup completed and localhost:17745 returned ready. Toolchain installation, adapter build and actual printer readiness remain blocked/pending.

Coordinator verification: full focused suite `PYTHONPATH=ops:tests python -m unittest test_labels test_hardware test_restore_printer_adapter`: 23 passed. Independent re-review approved source fixes. No physical output or print replay.

## Restoration completed — 2026-10-19
User confirmed package setup completed. Installed system Rust/Cargo1.96.1. `deploy/restore-printer-adapter.sh` succeeded (initial release build3m12s), restoring the pinned-source executable to the code-root path. A second script invocation reused cache (Cargo0.08s), confirming repeat restoration accepts its own source example and preserves cache.

Fresh verification:
- `PYTHONPATH=ops:tests python -m unittest test_labels test_hardware test_restore_printer_adapter`:23 passed.
- Actual `hardware.reconnect('printer')` using running service root settings: connected=true, reason=ready,40x30mm stock,3mm gap.
- Authenticated live UI hardware/status HTTP200 reports connected. Clicking the Printer popup's Reconnect button returned HTTP200 connected=true and rendered “Reconnected and ready.” Screenshot `work/frontend-review/printer-recovery-ready.png` inspected.
- No additional service restart required for the restored executable. No physical label or uncertain job replay was requested. Connection and material readiness verified; printed output was not tested.

Earlier pending toolchain/build/readiness notes above are historical and now resolved. Diagnostic fixes and restore tooling had already passed independent review.

## Sample-label follow-up (2026-10-19)

User authorized one physical sample. Live label preview initially returned HTTP 400 because asset roots pointed at label-ui source instead of work/label-ui-build. Corrected defaults in ops/label_render.py and deploy/kiosk-server.py, preserved explicit asset override, and resolved existing Playwright runtime from code root with override forwarded to subprocess. Focused renderer suite: 13 passed with explicit code root. Independent review found no scoped blockers. Service restarted to apply Python path fix. Live draft preview HTTP 200 for BS30 Intelligent Battery Charging Station, with full generated ID BATTERY-STATION-LAB-D-G38-1; no render warnings. Physical submission outcome to follow.

Single UI-confirmed physical print returned HTTP 200, status completed, operation 6cc6601b-dbd3-4244-8ce9-89b7fa60e35f. Saved reusable design QR + item name + Unique ID, template 09b29842-3fd7-4237-a194-4a81cab1a543. No retries or additional labels sent. Physical appearance requires user inspection.

## Physical-output contradiction

User reports that no label printed despite the adapter/operation reporting completed. Previous completed status is NOT evidence of physical success. No automatic retry sent. Read-only USB status on attached 1820:207f device: registers 00 00 10 00, print_count 0. HID descriptor declares 64-byte unnumbered output reports. Pinned adapter transport writes 64 payload bytes directly without report-ID prefix; Linux hidraw requires report-ID byte 0 preceding unnumbered payload. Kernel v6.18 usbhid_output_report strips a leading zero, so affected data packets lose a byte. Investigating exact sample packet evidence before confirming this explains the absent output.

Exact offline sample reproduction: Bayer raster compressed to one 1160-byte block; 64-byte payload chunks4 and5 begin with0, so old Linux HID framing drops two bytes. Implemented deploy/printer-hidraw.patch (65-byte hidraw buffer including separate zero report ID, full-write validation), guarded idempotent restore support and status diagnostics in adapter. Three Rust fixtures passed, offline build and isolated restore-twice fixture passed. Independent Sol review: no blocking findings.

One replacement submitted after user confirmed original printer completely idle. User explicitly confirmed replacement printed successfully. API returned409 uncertain; read-only device status after showed count0, regs00 00 10 80. Therefore do NOT use print_count advancement as a completion requirement: this hardware printed without incrementing that field. Based on user physical confirmation, resolved exact replacement operation f4c62df2-38e1-4d57-b15d-ed9184d9e7ee via normal UI Recovery, HTTP200 completed. No additional print sent. Remaining issue: automatic device completion acknowledgement can report uncertain despite physical success; preserve conservative recovery rather than false success.
