# Item Quick Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide consistent item-level Check out, Check in, Add to cart and Add note popups with truthful status, durable notes and explicit confirmation.

**Architecture:** Reuse ActionDialog, native cookie authentication, existing checkout/return/note services, and journaled recovery. Introduce a collection/account-bound web badge-verification session rather than sharing the physical terminal session. Extend cart and checkout contracts compatibly; mount one Vue action host for native pages and the imperative Workshop renderer.

**Tech Stack:** Vue/Nuxt, TypeScript and browser JavaScript, Python companion services, existing SQLite ledger/native-jobs journal, existing badge resolver, Chromium/Playwright and Node/Python fixture tests.

**Spec:** `docs/superpowers/specs/2026-10-19-frontend-consistency-and-quick-actions.md`.

## Global Constraints

- Homebox remains the inventory and account authority.
- Add no dependencies or external runtimes.
- Do not change operational inventory, custody, notes, or print output during verification; use isolated fixtures.
- Never automatically retry an uncertain write. Preserve its request key and use operation status or Recovery.
- Keep account and collection boundaries, role checks, badge verification, kit verification, and native history intact, including the explicitly approved member check-in/note policy in the shared spec.
- Use one coding worker at a time: GPT-6 Luna Low. Final implementation review: GPT-6.1 Sol High.
- Frontend source changes use the existing development watcher; Python changes need a controlled development-service restart. Do not require a production rebuild for frontend work.
- Do not stage or commit unrelated changes in the already-dirty working tree.

## Review Focus

- Badge revoked/expired, mismatched account, or changed collection during a popup: prevent mutation and request fresh verification; Task 2.
- Double confirm, disconnect after commit, or changed payload under the same key: recover the original receipt without duplicate custody/notes; Tasks 1–4.
- Kit changed since review or member already holds one component: do not permit an incomplete or stale checkout/return; Tasks 2 and 4.
- Existing carts, another tab’s edits, Unicode notes and explicit subset checkout (never silent partial checkout): preserve selections/notes and report conflicts; Task 1.
- Removed trigger, nested groups, narrow view or refreshed rows: restore sensible focus/context and never choose a different unit; Tasks 4–5.

## Approval and policy

The user confirmed all interview decisions Q1–Q26. Everyone verifies a matching badge inside checkout; no manager bypass or checkout-on-behalf. Members may check in their own loans without another badge scan; managers may return anyone’s. All signed-in collection members may append attributed notes and edit their own cart. Members can report problems; only managers can clear problem blocks. Return destinations default to assigned storage and can be explicitly changed during an authorized return. These approved changes replace the earlier manager-only check-in/note proposals.

The adjacent consistency plan covers audit-led visual fixes. The shared action anatomy and permission decisions are confirmed; execution remains a separate step after this documentation update, and it does not authorize unrelated visual/architecture changes.

## File map

Backend modify: `ops/returns.py` (authorized return/destination/problem handling), `ops/problems.py` and `ops/reviews.py` only if journal integration requires changes, `ops/checkout_cart.py` (versioned selection + notes), `ops/checkout.py` (note-bearing checkout intent), `ops/desktop_api.py` (authenticated action adapters/status/history), `deploy/kiosk-server.py` (service wiring and compatible cart-note handoff). Read/reuse `ops/{badges,sessions,kits,returns,item_notes,ledger}.py`.

Backend create: `ops/web_item_actions.py` (web popup verification and authorization service, without changing terminal session ownership).

Frontend create under `homebox-ui/overlay/`: `lib/item-action-contracts.ts`, `composables/use-item-actions.ts`, `components/Workshop/ItemActionHost.vue`, `components/Workshop/ItemQuickActions.vue`.

Frontend modify: `composables/use-workshop.ts`, `components/Workshop/{ActionDialog,ItemLoans,ItemLog}.vue`, `components/Location/ChildContents.vue`, `lib/{workshop-tools.js,workshop-loans.ts}`, `pages/workshop/[tool].vue`, and `deploy/build-homebox-ui.py` for native page/list mounts and the one layout host. The audit identifies exact native Item table/card overlay targets before Task 5.

