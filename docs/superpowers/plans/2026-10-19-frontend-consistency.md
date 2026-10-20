# Frontend Consistency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Audit C-Crate's actual frontend experience and deliver approved consistency fixes without disrupting equipment workflows.

**Architecture:** Audit native Vue screens and the imperative Workshop UI as one product. Reuse current theme tokens and components; authorize fixes in small batches after evidence and board review. Quick-action backend/UI work is separately specified in `2026-10-19-item-quick-actions.md`.

**Tech Stack:** Vue/Nuxt, TypeScript/browser JavaScript, existing Tailwind/theme CSS, Python source-overlay builder, Chromium and installed Playwright, Node/Python fixture tests.

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

- Long names, duplicate names and missing photos: identifiers/actions remain usable; Task 3 fixtures.
- Keyboard, 200% zoom and 800×480: dialogs/menus stay reachable with visible focus; Tasks 2–4 browser cases.
- Failed/slow status or image loads: existing content remains useful, no false Available label; Task 3 fixtures.
- Account/collection or route changes during requests: stale content does not replace the new view; Task 4 cases.
- Mixed native and imperative screens: common actions retain names, spacing and behavior in both; Task 4 comparative captures.

## File map and execution boundary

Create `docs/reviews/2026-10-19-frontend-audit.md` and `docs/reviews/2026-10-19-frontend-design-rules.md` for evidence and accepted patterns. Store scrubbed screenshot artifacts under `work/frontend-review/`; never commit real personal/inventory data or tokens.

Candidate source modules: `homebox-ui/overlay/assets/css/{ccrate,workshop}.css`, `components/Location/ChildContents.vue`, `components/Workshop/{ActionDialog,ItemLoans,ItemLog,OcrPopover}.vue`, `lib/workshop-tools.js`, `pages/workshop/[tool].vue`, and `deploy/build-homebox-ui.py`. Native source under `upstream/homebox/frontend` and generated `work/homebox-ui-dev` are references, not edit destinations; add focused overlays or builder patches instead.

New verification files: `tests/frontend_consistency.test.mjs` for deterministic pattern contracts and `tests/frontend_consistency.browser.mjs` for isolated browser fixtures. Use the existing installed Playwright package/system Chromium; no runtime downloads.

Tasks 2–4 only execute for user-approved audit findings. Task 1 must replace each candidate batch with exact issue IDs, files, assertions and captures before implementation; do not invent defects to fill the plan.

### Task 1: Evidence-backed board audit and approved batch list

**Files:** create audit/design-rules reports above; read all candidate modules, current `AGENTS.md`, README, prior reports and current diff.

**Interfaces:** produces `Finding {id, journey, state, evidence, confidence, impact, priority, fix, alternative, files, acceptance, rollback, disposition}` records and an approved list of exact implementation tasks. No product code changes.

- [ ] Record current HEAD, dirty-file list and live-development entry point. Distinguish existing modifications from proposed work.
- [ ] Build a route/state inventory for every area; prioritize Inventory, Locations, Workshop and borrowing/returns/cart/history, then OCR, labels, users and secondary tools, escalating serious issues anywhere; mark unreachable states with the actual blocker.
- [ ] Capture desktop/narrow/touch layouts at the four spec viewport sizes and 200% zoom; use fixture records for mutable journeys. Record light/dark and manager/member differences.
- [ ] Assign independent board reviewers the four evidence streams in the spec; require citations and distinguish source inspection from browser evidence. Do not spawn coding workers during audit.
- [ ] Cross-review consequential recommendations: UX versus complexity, performance versus reuse, convenience versus permission/receipt integrity. Record actual disagreements and their resolution.
- [ ] Produce the skill's seven-part report and token/pattern inventory. Record current computed colors/font/spacing before recommending changes; test contrast rather than guessing from hex values.
- [ ] Present actual findings and ask the user to approve prioritized fix batches. Q1–Q26 design decisions are already confirmed; do not ask for them again. Once a batch is approved, complete it without per-spacing/alignment approval requests. Expand Tasks 2–4 into exact finding-specific steps; leave unapproved issues deferred.
- [ ] Commit only the approved documentation hunks when requested by the execution workflow; never stage unrelated existing reports.

### Task 2: Shared layout, navigation and control consistency

**Files:** modify `assets/css/ccrate.css`, `assets/css/workshop.css`, `deploy/build-homebox-ui.py`, and `components/Workshop/ActionDialog.vue` under the overlay root as justified by approved findings. Create tests named above.

**Interfaces:** produces accepted semantic tokens and shared classes `.ccrate-page-header`, `.ccrate-item-actions`, `.ccrate-group-trailing`; keep ActionDialog's existing `modelValue/title/description/busy` props and slots backward compatible. Do not globally restyle every button or override unrelated Homebox themes.

