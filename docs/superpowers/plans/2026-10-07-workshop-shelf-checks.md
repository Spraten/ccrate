# Guided Workshop Shelf Checks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let authorized managers record, resume and review physical shelf observations without changing native inventory.

**Architecture:** A focused `ShelfChecks` service stores snapshots, observations, audit events and atomic request results in the existing Ledger SQLite database. Desktop and Terminal adapters derive trusted context and call the same service under the existing application write lock. Completion preserves a reviewed point-in-time comparison; Homebox remains independently mutable.

**Tech Stack:** Installed Python stdlib/SQLite/unittest, existing Homebox client and scanner helpers, native Nuxt/Vue JavaScript host, vanilla Terminal, installed Playwright/Chromium.

**Spec:** `docs/superpowers/specs/2026-10-07-workshop-shelf-checks-design.md`; umbrella `docs/superpowers/specs/2026-10-07-workshop-redesign-design.md`.

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

1. An ambiguous manufacturer scan requires explicit native identity selection and cannot observe several assets: Task 2 `test_ambiguous_code_and_location_scan_are_read_only`.
2. Boolean, fractional and negative tallies cannot masquerade as nonnegative integers: Task 2 `test_quantity_three_requires_explicit_integer_tally`.
3. A deleted shelf or removed initiating member leaves readable history and confirmed cancellation available: Task 3 `test_deleted_shelf_and_former_owner_remain_reviewable`.
4. A changed collection/account or revoked manager cannot read private results or replay another actor's intent: Task 4 `test_context_revocation_and_cross_actor_replay`.
5. Lost replies followed by navigation/reload retain recovery identity, without replay or stale rendering: Tasks 5–6 `test_desktop_uncertain_reopen` and `test_terminal_uncertain_reopen`.

---

## Execution prerequisites and interfaces

Execute after accepted plan, queued member/profile/release fixes and label editor, and Stage 1 acceptance; Stage 2 is optional. Preserve an isolated snapshot of **all required tracked/untracked source**: plain HEAD omits essential overlays. Verify matching build/runtime baseline; reuse installed dependencies. Sequential Luna Medium workers self-review/commit before Sol High task review; fixes require tests/fix commits/scoped re-review before acceptance. Commands run from that isolated repository at execution time, never during drafting. Deployment is unauthorized. Every Step 6 reviews committed BASE..HEAD using the SDD review package; fixes require affected tests, fix commits and scoped Sol re-review before acceptance/next task.

`ops/shelf_checks.py` owns domain/persistence in existing `work/ops/ledger.db`; existing desktop/Terminal adapters and JS hosts retain their responsibilities. Tests/verifier are named per task; no unrelated restructuring.

Consume Stage 1 exactly: `scoped_equipment(client, location_id: str, *, include_nested: bool = False) -> list[dict]`. Start accepts active native **locations**, regardless of Storage kind. Direct includes assigned item containers; nested adds mixed descendants, deduplicated by UUID. No room dependency. Consume Stage 1 `build_view(client, layout_state: dict, custody: list[dict], *, entity_id: str | None = None, include_nested: bool = False, room_id: str | None = None, can_view_loans: bool = False) -> dict` for native paths; never modify geometry.

Server-derived `ctx={group:UUID,actor:UUID,manager:bool}` requires management for all operations and owner for edits, except confirmed cancellation. States: `draft/completed/cancelled`; suspension is read-only metadata. Revalidate access under application lock.

Check read shape: `{id,group_id,actor_id,actor_label,location_id,include_nested,started_at,state,revision,original_snapshot,reviewed_snapshot,review_fingerprint,observations,notes,groups,changes,pending_operations,suspended_reason,can_edit,completed_at,cancelled_at,cancelled_by,point_in_time}`. Snapshots include location/path and item `{entity_id,name,quantity,parent_id,path,archived,updated_at,custody}`; observations are unique by UUID with `{entity_id,method,observed_quantity,first_observed_at,last_observed_at}`. `groups` has `observed_here`, `not_observed`, `checked_out`, `unexpected_here`; rows expose expected/observed quantities, quantity difference, original/current path, availability and custody-conflict flags. Exclude unobserved loans from physical expectations; observed loans appear once under `observed_here` with conflict. Unexpected rows show current path; never infer return/Missing.

## Task 1: Atomic local journal and request results

**Files:** Create `ops/shelf_checks.py`, `tests/test_shelf_checks.py`.