Tests: extend `tests/{test_checkout_cart,test_checkout,test_desktop_api,test_item_notes,test_returns}.py`; create `tests/test_web_item_actions.py`, `tests/item_actions.test.mjs`, `tests/item_actions.browser.mjs`. Existing old desktop source-contract tests must be triaged against actual served code, not silently weakened.

### Task 1: Durable cart and checkout notes

**Files:** modify `ops/checkout_cart.py`, `ops/checkout.py`, relevant adapters in `ops/desktop_api.py` and `deploy/kiosk-server.py`; extend cart/checkout tests.

**Interfaces:**
- Cart state becomes `{revision:int, items:list[UUID], notes:dict[UUID,str]}`. Keep `items` as IDs, not objects.
- `CheckoutCart.save(group, actor, items, revision, request_key, notes=None)`: omitted notes preserve current notes for retained items; explicit mapping replaces draft notes, and keys must be selected item IDs. New selections default to no note.
- `confirm_checkout(..., cart_context=None, notes=None)` adds an optional trailing argument, preserving old callers. Notes map exact checked-out native IDs to strings. Journal normalized notes in both operation intent (replay identity) and context (history), even without cart context.
- Checkout cart snapshot includes notes along with revision/items/original_items. Notes on a selected kit root attach to that root's history; component-specific notes require explicit component selection in review. Never silently duplicate one note across all components.

- [ ] Add `test_cart_notes_legacy_rows_and_payloads`, `test_cart_notes_revision_and_replay`, `test_checkout_notes_bound_to_receipt`, `test_cart_consumption_preserves_other_notes`: assert empty notes for old rows; retained notes survive legacy caller updates; removed item notes are removed; concurrent revision yields Conflict; replay returns identical result; changed notes under the same key conflict; only successfully consumed original roots lose notes.
- [ ] Add note-limit cases: 1,000 characters accepted, 1,001 rejected, invalid Unicode rejected, extraneous IDs rejected; failure leaves cart/custody unchanged. Assert a failed/uncertain checkout never produces an extra standalone-note job.
- [ ] Run `PYTHONPATH=tests:ops:kiosk python -m unittest test_checkout_cart test_checkout` and record expected contract failures.
- [ ] Add a transactional additive `notes TEXT NOT NULL DEFAULT '{}'` migration for cart rows. Normalize maps before hashing; include notes in new request digests. Preserve old receipt results and supply missing `notes:{}` at read boundaries. Extend consumption receipts and both checkout entry points to carry notes without discarding old clients' drafts.
- [ ] Update desktop history projection and `lib/workshop-loans.ts` to expose `checkout_notes: [{entity_id,text,author,created_at}]`, with author/time derived from the journaled operation, not browser fields. Native standalone notes remain a separate category.
- [ ] Repeat tests, independently review compatibility/replay behavior, and commit only task hunks as `feat(cart): preserve item notes through checkout receipts`.

### Task 2: Isolated badge verification inside web checkout

**Files:** create `ops/web_item_actions.py`, `tests/test_web_item_actions.py`; modify `ops/desktop_api.py`, dependency wiring in `deploy/kiosk-server.py`; reuse `Badges.resolve`, `Session`, existing kit/code resolution and `confirm_checkout`.

