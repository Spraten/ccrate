# Multiple Workshop Room Plans Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add named room plans in both interfaces while preserving existing geometry, native identities and recoverable revisioned saves.

**Architecture:** Normalize v1 reads without migration writes; persist v2 and atomic receipts in existing `Workshop` SQLite. Extend Stage 1's read view and both established JavaScript hosts with collection-wide concurrency.

**Tech Stack:** Existing Python/SQLite/unittest, stdlib UUIDv5, existing JavaScript/Nuxt overlay, installed Playwright/Chromium and matched-release tooling; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-07-workshop-rooms-design.md`; shared constraints: `docs/superpowers/specs/2026-10-07-workshop-redesign-design.md`.

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

- A populated legacy read or restart must preserve every value without migration writes: Task 1 `test_legacy_reads_are_stable_and_write_free`.
- Native relocation outside a root must retain the drawing and allow unrelated edits plus explicit repair: Task 2 `test_root_mismatch_survives_edit_and_can_be_repaired`.
- Lost confirmation, journal interruption and exact-key replay must not increment revision twice: Task 2 `test_receipt_recovers_interrupted_generic_journal`.
- A removed bookmark, ambiguous nearest ancestor or similar Cage names must select by UUID or show a chooser: Task 3 `test_ambiguous_and_dangling_room_selection`.
- Dirty room drafts and pending saves must stay with their original identity/collection: Tasks 4/5 `test_desktop_room_drafts` / `test_terminal_room_drafts`.

---

## Execution prerequisites and file boundaries

Before execution: accepted plan; preceding reviewed member/profile/release fixes, label editor and Stage 1 complete; isolated snapshot of required tracked **and untracked** source using the isolation workflow. Plain HEAD omits essential overlays. Record status, source hashes, matching native/frontend/Terminal/Python baseline and installed dependency paths; exclude private data. Missing matching provenance blocks execution. Commands run from the isolated repository, never during drafting; no deployment authorization.

Persistence/schema stays in `ops/workshop.py`; queries stay read-only in `ops/workshop_views.py`; adapters preserve existing auth. Both JavaScript hosts remain. No loan/import restructuring, Terminal TypeScript requirement or `ops/maps.py` changes.

Each task: one Luna Medium implementer, tests/self-review, task-only commit, Sol High committed-diff review, fixes/tests/fix commits/scoped re-review before acceptance or next task. Preserve existing dirty work. Deletion requires explicit UI confirmation and AGENTS.md destructive-action authorization.

### Task 1: Normalize documents and pin version-2 validation

**Files:** Modify `ops/workshop.py` (`layout`, `Workshop.get`); create `tests/workshop_room_fixtures.py`, `tests/test_workshop_rooms.py`.

**Interfaces:** Preserve `layout(data: dict) -> dict`. Add `normalize_document(group: str, stored: dict | None) -> dict`, `room_document(data: dict) -> dict`; `Workshop.get(self, group: str) -> dict` returns `{revision,schema_version:2,stored_schema_version:1|2,document,layout}`. Missing row: revision 0, empty rooms, layout None; logical v1: unchanged compatibility layout; persisted v2: layout None after Task 2 writer gate. Document exactly `{version:2,rooms:[{id:UUID,location_id:null|UUID,name,width,height,unit:'ft',approximate,objects:[current object format]}]}`; errors are outside geometry.

Fixture `RoomFixture()` owns temporary store/client, exposes `group,actor,legacy,room,drawing,root,shelf,document`; methods `seed_legacy() -> None`, `stored_row() -> tuple`, `request(document: dict | None = None, revision: int = 0) -> dict`, `close() -> None`. Requests supply schema 2/fresh key; SQL seeds legacy; client records writes; `addCleanup` closes fixtures.

- [ ] **1. Write named assertion-bearing tests**, including `test_document_limits_and_cross_room_ids`, with valid limits, 21 rooms, 201 objects, duplicate room/object UUIDs, malformed objects, NaN, quarter-turn/bounds checks and foreign-looking UUID syntax.

```python
def test_legacy_reads_are_stable_and_write_free(self):
    f = self.fixture; f.seed_legacy(); before = f.stored_row()
    a = f.store.get(f.group); b = Workshop(f.store.path).get(f.group)
    assert a == b and f.stored_row() == before
    room = a['document']['rooms'][0]
    assert room['id'] == str(uuid5(UUID(f.group), 'workshop:legacy-room'))
    assert room['location_id'] is None
    assert {k: room[k] for k in f.legacy} == f.legacy
    assert f.store.get(str(uuid4()))['document']['rooms'] == []
    assert f.client.writes == []
