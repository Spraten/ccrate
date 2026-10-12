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

## Saving and recovering edits

Save layout writes the complete room collection for the current Homebox group. If another browser saves first, the revision check keeps your draft from replacing that newer plan. Compare the open drawing with the saved version, copy over any changes you still need, and save again after reloading. Do not repeatedly submit a conflicted save.

Browse, Zoom, Fit and Turn view only change how the plan is displayed. They do not move a room or drawing object in saved coordinates. Review the geometry and storage links before saving a legacy plan for the first time; opening it keeps the legacy data intact, while the first successful save migrates it to the current room document format.

Drafts belong to the active Homebox group and signed-in identity. Switching group or account suspends the old draft instead of applying it to the new identity. If a save or native operation has an uncertain response, check its status and existing record before retrying; reuse the operation's original request when the status is still being recovered rather than creating a duplicate.

If a linked root location was moved or archived, the editor marks the link for review. Choose an active compatible root or deliberately unlink and relink the drawing after checking the native hierarchy. Moving or unlinking a drawing does not move the Homebox location, equipment, loan or history. Repair the link, then save the room plan.

## Storage and verification

Floor-plan geometry is private companion presentation data in work/ops/workshop.db, scoped to the Homebox group and included in cold-backup integrity/checkpoint/hash checks. Homebox remains the authority for locations and equipment. Native Homebox source is unchanged.

117 unit checks cover geometry validation, duplicate identities, concurrent saves, restart persistence, native hierarchy cycles, metadata preservation and duplicate storage codes alongside the existing regression suite. deploy/verify-workshop-editor.py verifies touchscreen position controls, rotation, duplication, undo, saved-plan reopening and touch-keyboard operation. Rack/shelf/bin navigation uses browser-only mock locations to keep live inventory empty. It writes no native sample records.

This version supports a collection of rectangular room plans. Each room uses feet for drawing dimensions and supports orthogonal objects. Walls follow the room boundary; fences and gates are movable objects. It does not provide a construction drawing or a 3D model.

## Guided shelf checks

Authorized managers can start a shelf check for a native location, scan or
visually tally expected equipment, and save notes. A scan selects an item; it
does not increase its quantity. Confirm a tally explicitly, including zero when
that is the observed count. Pause by leaving the draft saved, then reopen it
from shelf-check history. If its manager, location or current inventory context
is unavailable, the draft remains readable but suspended until review or
cancellation is possible.

The original start snapshot remains alongside the latest refreshed review.
Refresh shows changes to current membership, paths, quantities and custody
without erasing saved observations. Completion records a point-in-time review
and does not change Homebox quantities, locations or custody. Follow-up moves,
condition changes or returns must use their existing workflows and their own
confirmations. Cancellation requires confirmation and a reason; it retains the
draft and observations in cancelled history. Completed and cancelled records
are retained without automatic cleanup.

Shelf checks share the private Pi Ledger at `work/ops/ledger.db`, which the
existing deployment backup checkpoints, hashes and includes under `work/ops`.
For recovery, restore a backup only into a fresh temporary fixture first and
confirm its manifest hash and SQLite integrity before considering any separate
operational recovery procedure. Completion is non-atomic with direct Homebox
changes: the saved comparison describes the facts reviewed at that moment.
Human physical shelf and camera acceptance, plus deployment, remain separate
gates from these source and backup-fixture checks.

## Room document compatibility and rollback

Release selection for Workshop now requires format-2 bundles whose immutable provenance declares named `workshop_read_v1`, `workshop_read_v2`, and either `workshop_write_v2` or `workshop_write_disabled` checks. The named test receipt carries the digest of the exact runtime source, public static files, label assets, starter document, and native binary; the runtime source closure includes the server, Desktop and Terminal code, Python modules, and release launcher. Capability declarations without matching test-receipt evidence are rejected. A pre-v2 or truncating writer is not a compatible rollback target and must be rejected before service or selector callbacks.

The Task6 source fixture uses populated and empty legacy documents, same-named native-like locations with distinct UUIDs, linked drawings, completed Workshop receipts and an unresolved ledger operation. It injects failure after C saves, reopens selected F against the same files, and then returns F→C through the release selector engine and reopens C. Its disposable native-like rows include privacy, field, photo, loan and history sentinels; these are synthetic fixtures rather than the Homebox native schema. The helper compares full pending Ledger details and event rows across O/F/C. Replay calls and blocked physical-module imports are instrumented; the copy counter observes only four `shutil` copy functions for the three named store paths and does not establish that all possible restore mechanisms are absent. It does not perform physical output.

The browser verifier's `--case all` mode still exercises its disposable UI fixture, but those UI-only fixture bundles are not matched O/C/F releases. Its report therefore marks packaged same-store rollback as not run and compatibility as unclaimed. No fresh production-matched format-2 O/C/F packages are available in this task; these source gates and synthetic tests do not prove packaged process behavior or production compatibility.
