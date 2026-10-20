# Grouped Equipment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let staff search a shared product/model group and compare its individually tracked physical units, current availability, storage, and recent return notes.

**Architecture:** Keep Homebox entities as the authority for each item. Group records automatically when both manufacturer and model are present and match after trimming, case-folding, and collapsing whitespace; do not normalize punctuation or infer membership from names/serials. Allow managers to define an explicit custom group for incomplete or inconsistent model metadata using a reserved native tag, subject to Task 1's API safety check. Build results in the existing C-Crate Equipment page from native stock and history data.

**Tech Stack:** Existing C-Crate Python companion API, Homebox native entity/tag APIs, Workshop browser JavaScript and CSS, Python unittest and Node built-in test runner; manual UI review for browser presentation.

**Spec:** `docs/research/2026-10-16-inventory-browsing-and-grouping.md`

## Global Constraints

- “Homebox is the inventory and account authority. Preserve native identities, metadata, access rules and history.”
- “Never run demo-creating or mutation checks against an operational Homebox instance. Use fake clients or isolated temporary fixtures; never connect local tests to the live Pi.”
- “Never automatically repeat an uncertain create, save, badge issue, replacement or print. Keep its request identity and use Recovery/status checks.”
- “Do not restart or deploy services, print physical output, or change operational data unless the user explicitly authorizes that action.”
- “Make the smallest complete change. Reuse existing Homebox APIs, UI components and helpers. Do not add dependencies or unrelated features.”
- Preserve current collection authorization and the native UUID, serial, quantity, parent, condition, checkout, maintenance, and return-note history for every item.
- A status count counts physical entity records, not the sum of their `quantity` values.
- Automatically group only exact normalized manufacturer + model field pairs. Similar model/manufacturer values, name matches, or serial values never establish group membership.
- Cabinet-wide location browsing is a separate feature and is not part of this implementation.

## Review Focus

- Empty or partial manufacturer/model/serial values: searchable fields remain optional, do not block item display, and do not create an inferred model group unless both manufacturer and model are present.
- Duplicate serial numbers: both records remain separate and visible; serial is not a group or unique key.
- Similar but different models: exact manufacturer/model pairs remain separate unless a manager explicitly assigns a custom group. A custom assignment overrides the automatic pair for that item.
- Archived, checked-out, blocked, unreviewed, and quantity-greater-than-one entities: group totals and status labels follow the established entity-level checkout rules and do not imply they can be checked out.
- Missing or inaccessible note history: the group and member rows still render; show a scoped history-unavailable state rather than hiding or reassigning notes.

---

## File map

- `ops/desktop_api.py`: add manager-only custom-group assignment/removal actions and a collection-scoped read of recent group-member notes after native tag update behavior is confirmed. `entities()` already returns full native entity details, including tags, so do not add a redundant equipment response field. Automatic model grouping requires no write route.
- `homebox-ui/overlay/lib/equipment-groups.js`: pure grouping/search/count helpers, exported for deterministic Node tests.
- `homebox-ui/overlay/lib/workshop-tools.js`: add Equipment search fields, explicit group assignment, grouped results, per-unit status rows, and lazy group notes.
- `homebox-ui/overlay/assets/css/workshop.css`: style the grouped result and responsive member rows using existing theme tokens.
- `tests/test_desktop_api.py`: test route authorization, tag membership writes, and failure behavior against fake native APIs. Add tests for reserved-prefix collision and repeated/overlong custom names.
- `tests/equipment_groups.test.mjs`: test pure grouping, search, counts, and note aggregation with synthetic entities/histories.

## Task 1: Confirm and expose safe custom group membership (fallback only)

**Purpose:** This task only enables user-defined groups when model metadata is incomplete; the automatic exact-model workflow in Task 2 must remain functional if the tag safety gate fails.

**Files:**
- Modify: `ops/desktop_api.py`
- Test: `tests/test_desktop_api.py`

**Interfaces:**
- Consumes: Homebox entity detail and native tags, `client.call`, existing manager/collection context, and the `entities()` read path used by Workshop equipment.
- Produces: manager-only POST routes `equipment/groups/assign` and `equipment/groups/remove` for custom groups. Both accept `{entity_id: string, group_name: string}` and return the updated entity’s `{id, tags}`. Automatic manufacturer/model grouping needs no write route.