```

- [ ] **2. Run RED:** `PYTHONPATH=ops:kiosk:work/hardware/python python3 -m unittest discover -s tests -p 'test_workshop_rooms.py' -v`. Expect missing normalization/document behavior.
- [ ] **3. Implement signatures.** Normalize UUIDs/captions/coordinates/rotation/unit/approximate verbatim, without rounding or geometry revalidation. Writes enforce existing name/object rules, 4–200 ft, 200 objects/room, 20 rooms, collection-wide object UUID uniqueness and supported versions; permit duplicate native names.
- [ ] **4. Verify GREEN** with the RED command and `PYTHONPATH=ops:kiosk:work/hardware/python python3 -m unittest discover -s tests -p 'test_workshop.py' -v`; existing single-layout behavior still passes before the writer gate.
- [ ] **5. Self-review and commit** only these files: `git add ops/workshop.py tests/workshop_room_fixtures.py tests/test_workshop_rooms.py`; `git commit -m "feat: normalize versioned workshop room documents"`.
- [ ] **6. Sol review** committed diff for migration preservation/limits; fix/test/fix-commit/re-review before acceptance.

### Task 2: Atomically save, gate old writers and recover receipts

**Files:** Modify `ops/workshop.py`, `ops/desktop_api.py` (`safe_intent`, `post_action`, `operation_status`), `deploy/kiosk-server.py` (Workshop save/status branches), `tests/workshop_room_fixtures.py`, `tests/test_workshop_rooms.py`, `tests/test_workshop.py`, `tests/test_desktop_api.py`; create `tests/test_workshop_room_requests.py`.

**Interfaces:** `Workshop.validate_save(self, client, group: str, data: dict) -> dict`; `Workshop.save(self, client, group: str, data: dict, *, actor_id: str) -> dict`; `Workshop.save_status(self, group: str, request_key: str, *, actor_id: str) -> dict`. Request `{schema_version:2,revision:int,document,request_key:UUID}`. Existing workshop.db adds `workshop_save_receipts(group_id,request_key,actor_id,digest,result)`, primary key `(group_id,request_key)`, committed with `plans` under `BEGIN IMMEDIATE`/FULL. Digest binds actor/canonical complete intent. Status `{status:'completed',action:'workshop/save',result:<saved envelope>}` or `{status:'not_started'}`; actor/key mismatch conflicts. Preserve generic `once`, `safe_intent(kind,data) -> dict`, `operation_status(ctx,deps,data) -> dict` signatures.

- [ ] **1. Write tests** `test_first_save_migrates_once_and_rejects_old_writer`, `test_two_sessions_and_key_reuse_conflict`, `test_receipt_recovers_interrupted_generic_journal`, `test_root_mismatch_survives_edit_and_can_be_repaired`, `test_new_root_links_require_active_collection_locations`. Extend fixture methods `move_shelf_outside_root() -> None`, `repair_request() -> dict`; preserve all native fields/photos/history in fixture before/after comparisons.

```python
def test_receipt_recovers_interrupted_generic_journal(self):
    # Fixture injects journal-completion failure after layout commit, then restarts.
    assert api.operation_status(ctx, deps, {'request_key': key})['status'] == 'completed'
    assert f.store.save(f.client, f.group, request, actor_id=f.actor) == saved
    assert f.store.get(f.group)['revision'] == saved['revision'] == old_revision + 1
    assert f.client.writes == []

