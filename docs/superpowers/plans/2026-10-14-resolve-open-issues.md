# C-Crate Open GitHub Issues — Resolution Plan

**Goal:** Resolve the 15 issues currently open in `Spraten/ccrate` with small, verified changes. Preserve the existing Homebox authority, C-Crate overlay pipeline, printer recovery safeguards, badge audit semantics, and user's existing local Workshop work.

**Status (2026-10-14):** All 15 issue slices have implementation and focused regression coverage in this checkout. Homebox is pinned to public base `e01dd737`; the 23 private submodule commits are represented by ordered patches in `deploy/homebox-patches/`, and release staging exports a hash-verified snapshot of the exact pinned source. Focused checks pass for checkout/cart and scan flows (93 tests), label recovery and OCR/location behavior (15 Node tests), patchset/UI materialization (11 tests), label-release staging (3 tests), feedback reporting (15 tests), and legacy label text layout (4 tests). The release receipt also binds the staged backend binary to the exact overlay, patchset, builder, and frontend inputs. Commit `616ef3f` is pushed and verified on `codex/item-shortcodes-integration`. The local production Nuxt build remains unverified because this Windows checkout's package resolver fails with `EPERM` realpath under `node_modules/.pnpm`; typecheck is also blocked by the mismatched local dependency tree. GitHub issue delivery has service-level tests, but live submission requires `CCRATE_GITHUB_TOKEN` in the deployment environment. Issues remain open pending review and merge; #13 also needs its deployment credential configured.

**Follow-up audit (2026-10-14):** Sol found no additional source blocker across #3–16. Two edge cases found in the audit are now fixed: the legacy Python label renderer truncates at grapheme boundaries and omits over-wide glyphs (#3), and NETUM status retains its unfocused warning when a delayed scan result arrives (#16). Their focused tests pass. The full Python suite ran 582 tests: 5 failures, 103 errors, and 9 skips, primarily from the Windows environment (missing `qrcode`/`fcntl`, unsupported symlinks/POSIX mode bits, and unstaged Linux label assets). Nuxt builder/patchset tests pass, but the generated production UI build still fails before compilation when pnpm resolves the Windows staged workspace (`EPERM`). Camera/scanner browser flows, physical output, live Pi behavior, and GitHub delivery remain external verification gates.

**Execution:** Luna Low coding workers handle isolated issue slices in parallel; Sol High reviews each slice; coordinator integrates and verifies the combined result. Use the current checkout because the managed worktree attempt previously could not resolve refs. Keep unrelated dirty Workshop edits and `.serena/` untouched. Do not restart/deploy services, print physical output, mutate operational Homebox data, or close issues until changes are pushed and verified.

## Queue and acceptance

### 0. Build preflight and local barcode integration — #1, #8

- Update `deploy/build-homebox-ui.py` anchors for the current barcode-aware `CreateEntity` dialog type; preparation must remain fail-closed when upstream structure changes.
- Apply all native Homebox changes through the ordered C-Crate patchset on the public source pin; build and release staging must carry the patchset and use the same materialized source.
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
- Keep `upstream/homebox` pinned to the accepted public base and publish its C-Crate patchset as part of this repository. Before push, verify a clean clone can materialize the full patched source from the base plus patches, and that the submodule pointer is fetchable from the configured public remote.
- Do not close issues while their changes are only local. Close only issues whose accepted behavior is present on the remote branch and backed by checks.

## Open issues in scope

`#1, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16`.
