# Feature

Private cold backup and recovery

## Problem

The original handoff requires private cold backup and recovery within a convenient local Homebox companion.

## User Goal

Touch confirmation launches a separate user service. Stop both services, capture a private consistent archive, then restart. Restore into an isolated directory and loopback port before considering live recovery.

## User Experience

Touch confirmation launches a separate user service. Stop both services, capture a private consistent archive, then restart. Restore into an isolated directory and loopback port before considering live recovery.

## Current Homebox Behavior

Native inventory, templates, locations, custom fields, attachments and maintenance are accessed through the pinned v0.26.2 API. Native Homebox provides no companion custody/session transaction.

## Proposed Behavior

Implemented in deploy/backup-deployment.py and deploy/verify-deployment-restore.py. Current behavior is described below; this plan records the shipped prototype, not speculative future scope.

## Scope

Touch confirmation launches a separate user service. Stop both services, capture a private consistent archive, then restart. Restore into an isolated directory and loopback port before considering live recovery.

## Out of Scope

Section75 future features, invented real inventory/layout, unapproved private archive transfer and stronger production Admin policy. Physical and human passes cannot be inferred from automation.

## User Decisions

DEC026; see DECISIONS.md for rationale and approved overrides.

## Data Model

Private source/runtime/native storage/ops/credential archive and checksums; never included in public report.

## API Changes

Companion endpoints are implemented in deploy/kiosk-server.py. No upstream API or source modification.

## Homebox Integration

Use supported native APIs. Preserve full entity metadata for native PUT. No direct Homebox database writes.

## UI Changes

Touch confirmation launches a separate user service. Stop both services, capture a private consistent archive, then restart. Restore into an isolated directory and loopback port before considering live recovery.

## Hardware Dependencies

Pi4, 800×480 touchscreen, Chromium; camera and SUPVAN USB printer for the relevant scan/photo/label steps. No physical keyboard required.

## Security Considerations

Loopback services, same-origin mutations, private credentials outside Git, current native membership for badge transactions, approved temporarily open setup Admin. Badge identification is not strong authentication.

## Offline Considerations

All runtime assets and dependencies are local and pinned in runtime-manifest.json. Kernel-isolated local workflow proof is in offline-isolation-results.json.

## Failure Modes

Pending native jobs and operational intents preserve uncertain outcomes for explicit recovery. Do not blindly repeat an unknown print or native creation. Read the implementation-specific evidence below for the tested failures.

## Logging / Diagnostics

Native/operational event history plus journalctl --user -u homebox-companion.service and -u homebox-native.service. System Status shows service/device/storage failures.

## Implementation Steps

Implement native integration, durable intent where required, touch UI, then unit and live API/browser verification. These engineering steps are already performed for this prototype.

## Unit Tests

Run PYTHONPATH=ops:kiosk:work/hardware/python python3 -m unittest discover -s tests. Current suite has 95 tests; source tests provide exact coverage rather than assuming every feature has a dedicated unit test.

## Integration Tests

deployment-restore-results.json; final-touch-results.json; crash-recovery-results.json; reboot-results.json; inspect these files for exact tested behavior and injected-versus-real limitations.

## Hardware Tests

Initial camera/printer proof accepted by the user; actual camera stream and one completed proof print observed remotely. Current physical integrated QR scanning, print legibility and disconnect tests remain pending.

## User Acceptance Tests

Follow ACCEPTANCE_AUDIT.md. An unfamiliar person must perform the relevant task without coaching; record taps/scans/time/screens/typed fields/errors/help. No uncoached pass is currently claimed.

## Upgrade / Migration Considerations

Pin upstream and runtime versions. Operational schema2 is additive and covered by migration tests. Back up source, native data and operational journal before changing versions. Never discard pending operation context.

## Rollback Plan

Preserve a verified private archive and operational history, then revert source as needed. Restoring native and operational data must be coordinated; do not independently revert one while discarding completed transactions.

## Definition of Done

Engineering prototype behavior and referenced evidence are implemented. Full acceptance additionally requires the relevant physical/human gates and actual deployment setup. See ACCEPTANCE_AUDIT.md; do not mark the entire goal complete yet.