def test_root_mismatch_survives_edit_and_can_be_repaired(self):
    # Arrange native move, save unrelated geometry, then confirmed compatible root.
    assert saved_unrelated['document']['rooms'][0]['objects'][0]['location_id'] == f.shelf
    assert repaired['document']['rooms'][0]['location_id'] == compatible_root
    assert f.client.writes == []
```

- [ ] **2. Run RED:** `PYTHONPATH=ops:kiosk:work/hardware/python python3 -m unittest discover -s tests -p 'test_workshop_room_requests.py' -v`. Expect missing durable receipt/recovery and schema gate.
- [ ] **3. Implement.** Require schema 2 even on v1; legacy payloads get reload rejection before journaling/replay. First explicit save increments once. Completed replay checks actor/digest before current revision/native validation; changed intent conflicts. Preflight failures stay `not_started`; revalidate revision/links inside save. Status/replay reconcile pending/review generic journal from atomic receipt without reperforming. Uncertain journal without receipt remains review; geometry equality proves nothing. Safe intent: schema/revision, room UUIDs/names/counts/document digest, no full geometry/secrets. Terminal uses service actor, generic once/status and OPEN_ADMIN gate. Adapt existing save tests to v2/actor arguments, preserving assertions.

Validate new/changed roots/links against active collection locations and mixed ancestry/cycles. Unchanged saved `(room_id,root_id,object_id,location_id)` tuples survive native mismatch/unavailability and unrelated edits, flagged for review. Changed tuples must validate; explicit compatible re-root/unlink/relink repairs. Incompatible cross-room moves fail; no automatic deletion.
- [ ] **4. Verify GREEN:** RED command, then Task 1's focused command and `PYTHONPATH=ops:kiosk:work/hardware/python python3 -m unittest discover -s tests -p 'test_desktop_api.py' -v`. Inject before/after transaction and generic-journal failures; reopening performs no migration/write.
- [ ] **5. Self-review and commit:** `git add ops/workshop.py ops/desktop_api.py deploy/kiosk-server.py tests/workshop_room_fixtures.py tests/test_workshop_rooms.py tests/test_workshop_room_requests.py tests/test_workshop.py tests/test_desktop_api.py`; `git commit -m "feat: persist recoverable workshop room saves"`.
- [ ] **6. Sol review** committed transaction/replay/gates/repair diff; fix/test/fix-commit/re-review before acceptance.

### Task 3: Extend the locked read view across plans

**Files:** Modify `ops/workshop_views.py`, `ops/desktop_api.py` (view GET), `deploy/kiosk-server.py` (view POST); create `tests/test_workshop_room_views.py`.

**Interfaces:** Keep `scoped_equipment(client, location_id: str, *, include_nested: bool = False) -> list[dict]` unchanged. Extend the existing `build_view(client, layout_state: dict, custody: list[dict], *, entity_id: str | None = None, include_nested: bool = False, room_id: str | None = None, can_view_loans: bool = False) -> dict` through its already-reserved room parameter. Desktop GET `/workshop-api/workshop/view?id=<UUID>&nested=0|1&room_id=<UUID>`; Terminal POST `/workshop/view` `{entity_id:null|UUID,include_nested:boolean,room_id:null|UUID}`; absent room preserves prior requests. Retain GET workshop / POST workshop/get and all Stage 1 result keys/types: selection, path, contents, counts, coverage, rack, photos, errors, refreshed_at and include_nested. `selection.matches` uses real room UUIDs; append room/root display context to errors/coverage rather than changing required match keys.

- [ ] **1. Write** `test_ambiguous_and_dangling_room_selection`, `test_moved_link_is_excluded_from_placement`, `test_room_reads_preserve_stage_one_scope_and_privacy`.

```python
def test_ambiguous_and_dangling_room_selection(self):
    result = build_view(f.client, state, custody, entity_id=item)
    assert {m['room_id'] for m in result['selection']['matches']} == {overview, inset}
    assert result['selection']['destination_id'] == nearest_linked_ancestor
    assert build_view(f.client, state, custody, room_id=removed)['selection']['kind'] == 'unavailable'
    assert before_row == f.stored_row() and f.client.writes == []
    assert 'Borrower Secret' not in json.dumps(result)
