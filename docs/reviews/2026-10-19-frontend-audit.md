# C-Crate frontend review board — 2026-10-19

Status: **Initial audit findings ready for batch approval; implementation and full acceptance coverage remain pending.**

Scope: current dirty development checkout at HEAD `9af4aa323b437261baa7e14706887b3f872e4e54`, served at `http://localhost:17745`. Source files, generated UI and screenshots were inspected. No product edits, operational writes, device actions, service restart or deployment occurred. Existing dirty changes are preserved. Local screenshots contain collection data and must not be committed or published.

## 1. Executive assessment

Keep the existing identity, themes, photos and navigation structure. The most urgent observed friction is the squeezed global search on narrow layouts. Compact controls, inconsistent wording and two different return-dialog implementations add avoidable effort. Existing grouping, bounded metadata hydration, account scoping and uncertain-write protection are useful foundations.

Inventory still presents large cards: at 800×480 the first equipment names fall below the viewport. Item descriptions can contain imported status text while the authoritative borrowing panel reports a different state. This supports the already-approved compact rows and authoritative status summaries; never derive availability from description text or rewrite native descriptions as a presentation fix.

No P0 incident was established. UX-01 is P1 because finding equipment is the primary workflow. Source-only asynchronous/focus/recovery risks remain P2 until isolated browser reproduction shows higher impact. Requested quick actions and member permissions are planned features, not newly discovered regressions.

## 2. Team discussion

Real independent subagents supplied engineering, QA/accessibility and UX/product communications reports; the coordinator handled capture and product/project synthesis. Reports and the baseline file list are retained in `.superpowers/sdd/2026-10-19-frontend-consistency/`.

- **Search/layout:** UX proposed a separate usable search row. Engineering confirmed competing nonshrinking device/OCR controls and warned that wrapping alone is insufficient. Resolution: group search/submit/scanner at a content-width breakpoint; account for sticky edit-header offsets. Collapse sidebar earlier only if still needed.
- **Touch density:** UX measured 27–34 px map controls and 36 px shell controls. Engineering challenged changing the shared native button variant globally. Resolution: scoped 44 px hit areas with wrapping; no overlapping invisible targets or wholesale theme rewrite.
- **Return reliability:** QA challenged any claim of demonstrated wrong-item returns: the missing preparation guard is a concrete source race, not a reproduced custody failure. Engineering agreed. Resolution: local generation/scope guard; absorb draft and recovery behavior into the planned common popup if implemented next, avoiding duplicate modal systems.
- **Recovery integrity:** QA requested direct status access for an uncertain imperative return. Engineering showed that the existing request key can be passed explicitly and checked from the modal; calling the existing generic recovery dialog would replace the retained draft. Resolution: preserve the key and input, read status only, never resend automatically. Native ItemLoans already has Open recovery.
- **Performance:** QA identified cabinet request fanout, but no latency benchmark exists. Resolution: retain current four-wide detail hydration and loaded-only search semantics until a representative 20-bin fixture provides measurements.
- **Device trust:** UX observed Camera Connected in the header and Not ready in System. Engineering found a source-backed possible explanation: local-test System returns string placeholders while the view expects objects; header uses the hardware status endpoint. Exact capture/branch provenance remains to be confirmed. Resolution: local diagnostic consistency investigation, not evidence of a broken live camera or a new meaning for Connected.

## 3. Prioritized issue register

All fixes below are **proposed**, except overlaps with the already-confirmed feature spec. Source locations refer to the audited working tree; record hashes before coding. Effort is relative, not a delivery promise.