- [ ] Add a regression fixture for each approved issue: assert default landing is Inventory with accessible search while explicit deep links survive; Locations occurs once directly after Workshop; title/action placement matches the approved capture; action targets reach 44 px; modal Cancel/Confirm stay visible at 800×480 and 200% zoom; keyboard focus returns to its trigger.
- [ ] Run `node --test tests/frontend_consistency.test.mjs` and `node tests/frontend_consistency.browser.mjs`; record failures attributable to the fixture assertions, not missing dependencies.
- [ ] Apply the smallest shared token/class or template patch that resolves those approved findings. Keep existing fonts/theme selection and reduced-motion behavior.
- [ ] Repeat both commands and compare before/after captures in light/dark. Confirm no viewport-level horizontal overflow.
- [ ] Request an independent scoped review, fix findings, and commit only approved task hunks with `fix(ui): unify shared navigation and control layout`.

### Task 3: Inventory and location row patterns

**Files:** modify `components/Location/ChildContents.vue`, `lib/child-item-groups.js` only if an approved behavior defect requires it; create a focused overlay for the native Item view actually identified by Task 1. Extend `tests/location_child_contents.test.mjs` and browser fixtures.

**Interfaces:** consumes Task 2 classes; preserves `groupChildItems(items)`, `createChildItemHydrator(fetchDetail, concurrency=4)`, location-scoped expansion, matching/total counts and existing native routes. Quick-action mounting uses the sibling plan’s component contract, not duplicate mutation handlers. Availability summaries depend on its Task 3 status contract; visual fixes may ship independently, but do not mark that feature complete until the status integration is verified.

- [ ] Add cases for 120-character names, identical names with different serials, 0/1/5 members, quantity different from record count, missing/broken photos, partial metadata failure, and independently expanded bins. Add `restore_browse_context` (search/filter/scroll/disclosures survive an item round-trip but never cross account/collection), `group_availability_breakdown` (total, available, checked out, blocked and unknown counts are honest), `no_available_units_visible`, and `narrow_row_priorities` (name/status/count/action visible; specific-unit chooser retains serial/asset ID).
- [ ] Run `node --test tests/location_child_contents.test.mjs tests/frontend_consistency.test.mjs` and the browser runner; record relevant initial failures.
- [ ] Apply the approved alignment/label/spacing fixes; keep `×count` beside the disclosure, identifiers readable, and status honest. Retain bounded hydration and loaded-content search semantics. Add scoped browse-state restoration with Clear filters; show unavailable groups and one primary custody action with secondary cart/note actions. Use authoritative status via the quick-action plan’s status contract; unknown data stays unknown.
- [ ] Repeat tests plus `python -m unittest tests.test_location_child_preview`; measure a 20-bin fixture's requests and first-content time before and after without inventing a performance target.
- [ ] Review screenshots and changes independently, then commit only task hunks with `fix(ui): align inventory and location item patterns`.

### Task 4: Remaining journeys and regression acceptance

**Files:** exact approved modules from Task 1, potentially `ItemLoans.vue`, `ItemLog.vue`, `OcrPopover.vue`, `lib/workshop-tools.js`, `pages/workshop/[tool].vue`; update the audit register and `docs/BETA_HUMAN_TEST.md`.

**Interfaces:** consumes approved design rules and quick-action invalidation events if that plan is complete. Preserves map controls, unsaved drafts, OCR review, loan history and label receipts.

- [ ] Add issue-specific browser regressions, including stale responses after account/route change, recoverable load failure, unsaved editor navigation, and consistent confirmation language across Vue and imperative screens.
- [ ] Run the relevant existing focused tests listed per finding plus the new browser cases; record baseline failures separately from new regressions.
- [ ] Implement approved small fixes. Do not rewrite `workshop-tools.js` wholesale or change OCR/printing algorithms for visual consistency.
- [ ] Run the same checks, capture comparative journeys, and request GPT-6.1 Sol High review of the actual scoped working-tree diff.
- [ ] Confirm generated development files match source and affected Nuxt modules respond without compile errors. Do not confuse this with operational release deployment.
- [ ] Record every finding as fixed, accepted, deferred or blocked with evidence; commit only approved changes and report remaining limitations.

## Rollback and handoff

Revert individual UI commits/hunks, not the entire dirty file. No schema changes belong in this plan. The watcher should restore frontend source automatically; use a controlled restart only for separately approved Python changes. This plan is ready for the audit phase; implementation batches intentionally depend on actual evidence and user approval.

## Interview coverage and document review

Q1–Q26 are recorded in the shared spec’s decision log. This plan owns navigation, browsing context, information hierarchy, group summaries, responsive consistency and audit batch approval. The companion plan owns actions, authorization, notes and recovery. User-visible outcomes must be tested across both Vue and imperative screens. This document update does not claim the visual audit or implementation has occurred.

