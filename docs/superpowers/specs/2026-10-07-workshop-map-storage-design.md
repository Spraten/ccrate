# Connected workshop map and storage design

Status: proposed design for written review, October 7, 2026. Parent scope and constraints: [Workshop redesign](2026-10-07-workshop-redesign-design.md). Covers six accepted feature candidates, including extensions of existing Terminal behavior.

## User workflow

Search by native name, asset code or existing supported identifying metadata, or scan an existing equipment/location QR. Use the existing code normalization and inventory resolution; never navigate to an arbitrary scanned URL. Ambiguous results show distinguishable records with their full native path and visible identity. An unknown/manufacturer-only code offers the existing search workflow; map lookup never creates equipment.

Selecting equipment shows its native record, full mixed item/location path, assigned storage, condition and borrowing status. Selecting a location shows its parent, immediate child items and locations, and controls to continue into those children. Users can open the native item/location and return to their map selection. A location tree selection and a drawing selection resolve to the same native UUID. Drawing-only objects have their own identity and are clearly labeled as such.

“Show on map” resolves the nearest active linked location in the target's native ancestor chain. It highlights the exact selected location when drawn, or the containing mapped location otherwise. For equipment, an exact match requires its immediate native parent to be the linked location; an intervening box or other item is shown in the full path and keeps the highlight classified as a containing area. Examples: “Stored on Rack 1-A; highlighting Rack 1” and “Assigned storage: Storage Room / the Cage / Rack 1 / Rack 1-A.” A checked-out item also says it is checked out; a home-storage highlight does not imply current physical presence.

With multiple drawings linked to the same nearest location, show an explicit choice rather than picking the first. Missing placement shows the real path and “No map placement”; archived/deleted/foreign links are unavailable and never redirected by name. A malformed or cyclic path produces a review message and preserves the saved layout.

## Rack front view

Selecting a location with native Storage kind `Rack` offers a front view of its immediate children with Storage kind `Shelf`. Other child kinds remain reachable in a list, including mixed item containers. Shelf selection shows its immediate children and offers a subtree equipment view; navigating never changes native parents.

The view is schematic, not a claim about measured shelf elevations. Numeric Storage codes order shelves numerically from bottom to top; duplicate numeric values break ties by name then UUID. Nonnumeric or empty codes appear in a clearly labeled list unless the manager supplies an explicit order. Optional order is a versioned `Workshop shelf order` native text field on the rack, containing shelf UUIDs bottom-to-top; it changes presentation only. Existing native fields are preserved. Newly added shelves absent from an explicit order appear in an unordered section, and stale references are reported rather than assigned to another shelf.

Use the same order and labels in both interfaces. A photo, native name, short code and full path help users recognize a shelf. Do not infer physical levels from names such as Rack 1-A.

## Map setup checklist

Report four actionable states using the current companion layout and native hierarchy: active locations without map coverage; drawing-only objects; links to unavailable locations; and locations with multiple drawing representations. Map coverage means the location itself or an active ancestor has a valid link. A bin represented through its rack is “Covered by Rack 1,” not an error. Show exact placements separately from containing-area coverage.

Choose an existing location using its full path and UUID, then place/link the drawing. Creating a new location is an explicit native create, retaining existing duplicate-name and recovery behavior. Similar names never imply the same location. Locations needing legacy native-map field review are reported separately; current-layout setup never imports, removes or rewrites legacy geometry.

Linked drawing labels display the current native location name by default. An optional drawing caption is visibly secondary. Preserve existing stored drawing names as captions during upgrade; do not rename native locations to match them. Native rename/move refreshes labels, breadcrumbs, coverage and selection in both interfaces. Detect dirty geometry before a hierarchy refresh; retain the geometry draft while updating the native-reference view.

## Location recognition photos

Show existing native photo attachments for the selected location, primary photo first and other photos in a gallery. Preserve aspect ratio and provide text alternatives. Missing/unavailable images leave the native name and path usable. Attachment fetches retain native authorization and collection boundaries; private filesystem paths are never returned.

