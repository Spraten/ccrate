# SDD ledger — plan: docs/superpowers/plans/2026-10-20-touchscreen-check-in-out.md

## Authorization and workspace

- User approved the design spec and requested subagents implement the plan.
- User explicitly requires one codebase and no additional worktree. Work stays in the current `/home/user/Desktop/ccrate` checkout on `main`; do not create a worktree or push.
- User approved the badge-bound selected-item return lookup addition after the existing `/api/custody` borrower-name disclosure was discovered.
- Ruling: honor the explicit one-codebase constraint over the SDD default worktree isolation — use sequential agents, task reviews, and commits to keep shared edits reviewable. Cost if wrong: concurrent unrelated work in this checkout could overlap; mitigate with one implementer at a time and inspect status before every dispatch.

## Plan pre-flight scan

| Task(s) | Shared file/interface | Finding | Ruling |
| --- | --- | --- | --- |
| Task 1 ↔ Task 2 | `deploy/kiosk-server.py` | Task 1 changes authorization guards; Task 2 adds static terminal routes. Static routes must remain readable to members and not inherit manager guards. | Separate route branches; Task 1 tests both direct manager denial and Task 2 static availability. |
| Task 1 ↔ Task 4 | `deploy/kiosk-server.py` | Task 1 closes manager-only direct routes; Task 4 adds member badge-bound return availability. | Return availability is member-only and validates active badge/session; do not put it behind manager authorization. |
| Task 2 ↔ Task 3 | `kiosk/touchscreen.html`, `kiosk/touchscreen.js` | Task 2 owns shell/session; Task 3 adds checkout entry, selection, review, receipt. | Keep Task 2's session and navigation API stable; Task 3 consumes it and owns `checkout-ui.js`. |
| Task 2 ↔ Task 4 | `kiosk/touchscreen.html`, `kiosk/touchscreen.js`, session API | Task 2 owns shell/session; Task 4 adds return entry, review, receipt. | Use the same session generation/instance and navigation helpers; Task 4 owns `return-ui.js`. |
| Task 3 ↔ Task 4 | Shared review/receipt behavior | Both need clear, safe handling of one confirmation, receipt, and uncertainty. | Share presentation/session helpers only; retain distinct checkout and return payload validation. |
| Task 5 ↔ Tasks 1–4 | Tests and `deploy/verify-checkout-redesign.py` | Task 5 revises/extends contracts after the implementations. | Run only after Tasks 1–4 are individually reviewed. |

| Task | Internal consistency | Finding | Ruling |
| --- | --- | --- | --- |
| Task 1 | Access tests, migration, route guard | Manager actions must remain reachable via authenticated `/workshop-api`; member checkout/return must remain available. | Migrate or deny every legacy manager mutation; preserve badge transaction endpoints and prove manager/member behavior. |
| Task 2 | Static page, routes, session lifecycle | Client UUID must be sent consistently on session-owned requests. | Use `X-Homebox-Client` on every terminal API request and compare generation/instance before applying async results. |
| Task 3 | Search, scan, checkout, receipt | Search cannot add a confirmable item without server-recorded physical scan evidence; unknown confirmation cannot be resubmitted. | Keep scan evidence in the current badge generation and query operation status with the original request key. |
| Task 4 | Return lookup and transaction | Existing `/api/custody` exposes all borrower names and is not suitable for the kiosk. | Implement `GET /return/availability?ids=...`, scoped to 1–50 selected IDs and active badge; return only `{id, eligible, reason, condition, location}` and never borrower names. Any identified member may return a checked-out item; `/return/confirm` remains authoritative. |
| Task 5 | Whole-screen checks | Existing verification scripts contain conflicting historical expectations and some scripts mutate operational Homebox. | Use synthetic/intercepted browser data and inspect script behavior before running; avoid live mutations or device actions unless explicitly requested. |

## Task progress

- Task 1: complete — implementation commit `dbe1185`; reviewer approved. Focused access tests pass 12/12; full suite was interrupted and is incomplete. Report `.superpowers/sdd/2026-10-20-touchscreen-check-in-out/task-1-report.md`; review recorded in coordinator session.
- Task 2: complete — implementation `ed88249`; review fix `55c966d`; timer fix `1fcfd15`; review findings addressed. Focused static/shell tests pass; source-shape regression coverage remains a minor limitation. Report `.superpowers/sdd/2026-10-20-touchscreen-check-in-out/task-2-report.md`.
- Task 3: complete — implementation `5fd34b4`; fixes `ad64268`, `5e38ad7`, `1f42212`, `a4b2d88`, `efaae11` address supported search, independent physical scan matching, badge-bound saved cart, status-only recovery, captured-session receipt Done, and async cleanup race. Focused tests and scoped re-reviews pass. The old `test_checkout_cart_ui.py` cases referenced `kiosk/index.html` and legacy helpers absent at Task 3 base, so ruling: replace them with contracts against the new touchscreen flow and preserve saved-cart service coverage with current endpoint fixture tests; cost if wrong is losing intended behavior coverage from an untracked legacy UI, mitigated by actual route/behavior tests. Report `.superpowers/sdd/2026-10-20-touchscreen-check-in-out/task-3-report.md`.
- Task 4: complete — implementation `763e912`; coverage restoration `2a61808`; review fixes `ff209de` bind every return request to the same stable client UUID as badge/session calls and permit damaged checked-out items to be returned. Scoped reviewer approved with no findings. Focused return/API/checkout suites passed; no live Homebox access. Report `.superpowers/sdd/2026-10-20-touchscreen-check-in-out/task-4-report.md`.
- Task 5: complete — commit `3c09070` fixes checkout asset routing; follow-up fixes `[hidden]` CSS for home/inactive flow, hides the badge form after verification, and anchors checkout/return Review/Confirm actions in a shared bottom tray with reserved flow padding. The self-contained file-based Chromium verifier passed checkout and return badge→search→scan→review→confirm→receipt at 800×480, including no horizontal overflow, touch controls ≥44 px, visible primary actions, inactive flow hidden, long names/notes, return condition/location, and exactly one confirm request. All eight focused suites pass; manager tests require `PYTHONPATH=ops:kiosk`. Screenshots `/tmp/ccrate-checkout-review-800x480.png` and `/tmp/ccrate-return-review-800x480.png` were visually inspected. No dependency downloads, Homebox requests, devices, service restart, or deployment. Report `.superpowers/sdd/2026-10-20-touchscreen-check-in-out/task-5-report.md`.

## Decisions / unresolved findings

- Task 1's direct legacy manager-access boundary was approved by the task reviewer. The full project suite remains unverified because its run was interrupted.
- Task 1 review verdict: spec compliant; task quality approved; no findings. Reviewer verified direct legacy denial, authenticated manager badge operation, and terminal checkout/return preservation. Only future touchscreen home behavior remains to verify in later tasks.
- Task 2 review findings: add 120-second session activity/expiry behavior; connect Check out/Return to badge scanning and require a recognized member before continuing. Verify `/api/session` response shape and strengthen behavioral tests beyond static source-string assertions where feasible.
- Task 2 initial review findings (badge entry, activity timeout) and timer race were fixed in separate commits and re-reviewed. Reviewer confirmed timeout re-arms only on changed active session adoption and is not extended by unchanged polling.
- User authorized implementation, but deployment, push, service restart, and hardware mutation are outside this plan.
