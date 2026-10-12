# User work queue

## October 12 main integration

The user requested merging completed work onto local `main` and restarting the application for testing. Accepted Terminal member parity and profile name validation are being reconciled with the canonical maps, rooms, Shelf Checks, labels and item notes. The unfinished Profile Tasks 2–3 remain in their existing workspace. The native service startup layout has been repaired; final integration checks and release selection are in progress. The main checkout has no configured remote.

Finish the active task before starting queued work. Updated October 10, 2026.

## Current execution status — October 10, 2026

Terminal member parity Tasks 1–3 and Profile review Task 1 are accepted in the candidate at commit `bf88fef`. Profile Task 1 enforces the trimmed 255-byte UTF-8 name limit in native and companion APIs; its pinned native build, eight disposable native checks, account tests, stubbed Desktop API tests, and focused Terminal create/update checks are recorded in `work/queue-coordinator/profile-task1-utf8-evidence.json`. The full desktop verifier is not claimed as passed: the legacy Pi label selector skipped, and an unstubbed unit-test attempt hit two optional `qrcode` import errors. There were zero live mutations or physical prints. No release was made. The active serial task is Profile review Task 2; continue the remaining approved profile and matched-release/integration queue with the existing release gates. The five-minute metadata-only queue watchdog remains active.

The October 9 Shelf Checks and whole-map integration checkpoint remains historical: its current evidence is in `/home/user/canonical-integration-20261009/`, and no Shelf Checks deployment has occurred.

The user requested removal of backups, databases, notes, unused scripts and
one-off test output, targeting about 10 GB reclaimed. Cleanup must exclude the
live `work/baseline` database and `work/ops/ledger.db`, which running services
use. The recurring queue watchdog is enabled again at five-minute intervals,
with a successful metadata-only observation and active-root/worker safeguards.
Cleanup completed October 9: approximately 10.5 GB was reclaimed by
removing old restore snapshots and the private integration backup, Go package
and build caches, generated UI builds, disposable browser profiles, the old
Playwright environment, downloaded Rust components and a duplicate rollback
payload. Source, queued test code, the live databases, `program-files/runtime`,
the active floorplanner preview and all unfinished worktrees were retained. The
completed clean `device-status-isolation` worktree was removed; its branch and
published runtime remain. Four services are still active and the preview
returns HTTP 200.

## Current status

The persistent queue goal and five-minute watchdog are active. Profile Task 1 is accepted; Profile Tasks 2–3 remain. Matched-release and whole-map integration checkpoints remain fixture-only until production bundle compatibility is proved. Continue the active profile plan, then resume the remaining integration and matched-release work with exact compatibility, backup and same-store gates retained. Preserve native inventory, private data and durable recovery.

The integrated Terminal and label release is deployed and verified (October 8), transaction `2d0d40c8-6d22-405b-bc5f-e2accfa611cc`. The merged source passed 291 tests, publisher faults 17, same-database O→C→F→C, 12 built device checks and focused native/Terminal UI checks. A private local cold backup preceded publication. Both interfaces select `homebox-ui-releases/terminal-label-20261008/{public,kiosk}`. Authenticated candidate health passed with 130 matching assets and zero browser errors. Broad desktop attempts remain partial failed fixture runs, not suite passes. Receipts: `work/terminal-label-integration/`.

Item log/notes is now deployed and verified (October 8), transaction `c45325ef-2319-433d-82d1-f0425cbd6165`, preserving the integrated release above. Both interfaces select `homebox-ui-releases/item-notes-20261007/{public,kiosk}`. The merged source passed 336 tests with no skips; publisher faults passed 20 and backup fixtures 12. Built ItemLog, Terminal notes, native Recovery, device status and focused label/action-switch checks passed; real same-database O→C→F→C preserved new uncertain notes and existing uncertain labels. A fresh private backup and O health check preceded publication. Candidate live health verified both public notes markers and 130 assets with zero browser errors or unexpected writes. See [ITEM_LOG_NOTES_RELEASE.md](ITEM_LOG_NOTES_RELEASE.md).

The five-minute watcher is enabled and observed successfully. Desktop map Task 5
is accepted at isolated commit `661bea7`, and Terminal Task 6 plus all of Stage
1 are accepted at `a14e7c5`. Rooms Tasks 1–4 are accepted in isolation; the
current acceptance state and queue are recorded in `work/queue-coordinator/`.
Earlier dated statements below retain their historical scope.

