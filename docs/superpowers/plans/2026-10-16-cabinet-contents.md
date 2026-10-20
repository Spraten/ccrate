# Cabinet Contents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let staff open a cabinet or storage location and see its immediate bins and the items in those bins together, without opening each bin separately.

**Architecture:** Extend the existing `ChildContents.vue` native location preview, which is injected by the UI builder and currently loads one expanded child at a time. For a cabinet page, query direct items for all immediate child locations in one parent-filtered paginated sequence and group the results beneath each bin; keep deeper descendants collapsed and lazy-loaded. Preserve the native Homebox parent tree as the source of truth.

**Tech Stack:** Existing Vue 3 Homebox overlay, Homebox `ItemsApi.getAll({ parentIds })`, Python builder contract test, existing Node unit/fixture test conventions where a pure grouping helper is useful.

**Spec:** `docs/research/2026-10-16-inventory-browsing-and-grouping.md`; board decisions are recorded in `docs/reviews/2026-10-16-inventory-camera-workflows.md`.

## Global Constraints

- “Make the smallest complete change. Reuse existing Homebox APIs, UI components and helpers. Do not add dependencies or unrelated features.”
- “Homebox is the inventory and account authority. Preserve native identities, metadata, access rules and history.”
- “Never run demo-creating or mutation checks against an operational Homebox instance.”
- “Do not restart or deploy services, print physical output, or change operational data unless the user explicitly authorizes that action.”
- The parent location tree and each item’s immediate parent remain authoritative; browsing must not change storage assignment.
- Keep Playwright and Docker out of the supported workflow per the core-only plan; use focused unit/fixture checks and manual browser/device review.
- Include archived records if the native API returns them for the parent filter; label them Archived so the view reflects physical placement without implying checkout eligibility.
- Show the whole batch as partial if pagination fails; never present incomplete results as a complete cabinet count.

## Review Focus

- Cabinet with 20+ immediate bins: load direct items with a bounded request count and retain scroll/search usability.
- Empty bin: show the bin and an explicit empty message.
- Item with a missing parent summary or stale hierarchy: do not silently place it under the wrong bin.
- Failed/partial API request: show a cabinet-level error or partial-data status and allow retry without discarding returned item rows. Because items are fetched in one parent-filtered batch, do not claim a particular bin failed unless the API response identifies it.
- Deep or cyclic hierarchy: lazy load deeper levels and prevent duplicate rendering or recursion loops.

---

## File map

- `homebox-ui/overlay/components/Location/ChildContents.vue`: fetch direct items for all immediate child bins as one paginated parent-filtered query, display them under each bin, and recurse only on demand.
- `deploy/build-homebox-ui.py:399-415`: retain the existing component injection contract; change only if the generated root needs a bounded default-expand prop.
- `tests/test_location_child_preview.py`: extend the source/builder contract checks for batch loading, default immediate-bin visibility, and accessible expand/collapse controls.
- `homebox-ui/overlay/lib/location-contents.js` and `tests/location_contents.test.mjs` (create only if extracting pure item-to-parent grouping materially simplifies the component): deterministic grouping of API items by direct `parent.id`.

## Task 1: Batch the immediate bin contents

**Files:**
- Modify: `homebox-ui/overlay/components/Location/ChildContents.vue`
- Modify: `deploy/build-homebox-ui.py:399-415` only if a root-only prop is needed
- Test: `tests/test_location_child_preview.py`
- Test: `tests/location_contents.test.mjs` only if a pure helper is extracted

**Interfaces:**
- Consumes: The `locations: LocationNode[]` children already passed by the generated location page; each item’s native `parent.id`.
- Produces: Root preview displays all immediate child locations and their direct item lists by default. Query with `getAll({ parentIds: immediateChildIds, page, pageSize: 100, includeArchived: true })`, advancing pages until `total` is reached. A typical cabinet fits in one request; larger contents paginate. Deeper child locations remain collapsed and use the existing on-demand detail read.