**Interfaces:** Consume Ledger connections/transactions and UUID/timestamp/Conflict helpers. Produce `CheckAccessDenied(PermissionError)` (adapters map to HTTP 403), `ShelfChecks.__init__(self, ledger: Ledger)`, `request(self, ctx: dict, request_key: str) -> dict`, and `_apply(self, ctx: dict, action: str, intent: dict, request_key: str, change: Callable[[sqlite3.Connection], dict]) -> dict`.

- [ ] **1. Write failing tests.** Define `ShelfCheckTests`, temporary Ledger/native fake, trusted contexts, `new_key(self)->str`; no runtime import. Add:

```python
def test_atomic_result_restart_replay_and_changed_intent(self):
    result = self.store._apply(self.ctx, 'fixture', {'value': 1}, self.key,
                               lambda db: {'value': 1})
    reopened = ShelfChecks(Ledger(self.ledger.path))
    assert reopened.request(self.ctx, self.key)['result'] == result
    assert reopened._apply(self.ctx, 'fixture', {'value': 1}, self.key,
                          lambda db: self.fail('replayed mutation')) == result
    with self.assertRaises(Conflict):
        reopened._apply(self.ctx, 'fixture', {'value': 2}, self.key, lambda db: {})
```

`test_request_insert_failure_rolls_back_check` injects a SQLite abort trigger on result insertion and asserts zero check/event/request rows; `test_schema_preserves_existing_custody` asserts preexisting checkout history and custody survive reopen.
- [ ] **2. Run failing tests:** `PYTHONPATH=ops:kiosk:work/hardware/python python3 -m unittest discover -s tests -p 'test_shelf_checks.py' -v`. Expected import failure for `shelf_checks`.
- [ ] **3. Implement the interfaces.** Create `shelf_checks`, `shelf_check_observations`, `shelf_check_events`, `shelf_check_requests` and local schema metadata idempotently through Ledger transactions; no new database/`user_version` change. Enforce immutable original snapshot, append-only events and terminal rows. Request uniqueness `(group_id,request_key)` stores action/actor/intent digest/exact JSON result. Revision, mutation, event and result commit together; exceptions roll back. Replay checks current access/actor/intent before stale revision. Lookup: `{status:'completed',action,result}` or `{status:'not_started'}`. No secrets/raw scans/purge.
- [ ] **4. Verify:** rerun the focused command; PASS.
- [ ] **5. Self-review, then commit only task files:** `git add ops/shelf_checks.py tests/test_shelf_checks.py` then `git commit -m "feat: journal shelf checks atomically in ledger"`.
- [ ] **6. Obtain Sol High review** of transaction boundaries, immutability and existing Ledger compatibility; fix and reverify.

## Task 2: Frozen start scope, scanner resolution and observations

**Files:** Modify `ops/shelf_checks.py`, `tests/test_shelf_checks.py`.

**Interfaces:** Consume Task 1 journal, Stage 1 scope/path contracts, and `workshop_views.resolve_workshop_code(client, raw: str) -> dict` returning `{kind,entity_id:null|UUID,candidates:list[dict],message}`. That helper owns existing scanner normalization/native identity matching; do not duplicate it. Produce `start(self, client, ctx: dict, *, location_id: str, include_nested: bool = False, request_key: str) -> dict`; `resolve(self, client, ctx: dict, check_id: str, *, raw: str, selected_entity_id: str | None = None) -> dict`; `observe(self, client, ctx: dict, check_id: str, *, revision: int, entity_id: str, method: str, observed_quantity: int | None = None, request_key: str) -> dict`; `save_notes(self, client, ctx: dict, check_id: str, *, revision: int, notes: str, request_key: str) -> dict`.

- [ ] **1. Add named failing tests:** `test_direct_and_nested_mixed_scope_preserves_quantities` asserts direct container versus deduplicated nested descendants and separate Cage UUIDs. `test_ambiguous_code_and_location_scan_are_read_only` asserts multiple candidates, no automatic selection, unchanged active shelf and no writes. Add:

```python
def test_quantity_three_requires_explicit_integer_tally(self):
    check = self.start_fixture(quantity=3)
    for tally in (None, -1, 1.5, True, '3'):
        with self.assertRaises(ValueError):
            self.observe_fixture(check, observed_quantity=tally)
    saved = self.observe_fixture(check, observed_quantity=2)
    assert saved['observations'][0]['observed_quantity'] == 2
    assert saved['original_snapshot']['items'][0]['quantity'] == 3
    assert self.client.mutations == [] and self.physical_outputs == []
```

