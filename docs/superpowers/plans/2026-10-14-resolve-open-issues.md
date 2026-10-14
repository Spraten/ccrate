# C-Crate Open GitHub Issues — Resolution Plan

**Goal:** Resolve the 15 issues currently open in `Spraten/ccrate` with small, verified changes. Preserve the existing Homebox authority, C-Crate overlay pipeline, printer recovery safeguards, badge audit semantics, and user's existing local Workshop work.

**Current delivery state (2026-10-14):** Draft PR #17 is at `9e5cae57509fa458a3f7140a0a0a1c93e2a8ddab`. The latest commits restored four unreadable GitHub blobs from the exact local readable sources and added the missing checkout-cart regression tests. Sol reviewed both commits; the repaired files' blob hashes match local and GitHub reports them as UTF-8. Current focused checks pass: 52 Python display-ID, builder, navigation, feedback, and cart tests; all 43 Node tests; 17 patchset/builder tests; and JavaScript syntax validation. The 46-test desktop API suite still has Windows hard-link permission failures; GitHub reports no workflow runs. Keep the PR draft until the broader supported-platform checks and remaining product verification are complete. Browser automation remains unavailable here because Playwright is not installed and Bash cannot start in the sandbox. Browser camera flows, physical label printing, NETUM C750 hardware, Raspberry Pi runtime, and live theme changes remain hands-on verification gates.

Issue #9's browser-local name suggestion is in the PR, but its later-requested header toggle and OCR overlay are a separate UX upgrade and are not implemented. The selected direction is a draggable, chat-style pop-out that stays above the app, with camera capture and editable/copyable OCR results. A themed mockup has been shown and approval is pending before implementation. GitHub issue submission requires `CCRATE_GITHUB_TOKEN` in the deployment environment. All 15 issues remain open until the PR is reviewed, merged, and each applicable external gate is satisfied; the Pi release build remains paused.

**Follow-up audit (2026-10-14):** Sol found no additional source blocker across #3–16. Two edge cases found in the audit were fixed: the legacy Python label renderer truncates at grapheme boundaries and omits over-wide glyphs (#3), and NETUM status retains its unfocused warning when a delayed scan result arrives (#16). The #8 decoded-value omission is fixed in patch 0024, with a focused regression test. A follow-up review found Letter margin/gap edits cleared valid item previews (#5); the fix preserves the item reviews and print records, clears only the composed sheet, and rejects stale in-flight compositions. The full Python suite ran 582 tests: 5 failures, 103 errors, and 9 skips, primarily from the Windows environment (missing `qrcode`/`fcntl`, unsupported symlinks/POSIX mode bits, and unstaged Linux label assets). The 12-test Nuxt builder/patchset group passes. Direct Nuxt preparation succeeds, but production build and Vitest stop before compilation/test collection on Windows with `EPERM` native-realpath failures; typecheck output is invalidated by missing package links. Camera/scanner browser flows, physical output, live Pi behavior, and GitHub delivery remain external verification gates. The isolated staged-snapshot materialization test passes.

**Final source review (2026-10-14):** Sol identified that a confirmed-not-started label print failure was shown only in the hidden native view and incorrectly stopped the queue. The label workspace now shows the specific failure and allows retry only when the request is confirmed absent; retained/uncertain requests stay locked with Recovery guidance after reload and after a fresh preview. The browser host fixture inlines the new recovery helper so its classic-script harness remains valid. Feedback submission success text now uses a dark-theme readable color. Final focused validation passes: 43 Node tests; 63 Python contract/request/builder tests (1 skipped); and a supplementary 40-test patchset/builder/navigation/display-ID/cart run (1 skipped, overlapping the focused batch). The Playwright browser suite could not run because Playwright is not installed in this Windows runtime; broad Python discovery remains non-passing for the previously recorded Windows/platform dependency reasons. Target hardware, Pi deployment, and live feedback delivery still need their respective external checks.

**Execution:** Luna Low coding workers handle isolated issue slices in parallel; Sol High reviews each slice; coordinator integrates and verifies the combined result. Use the current checkout because the managed worktree attempt previously could not resolve refs. Keep unrelated dirty Workshop edits and `.serena/` untouched. Do not restart/deploy services, print physical output, mutate operational Homebox data, or close issues until changes are pushed and verified.

## Queue and acceptance

### 0. Build preflight and local barcode integration — #1, #8

- Update `deploy/build-homebox-ui.py` anchors for the current barcode-aware `CreateEntity` dialog type; preparation must remain fail-closed when upstream structure changes.
- Apply all native Homebox changes through the ordered C-Crate patchset on the public source pin; build and release staging must carry the patchset and use the same materialized source.
- Fix duplicate Nuxt component registration at its source without deleting intentional barrel exports or breaking shadcn imports.
- Keep the scoped oxc WASI fallback and distinguish its known experimental notice from build errors; real failures must keep a nonzero exit code.
- Verify in a disposable generated workspace. This preflight is required before validating other frontend issues.
- #8 now shows the decoded barcode in the detected status; the new helper has a focused source regression test, and generated patch materialization passes. Still verify camera decoding and the complete browser flow when the generated UI can run with camera permission. Keep #8 open until the PR is reviewed, merged, and behavior is validated.

### 1. Label output and printer recovery — #3, #5, #7

- #3: use one text-layout policy for designer preview, printed output, and legacy label rendering; cover multiword text, long identifiers, Unicode, explicit line breaks, small boxes, SUPVAN, and Letter output.
- #5/#7: expose persisted queue/recovery state immediately on page load; show useful status and a direct Recovery path; keep request keys and never auto-resend uncertain output. Keep “Print anyway” unavailable for uncertain outcomes.
- Remove the repeated separate review-window stop for routine printing. A good saved label design can be previewed in context and printed through the existing explicit print action; keep the physical print confirmation and never auto-repeat uncertain output.
- For Letter sheets, changing page margin or label gap preserves the current item previews and print records, invalidates only the composed sheet, and prevents an older in-flight composition from restoring stale geometry.
- Verify retries, cancellation, timeouts/lost responses, page reload with pending operations, double click, recovery, and that uncertain work cannot duplicate physical printing.

### 2. Add Item capture and form usability — #6, #9, #11

- #6: extract/reuse the existing webcam capture flow in a Vue component, add it to item edit, and reuse the same preview/save path as uploaded photos.
- #9: current item-form OCR suggestion flow is implemented and its four local OCR tests pass. Queue the UX upgrade: add a header-bar toggle that enables a movable, chat-style pop-out which stays above the app. Let the user drag it around, capture a photo, scan text, then edit or copy the result. Keep recognition browser-local and do not upload photos externally or silently overwrite item text. Show the revised interaction mockup for review before implementing the new overlay.
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