**Interfaces (new authenticated POST routes):**
- `item-actions/verify-badge`: `{attempt_id:UUID, badge_code:str, item_ids:UUID[]}` → `{verification_id:UUID, borrower:{id,name}, expires_in:120, required_items:UUID[], kit_versions:object}`.
- `item-actions/verify-item`: `{verification_id:UUID, code:str}` → `{verified_items:UUID[], required_items:UUID[]}`. Resolve scanned native codes on the server; never accept an arbitrary browser-supplied verified list.
- `item-actions/checkout`: `{verification_id:UUID, assets:UUID[], notes:Record<UUID,str>, request_key:UUID, cart?:{revision,items,notes}}` → existing journaled checkout receipt.
- `item-actions/cancel`: `{verification_id:UUID}` invalidates only this popup session; no custody mutation.
- `WebItemActions.verify_badge(ctx, badges, data)`, `.verify_item(ctx, data)`, `.checkout(ctx, ledger, data)`, `.cancel(ctx, data)` encapsulate the route behavior. `ctx` is server-authenticated native client/account/collection/identity; browser actor/group fields are rejected.

- [ ] Add `test_web_badge_isolation`, `test_badge_expiry_revocation_and_account_match`, `test_checkout_requires_server_scan_evidence`, `test_checkout_replay_after_expiry`: two accounts/tabs and two collections cannot consume each other's verification; 120 seconds of inactivity expires; revoked badge blocks confirm; manager cannot bypass badge; changing selected items invalidates proof; kits use the existing physical verification rules; matching completed request returns its receipt even after session expiry.
- [ ] Run `PYTHONPATH=tests:ops:kiosk python -m unittest test_web_item_actions test_checkout`; record expected missing-route/service failures.
- [ ] Implement a bounded in-memory registry of independent `Session` objects keyed by random verification IDs and bound to native identity, group, user, attempt and item set. Maximum four active attempts per account/collection, 256 total; reject excess rather than evict another active session. Prune expired records. Keep terminal Session untouched and raw badge codes out of persistence/logs. Repeating a live attempt for the same owner/items returns the existing verification; a different identity/selection conflicts.
- [ ] Resolve badge membership through the existing Badges service, require badge holder equals native user, and recheck badge revocation/membership at confirm. Use server-owned scan evidence and manifest versions. Require native origin/binding, reauthentication under the existing write lock, and native credentials; never use service credentials for web writes.
- [ ] Check existing operation status/replay before requiring a still-live verification for a previously completed request. New writes require fresh verification. A process restart expires unsubmitted proof; persisted journal recovery still works.
- [ ] Repeat tests with session switches and concurrent windows, request independent security review, then commit scoped changes as `feat(checkout): verify badges within isolated web action sessions`.

### Task 3: Member check-in, notes, problem reports and request recovery

**Files:** modify `ops/desktop_api.py`, `ops/web_item_actions.py`, `ops/returns.py`, `composables/use-workshop.ts`; reuse existing `ops/problems.py` and `ops/reviews.py` journal semantics; create `lib/item-action-contracts.ts`; extend API/note/return tests with problem-report and resolution fixtures and create `tests/item_actions.test.mjs`.

**Interfaces:**
- `POST item-actions/note`: `{entity_id:UUID,note:str,request_key:UUID}` → `submit_note` receipt. Allowed for all signed-in collection members, trusted author from current native user. Route reuses `submit_note(client,jobs,group,actor,key,{entity_id,note},author_name)`.
- `POST item-actions/checkin`: `{targets:[{entity_id:UUID,destination_id?:UUID,return_note?:str,problem_description?:str}], verified:UUID[], kit_versions:object, request_key:UUID}` → existing return receipt. Under the mutation lock, require every target’s current borrower to equal the authenticated member, or require manager role. Mixed-owner selections are rejected for members before any mutation. Preserve existing kit verification requirements; no badge verification is added to check-in.
- The check-in adapter maps a nonblank problem description to existing `condition:'Needs Attention'` and issue `note`; normal `return_note` stays separate. Members cannot supply arbitrary conditions or clear blocks. Default destination retains the existing parent; an explicit alternate destination must exist, belong to the current collection and pass native move/containment rules. Record destination changes and problem reports within the return journal, not a subsequent independent write.
- `GET item-actions/status?ids=<comma-separated IDs>` → `{items:[{id,availability:'available'|'checked_out'|'blocked'|'unknown',blocker?:str,loan?:{borrower_id,borrower_name,operation_id},can_checkin:boolean,can_add_note:boolean}]}`. Limit to 50 unique IDs, validate collection access, derive permissions server-side and keep unavailable records unknown rather than guessing. Availability buckets are exclusive: checked out takes precedence over a condition block; otherwise blocked, otherwise available only after all checks succeed, with unknown on missing status. Preserve any secondary blocker text. UI combines pages without counting duplicates; grouped counts are labelled incomplete until all relevant member statuses are loaded.
- `ItemActionKind = 'checkout'|'checkin'|'cart'|'note'`; `ItemActionRequest = {kind:ItemActionKind,itemId:string,source:string} | {kind:'checkout',itemIds:string[],cartRevision:number,source:'cart'}`; `ItemActionResult = {kind,itemIds:string[],receiptId?:string,cartRevision?:number}`.
- Extend `useWorkshop.write` with a narrowly enumerated policy for verified checkout, own-loan check-in, member notes and existing member cart routes. All unrelated manager routes stay manager-required; only the server can decide whether a member owns a current loan. Server authorization remains authoritative. Preserve request intent/owner for these actions in PendingAction and attach the stable request key to surfaced errors.

