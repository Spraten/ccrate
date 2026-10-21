# Touchscreen Check-in and Check-out Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore a touch-first checkout and return window in the existing C-Crate companion, with badge attribution, scan-verified batches, safe receipts, and manager-only administration.

**Architecture:** Serve a static touchscreen page and its assets from the existing companion on port 17749. The page uses the existing badge/session, scan, checkout, return, availability, and operation-status endpoints; it does not own transaction rules. Keep manager operations on authenticated `/workshop-api` routes and close any direct legacy admin route that bypasses that boundary.

**Tech Stack:** Existing Python `deploy/kiosk-server.py`, static HTML/CSS/JavaScript under `kiosk/`, existing Homebox companion APIs and browser verification tooling. No new service, runtime, build step, or product dependency.

**Spec:** `docs/superpowers/specs/2026-10-20-touchscreen-check-in-out-design.md`

## Global Constraints

- Keep the work in the current C-Crate repository and companion server; add no second service or version.
- The kiosk home presents only Check out and Return; both flows start with a member badge.
- Search may locate equipment, but confirmation requires a physical scan for each item.
- Checkout and return use a single reviewed batch confirmation and retain existing recovery behavior.
- The target display is 800 × 480 landscape and must remain usable at other viewport sizes.
- Do not expose manager actions on the kiosk; direct manager mutations require the authenticated manager boundary.
- Do not add a product dependency or require rebuilding the app to change the static touchscreen page.

## Review Focus

- Search-selected but unscanned items must remain ineligible for confirmation; Task 3 and Task 4 add UI contract coverage.
- A badge/session generation change or late response must not restore an old draft or confirm under a new member; Task 2 covers ownership and cleanup.
- Unavailable, broken, kit-changed, or otherwise blocked equipment must show a clear reason and prevent confirmation; Tasks 3 and 4 cover blockers and refresh behavior.
- An uncertain confirmation must preserve its request key and offer status recovery without resubmitting; Tasks 3 and 4 cover this explicitly.
- Long item names, per-item notes, and 50-item batches must remain navigable at 800 × 480; Tasks 2–4 cover compact layout and list behavior.
- Anonymous requests must not gain manager mutations through legacy routes; Task 1 verifies the manager boundary and preserves authenticated manager operations.

---

### Task 1: Close direct legacy manager access

**Files:**
- Modify: `deploy/kiosk-server.py:OPEN_ADMIN and manager-only route guards`
- Modify: `ops/desktop_api.py` only for manager routes proven to lack an authenticated equivalent
- Modify: manager UI route callers under `homebox-ui/overlay/` only where they still call a legacy route
- Test: `tests/test_kiosk_admin_access.py` (new)
- Test: `tests/test_desktop_api.py` (extend existing manager and non-manager cases)

**Interfaces:**
- Consumes: `ops/desktop_api.py:authenticate()` and its `manager` context; configured manager membership from `work/ops/desktop-managers.json`.
- Produces: all manager mutations remain available only through authenticated manager context; direct legacy manager endpoints return an authorization error.

- [ ] **Step 1: Add access-boundary tests**

  Cover an anonymous request and a signed-in non-manager against representative
  legacy manager routes. Assert rejection. Cover a configured manager through
  the corresponding `/workshop-api` route and assert it remains available.

- [ ] **Step 2: Run the focused access tests and confirm they fail on the open routes**

  Run: `python3 -m unittest discover -s tests -p 'test_kiosk_admin_access.py' -v`
  Run: `python3 -m unittest discover -s tests -p 'test_desktop_api.py' -v`
  Expected: the new direct-route assertions fail while the existing authenticated
  manager behavior passes.

- [ ] **Step 3: Inventory and migrate required manager callers**

  Search `homebox-ui/overlay/` and companion static callers for each direct
  route currently guarded by `OPEN_ADMIN`. Route any required manager action
  through the matching authenticated `/workshop-api` endpoint. Keep terminal
  member checkout and return endpoints outside the manager gate.

