# C-Crate frontend consistency and quick actions

Status: design decisions confirmed through the user interview (Q1–Q26). This update records the agreed scope; it does not start implementation. Audit findings still require batch approval.

## Purpose and audience

Make C-Crate feel like one coherent workshop tool. Prioritize finding equipment, understanding its status and location, and completing a task without losing context. Optimize for someone who knows the workshop but has not learned C-Crate. The primary journey is find equipment → see availability/location → check out or add to cart; check-in and notes follow. The Pi desktop with mouse/keyboard is primary; touch and narrow-screen access remain supported. Preserve the current brand and native Homebox records.

## Confirmed requests

- Audit the frontend for inconsistent layouts, overlooked states, and confusing interactions, with user experience first.
- Use frontend-design, project-review-board and independent code review. Discuss the target experience and plan before implementing audit findings.
- Add Check out, Check in, Add to cart and Add note actions. Each opens a modal with a note field and an explicit confirmation.
- Everyone, including managers, must verify their badge inside the checkout popup. User confirmed this on 2026-10-19.
- Preserve recent improvements: Locations below Workshop; nested contents; thumbnails; equipment disclosures with a right-aligned `×5 ▸`; wheel zoom/middle-button map pan; per-object name visibility; live frontend updates.

## Constraints

- Homebox remains the inventory and account authority.
- Add no dependencies or external runtimes.
- Do not change operational inventory, custody, notes, or print output during verification; use isolated fixtures.
- Never automatically retry an uncertain write. Preserve its request key and use operation status or Recovery.
- Keep account and collection boundaries, role checks, badge verification, kit verification, and native history intact, including the explicitly approved member check-in/note policy in the shared spec.
- Use one coding worker at a time: GPT-6 Luna Low. Final implementation review: GPT-6.1 Sol High.
- Frontend source changes use the existing development watcher; Python changes need a controlled development-service restart. Do not require a production rebuild for frontend work.
- Do not stage or commit unrelated changes in the already-dirty working tree.

## Target experience

### Common structure

Open on Inventory with search immediately available; preserve explicit deep links and post-login destinations. Keep Workshop and Locations one click away. Restore search, filters, expanded bins/groups and scroll position when returning from an item, scoped to the current account and collection, with a visible Clear filters control.

Favor compact rows for a 20-bin cabinet, with small thumbnails and readable names. Collapsed groups show total count and an availability breakdown (for example, 3 available, 2 checked out), plus blocked and unknown states when relevant; keep `×5 ▸` on the right. Groups with no available units stay visible. On narrow screens prioritize name, availability, count and primary action; serial/asset identifiers remain visible in the unit chooser.

Use one navigation vocabulary and consistent title/action/filter/content placement. Primary actions are recognizable; destructive or administrative actions are distinguishable. Align count/disclosure controls at the right of grouped rows; keep thumbnail and name alignment stable. Avoid nested interactive elements. Item actions are for individual native IDs, never an arbitrary first member of a collapsed group.

Keep the existing installed font and theme system. Consolidate semantic tokens in `ccrate.css` and align legacy `workshop.css` with them; do not add fonts or impose a new palette. Before changing tokens, document the actual light/dark colors, typography, contrast and screenshots. Proposed spacing scale: 4, 8, 12, 16, 24, 32 px. Proposed list text: 14/20 px; supporting text: 12/18 px; modal body: 16/24 px. Controls have a 44 px minimum touch target, including compact icons. These are reviewable proposals, not measured current values.

At 390×844, 800×480, 1280×800 and 1920×1080, content and confirmations remain reachable. Preserve 200% browser zoom, visible focus, keyboard disclosure, Escape behavior, reduced motion and screen-reader names. Horizontal scrolling is permitted inside a labelled data table or map, not across the whole page.

### Quick actions

Desktop item rows show one prominent applicable check-in/checkout action, with Add to cart and Add note as secondary buttons in a consistent trailing action area. On narrow screens use a labelled Actions menu to avoid squeezing identifiers. Detail pages show the same actions. A group-level checkout opens a unit chooser showing serial/asset identifiers and available units first. A group must be expanded, or a unit explicitly selected, before a mutation can be confirmed; never choose a unit automatically.

