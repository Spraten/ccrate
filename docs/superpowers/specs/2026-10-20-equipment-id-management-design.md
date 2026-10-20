# Equipment ID management

**Status:** Approved for implementation
**Date:** 2026-10-20

## Purpose

Give Workshop managers a reliable place to inspect generated equipment IDs and correct model codes used for future IDs. The existing generated ID format remains `TYPE-CODE-N`, for example `DRONE-2S-6`.

## Agreed direction

- Add a **Workshop → Equipment ID codes** page with a collection-scoped list of registered equipment models and their codes.
- Show the model/type, model code, active matching item count, active assigned-ID count, existing assigned IDs, and next sequence preview for each model. Link accessible assigned items to their native item records.
- Allow any authenticated current collection member to view and edit a model code, consistent with the prior collection-wide shared-template editing decision.
- A code edit changes IDs assigned in the future only. IDs already assigned to items remain unchanged and continue to resolve and search as before.
- Model-code changes happen through an explicit edit action. Adding an item that matches a registered product must use that product's current code; a stale or different submitted code must not silently change it. A genuinely new product can still register its initial model code during creation.
- Keep the existing short ID format and sequence. Do not rewrite legacy location-derived IDs, native UUIDs, QR destinations, item fields, or saved template data.
- Keep code changes collection-scoped, validated, conflict-safe, and auditable. The UI must clearly distinguish a model code from a complete assigned item ID.

## User workflow

1. A collection member opens **Equipment ID codes** from Workshop.
2. The page lists registered models and their assigned items. Search can match a model name, model code, or assigned ID.
3. The member opens a model row to inspect its current code, item counts, sequence state, and linked items.
4. The member edits the model code. The page previews `TYPE-CODE-(high_water + 1)` and labels it **Next ID preview — not assigned**. The preview is informational; another item assignment may receive that number first.
5. On save, the server validates code syntax and existing collection/type/display-base reservations, records the change, and updates the model code used for future assignments. Existing assigned IDs do not change.

## Identity and sequence rules

- Native Homebox UUIDs remain the item identity and QR destination.
- Every assigned generated ID remains an immutable identifier for its item. A code edit does not rename prior IDs or change their assignments.
- The existing product sequence high-water mark is retained; editing a code does not reset or reuse numbers.
- `Active matching items` counts accessible, non-archived native items linked to the product. `Active assigned IDs` counts those items with a non-deleted assignment. These are separate from the durable next sequence value, which is always `high_water + 1`.
- The ID preview is not a reservation and may become stale after another assignment. The server remains the only allocator.
- Previously assigned codes remain resolvable through their assigned ID records. Code reservations must prevent a retired model code from being accidentally claimed by a different product when it could make assignment ambiguous.
- If the requested code is already owned by another product, reject the edit with a clear explanation and leave all state unchanged.
- Existing unassigned items and legacy generated IDs are not converted by this page.

## Data ownership, permissions, and recovery

Homebox remains authoritative for item identity, type, name, storage, and item access. C-Crate's existing collection-scoped equipment catalog remains authoritative for generated model codes, assignments, and sequence state.

Every read and write is restricted to authenticated current members of the active collection. The backend validates membership, product ownership, and native item access; browser-supplied product IDs, item IDs, or collection IDs do not grant authority. Keep the established collection-member permission rather than adding a manager-only restriction.

Code edits use a durable request identity and optimistic concurrency check. A retry after an uncertain response returns the original result. A stale edit receives a conflict response and requires refresh/review. An append-only audit record includes actor, timestamp, prior code, new code, and request identity without exposing secrets or unrelated item data. Existing item creation cannot overwrite a registered product's code; explicit code editing is the only path to change it.

## Page loading and navigation

The UI route, page allowlist, sidebar link, and API contract must agree on the Equipment IDs page. An unknown or unauthorized page should show a specific recoverable message rather than falling through to a blank page or unrelated Workshop screen. The page must display a useful load error and retry control if the collection context or equipment catalog is unavailable.

## Acceptance criteria

- A collection member can open the Equipment ID codes page from Workshop in the live UI, and a direct page refresh retains the same page.
- The page displays registered model codes, active matching item count, active assigned-ID count, assigned IDs, and the next sequence preview for the active collection.
- Each assigned ID links to the correct native item; searching by a model code or assigned ID finds the expected model/item.
- A valid code edit is reflected in the next-ID preview and subsequent assignment while previous assigned IDs remain byte-for-byte unchanged and resolvable.
- Duplicate or malformed codes are rejected without changing the product, assignments, or sequence.
- Stale edits and uncertain retries cannot silently overwrite a newer code or create duplicate state.
- Any authenticated current collection member can view and edit codes; unauthenticated users and other collections cannot read or modify them.
- Creating an item for a registered product cannot change that product's code, even when a stale suggestion or a different submitted model code is used.
- The next ID preview is visibly labeled as unassigned and refreshes when the page reloads.
- Missing catalog data and API failures render explicit empty/error states and a retry action; they do not strand the page on an endless loading state.
- No existing equipment-template controls are reintroduced, and no saved template data is deleted.

## Scope exclusions

- Rewriting IDs for items that already have an assigned ID.
- Changing type prefixes, legacy location-derived display IDs, native serial numbers, asset IDs, UUIDs, or QR destinations.
- Bulk editing item metadata or assigning new IDs to every unassigned item from this page.
- Deleting products, assignments, historical IDs, templates, or audit records.
- Adding dependencies or changing deployment/service topology.

## Implementation boundary

Reuse the existing equipment catalog and Workshop UI conventions. Add only the collection-scoped member API and UI required to list products/assignments and edit a product model code safely. Exact routes, migration needs, concurrency mechanism, tests, and file boundaries belong in the implementation plan.