- [ ] **Step 4: Disable open legacy admin mode and satisfy the access tests**

  Set the legacy admin mode closed by default (or remove it where no legitimate
  caller remains). Ensure each needed manager operation checks the authenticated
  manager context; an absent or invalid manager configuration must deny access.

- [ ] **Step 5: Run focused tests and inspect the route access matrix**

  Run: `python3 -m unittest discover -s tests -p 'test_kiosk_admin_access.py' -v`
  Run: `python3 -m unittest discover -s tests -p 'test_desktop_api.py' -v`
  Expected: direct anonymous/non-manager mutations are rejected and manager UI
  operations still pass through `/workshop-api`.

---

### Task 2: Serve the touchscreen shell and shared session flow

**Files:**
- Create: `kiosk/touchscreen.html`
- Create: `kiosk/touchscreen.css`
- Create: `kiosk/touchscreen.js`
- Modify: `deploy/kiosk-server.py:Handler.do_GET static route mapping`
- Test: `tests/test_kiosk_static_assets.py`
- Test: `tests/test_touchscreen_shell.py` (new)

**Interfaces:**
- Consumes: existing `/api/session`, `/api/inventory`, `/scan`, `/session/activity`, and `/session/end` routes. Send the page's stable UUID as `X-Homebox-Client` on every terminal API request.
- Produces: `/touchscreen` and its static assets from the repository-owned `kiosk/` directory; a session-aware home screen with Check out and Return entry points.

- [ ] **Step 1: Define the static route contract**

  Extend the existing GET-route fixture to assert that `/touchscreen`,
  `/touchscreen.css`, and `/touchscreen.js` are served from `kiosk/`, while
  existing companion API and editor routes keep their current behavior.

- [ ] **Step 2: Run the focused static-route test and confirm the new route fails**

  Run: `python3 -m unittest discover -s tests -p 'test_kiosk_static_assets.py' -v`
  Expected: `/touchscreen` is currently unavailable; existing API route checks
  remain unchanged.

- [ ] **Step 3: Add the touch-first home and session shell**

  Use a quiet white/canvas/green palette drawn from
  `homebox-ui/overlay/assets/css/ccrate.css`, system sans-serif text, minimum
  44 px controls, visible focus, and left-aligned content. Show only Check out
  and Return as primary actions. Keep the active member/session visible during
  a flow.

- [ ] **Step 4: Add session ownership and timeout handling**

  Give the page a client UUID, read the current session from `/api/session`,
  and clear drafts when the badge generation or session instance changes. Use
  the existing 120-second inactivity behavior; explicit Done ends the matching
  generation and returns home. Ignore stale asynchronous responses.

- [ ] **Step 5: Serve the shell from the existing companion and run focused tests**

  Run: `python3 -m unittest discover -s tests -p 'test_kiosk_static_assets.py' -v`
  Run: `python3 -m unittest discover -s tests -p 'test_touchscreen_shell.py' -v`
  Expected: touchscreen assets load, only the agreed primary actions appear,
  session changes clear drafts, and the existing companion API routes remain
  available.

---

### Task 3: Implement scan-verified checkout batches

**Files:**
- Create: `kiosk/checkout-ui.js`
- Modify: `kiosk/touchscreen.html`
- Modify: `kiosk/touchscreen.js`
- Modify: `tests/test_checkout_cart_ui.py` to read the new `touchscreen.html` flow
- Test: `tests/test_touchscreen_checkout.py` (new)

**Interfaces:**
- Consumes: Task 2 session shell; `/scan`, `/api/kit`, `/checkout/availability`, `/checkout/cart`, `/checkout/confirm`, and `/operation/status`.
- Produces: `beginCheckout()`, `addCheckoutItem()`, `reviewCheckout()`, `confirmCheckout()`, and `recoverCheckout()` flow functions. A scanned selection carries item ID, scan evidence, optional item note, kit version where applicable, and the current session generation/instance. For a kit, expand the manifest, show its parts, require scans for every component, and submit a reviewed root selection with the verified manifest version.

