# Terminal Badge Recovery and Member Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring Terminal badge safety and member loan details to the behavior already delivered by native Members.

**Architecture:** Route local badge actions through existing `ops/desktop_api.py:post_action`/`once` and print jobs; expose the existing enriched loan projection through one local read endpoint. Reuse Terminal navigation/status helpers and the native badge/loan display rules without adding another user directory or journal.

**Tech Stack:** Python stdlib/unittest/SQLite, existing badge/print helpers, plain browser JavaScript, existing Playwright disposable-native verifier.

**Spec:** `docs/superpowers/specs/2026-10-06-user-management-review-fixes.md`

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

- Committed issuance with lost browser reply → Task 1 `terminal_issue_lost_reply_never_creates_twice` and `terminal_badge_uncertain_confirmation_stays_blocked`.
- Removed/foreign member and changed confirmation identity → Task 1 `test_terminal_badge_routes_preserve_membership_and_request_binding`.
- Multiple active/legacy/revoked badges → Task 2 `terminal_reprint_and_legacy_replacement_keep_identity`.
- Duplicate names, zero loans and missing/broken saved images → Task 3 `terminal_member_identity_empty_loans_and_photo_fallback`.
- Route departure and unavailable current checkout date → Tasks 1/3 `terminal_member_late_response_does_not_reopen_view` and `terminal_loan_dates_use_completion_without_inventing_history`.

---

Execute after the common baseline/isolation gate, before the profile plan. Commands run from the isolated source root. Preserve preexisting work; task-only commits follow successful Sol High review. Use fake badge credentials and print adapters only.

### Task 1: Deliver safe Terminal issuance end to end

**Files:** Modify `deploy/kiosk-server.py` (`Handler.do_POST` issue/revoke branches), `kiosk/users-ui.js`, `kiosk/index.html` Administration handler; test create `tests/test_terminal_members.py`, modify `deploy/verify-desktop-integration.py`; inspect existing `tests/test_desktop_api.py`, `tests/test_labels.py`, `tests/test_badges.py` for reusable assertions. Reuse `kiosk/workflow-ui.js:api`, `resolveTransaction`, `leaveTask`, `workflowBusy`.

**Interfaces:** Require `request_key` on existing local POST `/badge/issue` `{user_id,request_key}` and `/badge/revoke` `{id,request_key}`; preserve `/badge/print` `{badge_id,code,request_key}`. Under existing `OPEN_ADMIN` and `lock`, create `Homebox(ROOT)`, load `/api/v1/users/self`, set `client.tenant=group`, and pass context `{client,actor,group,manager:True}` plus existing dependencies to `post_action(route, data, ctx, deps, '')` (the unused badge-route address argument is explicitly empty). The manager flag reflects the already-approved local setup guard only; it grants no desktop privilege. Preserve `/operation/status` and `/recovery/resolve` contracts. Add shared `confirmMemberBadge(route: string, payload: object, key: string): Promise<object>` in `users-ui.js`: call `api` once, return its successful result; on failure perform only `resolveTransaction(key)` and return `{...saved.result,status:saved.status}` with the original display error. Completed status refreshes saved badges without reissuing; pending/review/unknown keeps the confirmation blocked and links Recovery. Only explicit cancellation/not-started allows another confirmation. Add `issueMemberBadge(member: {id:string,name:string,email?:string}): Promise<void>` as the minimal existing Administration issuance view. Keep one stable key per visible issue/revoke confirmation, and a separate key for printing; no second journal.

- [ ] Create a disposable-root handler harness in `tests/test_terminal_members.py`, using the existing verifier's source-prefix loader to replace ROOT **before executing any module code**, omit the serving tail, stub camera/decoder dependencies, use fake Homebox, temporary Ledger/NativeJobs and mocked label adapter. Never import the production server at its operational ROOT. Add `test_terminal_issue_is_journaled_and_secret_free`, `test_terminal_issue_uncertain_result_refuses_repeat`, `test_terminal_badge_routes_preserve_membership_and_request_binding` and `test_terminal_setup_guard_denies_issue_and_revoke`.

```python
# In the fixture handler tests, with synthetic user/group/key:
assert first.status == 200
assert replay.status == 200
assert len(badges.list(group)) == 1
assert replay.result['code'] is None
assert request_row(ledger, group, key)['status'] == 'completed'
assert raw_code not in journal_text
assert changed_payload_with_same_request_key.status == 409
# Inject failure after badges.issue, before completion: retry is 409,
# exactly one active badge exists, request status is review, recovery is visible.
```