Modal anatomy: action title; thumbnail/name/serial or generated ID/location; authoritative status; action-specific controls; labelled note field; inline error/status; Cancel and exact confirmation label. Preserve page scroll, filter, expanded groups and focus after completion. Refresh affected item status, history and cart count; avoid full-page reloads.

| Action | Required context | Note semantics | Confirmation |
|---|---|---|---|
| Check out | Fresh badge verification, current availability, physical verification required by existing item/kit rules | Optional per-item note saved with checkout receipt/history | Confirm checkout |
| Check in | Current loan; members may return their own loans, managers may return anyone’s; retain kit verification, no additional badge scan | Optional `return_note`; do not overload condition issue `note` | Confirm check-in |
| Add to cart | Signed-in member, current cart revision, exact selected item | Optional per-item private draft; carried into checkout history only when checkout completes | Add to cart |
| Add note | Any signed-in collection member, with trusted author and timestamp | Required nonblank append-only native item note; preserve previous notes | Save note |

Optional action notes use at most 1,000 characters per item. Standalone notes also respect the existing native 2,500-byte description limit including the journal marker. Empty optional notes are omitted. No separate hidden Add note request after checkout or return: note and operation outcomes must remain unambiguous.

Checkout popup sequence: review item → scan badge → satisfy item/kit verification → optional note → confirm → receipt. Web badge verification is scoped to the signed-in account, collection, popup attempt and selected items. It must not borrow the shared terminal's active badge session. Confirmed rule: badge holder must match the signed-in web user; explain mismatches and offer switching accounts; manager checkout on another person's behalf is outside this plan. Session inactivity expiry is 120 seconds, matching the current terminal default. Revalidate badge revocation and membership at confirmation. Changing account, collection or selected item invalidates the popup's verification.

A cart checkout uses one badge verification and one final confirmation for the selected items, with separate per-item notes. If any selected item becomes unavailable, stop and require selection review; never silently check out a subset. Changing the selected set invalidates its verification. Cart notes remain private drafts until checkout completes. Add to cart remains available for checked-out or condition-blocked equipment as a planning action; explain that it neither reserves equipment nor guarantees checkout. Existing eligibility restrictions on storage locations/archived records remain.

Check-in defaults to assigned storage, visibly displayed in the popup. “Returned somewhere else” allows an explicit valid destination change, journaled with the return. Members can change the destination of an item they are authorized to return; this does not grant general inventory-edit permission. For an item with no assigned location, show that honestly and allow choosing one.

Check-in includes Report a problem. Selecting it requires a description and records Needs Attention through the existing return workflow before the item can appear available. A normal return note does not change condition. Members can report problems; only managers can clear the resulting block after review. Keep report and resolution in history; uncertain or partially applied returns remain blocked through recovery.

Show the latest five notes in item details and a View all activity link; expanded compact rows show the latest note preview, while collapsed rows stay compact. Distinguish checkout, return and standalone notes with trusted author/time. These exact display limits implement the agreed “latest few” behavior.

Unknown status never appears as Available. Keep blocked actions visible with a reason where useful; hide actions that the current role cannot perform. While submitting, disable duplicate confirmation and prevent dismissing the modal. An uncertain outcome shows Check saved result and Recovery, never another automatic POST. An empty popup closes immediately. Closing a changed draft asks before discarding; cancellation never saves it. Confirmed success closes the popup, updates affected content, restores focus and shows a brief confirmation. Errors and uncertain outcomes keep the popup open with its input intact. Account changes clear private draft/verification state rather than transferring it to the new account.

## Source facts inspected for planning

