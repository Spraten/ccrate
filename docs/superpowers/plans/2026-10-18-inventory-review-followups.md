# Inventory Review Follow-ups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the grouped-equipment notes coverage gap and record the pending cabinet, OCR camera, and small-screen acceptance checks with an accurate live-development boundary.

**Architecture:** Keep the existing 100-ID limit on the collection-scoped history endpoint. The UI will request deterministic member batches, merge available results, and report partial failures without hiding notes already loaded. Documentation will expand the beta checklist and explicitly distinguish local UI hot reload from Pi release activation.

**Tech Stack:** Existing browser JavaScript, Node built-in tests, Markdown documentation.

**Spec:** `docs/superpowers/plans/2026-10-16-grouped-equipment.md` and `docs/research/2026-10-16-inventory-browsing-and-grouping.md`.

## Global Constraints

- Keep Homebox as the inventory authority and preserve collection-scoped history validation.
- Keep each history request at or below 100 distinct entity IDs.
- Do not contact or mutate operational Homebox or deploy/restart services.
- Do not change cabinet fetching strategy without measured evidence.
- Do not claim C920, target-screen, or real-inventory acceptance without running those checks.
- Add no dependencies.

## Review Focus

- Groups above 100 members: later-ID newest notes must be included; test a note on member 101.
- Partial history failures: already loaded notes remain visible and a clear partial-load message appears.
- Duplicate or unordered history rows: notes are globally sorted newest-first and capped at five.
- Many-bin cabinets: record request count and time without changing existing content/loading semantics.
- Camera and narrow-screen checks: record actual target hardware/browser and visible focus/control behavior.

## File map

- `homebox-ui/overlay/lib/equipment-groups.js`: deterministic history member ordering and 100-ID batching; partial-result presentation.
- `homebox-ui/overlay/lib/workshop-tools.js`: fetch group history by bounded batches and retain partial successes.
- `tests/equipment_groups.test.mjs`: regression coverage for member 101 and partial history.
- `docs/BETA_HUMAN_TEST.md`: group, cabinet, camera, narrow-screen, and cabinet timing checks.
- `docs/development/live-ui.md` and `README.md`: local HMR versus Pi release boundaries.

## Task 1: Fetch recent notes across all group members

- [x] Add failing tests for batching all IDs into chunks of 100, the newest note attached to sorted member 101, and partial-result presentation.
- [x] Run `node --test tests/equipment_groups.test.mjs` and verify the new assertions fail for the current first-100 behavior.
- [x] Implement deterministic member batching and merge successful UI batch responses; preserve successful rows if a batch fails.
- [x] Run `node --test tests/equipment_groups.test.mjs` (13/13 passed, including orchestration success and partial-failure cases).

## Task 2: Expand acceptance and development-boundary documentation

- [x] Add grouped-equipment and cabinet filter cases to `docs/BETA_HUMAN_TEST.md`.
- [x] Add target C920/Chromium, focus/zoom/readback, framing/OCR alignment, keyboard/touch, and 800×480 checks; mark them manual.
- [x] Add a 20-bin cabinet measurement step recording detail-request count and first-content latency; do not prescribe optimization without timing evidence.
- [x] Clarify in the live UI docs and README that overlay UI edits hot-reload only in the local development stack; Python companion changes and Pi release activation have separate restart/package paths.
- [x] Review the diff for accuracy and run `git diff --check`.

## Task 3: Focused verification and handoff

- [x] Run the Node equipment-group tests (13/13 passed) and wider Node suite (94 passed, 3 environment/source failures).
- [x] Verify the Python API still enforces the 100-ID limit and collection validation by source review; no API contract change was made.
- [x] Record device-dependent acceptance items as open.
