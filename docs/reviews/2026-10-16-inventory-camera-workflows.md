# Project review board: equipment groups, cabinet contents, and OCR camera

**Date:** 2026-10-16  
**Scope:** Plan and challenge three user-requested workflows in C-Crate: related serialized equipment, cabinet-wide visibility of bins and their contents, and zoom/focus in the browser OCR camera.  
**Audience:** Workshop managers and staff using desktop C-Crate and the Raspberry Pi kiosk.  
**Mode:** Read-only code/source review plus planning. No application implementation or tests were run.

## 1. Executive assessment

C-Crate already has the main data needed for these workflows: each physical item retains its own serial and stock state, Workshop knows current custody/condition, a recursive child-location preview is injected into native location details, and the OCR popover already handles camera lifecycle and local structured recognition. The friction is that model and serial fields are not part of Equipment search, cabinet users must expand bins individually, and the OCR camera has no framing/focus controls. The smallest connected improvements are to group exact manufacturer/model matches automatically, batch-load the direct contents of all immediate cabinet bins in the existing preview, and add browser capability-aware camera controls with a clearly labeled digital-zoom fallback. These should remain three independently testable plans because they touch different surfaces and carry different failure risks. No inventory schema migration is needed for the cabinet or camera work; Custom Product group tags are an optional fallback for incomplete model metadata and need a safety/API check before use. The requested OCR work explicitly supersedes the prior OCR-removal proposal; its wording is reconciled in the core-only design file. Confidence is high about current source behavior, medium about the preferred persistent group representation and the actual C920/browser controls, and low about how often other staff encounter these problems because no interviews, support logs, or telemetry were available.

### Strengths observed

- Homebox remains the authority for entity identity, parent/location, tags, serial, quantity, and history.
- Workshop already derives item status from current custody and condition, and checkout performs its own authoritative per-item validation.
- `ChildContents.vue` already provides recursive, read-only child inspection with retry and native links; it is a strong base for the cabinet feature.
- The OCR popover starts camera capture only after an explicit user action, stops tracks on close/minimize/unmount, and keeps photos and recognition in the browser. The staged diff in `OcrPopover.vue` and `local-ocr.js` adds colored OCR lines and bounding boxes but was not tested or reviewed as complete in this board pass.

## 2. Team exchange

Actual read-only subagents participated: Product/UX, Architecture/Engineering, and QA/Security/Performance. The primary agent synthesized product-management and research priorities. The points below are a concise synthesis of actual returned reviews, not a verbatim transcript.

### Grouped equipment

- **UX:** Keep every serialized unit separate; show a group heading with rows that compare serial/asset code, location, condition, and status. Recent notes should retain unit attribution.
- **Architecture:** Native tags could represent group membership without a new database, but the API must preserve every unrelated tag/field. A separate product entity adds storage/API lifecycle work.
- **QA challenge:** Generic tags are visible metadata and a reserved-name convention can collide. Search matches must never imply membership; duplicate serials remain separate; group totals must count physical entity rows and never bypass live checkout validation.
- **Resolution:** Group exact normalized manufacturer/model pairs automatically so ordinary repeated models need no setup. Keep explicit `C-Crate Product group: …` membership as a manager-only fallback for incomplete or inconsistent fields, behind an isolated API semantics test. Custom membership overrides derived grouping for that unit. Similar text and serial matches never establish membership. If the tag safety check fails, ship the derived grouping and omit the custom-group fallback.

### Cabinet contents

- **UX:** Make all immediate bins and their direct contents visible from the cabinet page. A tall expandable list is easier to scan than a grid of 20 cards; preserve the bin name beside each item and keep deeper levels collapsible.
- **Architecture:** The component is already mounted by `deploy/build-homebox-ui.py:399-415` and has a regression contract in `tests/test_location_child_preview.py`. It currently fetches items and location detail separately for each expanded bin. Workshop’s recursive view flattens descendants and is tied to map selection, so it is not the best first surface.
- **QA challenge:** Expanding 20 bins independently could create around 40 reads and unnecessary Pi load. Eagerly loading every descendant risks a large tree, duplicate ancestry, and misleading partial counts.
- **Resolution:** Batch direct items for all immediate child-location IDs through a parent-filtered paginated query. Show every immediate bin (including empty bins) and its direct items by default. Fetch deeper child details only on request; retain returned items and mark the batch partial if a later page fails. Do not add a spatial map or bulk move controls to this slice.

### OCR zoom and focus

- **UX:** The fixed `object-cover` preview can crop label edges; prefer a “fit” preview and keep the captured image coordinates aligned with OCR boxes. Add controls only when useful for the selected camera.
- **Architecture:** The browser camera is a `MediaStreamTrack`; inspect `getCapabilities()` and `getSettings()`, then apply changes through `applyConstraints()`. A server-side Pi camera helper cannot control a camera attached to a remote client browser and would add a misleading second control path.
- **QA challenge:** Zoom and focus features vary by browser/device; mocked support does not prove optical zoom or autofocus behavior. OCR currently makes an enhanced image and runs four recognition passes, which can already use significant memory/CPU on a Pi.
- **Resolution:** Use hardware zoom and focus only when advertised by the active track. Provide local digital crop as an explicitly labeled zoom fallback, apply the same crop to preview and captured image, and do not promise manual focus when unsupported. Preserve capture even when a control fails. Validate actual C920/browser behavior separately; defer OCR-pass optimization until measured.

