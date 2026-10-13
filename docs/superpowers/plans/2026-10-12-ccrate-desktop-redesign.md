# C-Crate Desktop Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the rejected page structure with one coherent desktop shell and usable Inventory, Workshop, Label, Home and Users workspaces.

**Architecture:** Maintain page-specific Vue composition in the existing overlay and reuse native authorities/components. Extract the existing map controller/canvas and label Workspace logic before changing their presentation, preserving their request, identity, history and recovery contracts. Keep the existing standalone label designer boundary while replacing duplicated host chrome.

**Tech Stack:** Existing Nuxt/Vue, native Reka/shadcn-style primitives, existing Tailwind/CSS, Pinia, PrintDesignPro and installed Playwright fixtures; no new application dependencies.

**Spec:** [C-Crate updates and desktop design specification](../specs/2026-10-12-ccrate-updates-and-desktop.md), sections Global constraints and B.

**Status (2026-10-12):** Immediate Workshop repair Tasks 8-10 and label designer repair Task 11 are complete and verified locally. Tasks 1-7 remain planned; these repairs do not complete the full desktop redesign. Workshop application revision `ffd2931` passed 35 focused Python checks, two catalog Node checks and compiled desktop/sidebar acceptance. Label application revision `f18b8f8` passed nine Node checks, 30 focused Python checks and actual native-item draft previews at 1280x800 and 1440x900. No added typecheck diagnostics; 43 pinned upstream diagnostics remain. Pi rollout, hardware and prebuilt updates remain separate.

## Global Constraints

- Homebox remains the inventory, account, collection and native-history authority.
- Preserve authentication, collection isolation, manager/owner checks, durable request identities and uncertain-result recovery.
- Keep databases, photos, credentials, peppers, badge keys and private backups outside public source and release assets.
- No new application dependencies; reuse installed components, PrintDesignPro, existing helpers and standard libraries.
- Maintain the pinned Homebox submodule e01dd737238a3fa7e1a6454b37de6c6fc88c86e4 and PrintDesignPro eb118cc05b169c554066d823c44dc179aa3b96bb; retain licenses.
- Build with Go 1.26.0, Node.js 24.21.0 and pnpm 10.28.0; retain both existing dependency lockfiles.
- Do not change the pinned upstream checkout or generated work/ files as maintained product source.
- Pi target is Linux ARM64 with GOOS=linux, GOARCH=arm64, CGO_ENABLED=0 and GOARM64=v8.0; refuse other hosts before activation.
- Existing deployment root and runtime prerequisites must be checked locally; no SSH access is available to the agent.
- Preserve ports 17745 (gateway), 17747 (private native API) and 17749 (Equipment Terminal), with current authentication and exposure rules.
- Never run operational deployment, service restart, data mutation, physical print or camera calibration without explicit operator authorization.
- Automated tests use disposable data, intercepted APIs or verifier-owned loopback services; never the operational Pi.
- Desktop acceptance sizes are 1280x800 and 1440x900 at 100% browser zoom, plus keyboard and 200% zoom checks.
- Mobile refinement and optional new features are deferred.
- Execution uses isolated branches/worktrees and parallel independent work, as requested; coding workers use GPT-6 Luna Low and the final reviewer uses GPT-6.1 Sol High.

## Review Focus

- Long names, custom themes and 200% zoom must not crop essential controls; Tasks 1/3/7 test actual compiled geometry and access.
- Collection/user changes during delayed reads must clear old details and ignore old results; Tasks 2/4/5/6 exercise scope changes.
- Unlinked drawings and pointer/input edge cases must preserve native storage and one history transaction; Tasks 2/3 preserve geometry and drawing-only behavior.
- An uncertain template save or mixed label profiles must not permit duplicate saves/invalid output; Task 4 retains the save intent and tests profile/review rules.
- Keyboard-only users, empty records and disconnected devices need named controls and actionable states; Tasks 1/5/6/7 test the connected desktop workflows.

---

## Visual Approval Prerequisite

