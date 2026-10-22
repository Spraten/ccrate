# C-Crate Timestamped Item Notes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Present existing item notes as a readable, timestamped history and preserve who added each note when known.

**Architecture:** Reuse the current append-only C-Crate activity journal and native maintenance records. Normalize the existing checkout, return, and standalone item-note sources in `item-activity-notes.js`; update item list previews and the item detail log without inventing dates/authors or duplicating storage.

**Tech Stack:** JavaScript ES modules, Vue/Nuxt overlay, Python journal/API, existing pytest and Node tests.

**Spec:** `TODO.md` section “Item notes”; existing `docs/superpowers/specs/2026-10-20-touchscreen-check-in-out-design.md`.

## Global Constraints

- Preserve append-only activity records, author/member attribution, request keys, and recovery semantics.
- Never post a second note when the first save outcome is uncertain; use the existing status/recovery flow.
- Reuse known `confirmed_at` or `created_at`; render missing historical times as unavailable instead of inventing them.
- Do not migrate or rewrite native maintenance history as part of this UI change.
- Use Homebox native text, muted text, separators, buttons, and active theme tokens; do not add note-specific colors or type styles.

## Review Focus

- Confirmed note uses `confirmed_at`, with `created_at` fallback (`test_recent_item_notes_use_confirmed_time_then_created_time`).
- Edited native maintenance text remains visibly attributed as uncertain (`test_item_note_display_keeps_edited_attribution_unknown`).
- Legacy return/checkout notes retain their member and time (`test_legacy_transaction_notes_keep_available_attribution`).
- Missing date/author displays an explicit unavailable/unknown value (`test_note_history_does_not_fabricate_legacy_metadata`).
- Double submission and lost reply remain idempotent/status-only (`test_double_confirm_sends_one_note_and_success_ends_expected_session`, `test_lost_reply_checks_status_once_then_saved_cleanup_failure_stays_saved`).

---

### Task 1: Normalize existing note events for consistent display

**Files:**
- Modify: `homebox-ui/overlay/lib/item-activity-notes.js`
- Test: new `tests/item_activity_notes.test.mjs`

**Interfaces:**
- Consumes: history rows containing `checkout_notes`, `return_notes`, or `action === 'add_note'` and their existing timestamps/attribution.
- Produces: `recentItemNotes(rows, itemId, limit)` returns events with `{ text, author, created_at, kind }`, sorted newest first; missing time/author remains `null` and does not remove the note.

- [ ] **Step 1: Add failing Node tests** `test_recent_item_notes_use_confirmed_time_then_created_time`, `test_legacy_transaction_notes_keep_available_attribution`, `test_note_history_does_not_fabricate_legacy_metadata`, plus sorting, item scoping, and edited note attribution cases.
- [ ] **Step 2: Run** `node --test tests/item_activity_notes.test.mjs`; expected: missing-time/source cases fail.
- [ ] **Step 3: Normalize without changing source records.** Use `confirmed_at || created_at` for completed standalone notes and preserve transaction note timestamps/authors.
- [ ] **Step 4: Run** `node --test tests/item_activity_notes.test.mjs` and `node --test tests/equipment_inventory.test.mjs`; expected: PASS.
- [ ] **Step 5: Commit** `feat: normalize timestamped item note history`.

### Task 2: Show compact note history on inventory and item detail screens

**Files:**
- Modify: `homebox-ui/overlay/components/InventoryGroups.vue`
- Modify: `homebox-ui/overlay/components/Workshop/ItemLog.vue`
- Modify: `deploy/build-homebox-ui.py` only if the detail log insertion point changes.
- Test: `tests/equipment_inventory.test.mjs`, `tests/test_item_notes_browser.py`, new `tests/item_note_display.browser.mjs`

**Interfaces:**
- Consumes: normalized note events from Task 1 and the existing `history?entity=<id>` route.
- Produces: inventory rows show only the newest note’s text, local timestamp, and author when known; item detail has an expandable newest-first notes section with **Add note** revealing the editor. Existing all-activity filters remain available.

- [ ] **Step 1: Add failing display tests** `test_item_note_history_is_newest_first_with_local_time`, `test_item_note_history_marks_missing_time_unavailable`, `test_item_note_editor_opens_only_after_add_note`, and `test_item_note_display_keeps_edited_attribution_unknown`; assert existing activity filters remain available.
- [ ] **Step 2: Run** `node --test tests/item_note_display.browser.mjs` and `pytest tests/test_item_notes_browser.py -q`; expected: new display assertions fail while security/recovery assertions pass.
- [ ] **Step 3: Update the list preview and item log presentation** using existing activity data and shared Homebox component styles/theme tokens. Do not alter `/notes/confirm`, native maintenance records, or ledger schema.
- [ ] **Step 4: Run** `node --test tests/item_note_display.browser.mjs tests/equipment_inventory.test.mjs` and `pytest tests/test_item_notes_browser.py -q`; expected: PASS, including stale session and duplicate-confirm protections.
- [ ] **Step 5: Commit** `ui: display item notes with their timestamps`.