Define fixture helper signatures `start_fixture(self, *, quantity: int = 1) -> dict` and `observe_fixture(self, check: dict, *, observed_quantity: object = None) -> dict` calling the exact service APIs with fresh request keys. `test_repeat_uuid_and_foreign_archived_unknown` asserts one row after repeated scans; foreign/archived/unknown/location observations never insert rows.
- [ ] **2. Run Task 1 focused command.** Expected missing start/observe/resolve methods.
- [ ] **3. Implement the listed methods.** Freeze scope/original quantities/paths. Quantity=1 defaults observed quantity to one; otherwise require `type(value) is int` and >=0. Scan only selects until tally confirmed. Methods: `scan/visual`; duplicates never increment. Explicit zero remains saved evidence without claiming physical presence; test zero tally under not_observed for unborrowed expected items. Resolution: `{kind,entity_id:null|UUID,candidates:[{id,name,path}],message}`; explicit selection must belong to candidates. Apply check-specific owner/collection/active/archive/location guards to the shared resolver; no URL navigation/code registration. Notes plain text <=1000 characters. Increment revision once per accepted mutation; stale revision conflicts. Audit repeated observations without increasing quantity.
- [ ] **4. Verify:** rerun focused tests, with zero native/physical effects.
- [ ] **5. Self-review, then commit:** `git add ops/shelf_checks.py tests/test_shelf_checks.py` then `git commit -m "feat: record scoped shelf observations"`.
- [ ] **6. Obtain Sol High review** of hierarchy, quantities and identity handling; fix and reverify.

## Task 3: Refreshed comparison, completion and historical actors

**Files:** Modify `ops/shelf_checks.py`, `tests/test_shelf_checks.py`.

**Interfaces:** Produce `get(self, client, ctx: dict, check_id: str) -> dict`; `history(self, client, ctx: dict, *, location_id: str | None = None, limit: int = 100) -> list[dict]`; `refresh(self, client, ctx: dict, check_id: str, *, revision: int, request_key: str) -> dict`; `finish(self, client, ctx: dict, check_id: str, *, revision: int, review_fingerprint: str, request_key: str) -> dict`; `cancel(self, client, ctx: dict, check_id: str, *, revision: int, confirmed: bool, reason: str, request_key: str) -> dict`. All writes return the check shape above through Task 1 atomic results. Callers hold the existing application write lock; the service does not reacquire that non-reentrant lock. Inside `_apply`, use its supplied SQLite connection for custody/revision reads and writes rather than opening a nested Ledger transaction. Fixture helpers follow the same lock contract.

- [ ] **1. Add failing tests:** `test_refresh_preserves_original_and_observations` asserts changed membership/parent/quantity/archive/custody blocks finish, refresh preserves original snapshot and observations, and only the refreshed fingerprint completes. `test_loan_groups_and_pending_native_operations` asserts observed checked-out conflict, unobserved checkout grouping and pending/review journal visibility. Add:

```python
def test_deleted_shelf_and_former_owner_remain_reviewable(self):
    check = self.start_fixture()
    self.client.remove_location_and_owner()
    read = self.store.get(self.client, self.other_manager_ctx, check['id'])
    assert read['suspended_reason'] and read['actor_label'] == 'Former CACI-Create member'
    with self.assertRaises(Conflict):
        self.finish_fixture(check)
    cancelled = self.store.cancel(self.client, self.other_manager_ctx, check['id'],
        revision=check['revision'], confirmed=True, reason='Owner unavailable', request_key=self.new_key())
    assert cancelled['cancelled_by'] == self.other_manager_ctx['actor']
    assert cancelled['original_snapshot'] == check['original_snapshot']
```

Define `finish_fixture(self, check: dict) -> dict` and native fake removal helper. `test_rename_only_and_terminal_immutability` asserts renamed rows retain observation identity, completion/cancellation reject further changes, and other manager cannot observe/refresh/finish. `test_companion_lock_and_point_in_time_versions` asserts lock ordering and persisted reviewed versions/completion timestamp without native writes.
- [ ] **2. Run focused tests.** Expected missing methods or incorrect groups.
- [ ] **3. Implement the listed methods.** Fingerprint sorted membership, parent/path, quantity, archive and custody for target/scoped/observed records; track versions separately. Rename-only changes update display, preserving observations. Refresh preserves original evidence and removed rows in `changes`. Finish rereads native facts under application lock and custody in committing Ledger transaction; mismatch requires explicit Refresh review. Persist exact reviewed versions/UTC completion, `point_in_time:true`: direct native writes can race. Missing/archived target remains readable/cancellable. Other-manager cancel requires `confirmed is True`, reason 1–1000 characters, separate actor audit. Retain historical UUIDs; terminal get returns stored comparison. History limit 1–100; pending operations are collection-filtered. Native follow-up links require separate confirmation.
- [ ] **4. Verify:** focused tests pass; mutation/output logs remain empty for refresh, finish and cancel.
- [ ] **5. Self-review, then commit:** `git add ops/shelf_checks.py tests/test_shelf_checks.py` then `git commit -m "feat: review and finish point-in-time shelf checks"`.
- [ ] **6. Obtain Sol High review** of rereads, race claims, custody and cancellation; fix and reverify.