- `components/Workshop/ActionDialog.vue` already provides modal structure and busy dismissal protection.
- `composables/use-workshop.ts` supplies native-session requests and pending-write recovery, but `write()` currently requires manager access for every action.
- `ops/desktop_api.py` exposes cart edits before the manager gate and administrative `return` after it; no current desktop checkout or standalone-note route exists.
- `ops/checkout.py:confirm_checkout` validates member/item/kit state and journals custody; it currently has no checkout-note argument.
- `deploy/kiosk-server.py` provides badge/session-bound checkout and notes. `ops/sessions.py:Session` is a single-terminal session, not a safe shared web-popup session.
- `ops/checkout_cart.py` stores IDs/revision only. Note persistence requires a backward-compatible extension; an extra frontend payload field alone would be ignored.
- `ops/item_notes.py:submit_note` already journals native maintenance entries with author/recovery metadata.
- Native summary lists omit model/serial fields. ChildContents now hydrates bounded item details; action status must likewise use authoritative services, not summary guesses.
- Existing tests can describe older behavior: `tests/test_desktop_checkout_return_ui.py` refers to `desktop/desktop.js` and expects a checkout route absent from current `ops/desktop_api.py`. Record this mismatch; do not claim those assertions establish current behavior.

These are source observations, not a completed visual audit or a passing test report.

## Audit and decision process

Capture representative workflows/states first, then trace observed inconsistencies to code. Four evidence streams cover product/UX/research, architecture/engineering, QA/accessibility/performance, and language/adoption; the coordinator covers PM. Use independent read-only agents in waves within the concurrency limit. Cross-examine major proposals before ranking P0–P3. Separate observed, reported, inferred and unknown evidence.

Audit every area; prioritize fixes for Inventory, Locations, Workshop and borrowing/returns/cart/history, followed by OCR, labels, users and secondary tools. Serious issues anywhere take precedence. Judge each recommendation by concrete task benefit: fewer unnecessary clicks, clearer information, easier recovery or better accessibility. Include manager/member, light/dark, loading/empty/error/stale/uncertain states. Measure request counts and actual Pi latency before changing fetch strategies. No speculative accessibility or performance score claims.

The report contains assessment, actual team exchange, prioritized issue register, unified direction, implementation batches, decision log and deferred work. Every accepted issue needs a screenshot or source citation, reproduction, owner, smallest fix/alternative, acceptance test and rollback scope. Unknown audit findings are not pre-approved refactors.

## Confirmed decision log

All interview recommendations Q1–Q26 were accepted, and the user confirmed the synthesized brief before requesting this plan update.

| Decisions | Agreed outcome | Implementation owner |
|---|---|---|
| Q1–Q6 | New-user clarity, find/borrow first, compact cabinet rows, primary/secondary action hierarchy, retain identity, task-based success | Consistency Tasks 1–4 |
| Q7–Q10 | Inventory landing, remembered place, group availability/counts, explicit unit chooser | Consistency Tasks 2–3; Quick actions Tasks 4–5 |
| Q11–Q13 | Member own-loan check-in; manager any-loan check-in; member append-only notes; changed-draft discard confirmation | Quick actions Tasks 3–4 |
| Q14–Q19 | Matching badge/account; no repeat badge for check-in; optional transaction notes; problem reporting blocks availability; unavailable groups remain; close only on confirmed success | Quick actions Tasks 1–4 |
| Q20 | Approve prioritized fix batches, then implement the complete batch without per-spacing approvals | Consistency Task 1 |
| Q21–Q26 | Visible/default return destination with change option; manager problem resolution; one verified cart confirmation; recent notes/history; narrow-screen priorities; full audit with core journeys first | Quick actions Tasks 1–5; Consistency Tasks 1–4 |

Approved role changes above supersede the earlier manager-only desktop check-in/note proposals. Changes to permissions, core workflows or visual identity beyond this brief require discussion; do not re-request approval for decisions already recorded here.

## Completion criteria

Audit findings have a disposition, not necessarily a rewrite. Approved P0/P1 issues are fixed or explicitly deferred by the user. Each enabled quick action completes its whole flow, retains notes as specified, preserves context, and handles uncertain results. Evidence includes focused fixtures, real Chromium walkthroughs at target sizes, before/after captures, independent review, and a live-development verification record. No claim of physical scanner/camera/printer testing without actually performing it.
