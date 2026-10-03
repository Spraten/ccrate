# Feature

Native-user badge registry

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

Badge only, no PIN. Issuance/admin UI pending access decision.

# Proposed Behavior

Issue random bearer token once; store only its SHA256 hash and native user/group IDs. Reject revoked badges and users removed from the current group.

# Scope

Small approved badge table and resolution/issuance/revocation module.

# Out of Scope

Copied user profiles, Homebox passwords, permanent label namespace or open issuance endpoints.

# User Decisions

DEC 006 badge only, DEC 008 native users, DEC 011 token registry approved. Admin login choice pending.

# Data Model

badges: ID, token hash, native group/user IDs, revoked flag and timestamps, in the same companion database.

# API Changes

None to Homebox; membership fetched from groups/members. Badge endpoints not enabled yet.

# UI Changes

None yet.

# Security Considerations

Tokens have 256-bit randomness, stored hashed; raw token returned only at issuance. Authorization required before issue/revoke. Membership must be fetched server-side rather than trusted from browser.

# Failure Modes

Lost badge can be revoked individually. Unknown/malformed/cross-group/removed-member badges rejected.

# Logging / Diagnostics

List exposes badge IDs and revoked status, never tokens/hashes.

# Implementation Steps

Implement and test registry, resolve admin policy, native-member lookup, then connect badge/session UI and review labels.

# Unit Tests

Seven tests pass on Windows and Pi: issue/resolve/revoke, removal, group isolation, no plaintext storage, restart, nonmember issue rejection and malformed code rejection.

# Integration Tests

Native membership lookup passed separately. Badge module not connected yet.

# Hardware Tests

Physical badge not issued.

# User Acceptance Tests

Pending first badge/session test.

# Definition of Done

Registry foundation tested; full badge workflow remains incomplete.
