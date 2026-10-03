# Feature

Badge checkout and operational ledger

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

Initial operational schema is unchanged by this integration. Condition is a native Homebox text field; native archive flag takes precedence. Explicit migrations are required for future schema changes.

# Rollback Plan

Prototype checkout endpoints are connected to the isolated demonstration account. Preserve work/ops/ledger.db and its WAL in a consistent backup before rollback. Restore source from Git without deleting operational history. Production account configuration remains pending.

# User Experience

Badge identification, touchscreen cart selection or scanning, removal and one confirmation. Shelf stays in Homebox; item detail resolves the borrower from native group membership. Session ends immediately after success and expires after two idle minutes.

# Proposed Behavior

Revalidate native group membership and each selected asset at confirmation, require Ready and quantity 1, journal intent, reserve assets and complete custody/cart atomically. Repeated request keys are idempotent. Keep unresolved operations reserved for explicit reconciliation.

# Scope

Operational UUID references, intent/outcome events, current custody projection, idempotency and recovery.

# Out of Scope

Copied inventory, changes to upstream Homebox, bulk quantity checkout and automatic external-write reconciliation. Return service and different-destination recovery are subsequent work.

# User Decisions

DEC 008-017 approve native identities, operational ledger, preserved shelf, badge registry, open setup Admin, session end after confirmation, default return shelf, two-minute idle timeout, eight conditions and review-before-Ready.

# Data Model

operations, operation_assets, append-only events and custody projection. Actor/group/entity references only.

# API Changes

No upstream API changes. Companion POST /checkout/confirm, GET /api/custody, GET /api/entity and POST /condition use supported Homebox APIs and the approved ledger. Confirmation requires an active badge session; same-origin guards apply to mutations.

# UI Changes

Checkout cart, Scan badge/equipment, touch selection/removal, confirmation, borrower display, condition review/confirmation and touchscreen search keyboard.

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

Live Pi/Homebox integration passes: badge required, unreviewed cart rejected, two-asset touchscreen checkout, repeated confirmation idempotent, native inventory unchanged, borrower visible and session cleared. See docs/checkout-integration-results.json. Synthetic test assets are archived after cleanup; test custody was returned through the ledger API, not the incomplete return UI.

# Hardware Tests

No real checkout yet.

# User Acceptance Tests

Physical integrated scanner and actual user workflow acceptance remain pending. Browser tests use touch events on native Pi Chromium.

# Definition of Done

Basic individually tracked asset checkout is implemented and integration-tested. Full plan remains incomplete: live return, alternative destination journaling/reconciliation, Admin recovery UI, bulk quantities, physical workflow acceptance, kits and deployment hardening are outstanding.
