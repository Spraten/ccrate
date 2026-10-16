# C-Crate Core Product Cleanup Design

## Purpose

Reduce C-Crate to the primary inventory and Workshop application. Remove adjacent products and features that add build, runtime, or interface weight without removing the inventory and checkout workflows the user wants to test.

## Approved product boundary

Keep the main Homebox-based C-Crate application and its core workflows:

- Inventory, categories, locations, people, and account management.
- Workshop room maps, storage planning, shelf checks, imports, recovery, and item notes.
- Native barcode fields, camera barcode scanning, and manufacturer barcode lookup.
- Full location-based asset IDs (`displayId`), including regeneration when an item moves.
- Check-in, checkout, returns, loans, and their recovery/history flows in the main C-Crate application.
- Shared authenticated APIs and operation-journal behavior that these retained workflows use.
- The native WSL local-test workflow with isolated local test data.

Remove from the product and build:

- Quick codes (`shortCode`, including generated `XXX-123` values), their schema/API/UI support, and quick-code-specific tests/docs.
- OCR, including the movable OCR pop-out and item-creation OCR/name-suggestion behavior. Keep camera barcode scanning.
- Label design, templates, label preview/queues, and physical label-print functionality.
- The separate Equipment Terminal client and its standalone desktop wrapper.
- Docker-based local development and packaging files.
- Playwright browser-automation dependencies and scripts. Keep focused unit/fixture checks for retained behavior and a concise human test checklist.

## Design

### Keep the shared C-Crate API boundary

The main Workshop currently uses companion APIs served by the process that also serves the Equipment Terminal. Removing that process or shared `ops/desktop_api.py` would break retained main-app workflows. Preserve the companion listener and the API routes, authentication, request identity, recovery, and checkout behavior used by the main app. Remove the terminal's static pages, terminal-only client code, and terminal-specific process behavior. Rename the service only if the rename is behavior-neutral and clarifies that it serves C-Crate APIs.

### Remove features at their owning boundaries

Remove label-specific components and routes from the Homebox overlay, label-specific operations and printer rendering from the companion API, the standalone label editor assets, and label UI assets/build steps. Keep imports, item creation, checkout, and other workflows intact when they have no label dependency. Remove label controls from the main app and shared API adapters; remove the terminal client as a whole.

Remove quick-code generation, persistence, lookup, and presentation. Preserve the independent `displayId` behavior and native barcode field/lookup. Do not add a destructive migration that drops already-created quick-code columns or data; after the feature is removed, existing values are ignored by the application.

Remove OCR launchers, image-to-text/name-suggestion logic, and OCR-only frontend/deployment assets. Retain the camera capture path used for barcode scanning.

### Native development and runtime

Make the native WSL local-test launcher the only supported local development path. Remove `Dockerfile`, Compose configuration, Docker ignore/start scripts, and Docker-only documentation. Keep a private, dedicated local test-data directory and the current bootstrap safeguards. Startup must reuse staged artifacts and must not silently rebuild the app.

### Test strategy

Remove Playwright dependencies and browser automation scripts. Preserve targeted Python and JavaScript unit/fixture tests for inventory, barcode scanning, full asset IDs, checkout/return, Workshop, user workflows, and safe local-test bootstrap. Keep the short manual feature checklist aligned with retained product behavior; remove steps for OCR, quick codes, label printing, and the Equipment Terminal.

## Data and compatibility

- Do not drop existing quick-code database columns/data automatically.
- Existing barcodes, full asset IDs, checkout records, item/location data, users, loans, and operation recovery records remain supported.
- No automatic changes to operational service state or data are part of this cleanup.
- A native local test database remains isolated from any Pi or operational Homebox data.

## Acceptance criteria

1. The main app starts through the native WSL local-test path without Docker and reuses already-staged builds.
2. Main inventory, Workshop, users, camera barcode scan, full location-based asset IDs, checkout, returns, and recovery remain reachable and functional.
3. No quick-code (`shortCode`) generation, API, schema usage, or UI remains in the active C-Crate application/build.
4. No OCR pop-out or item-image OCR/name-suggestion workflow remains; camera barcode scanning still works.
5. No label designer, label template/print queue, label printing service, or label build artifact remains in the product.
6. No separate Equipment Terminal or desktop terminal client remains; shared core APIs still work for the primary application.
7. Docker and Playwright are absent from the supported project workflow and dependencies.
8. Focused retained-feature tests pass, and the human test checklist covers only the retained scope.

## Risks and boundaries to verify during implementation

- The terminal server contains APIs also used by the Workshop. Route ownership must be checked before removing or renaming server modules.
- Label controls appear in main-app item, import, and terminal workflows. Removing them must not leave dead controls or disable import/checkout.
- The Homebox patchset includes barcode, display-ID, OCR, and quick-code changes. Removing selected patches must preserve patch order, generated backend behavior, and OpenAPI consistency.
- Device status currently combines camera and printer information. Printer-only status can be removed with printing; camera status remains only if the barcode scanner uses it.
- Numerous verification scripts use Playwright. Remove browser automation intentionally and retain small deterministic tests rather than replacing it with another browser framework.
