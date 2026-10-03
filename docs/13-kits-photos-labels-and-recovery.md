# Core workflow and deployment expansion

## Feature

Verified native kits, deliberate photos, native inspection/maintenance, labels, category/filter setup, managed startup and full backup.

## Problem

The first milestone lacked kit completeness, native photos, native category controls and an operational recovery package.

## User Goal

Complete the core touch workflows and recover the terminal without duplicating Homebox inventory.

## User Experience

Scan the complete kit, confirm one cart, inspect problems with photos, browse by category/location/condition, print stable native QR labels and create a private backup from Admin.

## Current Homebox Behavior

Native custom fields support UUID manifests. Native attachments and maintenance store equipment evidence. Native entity types supply categories.

## Proposed Behavior

Use these native structures through the API and keep only temporary intent and operational outcomes in the companion.

## Scope

Nested kit checkout/return; scan receipts tied to badge generation; photos; maintenance completion; categories; filters; badge/asset/location label adapter; service management; cold deployment backup and isolated restore.

## Out of Scope

The handoff section 75 explicitly defers consumables/bulk stock, reservations, multi-kiosk, NFC/RFID and advanced reporting. These are not acceptance blockers for this build.

## User Decisions

DEC018 delegates judgement. Verified kit handling is recommended. Both the kit and all expected components must be scanned; a checked-out kit is returned as one complete manifest. Explicit Admin review controls Ready.

## Data Model

Kit custom fields contain native UUID references only. Pending photo input is purged when its native attachment is verified. Badge print input stores a code hash, never a bearer token or QR raster. No separate inventory or product database.

## API Changes

Native kit, category, photo/file, maintenance, system and backup endpoints. Core mutations remain same-origin loopback. User confirmations identify badge generation and server instance.

## Homebox Integration

Unmodified pinned v0.26.2. Native parent locations stay unchanged during checkout and kit definition. Native templates, entity types, maintenance entries and attachments remain directly usable.

## UI Changes

Large verified-kit checklist, deliberate photo preview/capture/cancel, stock filters, touch categories/account setup, serial scan mode, manual code entry, file viewer and Admin system controls.

## Hardware Dependencies

SUPVAN access persists through a rule scoped to VID1820/PID207f and owner user. A narrow offline-built adapter prints exactly one raster fitting loaded stock. Actual webcam and physical label quality still need final integrated acceptance.

## Security Considerations

Temporary open Admin is explicitly approved. Real passwords stay in request memory and native Homebox password hashing. Raw badge tokens never enter print journals, files or diagnostics. Private backups contain credentials and must be protected.

## Offline Considerations

The kiosk uses system fonts and local resources. Native product templates supply the offline catalog. User services start without SSH login and restart after failure. Full runtime backup includes the native binary, Python dependencies and printer adapter.

## Failure Modes

Unknown native POST and printer outcomes require Admin review. Lost print completion is never blindly retried. Photos, categories and maintenance are verified against native IDs before the journal completes. Kit cycles, missing components and changed manifests block confirmation.

## Logging / Diagnostics

90 Pi unit tests pass. Live integration results are in docs. System diagnostics show service state, stock dimensions, camera device count, free storage and backup state without exposing credentials.

## Implementation Steps

Implement each native reference structure; add touch paths; verify synthetic live workflows; add scoped printer access; install user services; cold backup; isolate restore; conduct offline/crash/boot checks; complete physical/user acceptance.

## Unit Tests

90 Pi tests pass, including nested manifests, cycle rejection, missing scan rejection, badge print request deduplication, revoked badge rejection and raw-token exclusion.

## Integration Tests

Native account enrollment; kits checkout/return; enrollment/issue photos; filters; file preview; manual code entry; exact-case serial; condition reviews and maintenance completion passed on Pi Chromium.

## Hardware Tests

One stable native QR proof label completed and the same request did not reprint. Preview decoded correctly. Physical paper legibility is not claimed. Camera tests so far use synthetic browser feed.

## User Acceptance Tests

An uncoached human walkthrough remains required. The account and equipment used by integration tests are synthetic.

## Upgrade / Migration Considerations

Operational schema remains v2. Native manifests and map fields use version1; newer formats are rejected for review. Preserve Homebox pin and offline dependencies.

## Rollback Plan

Restore the matched application/state/runtime archive to a private directory first, validate hashes and native/operational data, then replace the deployment only during a planned stop. Never restore individual stale databases over a running system.

## Definition of Done

This implementation milestone is verified. Full acceptance still requires offline/crash/boot evidence, physical scanning/printing and an uncoached user test.