| ID / priority | Journey, evidence and confidence | Smallest fix / alternative | Files, acceptance and rollback |
|---|---|---|---|
| UX-01 / P1 | Finding equipment; observed narrow search collapse in `02-locations-390.png`, `03-workshop-map-390.png`, `03-workshop-map-800.png`. | Separate usable search row/group; sidebar breakpoint only if necessary. Small/medium. | Builder shell patch + scoped `ccrate.css`; readable editable query at 390/800, reachable scanner, sensible tab order, no horizontal page overflow, sticky edit toolbar correctly offset. Revert shell hunks. |
| UX-02 + QA-04 / P2 | Map/shell controls; DOM heights 27–36 px fall below approved 44 px target. | Scoped min-size/padding and wrap; avoid global native button redesign. Small. | `ccrate.css`, `workshop.css`, affected templates; measure actual nonoverlapping targets in four viewports/light/dark/zoom. Revert size rules. |
| UX-03/04/05 + ENG-03 / P2 | Map technical wording, destination naming, generic empty states observed; history API caps 100 mixed requests (`desktop_api.py:259–275`). | Consistent task names and headers; distinguish loading/error/empty/filter states; disclose recent loaded history. Full history paging is deferred alternative. Small/medium. | Builder, `workshop-tools.js`, `ItemLoans.vue`; Members/Labels names match destinations, honest note scope and filtered-empty copy, links/permissions unchanged. Revert wording/header hunks. |
| ENG-02 / P2 | Member Label link is unconditional (`build-homebox-ui.py:377`); denied route invokes changed-account messaging (`workshop-tools.js:15,116,695`). Source verified, member browser fixture pending. | Gate link and show explicit role denial for direct URL; alternative visible manager-only link adds noise. Small. | Builder + tools; member nav/deep link and manager access fixtures, genuine expiry still clears context, backend gate unchanged. Revert visibility/denial hunks. |
| ENG-01 / P2 | Native return preparation lacks its own async generation guard (`ItemLoans.vue:37–40`). Source verified. | Local token + item/account/collection snapshot and pending state; disable-only is incomplete. Small/medium. | `ItemLoans.vue`; delay/reorder kit reads, close/change item/scope, ensure no stale reopen/reset; retain current error retry. Revert preparation guard only. |
| ENG-04 + QA-02 / P2 | Native close drops drafts (`ItemLoans.vue:78,83`); imperative unknown return lacks inline status action (`workshop-tools.js:173`). Source verified. | Implement once in forthcoming shared quick-action popup; if delayed, local draft snapshot and request-key status action. Medium. | Both return entry points/shared dialog; all dismissal paths, preserved unknown input/key, no second POST, receipt refresh. Roll back presentation/guards, preserve operation journals. |
| QA-01 / P2 | Map selection repaints focused SVG control (`workshop-tools.js:493–497,340,659,220`). Source verified; empty-room capture cannot reproduce. | Restore current focused stable object identity at each repaint, without delayed focus stealing; renderer rewrite rejected. Small/medium. | Tools; isolated drawing fixture keyboard selection + async refresh retains appropriate focus; pointer pan/zoom unchanged. Revert focus hunks. |
| QA-05 / P2 | UserManager clears changed drafts on close/back/leave (lines 21,54,57,86). Source verified. | One changed-fields close guard; alternative retaining modal draft still needs scope clearing. Small/medium. | `UserManager.vue`; unchanged closes, dirty keep/discard, busy blocked, no write on cancel, no cross-account draft. Revert guard. |
| QA-06 / P2 | OCR panel has no explicit Escape/focus handoff (`OcrPopover.vue:135–138,307–315,330–358`). Source verified. | Preserve nonmodal tool; targeted launch/close/minimize focus and scoped Escape. Native popover replacement deferred. Medium. | OCR component; keyboard launch/close, background access, no unexpected focus stealing, stop work on close. Revert focus handlers. |
| QA-07 / P2 | Label results silently slice 100 (`LabelGenerator.vue:53–55,122–134`). Source verified. | Show first 100 of N / refine query; paging optional later. Small. | Label component; 101+ fixture, narrow search finds last match, selection/review cap preserved, no print. Revert notice. |
| QA-03 / validation gap | Existing desktop checkout/return tests target another implementation and absent route. Source verified; no failing run claimed. | Add focused coverage of mounted current flow as implementation proceeds; do not delete unrelated legacy checks without tracing support. | Current browser/API fixtures; distinguish static contracts, rendered evidence and actual receipt assertions. |
| UX-06 / P3 investigation | Visible System/header disagreement, consistent with `system_status.py:21–31` local-test response shape; capture provenance unconfirmed. | Confirm environment flag and unify adapter shape/message; no camera algorithm change. | System adapter/presentation; same-source local states and unknown/error fixture. No production defect claimed. |

Deferred hypotheses: cabinet latency (QA-H01), OCR rendered contrast (QA-H02), resize-handle semantics (QA-H03), unloaded filtered-bin clarity (QA-H04). Each needs a targeted fixture/measurement before a fix recommendation. Keep unknown availability unknown.

## 4. Unified direction

Use [frontend design rules](2026-10-19-frontend-design-rules.md) and the approved [shared spec](../superpowers/specs/2026-10-19-frontend-consistency-and-quick-actions.md). Primary path: Inventory → group availability/location → explicit unit → action popup → badge when checking out → confirmation → refreshed row and receipt. Cabinet view keeps bins and their contents together, thumbnails, right-aligned `×5 ▸`, and independent disclosure state. No arbitrary first-unit action.

Keep source-overlay development with the existing watcher. Generated files are references, not edit destinations. Frontend edits do not require a release build; Python changes still need a controlled restart. This audit changes neither runtime nor deployment.

## 5. Implementation roadmap

### Batch A — core consistency (recommended first; awaiting approval)

Scope UX-01, UX-02/QA-04 limited to shared shell and map controls, UX-03/04/05, ENG-02/03. Other QA-04 controls in ChildContents/OcrPopover remain deferred to their scoped component work. Frontend owner; one coding worker. Exact files: `deploy/build-homebox-ui.py`, overlay `assets/css/{ccrate,workshop}.css`, `lib/workshop-tools.js`, `components/Workshop/ItemLoans.vue`; add other template overlays only when necessary for the measured header/control. No schema changes.

