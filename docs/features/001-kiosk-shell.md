# Feature

Kiosk shell prototype

# Problem

Regular inventory navigation is cumbersome on a small touchscreen.

# User Goal

Reach common tasks directly and locate equipment quickly.

# User Experience

Six large task buttons and a smaller Admin entry. Home navigation; live search/browse and native item summaries.

# Current Homebox Behavior

Homebox provides native item lists, metadata and locations.

# Proposed Behavior

Read-only companion navigation using supported native API. Operational buttons remain explicit previews.

# Scope

Home, navigation, demo session banner, connection feedback, search/browse, item details.

# Out of Scope

Transactions, production login/permissions, scanner routing, inactivity policy, boot deployment.

# User Decisions

DEC 003 companion boundary; DEC 005 six-button home. Shell review pending.

# Data Model

Native Homebox entities only; no extra inventory database.

# API Changes

None to Homebox. Local GET /api/inventory returns demo native items.

# Homebox Integration

Server-side synthetic account login and paginated entity reads. Credentials never sent to browser.

# UI Changes

Local HTML/CSS/JS fitted to 800 by 480.

# Hardware Dependencies

Pi Chromium and touchscreen; camera/printer not used by shell yet.

# Security Considerations

Loopback diagnostic only. Admin entry is not an authorization boundary. Production authentication undecided.

# Offline Considerations

No CDN, fonts or external runtime assets.

# Failure Modes

Homebox unavailable produces 503 and visible retry status. Empty search shows a clear message.

# Logging / Diagnostics

Local runtime log; HTTP request logging disabled to avoid credential disclosure.

# Implementation Steps

Implement approved layout, native read-only views, verify API/browser output, inspect 800 by 480 screenshot, user review.

# Unit Tests

No separate tests for disposable static layout.

# Integration Tests

Live endpoint returned eight items including six demo assets. Chromium DOM reports connection to eight assets.

# Hardware Tests

Screenshot visually inspected at display resolution; opened on physical Pi browser.

# User Acceptance Tests

Click home tasks, search/browse, select an item and return Home; feedback requested.

# Upgrade / Migration Considerations

No database migration or upstream change. Prototype server can be replaced after runtime selection.

# Rollback Plan

Stop only prototype server; restore previous project Git commit if needed. Homebox data unchanged by shell.

# Definition of Done

Prototype rendered and live reads verified; user layout review pending. Operational shell requirements remain progressive follow-up work.