- [ ] **Step 1: Add checkout flow contract tests**

  Cover badge requirement, physical-scan requirement after search, duplicate
  rejection, per-item notes, unavailable-item blockers, 50-item limit,
  one-confirm behavior, and uncertain-outcome recovery without auto-retry.

- [ ] **Step 2: Run the focused checkout tests and confirm missing behavior fails**

  Run: `python3 -m unittest discover -s tests -p 'test_checkout_cart_ui.py' -v`
  Run: `python3 -m unittest discover -s tests -p 'test_touchscreen_checkout.py' -v`
  Expected: the new touchscreen checkout contract fails before implementation.

- [ ] **Step 3: Implement item lookup and physical scan verification**

  Search the current collection's inventory by name/ID. Treat a search result
  as a candidate only; require `/scan` to record a valid physical code before
  adding it to the confirmable batch. If the scanned item is a kit, fetch its
  `/api/kit` manifest, show the expected components, and require a scan for
  each component before the kit can be confirmed. Reject duplicate IDs and
  stale scan responses.

- [ ] **Step 4: Implement checkout review and confirmation**

  Show each selected item, availability/blocker, and its own optional note.
  Keep the batch at 50 or fewer distinct assets. Require explicit review and
  confirmation; submit the current request key and exact session context once.

- [ ] **Step 5: Implement receipt and uncertain-outcome recovery**

  Keep completed receipts visible until Done. For timeout/network uncertainty,
  preserve the request key, offer a saved-result status check, and do not issue
  a second confirmation automatically.

- [ ] **Step 6: Run the focused checkout tests**

  Run: `python3 -m unittest discover -s tests -p 'test_checkout_cart_ui.py' -v`
  Run: `python3 -m unittest discover -s tests -p 'test_touchscreen_checkout.py' -v`
  Expected: all checkout contract cases pass, including stale-session, blocked
  item, item-note, and recovery cases.

---

### Task 4: Implement scan-verified return batches

**Files:**
- Create: `kiosk/return-ui.js`
- Modify: `deploy/kiosk-server.py` to add a badge-bound, selected-item return-availability route
- Modify: `kiosk/touchscreen.html`
- Modify: `kiosk/touchscreen.js`
- Modify: `tests/test_return_scan_contract.py`
- Modify: `tests/test_kiosk_api_status.py`
- Test: `tests/test_touchscreen_return.py` (new)

**Interfaces:**
- Consumes: Task 2 session shell; `/scan`, `/api/entity`, `/api/kit`, `GET /return/availability?ids=<comma-separated item IDs>`, `/return/confirm`, and `/operation/status`.
- Produces: `GET /return/availability?ids=<comma-separated item IDs>` requires the current badge session and accepts 1–50 unique IDs. It returns `{items:[{id, eligible, reason, condition, location:{id,name}|null}]}` for only those IDs, with `reason` null when eligible and a plain-language reason when not eligible. It never returns borrower names or a full custody list. It permits a currently checked-out item to be returned by any identified member; `/return/confirm` remains authoritative. The task also produces `beginReturn()`, `addReturnItem()`, `reviewReturn()`, `confirmReturn()`, and `recoverReturn()` flow functions. Each target carries physical scan evidence, optional per-item return note, changed condition/note when applicable, and current badge generation/instance.

- [ ] **Step 1: Add return flow contract tests**

  Cover badge requirement, physical scan requirement after search, duplicate
  rejection, scoped return availability with no borrower names, default
  location/condition, changed-condition issue note, per-item return notes,
  batch limit, single confirmation, and uncertain-result recovery without
  using anonymous return or automatic retry.

- [ ] **Step 2: Run the focused return tests and confirm the missing UI behavior fails**

  Run: `python3 -m unittest discover -s tests -p 'test_return_scan_contract.py' -v`
  Run: `python3 -m unittest discover -s tests -p 'test_kiosk_api_status.py' -v`
  Run: `python3 -m unittest discover -s tests -p 'test_touchscreen_return.py' -v`
  Expected: the new touchscreen return contract fails before implementation.

