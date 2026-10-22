# C-Crate Touchscreen Transaction Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make badge scanning, item scanning, review, cancel, and recovery clear and reliable on the member touchscreen.

**Architecture:** Keep the existing companion routes and separate checkout, return, and shell scripts. Add small UI state transitions around the current session and request identity; retain the server as the authority for confirmation and recovery. Apply the shared theme compatibility prerequisite before restyling kiosk screens; use the same Homebox/C-Crate theme tokens and identifiers while keeping kiosk-specific touch layouts.

**Tech Stack:** Python 3.13 HTTP companion, plain browser JavaScript, HTML/CSS, pytest fixtures, Node-based browser harnesses.

**Spec:** `TODO.md` sections “Touchscreen check-in and checkout” and “Shared visual direction”; prerequisite `2026-10-21-ccrate-shared-theme-compatibility.md`; existing `docs/superpowers/specs/2026-10-20-touchscreen-check-in-out-design.md`.

## Global Constraints

- Make the smallest complete change; add no dependencies.
- Homebox remains the inventory and account authority; preserve badge session and native member checks.
- Never automatically repeat an uncertain checkout or return; keep its request key and use status recovery.
- Never run mutation checks against the operational Homebox instance or deploy/restart the service as part of implementation.
- Use 48 px minimum touchscreen controls, visible keyboard focus, and readable status text. Use the shared theme contract and theme IDs; do not add a separate kiosk palette or typography system.

## Review Focus

- NETUM keyboard-wedge scan with an Enter suffix submits exactly once (`test_badge_scan_focus_enter_submits_once`).
- Scanner without an Enter suffix remains usable through the visible scan button (`test_badge_scan_without_suffix_has_manual_submit`).
- Invalid or revoked badge shows a correction and does not start an authenticated session (`test_badge_scan_rejection_keeps_session_unauthenticated`).
- Cancel during a pending lookup cannot leak the old response into the next badge session (`test_cancel_invalidates_pending_scan_response`).
- Uncertain confirmation offers status recovery and cannot be confirmed or cancelled into a duplicate transaction (`test_uncertain_checkout_cancel_keeps_status_only_recovery`, corresponding return test).
- Kiosk styles use the shared theme stylesheet and preserve readable surfaces in light and dark themes (`test_kiosk_theme_ui`).

---

### Task 1: Make badge scanning ready and observable

**Files:**
- Modify: `kiosk/touchscreen.html`
- Modify: `kiosk/touchscreen.js`
- Modify: `kiosk/touchscreen.css`
- Test: `tests/test_touchscreen_shell.py`

**Interfaces:**
- Consumes: existing `POST /scan` and `GET /api/session` responses.
- Produces: after **Check out** or **Return**, reveal the member badge field and focus it; preserve the visible **Scan badge** button and status area.

- [ ] **Step 1: Write failing scanner-focus tests** for `test_badge_scan_focus_enter_submits_once`, `test_badge_scan_without_suffix_has_manual_submit`, and `test_badge_scan_rejection_keeps_session_unauthenticated` in the shell browser harness.
- [ ] **Step 2: Run the focused tests**

Run: `pytest tests/test_touchscreen_shell.py -q`
Expected: the new cases fail because the badge input is not focused on flow entry.

- [ ] **Step 3: Focus the badge input after revealing the flow**, retain Enter form submission, expose “Checking badge…” and the server rejection text, and keep the manual button large enough for touch.
- [ ] **Step 4: Run the focused tests**

Run: `pytest tests/test_touchscreen_shell.py -q`
Expected: PASS, with one `/scan` request per Enter and no authenticated session after rejection.

- [ ] **Step 5: Commit** `fix: focus badge scanner in touchscreen flow`.

### Task 2: Add safe cancel and back transitions

**Files:**
- Modify: `kiosk/touchscreen.html`, `kiosk/touchscreen.js`, `kiosk/touchscreen.css`
- Modify: `kiosk/checkout-ui.js`, `kiosk/return-ui.js`
- Test: `tests/test_touchscreen_shell.py`, `tests/test_touchscreen_checkout.py`, `tests/test_touchscreen_return.py`

**Interfaces:**
- Consumes: `/session/end`, current generation and instance values, each flow’s existing draft and operation key.
- Produces: `cancelFlow()` ends the captured badge session, clears only the unconfirmed draft, and returns home. Review’s **Back to items** keeps the current draft. Receipts remain visible until **Done**.

- [ ] **Step 1: Add failing cases** `test_cancel_invalidates_pending_scan_response`, `test_cancel_ends_only_captured_badge_session_and_clears_draft`, and `test_review_back_preserves_scanned_items` to existing JavaScript harnesses.
- [ ] **Step 2: Run** `pytest tests/test_touchscreen_shell.py tests/test_touchscreen_checkout.py tests/test_touchscreen_return.py -q`; expected: new cases fail.
- [ ] **Step 3: Implement explicit Cancel on collection and Back on review.** Disable draft cancellation while a confirmation is sending or uncertain; show **Check saved result** until status resolves. Do not call a second confirmation when leaving a screen.
- [ ] **Step 4: Run** `pytest tests/test_touchscreen_shell.py tests/test_touchscreen_checkout.py tests/test_touchscreen_return.py -q`; expected: PASS, old-session replies stay ignored, and uncertain requests remain status-only.
- [ ] **Step 5: Commit** `feat: add safe cancel and review navigation to kiosk`.

### Task 3: Add compact transaction previews and shared styling

**Files:**
- Modify: `deploy/kiosk-server.py`
- Modify: `kiosk/checkout-ui.js`, `kiosk/return-ui.js`, `kiosk/touchscreen.css`
- Test: `tests/test_touchscreen_checkout.py`, `tests/test_touchscreen_return.py`, new `tests/test_kiosk_item_thumbnail.py`

**Interfaces:**
- Consumes: existing `imageId` and `thumbnailId` item fields and authenticated badge session.
- Produces: `GET /api/item-thumbnail?id=<entity UUID>` returns that entity’s thumbnail (falling back to its full image) only for a current member session; checkout and return render image, name, status, and return location where available.

- [ ] **Step 1: Add failing fixture tests** for thumbnail access without a badge (401), wrong/missing item image (no image response), and a valid session returning the item’s thumbnail bytes; add UI assertions for photo fallback, item name, availability, condition and return location.
- [ ] **Step 2: Run** `pytest tests/test_kiosk_item_thumbnail.py tests/test_touchscreen_checkout.py tests/test_touchscreen_return.py -q`; expected: new route/UI cases fail.
- [ ] **Step 3: Add the session-checked thumbnail route using the existing native attachment endpoint; render an accessible “No photo” fallback.** Load the stable shared theme stylesheet from the compatibility plan and style surfaces, controls, text, focus, and status through its semantic variables. Keep 48 px touch targets and the existing scanner and recovery states. Do not hard-code a second palette or typography system.
- [ ] **Step 4: Run** `pytest tests/test_kiosk_item_thumbnail.py tests/test_touchscreen_checkout.py tests/test_touchscreen_return.py -q`; expected: PASS, no native token reaches the browser, and confirmation/recovery behavior remains intact.
- [ ] **Step 5: Commit** `feat: show equipment previews in touchscreen transactions`.
