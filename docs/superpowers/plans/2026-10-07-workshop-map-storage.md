# Connected Workshop Map and Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect native search, storage guidance, rack views, setup coverage, photos and equipment status in both existing Workshop interfaces.

**Architecture:** Add one shared native read/query module beside the existing layout store; keep schema-specific persistence in `ops/workshop.py`. Both established JavaScript hosts render the same server semantics. A narrowly added NativeJobs kind journals shelf presentation updates without changing native containment.

**Tech Stack:** Existing Python stdlib/SQLite, native Homebox APIs, Terminal JavaScript, native Nuxt overlay, installed Playwright/Chromium; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-07-workshop-map-storage-design.md`; also read `docs/superpowers/specs/2026-10-07-workshop-redesign-design.md`.

## Global Constraints

- Homebox remains the inventory authority; preserve native UUIDs, optional mixed item/location parents, attachments, custom fields, QR payloads, loan history and native permissions.
- Preserve both distinct locations named The Cage and the Cage; never merge records because their names look alike.
- Drawing changes never change native containment. A native move or rename is a separately confirmed native operation.
- Preserve current companion layouts and legacy native `Workshop map room` / `Workshop map object` fields. No automatic conversion or synchronization between their different coordinate systems.
- Keep all runtime assets local; add no external service or dependency for these stages.
- Support the 800 × 480 Terminal with controls at least 44 CSS pixels in height, keyboard operation, visible focus, and text alternatives to the drawing and status colors.
- Derive collection, actor and permissions on the server. Desktop uses native authenticated Workshop context; Terminal retains its existing authorization model. New management writes require management access at confirmation.
- Preserve uncertain operations for explicit recovery; never automatically repeat a create, upload or physical print.
- Product verification uses disposable Homebox instances and temporary fixtures. No live demo records, physical prints, service restarts or deployment are authorized by these documents.
- Execute one Luna Medium coding task at a time; Sol High reviews architectural and risk-sensitive changes, with fixes and renewed verification before acceptance.

## Review Focus

1. Same-looking Cage names, mixed item parents and multiple drawings must preserve identity and require a choice: Task 1 `test_mixed_path_and_duplicate_cage_identity`.
2. Held Ready, Broken-held, quantity blockers, Unreviewed and deep duplicated descendants must produce record counts without borrower leakage: Task 2 `test_scope_counts_and_private_custody`.
3. Malformed/stale shelf order must remain browsable; interrupted updates must not replay: Tasks 2/3 `test_invalid_order_keeps_other_children_reachable`, `test_lost_order_response_recovers_without_put`.
4. Foreign links/photos and revoked management must fail closed without returning filesystem paths or using badge identity as manager authority: Task 4 `test_view_photo_tenancy_and_revoked_manager`.
5. Refresh, changed accounts, revision conflicts and rotated legacy geometry must preserve/suspend drafts and prevent navigation edits: Tasks 5/6 `test_desktop_dirty_refresh_and_identity`, `test_terminal_browse_rotation_and_conflict`.

---

## Execution prerequisites and file boundaries

This document authorizes drafting only. Product execution requires accepted plan, completed preceding queue (member/profile/release fixes, label editor), and a preserved isolated snapshot of all current tracked **and untracked** source needed here. A plain HEAD worktree omits essential overlays. Verify matching build/runtime baseline before coding. Run one Luna Medium implementer per task, then Sol High review; fix findings, repeat affected verification, obtain renewed review before acceptance or the next task; Sol reviews committed BASE..HEAD diffs. Final whole-branch Sol review is required. No deployment/release selection is authorized. All commands below run from the isolated repository at execution time; reuse installed dependencies.

Create `ops/workshop_views.py` for hierarchy/selection/coverage/status/rack queries, not geometry persistence. Extend `ops/workshop.py` for native shelf-order mutation/recovery and `ops/native_jobs.py` for its supported kind. Reuse the existing authorized Terminal `/api/file` handler and native photo endpoints. Add adapters in `ops/desktop_api.py` and the existing `deploy/kiosk-server.py`; preserve their auth/origin/lock protections. UI changes stay within the two current hosts and assets; do not copy or reorganize unrelated loans/imports/users code. Add focused fixture/tests and one disposable verifier, never adapt an old live `verify-workshop-*` script as an acceptance command.

### Task 1: Native selection, paths and setup coverage

**Files:** Create `ops/workshop_views.py`, `tests/test_workshop_views.py`; modify `tests/test_workshop.py` only if a shared existing fixture needs extension.

**Interfaces:** Consume `client.entity(UUID)`, `client.entities(locations=False)`, `Workshop.get(group) -> {revision,layout}`, `hierarchy.validate_parent(client,parent,entity_id=None)` for ancestry safeguards. Produce exactly:

```python
scoped_equipment(client, location_id: str, *, include_nested: bool = False) -> list[dict]
build_view(client, layout_state: dict, custody: list[dict], *, entity_id: str | None = None, include_nested: bool = False, room_id: str | None = None, can_view_loans: bool = False) -> dict
resolve_workshop_code(client, raw: str) -> dict
```

`room_id` is None in Stage 1. Return `selection:{target_id,destination_id,kind:'exact'|'containing'|'unmapped'|'unavailable',matches:[{room_id:str|None,drawing_id:str,location_id:str}]}`, `path:[{id,name,is_location,parent_id}]`, `contents:list[dict]`, `include_nested:bool`, `counts:{assigned,checked_out,available,needs_attention}`, `coverage:list[dict]`, `rack:{ordered:list[dict],unordered:list[dict],errors:list[dict]}|None`, `photos:list[dict]`, `errors:list[dict]`, `refreshed_at:str` (UTC ISO 8601). Contents retain native item dictionaries plus derived status. Task 2 fills status/rack/photos. Coverage rows use `{location_id,drawing_id,kind,covered_by,matches,message}` with kinds `exact`, `containing`, `unmapped`, `drawing_only`, `unavailable`, `multiple`, `legacy_review`; emit separate legacy review rows without importing coordinates. Errors use `{code,entity_id,drawing_id,message}`. `resolve_workshop_code` returns `{kind,entity_id:UUID|null,candidates:[{id,name,is_location,asset_id,path}],message}`; reuse `scan_codes.normalize/resolve_equipment`, active native asset/UUID resolution, full collection entities and the same path builder; ambiguity/badge/foreign/unknown select none.

1. - [ ] Write `WorkshopViewTests` with temporary layout and fake tenant client fixtures: two separate Cage UUIDs, Cage→Rack→Shelf→box→tool, 70 mixed ancestors, duplicate entity summaries, duplicate rack drawings, drawing-only object and archived/foreign links. Named test assertions:

```python
def test_mixed_path_and_duplicate_cage_identity(self):
    v = build_view(self.client, self.state, [], entity_id=self.tool)
    assert [p['id'] for p in v['path']] == [self.cage, self.rack, self.shelf, self.box, self.tool]
    assert v['selection']['kind'] == 'containing'
    assert {m['drawing_id'] for m in v['selection']['matches']} == {self.drawing_a, self.drawing_b}
    assert self.other_cage not in [p['id'] for p in v['path']]
    assert self.client.writes == []