- [ ] **Step 3: Implement return lookup and review**

  Use the new badge-bound return-availability route for the scanned/selected
  item IDs. Do not use `/api/custody`, which exposes every borrower's name.
  Show the recorded condition and assigned return location. If the selected
  item is a kit, fetch `/api/kit`, show its manifest, and require physical
  scans for all components before confirming the kit return. Allow an issue
  condition and note, plus an independent optional return note. Keep all
  targets editable until the review is confirmed.

- [ ] **Step 4: Implement return confirmation and recovery**

  Require a scanned member and exact generation/instance. Submit one reviewed
  batch. Show the completed receipt until Done; if the result is uncertain,
  preserve its request key and query operation status instead of retrying.

- [ ] **Step 5: Run the focused return tests**

  Run: `python3 -m unittest discover -s tests -p 'test_return_scan_contract.py' -v`
  Run: `python3 -m unittest discover -s tests -p 'test_kiosk_api_status.py' -v`
  Run: `python3 -m unittest discover -s tests -p 'test_touchscreen_return.py' -v`
  Expected: all return flow cases pass with member attribution, location and
  condition defaults, item notes, and no anonymous-return path.

---

### Task 5: Check the complete shared-screen experience

**Files:**
- Modify: `deploy/verify-checkout-redesign.py`
- Modify: `deploy/verify-workflow-navigation.py` only if the touchscreen route changes shared navigation behavior
- Modify: `tests/test_kiosk_static_assets.py` and focused touchscreen tests as needed

**Interfaces:**
- Consumes: the full terminal page, the hardened manager boundary, and both transaction flows.
- Produces: evidence that the shared screen works at the target size and existing authenticated manager workflows still work.

- [ ] **Step 1: Update browser coverage for the implemented page**

  Exercise the badge → scan/search → review → confirm → receipt flows using
  synthetic data and intercepted APIs. Assert no horizontal scrolling and
  primary controls at least 44 px high at 800 × 480.

- [ ] **Step 2: Cover manager/member separation**

  Assert the touchscreen exposes no manager actions, anonymous and non-manager
  requests cannot mutate manager data, and an authenticated configured manager
  can still use the existing manager UI.

- [ ] **Step 3: Run focused checks and inspect the resulting diff**

  Run: `python3 -m unittest discover -s tests -p 'test_kiosk_static_assets.py' -v`
  Run: `python3 -m unittest discover -s tests -p 'test_kiosk_admin_access.py' -v`
  Run: `python3 -m unittest discover -s tests -p 'test_touchscreen_shell.py' -v`
  Run: `python3 -m unittest discover -s tests -p 'test_checkout_cart_ui.py' -v`
  Run: `python3 -m unittest discover -s tests -p 'test_touchscreen_checkout.py' -v`
  Run: `python3 -m unittest discover -s tests -p 'test_return_scan_contract.py' -v`
  Run: `python3 -m unittest discover -s tests -p 'test_kiosk_api_status.py' -v`
  Run: `python3 -m unittest discover -s tests -p 'test_touchscreen_return.py' -v`
  Run: `python3 deploy/verify-checkout-redesign.py`
  Expected: focused tests and browser flow pass; no operational Homebox account
  or inventory mutations are used.

- [ ] **Step 4: Capture an 800 × 480 screenshot and review it against the spec**

  Check action visibility, long names, per-item notes, status/blocker legibility,
  and no horizontal scroll. Correct any issue before considering the work done.

---

## Execution notes

- Inspect the actual active static asset root and direct-route consumers before
  changing `OPEN_ADMIN`; the source currently has conflicting old and new UI
  expectations. Keep a single repository-owned source and do not create a
  worktree or duplicate service.
- Use only synthetic members/items and intercepted APIs for browser verification.
  Do not run operational scripts that create Homebox items or print labels.
- Physical scanner and touchscreen acceptance should happen on the Pi after
  the page and route behavior are ready; no service restart or deployment is
  included in this plan.