## Audit checkpoint — 2026-10-19

Initial board findings: [audit report](../../reviews/2026-10-19-frontend-audit.md). Pattern inventory: [design rules](../../reviews/2026-10-19-frontend-design-rules.md). Task 1 remains in progress: evidence gaps and batch approval are explicit in the report. No implementation is claimed.

Proposed sequence: Batch A shared search/targets/wording/role denial; Batch B companion quick actions with return reliability findings integrated; Batch C map/profile/OCR focus and label result disclosure. Exact issue IDs, source files, acceptance cases and rollback are in the report. Tasks 2–4 must consume the approved subset; unapproved recommendations remain deferred. Full role/theme/zoom/state coverage is still required before final acceptance.

## Added work queue: PRINTER-01 — user-operated printer recovery

**Status:** queued at user request; not diagnosed or implemented. **Priority:** high, recurring interruption to label printing.

**Reported symptom:** printer appears in USB devices but the application reports disconnected again and does not reconnect. Treat this separately from the earlier local-test camera/System status discrepancy; USB enumeration alone does not establish print readiness.

**Outcome:** a workshop user can recover through the page's Printer button, or follow specific instructions shown there, without an LLM or developer assistance.

- [ ] Reproduce/trace USB-visible but disconnected state; inspect actual discovery, printer access, connection lifecycle and existing `hardware/status` / `hardware/reconnect` behavior before selecting a fix. Start with `components/Workshop/DeviceStatus.vue` and its backend handlers. Distinguish fresh results from stale cached status.
- [ ] Make Reconnect perform appropriate bounded recovery for the diagnosed failure, with visible progress, duplicate-click protection, a timeout and an honest success/failure result. Re-detect the configured printer after replugging; do not silently select another device.
- [ ] If recovery fails, display the detected cause and concrete steps: distinguish absent device, USB present but inaccessible/busy, service/configuration failure and unknown failure where evidence supports those distinctions. Provide a Check again action after user steps. Do not show generic unplug/replug instructions as the only answer to every failure.
- [ ] Where administrator action is genuinely needed, explain the exact standard package-managed step and who can perform it. Preserve permissions; do not substitute user-space services/drivers or download workarounds.
- [ ] Keep reconnect separate from printing: no unsolicited test label, queued-job replay or automatic retry of uncertain prints. Offer an explicit separately confirmed test print only if appropriate.
- [ ] Acceptance: USB present but inaccessible; absent/replugged device; service unavailable; repeated reconnect clicks; slow/failed recovery; successful reconnect refreshes header and popup consistently. Confirm a normal user can follow the in-app recovery path without an LLM. Use isolated fault fixtures first; schedule any physical output/service-changing checks explicitly.

This is a separately requested recovery task; it does not approve every outstanding frontend audit batch. Record diagnosis, exact implementation scope and evidence before marking it fixed.

### PRINTER-01 investigation checkpoint

USB SUPVAN `1820:207f` is present; `/dev/hidraw0` is accessible by the service user and persistent udev rule exists. The `kiosk-label` executable is absent from both the code and runtime data directories. Adapter lookup also incorrectly used the data root despite `WORKSHOP_CODE_ROOT` being configured. Missing executable errors were reported as a disconnected USB printer.

Implemented explicit/code-root/legacy adapter resolution and a separate software-setup status with restore instructions. Added `deploy/restore-printer-adapter.sh` using the existing source pin and system toolchain, guarded source checkout, minimum compiler version, atomic binary replacement and retained build cache; no print or job replay. Applied backend diagnostics through the existing user service restart. Printer readiness remains blocked by missing build tools, not proved fixed.

Admin step pending: install Rust/Cargo >=1.88 from official Debian trixie-backports plus `liblzma-dev` and `pkg-config`. Default Pi apt Rust1.85 is insufficient. Agent cannot sudo without user password; no alternative runtime installed. After installation run the restore script, then verify a read-only actual printer probe and UI Reconnect. Do not claim physical printing verified without a separately authorized output check. Focused suite: 23 tests passed; physical print not attempted.

### PRINTER-01 restoration completed — 2026-10-19

User completed package installation; pinned printer adapter restored with system Rust/Cargo1.96.1. Direct hardware probe and live UI Printer → Reconnect both confirm connected/ready and40×30mm labels; UI request HTTP200. All23 focused label/hardware/restore-script tests pass. Restore helper rerun succeeded using build cache. Missing-software diagnostics and admin recovery instructions are live. No physical test label printed and no pending print replayed. Report: `.superpowers/printer-recovery-report.md`. The earlier admin/build/readiness blocker is resolved.
