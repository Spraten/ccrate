# Profile Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reject invalid native names before journaling, finish profile saves cleanly while protecting drafts in both interfaces, and preserve picture proportions.

**Architecture:** Correct validation at the existing Go/Python profile boundaries. Handle confirmed completion, unchanged saves and unsaved dismissal together in the existing native/Terminal profile flows, using explicit request keys and read-only recovery status; keep generic Workshop write semantics unchanged. Refresh/focus native Members through its build overlay and crop in the single shared picture helper.

**Tech Stack:** Go/Ent, Python unittest, Vue/Nuxt/reka-ui, browser Canvas, existing Playwright fixture verifier.

**Spec:** `docs/superpowers/specs/2026-10-06-user-management-review-fixes.md`

**Revision:** October 7, 2026; this updates the existing plan in place. Task 2 owns the requested completion fix and earlier draft guards as one independently GREEN deliverable.

## Global Constraints

- Homebox is the account and inventory authority; use existing native UUIDs, APIs, components and helpers.
- Name-only profiles remain badge-only with NULL native passwords; existing desktop accounts keep their sign-in behavior.
- No password/PIN enforcement, role changes, dependencies, speculative authentication or unrelated refactors.
- Never automatically repeat an uncertain create, save, badge issuance, replacement or print.
- Never mutate live data, issue/print real badges, read secrets/backups, or restart services during implementation verification.
- Private credentials, badge keys, databases and backups stay outside release bundles and logs.
- Preserve the dirty working tree and existing uncommitted features; never reset, stash, delete or replace them with a clean HEAD checkout.
- One GPT-6 Luna Medium coding worker per task; GPT-6.1 Sol High risk review; fixes, tests and renewed review before the next task. No silent model/workflow fallback.
- Planning approval is not deployment approval; physical print/disconnect acceptance is a separately authorized gate.

## Review Focus

- Trimmed multibyte boundary and companion journal ordering → Task 1 `test_member_name_utf8_byte_boundaries` and `test_invalid_name_does_not_start_profile_journal`.
- Existing account email and notes semantics → Task 1 `test_profile_limits_preserve_email_and_notes_semantics` and disposable native assertions.
- Create→unchanged Save, double click and pending no-op → Task 2 `profile_create_then_unchanged_save_finishes_without_write`, `profile_double_click_posts_once` and `profile_pending_noop_cannot_finish` in both interfaces.
- Changed/reverted/cancelled draft, lost reply and context/list races → Task 2 `profile_reverted_draft_is_clean`, `profile_cancel_keeps_all_fields`, `profile_status_completed_finishes_review_stays_open`, `profile_context_switch_hides_draft_and_prompt` and `profile_committed_save_refresh_failure_stays_successful`.
- Portrait/landscape, transparency and failed bitmap decoding → Task 3 `avatar_rectangles_preserve_circle_proportions` and `avatar_cleanup_and_bad_upload`.

---

Execute after the common brief's baseline/isolation gate and Terminal parity plan. All commands below run from the isolated project root with its existing dependencies/toolchain available; never select or deploy output. Preserve a reviewed baseline outside task commits; commit only the task's delta and never auto-commit copied preexisting work.

### Task 1: Align native and companion byte validation

**Files:** Modify `homebox-backend/repo_member_profiles.go` (`validMemberDetails`), `ops/accounts.py` (`creation_input`, `profile_input`); test `tests/test_accounts.py`, `tests/test_desktop_api.py`, `deploy/verify-member-api.py`, `deploy/verify-desktop-integration.py`. Do not change `email`, global `ops/setup_native.py:text` or unrelated inventory inputs.

**Interfaces:** Preserve `validMemberDetails(name, email string, emailRequired bool) error`, `creation_input(data) -> dict`, `profile_input(data) -> dict`, `email(value) -> str`. Add `member_name(value: object) -> str` in `ops/accounts.py`: require a string, trim it, enforce nonempty and `len(value.encode('utf-8')) <= 255`. Both companion callers already validate before `once`; keep that ordering. Native checks `len(name) <= 255`; notes continue using Unicode codepoints. Preserve existing email behavior: optional blank remains valid, companion text validation keeps its 255-character limit and normalization, and the native email validator is unchanged.

