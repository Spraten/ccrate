# Modular Workshop editor

Open Equipment Terminal → Workshop. The saved approximate overhead drawing follows the user's supplied shop sketch. Initial dimensions are estimated as 13.5 × 21 feet and must be checked against actual measurements. The drawing contains four racks, a coffee table, a basing table, three base units, a fence and two gates. These are drawing elements, not seeded equipment or native storage records.

## Floor plan

Tap Edit layout. Select an object from the drawing or its large named button. Drag to snap in 3-inch increments, or use the four position buttons. Edit name, dimensions and position with the touch keyboard. Rotate quarter turns, duplicate a drawing object, remove a drawing, or Undo the last edit. Room settings changes the room name and dimensions. Objects must stay inside its bounds.

Add object offers racks, cabinets, workbenches, tables, fences, gates, doors, areas and kiosks. Objects are independent of the native location tree. Duplicate drawing produces a fresh drawing ID and clears its storage link; it does not clone native storage or equipment. Removing a drawing leaves its linked Homebox location and contents intact.

Zoom, Fit and Turn view adjust the presentation without changing stored physical coordinates. Save layout persists the complete drawing on the Pi. Leaving with unsaved changes asks whether to discard them. Layout saves check a revision to prevent overwriting edits made by another browser. On a conflict, reopening the Workshop loads the saved version.

## Storage locations

Select a drawing object → Edit layout → Link storage. Choose an existing native Homebox location or create one. Storage also opens the location hierarchy without selecting a drawing.

Use any hierarchy: Workshop → Area → Rack → Shelf → Bin is a suggested structure; Cabinet → Drawer and other combinations also work. Add inside a rack suggests Shelf, and inside a shelf suggests Bin. The kind selector remains editable. Location names and short codes are native metadata, not copied inventory records. Codes must be unique among active siblings, ignoring case.

For rack XYZ, shelf code 2 and bin code B, the storage view displays XYZ / 2 / B. Racks show a front view of their shelves, ordered by code with larger numbers above smaller numbers. Each shelf can contain a different number of bins. Tapping a shelf or bin opens that location. Equipment here uses the existing native equipment view; Location label uses its stable native Homebox QR.

Move this location changes its native parent, preserving the UUID, contained shelves/bins and equipment. Self/descendant moves, archived destinations and conflicting sibling codes are blocked. A stale native revision blocks an overwrite. If a response is uncertain, reload and inspect the existing location; do not create another record or blindly repeat the move. Creation uses the existing durable NativeJobs pipeline and Admin recovery.

## Storage and verification

Floor-plan geometry is private companion presentation data in work/ops/workshop.db, scoped to the Homebox group and included in cold-backup integrity/checkpoint/hash checks. Homebox remains the authority for locations and equipment. Native Homebox source is unchanged.

117 unit checks cover geometry validation, duplicate identities, concurrent saves, restart persistence, native hierarchy cycles, metadata preservation and duplicate storage codes alongside the existing regression suite. deploy/verify-workshop-editor.py verifies touchscreen position controls, rotation, duplication, undo, saved-plan reopening and touch-keyboard operation. Rack/shelf/bin navigation uses browser-only mock locations to keep live inventory empty. It writes no native sample records.

This first version edits one rectangular room, uses feet for drawing dimensions and supports orthogonal objects. Walls follow the room boundary; fences and gates are movable objects. It does not provide a construction drawing or a 3D model.
