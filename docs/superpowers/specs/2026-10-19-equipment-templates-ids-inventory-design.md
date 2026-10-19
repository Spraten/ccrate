# Equipment templates, generated IDs, and grouped Inventory

**Status:** Draft for product review  
**Date:** 2026-10-19

## Purpose

Make it quick to add repeat equipment without re-entering shared details, make generated IDs short and stable, and let staff understand model totals and individual unit status/location from Inventory.

The user-approved direction is:

- Equipment templates are shared across the current C-Crate collection and any collection member may edit them.
- Templates supply defaults for new items. Updating existing items is a separate, explicit action.
- New items use short generated IDs such as `DRONE-2S-6`. Existing IDs remain unchanged.
- The initial sequence for a model continues after the number of matching existing items. It then advances monotonically and is not reused after deletion. Moving an item does not change its ID.
- Inventory groups matching units across locations and exposes individual unit details when expanded.

## User workflow

### Create a reusable template

A member can start a template from an existing item using **Save as template**, or create one while adding an item. The template contains shared descriptive data: item type, name, manufacturer, model, editable model code, description, tags, and a default thumbnail/photo when available. The interface makes it clear that a template is shared with the collection.

Template codes are short values such as `2S`, `M3C`, and `M4P`. They are unique within an item type. Code edits affect IDs assigned to future items only; previously assigned IDs never change.

### Add another unit

The member chooses a template. Shared information fills in automatically. The member reviews the details and enters or scans the unique serial number, confirms the item's individual location and condition, then saves. The server assigns the next ID, for example `DRONE-2S-6`, in the same durable operation as the item creation or through an idempotently recoverable assignment step.

Serial numbers, current custody/status, notes, and per-unit location are never copied from a template. The template may provide a photo and shared description, but the new record can be reviewed and edited before save.

If a matching template does not exist, the member can enter an item normally and provide or create a model code as part of creation. Generated IDs for newly created equipment use the short format regardless of whether a template supplied the details.

### Browse Inventory

Inventory presents product groups across all storage locations. A group row shows a representative thumbnail, product name, honest unit count (for example, `Air 2S  ×5`), and a compact status summary. The disclosure expands to individual native item records. Each unit shows its thumbnail when available, status, full location path, serial number, generated ID, recent note preview, and existing quick actions.

A search for a model or identifier finds the containing group and expands the matching unit where practical. Existing native filters, permissions, bulk actions, pagination, and item-detail routes remain available. Grouping is computed across the complete filtered result set before pagination so group counts are not presented as page-local totals.

## Group identity and matching

Use the existing explicit product-group metadata when present. Otherwise, group by item type plus normalized manufacturer and model. Where those fields are absent, use the existing conservative exact-name fallback only when known metadata does not conflict. Never merge records solely because their display names are similar when manufacturer/model data identifies different products.

Templates carry a stable product identity and model code. Multiple templates for the same product (for example, packaging variants) share the same group and ID sequence. A code cannot be assigned to two different products of the same item type without an explicit resolution step. Count records separately from any native quantity field so the summary does not imply that one bulk record is several individually tracked items.

## Generated ID behavior

The visible format is `TYPE-MODEL-N`, with normalized uppercase ASCII segments, for example `DRONE-2S-6`. The type prefix comes from the native item type. The model segment comes from the product template/model code and can be edited before new IDs use it. The number is a collection-scoped sequence for a product identity.

At first allocation, seed the next number from the count of existing matching native item records, so the sixth matching unit receives `...-6`. After that, store a high-water mark transactionally. Concurrent creates must not receive the same ID. Deletion leaves a gap; moves, renames, later item edits, and template edits do not reassign an existing ID.

This feature changes generated IDs only for newly created records. Current IDs for existing records remain valid and searchable. Native UUIDs and QR destinations do not change. Labels consume the current generated ID at preview time; reviewed print payloads must continue to detect an ID change between preview and print.

## Data and integration design