- [ ] Add verifier assertions before implementation: `terminal_issue_lost_reply_never_creates_twice` allows real fixture issuance to commit then aborts its HTTP reply, verifies the stable posted key, one badge, no second POST on another click, and secret-free completed replay; `terminal_badge_uncertain_confirmation_stays_blocked` injects a mid-action failure/status unavailability and verifies retained key, blocked confirmation and Recovery; `terminal_member_late_response_does_not_reopen_view` holds a reply while navigating and ensures old-person UI/QR never returns. Assert current Administration issue/revoke buttons send request keys, cancel creates/prints nothing, and recovery resolution issues/prints nothing.
- [ ] Run `PYTHONPATH=ops:kiosk python3 -m unittest discover -s tests -p test_terminal_members.py -v`, then `python3 deploy/build-homebox-ui.py`, `python3 deploy/build-homebox-backend.py` and `HOMEBOX_VERIFY_NATIVE_BINARY="$PWD/work/homebox-backend-build/homebox" python3 deploy/verify-desktop-integration.py`. Expected RED: current issue creates duplicate badges/no journal; Administration posts no key and reenables the failed button. Builders stage artifacts only in the isolated workspace with the common baseline prerequisites.
- [ ] Replace direct Terminal issue/revoke branches with the specified existing dispatcher; import shared `ApiError` and map its `status`/`message` into local JSON errors so membership rejection is not an unhandled exception. Implement the shared confirmation helper and minimum issuance/revoke view; replace every old inline Administration issue/revoke caller with keyed calls to that flow in this task. Retain separate explicit print confirmation and its existing native print journal. Revoke ends affected sessions using shared code. Validate member/UUID, reject stale/foreign IDs without mutation and keep journal results/intents QR-free. Show short UUIDs for duplicate names. Do not add reprint/replacement UI yet.
- [ ] Preserve busy navigation through Terminal helpers and suppress late responses with `routeRevision`. Keep QR only in the current explicit issuance result, clear it on leave, and never persist it in localStorage/lists/logs/recovery intent. Uncertain state and key survive redisplaying the same confirmation; another click cannot create a new request key. Recovery acknowledgment inspects saved state without issuance/print.
- [ ] Rerun all commands above plus `PYTHONPATH=ops:kiosk python3 -m unittest discover -s tests -p test_desktop_api.py -v` and `PYTHONPATH=ops:kiosk python3 -m unittest discover -s tests -p test_labels.py -v`. Expected GREEN: handler and full existing disposable browser/API suite, including all three new safety assertions; receipt `live_mutations:0`, `physical_prints:0`, no browser errors or added typecheck diagnostics. Task 1 is usable end to end before Task 2 starts.
- [ ] Sol High reviews every Administration caller, retained keys, lost-reply/unresolved distinction, auth/membership, shared journal/redaction, status binding, late responses and session revocation. Fix/test/re-review until every Task 1 check is GREEN, then task-only commit before advancing.

### Task 2: Add complete Terminal member badge controls

**Files:** Modify `deploy/kiosk-server.py` (allowed-path list and reprint/replace dispatch), `kiosk/users-ui.js`, `kiosk/index.html` Administration links; test `tests/test_terminal_members.py`, `deploy/verify-desktop-integration.py`. Consume Task 1's already-tested confirmation helper and inspect `BadgeActions.vue` for parity behavior.

**Interfaces:** Consume Task 1 `confirmMemberBadge(route, payload, key)` and `issueMemberBadge(member)` unchanged. Add `userBadges(member: {id:string,name:string,email?:string}): Promise<void>` in `users-ui.js`; retain native UUID for badge associations. Proposed new local POST `/badge/reprint` `{badge_id,request_key}` and `/badge/replace` `{badge_id,request_key}` map to existing desktop names through the Task 1 context/guard and `post_action(route,data,ctx,deps,'')`. The same stable-key and no-repeat behavior now covers these confirmations.

