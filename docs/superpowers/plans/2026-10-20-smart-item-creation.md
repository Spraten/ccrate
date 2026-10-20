# Smart Item Creation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make it faster and safer to create similar items, record packaging and custom fields, and connect related items without changing their physical locations.

**Architecture:** Homebox continues to own item records, native custom fields, packaging, locations, and permissions. C-Crate adds collection-scoped persistence for custom-field Notes and symmetric related-item links, and extends its existing authenticated API and durable create-recovery flow. The generated frontend remains patched through `deploy/build-homebox-ui.py` and uses the existing OCR popover.

**Tech Stack:** Python standard library and SQLite; existing C-Crate `Ledger`, authenticated Workshop API, Homebox entity APIs; Vue 3/Nuxt TypeScript and JavaScript; existing Node and Python test fixtures.

**Spec:** `docs/superpowers/specs/2026-10-20-smart-item-creation-design.md`

## Global Constraints

- Homebox remains authoritative for item identity, collection membership, access rules, photos, locations, status, history, packaging, and custom field names and values.
- Suggestions use active items from the same collection and selected equipment type.
- Selecting a suggestion copies only name, manufacturer, model number, tags, and model code; the manufacturer serial number stays blank.
- Related-item links are symmetric, removable from either side, non-hierarchical, and cannot cross collections.
- A staged related item is created only after the main item succeeds; uncertain creates are checked before retrying.
- Remove template UI controls while preserving saved template data.
- Do not change existing IDs or QR destinations.
- Do not add dependencies or unrelated features.

## Review Focus

- A stale suggestion response must not replace results for a newer query or selected type; test query/type changes while a lookup is pending.
- Homebox fields with duplicate names, non-text types, or an update conflict must not be silently overwritten; test malformed field sets and preservation of unrelated native fields.
- A lost response after main or related item creation must recover the existing result before any retry; test uncertain create status and replay.
- Related items from a different collection or inaccessible to the current member must not be exposed or linked; test both endpoint authorization and collection scope.
- An item rename or custom-field value change must not detach its Note or relation; test stable IDs and field-name-keyed note updates.

---

## File Map

- `ops/item_metadata.py` — collection-scoped Notes and related-link persistence, idempotent mutations, and read models.
- `ops/desktop_api.py` — dispatch the new authenticated metadata and suggestion routes using the existing tenant-bound Homebox client.
- `ops/equipment_api.py` — active, type-scoped model suggestion lookup and model-code projection from existing equipment assignments.
- `ops/native_fields.py` — reuse existing native payload preservation and readback helpers for packaging and custom fields.
- `homebox-ui/overlay/lib/item-metadata.js` — client helpers for note/link calls and durable staged-related-item flow.
- `homebox-ui/overlay/lib/equipment-catalog.js` — retain ID assignment and creation recovery; remove only template-selection behavior from the create flow.
- `deploy/build-homebox-ui.py` — patch generated Homebox create/detail, Inventory search, OCR launcher target, and remove template controls.
- `homebox-ui/overlay/components/Workshop/EquipmentTemplatePanel.vue` and `EquipmentTemplateApply.vue` — remove all mounts/imports; leave dormant source and backend data intact.
- `tests/test_item_metadata.py`, `tests/test_desktop_api_item_metadata.py`, `tests/item_metadata.test.mjs`, and `tests/item_suggestions.test.mjs` — fixture coverage for persistence, API permissions, suggestion matching, and client recovery.
- `tests/test_homebox_ui_builder.py` — generated UI contract assertions for create, detail, OCR, and template-control removal.
- `tests/item_metadata.browser.mjs` — create and detail interactions, OCR launcher visibility, and related-item recovery UI.
- `tests/test_equipment_search_builder.py` and `tests/equipment_search.test.mjs` — custom-field search and stale-query behavior.

## Interfaces

- `ItemMetadata(ledger)` owns persistence. It exposes `save_field_notes(group_id, actor_id, entity_id, fields, request_key)`, `field_notes(group_id, entity_id)`, `add_related(group_id, actor_id, entity_a, entity_b, request_key)`, `remove_related(group_id, actor_id, entity_a, entity_b, request_key)`, and `related_items(group_id, entity_id)`. Relation IDs are stored as a normalized pair so either endpoint reads/removes the same link.
- `GET /workshop-api/equipment/suggestions?entity_type_id=<uuid>&q=<text>` returns at most 8 active same-type items with `{id, name, manufacturer, modelNumber, tagIds, modelCode}`. It returns no matches for an empty/whitespace-only query, excludes locations and archived items, and never crosses the authenticated collection.
- `GET /workshop-api/item-metadata?entity_id=<uuid>` returns `{fieldNotes: {normalizedFieldName: note}, relatedItems: [...]}` after validating access to the native item.
- `POST /workshop-api/item-metadata/field-notes` accepts `{request_key, entity_id, fields: [{name, note}]}` and replaces the Notes for the submitted item field set idempotently.
- `POST /workshop-api/item-metadata/related/add` and `/related/remove` accept `{request_key, entity_id, related_entity_id}`. Both native entities are resolved through the current collection client before mutation.
- Client create state stores the main create request and each staged related create/link step independently. Completed steps are retained and never reissued as creates; uncertain steps require status reconciliation before retry.

