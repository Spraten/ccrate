# Equipment ID codes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Add a collection-scoped Workshop page for viewing and editing generated equipment model codes without changing IDs already assigned to items.

**Architecture:** Extend the existing SQLite equipment catalog with a product overview and explicit audited code-update operation. Expose collection-member API routes and ensure item creation uses the canonical code of an existing product. Add the management view to the existing Workshop route and sidebar, reusing the current Workshop renderer and write-recovery path.

**Tech Stack:** Python standard library, SQLite ledger, existing C-Crate desktop API, Vue/Nuxt Workshop routing, existing browser fixtures and Python/Node contract tests.

**Spec:** `docs/superpowers/specs/2026-10-20-equipment-id-management-design.md`

## Global Constraints

- The existing generated ID format remains `TYPE-CODE-N`, for example `DRONE-2S-6`.
- IDs already assigned to items remain unchanged and continue to resolve and search as before.
- Any authenticated current collection member can view and edit model codes.
- Model-code changes happen through an explicit edit action; adding an item for an existing product cannot silently change its code.
- The existing product sequence high-water mark is retained; editing a code does not reset or reuse numbers.
- The ID preview is not a reservation; the server remains the only allocator.
- Homebox remains authoritative for item identity, type, name, storage, and item access.
- Keep existing equipment-template controls out of the UI and preserve saved template data.
- Add no dependencies and do not change deployment or service topology.
- Never run tests or checks against operational Homebox data; use isolated temporary fixtures.

## Review Focus

- Duplicate model code or display-base reservations: reject atomically without changing the product or sequence. (Task 1 tests.)
- Stale expected version or replayed request key: return a conflict or the original saved result without applying a second edit. (Task 1 tests.)
- Model with unassigned/archived members or removed assignments: show active counts separately from the durable next sequence. (Task 1 tests.)
- Old item suggestion after a code edit: return the product's current code and prevent item creation from reverting it. (Task 2 tests.)
- API failure or collection switch while the page loads/saves: show a recoverable error and preserve edit input; do not claim a save succeeded. (Tasks 2 and 3 tests.)

---

### Task 1: Add safe product-code catalog operations

**Files:**
- Modify: `ops/equipment_catalog.py`
- Test: `tests/test_equipment_catalog.py`

**Interfaces:**
- Produces `list_products(group_id: str, active_entity_ids: set[str]) -> list[dict]`. Each result contains `id`, `entity_type_id`, `type_prefix`, `manufacturer`, `model_number`, `model_code`, `active_item_count`, `active_assigned_count`, `next_number`, and `assignments`; each assignment has `entity_id`, `display_id`, and `number`. `next_number` is `high_water + 1`; counts include only supplied active native IDs, and assigned count additionally requires a non-deleted assignment.
- Produces `update_product_model_code(group_id: str, actor_id: str, product_id: str, model_code: str, expected_updated_at: str, request_key: str) -> dict`. It validates and reserves the new code using existing uniqueness rules, updates the product without resetting its high-water mark, and writes an append-only actor/time/old/new/request audit record in the same transaction. Replays return their original result; stale versions conflict.
- Produces `current_product_model_code(group_id: str, product_id: str) -> str | None` for suggestion projection in Task 2.
- Changes `register_product` so an existing product identity with a different submitted code conflicts instead of silently changing the registered code; initial code registration for a genuinely new identity remains supported.

- [ ] **Step 1: Write failing catalog tests** for active member/assignment counts and `high_water + 1`; code edit preserving prior assigned IDs and the sequence; code collision leaving all state unchanged; stale version conflict; same-key replay returning the original result with one audit row; and registration refusing to change an existing product code.
- [ ] **Step 2: Run the focused catalog tests and verify the new cases fail** with missing method/assertion behavior, not a fixture error.

  Run: `PYTHONPATH=ops:kiosk:work/hardware/python python3 -m unittest discover -s tests -p 'test_equipment_catalog.py' -v`

- [ ] **Step 3: Implement the three catalog methods and additive audit table** using the existing `Ledger.transaction`, code reservation, and request replay patterns. Keep old `equipment_assignments` rows untouched.
- [ ] **Step 4: Run the focused catalog tests and verify they pass** with pristine output.
- [ ] **Step 5: Commit** as `feat: manage equipment ID model codes`.

### Task 2: Expose member-scoped API and protect registered product codes

**Files:**
- Modify: `ops/equipment_api.py`
- Modify: `ops/desktop_api.py`
- Test: `tests/test_desktop_api_equipment_catalog.py`

**Interfaces:**
- Consumes Task 1 catalog methods.
- Adds `GET equipment/products`, returning Task 1 product summaries for active, accessible, non-location native entities in the authenticated collection.
- Adds `POST equipment/products/code` with `{product_id, model_code, expected_updated_at, request_key}`. It requires current collection membership and returns the updated product or existing typed conflict/error.
- For suggestions, `modelCode` is the current product code, not the historical assignment snapshot.
- For item assignment to a product identity that already exists, Task 1's catalog conflict is returned when a differing submitted code is supplied. A new identity can still register its initial code.

