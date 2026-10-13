# C-Crate updates and desktop design specification

Status: the Workshop repair wave (desktop Tasks 8-10) and label designer repair (Task 11) are implemented and verified locally on 2026-10-12. The full desktop redesign and prebuilt-update work remain planned.
Baseline: C-Crate commit 607a7144a6f7d4037ea01340fc5da75a7e6090b9.

## Intended outcome

C-Crate should feel like a coherent desktop workshop application, and normal updates should install prebuilt software without compiling on the Pi. The user reports Pi builds taking over 30 minutes, rejected the incremental visual polish, and prioritizes the desktop experience. Keep the existing inventory, people, hardware, label and recovery capabilities while changing their presentation.

The work is split into two independently deliverable plans:

- [Prebuilt updates](../plans/2026-10-12-ccrate-prebuilt-updates.md).
- [Desktop redesign](../plans/2026-10-12-ccrate-desktop-redesign.md).

This specification and those two plans are the canonical work queue. Do not add competing AI planning documents or miscellaneous verification scripts.

## Global constraints

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

## A. Prebuilt updates

### Build and distribution

Build once on GitHub, publish a versioned Linux ARM64 release archive, and let the Pi download and activate it. Git is the source-development interface; it is not the installed-runtime update interface. GitHub-hosted ARM64 support is documented in [the runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).