Acceptance cases: `narrow_search_readable`, `header_sticky_offset`, `targets_44px`, `permission_nav_and_deep_link`, `empty_error_filtered_states`, `recent_history_scope`, `consistent_destination_names`. Use isolated browser fixtures in `tests/frontend_consistency.browser.mjs` plus deterministic contracts in `tests/frontend_consistency.test.mjs`. Before/after captures at 390×844, 800×480, 1280×800, 1920×1080, both themes and actual browser 200% zoom. Keep independent code review and source-to-generated checks. Roll back only scoped hunks; no whole-file reversal in dirty checkout.

### Batch B — approved quick-action workflow and reliability

Proceed under the companion [quick-actions plan](../superpowers/plans/2026-10-19-item-quick-actions.md); incorporate ENG-01/04 and QA-02 into its return component acceptance. Backend status/authorization/receipt contracts precede grouped row action integration. Badge matching remains inside checkout for everyone; check-in own loans and append-only notes follow the approved policy. Preserve kit checks, dirty drafts and uncertain outcome recovery. Review all four actions and mixed cart results against isolated fixtures before calling them complete.

### Batch C — remaining bounded fixes (awaiting approval)

QA-01 map focus, QA-05 member drafts, QA-06 OCR focus, QA-07 label truncation. Exact files are listed per issue. Add targeted cases to the browser runner: `map_focus_async_refresh`, `profile_discard`, `ocr_focus_escape`, `label_result_limit`. No map renderer rewrite, OCR recognition algorithm change or printing action. Scope each fix after reproduction and independent review.

### Investigation and final acceptance

Confirm UX-06 adapter behavior and deferred hypotheses. Measure cabinet requests before optimizing. Complete member, error, nonempty, nested-cabinet, keyboard, light/dark and browser-zoom evidence. A source review or screenshot is not a successful checkout/return test. Do not mark the full audit/feature rollout complete while these remain open.

## 6. Decisions and approvals

Already accepted: Q1–Q26 in shared spec, current brand, 44 px targets, badge/account matching, authoritative status, explicit units, notes and draft rules, account-scoped browsing context, no automatic uncertain-write retries.

Pending: actual audit Batches A/C and incorporation of audited reliability fixes into Batch B. Task 1 explicitly requires presenting actual findings for batch approval; SDD invocation does not identify which previously unknown findings the user accepts. No per-spacing permission requests after batch approval.

Rejected for this evidence: wholesale UI/map rewrite, global palette/font change, speculative cabinet fetch redesign. Deferred: full history pagination and all unmeasured hypotheses. Worktree is prepared but implementation must first preserve the current dirty source baseline; it currently contains committed HEAD only.

## 7. Verification and evidence

Read-only capture commands: `node /tmp/ccrate-audit-pages.mjs`, `node /tmp/ccrate-audit-stable.mjs`, `node /tmp/ccrate-audit-extra.mjs` completed with exit 0. These navigated and captured UI; they did not assert action correctness or run implementation tests. Installed Chromium/Playwright were used, no downloads. Initial login-selector attempts failed and were corrected; transitional captures were rejected.

Accepted local artifacts under `work/frontend-review/`: Inventory `20-items-*-viewport.png`; Locations `02-locations-*`; map `03-workshop-map-*` and `23-map-*`; stable cart `21-checkout-cart-viewport.png`; loans `22-loans-viewport.png`; labels/members/imports/recovery/system/home `06`–`11`; light theme `24-items-light.png`; item detail `26-item-detail.png`. UX inspected core screenshots; coordinator inspected supplemental captures. Initial blank cart/loans and giant full-page Inventory images are excluded as evidence of defects.

Coverage: Inventory/map at four specified viewports; remaining screens primarily 1280, Locations also narrow. Manager-facing isolated local-test environment. Light theme was forced in browser DOM for appearance only, not persisted. `25-items-css-zoom200.png` uses CSS zoom as a stress capture; it is **not** actual browser 200% zoom and cannot satisfy that acceptance requirement. Native browser zoom, full light/dark matrix, member session, expanded nested cabinet, nonempty transactions, dialog failures, screen-reader checks and physical devices remain unverified. These are outstanding coverage, not access blockers or completed checks.

Computed tokens/font/input dimensions are in `24-theme-metrics-{dark,light}.json`; no contrast compliance claim is made. No Pi latency benchmark was performed. Source hashes and dirty-file baseline are retained with the SDD ledger. Private browser state is excluded from all reports/packages/commits.

**Next step:** user approves the concrete batches; coordinator then prepares the current-source isolated baseline, assigns one coding worker, completes focused reproduction/implementation checks and independent review for each batch.
