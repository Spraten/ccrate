# Project state

## October 12, 2026 — main integration prepared

Completed source has been reconciled onto local `main`: maps, rooms, Shelf Checks,
labels, item notes, Terminal member parity Tasks 1–3, and Profile Task 1 UTF-8
name validation. The checkout has no remote. Unfinished Profile Tasks 2–3 remain
in their existing isolated workspace.

The direct-layout native startup path is repaired. A disposable native
original → candidate → candidate-restart check preserved all 21 native tables;
eight member API checks and the compiled Desktop/Terminal map verifier passed.
The map verifier initially selected historical Terminal assets; its disposable
code root is now wired to the candidate. The scanner unit fixture was updated
to the accepted Rooms document schema. Neither failure required a product map
change.

The candidate UI is staged under `work/homebox-ui-releases/main-20261012/`.
Final review, source commit and the authorized cold-backup/service cutover are
in progress. The authoritative data remains `work/baseline/data/homebox.db`
and `work/ops/`; runtime copies are not authoritative. Evidence is local under
`work/main-integration-20261012/`. A fresh instance means restarted services,
with existing inventory and accounts preserved.

## Historical release records (superseded by the dated status above)

October 8 unattended queue update: item log/notes is deployed and verified, preserving the integrated label editor, Terminal return/action switching, C-Crate and Printer/Camera controls. Transaction `c45325ef-2319-433d-82d1-f0425cbd6165` reached `committed_C` with `verified: true`; authenticated live health matched 130 assets with zero browser errors or unexpected writes. A private local cold backup preceded publication. All three user services and the five-minute watchdog are active. Fresh read-only requests to the selected Desktop asset and Terminal index both return HTTP 200 and contain C-Crate, Printer and Camera markers. The browser address associated with the user's visibility report is unconfirmed.

Map Stage 1 is accepted at isolated commit `a14e7c5`: 310 unit tests, the production build, and compiled Desktop/Terminal verification passed. Rooms Task 1 is accepted at `0558d3f` with 23 focused tests. Rooms Task 2 is accepted at `c06dd27` after transaction, recovery, migration and mixed-ancestry corrections: 77 focused tests passed and Sol accepted the final diff. Task 3 cross-plan room selection is next in isolation. Rooms, shelf checks, matched release and member/profile follow-ups remain open; maps remain undeployed. The standing user instruction authorizes finishing and deploying the queue. Evidence: [ITEM_LOG_NOTES_RELEASE.md](ITEM_LOG_NOTES_RELEASE.md) and `work/queue-coordinator/audit.json`.

Authoritative project: /home/user/Desktop/inventory-system. The pinned Homebox
v0.26.2 upstream remains unmodified; the native backend remains `0.26.2-caci.2`.
Current release is the October 8 item log/notes selection. The
native selector is `homebox-ui-releases/item-notes-20261007/public`; the
Terminal selector is `homebox-ui-releases/item-notes-20261007/kiosk`. The
native binary is unchanged (SHA-256
`e8502bd85b18ff14d67172dffb0006e06504eddbe38a7c3d643bdee2088dd15a`). The gateway
listens on port 17745, Equipment Terminal on 17749, and native backend privately
on 127.0.0.1:17747. All three services are active.

The C-Crate name and native Printer/Camera status controls are deployed and
verified. The October 7 release-time inventory was 1 equipment / 6 locations / 3 members. The
authenticated live smoke passed with zero browser errors, blocked mutations,
prints or inventory changes. Baseline/candidate same-database compatibility and
rollback were verified. The baseline full desktop suite is a partial known
failure: 38 checks passed before the existing Recovery inspect-row timeout; it
must not be represented as a full-suite pass. Release details and receipts are
in [C_CRATE_RELEASE.md](C_CRATE_RELEASE.md). The unrelated implementation queue
remains open, with map corrections next. Optional passwords
and QR-plus-PIN enforcement remain disabled as documented in USER_MANAGEMENT.md.

The sections below record earlier phases and their original limitations. The
latest dated entries describe the current implementation; original physical
acceptance gates still require a person at the Pi.

## Original core verification

