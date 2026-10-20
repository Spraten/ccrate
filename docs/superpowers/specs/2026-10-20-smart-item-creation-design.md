# Smart item creation, custom fields, and related items

**Status:** Draft for product review  
**Date:** 2026-10-20

## Purpose

Make adding similar equipment faster while retaining per-unit identity, storage, and recovery safety. Add optional packaging and custom metadata, connect associated items without implying physical containment, and keep the existing OCR helper available during item creation.

The approved direction is:

- Suggestions use active items from the same collection and selected equipment type.
- Selecting a suggestion copies shared model details; serial number and unique item state stay new/blank.
- Packaging and custom fields can be viewed and edited after creation.
- Related-item links are symmetric, removable from either side, non-hierarchical, and can connect multiple items.
- Homebox remains the inventory authority. C-Crate stores only feature-specific notes and relationships.
- Remove template UI controls while preserving existing saved template data.

## User workflow

### Create an item from a similar item

The member selects an equipment type and enters a name. C-Crate suggests active items from the same collection and type, matching the entered text. Suggestions can be navigated with the keyboard and selected explicitly. Typing alone does not copy values. The image-based “suggest name” behavior is removed.

Selecting a suggestion fills the new item’s name, manufacturer, model number, tags, and generated model code. The manufacturer serial number remains blank and is entered for the new unit. The selection does not copy the source item’s serial number, description, photo, location, condition, status, notes, or other individual state. The member can edit copied values before saving.

### Packaging

The optional **Device Packaging** field offers: **Original Packaging**, **No Packaging**, **HardCase**, **Softcase**, **Bag**, and **Misc**. A blank field means unknown or not recorded. “No Packaging” is an explicit value. The field is visible and editable on the saved item detail page.

### Custom fields

The create form contains a table with **Name**, **Value**, and **Note** columns and an add-row control. Values are text, and each item has at most one row per field name. Name and Value are stored using Homebox’s native custom fields. C-Crate stores the corresponding Note and displays/edits it alongside Name and Value on the saved item detail page. Inventory search includes custom-field values, including barcode and tracking values.

### OCR helper

The existing OCR popover is available within the add-item popup. It retains its current camera scan, edit, and copy flow. OCR text is not automatically applied to form fields; the member chooses what to copy. The application continues to use its existing single OCR popover and camera workflow.

### Related items

The member can link one or more existing items or stage one or more new related items, such as a controller, battery, or case. A staged related item defaults to the main item’s location, which can be changed independently. Its creation occurs only after the main item succeeds, and the relationship is added after the related item is created.

Links appear on both item detail pages and can be removed from either side. They do not change either item’s location or parent/child containment. If the main item save succeeds but a related-item create or link step fails, the main item remains saved and C-Crate offers a retry for only the failed step. Recovery must check whether a create or link already completed before retrying, to avoid duplicate items or links.

## Data ownership and integration

Homebox remains authoritative for item identity, collection membership, access rules, photos, locations, status, history, packaging, and custom field names and values. C-Crate stores custom-field Notes and related-item links in collection-scoped storage, keyed by stable Homebox item IDs. Renaming an item does not break a relationship. Links cannot cross collections.

Related-item links use a distinct non-hierarchical relation; Homebox parent/child location structure continues to mean physical containment. Removing a link from either side removes the same relationship from both views.

Custom-field Notes must be associated with the corresponding item and field robustly, including when a field’s displayed value is edited. Enforce one row per field name per item, with validation that handles case and whitespace consistently. Preserve Homebox field IDs and values when editing unrelated item data.

Selecting a model suggestion copies only name, manufacturer, model number, tags, and model code. New model-generated IDs continue to use the existing assignment mechanism and its current recovery guarantees. Do not alter existing IDs as part of this feature.

Remove template create/apply/manage controls from the UI. Keep existing template records and backend data intact; removing this UI must not delete or migrate saved template data.

## Failure handling and recovery

- An uncertain main-item create must use the existing request identity/status recovery path before any retry; never create a second main item automatically.
- A staged related item is created only after the main item is confirmed successful. If its create status is uncertain, query status before retrying.
- A failed relationship write can be retried idempotently. The user sees which step failed and can retry that step without repeating successful creates.
- If an item or relation target becomes unavailable, show an explicit unavailable state. Never redirect a link to a different item based on name matching.
- If Homebox rejects a custom field or packaging update, preserve the user’s form input and show the error; do not report a successful save.
- If OCR is unavailable or camera access fails, the item form remains usable and the current OCR error/recovery behavior is shown.

## Permissions and search

All item reads, writes, and collection boundaries continue to follow Homebox authorization. C-Crate relationship and note operations must verify the current user can access the associated item(s) and the collection. Related links cannot reveal an inaccessible item; show only what the member is authorized to see.

Inventory search matches custom-field values in addition to existing searchable fields. Search results must preserve current item-level permissions and link to the native item record. Barcode/tracking values are searchable but do not replace the native item ID or generated ID.

## Scope exclusions

- No automatic copying of photos, descriptions, serial numbers, status, notes, condition, or location when selecting a suggestion.
- No automatic form filling from OCR output.
- No change to existing IDs or QR destinations.
- No physical containment changes when related items are linked.
- No deletion or migration of saved equipment-template data.

## Acceptance criteria

- Typing a partial model name offers keyboard-navigable active matches limited to the selected type and collection; explicit selection copies exactly the agreed shared details.
- Serial number remains blank after a suggestion is selected, and can be entered before save.
- Device Packaging is optional, has the six agreed values, and remains viewable/editable after save.
- The custom-field table supports adding and editing text rows; duplicate field names on one item are rejected; Notes persist and remain editable on item details.
- Inventory search finds an item by custom-field values such as a barcode or tracking number.
- OCR scan/edit/copy remains available from the add-item popup and never silently writes into form fields.
- Multiple related items can be linked, are visible symmetrically, can be removed from either side, and do not change locations or containment.
- A new related item is created only after the main item succeeds, inherits its location as an editable default, and can recover from a failed related step without duplicating successful work.
- Template UI controls are absent while saved template data remains intact.
- Existing permissions, item history, generated IDs, and QR destinations remain valid.

## Implementation boundary

The implementation should reuse existing Homebox APIs and C-Crate create/recovery flows. It should add only the smallest collection-scoped persistence needed for Notes and related-item links, plus the UI/API integration required for suggestions, editable packaging/custom fields, OCR access, and related-item recovery. Exact schema and API changes belong in the implementation plan after this spec is approved.