### Task 1: Collection-scoped metadata persistence and API

**Files:**
- Create: `ops/item_metadata.py`
- Modify: `ops/desktop_api.py`
- Create: `tests/test_item_metadata.py`
- Create: `tests/test_desktop_api_item_metadata.py`

**Interfaces:** Implements `ItemMetadata` methods above. API handlers validate native entities through `public_entity(client, id)`, use `ctx['group']` and `ctx['actor']`, and return the declared read models.

- [ ] Write SQLite fixture tests for field-note save/read/replay, normalized field-name uniqueness, symmetric relation lookup/removal, duplicate-add replay, and collection isolation.
- [ ] Run `python -m unittest discover -s tests -p 'test_item_metadata.py' -v`; confirm the new behavior fails before implementation.
- [ ] Implement `ItemMetadata` with additive SQLite tables keyed by collection and native entity UUID; make pair writes/removals transactional and idempotent by request key.
- [ ] Add authenticated GET/POST dispatch in `ops/desktop_api.py`; reject missing, location, inaccessible, or cross-collection entities before any mutation.
- [ ] Add API fixture tests for member access, inaccessible item, wrong collection, duplicate request key, and symmetric removal.
- [ ] Run `python -m unittest discover -s tests -p 'test_desktop_api_item_metadata.py' -v`; expected: all API cases pass.

### Task 2: Active model suggestion endpoint and client matcher

**Files:**
- Modify: `ops/equipment_api.py`
- Modify: `ops/desktop_api.py`
- Create: `homebox-ui/overlay/lib/item-suggestions.js`
- Modify: `tests/test_desktop_api_equipment_catalog.py`
- Create: `tests/item_suggestions.test.mjs`

**Interfaces:** `GET equipment/suggestions` returns the declared shape, obtains `modelCode` from the item’s persisted assignment when present, and returns no archived items. Client `rankItemSuggestions(query, items)` ranks normalized prefix/substring matches without changing the create form.

- [ ] Add API tests for selected type, active filtering, empty query, result limit, collection scope, and model-code lookup.
- [ ] Run `python -m unittest discover -s tests -p 'test_desktop_api_equipment_catalog.py' -v` and `node --test tests/item_suggestions.test.mjs`; confirm the new cases fail before implementation.
- [ ] Implement the endpoint using the authenticated Homebox client and existing assignment catalog; avoid leaking native errors for inaccessible records.
- [ ] Implement deterministic client ranking and tests for case, whitespace, partial words, stable tie ordering, and empty input.
- [ ] Run the focused API and Node tests; expected: all pass.

### Task 3: Create-form suggestions, packaging, custom fields, template removal, and OCR access

**Files:**
- Modify: `deploy/build-homebox-ui.py` (`equipment_catalog_create_frontend` and focused new create/OCR transforms)
- Modify: `deploy/build-homebox-ui.py` shell/OCR transform so the one global popover targets the add-item launcher while the dialog is open
- Keep: `homebox-ui/overlay/lib/equipment-catalog.js` ID assignment and create recovery; remove template controls only in the generated create component
- Remove mounts/imports for: `homebox-ui/overlay/components/Workshop/EquipmentTemplatePanel.vue` and `EquipmentTemplateApply.vue`; preserve their persisted backend records and APIs
- Modify: `tests/test_homebox_ui_builder.py`
- Create: `tests/item_metadata.browser.mjs`

**Interfaces:** Selected suggestions copy only `name`, `manufacturer`, `modelNumber`, `tagIds`, and `modelCode`; `serialNumber` remains empty. Packaging choices are exactly `Original Packaging`, `No Packaging`, `HardCase`, `Softcase`, `Bag`, `Misc`, with an empty value allowed. Create-form fields are serialized as native Homebox `fields` and confirmed by readback.

- [ ] Add generated-UI assertions that photo-based name suggestion and every create-template control are absent, while existing durable generated-ID assignment remains.
- [ ] Add interaction cases for keyboard navigation/selection, selection-only autofill, blank serial, packaging options, and custom-field row add/remove/edit.
- [ ] Add a fixture assertion that the single `OcrPopover` can target the create-form launcher and retains scan/edit/copy without writing into the form.
- [ ] Implement the create-form UX and preserve existing item-create identity, photo, and generated-ID recovery behavior.
- [ ] Include native packaging and custom Name/Value rows in the existing durable post-create update steps, preserving parent, type, tags, and unrelated native fields; keep values and expose retry if a post-create step fails.
- [ ] Persist custom Notes with the metadata endpoint after the native item update; make replay idempotent.
- [ ] Remove all template UI imports, launchers, and controls while leaving template API, tables, and saved data untouched.
- [ ] Run the generated builder and focused create/OCR fixtures; expected: generated form contains no template controls and all new interactions pass.

