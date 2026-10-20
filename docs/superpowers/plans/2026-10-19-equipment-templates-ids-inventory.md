# Equipment Templates, Generated IDs, and Grouped Inventory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let collection members reuse shared equipment templates, assign stable short IDs to new items, and browse matching equipment as cross-location Inventory groups.

**Architecture:** Keep Homebox as the authority for native item records, photos, status, permissions, and history. Store collection templates, product associations, and stable ID assignments in the existing C-Crate Python/SQLite service; connect them to native item UUIDs through authenticated, recoverable API calls. Extend the live UI overlay to apply templates, display/resolve IDs, and group the complete filtered Inventory result before paging.

**Tech Stack:** Python 3, existing C-Crate SQLite ledger and desktop API, Vue/Nuxt overlay, existing Node fixture tests, Playwright browser verification, current Homebox item APIs. No new dependencies or Go backend rebuild.

**Spec:** `docs/superpowers/specs/2026-10-19-equipment-templates-ids-inventory-design.md`

## Global Constraints

- Homebox remains the authority for native item identity, item fields, photos, storage, access, and history.
- Templates and stable ID assignments are collection scoped and linked to native item/product identity.
- Existing generated IDs remain unchanged; short IDs are assigned only to newly created items.
- An assigned ID never changes on item move, rename, edit, template edit, or deletion of another item. Deleted numbers are not reused.
- The first short ID continues after the number of existing matching native items, including archived records.
- IDs use `TYPE-CODE-N`, e.g. `DRONE-2S-6`; codes are editable and unique per item type/product.
- Template changes affect new items. Updating existing items requires an explicit unit and field selection, preview, and confirmation; never bulk-copy serial, location, condition, status, custody, note, UUID, or generated ID.
- Template routes require a current collection member; all members may edit collection templates. Item permissions remain Homebox controlled.
- Never automatically repeat an uncertain native create or assignment. Preserve request identity and recover by status/idempotent assignment.
- Group counts cover the complete filtered result before pagination. Never infer availability from missing status data.
- No new dependencies, operational inventory mutations, service deployment, or physical printing in fixture/browser verification.

## Review Focus

- Concurrent first assignment for one product: both requests must return unique IDs and a valid monotonic counter.
- Archived and incomplete native records while seeding a counter: include matching records for count and avoid false model merges.
- Assignment API timeout after native creation: retrying the same item/request returns its original ID without a second item or consumed counter.
- Inventory results spanning pages or filters: a product group appears once with a complete count and exact filtered units.
- Missing item status/location/photo or stale collection scope: preserve the row and show unavailable/placeholder state without leaking another collection's templates or assignments.

---

## File map

- `ops/equipment_catalog.py` — C-Crate collection-scoped template/product/ID persistence, normalization, counter allocation, and idempotent assignment.
- `ops/desktop_api.py` — authenticated template, assignment, mapping, and ID-resolution routes; trusted member attribution and native item validation.
- `ops/labels.py` and `ops/label_render.py` — use the persisted short ID for new records while retaining native generated IDs for unassigned legacy records.
- `deploy/build-homebox-ui.py` plus a focused C-Crate overlay component/helper — patch the generated `components/Entity/CreateModal.vue` with template selection, create-from-template flow, and post-create ID-assignment recovery state. The generated Homebox component is an input artifact; make durable edits in the builder/overlay.
- `deploy/build-homebox-ui.py` plus new `homebox-ui/overlay` components/helpers — patch the generated `pages/items.vue`, `components/Item/View/Table.vue`, and column defaults with cross-location grouping, expansion, per-unit details, and Inventory defaults. The generated Homebox files are input artifacts; make durable edits in the builder/overlay.
- `homebox-ui/overlay/lib/child-item-groups.js` — shared product identity projection and safe matching across Inventory and location contents.
- `tests/test_equipment_catalog.py`, `tests/test_desktop_api_equipment_catalog.py`, `tests/equipment_catalog.test.mjs`, and `tests/equipment_inventory.test.mjs` — isolated contract and UI projection fixtures.
- `tests/fixtures/equipment_catalog/` — native entity responses for existing, archived, incomplete, and conflicting products; fixture only, no operational inventory writes.

## Task 1: Collection Catalog and Stable ID Store

**Files:**
- Create: `ops/equipment_catalog.py`
- Create: `tests/test_equipment_catalog.py`
- Modify: `ops/ledger.py` only if a shared timestamp/transaction helper is required; otherwise keep the catalog tables in the existing database through its connection/transaction API.