- [ ] Add `test_desktop_note_permissions_and_trusted_author`, `test_member_checkout_requires_verified_route`, and `test_member_cannot_use_manager_writes`; assert members can append notes but cannot forge another author or clear problem blocks; assert origin/identity/account switch checks, native note journal/recovery, 1,000-character/native-byte limits, and no writable browser author.
- [ ] Add `test_member_return_ownership_rechecked_under_lock`, `test_member_cannot_return_other_or_mixed_loans`, `test_manager_return_records_actual_actor`, `test_return_destination_defaults_and_validates`, `test_problem_return_blocks_until_manager_resolution`, and `test_action_status_permissions_and_unknown`. Assert no extra badge for own-loan returns; a changed borrower/kit blocks confirmation; cross-collection or invalid destination is rejected before writes; a description is required for Report a problem; ordinary notes do not change condition; problem/history/destination steps are recoverable and unfinished returns remain unavailable; only a manager’s verified resolution clears the block.
- [ ] Add Node cases for duplicate confirm, timeout after submission, corrupt/unavailable pending storage, and account switch: no mutation is sent unless its pending intent is safely recorded; status checks use the original key and never resubmit.
- [ ] Run `PYTHONPATH=tests:ops:kiosk python -m unittest test_desktop_api test_item_notes test_returns test_web_item_actions` and `node --test tests/item_actions.test.mjs`; record expected failures.
- [ ] Implement member note and check-in adapters, authoritative status and explicit route policy, including member-owned operation status and collection-authorized history access. Keep the legacy administrative `return` route manager-only; both new and legacy routes reuse the journaled return service. Recheck ownership immediately before starting a new return. A completed replay uses the original receipt even though custody has already changed; mismatched intent conflicts. Do not expose general condition/move privileges to members. Apply the Needs Attention block before final custody release; incomplete native steps remain an unresolved operation so availability stays blocked. Reuse manager review/resolution with audit history; no automatic Ready reset on ordinary check-in. Ensure cart retry checks its own persistent request receipt (extend operation/status to lookup actor-scoped cart requests) rather than reporting not_started for a committed cart save.
- [ ] Repeat checks and review role/recovery boundaries before committing `feat(actions): expose journaled item notes and scoped action recovery`.

### Task 4: Shared action state and complete popup flows

**Files:** create `composables/use-item-actions.ts`, `components/Workshop/ItemActionHost.vue`, `components/Workshop/ItemQuickActions.vue`; modify ActionDialog only if needed. Create browser fixtures with authenticated API doubles and native response shapes.