The October 7 C-Crate rename and Printer/Camera status release is published and
verified. The deployed native public and Terminal selectors, unchanged native
binary, live smoke results and launcher text update are recorded in
[C_CRATE_RELEASE.md](C_CRATE_RELEASE.md). The fresh compatibility and rollback
gate approved this bounded transaction; it does not establish historical
companion/build provenance, and the immutable earlier handoff remains unchanged.

The implementation queue below is unchanged. The integrated item QR label
editor and item log/notes are deployed; floor-plan work is next. Optional web passwords and QR-plus-PIN verification retain their
existing future plan. Original physical acceptance checks remain documented
separately in PROJECT_STATE.md.

The following isolated-worktree and planning entries record their earlier state; the October 8 deployment status above supersedes their release-pending statements.

The isolated source workspace is `work/review-fixes-isolation` on branch `review-fixes-20261007`, starting at snapshot `820f1d8`. All 221 existing fixture unit tests passed using the already-installed Python dependency path. Native/static hashes match their existing manifests, but historical companion/builder provenance is incomplete. That historical limitation was resolved for the October 7 C-Crate deployment only by a fresh bounded source/static and rollback gate; this does not establish historical provenance or pre-approve future releases. See the local `work/review-fixes-baseline-report.md` and [C_CRATE_RELEASE.md](C_CRATE_RELEASE.md).

The separately requested Terminal return fix is ready in `work/terminal-camera-focus-isolation` on branch `terminal-camera-focus-20261007`. Scan startup initializes autofocus and retains manual focus controls; returns offer an explicit no-badge path, recorded as “Unidentified returner,” while preserving borrower history and kit verification. Sol High reviewed the corrections, and the coordinator independently verified all 235 isolated fixture tests, including the browser callbacks. No physical camera clarity check, source integration, service restart or deployment has occurred. This parallel fix does not reorder the approved work below.

The requested item action switch is now implemented and reviewed in that isolated workspace: when Return finds an item that is not checked out, offer checkout using the already selected item; when Checkout finds an item already checked out, offer return. Keep the source list available, revalidate custody, retain badge requirements and protect uncertain operations. Luna Medium implemented it; Sol High approved the final source and test harness. The coordinator independently verified all 235 isolated fixture tests with no skips and unchanged reviewed/tested file fingerprints. Browser tests exercise actual scan, badge polling, picker and navigation callbacks; the harness reuses the existing installed Playwright/Chromium. No source integration or publication has occurred. The next queued coding assignment is the label maker.

The requested printer/camera connection indicators beside native search and the displayed-name correction to **C-Crate** were implemented and Sol High reviewed in `work/device-status-isolation` on branch `feature/device-status-buttons`, source/report HEAD `5dab98c`. Connection Test/Reconnect use read-only probes. The frozen source/public handoff is `work/c-crate-device-status-review-5dab98c` with verified hashes and review receipts. On October 7, the bounded source/static release was published; its 221 baseline and 222 candidate unit tests, 12 device checks, 8 Terminal checks, same-database baseline→candidate→baseline compatibility fixture and authenticated live smoke are recorded in [C_CRATE_RELEASE.md](C_CRATE_RELEASE.md). The full baseline desktop suite passed 38 checks before the existing Recovery UI inspect-row timeout; it is recorded as a partial known failure, not a suite pass. The immutable handoff and original queue order remain unchanged.

**Latest priority instruction, October 7:** the current C-Crate release assignment is complete. Work on the label-maker implementation next, then the new item log/notes section, then the floor-plan redesign. This preserves the revised order after the approved fixes. Keep the earlier approved plans and isolated sources intact; deployment of those future tasks remains separately gated.

## Planned follow-up

First preserve the dirty source and a proven matching caci.2 baseline in isolation.
Then complete these reviewed tasks in order, with one Luna Medium coding worker
and Sol High review/fixes/tests before the next task. Plan preparation made no product changes or deployments. Execution is approved; deployment remains separately gated.

1. [Terminal badge recovery and member parity](superpowers/plans/2026-10-06-terminal-member-parity.md): journal Terminal badge issuance against lost replies; add reprint/replacement and per-member loan counts/dropdowns with saved pictures, original checkout dates and elapsed durations.
2. [Profile review fixes, revised October 7](superpowers/plans/2026-10-06-profile-review-fixes.md): enforce native name byte limits; make confirmed Save profile close/return to users with success, and unchanged Save finish without an update; combine safe completion, recovery and unsaved-draft guards in both interfaces; preserve rectangular picture proportions through the shared helper.
3. [Matched release selection and rollback](superpowers/plans/2026-10-06-matched-release-rollback.md): preserve a complete matching native/static/Python bundle and verify rollback against disposable data. Legacy releases without matching companion source cannot be safe automatic targets.

