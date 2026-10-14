# C-Crate Item Barcode Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Save a scanned or manually entered barcode on a C-Crate item, allow lookup enrichment when available, and find matching items without requiring catalog data.

**Architecture:** Add a nullable barcode field to Homebox's entity schema and API, with a backward-compatible migration for both supported databases. Extend the existing group-scoped item query with an exact barcode filter, then keep capture, optional catalog lookup, and duplicate results in the existing C-Crate item-create flow.

**Tech Stack:** Go, Ent, Goose, SQLite/PostgreSQL, Nuxt/Vue 3, TypeScript, ZXing, Vitest.

**Spec:** `docs/superpowers/specs/2026-10-13-ccrate-item-barcode-design.md`  
**GitHub issue:** [#8 Fix barcode scanning and show live scan feedback](https://github.com/Spraten/ccrate/issues/8)  
**Execution:** Use one GPT-6 Luna Low coding agent per task, in sequence; use GPT-6.1 Sol High for the independent final review; Astra coordinates.

## Global Constraints

- Make the smallest complete change. Reuse existing Homebox APIs, UI components and helpers. Do not add dependencies or unrelated features.
- Homebox is the inventory and account authority. Preserve native identities, metadata, access rules and history.
- Use isolated local test data; never connect tests to the live Pi.
- Accept an opaque barcode string up to 80 characters, trim surrounding whitespace, preserve leading zeroes and internal characters, and do not impose uniqueness.
- Do not add OCR, image scraping, external catalog integrations, kiosk behavior, or a new settings subsystem.

## Review Focus

1. Camera denied or unavailable: manual code entry still works and can save (Task 3 test).
2. Alphanumeric code / leading zeroes: code persists unchanged through API create, read, and update (Task 1 tests).
3. Barcode omitted by older clients: existing create/update requests continue to work (Task 1 tests).
4. Duplicate code in the same or another group: show same-group matches, never leak cross-group items, and do not block saving a duplicate (Task 2 repository/API tests; Task 3 UI test).
5. Lookup miss or provider failure: preserve the code and manual fields; a match only prefills editable fields and does not silently overwrite edits (Task 3 tests).

---

### Task 1: Persist barcode on entities and expose it through the item API

**Files:**
- Modify: `upstream/homebox/backend/internal/data/ent/schema/entity.go`
- Generate: Ent code under `upstream/homebox/backend/internal/data/ent/`
- Create: versioned Goose migrations under `upstream/homebox/backend/internal/data/migrations/sqlite3/` and `.../postgres/`
- Modify: `upstream/homebox/backend/internal/data/repo/repo_entities.go`
- Modify: `upstream/homebox/backend/internal/data/repo/repo_entities_test.go`
- Modify: item API request/response contracts and generated TypeScript contracts (`upstream/homebox/frontend/lib/api/types/data-contracts.ts`)

**Interfaces:**
- Produces: `barcode` as an optional string on entity create/update/output. Persist empty values as SQL NULL; maximum length is 80. Existing clients may omit it.

- [ ] Add repository tests that create an entity with `X9TEUJR4L` and `0012345`, then read/update it and assert the value is preserved exactly.
- [ ] Add a compatibility test showing create/update without `barcode` remains successful and returns an empty barcode.
- [ ] Run the focused repository test from `upstream/homebox/backend`: `go test ./internal/data/repo -run 'TestEntityRepository.*Barcode|TestEntity.*Barcode' -count=1`; confirm it fails before implementation.
- [ ] Add optional `barcode` (max 80) to the Ent entity schema, with a non-unique index. Run `go generate ./internal/data/ent` from the backend directory.
- [ ] Add forward/backward-compatible Goose migrations for SQLite and PostgreSQL that add/drop the nullable column and non-unique index; leave existing rows NULL.
- [ ] Add barcode to create/update/output repo structs and map it through create, update, and entity response conversion. Update the API source contract and run `task generate` from `upstream/homebox` to refresh OpenAPI docs and `data-contracts.ts`.
- [ ] Run `go test ./internal/data/repo -run 'TestEntityRepository.*Barcode|TestEntity.*Barcode' -count=1` and `go test ./internal/data/migrations/...`; both must pass.

### Task 2: Add exact, group-scoped barcode search for duplicate review

**Files:**
- Modify: `upstream/homebox/backend/internal/data/repo/repo_entities.go`
- Modify: `upstream/homebox/backend/internal/data/repo/repo_entities_test.go` and `repo_authz_test.go`
- Modify: existing v1 item-list query parsing/handler under `upstream/homebox/backend/app/api/handlers/v1/`
- Modify: generated API client/types if the query contract is generated

**Interfaces:**
- Consumes: persisted `Entity.Barcode` from Task 1.
- Produces: an optional exact `barcode` filter on the existing group-scoped item query. Results retain existing paging and authorization behavior; a repeated product code is valid and returns each matching item across pages.

- [ ] Add tests that create two same-group entities with barcode `X9TEUJR4L` and one entity with a different barcode; exact lookup must return only the first two.
- [ ] Add an authorization test proving an exact barcode lookup in one group cannot return another group's matching entity.
- [ ] Run focused tests and confirm they fail: `go test ./internal/data/repo -run 'Test.*Barcode.*(Search|Query|Group)' -count=1` from the backend directory.
- [ ] Add the exact barcode filter to the existing list query and apply `entity.Barcode(code)` alongside its current group, archived, and item/location constraints. Trim the query value; do not use a partial match.
- [ ] Parse and pass the optional query parameter through the existing v1 item-list handler; do not create a separate unscoped endpoint.
- [ ] Run `go test ./internal/data/repo -run 'Test.*Barcode.*(Search|Query|Group)' -count=1` and the focused v1 handler tests; both must pass.

### Task 3: Keep scan, manual entry, enrichment, and duplicate review in Add Item

**Files:**
- Modify: `upstream/homebox/frontend/components/Entity/CreateModal.vue`
- Modify: `upstream/homebox/frontend/components/App/ScannerModal.vue`
- Modify: `upstream/homebox/frontend/components/Item/BarcodeModal.vue` only as needed to retire its create-flow handoff
- Modify: `upstream/homebox/frontend/components/ui/dialog-provider/utils.ts`
- Modify: `upstream/homebox/frontend/pages/item/[id]/index.vue` and `.../index/edit.vue`
- Modify: existing locale files for item barcode labels/status text
- Test: focused Vitest tests alongside the relevant existing frontend component/API tests

**Interfaces:**
- Consumes: create/update/output `barcode` from Task 1 and exact list filter from Task 2.
- Produces: `CreateEntity` accepts an optional initial barcode; scanner results route into that form, and candidate lookup fills only untouched/empty fields.

- [ ] Add frontend tests for the following behaviors: manual alphanumeric entry survives create; scanned code initializes the create form; lookup miss/provider error leaves manual creation enabled; selecting a product prepopulates editable fields; user edits made before selection are not silently overwritten; duplicate results appear but do not block saving; scanner status changes from starting to scanning to detected/error; frame-level `NotFoundException` keeps the scanning status instead of showing an error.
- [ ] Update the scanner format switch to recognize Code 128 in addition to existing UPC/EAN formats, then pass the detected value into the existing CreateEntity dialog rather than leaving it only in Product Import. Preserve URL/QR navigation. Add visible live status beside the video for camera startup, active scanning, the decoded value and format, and actionable camera errors; ignore normal frame-level `NotFoundException` results.
- [ ] Add a labelled barcode field and optional lookup action to Add Item. Accept 1–80 characters after trimming. For numeric codes use the existing product lookup; show candidates for explicit selection and leave the form usable when lookup returns no match or fails.
- [ ] Include the barcode in normal item creation and template-based creation when provided. Use the exact barcode query to show matching inventory items in the create flow; selecting a match opens it, while the current form remains available to create a duplicate.
- [ ] Add barcode to item detail and edit screens and send updates through the existing item API.
- [ ] Run the focused frontend component/API tests, `pnpm typecheck`, and `pnpm lint:ci` from `upstream/homebox/frontend`; all must pass.

## Final verification

- Run `go test ./internal/data/repo ./internal/data/migrations/...` from `upstream/homebox/backend`.
- Run focused v1 item handler tests from `upstream/homebox/backend`.
- Run frontend focused tests, `pnpm typecheck`, and `pnpm lint:ci` from `upstream/homebox/frontend`.
- Manually verify with isolated local data: enter `X9TEUJR4L`, save and reopen; enter `0012345` and confirm zeroes remain; scan a UPC/EAN or Code 128; and confirm no-match lookup still permits save.


