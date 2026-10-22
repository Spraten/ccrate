# C-Crate Search Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Return useful item matches quickly in the manager inventory and member checkout/return searches.

**Architecture:** Pass the query to Homebox’s existing filtered entity API instead of downloading the whole collection for each search. Bound kiosk results, debounce input, discard stale responses, and retain C-Crate enrichment only for the matching records.

**Tech Stack:** Vue/Nuxt source built by `deploy/build-homebox-ui.py`, plain JavaScript, Python 3.13 companion, Homebox API, pytest and Node tests.

**Spec:** `TODO.md` sections “Touchscreen check-in and checkout”, “Item and location screens”, and “Shared visual direction”.

## Global Constraints

- Homebox remains the native inventory authority; preserve filters, group expansion, assigned-ID lookup, and native pagination.
- Do not expose credentials or badge codes, add dependencies, or query an operational instance in tests.
- Search results remain suggestions only; physical code scan is still required before checkout or return confirmation.
- Keep manager search styling native to Homebox and kiosk search styling on the shared theme contract from `2026-10-21-ccrate-shared-theme-compatibility.md`. Both use the approved photo/name/status hierarchy without introducing another palette.

## Review Focus

- Query with zero matches clears results and reports no matches (`test_empty_kiosk_search_has_no_matches_state`).
- Rapidly changing text ignores an older response (`test_stale_search_response_is_ignored`).
- One-character query performs no full inventory request (`test_short_query_does_not_load_inventory`).
- Assigned ID and custom-field matching still resolve after narrowing (`test_inventory_search_projection_matches_custom_fields_on_projected_records`; existing assigned-ID tests).
- Offline Homebox returns an actionable state without replacing complete current results with partial data (`test_search_failure_keeps_last_complete_results`).

---

### Task 1: Add bounded query search to the touchscreen companion

**Files:**
- Modify: `deploy/kiosk-server.py`
- Modify: `kiosk/checkout-ui.js`, `kiosk/return-ui.js`
- Test: new `tests/test_kiosk_inventory_search.py`, `tests/test_touchscreen_checkout.py`, `tests/test_touchscreen_return.py`

**Interfaces:**
- Consumes: `GET /api/inventory?q=<text>`.
- Produces: `inventory(locations=False, query='') -> list[dict]`; with non-empty query, pass `q`, `page=1`, `pageSize=20`, and `includeArchived=false` to the native entity endpoint and return only the first 20 matches. Empty query preserves the current complete inventory behavior for existing callers.

- [ ] **Step 1: Write failing tests** `test_inventory_search_forwards_query_and_caps_page_size` and `test_inventory_search_escapes_query_and_preserves_location_route` in `tests/test_kiosk_inventory_search.py`; add `test_empty_kiosk_search_has_no_matches_state`, `test_stale_search_response_is_ignored`, and `test_short_query_does_not_load_inventory` to `tests/test_touchscreen_search.browser.mjs`.
- [ ] **Step 2: Run** `pytest tests/test_kiosk_inventory_search.py -q` and `node --test tests/test_touchscreen_search.browser.mjs`; expected: new query/UI assertions fail.
- [ ] **Step 3: Parse `q` in the `/api/inventory` handler and forward it through `inventory(..., query=...)`.** Client searches start at two characters, debounce 200 ms, show a loading/no-results state, and ignore stale requests. The selected candidate still requires a matching physical scan.
- [ ] **Step 4: Run** `pytest tests/test_kiosk_inventory_search.py tests/test_touchscreen_checkout.py tests/test_touchscreen_return.py -q` and `node --test tests/test_touchscreen_search.browser.mjs`; expected: PASS and no repeated full collection request for typed queries.
- [ ] **Step 5: Commit** `perf: query inventory while searching in the kiosk`.

### Task 2: Remove redundant full-collection loading from manager search

**Files:**
- Modify: `deploy/build-homebox-ui.py` (`grouped_inventory_frontend`)
- Modify: `homebox-ui/overlay/lib/child-item-groups.js`
- Test: `tests/test_equipment_inventory_builder.py`, `tests/equipment_inventory.test.mjs`, `tests/test_equipment_search_builder.py`

**Interfaces:**
- Consumes: the existing Homebox `api.items.getAll({ q, page, pageSize, ...filters })` response and current assigned-ID/status enrichment helpers.
- Produces: one complete filtered result set per query; never performs both an unfiltered full scan and a second full q-filtered scan for a non-empty query. Preserve exact assigned-ID resolution and grouped peer behavior for records returned by Homebox.

- [ ] **Step 1: Add failing projection and builder tests** asserting a non-empty query makes only q-filtered paged requests and retains grouping for returned records.
- [ ] **Step 2: Run** `pytest tests/test_equipment_inventory_builder.py tests/test_equipment_search_builder.py -q` and `node --test tests/equipment_inventory.test.mjs`; expected: new request-count assertions fail.
- [ ] **Step 3: Change the build transform’s `search()` flow** to load unfiltered pages only when query is empty; otherwise load q-filtered pages once. Retain revision cancellation, status enrichment, assigned-ID exact resolution, and custom-field matching on projected rows.
- [ ] **Step 4: Run** `pytest tests/test_equipment_inventory_builder.py tests/test_equipment_search_builder.py -q` and `node --test tests/equipment_inventory.test.mjs`; expected: PASS with complete results and no duplicate collection scan.
- [ ] **Step 5: Commit** `perf: avoid duplicate full inventory scans during search`.
