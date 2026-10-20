# Equipment ID management

**Status:** Draft for product review
**Date:** 2026-10-20

## Purpose

Give Workshop managers a reliable place to inspect generated equipment IDs and correct model codes used for future IDs. The existing generated ID format remains `TYPE-CODE-N`, for example `DRONE-2S-6`.

## Agreed direction

- Add a **Workshop → Equipment IDs** page with a collection-scoped list of registered equipment models and their codes.
- Show the model/type, model code, assigned item count, current assigned IDs, and next number for each model. Link each assigned ID to its native item record.
- Allow Workshop managers to edit a model code after reviewing a preview of the next ID.
- A code edit changes IDs assigned in the future only. IDs already assigned to items remain unchanged and continue to resolve and search as before.
- Keep the existing short ID format and sequence. Do not rewrite legacy location-derived IDs, native UUIDs, QR destinations, item fields, or saved template data.
- Keep code changes collection-scoped, validated, conflict-safe, and auditable. The UI must clearly distinguish a model code from a complete assigned item ID.

## User workflow

1. A Workshop manager opens **Equipment IDs**.
2. The page lists registered models and their assigned items. Search can match a model name, model code, or assigned ID.
3. The manager opens a model row to inspect its current code, sequence state, and linked items.
4. The manager edits the model code. The page previews the next ID using the unchanged sequence number.
5. On save, the server validates code syntax and uniqueness within the collection/type, records the change, and updates the model code used for future assignments. Existing assigned IDs do not change.

## Identity and sequence rules

- Native Homebox UUIDs remain the item identity and QR destination.
- Every assigned generated ID remains an immutable identifier for its item. A code edit does not rename prior IDs or change their assignments.
- The existing product sequence high-water mark is retained; editing a code does not reset or reuse numbers.
- Previously assigned codes remain resolvable through their assigned ID records. Code reservations must prevent a retired model code from being accidentally claimed by a different product when it could make assignment ambiguous.
- If the requested code is already owned by another product, reject the edit with a clear explanation and leave all state unchanged.
- Existing unassigned items and legacy generated IDs are not converted by this page.

## Data ownership, permissions, and recovery

Homebox remains authoritative for item identity, type, name, storage, and item access. C-Crate's existing collection-scoped equipment catalog remains authoritative for generated model codes, assignments, and sequence state.

The page is restricted to Workshop managers. Every read and write is scoped to the active collection and authenticated user. The backend validates ownership and item access; browser-supplied product IDs, item IDs, or collection IDs do not grant authority.

Code edits use a durable request identity and optimistic concurrency check. A retry after an uncertain response returns the original result. A stale edit receives a conflict response and requires refresh/review. The audit record includes actor, timestamp, prior code, and new code without exposing secrets or unrelated item data.

## Page loading and navigation

The UI route, page allowlist, sidebar link, and API contract must agree on the Equipment IDs page. An unknown or unauthorized page should show a specific recoverable message rather than falling through to a blank page or unrelated Workshop screen. The page must display a useful load error and retry control if the collection context or equipment catalog is unavailable.

## Acceptance criteria

- A manager can open the Equipment IDs page from Workshop in the live UI, and a direct page refresh retains the same page.
- The page displays registered model codes, assigned IDs, per-model item count, and the next sequence number for the active collection.
- Each assigned ID links to the correct native item; searching by a model code or assigned ID finds the expected model/item.
- A valid code edit is reflected in the next-ID preview and subsequent assignment while previous assigned IDs remain byte-for-byte unchanged and resolvable.
- Duplicate or malformed codes are rejected without changing the product, assignments, or sequence.
- Stale edits and uncertain retries cannot silently overwrite a newer code or create duplicate state.
- Non-manager members cannot edit codes, and no collection can read or modify another collection's equipment codes.
- Missing catalog data and API failures render explicit empty/error states and a retry action; they do not strand the page on an endless loading state.
- No existing equipment-template controls are reintroduced, and no saved template data is deleted.

## Scope exclusions

- Rewriting IDs for items that already have an assigned ID.
- Changing type prefixes, legacy location-derived display IDs, native serial numbers, asset IDs, UUIDs, or QR destinations.
- Bulk editing item metadata or assigning new IDs to every unassigned item from this page.
- Deleting products, assignments, historical IDs, templates, or audit records.
- Adding dependencies or changing deployment/service topology.

## Implementation boundary

Reuse the existing equipment catalog and Workshop UI conventions. Add only the collection-scoped manager API and UI required to list products/assignments and edit a product model code safely. Exact routes, migration needs, concurrency mechanism, tests, and file boundaries belong in the implementation plan after this spec is approved.