- [ ] **Step 1: Add `test_custom_group_assign_preserves_native_tags`, `test_custom_group_remove_preserves_other_tags`, and `test_custom_group_reassignment_requires_remove`** to `tests/test_desktop_api.py`; assert the entity UUID, membership result, unchanged unrelated tags and metadata, and refusal to replace an existing custom group implicitly.
- [ ] **Step 2: Add `test_custom_group_changes_require_manager`** to `tests/test_desktop_api.py`; assert a non-manager receives 403 and the fake Homebox client records no write.
- [ ] **Step 3: Run `python3 -m unittest tests.test_desktop_api -v`.** Expected: the new tests fail because the routes are not implemented.
- [ ] **Step 4: Verify Homebox tag API semantics** against the repository's pinned Homebox source and a fake client. Use the established full-entity update pattern in `ops/native_fields.py`: fetch the entity, preserve all fields and native properties, update only `tagIds`, write once, then fetch and verify. Tests must prove parent, entity type, fields, unrelated tags, and identity are preserved. If this safety gate fails, omit custom groups and deliver automatic exact-model grouping; do not create companion persistence or patch Homebox implicitly.
- [ ] **Step 5: Implement the narrow native operation** in `ops/desktop_api.py`; use a reserved `C-Crate Product group: ` tag prefix, normalize surrounding whitespace, reject empty/overlong names, detect prefix collisions and duplicate native tags, and call `require_manager(ctx)` before any native write. Look up an exact existing group tag before creating one; if creation outcome is uncertain, re-read tags before any retry. Refuse implicit reassignment: remove the existing custom group explicitly before assigning another. Ordinary tags remain unchanged.
- [ ] **Step 6: Run `python3 -m unittest tests.test_desktop_api -v`.** Expected: all custom group API tests pass and existing API tests remain unchanged.

## Task 2: Search and compare grouped physical units

**Files:**
- Modify: `homebox-ui/overlay/lib/workshop-tools.js`
- Modify: `homebox-ui/overlay/assets/css/workshop.css`
- Create: `homebox-ui/overlay/lib/equipment-groups.js`
- Test: `tests/equipment_groups.test.mjs`

**Interfaces:**
- Consumes: equipment rows with full native tags and the manager-only membership operations from Task 1; existing `held(id)`, `equipmentBlocker(item)`, `checkoutCartStatus(id)`, and `showItem(id)`.
- Produces: an Equipment page result grouped by exact normalized manufacturer/model pair, or by a manager-defined custom group when explicitly assigned. Custom membership overrides derived grouping for that item. Records without both model fields and without a custom group remain visible as individual rows. Groups have detail/expand actions, count summaries, member rows, and manager-only custom-group controls.

- [ ] **Step 1: Add `groupsSearchesModelManufacturerSerialAndStorage`, `groupsExactNormalizedManufacturerModelPairs`, `groupsCustomMembershipOverridesDerivedModel`, `similarModelsStaySeparate`, and `groupCountsPhysicalRecordsBySnapshotStatus`** to `tests/equipment_groups.test.mjs`; assert partial fields, serial-only matches, ungrouped records, punctuation differences, and mixed status counts.
- [ ] **Step 2: Run `node --test tests/equipment_groups.test.mjs`.** Expected: failures because the helper is not implemented.
- [ ] **Step 3: Implement group projection and search** in `workshop-tools.js`. Search name, asset code, storage path, manufacturer, model, serial, and custom group name. Derive automatic groups only from exact normalized manufacturer + model pairs; a custom group tag takes precedence. Count entity records (never quantity); present status categories separately: available for checkout, checked out, blocked/needs review, and archived. Label counts as the current loaded snapshot, keep condition and quantity visible per unit, and let existing checkout revalidate the chosen item.
- [ ] **Step 4: Render the expanded grouped rows** in `workshop-tools.js` and `workshop.css`, inheriting current theme tokens, using visible text for status, preserving keyboard focus and touch target sizes, and stacking columns on narrow displays.
- [ ] **Step 5: Run `node --test tests/equipment_groups.test.mjs`.** Expected: search and group projection cases pass.
- [ ] **Step 6: Manually inspect** desktop and 800×480 layout, keyboard access, textual statuses, manager-only assignment controls, and exact item links using the supported local app with fixture data.

## Task 3: Add recent notes to the group detail

**Files:**
- Modify: `ops/desktop_api.py`
- Modify: `homebox-ui/overlay/lib/workshop-tools.js`
- Modify: `homebox-ui/overlay/lib/equipment-groups.js`
- Test: `tests/test_desktop_api.py`
- Test: `tests/equipment_groups.test.mjs`