```

Add `test_exact_requires_immediate_location_parent`, `test_unavailable_and_cycles_preserve_layout`, `test_coverage_separates_indirect_and_legacy`; assert mapped shelf/direct tool is exact, boxed tool remains containing, corrupt ancestry is diagnostic and unchanged saved state, foreign links never redirect by name, indirectly covered bins are covered by rack, and legacy fields never write. `test_query_ambiguity_and_unknown_codes` asserts `entity_id is None` for duplicate serial/foreign/unknown codes and visible UUID/path matches for ambiguity. `scoped_equipment` raises for unavailable/foreign root or cyclic ancestry; `build_view` returns safe diagnostics preserving geometry.
2. - [ ] Run `PYTHONPATH=ops:kiosk:work/hardware/python python3 -m unittest discover -s tests -p 'test_workshop_views.py' -v`; expect missing-module/signature failure.
3. - [ ] Implement the signatures with a per-read native graph and UUID sets. Direct scope includes directly assigned item containers; nested follows mixed item/location edges and deduplicates active items. Nearest active valid linked ancestor wins; retain all representations for explicit choice. No selection returns setup coverage and empty selected scope.
4. - [ ] Run the same command and focused existing `test_workshop.py` command; expect all PASS, zero native writes and existing dimension/object/revision protections intact.
5. - [ ] Implementer self-reviews the task diff against its spec, assertions and safeguards.
6. - [ ] Stage only listed task files; `git commit -m "feat: resolve workshop native paths and coverage"`.
7. - [ ] Sol High reviews committed BASE..HEAD; send findings to Luna for fixes, affected tests and fix commits, then scoped Sol re-review before acceptance/next task.

### Task 2: Rack order, status and recognition descriptors

**Files:** Modify `ops/workshop_views.py`, `tests/test_workshop_views.py`.

**Interfaces:** Consume Task 1 signatures and `conditions.condition(entity)`, `conditions.checkout_blocker(entity)`, `native_fields.text_field(entity,name)`, `ledger.custody(group)`. Produce completed `build_view` fields; `photos` is `{id,title,primary,alt}` descriptors only, primary first, no disk paths or credentials. Rack rows retain UUID/name/code/parent identity.

1. - [ ] Add assertions:

```python
def test_scope_counts_and_private_custody(self):
    v = build_view(self.client, self.state, self.custody, entity_id=self.shelf, include_nested=True)
    assert v['counts'] == {'assigned':5, 'checked_out':2, 'available':1, 'needs_attention':2}
    assert len({e['id'] for e in v['contents']}) == 5
    assert 'Private Borrower' not in json.dumps(v)
    assert v['include_nested'] is True