## 3. Prioritized issue register

Effort ratings are planning estimates only, not measured durations.

| ID | Issue | Evidence / confidence | Solution / alternative | Impact | Effort / risk | Owner | Priority | Acceptance test |
|---|---|---|---|---|---|---|---|---|
| EQ-1 | Find same-model serialized units and compare status | Verified: `workshop-tools.js:162-163` searches name/asset/storage only; full native entities include model/serial. High confidence. | Add model/manufacturer/serial search and exact normalized manufacturer/model groups; permit manager-defined custom groups only as a fallback. Alternative: show search matches as an ungrouped list, which requires staff to scan units individually. | High for user’s repeated Mavic example. | Medium; model data quality and the custom-tag fallback are the main risks. | Inventory/API + Workshop UI | P1 | Search finds records by name/model/manufacturer/serial; group exact manufacturer/model pairs or explicit custom members; each item row retains UUID, serial, location, condition, status; counts reflect the loaded status snapshot; notes link to source item. |
| LOC-1 | Cabinet contents require opening bins one at a time | Verified: `ChildContents.vue:23-48,57-98` loads one expanded node at a time; builder injection and contract test already exist. High confidence. | Batch direct items for all immediate bin IDs with pagination and render under each visible bin; lazy-load deeper locations. Alternative: flattened Workshop list; loses visible bin partition and leaves native location context. | High for cabinet with 20+ bins. | Low-medium; parent association, pagination, and partial batch status need care. | Homebox overlay/UI builder | P1 | A fixture cabinet with 20 bins shows every bin and each direct item without navigation; queries paginate to total; empty bins and partial batch errors are clear; deeper levels remain lazy. |
| OCR-1 | OCR preview cannot control zoom/focus and may crop edges | Verified: `OcrPopover.vue:54-114,267-290` has no controls; current preview uses `object-cover`. Medium-high confidence on opportunity; actual controls unknown. | Capability-aware browser zoom/focus, digital crop fallback, fit framing. Alternative: no UI controls and ask users to reposition; minimal but does not address zoom request. | High for OCR label readability. | Medium; hardware/browser variance and Pi CPU/memory are risks. | OCR frontend | P1 | Mocked range/mode controls apply correctly and reject safely; unsupported camera still captures; live and captured crop match; manual C920 check records actual capability/settings and readable serial result. |
| X-1 | OCR removal and retention directions conflict | Verified in prior core-only spec text; current user has explicitly asked to improve OCR. High confidence. | Retain browser OCR and camera barcode scanning; remove OCR from the removal list and retain it in test/manual checklists. Alternative: preserve old removal proposal, which conflicts with this request. | High scope clarity. | Low, doc-only. | Product/PM | P1 | Core-only spec has one consistent OCR direction and its acceptance/test clauses agree. |
| X-2 | Group recent notes may be incomplete or misattributed | Verified: existing global history response caps results at 100; item notes are per-entity. Medium confidence on edge-case frequency. | Add one collection-scoped batch history read for selected member IDs; keep source entity on every note. Alternative: request each item history separately, creating browser request fanout. | Medium. | Medium; new read route needs authorization and caps. | API + Workshop UI | P2 | Foreign/missing entity IDs are rejected; notes are newest-first, capped, source-linked, and history failure does not hide equipment. |
| X-3 | Browser/OCR/device testing scope conflicts with core-only tooling proposal | Verified: core-only spec removes Playwright and Docker. High confidence. | Use Node/Python pure helper fixtures and a concise supported-browser/manual C920 checklist. Alternative: retain browser automation, which conflicts with the proposed core-only boundary. | Medium. | Low-medium; UI details rely on manual acceptance. | Engineering/QA | P2 | Focused helpers pass; manual checklist records screen size, browser, camera capability/settings, capture result, and no operational data mutation. |

No P0 safety or data-loss issue was identified in the reviewed scope.

## 4. Unified design and engineering direction

Keep one consistent “find the physical thing” model:

- An **automatic model group** answers “which units share these exact manufacturer/model fields?”; an explicit custom group handles incomplete metadata. Neither replaces the individual equipment record.
- A **location subtree** answers “what is inside this cabinet and each bin?” and shows items under their direct storage parent.
- The **OCR camera** helps read a label at intake or inspection time; it does not become another inventory authority. Its output remains editable and must be confirmed before saving item data.

