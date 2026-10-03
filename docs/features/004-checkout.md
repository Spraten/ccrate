# Feature

Operational ledger foundation

# Problem

Fast checkout needs reliable custody history and a badge identity tied to native Homebox users.

# User Goal

Identify with a badge, scan equipment and confirm without typing.

# Current Homebox Behavior

Native users/group membership and inventory metadata are available. No native custody transaction ledger or badge lookup.

# Homebox Integration

Use native user/group/entity UUIDs and supported APIs. No direct Homebox database mutation or source changes.

# Hardware Dependencies

Touchscreen and on-demand camera; physical integrated QR acceptance pending.

# Offline Considerations

Python standard library SQLite and local dependencies only. No network service required at runtime.

# Upgrade / Migration Considerations

Initial schema only; schema migrations must be explicit before deployment.

# Rollback Plan

Modules are not connected to production workflow endpoints; revert project commit. Preserve any future operational data before rollback.

# User Experience

Workflow UI pending admin/session decisions. Shelf stays in Homebox; companion shows custody separately.

# Proposed Behavior

Journal intent, reserve assets, complete custody/cart atomically, retain unresolved operations and reconcile explicitly.

# Scope

Operational UUID references, intent/outcome events, current custody projection, idempotency and recovery.

# Out of Scope

Copied inventory, badge UI, condition policy, cart UI or automatic external-write reconciliation.

# User Decisions

DEC 009 limited ledger and DEC 010 preserve shelf approved. Admin and session behavior pending.

# Data Model

operations, operation_assets, append-only events and custody projection. Actor/group/entity references only.

# API Changes

None to Homebox; workflow endpoints not enabled yet.

# UI Changes

None yet.

# Security Considerations

Membership/authorization validation required in service before calling ledger. Append-only SQL guards are application protection, not tamper-proof storage against trusted administrators.

# Failure Modes

Pending/review operations reserve referenced assets; another checkout conflicts. Cart completion rolls back entirely on failure. Never silently mark an unknown result complete.

# Logging / Diagnostics

Durable request/review/reconciliation/completion events.

# Implementation Steps

Implement foundation, verify concurrency/crash persistence, connect native validation and approved identity/session flow, then test end-to-end.

# Unit Tests

11 tests pass on Windows and Pi: repeat/changed idempotency key, custody return, pending restart, atomic rollback, append-only guards, simultaneous attempts, group isolation, duplicate assets and reconciliation.

# Integration Tests

No operational endpoint integration yet.

# Hardware Tests

No real checkout yet.

# User Acceptance Tests

Pending badge/admin choices and checkout UI.

# Definition of Done

Foundation tested. Full checkout is incomplete until native validation, badge/session/UI and recovery integration pass.