```

Fixture records: one Ready available, Ready held, Broken held, Ready quantity 2 blocked, Unreviewed; archived sixth excluded. `test_direct_scope_includes_box_without_descendants` asserts only immediate items unless nested. `test_invalid_order_keeps_other_children_reachable` asserts explicit listed shelves ordered bottom-to-top, new unlisted shelves unordered, stale/duplicate/malformed/wrong-type field errors visible, and nonshelf children reachable in the existing native child list. `test_numeric_order_and_photos` asserts 2 before 10, equal numeric code ties name then UUID, nonnumeric/empty codes unordered, native primary first.
2. - [ ] Run `PYTHONPATH=ops:kiosk:work/hardware/python python3 -m unittest discover -s tests -p 'test_workshop_views.py' -v`; expect count/order/photo assertion failures.
3. - [ ] Complete read projection. Available requires no custody and no blocker; needs-attention means non-Ready/Unreviewed, counts overlap and count records. Respect loan visibility, redact borrower identities throughout returned content/errors. Parse `Workshop shelf order` JSON `{version:1,shelf_ids:[UUID,...]}`; read errors never hide the rack. Numeric finite storage codes order numerically, never infer levels from names. Preserve original captions; linked labels derive current native names.
4. - [ ] Run focused views and `test_conditions.py`; expect PASS with native attachments/fields unchanged.
5. - [ ] Implementer self-reviews the task diff against its spec, assertions and safeguards.
6. - [ ] Stage only task files; `git commit -m "feat: share rack and equipment status views"`.
7. - [ ] Sol High reviews committed BASE..HEAD; send findings to Luna for fixes, affected tests and fix commits, then scoped Sol re-review before acceptance/next task.

### Task 3: Durable shelf-order update and inspection recovery

**Files:** Modify `ops/workshop.py`, `ops/native_jobs.py`, `tests/test_workshop.py`, `tests/test_native_jobs.py`.

**Interfaces:** Consume `NativeJobs.prepare/sent/context/review/bind/complete/cancel/detail`; add supported kind `workshop_shelf_order`. Produce:

```python
submit_shelf_order(client, jobs, group: str, actor: str, request_key: str, data: dict) -> dict
recover_shelf_order(client, jobs, group: str, job_id: str, outcome: str) -> dict
```

Data is `{entity_id:UUID,updated_at:str,shelf_ids:list[UUID]|None}`; None removes only the order field. Result `{id:jobUUID,status,entity_id:UUID}`; completion of an existing identical key returns confirmed result without PUT.

1. - [ ] Add `test_lost_order_response_recovers_without_put` and validation/metadata tests:

```python
def test_lost_order_response_recovers_without_put(self):
    with self.assertRaises(OSError): self.submit_order(fail_after_put=True)
    job = self.jobs.unresolved(self.group)[0]
    assert job['status'] == 'review'
    before = len(self.client.writes)
    result = recover_shelf_order(self.client, self.jobs, self.group, job['id'], 'complete')
    assert result['status'] == 'completed'
    assert len(self.client.writes) == before
