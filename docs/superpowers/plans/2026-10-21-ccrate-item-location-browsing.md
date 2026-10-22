# C-Crate Item and Location Browsing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make item and location browsing easier to scan, with useful photos and facts, less empty space, and fewer repeated controls.

**Architecture:** Preserve existing routes, native item/location data, manager authorization, and child-location loader. Add focused identity and detail components; render list/detail split view on desktop and list-then-detail navigation on narrow screens. Build the views with Homebox components and `workshop-native` styles so they follow the saved Homebox theme.

**Tech Stack:** Vue/Nuxt generated from `deploy/build-homebox-ui.py` plus `homebox-ui/overlay`, TypeScript, Tailwind theme tokens, existing attachment API, pytest and Node tests.

**Spec:** `TODO.md` sections “Item and location screens” and “Shared visual direction”; prerequisite `2026-10-21-ccrate-shared-theme-compatibility.md`; existing `docs/superpowers/specs/2026-10-19-equipment-templates-ids-inventory-design.md`.

## Global Constraints

- Homebox remains inventory, identity, location, and attachment authority; keep the auth middleware and existing route IDs.
- Reuse `thumbnailId` then `imageId`; show “No photo” when neither is present.
- Keep child location requests lazy and errors retryable; do not change storage contents or native records.
- Use the shared theme contract in `2026-10-21-ccrate-shared-theme-compatibility.md`; inherit Homebox typography, colors, controls, borders, focus rings, and `--radius`. Do not add page-specific palette values or a new font.

## Review Focus

- An item without photo/details does not create a large blank panel (`test_identity_header_hides_empty_optional_fields`).
- An item with only full-size image still shows a preview (`test_identity_header_falls_back_to_image_id`).
- Location with no children shows a compact explicit empty state (`test_location_detail_empty_state_is_compact`).
- Narrow viewport offers a visible back-to-results path (`test_item_browser_mobile_detail_has_back_navigation`).
- Views follow the saved Homebox theme and native control/surface styles (`test_item_location_view_uses_active_homebox_theme`).
- Existing expand/filter/retry behavior remains intact (`test_nested_contents_stay_lazy_and_failures_keep_retryable_rows`).

---

### Task 1: Build a reusable item/location identity header

**Files:**
- Create: `homebox-ui/overlay/components/Workshop/EntityIdentityHeader.vue`
- Modify: `deploy/build-homebox-ui.py` (`item_log_frontend`, location detail transform)
- Test: `tests/test_homebox_ui_builder.py`, new `tests/test_entity_identity_header.py`

**Interfaces:**
- Consumes: `entity: EntitySummary`, `kind: 'item' | 'location'`, `status?: string`, and `locationPath?: string`.
- Produces: one photo/name/status/location header; `kind='location'` labels the entity as a location and displays its parent path. No action buttons live inside the header.

- [ ] **Step 1: Write failing component/transform tests** `test_identity_header_prefers_thumbnail_id`, `test_identity_header_falls_back_to_image_id`, `test_identity_header_hides_empty_optional_fields`, `test_location_detail_empty_state_is_compact`, and `test_identity_header_transform_is_injected_for_item_and_location`.
- [ ] **Step 2: Run** `pytest tests/test_homebox_ui_builder.py tests/test_entity_identity_header.py -q`; expected: component/transform assertions fail.
- [ ] **Step 3: Add `EntityIdentityHeader.vue`** and inject it into `pages/item/[id]/index.vue` and `pages/location/[id]/index.vue` with existing entity data.
- [ ] **Step 4: Run** `pytest tests/test_homebox_ui_builder.py tests/test_entity_identity_header.py -q`; expected: PASS with no generated fields for missing metadata.
- [ ] **Step 5: Commit** `feat: clarify item and location identity details`.

### Task 2: Simplify location content and item activity sections

**Files:**
- Modify: `homebox-ui/overlay/components/Location/ChildContents.vue`
- Modify: `homebox-ui/overlay/components/Workshop/ItemLog.vue`
- Test: `tests/test_location_child_preview.py`, `tests/location_child_contents.test.mjs`

**Interfaces:**
- Consumes: current location tree, lazy child fetches, item activity rows.
- Produces: location contents grouped by direct child location and item type, empty rows omitted, existing filter/expand/retry semantics preserved; item details show concise expandable sections with one primary action outside detail content.

- [ ] **Step 1: Add failing layout assertions** `test_location_contents_hide_empty_optional_metadata`, `test_location_contents_keep_filter_path_and_retry_controls`, and `test_item_detail_has_one_primary_action_and_compact_optional_sections`.
- [ ] **Step 2: Run** `pytest tests/test_location_child_preview.py -q` and `node --test tests/location_child_contents.test.mjs`; expected: new layout assertions fail while current lazy-load tests pass.
- [ ] **Step 3: Rework only the presentation** of child groups and item details; preserve the current request/state functions and manager-only checks.
- [ ] **Step 4: Run** `pytest tests/test_location_child_preview.py -q` and `node --test tests/location_child_contents.test.mjs`; expected: PASS, including lazy failures, retry, filter, archived status, and ancestor context.
- [ ] **Step 5: Commit** `ui: compact item and location detail sections`.

### Task 3: Add responsive item/location split browsing

**Files:**
- Modify: `deploy/build-homebox-ui.py` (inventory page transform)
- Modify: `homebox-ui/overlay/components/InventoryGroups.vue`
- Test: `tests/test_equipment_inventory_builder.py`, new `tests/test_inventory_browser_layout.py`

**Interfaces:**
- Consumes: current `inventoryGroups`, filters, page, and selected entity ID.
- Produces: desktop left result list/right selected detail; narrow-screen result list followed by full-screen detail with Back. Selection is URL-addressable by the existing item/location route.

- [ ] **Step 1: Add failing layout tests** for selection, URL-backed detail, small-screen back navigation, selected-row focus, and no selection empty prompt.
- [ ] **Step 2: Run** `pytest tests/test_inventory_browser_layout.py tests/test_equipment_inventory_builder.py -q`; expected: split-view selectors and transitions are absent.
- [ ] **Step 3: Add the responsive browser layout** using existing grouping and route navigation. Keep rare/destructive actions in the existing authorized menu and expose one primary action.
- [ ] **Step 4: Run** the same focused tests; expected: PASS for desktop and mobile selection states.
- [ ] **Step 5: Commit** `feat: add responsive inventory detail browsing`.

#### Task 3 routing interpretation (2026-10-21)

Keep `/items` as the browsing route and store the selected item ID in the `selected` query parameter. This keeps the list and its existing filters/pagination in place while making the detail selection shareable and browser-history friendly. The right pane shows the selected row's available summary data and links to the existing `/item/:id` page for full native details and manager actions. On narrow screens, selecting an item shows the detail pane with a visible Back to results control.