```

- [ ] **2. Run RED:** `PYTHONPATH=ops:kiosk:work/hardware/python python3 -m unittest discover -s tests -p 'test_workshop_room_views.py' -v`; expect unrecognized v2 rooms/missing cross-plan matches.
- [ ] **3. Implement** nearest valid ancestor across all plans, exact/containing semantics and all matches there. Room filters presentation, never chooses a farther ancestor. Multiple matches show chooser; one can auto-open. Invalid roots/links remain review errors, excluded from placement/coverage. Invalid room UUID shows chooser; no name fallback. Preserve Stage 1 scope/count/privacy/photos and both Cage UUIDs.
- [ ] **4. Verify GREEN:** RED command plus `PYTHONPATH=ops:kiosk:work/hardware/python python3 -m unittest discover -s tests -p 'test_workshop_views.py' -v` from Stage 1.
- [ ] **5. Self-review and commit:** `git add ops/workshop_views.py ops/desktop_api.py deploy/kiosk-server.py tests/test_workshop_room_views.py`; `git commit -m "feat: resolve native workshop targets across room plans"`.
- [ ] **6. Sol review** committed resolution/privacy/compatibility diff; fix/test/fix-commit/re-review before acceptance.

### Task 4: Desktop room picker, scoped drafts and editing

**Files:** Modify `homebox-ui/overlay/lib/workshop-tools.js`, `homebox-ui/overlay/composables/use-workshop.ts`, `homebox-ui/overlay/pages/workshop/[tool].vue`, `homebox-ui/overlay/assets/css/workshop.css`; create `deploy/verify-workshop-rooms.py`.

**Interfaces:** Within established mount closure add `selectRoom(roomId: string | null) -> void`, `moveDrawing(drawingId: string, targetRoomId: string, x: number, y: number) -> void`, `removeEmptyRoom(roomId: string) -> void`; retain `saveLayout() -> Promise<void>`, `workshopPage(revision) -> Promise<void>`, dispose/canLeave and `useWorkshop.write`. Preserve Stage 1's `mountWorkshopTools(root,initialPage,workshop,navigate,notify,initialSelection={entityId:null,drawingId:null,roomId:null})`; the Vue wrapper still maps `id`, `drawing_id`, `room_id` into that option. Draft document initialized from server; selected room, per-room undo/selection and dirty draft are scoped by collection/user identity. Bookmark values are UUIDs.

Verifier CLI `--case desktop_rooms|terminal_rooms|all --native-port 0 --companion-port 0 --gateway-port 0 --candidate <bundle> [--previous <bundle>]` allocates fresh temporary runtime/database and free ports. Reuse disposable integration bootstrap patterns, existing installed Chromium/Playwright, fake hardware/print boundaries and artifact-resolved imports. No operational paths/default 17749. Add named `test_desktop_room_drafts(page, fixture) -> None` using real picker/form actions.

- [ ] **1. Write browser assertions:** create two empty rooms, edit first, switch second/back; `assert first_room_x == edited_x`; second session saves, first save conflicts: `assert first_draft_x == edited_x`; identity/collection changes: `assert displayed_group != original_group` and original draft is suspended. Assert ambiguous/dangling bookmark opens chooser; rename title keeps `assert native_name_after == native_name_before`; invalid move leaves `assert object_id_and_location == original_pair`; cancelled/nonempty removal keeps `assert room_id in saved_room_ids`. Verify timeout/status completion leaves `assert revision == previous_revision + 1` and no automatic second POST.
- [ ] **2. Run RED:** `python3 deploy/verify-workshop-rooms.py --case desktop_rooms --native-port 0 --companion-port 0 --gateway-port 0 --candidate "$WORKSHOP_CANDIDATE_FIXTURE_BUNDLE"`; expect missing room picker. Set the variable to a newly staged nonprivate matched fixture bundle, never a live selector.
- [ ] **3. Implement** initialized picker; Save includes all dirty rooms. Empty create, title/dimensions/root editor, target/coordinates move, confirmed empty-only removal; preserve IDs/bounds/captions, no scaling/cropping/native move. Repair uses native paths/UUIDs; refresh secondary labels without replacing drafts. Suspend drafts under original identity, scope pending/status recovery. Schema rejection retains drafts/offers reload. Old URLs use remembered valid/first room; explicit invalid UUID shows chooser.
- [ ] **4. Verify GREEN:** isolated `python3 deploy/build-homebox-ui.py`, then RED command with freshly hashed staged candidate; no added TypeScript diagnostics beyond pinned baseline. Assert keyboard/focus and readable textual choices.
- [ ] **5. Self-review and commit:** `git add homebox-ui/overlay/lib/workshop-tools.js homebox-ui/overlay/composables/use-workshop.ts 'homebox-ui/overlay/pages/workshop/[tool].vue' homebox-ui/overlay/assets/css/workshop.css deploy/verify-workshop-rooms.py`; `git commit -m "feat: edit scoped workshop room plans on desktop"`.
- [ ] **6. Sol review** committed lifecycle/identity/all-room-save/confirmation diff; fix/test/fix-commit/re-review before acceptance.

### Task 5: Terminal parity and pending-save recovery

**Files:** Modify `kiosk/workshop-ui.js`, `kiosk/workflow-ui.js`, `deploy/verify-workshop-rooms.py`; modify `kiosk/index.html` only for required local CSS/host wiring.

**Interfaces:** Add `workshopSelectRoom(roomId: string | null) -> void`, `workshopMoveDrawing(drawingId: string, targetRoomId: string, x: number, y: number) -> void`, `workshopRemoveEmptyRoom(roomId: string) -> void`, `workshopSave() -> Promise<void>`, `workshopCheckSave(requestKey: string) -> Promise<void>`; preserve `workshopOpen(entity=null) -> Promise<void>` with optional bookmark state supplied by existing navigation. Use Task 2 save/status and Task 3 view shapes. Add `test_terminal_room_drafts(page, fixture) -> None`.

- [ ] **1. Write browser assertions** matching Task 4 draft/conflict/identity cases at 800 × 480. `assert all(height >= 44 for height in room_control_heights)`; `assert keyboard_selected_room == requested_room`; `assert moved['id'] == original['id'] and moved['location_id'] == original['location_id']`; after dropped response and reload/status, `assert save_post_count == 1 and recovered_revision == old_revision + 1`. Browse/pan keeps `assert saved_geometry == before`; per-room undo changes only active room. Revoked management before confirmation keeps `assert revision == before_revision`.
- [ ] **2. Run RED:** `python3 deploy/verify-workshop-rooms.py --case terminal_rooms --native-port 0 --companion-port 0 --gateway-port 0 --candidate "$WORKSHOP_CANDIDATE_FIXTURE_BUNDLE"`; expect missing Terminal picker/recovery.
- [ ] **3. Implement** Desktop operations/root rules; retain zoom/pan/rotation/numeric editing/undo/Browse guards. Update `hasDraft`, `resetTask`, `leaveTask` for all drafts/pending keys. Scope state by configured collection/session, no badge promotion. Persist key before send, freeze request, inspect uncertain status, never auto-resend. Native creation keeps separate confirmation/recovery.
- [ ] **4. Verify GREEN:** RED command and Stage 1's `PYTHONPATH=ops:kiosk:work/hardware/python python3 -m unittest discover -s tests -p 'test_workshop_routes.py' -v`. Restage/hash candidate; require nonzero discovered tests.
- [ ] **5. Self-review and commit:** `git add kiosk/workshop-ui.js kiosk/workflow-ui.js deploy/verify-workshop-rooms.py`; add `kiosk/index.html` separately only if changed; `git commit -m "feat: support room plans and recovery on terminal"`.
- [ ] **6. Sol review** committed accessibility/identity/recovery diff; fix/test/fix-commit/re-review before acceptance.

### Task 6: Prove matching rollout and data-safe rollback

**Files:** Modify `deploy/verify-workshop-rooms.py`, `deploy/release_bundle.py`, `tests/test_release_bundle.py`, `docs/WORKSHOP_EDITOR.md`. Release bundler exists only after prerequisite release work; do not invent a second publisher.

**Interfaces:** Extend existing `validate_bundle(release: pathlib.Path) -> dict` capability/provenance checks, retaining `stage_bundle`/`select_bundle` signatures. Workshop rollback requires a matched server/Desktop/Terminal/Python bundle that can read document versions 1/2 and either writes version 2 or disables Workshop writes. A pre-v2 writer is not a valid rollback target, even with matching binary hashes. Add verifier `test_room_bundle_rollback(fixture, previous, candidate) -> None` and unit `test_incompatible_workshop_writer_is_rejected_before_selection`.

- [ ] **1. Write assertions:** incompatible previous manifest raises before fake service/pointer callbacks; `assert callback_calls == []`. Candidate explicitly migrates fixture, saves second room and native fixture history; rollback switches only application artifacts: `assert rollback_document == candidate_document`, `assert native_uuid_fields_photos_loans == before_rollback`, `assert receipt_status == 'completed'`. Compatible read-only previous build reads both rooms and refuses writes; `assert revision_after_rejected_legacy_save == saved_revision`. Assert code/static imports all resolve one bundle and source-file edits cannot alter fixture responses.
- [ ] **2. Run RED:** `PYTHONPATH=deploy:ops:kiosk:work/hardware/python python3 -m unittest discover -s tests -p 'test_release_bundle.py' -v`; expect missing Workshop capability gate.
- [ ] **3. Implement** capability checks using artifact-matched test receipts. Prepare/review v2-readable, writer-gated rollback bundle if baseline lacks support; reject truncating writers. Verify populated/empty migration/restart, same-item selection, unchanged legacy fields, Cage UUIDs, privacy and fake selection failure. Candidate/previous share fresh fixture data; never restore older databases. Document editing/conflicts/recovery/root repair/legacy review/rollback limitations.
- [ ] **4. Verify GREEN:** RED command, focused room tests via `PYTHONPATH=ops:kiosk:work/hardware/python python3 -m unittest discover -s tests -p 'test_workshop_room*.py' -v`, then `python3 deploy/verify-workshop-rooms.py --case all --native-port 0 --companion-port 0 --gateway-port 0 --candidate "$WORKSHOP_CANDIDATE_FIXTURE_BUNDLE" --previous "$WORKSHOP_PREVIOUS_FIXTURE_BUNDLE"`. Expect named checks pass, `live_mutations:0`, `physical_prints:0`, source/runtime manifest hashes and no new build diagnostics. Do not run older `verify-workshop-*` scripts targeting 17749.
- [ ] **5. Self-review and commit:** `git add deploy/verify-workshop-rooms.py deploy/release_bundle.py tests/test_release_bundle.py docs/WORKSHOP_EDITOR.md`; `git commit -m "test: verify workshop room migration and safe rollback"`.
- [ ] **6. Sol task and whole-stage review** committed coverage/compatibility/receipts/diff; fix/test/fix-commit/re-review. Coordinator confirms Review Focus coverage. Fixture success does not claim physical recognition. Present artifacts/evidence for separate deployment approval; no live selection/restart/private-backup reads.