- [ ] Add `test_terminal_reprint_and_replace_dispatch_existing_helpers` and `test_terminal_setup_guard_denies_new_routes`. Add browser assertions `terminal_reprint_and_legacy_replacement_keep_identity` (reprint makes one fake print and zero badge rows, legacy replacement separately confirmed, old badge revoked/session ended, UUID/loans unchanged), `terminal_badge_cancel_and_multiple_selection` (Cancel performs no writes/prints; multiple active badges require selection; revoked badges cannot reprint), and `terminal_reprint_replace_uncertain_confirmation_stays_blocked` (both new actions reuse Task 1 no-repeat behavior on lost replies). Rename fixture profile before reprint and verify saved name with unchanged QR. Duplicate names retain short IDs in Manage users and Administration.
- [ ] Run Task 1 handler command, `python3 deploy/build-homebox-ui.py` then `HOMEBOX_VERIFY_NATIVE_BINARY="$PWD/work/homebox-backend-build/homebox" python3 deploy/verify-desktop-integration.py`. Expected RED: new route dispatch, reprint controls or explicit legacy replacement absent; all Task 1 assertions remain GREEN.
- [ ] Add the two guarded shared-dispatch routes and minimal per-member Manage badges/Reprint UI using `Badges.list`'s existing `id,user_id,revoked,reprintable,created_at`; mirror `BadgeActions.vue` confirmation text. Reprint calls `/badge/reprint`; unreprintable legacy selection separately confirms `/badge/replace`, then explicit `/badge/print`. Replacement ends affected sessions through shared code. Link Administration and Manage users to this UI; reuse Task 1 issue/revoke/helper rather than duplicating them.
- [ ] Apply Task 1 busy, revision and QR-lifetime protections to the additional controls. Rerun build/verifier and handler tests. Expected GREEN: all Task 1 and Task 2 named assertions, `live_mutations:0`, `physical_prints:0`, no browser errors or added typecheck diagnostics. Physical acceptance remains separately authorized.
- [ ] Sol High reviews parity controls, shared-helper reuse, explicit legacy replacement, uncertainty/session behavior and secret lifetime. Fix/test/re-review until all checks pass, then task-only commit before Task 3.

### Task 3: Show native loan details in Terminal Manage users

**Files:** Modify `deploy/kiosk-server.py:Handler.do_GET`, `kiosk/users-ui.js`; test `tests/test_terminal_members.py`, `tests/test_desktop_api.py`, `deploy/verify-desktop-integration.py`; reference `ops/desktop_api.py:get_action('loans')`, `MemberItems.vue`, `workshop-loans.ts`.

**Interfaces:** Proposed GET `/api/member-loans` is a local setup-admin read, guarded by `OPEN_ADMIN`. Construct the native tenant context as Task 1 and return `get_action('loans', {}, ctx, deps)` unchanged. Existing `/api/custody` remains unchanged for checkout callers. Loan fields are `entity_id,actor_id,entity_name,assetId?,unavailable?,checked_out_at?,imageId?,thumbnailId?` plus existing custody metadata. The date is the current custody operation's `completed` event timestamp (fallback its `created_at`), not a new refresh time. Reuse GET `/api/file?entity=<entity_id>&attachment=<imageId>` for full saved photos: the existing handler validates attachment ownership and expects a top-level attachment ID, so do not pass a thumbnail ID as if it were an attachment.

- [ ] Add `test_terminal_member_loans_reuses_native_projection` and `test_terminal_member_loans_respects_setup_guard`: compare local data with existing desktop projection, assert completion timestamp/primary `imageId`, collection-filtered custody, unavailable item fallback, and denied read when setup guard is off. Retain `DesktopTests.test_members_loans_use_completion_time_and_primary_photo`.
- [ ] Add browser assertions `terminal_member_identity_empty_loans_and_photo_fallback` (two same-name UUIDs have independent counts, zero reads as `0 items checked out`, no-photo/broken-photo has labeled placeholder); `terminal_loan_dates_use_completion_without_inventing_history` (known timestamp in `<time datetime>`, elapsed text follows fixed fixture clock, missing date says `Checkout date unavailable`/`Duration unavailable`); `terminal_member_loan_read_failure_is_unavailable` (503 shows Items unavailable, never zero). Assert saved item picture loads through `/api/file` without exposing native token, and no history/photo from another collection is shown.
- [ ] Run handler tests and the build/verifier commands pinned in Task 1 and retained in Task 2. Expected RED: endpoint 404, missing expandable details/counts; all prior badge safety/parity checks remain GREEN.
- [ ] Add per-member loan count and native `<details>/<summary>` dropdown in `userManager()`, filtered by `actor_id`, with existing member short ID/profile/picture and badge controls. Display saved photo with contain sizing and fallback, item name/asset ID, completion date and duration using `MemberItems.vue` formatting. Update elapsed duration on opening and at most once/minute while this view is active; clear timer or gate by revision on leave. Use current native UUID, never names, for filtering. On read failure offer explicit reload; discard late responses after route changes. Do not create new inventory/history storage.
- [ ] Rerun tests/build/verifier. Expected GREEN: all named parity assertions, existing desktop loan/badge checks and profile assertions pass; receipts show no browser errors/live mutations/physical prints.
- [ ] Sol High reviews native projection reuse, photo authorization, date provenance, duplicate IDs, empty/error distinction and view cleanup. Fix/test/re-review, task-only commit and whole Terminal diff review; execute the profile plan next, then review the combined profile/parity diff before release work.