## Task 4: Authenticated desktop and Terminal adapters

**Files:** Modify `ops/desktop_api.py` (`get_action`, `post_action`, `operation_status`, `recovery_rows`), `deploy/kiosk-server.py` (dependencies, allowlist, workshop dispatch); create `tests/test_shelf_checks_api.py`.

**Interfaces:** Instantiate `shelf_checks=ShelfChecks(ledger)`; pass this dependency to both desktop handler calls. Preserve existing `handle(handler,deps)`, `get_action(route,query,ctx,deps)`, `post_action(route,data,ctx,deps,address)`. Add `terminal_check_context(client, *, open_admin: bool) -> dict` in `ops/shelf_checks.py`: reject disabled setup mode, read native self/group/membership, bind tenant, use service-account native UUID as actor; never use `session.current()`.

Routes use prefix Desktop `/workshop-api/workshop/checks`, Terminal `/workshop/checks`:

| Suffix | Desktop | Terminal | Input |
| --- | --- | --- | --- |
| `/list` | GET | POST read | optional `location_id`, `limit` |
| `/get` | GET | POST read | `id` |
| `/resolve` | POST read | POST read | `id,raw,selected_entity_id?` |
| `/request` | POST read | POST read | `request_key` |
| `/start` | POST write | POST write | `location_id,include_nested=false,request_key` |
| `/observe` | POST write | POST write | `id,revision,entity_id,method,observed_quantity?,request_key` |
| `/notes` | POST write | POST write | `id,revision,notes,request_key` |
| `/refresh` | POST write | POST write | `id,revision,request_key` |
| `/finish` | POST write | POST write | `id,revision,review_fingerprint,request_key` |
| `/cancel` | POST write | POST write | `id,revision,confirmed,reason,request_key` |

- [ ] **1. Add `test_context_revocation_and_cross_actor_replay`:** use isolated request/native fixtures modeled on `tests/test_desktop_api.py`; assert nonmanager detail/status=403, foreign group is denied, identity binding mismatch=409, permission revoked while queued=403, another actor's replay=409, ordinary scanned badge cannot become Terminal check actor, OPEN_ADMIN=False=403. Reuse `Request` and fixture dependency construction from `test_desktop_api.py`:

```python
def test_nonmanager_private_check_list(self):
    request = Request('workshop/checks/list', headers={'Cookie': 'hb.auth.token=member; hb.auth.remember=true'})
    api.handle(request, self.deps)
    assert request.status == 403
```

`test_route_parity_and_conflicts` asserts identical groups/revisions for both adapters, read requests do not write, stale revision=409, malformed scope/tally=400, own lost-response lookup returns committed result, and native writes/output calls=0.
- [ ] **2. Run:** `PYTHONPATH=ops:kiosk:work/hardware/python python3 -m unittest discover -s tests -p 'test_shelf_checks_api.py' -v`. Expected 404 routes/missing context helper.
- [ ] **3. Implement route adapters/context helper.** Preserve desktop origin/cookie/identity gates and reauthentication under lock. Gate every detail/status read. Terminal preserves same-origin/client boundaries, refreshes OPEN_ADMIN service identity under lock. Reject supplied actor/group/manager and invalid booleans/UUIDs. Do not wrap check methods in `once()` (split commits). Add collection-bound, manager-gated check lookup to operation/status/recovery; dedicated lookup remains authoritative. Reads use read classifications; no stock invalidation/native dispatch.
- [ ] **4. Verify:** focused API command (nonzero tests), then `PYTHONPATH=ops:kiosk:work/hardware/python python3 -m unittest discover -s tests -p 'test_desktop_api.py' -v`; PASS. Patch runtime root/database/output dependencies before server import; never load operational globals.
- [ ] **5. Self-review, then commit:** `git add ops/shelf_checks.py ops/desktop_api.py deploy/kiosk-server.py tests/test_shelf_checks_api.py` then `git commit -m "feat: expose authorized shelf check APIs"`.
- [ ] **6. Obtain Sol High review** of authentication, routes and replay disclosures; fix and reverify.