- Git clone and source are on the Pi desktop; fullscreen Equipment Terminal shortcut and touch Desktop exit are installed.
- Original printer and camera hardware tests accepted by user. On-demand camera QR decoding and browser start/cancel are integrated; physical integrated scanning acceptance remains unverified.
- Native inventory reads, Find Item, Browse Stock, touch search keyboard, asset details and native shelf display.
- Native Homebox accounts identify badge holders. Approved hashed random-token registry supports issuance and revocation. Open setup Admin is explicitly approved temporarily.
- Server-enforced two-minute badge inactivity timeout; touches/scans extend it, background polling does not. Expiry clears session and cart. Confirmation ends the session immediately.
- Eight approved states use native Equipment condition field and native archive flag. Unreviewed is blocked until Admin explicitly marks Ready. Only Ready is eligible. Native update metadata preservation and touch confirmation pass live integration.
- Individually tracked assets (quantity 1) can be checked out by badge, touch cart or scan and one confirmation. Native membership, condition and custody are revalidated. The ledger completes the cart atomically and idempotently. Native inventory is unchanged; borrower is resolved and displayed separately.
- 95 unit tests pass. Scanner/touch keyboard, conditions, checkout, return and map live Pi Chromium integration tests pass with no browser errors. Results are in corresponding docs/*-integration-results.json files.
- Routine return defaults to its current assigned parent; changed conditions/notes and scanned active destinations use journaled native writes. Any current badge holder can return. Admin can finish or safely cancel an interrupted operation; completed history is visible.
- Workshop room/object geometry is stored on native location fields. Touch steppers place/resize locations; Find Item highlights the exact native shelf. Removing a visual placement preserves the location. No real layout has been invented.
- Homebox cold backup/restore, attachment bytes and API-key continuity verified. Recovery helpers use correct relative storage prefix. Complete deployment recovery passed in isolation; external backup media remains pending approval.

## Original core phase

Core prototype implementation and engineering verification complete, subject to the outstanding physical and human acceptance gates. Fullscreen boot, kernel-isolated offline operation, actual webcam streaming, forced process crash recovery and final private archive restoration passed. Find Item supports serial, model, manufacturer, category, tags and description. System Status warns below 2 GiB or 10% free; below 512 MiB is critical. Simulated low-space, printer disconnect and missing-camera feedback passed without disturbing real hardware.

## Original core physical acceptance gates

Physical label readability and orientation, physical badge/asset/location scans, printer reconnection, abrupt power-loss recovery and uncoached user testing cannot be proved remotely while nobody is at the Pi. Real users, equipment and workshop geometry require actual setup information. Admin remains temporarily open by user choice. No real inventory has been invented. A private off-Pi backup copy awaits explicit approval after automatic review rejected transfer of credentials and private data. The public visual report is on the desktop and in docs/report.

Consumables/bulk stock, reservations and other section75 future features are excluded by the original handoff's explicit "Do Not Build Yet" rule.

## Original prototype limits

The current account and assets are synthetic. Checkout and return proof assets remain archived to preserve native references in operational history. No real equipment has been checked out by these tests. Trashed retains an asset record. The return UI is live for synthetic individual assets. It keeps custody through uncertain native outcomes until Admin recovery verifies the saved plan. Native condition updates perform read/modify/PUT; concurrent edits made directly in Homebox cannot be made atomic with companion updates by this API. Production concurrency policy and configuration require later review.

Native setup evidence: docs/enrollment-integration-results.json and docs/problem-integration-results.json. The schema-v2 migration has a verified consistent pre-migration operational backup. Native problem lost-response recovery produces one maintenance entry per report. Confirmation identifies both badge generation and server process instance.

Core evidence added: account, kit, photo, label and admin-stock integration results; deployment-restore-results.json. User services are active and lingering is enabled. The complete private backup restored native records, all operational tables, runtime hashes and a native attachment in isolation.

## October 5, 2026: photos and network access

Equipment enrollment and problem reports accept up to six JPEG photos. Each photo can be added, retaken or removed before confirmation. The Pi C920 photo preview explicitly enables continuous autofocus and offers autofocus/manual focus controls. Upload recovery tracks each photo separately, verifies native attachment bytes, and never automatically repeats an uncertain upload. Existing single-photo intents remain recoverable. Mock-camera browser coverage and 149 temporary-fixture unit tests pass; physical focus/readability still requires user verification. The older full navigation verification stops at its enrollment scenario, which attempts review without selecting the required location; no live writes were made.

Native Homebox listens globally on port 17745; the companion now listens on all IPv4 interfaces on port 17749. Companion browser mutations require an Origin matching the request Host on port 17749; cross-origin requests remain rejected. Network clients use editor mode automatically, create independent client sessions even on plain HTTP, and open native Homebox links using the current Pi hostname/address. Kiosk exit remains loopback-only. Both services were restarted and both network URLs returned HTTP 200. Direct HTTP LAN access does not provide a browser secure context for camera capture; use the Pi kiosk or the existing localhost SSH tunnel for webcam capture. Admin remains temporarily open as previously authorized.

## October 5, 2026: manufacturer equipment identification

Checkout and return share native equipment identification for Homebox asset numbers/URLs, entity UUIDs, exact serials, product GTIN fields and arbitrary registered manufacturer QR text. Manufacturer URLs with a single explicit sn/serial/serialNumber/serial_number query value can match the native serial exactly; scanned URLs are never fetched or navigated. Shared product codes, duplicate serials and duplicate registered codes never choose an item automatically. Archived equipment is excluded from manufacturer matching; normal custody, condition, badge, kit and final-confirmation validation remains authoritative.

To register an opaque manufacturer code, open an existing item and choose **Link manufacturer QR code**, scan its physical manufacturer label, verify the shown Homebox asset, then choose **Confirm code for this item**. Add Equipment also provides **Scan manufacturer QR code**. Codes are stored as a native text field named **Manufacturer QR code**, preserving existing metadata. Registration has a durable native job and Admin recovery; uncertain responses do not repeat writes. Existing nonempty manufacturer code fields are not overwritten. Register individual serials or Homebox labels when a product code is shared by multiple physical items.

Validation: 161 temporary-fixture unit tests and deploy/verify-manufacturer-scans.py browser checks for checkout, return, duplicate scans, ambiguity and arbitrary-code registration. All browser HTTP requests are intercepted; no live inventory or custody mutations are used for verification.

## October 6, 2026: shared Homebox and Equipment Terminal tools

Homebox's existing network address on port 17745 now uses a local gateway. The unchanged native binary runs privately on loopback port 17747 against its existing database; the gateway serves a rebuilt native Homebox frontend with workshop actions integrated into its navigation and pages. Equipment Terminal remains available on port 17749 and has a Homebox button in desktop mode. Native Homebox source remains unchanged.

The desktop workspace was selectively integrated from the saved October 5 staging build, preserving the newer camera/photos and manufacturer-code implementation. Desktop APIs use the current native HttpOnly session cookies, group membership and explicit Workshop manager access. Workshop Admin retains protected management access; managers can grant/revoke management access for current native members through Collection → Members. Issuance, revocation, printing, imports, loans, notes, geometry and recovery use the existing companion stores and Pi printer. Issued badge secrets stay ephemeral and uncertain operations do not automatically repeat. Backups include the desktop workspace and service installation includes the gateway.

Deployment uses deploy/install-shared-tools.py with previous service files saved privately for rollback. Inventory and membership are compared using private before/after hashes. All mutation checks use fixtures or a disposable native Homebox database; production verification reads existing records.

Validation completed: 196 unit checks, 22 fixture browser scenarios, 12 real isolated native integration checks, existing manufacturer-scan regression and 12 read-only live checks. The live browser reports no page errors. Native equipment, locations and group-member hashes are unchanged from the private pre-deployment snapshot. Both network URLs returned HTTP 200 at the current address 10.249.140.95. The printer was not detected during live verification, and no physical print was sent. A private pre-deployment backup completed with database integrity checked.


## October 6, 2026: native Homebox workflow and theme

The floating injected controls and iframe panels have been replaced by a frontend overlay built from the pinned Homebox source. The upstream checkout and native binary are unchanged. Collection → Members now contains personal badge and management-access actions using native Vue dialogs and table components. Item details show borrowing status, with a normal Loans & return notes tab for history, reviews and administrative returns. The existing label dialog adds an explicit Pi printer action and preview. Workshop tools use the native sidebar, selected collection and Homebox theme colours. Equipment Terminal is a regular sidebar link and retains its Homebox link in editor mode.

The frontend lives in homebox-ui/overlay, with reproducible patches in deploy/build-homebox-ui.py. The gateway serves a selected static release through work/homebox-ui-current, without HTML injection. Both UI implementations bind companion requests to the current native account and collection, and use durable pending request IDs for uncertain outcomes. Raw badge codes remain in memory until their dialog closes. The People response identifies protected Workshop Admin access for the native Members UI. Backups include the overlay and the selected compiled frontend.

The pinned upstream's 51 TypeScript diagnostics were reproduced in an unmodified copy with the same dependency versions. The overlay introduces no additional diagnostics. The baseline and commit are recorded in homebox-ui/upstream-typecheck.json; builds reject new diagnostics.

Validation: 197 fixture unit checks, 16 isolated native integration checks, and 16 live read-only browser checks passed. Native editing, member badges, item borrowing/returns, label previews, sidebar routes, theme colours and uncertain-print protection were verified. The final frontend typecheck adds no diagnostics to the reproduced upstream baseline. Live equipment/location/member fingerprints remain unchanged (2/1/2). Services are active at 10.249.140.95 on ports 17745 and 17749. The Pi printer was not detected; no physical print was sent. Private pre-publication backup deployment-20261006T150123Z.tar.gz completed with database integrity checked. The selected release is native-20261006T150342Z.

## October 6, 2026: checked-out items on Home

Home now includes a native Checked-out items section below its statistics. It shows current custody count, item names and asset numbers, borrowers, item links, and links to each item's borrowing history. The section follows the selected collection and refreshes on focus, every 30 seconds while visible, or explicitly. Unconfirmed checkout requests are excluded, returned items disappear, and failed reads show an error instead of a false zero. Inaccessible native records retain their custody count without broken item links.

Validation: 22 isolated native integration checks and 17 read-only live preview checks passed. The overlay adds no TypeScript diagnostics to the reproduced upstream baseline. The cache handoff fixture now seeds a stale private response and checks that cached responses are removed; an empty cache container can reappear during handoff. The selected frontend release is native-20261006T170851Z, published atomically without restarting services. The previous release remains available for rollback. Existing inventory fingerprints were preserved through publication (2 equipment, 2 locations, 2 members). Storage Room was added by the user during this work; the prior equipment, members and location metadata also matched the original snapshot.

At the user's request, **the Cage** was then created as a native child location of **Storage Room** through the authenticated durable location API. Storage Room remains top-level. Existing equipment, members and location metadata were preserved; its children list gained the requested location. The browser's creation parent dropdown includes Storage Room, while editing Storage Room excludes itself and its descendants to prevent cycles.

## October 6, 2026: native Members item previews and badge reprinting

Collection → Members now shows User, Email, Kiosk Badge and Items in the native table. Each person's checked-out count expands into saved item photos, actual completed checkout dates, elapsed time and native item/history links. The view follows the selected collection, refreshes while visible and on focus, and reports unavailable reads rather than a false zero. The checked-out dashboard remains available on Home.

Reprint badge and Manage badges are explicit native actions. Newly issued badges keep an encrypted QR credential in the private operational database, with a separate owner-only badge-print.key on this Pi. Public lists and request journals expose no QR credential. Older badges cannot reconstruct their QR from a hash: an explicit replacement revokes the older badge and ends its active kiosk sessions before printing separately. Unconfirmed initial prints block reprints in both the browser and backend. No physical print was performed during verification. This encrypted retention supersedes the earlier ephemeral-only issuance behavior; the QR shown in an issuance dialog is still cleared when it closes.

Validation: 207 fixture unit tests, 28 isolated native integration checks and 18 live read-only browser checks passed. The rebuild adds no diagnostics to the 51 known upstream TypeScript diagnostics. The stale-worker fixture seeds its private response during activation and waits for native PWA reloads, avoiding a race between fixture setup and worker replacement. Live equipment, locations and membership fingerprints were preserved (2/4/2). The printer probe reported ready; physical output remains untested. Private backup deployment-20261006T175057Z.tar.gz completed with database integrity checked. Selected frontend: native-20261006T175147Z; prior release retained for rollback. All three services are active.

## October 6, 2026: device reconnect controls

Homebox System and Equipment Terminal System status both offer Reconnect printer and Reconnect webcam. Native printer dialogs and Terminal label/badge dialogs include printer reconnection. Scan/photo previews reopen browser streams explicitly while retaining the scan purpose, enrollment draft, captured photos and identity. Permission failures explain browser permissions and secure laptop access. The backend rediscovers SUPVAN hidraw and opens a fresh probe, and checks the original C920 stable USB identity and controls. Missing, inaccessible, busy and timed-out devices return specific steps. No USB reset, application termination, session restart or automatic print occurs during reconnection; current focus settings remain unchanged. Desktop reconnect endpoints retain native cookie, manager, tenant, identity and origin checks.

Validation: 210 unit tests, 29 isolated native checks, four Terminal browser scenarios with a synthetic camera, and 20 live checks passed. Live reconnect controls probed the actual printer/webcam without sending a print or capturing private images. Inventory/member fingerprints remained identical (2/4/2). Typecheck adds no diagnostics. Backup deployment-20261006T183652Z.tar.gz checked database integrity; selected release native-20261006T183729Z.

Official Ponytail was installed at a pinned revision through the skill-installer, verified with deploy/verify-ponytail.py and applied in full mode. Project AGENTS.md enables it for future coding workflows; docs/PONYTAIL_WORKFLOW.md explains installation and use. It is an agent ruleset, not a background service.

## October 6, 2026: stable member avatars

Native Members displays generated identicons beside names. Equipment Terminal's member badge list uses the same generator, so each native account keeps the same SVG avatar across both interfaces and page reloads. No external avatar request, user setup or native account mutation is required. The frame follows native theme components.

Validation: 30 isolated native scenarios, five Terminal browser scenarios and 22 live checks passed, including distinct local avatars, stable reloads, and identical native/Terminal avatars for current members. The live walkthrough initially hit timing limits at sign-in and Terminal member loading; a focused Terminal read proved both avatars rendered, and the complete walkthrough then passed without product changes. Typecheck adds no diagnostics. Inventory/member fingerprints remained unchanged (2/4/2). Backup deployment-20261006T184939Z.tar.gz completed with database integrity checked; selected release native-20261006T185019Z.

## October 6, 2026: CACI-Create branding

The displayed application is now CACI-Create, using the user's requested spelling. A shared SVG silhouette shows a drone flying out of an open crate. Native navigation and sign-in retain the existing theme colours and components; page titles, locale text, theme display label, browser/PWA icons, Equipment Terminal header, printed label footer, help text, Pi shortcut and Connection Info use the name. API identifiers, QR payloads, theme keys, native accounts and inventory remain compatible. The sign-in logo is decorative beside its readable heading. The reproducible build replaces display-name words while retaining label-generator identifiers; upstream source and binary are unchanged. The old shortcut installer now uses the current connection guide instead of overwriting it with obsolete instructions.

Validation: 210 fixture unit tests, 31 isolated native checks, six Terminal browser scenarios and 24 live checks passed. The final typecheck adds no diagnostics to the 51 known upstream diagnostics. An initial rename changed an internal label-generator identifier and was corrected; isolated verification then exposed the repeated accessible sign-in heading, which was also corrected before publication. The final anonymous sign-in screenshot was visually inspected. Native inventory and member fingerprints were preserved (2/4/2); all three services are active. No physical print or live inventory mutation was performed. Private backup deployment-20261006T192027Z.tar.gz passed database integrity checks. Selected release: native-20261006T192821Z; prior release retained for rollback.

The project now records the user's standing request to identify missing workflow requirements before each task in AGENTS.md. Admin name-only user creation, profile picture management and a future optional QR-plus-PIN foundation are queued after flexible nesting.

### October 6: flexible nesting, published

Release `native-20261006T210239Z` selects the verified native hierarchy backend,
compiled Homebox frontend and immutable Terminal assets together. All 218 fixture
unit tests, 9 disposable API scenarios, 36 isolated integration checks, 8 Terminal
browser scenarios and 26 live read-only checks passed, without browser errors,
live fixture writes or physical prints. The frontend adds no TypeScript diagnostics
(43 pre-existing upstream diagnostics remain). Private database shadow, cutover
and final live checks preserve the exact 2 equipment, 4 locations and 2 members,
including full native metadata. Backup and selected release checksums match.
The original binary and previous branded frontend remain available for rollback;
no database restoration is automatic. See docs/FLEXIBLE_NESTING.md.
Both The Cage and the Cage under Storage Room were preserved. Name-only user
management is now the active authorized task.


## October 6: name-only user management, published

Release `native-20261006T220538Z` selects native backend `0.26.2-caci.2`, the rebuilt
native frontend and immutable Terminal assets. Collection → Members → Manage
users and Terminal → Admin → Manage users share the same native accounts. Name
is the only required creation field. New badge-only accounts have NULL passwords
and ordinary privileges; optional contact details, profile pictures and notes
remain native metadata. Primary-collection owner authorization, protected owner
sign-in details, stable IDs for duplicate names and safe interrupted-write
Recovery are enforced. Renames and uploaded pictures preserve badges, custody
and history. Preference saves cannot erase or inject reserved profile metadata.
Collection removal retains the native user identity. Both interfaces accept and
share normalized local pictures, or reset to the same generated avatar.

All 221 fixture unit tests, 7 disposable member API scenarios, 9 hierarchy API
scenarios, 42 isolated integration checks, 8 Terminal scenarios and 28 live
read-only checks passed. Recovery verifies saved profiles through the native UI
and accepts completed request replay without repeating a write. No browser errors,
added TypeScript diagnostics, live fixture mutations or physical prints occurred.
The exact 2/4/2 records and their complete metadata matched the private shadow,
cutover and final checks. The initial full-test run selected the old binary;
the harness now records the binary SHA and publication checks it. An obsolete
fixture PATCH rename was replaced with a preserving PUT. The live sign-in timing
check now waits for its actual response before navigation.

Private backup `deployment-20261006T220512Z.tar.gz` passed database integrity and
archive/record checksum checks. Selected frontend/Terminal assets and native
binary checksums match their manifest. Previous nesting release and backend are
retained for rollback; no database restoration is automatic. All three services
are active. Password and QR-plus-PIN foundations are documented in
USER_MANAGEMENT.md; enforcement is deliberately deferred as requested.

## October 7, 2026: C-Crate and device status, published

The bounded release selected the C-Crate native and Terminal overlays while
leaving the native binary unchanged. Authenticated live smoke and the
baseline→candidate→baseline same-database compatibility check passed. Inventory
remained 1 equipment / 6 locations / 3 members; all three services are active.
The baseline full desktop run remains partial (38 checks before the Recovery UI
timeout). See [C_CRATE_RELEASE.md](C_CRATE_RELEASE.md) and its linked receipts.

## October 8, 2026: restart recovery and current queue

The user resumed the authorized queue after restarting the Pi. All three user
services are active, and the queue watchdog is enabled. The live Desktop and
Terminal assets retain C-Crate and the Printer/Camera indicators. The Pi desktop
now has `C-Crate.desktop` and `C-Crate Connection Guide.desktop`; the reviewed
installer preserves unrelated launchers and rejects symlinks. Its eight focused
fixture tests pass. A further 42 visible labels in the isolated development
branch have been updated so a future build keeps the requested name.

Workshop map Stage 1 and Rooms Tasks 1–3 are accepted in the isolated branch.
Rooms Task 4 is active; room feature changes have not been deployed. The
remaining approved order is Rooms 4–5, matched release prerequisites, Rooms 6
rollback proof, shelf checks, map integration/release, then member/profile
follow-ups and the final matching release. The user has authorized completing
and deploying this queue. Native inventory and uncertain-operation recovery
remain protected. Current evidence and execution ownership are recorded in
`work/queue-coordinator/workshop-status.json` and the Rooms progress ledger.

The post-reboot queue watchdog was subsequently found enabled with no scheduled
next deadline. Starting its existing metadata-only service once re-established
the timer; the automatic 08:47:04 EDT run succeeded and scheduled the next run
for 08:52:04. No watchdog code, units or application services changed. Receipt:
`work/queue-coordinator/watchdog-post-reboot-rearm-receipt.json`.
