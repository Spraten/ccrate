# Feature

Journaled return and recovery

## Problem

Returns must be quick and must not lose custody when a native API update is interrupted.

## User Goal

Identify, scan equipment, confirm its recorded condition and shelf; report changes only when needed.

## User Experience

Return cart supports touch selection or scans, previous condition, optional changed condition/note, destination scan, remove and one confirmation. Any badge holder may return equipment. Successful confirmation ends the session.

## Current Homebox Behavior

Native entity parents, custom fields, archive state and supported PUT/PATCH APIs are available. Homebox has no native custody transaction.

## Proposed Behavior

Journal return intent before any native change. Verify condition/note and destination, then clear the complete cart custody atomically. An uncertain result remains reserved for explicit Admin recovery.

## Scope

Individually tracked assets, default shelf, changed conditions, touch notes, location scans, idempotency, history and recovery.

## Out of Scope

Bulk quantity returns, kit verification, automatic physical quarantine movement and production Admin authentication are later work.

## User Decisions

DEC 013-020: end session after confirmation, default shelf, two-minute idle expiry, reviewed Ready eligibility, recommended-choice delegation, any-member return and exception-only condition edits.

## Data Model

Existing operational tables plus schema-v1 operation_context. Snapshots hold native IDs and operational before/after values. Native fields hold current condition/note.

## API Changes

Companion POST /return/confirm, GET /api/history, GET /api/recovery, POST /recovery/resolve, GET /api/locations. No upstream Homebox API changes.

## Homebox Integration

Supported native GET/PUT/PATCH only; full condition updates preserve metadata. Native move uses parentId PATCH. No direct Homebox database writes.

## UI Changes

Return cart, changed-condition screen, touch note keyboard, scanned destination, per-item history, open setup Admin recovery and explicit recovery confirmation.

## Hardware Dependencies

Touchscreen and on-demand QR camera. Browser tests use Pi Chromium touch events and a synthetic camera; integrated physical acceptance remains to be observed.

## Security Considerations

Current native membership and active badge are required for return. Mutations require the kiosk origin. Recovery is limited to the current group and approved temporary open Admin. Normal returns cannot unblock equipment.

## Offline Considerations

All APIs, decoder and assets are local. Inactive session polling no longer requires Homebox availability. Physical zero-network deployment tests remain pending.

## Failure Modes

Lost native responses or ledger completion failures retain custody and reserve every selected asset. Recovery compares current values against the saved intent. Unrelated native changes block automatic completion. Cancellation cannot hide applied changes.

## Logging / Diagnostics

Append-only requested, native-condition start/verified, destination start/verified, review, reconciliation and completion events. History resolves actor names from current native membership.

## Implementation Steps

Back up schema zero; apply additive version-one migration; validate return intent; implement native steps and recovery; wire touch UI; run unit and real Homebox integration tests.

## Unit Tests

51 total tests pass. Ten return tests include colleague return, no native rewrite for unchanged return, idempotency, changed condition/note/destination, lost response recovery, cancellation before write, expiry, removal from group and cross-group rejection. Two migration tests preserve legacy requests/custody and reject newer databases.

## Integration Tests

docs/return-integration-results.json proves unchanged return, default shelf, native record preservation, touch issue note, scanned alternate destination, metadata preservation, idempotency, session end, injected lost native response, touch Admin recovery and visible asset history.

## Hardware Tests

Original hardware proof accepted by user. Physical complete return with real QR labels is still pending.

## User Acceptance Tests

No uncoached-user acceptance yet; do not claim the full project complete.

## Upgrade / Migration Considerations

SQLite user_version=1, additive operation_context. Pre-migration operational backup has integrity_check=ok. Native layout/condition fields remain supported API metadata.

## Rollback Plan

Preserve a consistent operational backup, then revert source. Native changes already completed by a return remain in Homebox. Do not discard context or history for unresolved operations.

## Definition of Done

Prototype individual-asset return, history and recovery are implemented and integration-tested. Physical acceptance, production permissions, kit/bulk behavior and full backup/restart tests remain part of the overall plan.