- [x] Write `AccountInputs.test_member_name_utf8_byte_boundaries`: accept `'a'*255`, `'界'*85`, `'😀'*63+'abc'`, and whitespace around valid values; reject empty/whitespace, nonstring, `'a'*256`, `'界'*86`, `'界'*90`, `'😀'*64` for both create/update; assert accepted names are trimmed. Write `test_profile_limits_preserve_email_and_notes_semantics`: optional empty email accepted, existing 255-character email boundary preserved, 1000 CJK note characters accepted, 1001 rejected.
- [x] Add `DesktopTests.test_invalid_name_does_not_start_profile_journal` using fake native member/profile responses and an invalid name on `users/create` and `users/update`: assert HTTP 400, no native POST/PUT, `request_row(...) is None`, and no Recovery row. Add equivalent Terminal browser fixture checks to the existing verifier: no `desktop_requests` entry and form stays editable on rejection. Extend `verify-member-api.py` with named `Native UTF-8 name boundaries return 400 without changing users` assertions for both native create/update; failed update preserves name/version. A normal valid name-only creation still has NULL password; duplicate names retain different IDs.

```python
assert accounts.creation_input({'name': '界' * 85, 'request_key': key})['name'] == '界' * 85
with self.assertRaises(ValueError):
    accounts.creation_input({'name': '界' * 86, 'request_key': key})
assert invalid_response.status == 400
assert api.request_row(self.ledger, self.group, key) is None
assert not [call for call in self.native_calls if call[3] in ('POST', 'PUT')]
```
- [x] Run the account/Desktop API tests and native reproduction. The name-boundary defect was reproduced before implementation. The Desktop API suite passed 42/42 with an in-memory `qrcode` stub because that optional dependency is absent in this environment. The first Go build attempt exhausted `/tmp`; one bounded retry using candidate-local scratch passed, after which `verify-member-api.py` passed eight disposable checks. This builder stages code only.
- [x] Implement the specified byte guards with product copy `Name is too long. Try a shorter name.` and the existing required-name message for empty values; preserve optional email and current note rules. Keep the exact 255-byte criterion in tests/docs. Do not widen Ent schema, truncate names, or alter retry behavior.
- [x] Rerun the relevant checks: `test_accounts.py` passed 5/5; `test_desktop_api.py` passed 42/42 with the in-memory `qrcode` stub; the native member verifier passed 8/8; and the focused Terminal browser probe passed both invalid-name cases with no live mutations or physical prints. No Homebox UI build was needed because this task changes no Homebox UI source. The full desktop verifier is not claimed as passed: its legacy Pi label assertion skipped, and the focused probe stopped after the Task 1 assertions.
- [x] Sol High reviewed trust-boundary ordering, exact byte semantics, original account behavior and safe-intent privacy. The two Minor test-fixture findings were corrected and rechecked; accepted source is at commit `bf88fef`. Verification scope and known skips are recorded in `work/queue-coordinator/profile-task1-utf8-evidence.json`.

**Coordinator status — October 10, 2026:** Task 1 is accepted. The native backend build and eight disposable native checks passed; the focused Terminal invalid-create/update cases passed; `test_accounts.py` passed 5/5 and the Desktop API suite passed 42/42 with an in-memory `qrcode` stub. The full desktop verifier is not claimed as passed (its legacy Pi label assertion skipped); no live mutations or physical prints occurred. See the acceptance evidence receipt above.

### Task 2: Finish profile editing and protect its complete draft lifecycle

**Files:** Modify `homebox-ui/overlay/components/Workshop/UserManager.vue` (`save`, `edit`, exits/watchers/actions), `kiosk/users-ui.js` (`userManager`, `userProfile`, `userForm`, task teardown), `deploy/build-homebox-ui.py:prepare()` (generated Members handler/focus/error integration); test `deploy/verify-desktop-integration.py`. Inspect `use-workshop.ts:write/request/pending/forget`, `kiosk/workflow-ui.js:resolveTransaction/leaveTask/resetTask/primary` and `ActionDialog.vue`; preserve these shared APIs and existing auth/role rules. Do not edit upstream or `work/homebox-ui-build` outputs.