### Task 4: Durable staged related-item creation and retry

**Files:**
- Modify: `homebox-ui/overlay/lib/item-metadata.js`
- Modify: `deploy/build-homebox-ui.py` create-form integration
- Modify: `tests/item_metadata.test.mjs`
- Modify: `tests/item_metadata.browser.mjs`

**Interfaces:** A staged related record contains the user-entered native create fields, editable `parentId` defaulted from the main item, and a stable request key. The flow in `item-metadata.js` exposes `stageRelated(item) -> stepKey`, `recordMainCreated(entityId)`, `resumeRelatedSteps()`, `reconcileRelatedCreate(stepKey, entityId)`, and `retryRelatedStep(stepKey)`. Each step has `pending | uncertain | completed | failed` state and an entity ID once confirmed.

- [ ] Test main-create failure, related create only after main success, lost related-create response reconciliation, link-write replay, and retrying one failure without repeating completed creates.
- [ ] Implement durable per-step state keyed by collection/user identity using existing local recovery patterns; verify current identity before resuming.
- [ ] Create staged native related entities only after main success, then call the idempotent link endpoint. Default their location from the main form while allowing independent edits.
- [ ] Surface the successful main item and exact pending/failed related step; never close out or repeat a successful native create as a retry shortcut.
- [ ] Run focused flow and browser fixtures; expected: retries issue only unresolved steps.

### Task 5: Saved item detail editing for packaging, custom fields, and related links

**Files:**
- Modify: `deploy/build-homebox-ui.py` item detail transform and add a focused component mount
- Create: `homebox-ui/overlay/components/Workshop/ItemMetadataPanel.vue`
- Modify: `homebox-ui/overlay/lib/item-metadata.js`
- Modify: `tests/item_metadata.browser.mjs`

**Interfaces:** Detail panel consumes native item data plus `GET item-metadata`; saves Homebox packaging/custom fields through the native item update, then saves Notes with an idempotent key. Related item add/remove uses the declared endpoints, existing-item selection uses authenticated Homebox search, and visible links resolve by native UUID.

- [ ] Add detail fixture cases for load/edit/save packaging, Name/Value/Note, relation visibility from either item, removal from either side, inaccessible targets, and failed metadata save.
- [ ] Implement the focused detail panel, preserving native field IDs, unrelated native fields, and item permission checks; mount it on generated `pages/item/[id]/index.vue`.
- [ ] Show explicit unavailable states for stale relation targets; do not resolve stale links by name.
- [ ] Run item-detail builder and browser fixtures; expected: details remain editable and relation changes are symmetric.

### Task 6: Custom-field Inventory search

**Files:**
- Modify: `deploy/build-homebox-ui.py` Inventory search transform
- Modify: `homebox-ui/overlay/lib/child-item-groups.js` for a focused custom-field match helper, then call it from the existing Inventory projection
- Modify: `tests/test_equipment_search_builder.py`
- Modify: `tests/equipment_search.test.mjs`

**Interfaces:** Search includes native custom-field names/values in the already-loaded, authenticated `equipmentRows` used by the existing Inventory projection. Merge these matches with native search results by item UUID. Keep native filters, pagination, group expansion, and existing search precedence unchanged.

- [ ] Add unit cases proving a barcode/tracking value finds its item and hidden or unloaded items are not introduced by search.
- [ ] Add builder assertion that the generated Inventory search projection includes native field values.
- [ ] Implement matching in the existing `projected` item filter using native `fields` from `equipmentRows`; do not add an unscoped secondary fetch.
- [ ] Run focused Inventory search tests; expected: custom values match and existing filters/group counts remain stable.

### Task 7: Cross-feature builder and recovery review

**Files:**
- Modify: `tests/test_homebox_ui_builder.py`
- Modify: `tests/test_desktop_api_equipment_catalog.py` for retained generated-ID behavior

- [ ] Add a builder-level regression covering exactly one global OCR popover, create launcher targeting, no template UI, and generated-ID assignment still present.
- [ ] Add a regression confirming existing template records remain readable through the backend API and are not deleted by UI changes.
- [ ] Run focused Python/Node fixture suites from Tasks 1–6 in isolated fixtures only; do not point mutation tests at operational Homebox.
- [ ] Review the diff for credentials, databases, unintended Homebox rebuild artifacts, unrelated source changes, and changes to existing IDs or QR routes.
