# Native setup and problem reporting

## Feature

Native location management, offline product catalog, equipment enrollment and problem reporting.

## Problem

Touch-only setup and issue reporting previously ended at workflow previews.

## User Goal

Create an asset at a native shelf and record equipment problems without changing Homebox itself.

## User Experience

Admin creates locations and product defaults. Badge holders add individually tracked assets or report blocked conditions with touch text entry.

## Current Homebox Behavior

Native locations, templates, entities, custom fields and scheduled maintenance are available through the pinned API.

## Proposed Behavior

The companion guides these APIs and journals uncertain writes for Admin recovery.

## Scope

Native creation, GTIN template lookup, serial duplicate guard, shelf selection, explicit review and scheduled issue entries.

## Out of Scope

Photo capture, arbitrary QR printing, kits and production account setup are separate remaining milestones.

## User Decisions

DEC018 delegates recommended choices. New assets default Unreviewed. Only explicit inspection can mark Ready. Problem reports never imply a completed repair.

## Data Model

Additive operational schema v2 stores pending native intent and append-only outcomes. Completed/cancelled intent is purged. Inventory and catalog remain native.

## API Changes

Same-origin loopback creation and problem confirmation endpoints; badge generation plus process instance protect confirmation identity.

## Homebox Integration

Unmodified v0.26.2 native entity/template/tag/maintenance APIs. Temporary native markers identify a record after a lost creation response and are removed after verification.

## UI Changes

Touch-only fields, shift and punctuation keys, storage selector, review before confirmation and Admin recovery.

## Hardware Dependencies

Existing Pi touchscreen. Camera routes product/location codes. Integrated physical scanner acceptance remains outstanding.

## Security Considerations

Approved temporary open Admin; ordinary enrollment and problem reporting require current native group badge membership. Passwords are not copied into companion tables.

## Offline Considerations

Catalog uses native templates and needs no remote product service. All endpoints run on loopback.

## Failure Modes

Unknown write outcomes enter review. Entity creation is never blindly repeated. Native changes conflicting with saved recovery intent require manual review.

## Logging / Diagnostics

Append-only operation events contain outcome/reference data. Completed job input is purged. Integration result JSON files record evidence.

## Implementation Steps

Back up operational DB; migrate additively; implement native markers; connect touch workflows; verify real native API; commit reviewed source.

## Unit Tests

77 Pi tests pass, including native job lifecycle, migrations, template creation and lost-response mock recovery.

## Integration Tests

Enrollment and problem live Chromium checks pass; problem test injects a lost native maintenance response and verifies no duplicate after recovery.

## Hardware Tests

Existing initial hardware acceptance stands. New physical integrated scan/print tests are not claimed.

## User Acceptance Tests

Touch interactions are automated at 800x480; an uncoached real user has not yet completed the integrated workflows.

## Upgrade / Migration Considerations

Schema v2 preserves earlier checkout/return/badge tables. Newer schemas are rejected. Native templates remain usable directly in Homebox.

## Rollback Plan

Verified pre-v2 consistent backup is in work/backups. Restore matching application and database together; retain native records created after backup for manual reconciliation.

## Definition of Done

This milestone is implemented and verified; the full project still requires remaining original-plan workflows and physical acceptance.
