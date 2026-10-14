# C-Crate Open GitHub Issues — Resolution Plan

**Goal:** Resolve the 15 issues currently open in `Spraten/ccrate` with small, verified changes. Preserve the existing Homebox authority, C-Crate overlay pipeline, printer recovery safeguards, badge audit semantics, and user's existing local Workshop work.

**Status (2026-10-14):** The 15 feature slices are implemented locally on `codex/item-shortcodes-integration`. The production UI build succeeds, focused feedback/builder/navigation/item-log tests pass (34), checkout/return tests pass (68, one skipped), and focused scanner/label-editor bridge tests pass (16). Sol reviewed the feedback changes and the build/barcode integration as SHIP; the generated UI typecheck matches its 38-entry upstream baseline. Publishing is not complete: the branch points at local commits in the upstream Homebox submodule, which are not present in that remote. The user-owned C-Crate branch is left unchanged until the submodule can be made fetchable. GitHub issues remain open until the verified implementation is available on the remote branch.

**Execution:** One GPT-6 Luna Low coding worker at a time per `AGENTS.md`; GPT-6.1 Sol High reviews every slice; coordinator keeps the queue and checks integrations. Use the current checkout because the managed worktree attempt previously could not resolve refs. Keep unrelated dirty Workshop edits and `.serena/` untouched. Do not restart/deploy services, print physical output, mutate operational Homebox data, or close issues until changes are pushed and verified.

## Queue and acceptance

### 0. Build preflight and local barcode integration — #1, #8

- Update `deploy/build-homebox-ui.py` anchors for the current barcode-aware `CreateEntity` dialog type; preparation must remain fail-closed when upstream structure changes.
- Fix duplicate Nuxt component registration at its source without deleting intentional barrel exports or breaking shadcn imports.
- Keep the scoped oxc WASI fallback and distinguish its known experimental notice from build errors; real failures must keep a nonzero exit code.
- Verify in a disposable generated workspace. This preflight is required before validating other frontend issues.
- Revalidate the local barcode changes for #8 against the repaired build path. Before closing #8, cover barcode search, duplicate-item copy, and CSV export/import round trips; Sol review found these metadata gaps. #8 remains open until code reaches the remote branch.

### 1. Label output and printer recovery — #3, #5, #7

- #3: use one text-layout policy for designer preview, printed output, and legacy label rendering; cover multiword text, long identifiers, Unicode, explicit line breaks, small boxes, SUPVAN, and Letter output.
- #5/#7: expose persisted queue/recovery state immediately on page load; show useful status and a direct Recovery path; keep request keys and never auto-resend uncertain output. Keep “Print anyway” unavailable for uncertain outcomes.
- Remove the repeated separate review-window stop for routine printing. A good saved label design can be previewed in context and printed through the existing explicit print action; keep the physical print confirmation and never auto-repeat uncertain output.
- Verify retries, cancellation, timeouts/lost responses, page reload with pending operations, double click, recovery, and that uncertain work cannot duplicate physical printing.

### 2. Add Item capture and form usability — #6, #9, #11

- #6: extract/reuse the existing webcam capture flow in a Vue component, add it to item edit, and reuse the same preview/save path as uploaded photos.
- #9: add user-reviewed OCR from a captured image into the item name field. Choose the lightest supported approach after checking existing dependencies/runtime availability; do not upload images to an external service or silently overwrite user text.
- #11: move Create Item below photo controls without changing form validation/submission.
- Verify capture permission failures, retake/use/cancel, persistence on edit, long/multiline OCR candidates, and exact form submission behavior.

### 3. Desktop inventory navigation and theme — #10, #12

- #10: make parent/location selection hierarchical with clear expand/collapse and selected-path context; preserve current selection/save behavior.
- #12: add a clear light/dark/system choice, persist it, honor system preference only when no saved preference exists, and keep C-Crate layout structure and label-editor theme tokens consistent.
- Verify accessible controls, similar names, persistence, initial system preference, and live theme changes in the label editor.

### 4. Asset identity — #4

- Add a descriptive display ID while preserving the native UUID and existing numeric asset ID. Validate conflicts and show the descriptive ID in details, search, and labels.
- Generate the full ID from item type and its storage path (including the column), such as `BIN-D-GC-C-1`; update it when the item moves. Keep this separate from the native UUID and numeric asset ID, and ensure collision-safe regeneration.

### 5. Badge and scanner workflows — #14, #16

- #14: make the existing anonymous-return option clear in supported workflows; retain actor/audit requirements for checkout, enrollment, item notes, and issue reporting.
- #16: add focused keyboard/HID scanner capture with Enter framing, status, cancellation, and webcam/manual fallback. Do not claim browser-level pairing or connected state without device telemetry. Match native barcode fields in kiosk lookup and reject ambiguous matches.
- User identified NETUM 2D-C750-Yellow. Official C750 documentation supports Bluetooth HID keyboard mode and USB/2.4GHz options. Implement focused keyboard input; show pairing/help guidance without claiming live connection telemetry.

### 6. Feedback reporting and desk cart — #13, #15

- #13: add a simple report form and member-authenticated server route. Keep GitHub credentials server-only; retain drafts and idempotent request identity; actor-scope status; rate-limit; handle uncertain submissions without blindly creating a second issue. Actual delivery needs a configured repository credential.
- #15: persist one group/member-scoped draft cart; desk edits do not reserve items or change custody. On kiosk confirmation, revalidate items and kits and use the existing atomic checkout/ledger/Recovery flow. Preserve failed selections for correction and prevent cross-user/group access or duplicate checkout.

## Review and delivery gates

- Each slice: add focused tests first where practical, implement, run relevant local checks, Sol review, fix findings, and record exact commits/results here or in the SDD ledger.
- Run the isolated disposable frontend build before declaring browser/UI issues verified. Keep operational services and printers untouched.
- Issues with unavailable external prerequisites (#13 server credential) remain visibly blocked only at those dependent decisions; finish independent work meanwhile.
- Push the Homebox submodule commit before pushing the C-Crate pointer. The current local commits are on detached submodule history at `upstream/homebox`; `Spraten/homebox` does not exist, and the configured remote is `sysadminsmedia/homebox`. Do not publish those commits to the upstream maintainer's repository without explicit authorization. Create/use a user-owned Homebox fork, update `.gitmodules`, and verify both remote refs before pushing the C-Crate pointer.
- Do not close issues while their changes are only local. Close only issues whose accepted behavior is present on the remote branch and backed by checks.

## Open issues in scope

`#1, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16`.
