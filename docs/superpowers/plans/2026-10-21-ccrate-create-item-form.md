# C-Crate Create Item Form Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the long, visually dense Create Item modal with a compact single-page form that keeps essential fields and a photo preview visible.

**Architecture:** Keep the upstream `CreateModal.vue` behavior and source generation pipeline. Change its generated layout through a fail-closed build transform; retain the existing create pipeline, recovery, field persistence, scanner, OCR, and photo components.

**Tech Stack:** Vue 3/Nuxt, TypeScript, Tailwind, `deploy/build-homebox-ui.py`, pytest builder fixtures.

**Spec:** `TODO.md` sections “Create Item screen” and “Shared visual direction”; prerequisite `2026-10-21-ccrate-shared-theme-compatibility.md`; existing `docs/superpowers/specs/2026-10-20-smart-item-creation-design.md`.

## Global Constraints

- Preserve every current create field and capability, including locations, item type, code lookup, photos, custom fields, tags, and related equipment.
- Keep creation manager-authenticated, idempotent, and safe for uncertain requests; do not bypass the existing creation flow or post-create recovery.
- Add no runtime or build dependencies; use existing Homebox theme tokens and components. Do not change the saved Homebox theme as a side effect of opening or closing the form.
- Use one primary “Create item” action; offer “Create another” after confirmed save.

## Review Focus

- Selecting a location as entity type keeps location-specific fields/actions (`test_create_location_type_keeps_location_fields`).
- A create with pending recovery never offers a second create (`test_uncertain_create_offers_recovery_only`).
- Uploaded image preview remains visible and keyboard accessible (`test_create_photo_preview_remains_accessible`).
- The form follows the active Homebox theme and native form/button styles (`test_create_form_uses_active_homebox_theme`).
- Optional advanced fields remain reachable and retain entered data (`test_create_more_details_preserves_form_values`).
- Reopening/closing the dialog does not duplicate the OCR launcher or create controls (`test_create_form_transform_is_idempotent`).

---

### Task 1: Restructure the generated form into essential and optional groups

**Files:**
- Modify: `deploy/build-homebox-ui.py` (CreateModal layout transform)
- Test: `tests/test_homebox_ui_builder.py`

**Interfaces:**
- Consumes: upstream `components/Entity/CreateModal.vue` with existing `form`, `selectedEntityType`, `PhotoUploaderPreview`, and creation state.
- Produces: compact identity row (name, location, quantity/code as applicable), persistent photo preview, collapsed **More details** section for description/manufacturer/model/serial/packaging/custom fields/tags/related items. Existing selectors and field models remain unchanged.

- [ ] **Step 1: Add failing builder/browser tests** `test_create_location_type_keeps_location_fields`, `test_create_photo_preview_remains_accessible`, `test_create_more_details_preserves_form_values`, and `test_create_form_transform_is_idempotent`; assert required fields precede optional fields, photo preview stays visible, advanced fields remain under one disclosure, and every existing `v-model` is preserved.
- [ ] **Step 2: Run** `pytest tests/test_homebox_ui_builder.py -q`; expected: new compact-layout assertions fail.
- [ ] **Step 3: Implement `create_item_layout_frontend()`** as a fail-closed transformation of the upstream modal; invoke it after the current CreateModal feature transforms and preserve exact submitted form data.
- [ ] **Step 4: Run** `pytest tests/test_homebox_ui_builder.py -q`; expected: PASS, existing barcode/OCR/suggestion/photo/recovery builder contracts unchanged.
- [ ] **Step 5: Commit** `ui: group create item fields into a compact form`.

### Task 2: Replace competing creation actions with a confirmed-success choice

**Files:**
- Modify: `deploy/build-homebox-ui.py` (CreateModal action transform)
- Test: `tests/test_homebox_ui_builder.py`, new `tests/create_item_actions.browser.mjs`

**Interfaces:**
- Consumes: existing `create()` and `guardedEquipmentCreate(...)` outcome, including operation status/recovery.
- Produces: exactly one form submit action labeled **Create item**; after a confirmed successful create, show a success state with **Create another** and **View item**. Do not show “Create another” for an uncertain or failed result.

- [ ] **Step 1: Add failing browser tests** `test_success_offers_create_another_and_view_item`, `test_uncertain_create_offers_recovery_only`, and `test_form_has_one_submit_action`.
- [ ] **Step 2: Run** `node --test tests/create_item_actions.browser.mjs`; expected: current two-button action group violates the assertions.
- [ ] **Step 3: Implement the success-state choices** using the existing completed entity ID and modal reset helpers; never re-run `create()` on an uncertain response.
- [ ] **Step 4: Run** `node --test tests/create_item_actions.browser.mjs` and `pytest tests/test_homebox_ui_builder.py -q`; expected: PASS with no duplicate request after uncertain creation.
- [ ] **Step 5: Commit** `ui: simplify create item completion actions`.