**Interfaces:** Preserve native exposed `show(user?: UserSummary): void`, `save(): Promise<void>` and `Profile` shape; change `changed` to `[memberId: string]`, emitted once per confirmed create/update, never for an unchanged finish; add `finished: [memberId: string]` for focus after successful closure, including unchanged Save. Add native `draftSnapshot(value: Profile | null): string` for `name,email,avatar,notes`; `finishProfile(memberId: string, outcome: 'saved' | 'unchanged'): void` performs successful cleanup directly; `requestLeave(destination: 'close' | 'list'): void`, `discardAndLeave(): void`, `backToUsers(): void` handle user exits separately. Retain create key `draft.id`; allocate/store one update key when an edit session is loaded and explicitly pass `request_key` to `workshop.write`. Capture revision, user/group/identity and key before submitting. Local submitting/uncertain state participates in guards and prevents another save through status resolution; inspect `workshop.pending()` for matching `users/create|users/update` subject/context before allowing even unchanged finish.

**Interfaces continued:** In generated Members add `profileChanged(memberId: string): Promise<void>` as sole `@changed` handler: load members/badges/loans once each and retain that refresh promise with its context. Add `profileFinished(memberId: string): Promise<void>` for `@finished`: await any same-context in-flight refresh and rendering, then focus the UUID's Manage profile button (`data-member-id`) or Manage users if unavailable, without starting another refresh. Creation's optional profile phase remains open and receives no Members focus; unchanged Save emits only finished. Keep generic `refreshMembers()` for other callers. Existing loads record errors; keep read failure outside the mutation catch. Terminal keeps `userProfile(id)`/`userForm(isNew)` and adds `memberDraftSnapshot(value): string`, `finishMemberProfile(memberId: string, outcome: 'saved' | 'unchanged'): Promise<void>` and extends `userManager(options: {focusMemberId?: string; message?: string} = {}): Promise<void>` for direct completion/focus. Create key remains UUID; update key remains stable until definitive result. Reuse `resolveTransaction(key)`; finish bypasses `leaveTask` (wrapped Save still contributes to `writeCount`) and clears profile route snapshots so Back cannot restore the finished draft.

**No-op pending contract:** Before unchanged completion, inspect the local retained attempt/native pending store and read existing Recovery (`workshop.request('recovery')` natively, `api('/api/recovery')` in Terminal). Block rows where `desktop_job`, action `users/create|users/update`, and `intent.user_id` match this profile in the current server-selected collection; use the known key's status read to resolve a locally retained attempt. A failed Recovery read does not prove absence: keep the form with reload/Recovery, without writing. This uses existing read APIs rather than a new pending store/cache and also covers reopening a profile after an uncertain prior confirmation.