```

`test_order_validation_and_metadata_preservation` asserts stale version, non-Rack, nonchild/non-Shelf/foreign/duplicate UUIDs, duplicate/wrong-type native fields and serialization above 8000 characters **or UTF-8 bytes** fail before PUT. Successful PUT preserves parent, tags, attachments, description, other fields and native IDs. `test_order_restart_key_conflict_and_cancel` asserts pending context survives restart, changed payload/actor key conflicts, uncertain cancellation requires unchanged original field/child fingerprint and unavailable/third-state results remain review.
2. - [ ] Run `PYTHONPATH=ops:kiosk:work/hardware/python python3 -m unittest discover -s tests -p 'test_workshop.py' -v` and `PYTHONPATH=ops:kiosk:work/hardware/python python3 -m unittest discover -s tests -p 'test_native_jobs.py' -v`; expect missing-function/unsupported-kind failure.
3. - [ ] Validate before preparing; record desired field, original field, original `updatedAt`, rack ID and immediate Shelf UUID fingerprint. Re-read latest metadata/version/membership before send; use `native_fields.update_payload` and edit only the text field. Mark sent durably before the single PUT; exception/readback mismatch becomes review. Repeated pending keys never send; completed keys return status. Recovery only reads: complete requires desired field and original validated membership, cancel requires original field and fingerprint; otherwise explicit review/new confirmation. Never recover by calling creation recovery or replaying PUT. A native full PUT cannot be atomic against external writers: preserve all latest fetched metadata, detect version changes where observable, and state that limitation without claiming CAS.
4. - [ ] Rerun both focused commands; expect PASS and exactly one PUT across lost-response/restart/recovery.
5. - [ ] Implementer self-reviews the task diff against its spec, assertions and safeguards.
6. - [ ] Stage only task files; `git commit -m "feat: journal native workshop shelf order"`.
7. - [ ] Sol High reviews committed BASE..HEAD; send findings to Luna for fixes, affected tests and fix commits, then scoped Sol re-review before acceptance/next task.

### Task 4: Bound routes, photo authorization and recovery dispatch

**Files:** Modify `ops/desktop_api.py`, `deploy/kiosk-server.py`, `homebox-ui/overlay/composables/use-workshop.ts`, `tests/test_desktop_api.py`; create `tests/test_workshop_routes.py`.

**Interfaces:** Consume Tasks 1–3. Produce Desktop GET `/workshop-api/workshop/view?id=<UUID>&nested=0|1` (optional id), Terminal POST `/workshop/view` `{entity_id:null|UUID,include_nested:boolean}`; preserve existing GET workshop/POST workshop/get. Read-only POST `/workshop-api/workshop/resolve` and `/workshop/resolve` accept `{code:str}`, return `resolve_workshop_code`, before management-write gates. Desktop POST `/workshop-api/workshop/shelf-order` and Terminal POST `/workshop/shelf-order` accept Task 3 data plus `request_key`. Photos reuse Terminal GET `/api/file?entity=<UUID>&attachment=<UUID>` and Desktop GET `/api/v1/entities/{entity_id}/attachments/{attachment_id}`; no second downloader or photo route. Reserve optional `room_id` extension for Stage 2; Stage 1 rejects non-None room selection.

1. - [ ] `test_view_photo_tenancy_and_revoked_manager` and `test_read_route_parity_and_order_recovery_dispatch` assert:

```python
assert desktop_view['selection'] == terminal_view['selection']
assert foreign_photo.status == 404  # Existing Terminal handler conceals inaccessible files.
assert revoked_order.status == 403
assert stale_identity.status == 409
assert fake_native.put_count == 0
assert terminal_order_actor == configured_native_admin_id
assert terminal_order_actor != scanned_member_id
```

Also add `test_resolve_foreign_ambiguity_badge_unknown_and_parity`: assert both routes return no selected UUID for those four inputs, distinct UUID/path candidates for ambiguity, identical valid results and zero enrollment/native writes. Assert invalid nested types rejected, photos reference selected entity attachments, no paths/secrets, both status/recovery paths find original order job and inspect only, disabled manager rejects mutations. Terminal tests load only after configuring a fresh temporary ROOT: current top-level ROOT opens operational SQLite files.
2. - [ ] Run `PYTHONPATH=ops:kiosk:work/hardware/python python3 -m unittest discover -s tests -p 'test_desktop_api.py' -v` and `PYTHONPATH=ops:kiosk:work/hardware/python python3 -m unittest discover -s tests -p 'test_workshop_routes.py' -v`; expect 404/new-handler failure.
3. - [ ] Add handlers using authenticated tenant client/custody. In `desktop_api.handle(handler,deps)`, selectively call `binding(handler,ctx)` for view GET; `useWorkshop.request` sends identity for it. Resolve POST uses `request`, not `write`/pending. Terminal derives OPEN_ADMIN service-account actor, tenant and session context; view/resolve require no management. Reuse the preceding matched-release launcher's `WORKSHOP_ROOT` for fixture isolation and packaged code-root imports. Load handlers with the existing source-prefix harness after substituting temporary globals; do not introduce a competing bootstrap or test-only production environment variable. Existing `/api/file` enforces entity/attachment ownership, a 10 MB byte limit, allowed local redirects, nosniff and no-store; retain it and verify wrong-entity/foreign attachments are unavailable. Add both recovery-kind branches, order intent/messages and operation-status plumbing; no second outer journal. Retain origin/management/lock checks and loan privacy.
4. - [ ] Run both focused commands and `test_attachments.py`, `test_workshop_gateway.py`; expect PASS without native/live IO.
5. - [ ] Implementer self-reviews the task diff against its spec, assertions and safeguards.
6. - [ ] Stage only task files; `git commit -m "feat: expose authorized workshop storage views"`.
7. - [ ] Sol High reviews committed BASE..HEAD; send findings to Luna for fixes, affected tests and fix commits, then scoped Sol re-review before acceptance/next task.

### Task 5: Desktop connected browse and draft-safe editing

**Files:** Modify `homebox-ui/overlay/lib/workshop-tools.js`, `homebox-ui/overlay/assets/css/workshop.css`, `homebox-ui/overlay/pages/workshop/[tool].vue`, `homebox-ui/overlay/components/Workshop/InsideActions.vue`; create `deploy/verify-workshop-map-disposable.py`, `tests/test_workshop_browser.py`.

**Interfaces:** Consume view/order routes and existing `useWorkshop.write`. Extend `mountWorkshopTools(root,initialPage,workshop,navigate,notify,initialSelection={entityId:null,drawingId:null,roomId:null})`; existing five-argument callers remain valid. The Vue wrapper maps route query `id`, `drawing_id`, `room_id` to that option. Add host-local `refreshWorkshopView(entityId=null,includeNested=false) -> Promise<void>` and `selectWorkshopEntity(entityId:string) -> Promise<void>`; render server results without replacing dirty geometry. `InsideActions.vue` already appears on both native item/location pages; add a Show on map link to `/workshop/map?id={native UUID}` alongside its current actions. Verifier `run_checks(*, interface:str, port:int=0, native_port:int=0, outputs:str='disabled') -> None` allocates fresh temporary root/databases, serves isolated matched assets and disposable native fixtures, disables physical outputs and accepts only test endpoints; no operational defaults or port 17749.

1. - [ ] Browser `test_desktop_dirty_refresh_and_identity` and `test_desktop_search_rack_coverage_photos` assertions include:

```python
assert page.locator('[data-workshop-caption]').inner_text() == 'Old drawing name'
assert page.get_by_text('Assigned storage: Storage Room / the Cage / Rack 1 / Rack 1-A').is_visible()
assert draft_after_refresh == draft_before_refresh
assert native_writes_after_browse == []
assert page.get_by_text('Status unavailable', exact=True).is_visible()
assert suspended_draft_identity == original_identity
```

Assert native item/location Show on map links initialize the correct server-resolved selection, native-record/photo-editor return restores that location, explicit representation choice, subtree toggle/filter counts, rack order confirmation/recovery, full identity/path for ambiguous results, overlays initially off, keyboard drill-down and long names. Unknown/manufacturer-only codes never create or navigate scanned URLs.
2. - [ ] Run `PYTHONPATH=ops:kiosk:work/hardware/python python3 -m unittest discover -s tests -p 'test_workshop_browser.py' -v`; expect missing UI controls/guidance failure in isolated fixtures.
3. - [ ] Extend map/storage host functions; use Task 4 resolve route for scanned/manual codes and existing authorized equipment/location reads for search by native name, asset code, serial/manufacturer metadata. Results show native names/full path/UUID. Render labels/captions, setup states, native children, gallery with aspect ratio/alt text, destination/borrowing guidance, status labels and record-count explanation. Browse/Edit gates writes. Refresh on open/selection/manual/visible return and every 30 seconds while visible; ignore stale responses. Failed refresh invalidates availability. Preserve dirty geometry/base revision; suspend drafts under original actor/collection on identity changes. Save conflict offers draft review/reload; retain numeric alternatives/leave prompts.
4. - [ ] Run browser command plus `python3 deploy/verify-workshop-map-disposable.py --interface desktop --port 0 --native-port 0 --outputs disabled`; expect PASS. Run `python3 deploy/build-homebox-ui.py` only from the preserved isolated snapshot with installed dependencies, output remains staged; expect successful build/type validation with documented matching baseline.
5. - [ ] Implementer self-reviews the task diff against its spec, assertions and safeguards.
6. - [ ] Stage only task files; `git commit -m "feat: connect desktop workshop browsing"`.
7. - [ ] Sol High reviews committed BASE..HEAD; send findings to Luna for fixes, affected tests and fix commits, then scoped Sol re-review before acceptance/next task.

### Task 6: Terminal parity and complete isolated acceptance

**Files:** Modify `kiosk/workshop-ui.js`, `kiosk/index.html`, `deploy/verify-workshop-map-disposable.py`, `tests/test_workshop_browser.py`; extend `tests/test_workshop_routes.py` for scan parity.

**Interfaces:** Consume Tasks 1–5. Preserve `workshopOpen(entity=null)`, `workshopStorage(id)`, `workshopRefreshStorage()` and `routeScan(code,expectedOverlay=null)`; add `workshopRefreshView(entityId=null,includeNested=false) -> Promise<void>`. Map-only scan purpose calls Task 4 `/workshop/resolve` before existing badge/enrollment branches, selecting only its resolved UUID. Other scan purposes retain `/scan`; both use native normalization. Build/serve `kiosk/index.html` and `kiosk/workshop-ui.js` through existing terminal_assets paths; Desktop remains imported through `[tool].vue` and overlay-copy build.

1. - [ ] Add `test_terminal_browse_rotation_and_conflict`, `test_terminal_scan_and_desktop_selection_parity`, `test_terminal_order_recovery_and_photo_return` with assertions:

```python
assert terminal_selection == desktop_selection
assert geometry_after_pan_and_selection == geometry_before
assert saved_object_after_rotation_read == original_saved_object
assert visible_rotated_footprint == stored_bounds
assert draft_after_revision_conflict == edited_draft
assert min(button_heights) >= 44
assert lost_order_recovery_puts == 0
assert browser_errors == []
```

Exercise 800×480 touch plus keyboard: zoom/pan/fit, quarter-turn viewport/object controls, undo, rack/shelf/box drill-down, native-record/photo-editor return, stale read failure, account change suspension, dirty hierarchy rename/move refresh, duplicate Cage/representation choice, inaccessible images, no selection for ambiguous/foreign/unknown scans.
2. - [ ] Run the exact Task 5 browser and Task 4 route unittest commands; expect Terminal parity/rotation assertion failures.
3. - [ ] Extend existing Terminal adapter with same semantics and timing as Desktop, existing touch keyboard and scan cancellation/generation protection. Gate management controls with current authorization, retain original shelf-order key/status after lost response. Preserve orientation/undo and numeric editing. Define rotation as orientation within the stored width×height footprint: render quarter-turns in local coordinates to those bounds, do not silently swap width/height or migrate existing objects; intentional resize/rotation edits validate bounds through existing layout validator. Wire all leave routes to dirty prompt; refresh retains drafts and never reparents native children. Both host frontends stay thin around shared server definitions.
4. - [ ] Run `python3 deploy/verify-workshop-map-disposable.py --interface both --port 0 --native-port 0 --outputs disabled` and `PYTHONPATH=ops:kiosk:work/hardware/python python3 -m unittest discover -s tests -v`; expect complete isolated PASS. Confirm 4–200 ft bounds, 200-object cap, revision conflicts, existing journals/loan/import protections and local assets. Report physical shelf/photo recognition as outstanding human acceptance, never claim automated fixtures prove it.
5. - [ ] Implementer self-reviews final scope and checks private fixture snapshots remain on the Pi.
6. - [ ] Stage only task files; `git commit -m "feat: align terminal workshop storage navigation"`. Leave build artifacts unselected; publication/deployment needs separate authorization.
7. - [ ] Sol High reviews committed task BASE..HEAD, then the whole branch. Findings require Luna fixes, tests, fix commits and scoped Sol re-review before acceptance.
