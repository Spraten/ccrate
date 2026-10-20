# UI and Hardware Acceptance Follow-up Plan

> **For agentic workers:** Use the already selected subagent-driven-development workflow. Keep each task in the live development checkout so UI edits hot-reload.

**Goal:** Make grouped equipment reachable and complete practical OCR and cabinet-content validation in the isolated Pi development environment.

**Architecture:** Register the existing Equipment tool route and add a visible path from Workshop. Keep existing grouping, history, and authorization behavior. Diagnose OCR in the active browser before changing its runtime; use the existing local OCR pipeline. Run cabinet measurements only against isolated test data and remove all temporary rows.

**Tech Stack:** Vue/Nuxt route, Workshop browser JavaScript, existing Node/Python tests, Playwright already present on the Pi, local Homebox test data.

**Spec:** `docs/superpowers/plans/2026-10-16-grouped-equipment.md`, `docs/superpowers/plans/2026-10-16-ocr-camera-controls.md`, `docs/superpowers/plans/2026-10-16-cabinet-contents.md`.

## Global Constraints

- Keep Homebox as inventory authority and preserve per-item IDs, metadata, tags, and history.
- Do not restart or deploy operational services, print labels, or mutate operational Homebox.
- Use the running local-test environment or disposable local fixtures only; clean up test records and verify cleanup.
- Do not add dependencies or replace system services.
- Hardware controls must reflect browser-reported capability; label digital crop as digital zoom.
- Report unverified hardware acceptance honestly; no success claims without observed results.

## Review Focus

- Direct navigation to an unsupported or signed-out Equipment route must retain existing authentication behavior.
- Search must preserve each serialized physical record and not merge on serial/name similarity alone.
- Local OCR runtime/model failures must surface a usable error and leave the capture/edit flow recoverable.
- 21-bin cabinet filtering must only claim to search loaded data and preserve nested-bin semantics.
- Temporary fixture cleanup must leave the local-test baseline inventory unchanged.

## File Map

- `homebox-ui/overlay/pages/workshop/[tool].vue`: allow the existing Equipment tool route.
- `homebox-ui/overlay/lib/workshop-tools.js`: expose a clear Workshop link to Equipment.
- Existing grouped-equipment and OCR tests: regression checks for route and OCR failure handling where a pure test is suitable.
- `docs/BETA_HUMAN_TEST.md`: record measured camera, screen, cabinet, and printer observations.

## Task 1: Reachable grouped equipment

- [ ] Add a visible Equipment link from Workshop and allow `/workshop/equipment` while preserving auth middleware.
- [ ] Run focused existing group tests and inspect the 800×480 local UI route.
- [ ] Search the local Mavic records; verify group semantics, per-unit serials/status, and history behavior. Do not change operational data.

## Task 2: OCR scan completion

- [ ] Reproduce the stall in a fresh browser context; capture console, worker, and network failures without exposing credentials.
- [ ] Identify whether the fault is runtime download, worker/model initialization, or OCR processing.
- [ ] Fix only a confirmed C-Crate defect; add a focused regression test and rerun OCR helper tests.
- [ ] Verify capture, scan completion/error state, line boxes, colored text, editable text, and recoverability at 800×480.

## Task 3: Cabinet and hardware acceptance

- [ ] Use an isolated disposable fixture with a cabinet and 21 bins, with sample contents in multiple bins.
- [ ] Record first-content latency, immediate-bin count, and location/item detail request counts; verify filter finds a known item.
- [ ] Delete all temporary data and verify the baseline inventory count.
- [ ] Record C920 capability/zoom readback, framing/focus limits, 800×480 behavior, and printer connection/configuration status. Do not print physical output.