Use existing Homebox identities, location hierarchy, tags, notes, and permission model. Keep user-facing statuses textual, show complete storage path, avoid status color as the only signal, preserve keyboard/touch interaction, and keep long content in a readable vertical list. Each feature gets its own rollback and acceptance check. No new dependency, schema, service, or device permission is proposed by these plans.

## 5. Phased implementation roadmap

### Phase 0 — Scope and safe baseline

- **Modules:** Research/spec and plans only.
- **Work:** Use exact manufacturer/model fields for automatic groups; verify the optional custom-tag fallback and return-note scope. Reconcile OCR-retain direction in the core-only spec. Record staged structured-OCR code as existing but unverified.
- **Checks:** No live Pi/service operations. Preserve unrelated staged changes.
- **Rollback:** Revert only planning-document edits; no runtime change.

### Phase 1 — Cabinet immediate-bin view (smallest existing-surface improvement)

- **Modules:** `ChildContents.vue`, generated location page wiring if required, `test_location_child_preview.py`, optional pure item-to-parent helper.
- **Work:** One batch read of direct items across immediate bins; all bins visible by default; deeper hierarchy remains on-demand.
- **Checks:** Python builder contract, fixture hierarchy with 20+ bins, empty/partial/error cases, desktop and 800×480 manual pass.
- **Rollback:** Revert component/builder UI change; no inventory data is written.

### Phase 2 — Model search and explicit groups

- **Modules:** `ops/desktop_api.py`, `equipment-groups.js`, `workshop-tools.js`, `workshop.css`, Python API fixtures, Node pure-helper tests.
- **Work:** Prove safe tag update behavior before writes; add explicit group management, search fields, member rows, status counts, and batch group notes.
- **Checks:** Duplicate/blank serials, different models with similar names, ungrouped items, every checkout state, history attribution, collection authorization, desktop/touch manual pass.
- **Rollback:** Remove UI/routes if needed. Any Product group tags already written remain ordinary native tags and are preserved; do not auto-delete them as rollback cleanup.

### Phase 3 — OCR camera zoom/focus controls

- **Modules:** `ocr-camera-controls.js`, `OcrPopover.vue`, helper tests, OCR helper tests, manual hardware checklist.
- **Work:** Discover current track capabilities; expose supported hardware controls; digital zoom fallback; fit preview; capture same framing.
- **Checks:** Mocked capability matrix and lifecycle; desktop webcam plus target C920/browser check; no capture blockage when unsupported.
- **Rollback:** Revert browser controls/helper; camera stream stops normally and no persistent OCR data migration exists.

### Phase 4 — Integrated review

- **Checks:** Focused tests for each plan, final review of access/data boundaries, manual workflow from search → choose unit, cabinet → bin → item, OCR frame → capture → edit result. No deployment, restart, physical label printing, or operational Homebox mutation is implied.

## 6. Decision log

| Decision | Current proposal | Status |
|---|---|---|
| OCR product boundary | Keep local OCR and add browser-camera controls where supported. This supersedes the earlier OCR-removal direction. | Explicitly requested now; core-only spec text has been reconciled. |
| Cabinet interaction | Show all immediate bins and direct items together using a parent-filtered, paginated query; lazy-load deeper levels. | First-version default; query pagination and partial state are specified in the plan. |
| Group identity | Derive groups from exact normalized manufacturer/model fields; custom `C-Crate Product group: ` tags are manager-only fallback and override the derived group. | First-version default; only custom-group writes have a hard API safety gate. |
| Group note scope | Return notes only; leave native maintenance distinct. | First-version default. |
| Camera fallback | Hardware zoom/focus only when supported; 1×–4× digital crop fallback for zoom; autofocus explanation when focus cannot be controlled. | First-version default; actual C920 support must be measured. |
| Test stack | Focused Python/Node fixtures plus manual device/UI checks; no Playwright or Docker dependency in the supported path. | Follows current core-only proposal. |

### Defaults adopted for the first implementation

- Cabinet pages open with every immediate bin and its direct contents visible; users can collapse all bins. Deeper descendants remain on demand.
- Digital zoom is included where hardware zoom is unavailable, clearly labeled, capped at 4×, and used for both preview and capture.
- Exact manufacturer/model pairs group automatically without writes. For incomplete or inconsistent metadata, a manager may create one explicit custom group per item; similar text alone never joins items.
- Group notes begin with C-Crate return notes. Maintenance stays in its existing history surface.
- These are scope defaults for implementation, not irreversible data-model decisions. The optional native custom-group tag write remains blocked unless isolated safety tests prove native metadata is preserved.

## 7. Deferred opportunities and next step

Deferred: spatial cabinet maps; bulk move/edit; group auto-merge; multi-group membership; a new Product/Model database; merged return+maintenance timeline; persistent camera presets; Pi-side V4L2 control; OCR-pass performance changes without measurements.

**Plan status:** The three implementation plans are complete to begin execution with the stated defaults and safety gates. The prior session selected subagent-driven development; use that method for implementation, keep each feature independently reviewable, and do not deploy or mutate operational Homebox data as part of development.