**Interfaces:**
- Consumes: selected group member IDs from Task 2 and a collection-scoped `POST history/group` read route accepting at most 100 distinct entity IDs. The UI must disclose when a group exceeds this cap and request notes for its first 100 stable, sorted members; member rows remain complete.
- Produces: up to five newest return notes across the selected group, ordered by `created_at` descending. The route validates every item against the signed-in collection before returning history; each entry includes source entity ID. The UI shows source item, serial or asset code when available, author, timestamp, and note text; selecting its source opens that physical item.

- [ ] **Step 1: Add `test_group_history_validates_collection_entities` and `test_group_history_returns_latest_entity_linked_notes`** to `tests/test_desktop_api.py`; assert foreign/missing entity rejection and source-ID attribution.
- [ ] **Step 2: Run `python3 -m unittest tests.test_desktop_api -v`.** Expected: the new route tests fail before implementation.
- [ ] **Step 3: Add `groupNotesAreOrderedAndCappedAtFive` and `groupNotesFailureKeepsMembers`** to `tests/equipment_groups.test.mjs`; assert order, source link data, empty state, and non-blocking history failure.
- [ ] **Step 4: Run `node --test tests/equipment_groups.test.mjs`.** Expected: aggregation tests fail before implementation.
- [ ] **Step 5: Implement `POST history/group` as a read-only POST route** and add it to `READ_POSTS`; use the existing collection context and history readers; reject malformed, duplicate, missing, or foreign IDs before reading; aggregate entity-specific return-note history, deduplicate, sort newest-first, and cap server output at 100. Keep every note’s source entity ID. This endpoint must not write to native inventory or the operation ledger.
- [ ] **Step 6: Load history only after a group is expanded**, render the five newest return notes, and keep maintenance logs in their existing surfaces.
- [ ] **Step 7: Run `python3 -m unittest tests.test_desktop_api -v` and `node --test tests/equipment_groups.test.mjs`.** Expected: notes remain attributed to their source entity and unavailable history does not hide member rows.

## Task 4: Whole-feature verification and handoff

**Files:**
- No additional production files unless a focused review finds a defect.

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: verified grouped Equipment workflow and a short implementation receipt listing checks run and known limitations.

- [ ] **Step 1: Run** `python3 -m unittest tests.test_desktop_api -v` and `node --test tests/equipment_groups.test.mjs` using isolated fixtures only.
- [ ] **Step 2: Review the UI at desktop and 800×480**, confirming the storage path, serial/asset identifier, status, and group heading remain readable without horizontal loss; verify visible keyboard focus.
- [ ] **Step 3: Review the change** for collection/manager authorization, native metadata preservation, note attribution, stale read behavior, and no changes to live Homebox or deployment state.
- [ ] **Step 4: Record test commands, outcomes, and deferred decisions** in the implementation receipt. Do not deploy or restart the Pi service as part of this plan.

## First-version product decisions

- Default grouping uses exact normalized manufacturer + model fields without writes or setup. Trim and case-fold values and collapse repeated whitespace; preserve punctuation and accents so distinct labels are not silently combined.
- Custom grouping uses a reserved `C-Crate Product group: ` native tag, hidden behind manager-only controls, for incomplete/inconsistent model metadata. Task 1 is a safety gate for this fallback only; automatic model groups ship even if native tag updates cannot be proven safe.
- One custom group per item; custom membership overrides its derived model group. Ordinary tags remain independent.
- Recent notes means C-Crate return notes only in the first version. Maintenance remains a separate history until product review says to combine it.
- Location subtree browsing is a separate plan, not a dependency of grouped Equipment.

## Demonstration workflow

1. Staff search `Mavic 3 Classic`; records with the same manufacturer/model fields appear together immediately. Search also matches item names, serials, storage paths, and custom group labels.
2. Staff expand the model group and see every member as its own row, including serial/asset ID, location, condition, quantity, current status, and an item link. The heading counts physical records by status.
3. If a unit has incomplete or inconsistent model fields, a manager can explicitly place it into a custom group. Similar text alone never adds it automatically.
4. Staff open recent return notes; each note names and links to its source unit. If history is unavailable or the group exceeds the history cap, equipment rows remain usable and the notes state the limitation.
5. Staff choose a specific available unit and continue through the existing checkout flow, which revalidates that physical record.