- [ ] Add named native **and Terminal** fixture cases: `profile_create_then_unchanged_save_finishes_without_write` (one create, one optional-details transition, `User created.`, unchanged Save closes/returns list, `Profile is up to date.`, zero update POST/journal; native has no changed refresh, Terminal may read its list once); `profile_changed_save_finishes_once` (one POST/journal, closed modal/list, `Profile saved.`, one native parent refresh or Terminal list load, correct UUID focus, no post-update profile GET/reload); `profile_double_click_posts_once` (hold response, second click creates no request/new key); `profile_validation_or_stale_error_keeps_draft` (400/409 with not_started status keeps all fields/error, no success); `profile_status_completed_finishes_review_stays_open` (abort committed HTTP reply then status-completed finishes identically; injected after-write/native lost-response review or unavailable status preserves key/draft and blocks Save/Close, with explicit Recovery); `profile_pending_noop_cannot_finish` (reopened clean profile with unresolved same-person/context create/update or unavailable Recovery read cannot no-op-close or write); `profile_definitive_failure_allows_only_explicit_retry` (no automatic retry, not_started may retain its unjournaled key, cancelled explicit retry uses a fresh key; cancelled create gets a new UUID after definitive recovery proves the prior create absent, cancelled update keeps the person's UUID).
- [ ] Retain/add lifecycle assertions `profile_clean_exit_has_no_prompt`, `profile_cancel_keeps_all_fields`, `profile_discard_writes_nothing`, `profile_reverted_draft_is_clean`, `profile_busy_cannot_dismiss`, `profile_context_switch_hides_draft_and_prompt`. Exercise Close/Done, Back, Escape/outside and route leave; edit→revert is clean, Keep editing preserves photo/notes/name/email, explicit discard creates no user/update/journal. Busy or unresolved writes block incidental exits; explicit Open recovery permits that route without repeating/cancelling a mutation. Auth/collection/Terminal session or route changes force-clear private state and suppress late profile reads/uploads/save/status success. Verify scoped pending-store cleanup never removes another context's entry.
- [ ] Add `profile_committed_save_refresh_failure_stays_successful` (committed native update then Members read fails: modal stays closed, success remains, read-only Reload members; Terminal read failure shows saved status plus Reload users, no profile form reopening/mutation); `profile_create_followup_read_failure_cannot_create_again` (confirmed create then optional-profile GET fails: `User created.` remains, offer read-only Reload profile/Done, no Create button/replayed POST); `profile_context_refresh_race_never_focuses_old_member` (held list refresh then switch context suppresses old focus/success and data). Retain photo/notes persistence, stable UUID, badge resolution, loan operation/date/history, name-only NULL-password and original web-account assertions. Replace the old verifier expectation that update reenables Save then requires Escape; assert immediate successful closure/list instead. Update exact Terminal creation status expectation to `User created.`.

```python
# Fixture request counters count only mutation paths, not operation/status reads.
assert create_posts == 1 and update_posts == 0  # create → unchanged Save
assert new_update_journal_rows == 0
assert profile_dialog.count() == 0             # native successful finish
assert success_message == 'Profile is up to date.'
# For an edited confirmed save, inspect the real fixture API/database:
assert update_posts == 1 and new_update_journal_rows == 1
assert saved_profile['id'] == member_id and saved_profile['notes'] == edited_notes
assert scope['ledger'].custody(group)[0]['operation_id'] == prior_loan_id
# Cancel keeps the draft; discarded creation never creates a native person.
assert kept_name == edited_name
assert not any(row['id'] == cancelled_draft_id for row in client.call('/api/v1/groups/members'))
```

- [ ] Build with `python3 deploy/build-homebox-ui.py`, then run `HOMEBOX_VERIFY_NATIVE_BINARY="$PWD/work/homebox-backend-build/homebox" python3 deploy/verify-desktop-integration.py`. Expected RED: current native/Terminal update reloads/leaves profile open, unchanged Save performs update, and Close/Back or idle Escape/outside discards changed fields. The existing verifier uses disposable native/HTTP/journal fixtures and fake physical outputs; do not run live verification scripts.
- [ ] Implement the native/Terminal baseline and completion branches together. Capture baseline after blank draft/profile load; compare only editable persisted fields, ignoring search/UUID/version/errors. Confirmed create acknowledges `User created.`, emits one changed ID natively and transitions once to optional profile; a failed follow-up read preserves creation success and offers only read-only reload/Done. A changed update or status-proven completed update calls successful finish once without `edit/userProfile`; unchanged Save first verifies no unresolved matching request, then finishes without mutation/changed event. Native changed success uses existing `toast.success('Profile saved.')`; no-op uses `Profile is up to date.`; Terminal uses matching status. `write` releases shared busy in its finally before returning, but local submitting may still be true: successful cleanup must not call guarded `close` or user-discard prompts. Parent/list reads are a separate error boundary and never undo confirmed success.
- [ ] Implement user dismissal through the same dirty snapshot: native local `Keep editing`/`Discard changes` prompt for Close/Back/Escape/outside and `window.confirm('Discard unsaved profile changes?')` for idle dirty route departure; Terminal uses existing leave/back guards with actual profile equality rather than sticky changed flags. Pending/uncertain keys remain blocked even for unchanged fields; expose explicit Recovery. On failed write, read `operation/status` with the captured key/identity (Terminal `resolveTransaction`) and never automatically repeat POST; only proven completed reaches finish. not_started permits explicit correction/retry with the unjournaled key; cancelled permits only explicit retry with a new key (and new UUID for definitively absent cancelled creation); review/pending/unknown retains draft/error/key. Scope any pending cleanup after a definitive status to the captured matching context: completion cleanup uses `forget(key)` only while user/group/identity still match; cancelled/previously pending not_started cleanup likewise cannot touch another context. Context/unmount teardown clears drafts/prompts/keys in memory and invalidates late results without clearing another pending store. Preserve busy protections during uploads/submission/status resolution. Native no-op emits only finished; Terminal may perform one read-only list load, without adding a cache.
- [ ] Rerun build/verifier plus `PYTHONPATH=ops:kiosk python3 -m unittest discover -s tests -p test_accounts.py -v` and `PYTHONPATH=ops:kiosk python3 -m unittest discover -s tests -p test_desktop_api.py -v`. Expected GREEN: all completion/dismissal/context assertions in both interfaces, Task 1 invalid-input and prior Terminal badge/loan tests pass, no added typecheck diagnostics/browser errors, `live_mutations:0`, `physical_prints:0`. No outstanding RED tests are deferred to Task 3.
- [ ] Sol High reviews create versus update/no-op branches, one-key/one-submit semantics, actual write-finally timing, completed versus uncertain recovery, scoped forget, dirty guards, parent refresh/focus races and privacy/identity preservation. Luna fixes/tests/re-review until the standalone combined lifecycle task is GREEN, then task-only commit before Task 3.

### Task 3: Preserve picture proportions in the shared helper

**Files:** Modify `kiosk/member-avatar.js:prepareMemberAvatar`; test `deploy/verify-desktop-integration.py`. Existing `deploy/build-homebox-ui.py` helper copy and `UserManager.vue`/`kiosk/users-ui.js` imports stay authoritative.

**Interfaces:** Preserve `prepareMemberAvatar(file: File) -> Promise<string>` and `memberAvatar(id) -> string`. Decode the source bitmap at its natural aspect, crop the centered square with source rectangle `(width-side)/2,(height-side)/2,side,side`, `side=min(width,height)`, and draw it to 128×128. Keep JPEG 0.85, white background, existing allowed MIME/size checks and `finally { picture.close(); }`.

- [ ] Add browser fixture assertion `avatar_rectangles_preserve_circle_proportions`: generate synthetic 300×100, 100×300 and 100×100 PNGs with a centered circle of diameter 70; call the real helper in Terminal and native UI build, decode saved JPEG, assert 128×128 and circle bounding widths/heights differ by at most 3 pixels (ignore JPEG antialiasing). Compare native/Terminal helper output for the same file and assert shared saved profile avatar. The old landscape result is approximately 32×101 for the confirmed circle fixture and fails aspect equality.
- [ ] Add `avatar_cleanup_and_bad_upload`: JPEG/WebP valid, transparent source has white background, empty/wrong MIME/over-20 MB and corrupt images reject without profile writes, bitmap closes on successful render and simulated draw/export failure; generated-picture reset still works and stripped image has no EXIF. Keep fixture data synthetic.

```python
assert decoded.size == (128, 128)
assert abs(circle_bounds_width - circle_bounds_height) <= 3
assert terminal_avatar == native_avatar
assert not decoded.getexif()
```
- [ ] Run the Task 2 build and fixture commands. Expected RED: rectangular circle proportions fail.
- [ ] Implement the specified centered crop in the one helper, without a second native/Terminal transform or dependency. Preserve existing Python/native upload validation.
- [ ] Rerun build/verifier and `PYTHONPATH=ops:kiosk python3 -m unittest discover -s tests -p test_accounts.py -v`. Expected GREEN: circle ratio checks and privacy/cleanup assertions pass, no added typecheck diagnostics, no physical outputs/live mutations.
- [ ] Sol High reviews crop math, orientation handling provided by browser decode, metadata/resource cleanup and shared build provenance. Fix/test/re-review, then commit accepted files only. Record physical photo/print acceptance as unperformed.