**Interfaces:**
- `EquipmentCatalog.list_templates(group_id) -> list[Template]`
- `EquipmentCatalog.register_product(group_id, actor_id, request_key, product, matching_entity_ids) -> Product`
- `EquipmentCatalog.save_template(group_id, actor_id, request_key, payload, type_prefix, matching_entity_ids=(), template_id=None, expected_updated_at=None) -> Template`; edits retain the product UUID and current sequence, and require an optimistic `expected_updated_at` value.
- `EquipmentCatalog.archive_template(group_id, actor_id, template_id, request_key) -> Template`
- `EquipmentCatalog.assign_item(group_id, actor_id, entity_id, product_id, request_key) -> Assignment`
- `EquipmentCatalog.assignment(group_id, entity_id) -> Assignment | None`
- `EquipmentCatalog.resolve_id(group_id, display_id) -> entity_id | None`
- Template payload fields are exactly `name`, `entity_type_id`, `manufacturer`, `model_number`, `model_code`, `description`, `tag_ids`, and optional `photo_attachment_id`; per-unit fields are rejected.
- Assignment output includes `entity_id`, `product_id`, `display_id`, `type_prefix`, `model_code`, `number`, and assignment timestamp.

- [ ] **Step 1: Add failing SQLite fixture tests** for collection isolation, required template fields, normalized uppercase `model_code`, rejection of unknown/per-unit fields, archive/reserved-code behavior, template edit/version conflict, type-prefix derivation, assignment request-key binding, product/template idempotency under concurrent identical/conflicting requests, visible-prefix collision rejection, ID resolution, first-number seeding after matching active/archived records, movement/rename stability, and assignment tombstone/replay identity.
- [ ] **Step 2: Run** `PYTHONPATH=tests:ops:kiosk python -m unittest test_equipment_catalog -v`. Expected: fail because catalog API/storage is absent.
- [ ] **Step 3: Implement additive catalog schema and `EquipmentCatalog`**. Store templates, product identity, entity membership, high-water counter, and entity-to-ID assignment under the collection ID. Product registration receives matching native UUIDs already verified by the API layer, links those legacy records without changing their IDs, and seeds the first number from active and archived records. Use one SQLite transaction for code reservation, counter increment, and assignment. Existing assignments replay unchanged; code/product mismatches conflict. Reserve all `(group,type_prefix,model_code)` values historically used by a product, including archived template codes. Keep history rows sufficient to attribute template writes to actor and timestamp. Persist request digests/results in the same transaction as product/template writes; identical replay returns the original result and changed payload under the same key conflicts.
- [ ] **Step 4: Run** `PYTHONPATH=tests:ops:kiosk python -m unittest test_equipment_catalog -v`. Expected: all catalog fixtures pass, including concurrent assignment to the same product and deleted-number non-reuse.
- [ ] **Step 5: Commit** `feat(catalog): persist templates and stable equipment IDs` with only Task 1 files.

## Task 2: Authenticated Catalog and Assignment API

**Files:**
- Modify: `ops/desktop_api.py`
- Create: `tests/test_desktop_api_equipment_catalog.py`
- Modify: `ops/equipment_catalog.py` only for tested contract corrections.

**Interfaces:**
- `GET equipment/templates` returns current-collection templates.
- `POST equipment/templates/save` accepts `{request_key, template_id?, source_entity_id?, fields}` and returns the saved template. If `source_entity_id` is supplied, fetch it from Homebox and allow only shared template fields.
- `POST equipment/templates/archive` accepts `{request_key, template_id}` and returns the archived template.
- `POST equipment/ids/assign` accepts `{request_key, entity_id, template_id?, model_code?}`; exactly one product source is required. The server re-fetches the native item, validates same collection and non-location type, resolves/creates a product identity, matches existing native records using the spec matching rules, then returns the stable assignment. Request replay for the same item is idempotent; another item under the same request key conflicts.
- `POST equipment/ids/resolve` accepts `{display_id}` and resolves only inside the authenticated collection.
- `GET equipment/ids` accepts up to 100 native entity UUIDs and returns a scoped `entity_id -> {product_id, display_id}` mapping for UI projection.

- [ ] **Step 1: Add failing endpoint fixtures** for member access, collection scoping, native item revalidation, location rejection, field whitelist, request replay/conflict, and assignment timeout recovery.
- [ ] **Step 2: Run** `PYTHONPATH=tests:ops:kiosk python -m unittest test_desktop_api_equipment_catalog -v`. Expected: fail because routes are absent.
- [ ] **Step 3: Implement authenticated routes** in `ops/desktop_api.py`. Template edits allow any authenticated current member. Assignment fetches native item details server side; browser-supplied type/manufacturer/model is never trusted. When registering a product, the API queries all matching active and archived Homebox items using the spec matching rules and passes only their UUIDs into the catalog transaction. Re-fetch mapping records under the authenticated collection and cap batches at 100.
- [ ] **Step 4: Run** `PYTHONPATH=tests:ops:kiosk python -m unittest test_desktop_api_equipment_catalog -v`. Expected: all route and replay fixtures pass without contacting the live Pi.
- [ ] **Step 5: Commit** `feat(api): expose collection templates and equipment IDs` with only Task 2 files.