Before Task 1, the user reviews the [three concepts and original reference](../specs/2026-10-12-ccrate-updates-and-desktop.md#visual-decision-and-references). Record the selected or revised target in the existing spec, including its actual sidebar/header/palette/inspector dimensions, color/type/control tokens and source assets. Do not mark a concept approved merely because this plan was requested. A combined direction needs a revised visual target before coding.

This is a design review, not an artificial unit-test task. The first coding task owns its compiled acceptance fixture. Keep geometry/save behavior functional throughout; a mock image is not a working application.

## File Structure and Work Ownership

| Files | Responsibility |
|---|---|
| deploy/build-homebox-ui.py, overlay/assets/css/ccrate.css | Checked shell patches, consistent native theme/layout and overlay preparation |
| overlay/composables/use-app-release.ts (new) | Read the installed public C-Crate release identity |
| overlay/lib/workshop-room-controller.js, workshop-room-canvas.js (new) | Map state/requests/history/recovery and SVG/pointer rendering respectively |
| overlay/components/Workshop/WorkshopWorkspace.vue, WorkshopPalette.vue, WorkshopInspector.vue (new) | Selected map workspace composition and commands |
| overlay/lib/label-workspace.ts, overlay/composables/use-label-workspace.ts (new) | Existing label Workspace type and scoped actions |
| LabelGenerator.vue, LabelDesigner.vue, label-ui/src/editor-host.ts, kiosk/label-editor.js | Label modes, selected context, one host toolbar and truthful persistence |
| label-ui/vendor/print-design-pro/src/components/shell/PrintDesigner.vue and patches/0002-host-toolbar-slot.patch | Small backward-compatible host toolbar slot; retain vendor canvas/document behavior |
| overlay/pages/items.vue and home/index.vue (new) | Native Inventory and Home composition with original data authorities |
| overlay/pages/users.vue (new) | Dedicated people workspace using existing member/profile/badge components |
| overlay/pages/workshop/[tool].vue | Route map/label workspaces; keep secondary host workflows and legacy bookmarks |
| tests/test_desktop_workspaces.py (new) | One compiled desktop fixture/acceptance suite, not scattered scripts |
| Existing navigation/map/label/transport tests | Focused regression and authority checks |

All overlay paths above are under homebox-ui/. Shared builder/route/type changes have one owner. Task 1 establishes the shell and compiled fixture; Tasks 2-3 own map files, Task 4 owns labels, and Tasks 5-6 own distinct pages. Map/labels can proceed in parallel after shared contracts stabilize.

Run all python3/build commands in Linux WSL or CI with the existing fixture dependencies. A UI-only task builds native/label static assets and runs their intercepted compiled fixture; it does not rebuild an unchanged Go backend. Required tests skipped for missing assets/dependencies do not count as acceptance. Shelf-check cases needing the remote fixture use python3 deploy/verify-shelf-checks.py --root . --base-url http://127.0.0.1:0 --interface desktop, which creates its own guarded ephemeral service.

### Task 1: Replace the oversized shell and establish compiled desktop acceptance

**Files:** Modify deploy/build-homebox-ui.py functions navigation_frontend/shell_frontend/brand_frontend and homebox-ui/overlay/assets/css/ccrate.css; create homebox-ui/overlay/composables/use-app-release.ts and tests/test_desktop_workspaces.py; modify tests/test_homebox_navigation_contract.py.

**Interfaces:**
- useAppRelease() -> { release: Ref<AppRelease|null>, refresh: () => Promise<void> }, where AppRelease has format:1, application:'ccrate', commit:string, upstream_pin:string and built_at:string.
- Read only /ccrate-release.json from the selected public tree and label it C-Crate UI; absent/invalid metadata displays version unavailable, not an invented C-Crate revision. Backend upstream version remains separately truthful. F recovery retains the previous UI commit while its runtime stays candidate-compatible; do not mislabel that old UI as the new candidate.
- CompiledDesktopTests serves compiled public/label assets and synthetic API responses using the existing verifier-owned/intercepted browser pattern. Inputs: CCRATE_BUILT_UI_ROOT and CCRATE_LABEL_ASSET_ROOT; it never accepts an operational endpoint.

- [ ] **Step 1: Add test_compact_shell_preserves_navigation_collection_and_devices, test_shell_supports_custom_theme_long_names_and_keyboard and test_displayed_revision_matches_selected_public_manifest.** Assert one visible brand, exact Home/Inventory/Workshop/Label/Users links and collapsed More; retain every previous secondary destination, native create actions, account controls, search/scanner and device details. At 1280x800/1440x900, measure shell against the approved dimensions. Test 200% zoom and expanded/collapsed navigation without logo/control overflow.
- [ ] **Step 2: Build the isolated UI and run python3 -m unittest tests.test_homebox_navigation_contract tests.test_desktop_workspaces -v.** Expect the new layout/version cases to fail against the rejected shell.
- [ ] **Step 3: Implement the approved shell via native primitives and checked patches.** Use one compact create affordance rather than deleting native creation; remove repeated branding and giant footer hashes. Keep Users pointed at its working existing route until Task 6 supplies /users. Scope default palette changes to the native default theme. Adapt the existing device verifier's synthetic native/API setup into the single new compiled fixture.
- [ ] **Step 4: Rebuild and run the focused tests; capture both desktop sizes and keyboard/device-detail interactions.** Expect no new typecheck diagnostics beyond the exact existing upstream baseline; screenshots must visibly match the chosen shell. Source-string tests alone do not satisfy this task.
- [ ] **Step 5: Commit.** Commit message: feat: rebuild the C-Crate desktop shell.

### Task 2: Extract the room controller and canvas without changing behavior

**Files:** Create homebox-ui/overlay/lib/workshop-room-controller.js and workshop-room-canvas.js; modify homebox-ui/overlay/lib/workshop-tools.js and tests/test_workshop_browser.py; retain tests/test_workshop_room_requests.py.

**Interfaces:**
- WorkshopSelection = { entityId:string|null, drawingId:string|null, roomId:string|null }.
- createWorkshopRoomController({ workshop, navigate, notify, initialSelection:WorkshopSelection, changed }) -> controller. Consume the existing useWorkshop API unchanged; changed(snapshot) is invoked after validated state changes.
- snapshot() returns read-only render state: layoutState, layoutDraft, activeRoomId, selectedDrawingId, browseMode, manager, dirty, uncertainSave, pendingPalette, nativeView, viewError, saveStatus and viewport {zoom, panX, panY, grid, snap, tool:'select'|'pan'}. Room/document contents and drawing patch fields retain the existing v1/v2 schema, including style/layer fields; no new persisted fields are introduced.
- Commands: updateSelection(selection) -> Promise<void>; selectRoom(roomId:string|null) -> void; selectDrawing(drawingId:string) -> void; setMode(mode:'browse'|'edit') -> void; setViewport(patch:Partial<Viewport>) -> void; createRoom() -> void; applyRoomPatch(roomId:string, patch:object) -> void; removeEmptyRoom(roomId:string) -> void; choosePreset(kind:string, name:string) -> void; addDrawingAt(point:{x:number,y:number}) -> void; applyDrawingPatch(drawingId:string, patch:object) -> void; removeDrawing(drawingId:string) -> void; beginGeometryGesture(drawingId:string) -> void; previewGeometry(patch:object) -> void; commitGeometryGesture() -> void; cancelGeometryGesture() -> void; undo()/redo() -> void; save()/checkSaveStatus()/reload() -> Promise<void>; canLeave() -> boolean; dispose() -> void. Viewport is the snapshot's viewport shape; object patches are the existing validated room/drawing fields, not unconstrained arbitrary server fields. Existing native-create/link dialogs retain their request/confirmation handlers during extraction and are connected to the new inspector, never replaced with unguarded direct writes.
- mountWorkshopRoomCanvas(element:HTMLElement, { snapshot, onSelect, onGeometryBegin, onGeometryPreview, onGeometryCommit, onGeometryCancel }) -> { render(snapshot):void, dispose():void }. The controller owns all mutations; the canvas owns SVG/material/pointer behavior.

- [ ] **Step 1: Retarget existing map browser fixtures to import the actual modules and add test_controller_discards_old_scope_response and test_gesture_commits_one_history_record.** Preserve the existing blank/palette, room bookmarks, rotation/resize, input-before-change, native/drawing selection and uncertain-save cases. Assert no native record is created by adding a drawing; an identity change clears old state and delayed results; gesture cancel restores geometry, while undo reverses exactly one completed gesture.
- [ ] **Step 2: Run python3 -m unittest tests.test_workshop_browser.WorkshopBrowserTests.test_controller_discards_old_scope_response tests.test_workshop_browser.WorkshopBrowserTests.test_gesture_commits_one_history_record tests.test_workshop_room_requests -v.** New extraction cases must fail before the modules exist; missing verifier-owned prerequisites must be reported, never counted as passing.
- [ ] **Step 3: Move the existing map seams together.** Session persistence at the existing planner-session functions, selection/bookmarks, history/geometry, SVG pointers and save reconciliation move without altering request/revision/schema behavior. The legacy map composition consumes the controller during this task; secondary tools stay in workshop-tools.js. Do not maintain two writable copies of room state.
- [ ] **Step 4: Run all affected map cases through their proper fixture launchers.** Expect unchanged behavior and no stale-scope/native-link/history regressions. Ordinary copied-JS fixtures must load new imports rather than stub out the controller or bridge.
- [ ] **Step 5: Commit.** Commit message: refactor: isolate Workshop room state and canvas behavior.

### Task 3: Build the approved Workshop workspace around the preserved controller

**Files:** Create homebox-ui/overlay/components/Workshop/WorkshopWorkspace.vue, homebox-ui/overlay/components/Workshop/WorkshopPalette.vue and homebox-ui/overlay/components/Workshop/WorkshopInspector.vue; modify homebox-ui/overlay/pages/workshop/[tool].vue and homebox-ui/overlay/assets/css/workshop.css; extend tests/test_desktop_workspaces.py and tests/test_workshop_browser.py.

**Interfaces:**
- WorkshopWorkspace consumes initialSelection:WorkshopSelection and the Task 2 controller; exposes canLeave():boolean, updateSelection(selection):Promise<void> and dispose():void.
- WorkshopPalette consumes snapshot and emits choosePreset(kind,name). WorkshopInspector consumes snapshot and emits controller commands; neither directly writes native data or mutates render snapshots.
- The /workshop/map route keeps existing id, drawing_id and room_id query meanings and native linked-location navigation. Dirty/uncertain leave guards remain connected to the router.

- [ ] **Step 1: Add test_workshop_has_one_toolbar_and_full_height_canvas, test_selection_drives_inspector_and_native_link and test_workshop_controls_survive_long_names_zoom_and_keyboard.** At approved desktop sizes, assert the entire room and essential controls are reachable, palette placement and inspector dimensions match the target, and only the selected object's properties appear. Test blank room, drawing-only object, mapped native shelf, stale bookmark, manager denial and offline/uncertain save.
- [ ] **Step 2: Run the new compiled desktop cases against the old map composition.** Expect composition assertions to fail while existing controller cases still pass.
- [ ] **Step 3: Implement the chosen composition.** Vue owns the command bar/palette/inspector; reuse the canvas renderer and native components. Remove the old map page DOM composition once routed to the new workspace, retaining unrelated secondary flows. Identify approved source/illustration assets from the spec; use existing material assets or approved generated/licensed artwork, not approximate replacement drawings presented as reference-faithful assets.
- [ ] **Step 4: Rebuild, run compiled desktop and retained map authority tests, then compare screenshots at the same target size/state.** Validate room selection, linking, keyboard edits, drag/resize, undo/redo and uncertain-save reconciliation. No operational database or physical effects are involved.
- [ ] **Step 5: Commit.** Commit message: feat: redesign the Workshop desktop workspace.

### Task 4: Integrate label Design/Produce modes and repair save uncertainty

**Files:**
- Create homebox-ui/overlay/lib/label-workspace.ts and homebox-ui/overlay/composables/use-label-workspace.ts.
- Modify homebox-ui/overlay/components/Workshop/LabelGenerator.vue, homebox-ui/overlay/components/Workshop/LabelDesigner.vue, homebox-ui/overlay/pages/workshop/[tool].vue, homebox-ui/overlay/lib/workshop-tools.js, homebox-ui/overlay/composables/use-workshop.ts, kiosk/label-editor.js and label-ui/src/editor-host.ts.
- Add label-ui/patches/0002-host-toolbar-slot.patch and its small maintained change to label-ui/vendor/print-design-pro/src/components/shell/PrintDesigner.vue; retain existing vendor/source/patch manifest validation.
- Update tests/test_label_generator_contract.py, tests/label_editor_bridge.test.mjs, tests/test_use_workshop_transport.mjs and tests/test_desktop_workspaces.py.

**Interfaces:**
- Export the existing LabelGenerator Workspace, Item, Template and Review types unchanged to lib/label-workspace.ts; retain selectedIds/templateId/marginMm/gapMm/reviews/printedReviewIds/pages/pendingActions/busy and existing action names.
- useLabelWorkspace(initialIds:string[] = []) -> { workspace:ShallowRef<Workspace|null>, status:Ref<string>, refresh():Promise<void>, canLeave():boolean, dispose():void }. IDs must resolve in the active collection; unavailable IDs are not silently substituted with another item.
- Preserve LabelDesigner selectedItem {id,name,assetId?}, ready/dirty/busy/closed events, and the plain-cloned origin/source/nonce/epoch bridge.
- Add a backward-compatible PrintDesigner toolbar slot exposing fit():void. The host provides one grouped command bar using existing ToolStrip/history/viewport controls; default vendor consumers retain their old toolbar. Record the patch in captured build inputs/vendor hash and retain licenses.
- For template saves, invoke the supplied write callback, retain exact unresolved intent/key in the existing collection/user-scoped pending journal, rehydrate it after editor reload and expose Check save result via labels/templates/result. Clear only on confirmed result or a proven-not-started result; unknown/404 is not permission to generate another key.

- [ ] **Step 1: Add test_design_and_produce_share_one_truthful_toolbar, test_uncertain_template_save_keeps_one_key_across_reload, test_template_profiles_and_36_item_limit and test_label_scope_change_discards_old_preview.** Use real structuredClone in bridge mocks. In compiled browser fixtures, fail Save and result lookup, reopen the editor and assert a second write is blocked until the same key resolves. Verify late edits, profile switches, correct native selected-item draft context, mixed-size refusal, PDF output and a print-confirmation dialog that sends nothing when canceled.
- [ ] **Step 2: Run node --test tests/label_editor_bridge.test.mjs tests/test_use_workshop_transport.mjs and the new compiled label cases.** Expect missing modes/pending intent/toolbar hooks to fail.
- [ ] **Step 3: Extract existing label actions and implement the interfaces.** Replace DOM captureUi checks with captured scope/revision checks, not a second auth transport. Preserve existing starters, SUPVAN 40x28 mm, Letter labels 60x40 mm, 36-item limit and reviewed Letter-sheet authority. Filter saved choices by active profile. Remove conflicting vendor persistence copy and duplicated brand/host controls; use explicit Unsaved changes, Saving, Saved or Save unconfirmed status. Retain every useful editing tool and template recovery action.
- [ ] **Step 4: Rebuild label/native UI and run focused label transport/generator cases plus tests.test_label_layouts, tests.test_label_paper_authority and tests.test_label_print_reviews.** Capture full desktop editor/produce flows; verify draft preview is separate from reviewed/printable output and no physical print call occurs. Hash/validate the modified vendor source and maintained patch with existing build manifest checks.
- [ ] **Step 5: Commit.** Commit message: feat: unify label design and production with durable save recovery.

### Task 5: Recompose Inventory and Home around existing native data

**Files:** Create homebox-ui/overlay/pages/items.vue and homebox-ui/overlay/pages/home/index.vue adapted from the pinned native pages; create homebox-ui/overlay/components/Workshop/InventoryDetails.vue; modify only corresponding old injection anchors in deploy/build-homebox-ui.py and homebox-ui/overlay/assets/css/ccrate.css; extend tests/test_desktop_workspaces.py.

**Interfaces:**
- Preserve the native Inventory query/filter/pagination/selection script and api.items.getAll; do not replace it with useItemSearch's picker-level search.
- InventoryDetails consumes itemId:string|null, displays native api.items.get(itemId) data and existing edit/location/label links, and clears state on collection/user/selection changes. Label links use /workshop/labels?id=ITEM_ID and Task 4 validates scope.
- Home reuses its native recent-item/table APIs and CheckedOutItems.vue; no new statistics/API endpoints. Remove superseded builder Home injection patches once the overlay owns the composition.

- [ ] **Step 1: Add test_inventory_filters_paging_selection_and_details_work, test_inventory_delayed_detail_cannot_cross_scope and test_home_resumes_work_without_dominant_purchase_statistics.** Test empty collection, long item names, missing photos, stale selected ID, slow detail responses, table/photo view switching and existing native create/edit links. Assert label/location links refer to the selected native item and no stale item survives a group change.
- [ ] **Step 2: Run those compiled desktop cases against the baseline pages.** Expect new composition/details assertions to fail; retained native search/filter behavior must remain covered.
- [ ] **Step 3: Implement the chosen list/details composition and Home page job.** Reuse native selectable/table/card and item APIs, CheckedOutItems, and existing metadata/loan authority. Preserve all filter semantics and bookmark query parameters. Keep full item-edit authority on the native route instead of inventing an unguarded details-panel mutation path.
- [ ] **Step 4: Rebuild and run the cases, then capture native Inventory/Home with realistic synthetic records.** Expect usable density, accessible loading/empty/error states and no lost native features or full-detail request storm from the new panel.
- [ ] **Step 5: Commit.** Commit message: feat: redesign desktop Inventory and Home workflows.

### Task 6: Give Users its own people workspace

**Files:** Create homebox-ui/overlay/pages/users.vue; modify deploy/build-homebox-ui.py navigation mapping; reuse UserManager.vue, MemberAvatar.vue, BadgeActions.vue, MemberItems.vue and CheckedOutItems.vue; extend tests/test_homebox_navigation_contract.py and tests/test_desktop_workspaces.py.

**Interfaces:**
- /users consumes native api.group.getMembers plus existing workshop people/badges/loans/administration/profile requests through useWorkshop.
- Preserve UserManager members:UserSummary[], changed event and exposed show(user?:UserSummary); BadgeActions member/badges/canManage/protectedOwner props and changed event; MemberItems memberId/loans/loading/error props.
- Users nav now targets /users. Existing collection-settings and members bookmarks continue to work under More; no unsafe identity remapping or duplicate profiles.

- [ ] **Step 1: Add test_users_opens_people_not_collection_settings, test_users_scoped_delayed_requests_and_owner_protection and test_users_keyboard_empty_and_badge_dialogs.** Assert selection shows the correct person's profile/borrowing, owner and self-removal restrictions remain enforced, badge-only accounts remain password-free and name-only profiles are not forced through a web sign-in flow. Intercept writes; canceled badge/permission dialogs must send none.
- [ ] **Step 2: Run new compiled Users cases and navigation contracts.** Expect missing /users and new composition to fail.
- [ ] **Step 3: Implement list/details and refresh orchestration using the existing components/authorities.** Clear private rows and selected person on account/collection changes; guard delayed results by captured revision/identity. Put collection administration under More and retain existing protected-owner behavior.
- [ ] **Step 4: Rebuild and run python3 -m unittest tests.test_desktop_workspaces tests.test_homebox_navigation_contract tests.test_terminal_members -v.** Capture list/details and keyboard/dialog flow; verify the manager/member views expose only authorized actions. This does not substitute fixture success for a real native-service acceptance check.
- [ ] **Step 5: Commit.** Commit message: feat: add the dedicated desktop Users workspace.

### Task 7: Verify the whole desktop experience and publish a testable release

**Files:** Extend tests/test_desktop_workspaces.py; update README.md and homebox-ui/README.md to match final navigation/workflows; touch other files only for failures found in this acceptance task.

**Interfaces:**
- Consume all prior page interfaces and the prebuilt-update plan's package/version contract. Browser checks run compiled native and label assets, synthetic accounts/records and isolated loopback/API fixtures.
- Task completion evidence includes actual screenshots, focused test output, exact source revision, installed release metadata and a fresh whole-branch review.

- [ ] **Step 1: Add test_desktop_primary_journeys_remain_connected and test_desktop_keyboard_zoom_and_offline_states.** Navigate all five primary pages and More, select a native Inventory item, open its Workshop location, design/review a label, inspect its borrower's profile and return to Home. Verify dirty/uncertain navigation guards, no stale cross-scope information and no physical output. Repeat layout checks at 1280x800, 1440x900 and 200% zoom with long names and empty collections.
- [ ] **Step 2: Run those compiled cases before completing missing cross-page wiring.** Every interaction must have an observed result; synthetic screenshot-only controls are not acceptance.
- [ ] **Step 3: Fix only demonstrated integration/layout regressions and update final docs.** Use the same viewport/state to compare implementation against the approved source image. Resolve remaining duplicated controls, unreachable properties and misleading save statuses; do not broaden into mobile or optional features.
- [ ] **Step 4: Run focused suites and compiled builds with no added upstream typecheck diagnostics; obtain a fresh GPT-6.1 Sol High whole-branch review.** Stop when required checks pass. Publish the prebuilt candidate only through its verified pipeline, then let the user test on the Pi through the supported updater path. Hardware/physical printing remain separate explicitly authorized acceptance.
- [ ] **Step 5: Commit and push the reviewed result to Git.** Commit message: test: verify the redesigned desktop workflows. Attach every PR created; do not claim the Pi has updated merely because source or a release was pushed.

## Execution Handoff

The user already requested parallel tasks/sessions and separate branches. Preserve that method: one shared-contract owner; independent map, label and page branches after the shell/fixture gate; review each deliverable and perform a fresh whole-branch review at the end. Coding workers use GPT-6 Luna Low; final review uses GPT-6.1 Sol High.

Execution ruling (2026-10-12): the user explicitly authorized subagents to start the Workshop repair wave. Use the original uploaded Workshop reference for this wave; no generated alternative is claimed as selected. Tasks 8-10 are prioritized without marking Tasks 1-7 complete. Prebuilt-update implementation can proceed independently once its plan is approved. Mobile and the separate reliability backlog are not silently included; update-blocking backup and touched template-save defects are explicitly covered by their owning plans.


## Immediate Workshop repair wave

### Task 8: Expand the object catalog and supply recognizable artwork

**Files:** Create `homebox-ui/overlay/lib/workshop-object-catalog.js`, reusable assets under `homebox-ui/overlay/public/workshop/objects/`, and `tests/workshop_object_catalog.test.mjs`. Own these files only; Task 9 owns catalog wiring in workshop-tools.js.

**Interface:** Export `workshopObjectPresets` as records `{id,kind,name,category,width,depth,asset}`. Dimensions use feet. Export `workshopPresetForDrawing(drawing)` to return the matching preset or null using the existing kind/name data, without adding persisted fields. Catalog kinds must be accepted by the existing room schema. `asset` is a same-origin absolute `/workshop/objects/...` URL. Existing/custom names must have a safe visual fallback; do not interpret user names as URLs/markup. Renaming must not corrupt geometry/native links. Category order: Shelves, Cabinets, Drawers, Bins, Work surfaces, Structure, Machines.

- [x] Add at least 20 practical presets with distinct sizes: shelving/racks, wall/floor cabinets, drawer units/small-parts drawers, open/stacking bins/crates, tables/workbenches, wall/post and printer/CNC machines. Read the existing schema and reuse its types; unsupported furniture maps to Misc.
- [x] Provide distinct recognizable cabinet, bin and drawer artwork plus artwork for every preset category. Reuse the app's SVG/platform renderer and visual materials; no dependency. Asset files contain no caption text, executable content, external references or embedded private data. Preserve viewBox aspect ratio and verify every catalog asset exists.
- [x] Test unique IDs, schema-compatible kinds, positive dimensions, same-origin assets, known-name matching and custom-name fallback; run the Node test and record results.
- [x] Commit and write the task report with scope, commits, tests, limitations and asset provenance. Do not modify Task 9 or Task 10 files.

### Task 9: Repair Workshop text and editor interactions; wire the catalog

**Files:** Modify `homebox-ui/overlay/lib/workshop-tools.js` and `tests/test_workshop_browser.py` only. Consume Task 8's catalog module/assets. Task 10 owns CSS and its layout tests.

**Interface:** Use Task 8's catalog records and resolver without adding persisted room/drawing fields. Palette selection uses a preset's native kind/name/dimensions; retained custom and historical drawing names render via fallback. Load the actual catalog in fixtures (never stub the behavior). Expose classes/data hooks needed by Task 10 without editing CSS. Preserve existing route bookmarks, manager restrictions, native-link dialogs, save request identities and uncertain result reconciliation.

- [x] Reproduce caption distortion and at least one demonstrable editor interaction fault before changing behavior; add focused browser regression cases. Exercise narrow and wide drawings, rotation, resize preview, selection, undo/redo, pointer cancellation and switching rooms.
- [x] Keep captions outside nonuniform artwork transforms. Use actual SVG geometry/viewport math to make readable text independent of drawing aspect ratio, with truncation/full accessible name. Render catalog artwork with preserved aspect ratio and safe fallback. Do not flatten/remove useful geometry/material behavior.
- [x] Group and search the full catalog; selecting a preset sets pending placement, pointer placement creates exactly one drawing with its preset dimensions and no native data mutation. Retain old machine native-kind behavior and meaningful placement/cancel feedback.
- [x] Correct reproduced drag/resize/history/cancel issues in the existing shared handlers. A completed gesture is one history transaction; cancellation leaves no geometry/history change. Do not introduce a speculative controller rewrite during this bounded wave.
- [x] Run affected standalone map cases plus room request tests in proper isolated fixtures, commit and report evidence/limitations. Coordinate catalog interface questions with the controller before assumptions.

### Task 10: Rework Workshop desktop proportions and control access

**Files:** Modify `homebox-ui/overlay/assets/css/workshop.css` and create `tests/test_workshop_layout.py` only. Task 9 owns DOM/handlers; request hooks through the controller if needed.

**Interface:** Style the existing `.room-planner`, `.planner-toolbar`, palette/canvas/inspector and category/card classes. Preserve native theme variables, other Workshop pages and navigation. Use the original reference structure; no new dependency or fake nonfunctional controls.

- [x] Read the current renderer and reproduce the clutter/space/scroll problems in an isolated actual-JS browser fixture. Capture the before screenshot and add meaningful desktop geometry/access checks at 1280x800 and 1440x900.
- [x] Give the canvas the dominant area, a compact grouped command bar, a usable two-column illustrated/searchable catalog and an independently scrollable properties panel. Show the illustrated presets immediately after search, ahead of legacy drawing-type rows. Model the actual native sidebar, 32px content padding and 36px footer when checking the outer desktop viewport; a full-width standalone fixture is insufficient. Assert that preset artwork is painted in the initial palette viewport and that the page fits vertically at both desktop sizes, with all controls reachable. Avoid nested page scrolling and giant empty panels. Essential controls remain reachable at 200% zoom; long names do not force horizontal overflow.
- [x] Coordinate with Task 9 on any required class/DOM hooks; do not edit its files. Test existing/default and custom theme contrast and keyboard focus access.
- [x] Run the layout checks, capture after screenshots, commit and report. Report fixture verification separately from compiled native-application verification, which the controller performs after integration.

**Completion evidence:** Compiled application `ffd2931` has no horizontal or vertical overflow in all four desktop/sidebar states; its footer ends at the viewport edge. All 22 catalog assets load and illustrated cards are visible immediately after search. Actual cabinet/CNC placement and undo, horizontal caption geometry, rotation/resize and undo, sticky search, inspector scrolling and Escape cancellation passed. Local room data was unchanged after discarding edits; no JavaScript errors or server writes occurred, and three preference requests were locally stubbed. The isolated layout fixture also covers custom-theme contrast, keyboard order and a 200% zoom approximation. Source and compiled evidence received GPT-6.1 Sol High review. The legacy query fixture failure on the unchanged baseline remains in the separate reliability queue; the whole legacy browser suite is not claimed green.

**Workshop keyboard-focus border follow-up (2026-10-12):** Application `dbc0e88` replaces scaled keyboard-focus outlines with a 3 px dashed non-scaling stroke on the actual drawing or resize handle. The legacy map path is covered too. Five focused Chromium checks passed, including screenshot-pixel bounds, selected-versus-focused appearance, rotation and caption contrast; test revision `8711dd9` explicitly uses the native theme color. Compiled keyboard focus on Shelf A1 and Workbench passed at 1280x800 and 1440x900 through 83%, 100% and 120% zoom and Fit room. The two original drawings and their geometry stayed unchanged; no room writes, page errors or page overflow occurred. This CSS repair does not change the map controller, save/history or native data.

**Workshop pointer-focus correction (2026-10-13):** The previous keyboard/complete-click checks missed the native mouse-down state before SVG repaint. Holding the pointer in the actual Codex browser reproduced the user's exact black pill and white halo on the current build: the focused SVG group was not `:focus-visible`, so its browser-default `outline: auto 5px` still scaled in room units. A stale tab also existed, but refreshing it did not fix this pointer case. Application `e092689` changes the outline reset to `:focus`, retaining the bounded keyboard cue. Four focused Chromium checks passed; the new held-pointer test fails against the previous CSS and passes the fix. Six native held-press cases in the same Codex browser passed on Shelf A1 and Workbench in Browse at 100% and Edit at 120%/83%; the exact before/after held state was captured. Drawing IDs/geometry stayed unchanged, keyboard focus retained its 3 px dashed non-scaling stroke, and no room save was submitted. Both open Workshop tabs were refreshed after checking their saved status. The isolated build passed with no added typecheck diagnostics; the 43 pinned upstream diagnostics remain.

### Task 11: Repair the existing label designer workflow

**User reports:** Controls are confusing or ineffective; SUPVAN paper size is hard to find; users need a draggable starter; newly created items are missing from the editor.

**Reproduced baseline:** SUPVAN is already 40 x 28 mm but generic Add Text creates a 60 x 12 mm element at x=-10. Other insertion defaults also exceed the label. Selecting a native item updates the host status while the canvas still shows sample values. The vendor home button has no handler; native persistence is not represented by its Autosaved copy. The desktop iframe also exceeds the 1280 x 800 viewport. Existing starter dragging and undo/redo work and must be retained.

Compiled testing also reproduced a Preview race: an identical delayed editor-model echo invalidated an immediate post-edit preview. The repair distinguishes that echo from a real edit, retains stale-result rejection, and uses a centered native dialog for draft images with Close, Escape and focus return.

**Scope:** Existing label host, iframe bridge, selected-item integration, affected vendor insertion/preview/chrome components and maintained patches/tests. Reuse PrintDesignPro; no new dependencies or schema changes. Keep SUPVAN calibration, profile validation, native item identities, reusable template bindings, nonce/origin/epoch checks, dirty leave guards, request identities and reviewed physical-print authority.

- [x] Add failing checks for element insertion bounds/visible glyphs, explicit paper size, real blank versus starter choices, native item canvas preview and retained history.
- [x] Fit inserted elements to the active paper, retain image/QR proportions, use native field bindings and avoid silently creating a second item QR. Make starter and saved choices unambiguous and profile-aware.
- [x] Render selected-item values through transient preview state, preserving reusable bindings and clearing old context safely. Keep starter elements selectable/draggable and retain undo/redo.
- [x] Remove demonstrated no-op/misleading/duplicate controls, retain insertion/fit/zoom/layers/properties, and fit the actual desktop host without shrinking controls beyond readability. Display actual document dimensions.
- [x] Capture maintained vendor patches/provenance; run focused label/bridge/authority checks and compiled desktop journeys with synthetic data and intercepted writes. Review with GPT-6.1 Sol High. No operational Pi or physical printing.

**Completion evidence:** Application `f18b8f8` passed nine Node checks and 30 focused label/paper/print-authority Python checks. The final build passed with no added typecheck diagnostics, and strict editor validation matched its source inputs, both maintained patches, exact runtime assets and vendor-tree digest. Compiled native-item previews returned HTTP 200 with readable 320 x 224 images after adding Text at both desktop sizes; page height matched the viewport, canvas/footer remained reachable, and Close/Escape restored focus. The actual renderer's shared line-height now prevents the newly inserted text from fitting zero printable lines. Prior compiled checks verified profiles, genuine blank designs, native name/code values, starter dragging/history, and palette additions. A delayed mocked response survived an identical echo; a real inspector X edit discarded the pending stale result. No template-save, reviewed-print or physical-print requests occurred. Source and compiled evidence passed GPT-6.1 Sol High review. Git delivery must push main and the task branches and verify their remote hashes; publication is reported separately from local acceptance.

Task 11 does not mark Task 4's broader Design/Produce composition or durable pending-save journal complete. Report that boundary explicitly; do not silently retry an uncertain save during acceptance.