**Interfaces:**
- `useItemActions()` returns `{open(request:ItemActionRequest):void, close():void, state, changed}`. State phases: `closed|loading|review|verifying|submitting|uncertain|success|error`; one shared popup per app, scoped to current identity/group. `changed` emits ItemActionResult only on confirmed success.
- `ItemQuickActions` props `{itemId:string, compact?:boolean}`; a group action opens an explicit unit chooser (available units first, serial/asset ID always visible) before passing an itemId. The cart passes the separate multi-item request variant; action visibility comes from trusted permissions/status, not guessed summary fields.
- `ItemActionHost` uses existing ActionDialog and renders the four action modes. Provide stable test IDs for action buttons, note input, confirm, badge scan, item scan and receipt status. Scanner keyboard input works inside the modal; optional camera input reuses the existing scanner capability with explicit user activation.

- [ ] Add browser cases `checkout_badge_then_confirm`, `checkin_return_note`, `cart_note_atomic_save`, `append_item_note`, `unknown_result_status_only`, `kit_manifest_changed`, `cancel_draft`, `long_unicode_note`, `modal_small_screen_focus`, `member_own_return_without_badge`, `changed_draft_discard_prompt`, `empty_draft_closes_immediately`, `problem_description_required`, `return_elsewhere`, `single_badge_cart_confirmation`, and `cart_blocked_member_stops_whole_selection`. Assert correct payloads, borrower attribution, note persistence, one request per confirmation, fresh availability, kit checks and unchanged custody on cancel.
- [ ] Run `node --test tests/item_actions.test.mjs` and `node tests/item_actions.browser.mjs`; record failures for missing component/controller behavior.
- [ ] Implement the shared controller and modal: load current item/loan/kit/status, maintain draft through recoverable errors, use exact confirmation copy from the spec, prevent closing during submit, and expose only Check saved result/Recovery for uncertainty. Require status refresh after a conflict; don't invent availability. Add to cart loads latest state, deduplicates item IDs and honors revision/50-item limit. Checked-out or condition-blocked equipment remains eligible for cart planning with a non-reservation explanation. Cart checkout uses one verification and one final confirmation for the reviewed set; a newly unavailable member stops the whole confirmation and requires explicit selection review, never silent partial checkout. User removal of items changes the set and requires fresh verification. Display per-item notes throughout review.
- [ ] Show assigned storage by default with Returned somewhere else selector and Report a problem requiring a description. Ask before discarding any changed draft, but close untouched popups immediately. Close automatically only on confirmed success, then show a brief confirmation and update the affected content; keep errors/uncertain outcomes open with draft intact. Clear sensitive verification state on close/account/group changes; restore focus to the triggering action or its surviving row. Never clear another user's pending records. For expired badge verification, retain the note draft in the current popup but require re-verification.
- [ ] Repeat browser checks at all four viewport sizes, light/dark and keyboard-only. A note written with an action must be visible in its resulting history; cart draft notes must not appear in shared history before checkout.
- [ ] Request independent review, then commit scoped changes as `feat(ui): add consistent item action confirmation popups`.

### Task 5: Connect all item surfaces and preserve context

**Files:** modify `ChildContents.vue`, `ItemLoans.vue`, `ItemLog.vue`, `lib/workshop-tools.js`, `pages/workshop/[tool].vue`, source builder mounts; add native table/card overlays selected during the audit. Update `docs/BETA_HUMAN_TEST.md`.

**Interfaces:** append an optional eighth positional argument `onItemAction(request:ItemActionRequest):void` to `mountWorkshopTools(root, initialPage, workshop, navigate, notify, initialSelection, labelWorkspaceChanged, onItemAction)`. Preserve its seven existing arguments and callers; omit quick-action buttons when the callback is absent. The Vue page passes the shared controller's open function rather than dispatching DOM events carrying credentials. Consumers of `changed:ItemActionResult` refresh only affected status/history/cart data; direct subscriptions are torn down on unmount.