## Task 3: Template-Based Item Creation and ID Recovery

**Files:**
- Modify: `deploy/build-homebox-ui.py` at the existing CreateModal extension points.
- Create/modify: focused overlay helper/component files under `homebox-ui/overlay` for template state and UI.
- Do not edit generated `work/homebox-ui-current` or `work/homebox-ui-dev` source directly.
- Modify: `homebox-ui/overlay/lib/workshop-tools.js` or a new `homebox-ui/overlay/lib/equipment-catalog.ts` for typed companion calls.
- Create: `tests/equipment_catalog.test.mjs`
- Create: focused component/flow fixture under `tests/` using established project test helpers.

**Interfaces:**
- `listEquipmentTemplates()` returns `Template[]` for the active Workshop identity.
- `saveEquipmentTemplate(fields, requestKey, sourceEntityId?)` returns the saved `Template`.
- `assignCreatedEquipment(entityId, templateId, requestKey)` returns the stable `Assignment`.
- Create modal keeps the native UUID as the record identity; it stores the assignment request key and never repeats `api.items.create` after uncertainty.

- [ ] **Step 1: Add failing helper and flow fixtures** for template defaults, per-unit blank fields, duplicate submission guard, assignment retry using the same entity UUID, successful creation without a template, explicit existing-unit selection/field preview, and rejection of attempts to include serial/location/status/ID fields in bulk apply.
- [ ] **Step 2: Run** `node --test tests/equipment_catalog.test.mjs`. Expected: fail because catalog UI helpers are absent.
- [ ] **Step 3: Implement template selection and inline template save** in the existing CreateEntity modal. Copy name/type/manufacturer/model/description/tags. Use the template photo as a shared thumbnail fallback; an item’s own photo takes precedence. Do not copy the source item attachment or prefill serial, item location, condition, status, loan, or notes. Add an explicit “Apply to existing items” action: choose exact units and shared fields, preview each proposed change, confirm, then call Homebox item patch only for selected shared fields; report per-unit partial success and never auto-repeat an uncertain patch. After a native item create succeeds, register its UUID with the selected product and retain a recoverable assignment state if that call fails. For items created without a saved template, require an editable model code and let the assignment API create a product identity from the server-fetched native record; offer to save the shared values as a reusable template.
- [ ] **Step 4: Run** `node --test tests/equipment_catalog.test.mjs` and the focused CreateEntity component checks. Expected: templates populate only approved shared fields; an uncertain assignment can resume without another native create; applying template changes touches only selected shared fields and identifies partial outcomes.
- [ ] **Step 5: Commit** `feat(items): create equipment from shared templates` with only Task 3 files.

## Task 4: Stable IDs in Search, Item Views, and Labels

**Files:**
- Modify: `homebox-ui/overlay/pages/items.vue` and relevant item search helper for batched assignment projection and generated-ID resolution.
- Modify: `ops/labels.py` and `ops/label_render.py` to override the dynamic native `displayId` only when a C-Crate assignment exists.
- Modify: `tests/test_labels.py` and search helper fixtures.
- Modify: `deploy/build-homebox-ui.py` only if an exact native component replacement/copy is needed.

**Interfaces:**
- `projectAssignedDisplayIds(items, assignments)` copies the persisted `display_id` onto assigned rows and leaves all unassigned legacy rows unchanged.
- Search first retains native Homebox search behavior; on an exact generated-ID miss, resolve through `equipment/ids/resolve`, then open the native UUID route.
- Label preview uses persisted assigned ID for new records and current native `displayId` for existing records. The preview receipt binds the effective ID and invalidates if it changes before print.

- [ ] **Step 1: Add failing fixtures** for legacy/new ID coexistence, exact ID search resolution, label preview ID selection, review invalidation when the effective ID changes, and cross-collection non-resolution.
- [ ] **Step 2: Run** focused Node and Python fixtures. Expected: fail when assigned display ID is absent.
- [ ] **Step 3: Implement the batched mapping and search fallback** in the overlay; integrate effective ID selection into label preview without changing UUID QR destinations or existing label template keys.
- [ ] **Step 4: Run** `node --test tests/equipment_catalog.test.mjs` and `PYTHONPATH=tests:ops:kiosk python -m unittest test_labels -v`. Expected: both legacy and new label/search paths pass.
- [ ] **Step 5: Commit** `feat(ids): display and resolve stable equipment IDs` with only Task 4 files.