The [common scope and execution brief](superpowers/specs/2026-10-06-user-management-review-fixes.md)
maps all six confirmed findings plus profile completion, private-data safeguards and remaining physical
acceptance gates. Planning approval does not authorize deployment.

## Queued priorities

- **Integrated item QR label editor — next after the current assignment**, revised October 7: replaces the earlier mockup-only request. Provide several starter templates and a drag-and-drop editor with dynamic QR, item-name and shorthand/asset-code fields. Users place fields once; labels render the selected item's actual values. Design for both native Homebox and Equipment Terminal, using shared saved templates and the current printer/label dimensions. Include resize/alignment, preview with synthetic or selected-item data, and optional icon/text elements. Preserve stable item identities/current QR payloads, scan-safe QR size/quiet margins, readable text and existing explicit print/recovery safeguards. Avoid a separate user/inventory directory. Plan template scope/permissions, duplicate/save/reset behavior, long-name/empty-field handling, supported label stock and testable preview/print parity. Condition icons can become stale on physical labels; decide whether they are manual decoration or bound to supported item status before adding that behavior. The [design](superpowers/specs/2026-10-07-label-layout-maker-design.md) and [implementation plan](superpowers/plans/2026-10-07-label-layout-maker.md) are drafted and a fresh Sol High review confirmed the corrected plan has no blocking gaps. PrintDesignPro is selected, with SUPVAN and US Letter output profiles. The editor itself has not been implemented or published; the user explicitly requested its implementation be next after the current item action-switch assignment. Retain the reviewed design/plan handoff and separate deployment requirement. Initial scope is item labels; personal badge editing and general arbitrary QR generation are not inferred.

- **Item log / notes section**, requested October 7: a simple activity table with action, person, time and notes, filterable by note text, person, date/time range and check-in/check-out. Use a separate expandable section beside Details on each native item page as the stated default, subject to any later placement correction. Reuse existing borrowing history and return notes with stable item and member identities rather than a second log store. Trace native activity and companion history, preserve honest anonymous return attribution, and make any history limits or incomplete coverage explicit. A standalone Equipment Terminal note-entry button is now queued below; brainstorm that workflow together with this section before implementation. Implement after the label maker using the existing UI components and authorization boundaries.

- **Workshop floor-plan redesign**, queued October 7: start with the explicitly requested `$brainstorming` skill to flesh out the user workflow, existing location hierarchy, map interactions and success criteria; agree on the written design before implementation planning or product changes. Rework the confusing map UI and connect map rooms, racks and shelf areas to actual Homebox locations, including locations such as “the Cage,” “Rack 1” and “Rack 1-A.” Trace the existing location hierarchy and map workflow before designing; users must be able to choose an existing location, see its parent/children and equipment, and navigate between the map and that native location. Use stable native location UUIDs rather than disconnected names or a separate location directory; preserve existing locations, nesting, map assignments and inventory. Keep location rename/move and map selection consistent in native C-Crate and Equipment Terminal. Prepare a researched redesign and implementation plan after the preceding approved fixes and label-editor work; this queue entry authorizes planning later, not implementation or deployment now.

## New requests — brainstorm later

Queued October 7, 2026. These are requests to record for later discussion, not
implementation or deployment approval. Preserve the existing priority order
above; clarify and brainstorm these features before planning their implementation.

- **Default returner to the borrower:** when returning an item, assume the person
  returning it is the person who checked it out. Add a button to change the
  returner when someone else brings it back. Preserve the original borrower in
  checkout history.
- **Checkout scans in either order:** accept a person scan followed by an item
  scan, or an item scan followed by a person scan. A person must be assigned
  before completing checkout.
- **Readable quick codes and manual entry:** show a short code on item labels
  and person badges, and accept typed codes for checkout, returns and lookup
  when scanning fails. Examples supplied by the user: `ABC-123`, `D12-001`
  (Drone/model 12/item 1), and `AN-873` (Andreas Nissen with a random or
  customizable number). Brainstorm the exact format, assignment/customization,
  uniqueness and how these codes relate to existing identifiers later.