- [ ] Add browser cases covering individual child rows, expanded equipment groups, native inventory table/card, item details, map-selected native equipment and current loans. Assert identical action names; collapsed groups do not execute against their first item; no item mutation actions appear on storage locations or drawing-only shapes.
- [ ] Add cases for 20 bins, active filters, collapsed/expanded groups, virtualized/removed triggers and an action finishing after navigation. Assert scroll/filter/disclosure preservation, no stale success in a different collection, and at most 50 IDs per availability request with bounded concurrency; do not fetch full inventory for row actions.
- [ ] Run the Node/browser checks and existing affected location/cart/history tests; record baseline failures against old desktop sources separately. Preserve terminal behavior tests.
- [ ] Mount one host in the native layout and reuse the action row across surfaces. Route old administrative return entry points through it where behavior matches; keep the manager’s broader condition-editing flow distinct, while exposing the approved return destination and problem-report controls in the shared popup. Update checkout-cart copy so badge verification inside the modal replaces the obsolete mandatory navigation to the kiosk, only once Task 2 is complete.
- [ ] Show checkout, return and standalone notes distinctly with trusted author/time: latest five in item details plus View all activity, latest note preview only in expanded compact rows. Add `recent_notes_types_and_limits` browser coverage and verify older activity remains accessible. Group summaries show available/checked-out/blocked/unknown counts plus total; a zero-available group stays visible with checkout disabled and cart planning available. Add `group_unit_chooser_no_implicit_target` and `unavailable_group_cart_planning` cases. Invalidate scoped metadata/status caches following successful actions and keep the right-aligned count/disclosure pattern.
- [ ] Run all focused commands below, inspect before/after captures, obtain final GPT-6.1 Sol High review, and resolve important findings. Commit only scoped approved hunks as `feat(ui): connect quick actions across equipment views`.

## Final verification and rollout

Run `PYTHONPATH=tests:ops:kiosk python -m unittest test_checkout_cart test_checkout test_returns test_item_notes test_desktop_api test_web_item_actions`, `node --test tests/item_actions.test.mjs tests/location_child_contents.test.mjs tests/equipment_groups.test.mjs`, and both `node tests/item_actions.browser.mjs` and `node tests/frontend_consistency.browser.mjs` once available. Run `git diff --check`. Do not imply every historical test passes; report actual executed results and unrelated baseline failures.

Before enabling the UI, apply/review backend migrations and routes in the isolated development data environment, then perform the authorized development-service restart. Use fixtures for mutations. Confirm served frontend source, compiled modules, service health and contract versions; an old backend must disable unavailable actions with a clear explanation, not accept and discard notes. Inventory/locations UI changes can hot reload. No production build is required, but backend changes are not hot-reloaded automatically.

Rollback: hide/disable new action entry points first; revert scoped frontend/backend adapter commits while retaining additive cart-note columns and completed operation context. Never roll back custody/history rows or destroy stored notes. Older cart callers preserve retained notes, and immutable completed receipts remain readable. Schema removal is not part of rollback.

## Self-review and handoff

The spec's four actions, note semantics, badge policy, confirmed member/manager permissions, destination/problem workflow, context preservation and failure states map to Tasks 1–5. Shared action types are defined in Task 3 and consumed unchanged by Tasks 4–5. All five Review Focus conditions have named fixture cases. Existing native APIs and tests are distinguished from proposed interfaces. No implementation or visual audit was performed as part of writing this plan.

Execution recommendation: subagent-driven, one coding worker at a time with independent review per task. Review this plan and the shared spec before implementation, against the confirmed Q1–Q26 decision log. No further approval of those agreed permissions is needed; implementation and audit fix batches are separate steps.

## Interview change record

The user confirmed Q1–Q26 and requested this plan update. The former manager-only desktop check-in/note defaults are superseded. Task 3 now owns member return authorization, return destination changes, problem blocking and manager resolution. Tasks 4–5 own the specific-unit chooser, single-confirmation cart flow, discard warning, success/error behavior and recent activity display. Existing source observations in the shared spec describe the pre-implementation baseline, not the approved target policy. No product code is changed by this update.