- [ ] **Step 1: Add contract assertions** to `tests/test_location_child_preview.py` that the generated location page still mounts `ChildContents`, immediate children default open, and the component batches direct items using the full immediate child ID list.
- [ ] **Step 2: Run `python3 -m unittest tests.test_location_child_preview -v`.** Expected: new assertions fail against the current one-bin-at-a-time loader.
- [ ] **Step 3: Implement batch state** in `ChildContents.vue`; request pages until the API's `total` is reached, map returned entities by `item.parent.id`, and preserve one location row even when its item list is empty. Show a batch-level loading/error/empty state. If a later page fails, retain returned rows but mark the entire result partial and allow retry; do not label individual bins failed without evidence.
- [ ] **Step 4: Add “Collapse all bins” and “Expand bins” controls** with an accessible expanded state. Expansion changes presentation; the already-fetched direct items stay cached for the current page.
- [ ] **Step 5: Run the focused contract test.** Expected: generated page uses the updated component and the source contract passes.

## Task 2: Preserve navigation, filtering, and deeper hierarchy

**Files:**
- Modify: `homebox-ui/overlay/components/Location/ChildContents.vue`
- Test: `tests/test_location_child_preview.py`
- Test: `tests/location_contents.test.mjs` only if the pure helper exists

**Interfaces:**
- Consumes: Task 1 batch result, the existing `api.items.getLocation(locationId)` read for deeper children, and existing item/location routes.
- Produces: each bin lists direct items with item link, asset/display ID, and quantity; item row shows its bin name/path context; deeper child locations can be expanded individually without fetching their contents until requested.

- [ ] **Step 1: Add contract assertions** for direct parent grouping, nested child collapse/lazy loading, empty bins, retry, and native item/location links.
- [ ] **Step 2: Run `python3 -m unittest tests.test_location_child_preview -v`.** Expected: failures for any newly specified states missing from current output.
- [ ] **Step 3: Keep deeper levels lazy**; do not recursively expand all descendants or issue one item-list request per bin at initial page load. Expose partial-load state and preserve successfully returned rows.
- [ ] **Step 4: Add a local filter scoped to the loaded cabinet view** over bin names, item names, asset/display IDs, manufacturer, model, and serial; show the full bin name beside each item match and provide a clear-filter action. Do not imply that unloaded deeper descendants were searched.
- [ ] **Step 5: Run `python3 -m unittest tests.test_location_child_preview -v`.** Expected: item ancestry, empty state, and retry contracts pass.

## Task 3: Whole-feature verification and handoff

**Files:**
- Review: `homebox-ui/overlay/components/Location/ChildContents.vue`
- Review: `deploy/build-homebox-ui.py`
- Review: `tests/test_location_child_preview.py`

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces: verified cabinet contents experience and a manual acceptance record from a synthetic location tree.

- [ ] **Step 1: Run** `python3 -m unittest tests.test_location_child_preview -v`; record the focused result.
- [ ] **Step 2: Use a fake API fixture with 20+ bins**, mixed populated/empty bins, more than 100 direct items to exercise pagination, archived items, and one nested bin; confirm direct contents appear without opening bins, no item is misplaced, and pagination stops at `total`.
- [ ] **Step 3: Inspect at desktop and 800×480** with keyboard only; confirm search, expand/collapse, per-bin states, links, and focus remain usable.
- [ ] **Step 4: Check** that no operational Homebox data was changed and no deployment/service operation occurred.

## Deferred

- A spatial cabinet/bin map, bulk moves, and inventory edits from the subtree view.
- Expanding every nested level by default or loading the entire collection into one response.
- Combining cabinet location notes/maintenance with grouped product notes.

## Demonstration workflow

1. Staff open the Gray cabinet location. All immediate bins appear, with their direct items listed under the correct bin without expanding each one.
2. Empty bins remain visible with an explicit empty label. Archived equipment is visible with an Archived status.
3. Staff search the loaded cabinet view for a model, asset code, or serial; each match retains its bin name and a link to its native item page.
4. Staff expand a deeper nested location only when needed. Its contents load on demand; the initial cabinet view does not fetch every descendant.
5. If a page of a large result fails, already loaded rows remain visible with a partial-results notice and a retry action.