Photo management uses the existing native location photo editor, linked from the map; the Terminal offers the native editor link and displays saved photos after refresh. This stage does not introduce a second upload/editor workflow or media store. The pinned native location page already renders photos, and native entity attachment services permit location attachments.

## Status and contents

The selected area defaults to directly assigned active equipment. A labeled “Include nested contents” toggle includes every active descendant item through the full mixed hierarchy, deduplicated by UUID. Checked-out items remain in their assigned storage list, labeled as checked out. Archived equipment is excluded by default and accessible through the existing native record.

Show total assigned equipment, currently checked out, available for checkout, and needing attention. Counts describe equipment records, not a sum of quantities. Available requires no current custody and no existing checkout blocker; Ready alone is insufficient. Needing attention includes non-Ready or Unreviewed equipment. Counts can overlap and are labeled accordingly; a checked-out Broken item contributes to both. Map badges and text filters use the selected scope and share the same definitions in both interfaces. Borrower details follow existing loan visibility rather than broadening access. Color overlays are optional and off by default; selected-area text counts remain available without enabling them.

Refresh on open, selection, explicit refresh and return to a visible page; while visible, refresh status every 30 seconds, matching existing loan views. Show last refresh time. If status cannot be refreshed, mark it unavailable/stale and never show cached equipment as currently available. Layout editing drafts survive read refreshes.

## Architecture and failure handling

Keep the companion document shape in this stage: name, dimensions, unit, approximate flag and objects. Retain the existing 4–200 ft dimension limits, 200 drawing-object limit and revision conflict checks. Drawing-object IDs and native location IDs are distinct.

Add focused shared read/query logic alongside `ops/workshop.py` for hierarchy resolution, selection, coverage, contents scope and status definitions. Both API adapters call it with their authorized client and custody context. Extend the two existing UI adapters and their local assets without moving unrelated loan/import/user workflows. Reuse native attachment APIs, `ops/hierarchy.py`, `ops/conditions.py`, the custody ledger, QR resolvers and native write journals. Shelf-order updates use a metadata-preserving native update with stale-version checks and durable uncertain-result recovery.

Explicitly separate Browse and Edit modes in both interfaces so selecting or panning cannot move a drawing. Retain existing Terminal zoom/pan/fit, quarter-turn controls and undo; ensure rotation is rendered consistently with saved bounds. Desktop retains its established form/drag editing while receiving the same navigation semantics and numeric alternatives. Unsaved changes prompt before leaving; stale layout revisions preserve a draft for review rather than overwrite another save. Account/collection changes suspend drafts under their original identity.

## Acceptance and verification

- Fixture search/scan resolves the same item, map target and path in both interfaces; foreign/ambiguous/unknown codes select no unintended entity.
- A Cage → Rack → Shelf → item path highlights the rack as a containing area until the shelf is explicitly mapped; an item container between item and shelf is retained in the guidance.
- Rack front view handles numeric, nonnumeric, duplicate and missing codes; explicit order survives rename/move and never reparents children.
- Coverage correctly handles intentionally indirect bins, unplaced locations, missing links, multiple representations, legacy fields and distinct similarly named Cage locations.
- Status counts deduplicate deep mixed descendants and distinguish Ready-but-held, blocked quantity, Unreviewed, archived and unavailable equipment.
- Native photos are visible only with authorized access and retain their proportions; photo management returns to the selected map location.
- Fixtures exercise revision conflicts, interrupted native order updates, refresh with unsaved geometry and revoked/changed account context.
- Disposable browser verification at 800 × 480 touch and desktop dimensions covers keyboard selection, front-view drill-down, native-record return, Browse/Edit separation and long names. Existing live mutation verification scripts are not acceptance commands.

Human acceptance requires a person to recognize a real shelf/photo and follow an actual workshop path without coaching. Automated fixture success does not claim that physical acceptance.