- [ ] **Step 1: Write failing API tests** for member-only collection-scoped listing/editing, unauthenticated and foreign-collection rejection, valid update, duplicate/stale errors, suggestion returning the current canonical code, and assignment not reverting a changed code.
- [ ] **Step 2: Run the focused API tests and verify the new cases fail** for the expected missing route or incorrect current behavior.

  Run: `PYTHONPATH=ops:kiosk:work/hardware/python python3 -m unittest discover -s tests -p 'test_desktop_api_equipment_catalog.py' -v`

- [ ] **Step 3: Implement GET/POST dispatch and handlers** with existing member validation and typed conflict handling. Ensure API responses include only products and assigned entities visible in the active collection.
- [ ] **Step 4: Update suggestion projection and registration behavior** so only explicit code-edit operations can change the code of an existing product; preserve new-product assignment recovery.
- [ ] **Step 5: Run focused API tests and review existing template/member tests**; verify all pass with pristine output.
- [ ] **Step 6: Commit** as `feat: expose equipment ID code API`.

### Task 3: Add the Equipment ID codes Workshop page

**Files:**
- Modify: `homebox-ui/overlay/pages/workshop/[tool].vue`
- Modify: `homebox-ui/overlay/pages/workshop/index.vue`
- Modify: `homebox-ui/overlay/lib/workshop-tools.js`
- Modify: `deploy/build-homebox-ui.py`
- Test: `tests/test_homebox_navigation_contract.py`
- Test: `tests/test_workshop_browser.py`
- Test: `tests/workshop_action_surfaces.browser.mjs`

**Interfaces:**
- Consumes `GET equipment/products` and `POST equipment/products/code` from Task 2 through the existing Workshop API client.
- Registers route `/workshop/equipment-ids`, titled **Equipment ID codes**, and exposes it under the Workshop sidebar group for all collection members.
- The product list supports search by model, model code, or assigned ID; expands to linked item records; displays active item count, active assigned-ID count, and a **Next ID preview — not assigned** computed from returned `next_number`.
- The preview explains that another assignment may use the number first. The edit dialog submits a request key and expected version through the existing durable Workshop write flow. It explains that only future IDs change and preserves the draft on conflict or service error.

- [ ] **Step 1: Add failing navigation and browser-fixture tests** proving sidebar discovery, direct route registration, product list and assigned-item links, tentative preview wording, edit confirmation, and visible recoverable load/save errors.
- [ ] **Step 2: Run the focused UI tests and verify the new cases fail** because route/navigation/page behavior is absent.

  Run: `PYTHONPATH=ops:kiosk:work/hardware/python python3 -m unittest discover -s tests -p 'test_homebox_navigation_contract.py' -v` and `node tests/workshop_action_surfaces.browser.mjs`

- [ ] **Step 3: Register the Workshop route and sidebar link** in the Vue route and builder. Direct refresh must keep `/workshop/equipment-ids`; do not expose template controls or restrict this page to managers.
- [ ] **Step 4: Implement the list, search, detail expansion, preview, and edit dialog** in the existing Workshop tool renderer. Use its loading, retry, toast, API, and write-recovery patterns.
- [ ] **Step 5: Run focused navigation and browser tests** and verify all new behavior passes with pristine output.
- [ ] **Step 6: Commit** as `feat: add equipment ID codes page`.

---

## Task dependency table

| Producer | Consumer | Shared interface | Scan result |
|---|---|---|---|
| Task 1 catalog list/update/current-code methods | Task 2 API handlers | Exact signatures and response keys are defined in Task 1 | Compatible; Task 2 must not introduce parallel counters or rewrite assignments. |
| Task 2 API routes/response schema | Task 3 Workshop page | `GET equipment/products`; `POST equipment/products/code`; fields are listed in Task 2 | Compatible; UI remains a client of authenticated Workshop transport. |
| Task 2 suggestion projection and registration guard | Existing item-create flow | `modelCode` resolves to current product code; mismatches conflict | Compatible with suggestions; plan specifically pins regression. |

## Preflight ruling

`Ruling: collection members retain model-code edit access — this follows the earlier explicit collection-wide edit decision and avoids silently changing permissions; if wrong, users who expected manager-only control can edit codes until access policy is changed.`

`Ruling: model-code changes are separated from item creation — item creation currently can mutate an existing product code; this avoids surprise changes to future IDs, at the cost of requiring an explicit conflict/edit step when a member enters a different code for a known model.`

## Rollback and verification

The schema change is additive. UI removal/revert does not alter assigned IDs or saved template data. API rollback must leave the new audit table harmless and preserve product code reservations. Tests use temporary ledgers and fake collection fixtures only; no operational item creation or catalog mutation is permitted. The final review must inspect the full branch diff, including the existing dirty working-tree changes, without staging or committing unrelated files.