Homebox remains the authority for native item identity, photos, item fields, storage, access, and history. Templates and stable generated-ID assignments are collection-scoped C-Crate metadata linked to native item/product identity. Do not place serial numbers, custody, notes, or unique item state in a template.

The backend owns template validation, product-code uniqueness, sequence allocation, and ID persistence. The UI must not allocate identifiers locally. New-item creation and ID assignment must behave as one idempotent operation: if the integration spans more than one storage write, persist the request identity and recovery state so a retry returns the same native item and ID rather than creating a duplicate.

The current location-derived display-ID calculation must remain available for legacy records during transition. New records receive a persisted short ID and do not have it recomputed by location or rename refreshes. Search resolves both legacy and new generated IDs alongside native identifiers. Inventory grouping uses the same product identity rules as template creation and ID allocation.

Template edits are collection-wide and concurrency checked. Changing defaults affects future creation. Applying changed shared fields to existing records requires the user to choose the exact units and fields, preview the affected values, and confirm; it must never change serial number, location, condition, status, checkout state, notes, UUID, or generated ID through bulk template application.

## Errors and recovery

- Invalid/duplicate model codes are rejected with a field-level explanation before allocation.
- If an item save is uncertain, keep its idempotency key and query status before retrying. The server must return the original item and assigned ID for a completed replay.
- If a product identity conflicts with an existing code or group, ask the member to select the existing product/template or resolve the conflict; do not silently merge products.
- If the item has no photo, show the standard thumbnail placeholder.
- If status/location/history cannot be loaded, show an explicit unavailable state; do not infer “in stock” or hide the unit.
- If an item cannot be grouped confidently, show it as an individual row.
- Existing custom column preferences may be preserved, but Inventory's default presentation removes Insured and Purchase Price and shows Photo, Name, Status, Location, and Quantity/group disclosure. Financial data stays on item detail.

## Permissions and audit

All current collection members may create and edit shared templates, as requested. Template writes are authenticated, collection-scoped, validated, and recorded with native member identity and timestamp. Item-level permissions remain Homebox-controlled. Grouping does not grant additional access to hidden items or allow a member to perform an action they could not perform on the individual record.

## Rollout and compatibility

1. Add additive collection-scoped template and stable-ID allocation storage with migration tests.
2. Preserve old display-ID generation for records without a persisted short ID; add lookup support for both formats.
3. Add template create/edit/select flows and backend-owned new-item ID allocation with replay recovery.
4. Add Inventory grouping, summary, expansion, per-unit detail, search expansion, and column defaults while preserving native deep links and bulk operations.
5. Connect labels and quick actions to expanded native units; verify label preview/print identity checks.
6. Roll out without rewriting existing IDs. Provide a way to resolve duplicate model templates/codes before they affect new assignments.

## Acceptance criteria

- Adding a repeated unit from a template fills shared fields and leaves serial, condition, custody, note, and location for the member to confirm.
- A new unit gets `TYPE-CODE-N`; sequence allocation is unique under concurrent creation and survives movement, edits, and deletion of other units.
- Existing records keep their exact generated IDs; both old and new IDs remain searchable, and existing QR links continue to open the same record.
- A replay after uncertain creation returns the same native item and generated ID without creating a duplicate.
- Five matching individual Air 2S records across different locations display as one `×5` group; expansion shows each record's own status, full location, serial, generated ID, and available quick actions.
- Distinct products with similar names do not merge. Missing status/location/photo values render explicit states/placeholders.
- Filters and group counts cover the full result set, preserve native authorization and bulk actions, and do not make pagination totals misleading.
- Default Inventory columns show the requested photo/status/location and omit Insured/Purchase Price; users can still find financial fields on item detail.
- Template edit and any explicit apply-to-existing operation are scoped, reviewable, auditable, and recoverable.

## Draft defaults for review

- Archiving a template removes it from new-item selection but retains its model code and assignment history, so old IDs and product identity remain unambiguous. A reserved code cannot be reassigned to a different product of the same type.
- Members can create a template inline while adding an item; the same collection-wide validation and audit rules apply.
- Template archive is reversible. It never deletes native items or changes their IDs.