Toolchain sources: [Node.js 24.21.0 downloads](https://nodejs.org/download/release/v24.21.0/) and [official Go download metadata](https://go.dev/dl/?mode=json&include=all). Verify archive checksums from the official distributions; the native source's go.mod also requires Go 1.26.0.

Split frontend, label editor and backend build/cache inputs. The gateway already serves a selected external public tree; backend compilation must stop depending on the current frontend tree. Keep a small static gateway-directed placeholder in the private native server's embedded public directory. Existing builder behavior may remain available for legacy callers, but prebuilt releases use the independent mode.

Each component fingerprint binds its actual source files, modes, upstream/vendor pin, lockfiles and relevant toolchain versions. A frontend edit must not rebuild an unchanged backend or label editor. A backend edit must not reuse an incompatible cached binary. Hash and verify cached outputs before reuse; record their original build evidence rather than claiming a fresh compilation.

Release assets contain the sealed candidate application, public assets, labels and source/build/test receipts. They exclude toolchains, node_modules, dependency caches, private stores and runtime calibration. The Pi keeps its existing compatible Python, Node, Chromium, fonts, camera tools and calibrated SUPVAN adapter. Missing or incompatible prerequisites require a deliberate one-time repair; normal updates never compile or install dependencies.

Publish trusted-main/tag builds only. Pull requests run checks without publishing. Pin CI actions to full commit SHAs and use only the permissions required by the publishing job. Store artifacts on GitHub Releases, not as generated binaries in Git. Keep package commit, upstream pin and build timestamp in public/ccrate-release.json without forcing a UI recompile just to update the displayed version.

That public metadata identifies the UI build. Compatible fallback F preserves O's exact public bytes, including its UI metadata; display C-Crate UI with that captured commit rather than calling it C's new UI. The updater reports the actual selected manifest hash and candidate-compatible runtime identity separately. Do not rewrite old public metadata to imply the failed new UI is active.

### Download and preparation contract

Operator commands:

    python3 deploy/update-ccrate.py --root /path/to/existing/install --version ccrate-COMMIT12 --check
    python3 deploy/update-ccrate.py --root /path/to/existing/install --version ccrate-COMMIT12 --apply

The first command downloads/stages/checks only; it never stops services. The second explicitly authorizes a local activation. No scheduler, unattended deployment or new update UI is included.

The public release descriptor is format 1 with application=ccrate, architecture=linux-arm64, a 40-character source commit, the exact upstream pin, archive name, compressed byte count, expanded byte count, SHA-256 and candidate manifest SHA-256. Release tag is ccrate- plus the first 12 commit characters. Bind the descriptor and archive to the trusted Spraten/ccrate GitHub release/tag commit and asset digest over HTTPS before using packaged executable code. A checksum inside an untrusted archive alone is insufficient.

Use the [GitHub release asset API](https://docs.github.com/en/rest/releases/assets) for the trusted asset identity/digest/download metadata; local internal bundle validation is an additional check, not a substitute.

Use bounded standard-library downloading/extraction: maximum archive 512 MiB, expanded content 1 GiB, 20,000 members and descriptor 256 KiB. Reject absolute paths, traversal, links, devices, duplicate members and archive paths outside one candidate tree. Partial downloads live under root/work/update-downloads and never replace an existing valid release. Validate the sealed format-2 package with the installed trusted release validator before any packaged Python executes.

Preflight checks architecture, installed runtime, free space, current selector, bundle/provenance compatibility and existing stores. Space calculation includes actual download/expanded size, fallback staging, backup estimate and a 100 MiB reserve. The measured local app is approximately 115 MB; the local Docker image is approximately 430 MB. A 1 GB application/update allowance is a planning estimate, not a measured Pi requirement or a cap on user data/backups.

### Activation and recovery

Reuse release_bundle.stage_bundle, validate_bundle, select_bundle and recover_interrupted. Preserve three distinct sealed format-2 packages: previous O, candidate C and compatible fallback F. F retains C's native/Python/label code and O's captured public/Terminal assets. Failure before candidate exposure can return to O; failure after exposure must use F with the same stores. Never restore an old database automatically or replay a physical action.

Prepare F locally by assembling verified existing artifacts without compilation. Record actual assembly hashes, captured origin manifests and executed closure tests; never invent build/test success or relabel fixture-only evidence as production-matched. Execute production-matched O/C/F compatibility checks against privately restored copies of the actual cold snapshot, on loopback, with physical effects disabled. Keep private proof on the Pi, not in release uploads. Revalidate bundle/receipt bindings and the active store baseline immediately before selection; changed stores require a fresh snapshot/check rather than stale proof.

Repair the existing backup mismatch: producer emits format 2 while the publisher accepts only format 1. Support both known formats with full member/hash/privacy checks. Back up the selected sealed release and its selector identity in addition to every current database, photos, credentials and operation journal, and verify that an offline restore can start the captured selection.

The activation coordinator owns service stop/start ordering and the release lock. Backup called inside that transaction must not independently restart services. Check gateway, native/companion readiness and inventory/profile/loan preservation. Retain interrupted-transaction recovery and immutable bundle validation. Do not implement a second selector or rollback mechanism.

Normal-update scope requires an existing, valid sealed format-2 installation. Missing, legacy or unrecognized selectors return migration_required before any service or store changes, with documented operator instructions. Fresh installation and automatic legacy adoption are separate work; never silently create accounts or replace a database. First rollout cannot be claimed complete until the user runs the check command on the Pi and its actual installation is supported.

## B. Desktop redesign

### Visual decision and references

The user has not selected a generated concept. The original reference and three concepts travel with this spec:

- [Original Workshop reference](../../design/desktop/workshop-reference.jpg).
- [Displayed concept 1](../../design/desktop/workshop-studio.png).
- [Displayed concept 2](../../design/desktop/inventory-workbench.png).
- [Displayed concept 3](../../design/desktop/focused-canvas.png).

These are design concepts, not working screens, real inventory or production assets. Recommendation: use the reference-led workspace structure as the starting point. User review must settle the visual target or a revised combination before layout implementation. Do not treat this recommendation as approval. The initial desktop task produces the chosen target and concrete tokens, with source assets/libraries identified before making promises about illustrated furniture fidelity.

### Shared shell

Keep one compact left navigation with Home, Inventory, Workshop, Label, Users and collapsed More. Preserve all existing destinations under More, the collection selector, account/sign-out, scanner, global search and printer/camera details/reconnect actions. Use one brand, one global header and one workspace command bar. Device state stays visible but does not dominate the header. Remove the giant Create block, repeated branding and giant version/hash footer. Existing custom themes remain valid; light defaults do not override other themes.

Use 14-16px body/control text, comfortable 32-40px controls, clear keyboard focus, quiet dividers and deliberate density. Editors fill their available viewport instead of sitting in explanatory cards. Empty, loading, offline, permission-denied and uncertain states provide clear actions with truthful status. At 200% zoom controls may stack/scroll deliberately, but cannot become unreachable.

### Page jobs

| Page | Main desktop job | Required composition |
|---|---|---|
| Home | Resume workshop work | Checked-out items, recent records and useful existing-workflow shortcuts; remove purchase/value statistics as the dominant content |
| Inventory | Find and inspect records | Preserve full native search/filter/pagination; compact table/photo list, selected-item details and existing edit/location/label links |
| Workshop | Understand and edit physical storage | One command bar, object palette, full-height canvas, contextual inspector; preserve room bookmarks, history, geometry, native links and save reconciliation |
| Label | Design or produce reviewed labels | Explicit Design and Produce modes; one toolbar and one main preview, integrated existing canvas/layers/properties, clear persistence status |
| Users | Find people and manage profiles/badges | Dedicated /users page with list/details; reuse existing member, permission, profile, borrowing and badge authorities |

Move collection administration under More; Users must not land in a renamed collection-settings page. Existing bookmarks and old routes keep functioning or redirect safely.

### Implementation boundaries

Maintained Vue pages/components live under homebox-ui/overlay. Keep upstream source pinned; minimize checked builder patches. Use existing native UI primitives and useWorkshop/useCollections/auth helpers. Preserve the Inventory page's complete native query and pagination script rather than substituting a simplified picker search.

Extract map state/history/session/requests/recovery into one room controller and SVG/material/pointer behavior into one canvas module. Vue owns workspace composition. Leave imports, recovery and other secondary tools in the old host until their own changes are justified. Controller snapshots are read-only render state; components issue commands. Preserve live drag/resize preview and one history commit per gesture.

Extract the existing labels Workspace/actions into a shared type/composable. Retain PrintDesigner and the validated iframe boundary initially, while giving its surrounding chrome one C-Crate identity and control hierarchy. Never remove useful tools just to hide a crowded toolbar.

Fix the touched template-save ambiguity: route save through the existing write callback; retain one unresolved save key and exact intent; provide Check save result using labels/templates/result; block a new save while unresolved. Status must distinguish unsaved design changes from an actual native template save. Do not call a local/vendor state Autosaved when native persistence is unconfirmed.

Preserve the 36-item review limit, SUPVAN versus Letter profiles, matching reviewed dimensions, selected-item draft context, stale preview suppression, browser PDF/print and separate confirmation for physical printing. No physical output occurs during automated acceptance.

## Workshop priority repair wave

The user reports too few objects, clunky/buggy interactions, stretched object text and poor cabinet/bin/drawer artwork. This repair wave takes priority over the remaining desktop page work. The original [Workshop reference](../../design/desktop/workshop-reference.jpg) is the visual authority; the generated concepts are alternatives, not selected designs.

- Expand the searchable, grouped catalog with at least 20 useful shelf, cabinet, drawer, bin, work-surface, structural and machine presets. Preserve native drawing kinds and the existing persisted schema; drawings alone never create native inventory.
- Provide recognizable, distinct reusable artwork for cabinets, bins and drawer units in both the palette and map. Use existing rendering/platform facilities, with no new application dependency. Captions remain separate readable text, never baked into or stretched with artwork.
- Reproduce and correct caption distortion, drag/resize/selection/history faults. Text stays readable across narrow/wide objects and rotation; a completed gesture is one undo action, canceled gestures restore geometry, and existing save/recovery guards remain intact.
- Rework the desktop palette/canvas/inspector proportions and scroll behavior around the original reference. Make object search, placement instructions, selected properties and primary tools immediately usable at 1280x800 and 1440x900. Retain keyboard access and 200% zoom access.
- Verify actual interactions and screenshot the result in isolated fixtures and the local compiled application before publishing. This bounded repair wave does not mark the later Vue controller extraction or other page redesign tasks complete.

## Work queue and dependencies

**Next priority: update-blocking backup and release contracts, then prebuilt updates.** The bounded label designer repair is complete locally; Task 4's full workspace and durable pending-save work remain queued.

1. **Completed: Workshop repair wave (desktop plan Tasks 8-10), in parallel isolated branches:** 22 illustrated presets, readable independent captions, corrected gesture/history handling, and desktop layout. Application revision `ffd2931` passed 35 focused Python checks and compiled desktop acceptance in all four viewport/sidebar states; two catalog Node checks passed. No new dependencies or persisted schema changes. Native room data was unchanged during compiled testing. This completes the bounded repair wave, not the later Vue workspace redesign.

   Workshop follow-up application `dbc0e88` fixes the oversized keyboard-focus border using a 3 px dashed non-scaling stroke. Five focused Chromium checks and compiled keyboard/zoom acceptance at both desktop sizes passed; original drawing geometry stayed unchanged and no room writes occurred. Test revision `8711dd9` qualifies focus appearance against the native theme.

   Pointer-focus correction `e092689` (2026-10-13) also resets the browser's default outline during mouse-down. The earlier completed-click checks missed this state, which reproduced the user's black pill/white halo even with current assets. Four focused Chromium checks and six actual Codex-browser held-press cases passed, retaining keyboard focus and original drawing geometry. The local app and both open Workshop tabs were updated; no room save or Pi deployment occurred.

2. **Completed: bounded label designer repair (desktop Task 11):** visible SUPVAN dimensions, grouped starters/saved designs and a genuine blank, fitted selected additions, native item values and corrected preview behavior. Application `f18b8f8` passed nine Node and 30 Python checks, source/asset provenance validation, and actual native-item previews after adding Text at both desktop sizes. Drag/history and stale-result rejection passed compiled checks. No operational data, template-save or print requests occurred during acceptance. The full Design/Produce workspace and durable pending-save journal remain queued.
3. Repair update-blocking backup and release preparation contracts.
4. Build/cache/publish precompiled candidates and implement staging/preflight in parallel after agreeing their descriptor contract.
5. Prove compatible fallback preparation, activation and interrupted recovery in isolated tests.
6. User runs the Pi check; a supported installation and explicit apply authorization are prerequisites for real rollout.
7. Select the desktop visual direction; this can proceed while update infrastructure is built.
8. Rebuild the shared shell, then Workshop and Labels; these two pages may run on independent branches after shared contracts are stable.
9. Rework Inventory, Home and Users with native authorities and clear page jobs.
10. Whole-branch review, compiled desktop acceptance, Git push and a prebuilt release for user testing.

Parallel workers must not edit the same builder, shared type or README simultaneously. Assign one owner to shared contracts and integrate dependent tasks sequentially. Run focused tests after each task and a fresh whole-branch review before publication. Keep the existing exact upstream typecheck baseline; do not expand it to hide new diagnostics.

## Item shortcodes (2026-10-13)

The user needs a short manual lookup alternative when an item's UUID QR cannot be scanned, and a corresponding draggable label field. Use a permanent native `shortCode` such as `DHP-001`, linked to the existing UUID. The first three uppercase ASCII letters/digits come from the model number after removing punctuation, falling back to the item name; pad a shorter prefix with `X`, or use `ITM` when neither supplies characters. Prefixes are readable model hints, not separate model identities: models sharing a prefix share its sequence. Numbering starts at 001, expands beyond 999, is collection-scoped, and never reuses a deleted number.

Store assignments and counters in the native Homebox database with transactional allocation and a collection/code uniqueness constraint. Allocate on every native item creation path and idempotently backfill existing/archived items; preserve UUIDs, asset IDs, metadata and assignments through ordinary updates. Duplicates and newly imported items get new codes. Existing-item import updates retain codes. Read/preview requests never allocate. Database backups restore assignments and counters together. CSV identity policy must be explicit; never silently adopt a conflicting code supplied by an import.

Expose `shortCode` on native item summaries/details and in native search. Keep UUID QR contents unchanged. The existing manual-code flows accept trimmed, case-insensitive `XXX-123` and resolve under the active collection/account; unavailable/archived/foreign items do not resolve. A collision with an existing manufacturer/serial code fails closed instead of silently choosing another item. Label templates use `{{short_code}}`; selected-item canvas preview, rendered review and output read the real native value. Codes remain fixed after model/name/parent edits so printed labels stay valid. Add an obvious Short code insertion control and display/copy the code on the item, following the existing theme.

Implement and verify this bounded feature in the existing authorities before the broader redesign. No Pi deployment or physical printing is authorized by this feature request.

## Separate reliability follow-up queue

- Native metadata edits can be overwritten by companion read/modify/write operations.
- A deleted entity's stale loan can block unrelated returns.
- Cookie-authenticated photo recovery/upload can fail.
- History truncation and repeated detail requests need focused fixes if they obstruct the new views.
- Retarget the legacy query browser fixture that still expects Edit layout: it fails on the unchanged baseline. Preserve its scope/dirty-state assertions when moving to the room controller; do not delete useful authority tests to make the suite appear green.

These are recorded findings, not completed fixes. Backup/update blockers and template-save uncertainty are in the two active plans because those workflows touch them. Other fixes need their own small reproduction and repair tasks, not unrelated additions to the redesign.

## Acceptance and limitations

The update plan is accepted when a supported existing installation can stage and activate a prebuilt release without Go, pnpm, Rust or dependency installation, preserve stores, and recover correctly after injected failures. Measure actual Pi download/verification/activation time; do not promise a duration from local Docker timings.

The desktop plan is accepted when the chosen target is visibly matched, all five primary workflows are reachable and coherent at the specified desktop sizes, keyboard use works, and save/review/print statuses remain truthful. Screenshot comparison must use the same size/state as its approved visual target; passing structural text tests is insufficient.

The Workshop and bounded label repair waves are implemented and verified in the isolated local app. Workshop now supports left-dragging empty room/canvas space to pan in Browse and Edit, with exact pointer tracking across zoom levels and retained object selection, geometry, history and placement clicks. The canonical desktop plan records focused tests and actual Codex-browser evidence, including the native selected-text drag conflict and its correction. No Pi deployment, physical print or hardware calibration occurred. The prebuilt updater is not implemented yet: pulling Git source alone does not refresh an installed sealed frontend; the existing build/deployment process is still required until that updater is delivered.