## Task 5: Desktop observation and recovery screens

**Files:** Modify `homebox-ui/overlay/lib/workshop-tools.js`, `homebox-ui/overlay/composables/use-workshop.ts`, `homebox-ui/overlay/assets/css/workshop.css`; create `deploy/verify-shelf-checks.py`.

**Interfaces:** Preserve Stage 1's `mountWorkshopTools(root,initialPage,workshop,navigate,notify,initialSelection={entityId:null,drawingId:null,roomId:null})` and `useWorkshop().request/write/pending/forget`; add scoped host functions `async openShelfCheck(locationId: string | null, checkId: string | null): Promise<void>` and `async recoverShelfCheck(requestKey: string): Promise<void>`. Verifier CLI: `--interface desktop|terminal|both --root PATH --base-url URL --fixture-port 0`; fresh temporary root/databases, disposable ports, explicit endpoint, disabled outputs. Never use 17749/existing verify-workshop scripts.

- [ ] **1. Write failing browser cases:** `test_desktop_uncertain_reopen` asserts one start request after a dropped committed reply, pending key survives reload, explicit lookup reopens same check, no replay and no stale account rendering. `test_desktop_observe_refresh_finish_history` asserts default Direct contents, nested opt-in, visual/scan quantity controls, four groups/conflict text, unsaved notes warning, refresh preservation, owner-only editing, other-manager confirmed cancel and immutable completed history. Pin the browser assertions to real service state: `assert page.get_by_text("Direct contents", exact=True).is_visible()` and `assert fixture.check_count() == 1`. Define verifier fixture `check_count()->int` and `requests:list[dict]` querying only its temporary Ledger/request log. Uncertain tests assert one start POST and zero automatic replays.
- [ ] **2. Run:** `PYTHONPATH=ops:kiosk:work/hardware/python python3 deploy/verify-shelf-checks.py --interface desktop --root "$PWD" --base-url http://127.0.0.1:0 --fixture-port 0`. Port zero selects verifier-owned disposable server. Expected missing controls.
- [ ] **3. Implement host screens.** Enter from location/storage view; reuse scan/decode/manual controls and dedicated resolution. Explicit observation/notes Save, Refresh review, Finish and Cancel confirmations. Pause warns about unsaved edits; reopen uses server history/drafts. Browser storage holds scoped IDs/request metadata only, no snapshots/notes/codes/frames. Reuse uncertain-write mechanism; lookup restores committed results, not_started permits explicit confirmation only. Disable writes while uncertain/busy; show revision/frozen scope/point-in-time caveat. Teardown/identity/route tokens suppress late responses. Follow-up links use existing confirmations.
- [ ] **4. Verify:** run `python3 deploy/build-homebox-ui.py` **inside isolated snapshot only** using copied installed toolchain/dependencies; verify matching upstream baseline and no added diagnostics. Rerun browser command; no browser errors, PASS. No release selection.
- [ ] **5. Self-review, then commit:** `git add homebox-ui/overlay/lib/workshop-tools.js homebox-ui/overlay/composables/use-workshop.ts homebox-ui/overlay/assets/css/workshop.css deploy/verify-shelf-checks.py` then `git commit -m "feat: add desktop shelf check workflow"`.
- [ ] **6. Obtain Sol High review** of pending recovery, stale UI and private storage; fix and reverify.

## Task 6: Terminal touch workflow and pause/reopen

**Files:** Modify `kiosk/workshop-ui.js`, `kiosk/workflow-ui.js` (readPosts/scanner lifecycle only), `kiosk/index.html` (scoped styles only), `deploy/verify-shelf-checks.py`.

**Interfaces:** Reuse `workshopOpen(entity=null)`, `workshopStorageRender(id)`, `api(path,data)`, existing touch keyboard/camera decoder, route revision and cancellation hooks. Produce global `async workshopCheckOpen(locationId = null, checkId = null)` and `async workshopCheckRecover(requestKey)` consuming Task 4 routes and Task 3 shape.