## Task 5: Cross-Location Grouped Inventory

**Files:**
- Modify: `homebox-ui/overlay/lib/child-item-groups.js`
- Modify: `deploy/build-homebox-ui.py` to patch the generated `pages/items.vue`, `components/Item/View/Table.vue`, and default column definitions through exact existing anchors.
- Create: focused Inventory group/row overlay components under `homebox-ui/overlay/components/Item/` if they keep the builder patch small.
- Do not edit generated `work/homebox-ui-current` or `work/homebox-ui-dev` source directly.
- Create: `tests/equipment_inventory.test.mjs`

**Interfaces:**
- `groupInventoryItems(items, productAssignments, {query, filters, storagePath}) -> InventoryGroup[]` applies identity precedence: assigned product ID, explicit product-group tag, normalized type/manufacturer/model, then conservative exact-name fallback when metadata does not conflict.
- Each `InventoryGroup` contains all filtered matching native records, separate `recordCount` and native quantity totals, per-status counts for `available`, `checked_out`, `blocked`, `archived`, and `unknown`, and a stable key. Status and action permission come from the authoritative C-Crate equipment status/permissions endpoint backed by Homebox state.
- Expanded units carry the item photo or template thumbnail fallback, authoritative equipment status, full storage path, serial, effective generated ID, recent note preview, and item UUID for native detail. Mount the existing shared `ItemQuickActions` host for check-in, check-out, cart, and note actions; do not add per-row mutation handlers.

- [ ] **Step 1: Add failing grouping and rendering projection fixtures** for five Air 2S units across locations, same-name conflicting models, custom group tags, available/checked_out/blocked/archived/unknown status, unavailable metadata, quantity-vs-record count, search-by-unit ID expansion, and pages whose rows belong to one group.
- [ ] **Step 2: Run** `node --test tests/equipment_inventory.test.mjs`. Expected: fail because full Inventory grouping projection is absent.
- [ ] **Step 3: Implement whole-result group projection** after native filters and before display pagination. Fetch native result pages with cancellation and a bounded concurrency of four; only publish group totals when all filtered pages are loaded. Preserve native bulk-selection and deep links. Add the default thumbnail, status, location, name, and `×N >` presentation; remove Insured and Purchase Price from default columns while leaving item detail fields untouched. Expanded units show per-item location and quick actions. Missing status/location/history remain visible with explicit placeholders.
- [ ] **Step 4: Run** `node --test tests/equipment_inventory.test.mjs tests/location_child_contents.test.mjs` plus focused frontend component checks. Expected: groups remain complete across page boundaries and failures never remove item rows or imply availability.
- [ ] **Step 5: Commit** `feat(inventory): group equipment across locations` with only Task 5 files.

## Task 6: Integrated Browser Acceptance

**Files:**
- Create: `tests/browser/equipment-catalog-inventory.spec.ts` using the established isolated local browser state.
- Modify: this plan's progress ledger only as tasks are completed.

**Interfaces:**
- Browser uses isolated local C-Crate/Homebox fixture accounts and API interception or disposable data; never mutates operational inventory.

- [ ] **Step 1: Add acceptance cases** for shared template creation/edit/archive, new item from template, short ID assignment and replay recovery, legacy ID retention, search, cross-location `×5` group expansion, status/location/photo, quick actions, and default column preferences.
- [ ] **Step 2: Run** the isolated browser case at desktop and narrow viewport sizes. Expected: no duplicate native item on assignment recovery; all unit details stay attached to the correct UUID; filters/pagination and existing bulk actions remain usable.
- [ ] **Step 3: Fix only scoped integration defects**, preserving the Homebox native authority and existing unsaved/user preferences.
- [ ] **Step 4: Run** the focused Python, Node, component, and browser acceptance commands from Tasks 1–6. Record any environment-only gap without substituting an operational data test.
- [ ] **Step 5: Commit** `test(inventory): cover catalog and grouped item workflows` with only Task 6 files.

## Execution Order

Tasks 1 and 2 establish storage and API contracts. Task 3 consumes those contracts. Task 4 lets labels and search consume stable IDs. Task 5 consumes both product identity and ID mapping. Task 6 verifies the combined workflow. Keep one coding worker at a time; use an independent Sol review after each task and a final whole-plan review after Task 6.