- **Equipment Terminal QR lookup:** add a QR lookup button to find an item by
  scanning its label.
- **Equipment Terminal Add Notes to Item:** add a button to record an item note
  without returning it. Coordinate this with the queued item log / notes section;
  this request supplies the previously unspecified standalone note workflow.

## Completed

- **C-Crate rename and Printer/Camera status indicators, published October 7.** Native Homebox and Equipment Terminal display C-Crate; the native header shows connection-only printer/camera status and opens a read-only details panel. The bounded publisher changed 49 reviewed source paths, added 3 reviewed files and selected both verified static trees. It did not replace the native binary. The full baseline desktop suite remains a 38-check partial result with the existing Recovery UI timeout; see [C_CRATE_RELEASE.md](C_CRATE_RELEASE.md).

- Admin-managed users: **Collection → Members → Manage users** and **Terminal → Admin → Manage users**. Create by name alone; edit name, optional email/details and shared local pictures; reset to a stable generated avatar. Native identities, badges, loans and history remain intact; duplicate names have distinct visible IDs, owner sign-in access is protected, and interrupted writes have verified Recovery. Published `native-20261006T220538Z`; 221 unit tests, 7 member API scenarios, 9 hierarchy scenarios, 42 isolated checks, 8 Terminal scenarios and 28 live read-only checks passed. Inventory remained exactly 2/4/2. Password/PIN enforcement is disabled, with the future plan in [USER_MANAGEMENT.md](USER_MANAGEMENT.md).


- Flexible nesting: optional item/location parents, Add inside in both interfaces, mixed typed paths, deep trees and cycle prevention; moving containers preserves contents. Published `native-20261006T210239Z`; 218 unit tests, 9 API scenarios, 36 isolated checks, 8 Terminal scenarios and 26 live read-only checks passed. Exact inventory/membership metadata preserved.

- CACI-Create branding: native navigation/sign-in, page titles, theme label, browser/PWA icons, Terminal, label footer, help and Pi shortcut share the new name and scalable drone/crate logo. Published; 210 unit tests, 31 isolated checks, 6 Terminal scenarios and 24 live checks passed.

- Stable generated member avatars in Homebox Members and Equipment Terminal, using a shared local SVG generator seeded by native user identity. Published; 30 isolated checks, 5 Terminal scenarios and 22 live checks passed, including cross-interface equality.

- Webcam and printer reconnection: explicit controls in both interfaces and scan/photo/print dialogs; specific recovery steps; drafts, photos, sessions and uncertain outputs preserved. Published and verified with 210 unit tests, 29 isolated native checks, 4 Terminal browser checks and 20 live checks.

- Official Ponytail skill installed in full mode, checksum verified, applied during this queue and activated persistently through project AGENTS.md. See docs/PONYTAIL_WORKFLOW.md.

- Native Collection → Members: User, Email, Kiosk Badge and expandable Items, with reprint/manage actions and saved photos, checkout dates and durations. Published and verified live; 207 unit tests, 28 isolated checks and 18 live read-only checks passed.

- Native checked-out section on Home: count, items, borrowers, loan links and refresh.
- User-requested native location hierarchy: Storage Room → the Cage. Verified in the edit form; existing inventory metadata preserved.

## October 8 execution checkpoint

Restart pause revoked; the central goal and watchdog are active. Stage 1 and
Rooms 1–3 are accepted, and the shortcut/visible-label cleanup is accepted.
Rooms 4 is active before Rooms 5, matched release prerequisites, Rooms 6, shelf
checks, integration/release and member/profile follow-ups. The user explicitly
authorized queue completion and deployment; earlier approval notes do not
require another confirmation for this approved scope. The new room features
remain isolated until their release and rollback checks pass.

### October 8 workshop design steering

The active Rooms work now includes the user-requested full workshop view/edit
rework: a dominant 2D canvas, clear Browse/Edit modes, drawing palette and
contextual storage/geometry inspector. Drag/resize/quarter-turn rotation, numeric
edits, zoom/pan/fit/snap and per-room undo retain native IDs and safe drafts.
The existing conflict, identity and uncertain-save checks remain required.
Behavioral tests and desktop/narrow-width screenshot review must prove this
outcome before release; adding only a room picker is insufficient. The detailed
accepted direction is in `work/queue-coordinator/rooms-task4-ui-direction-20261008.md`.