- [ ] **1. Add `test_terminal_uncertain_reopen`:** assert dropped committed observation response retains key, pause/reload/reopen reads exact saved revision/quantity, no automatic write and account context cannot come from badge. `test_terminal_touch_keyboard_camera_and_cancel` asserts 800×480 controls >=44 CSS px, keyboard focus, synthetic-frame scanner cancellation and ambiguity, explicit tallies, groups/text alternatives, refreshed review and completed history, no print/native mutation; live camera/physical shelf acceptance is not established. Assert `all(box["height"] >= 44 for box in control_boxes)` and `assert fixture.check_count() == 1`; obtain boxes through Playwright, fixture through Task 5.
- [ ] **2. Run Task 5 verifier command with `--interface terminal`.** Expected missing check controls.
- [ ] **3. Implement Terminal functions.** Show service manager attribution and desktop-equivalent scope/confirmations/recovery. Extend `readPosts`; intercept check scan purpose before loan-session behavior; location scan never switches shelf. Pause stops camera/cancels responses; retain saved draft, mark unsaved notes/tally. Pending metadata is service actor/collection scoped; no snapshot copies. Keep controls/actions accessible at 800×480; no new tooling.
- [ ] **4. Verify:** rerun Terminal command; all assertions/output counters pass, no browser errors. Then run `PYTHONPATH=ops:kiosk:work/hardware/python python3 -m unittest discover -s tests -p 'test_terminal_ownership.py' -v`; nonzero tests pass.
- [ ] **5. Self-review, then commit:** `git add kiosk/workshop-ui.js kiosk/workflow-ui.js kiosk/index.html deploy/verify-shelf-checks.py` then `git commit -m "feat: add resumable Terminal shelf checks"`.
- [ ] **6. Obtain Sol High review** of touch/accessibility, scanner teardown and recovery; fix and reverify.

## Task 7: Private backup restoration and final acceptance

**Files:** Create `tests/test_shelf_checks_backup.py`; modify `homebox-ui/README.md` and `docs/WORKSHOP_EDITOR.md`; inspect `deploy/backup-deployment.py` without changing its service lifecycle.

**Interfaces:** Existing backup members include `work/ops`; existing checkpoint/hash inventory includes `work/ops/ledger.db`. New tables automatically travel with that database. No new snapshot directory, export endpoint or cleanup schedule.

- [ ] **1. Write `test_private_backup_restores_original_review_and_results`:** run existing backup script through a controlled temporary-root harness, patch service/subprocess calls and optional binary/source paths before execution, create draft/completed/cancelled fixtures, force SQLite WAL activity, and assert archive contains Ledger/manifest, checkpoint integrity is `ok`, manifest digest matches restored bytes, private mode=0600, and reopened service preserves original/refreshed snapshots, actor UUIDs, observations, states and request results. Assert no real systemctl/print/native call. `test_backup_selection_includes_ledger` asserts the actual script's member/database selection covers that fixture. No operational backup invocation. Fixture harness `run_fixture_backup(source: Path, root: Path) -> Path` substitutes the script root literal in an in-memory AST and patches subprocess calls before executing; never execute its hardcoded operational root. Assertion code: `assert reopened.get(client, ctx, saved['id'])['original_snapshot'] == saved['original_snapshot']`; `assert reopened.request(ctx, request_key)['result'] == saved_result`; `assert real_service_calls == []`. All values come from that temporary fixture.
- [ ] **2. Run:** `PYTHONPATH=ops:kiosk:work/hardware/python python3 -m unittest discover -s tests -p 'test_shelf_checks_backup.py' -v`. Existing backup behavior may already pass: retain that evidence without manufacturing a failure or adding backup code.
- [ ] **3. Complete harness and docs.** Document private Pi retention, pause/recovery, tally/suspension/cancellation, original/refreshed evidence, follow-up confirmation and non-atomic completion. Restore Ledger only into a fresh temporary fixture; never touch the operational database. Human physical shelf/camera acceptance and deployment remain separate gates.
- [ ] **4. Verify:** rerun backup command and `PYTHONPATH=ops:kiosk:work/hardware/python python3 -m unittest discover -s tests -p 'test_shelf_checks*.py' -v`; run verifier command with `--interface both`; PASS. Read back docs and run `git diff --check`; require zero errors. Do not broaden into live validation.
- [ ] **5. Self-review, then commit:** `git add tests/test_shelf_checks_backup.py homebox-ui/README.md docs/WORKSHOP_EDITOR.md` then `git commit -m "test: verify private shelf check backup and recovery"`. No publishing/restarts/release selection.
- [ ] **6. Obtain final Sol High review** against both specs and all five Review Focus tests, task diffs, no-native-write counters, backup evidence and matched build/runtime baseline; fixes and renewed affected verification before acceptance.
