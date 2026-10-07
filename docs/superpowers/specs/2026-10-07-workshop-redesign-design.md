# Workshop redesign: design for written review

Status: design basis for implementation planning, October 7, 2026. The user accepted all eight feature candidates, received this written design, then selected subagent-driven development. The selected execution method is preserved; the detailed implementation plans must be reviewed before product execution. Proposed defaults remain explicit below and in the stage designs so the user can correct them during that review.

## Intended outcome

People using CACI-Create and Equipment Terminal can find equipment, recognize its assigned storage, organize the map, and check a shelf against recorded inventory. Existing Homebox identities and nesting remain authoritative. The working assumption is that finding equipment and setting up storage are equally important; the user has not selected a narrower priority.

Success means an unfamiliar user can search or scan an item, follow its complete storage path, select the corresponding map representation, inspect the rack and shelf contents, and understand whether the highlighted shape is the exact destination or a containing area. Managers can identify incomplete layout setup, manage multiple plans, and record a physical check without changing inventory merely by scanning it.

## Scope and sequence

| Stage | Features | Design | Implementation plan |
| --- | --- | --- | --- |
| 1. Connected map and storage | Search/scan to map; rack front view; setup checklist; location photos; equipment status; clear destination guidance | [Map and storage design](2026-10-07-workshop-map-storage-design.md) | [Map and storage plan](../plans/2026-10-07-workshop-map-storage.md) |
| 2. Multiple room plans | Named plans and optional native room links; explicit selection among representations; preservation of existing layouts | [Multiple room design](2026-10-07-workshop-rooms-design.md) | [Multiple room plan](../plans/2026-10-07-workshop-rooms.md) |
| 3. Guided shelf checks | Scan observations; discrepancy review; resumable drafts and completed history | [Shelf check design](2026-10-07-workshop-shelf-checks-design.md) | [Shelf check plan](../plans/2026-10-07-workshop-shelf-checks.md) |

Stage 1 is usable with the current single layout. Stage 2 depends on Stage 1's location resolution and selection contract. Stage 3 depends on Stage 1's scoped inventory view and works with or without Stage 2. Each stage gets its own implementation plan and independently testable deliverable. Preserve the existing queue: approved user-management/release fixes, label editor, then workshop implementation. This request authorizes workshop design work now; it does not reorder product execution or authorize deployment.

## Shared constraints

- Homebox remains the inventory authority; preserve native UUIDs, optional mixed item/location parents, attachments, custom fields, QR payloads, loan history and native permissions.
- Preserve both distinct locations named The Cage and the Cage; never merge records because their names look alike.
- Drawing changes never change native containment. A native move or rename is a separately confirmed native operation.
- Preserve current companion layouts and legacy native `Workshop map room` / `Workshop map object` fields. No automatic conversion or synchronization between their different coordinate systems.
- Keep all runtime assets local; add no external service or dependency for these stages.
- Support the 800 × 480 Terminal with controls at least 44 CSS pixels in height, keyboard operation, visible focus, and text alternatives to the drawing and status colors.
- Derive collection, actor and permissions on the server. Desktop uses native authenticated Workshop context; Terminal retains its existing authorization model. New management writes require management access at confirmation.
- Preserve uncertain operations for explicit recovery; never automatically repeat a create, upload or physical print.
- Product verification uses disposable Homebox instances and temporary fixtures. No live demo records, physical prints, service restarts or deployment are authorized by these documents.
- Execute one Luna Medium coding task at a time; Sol High reviews architectural and risk-sensitive changes, with fixes and renewed verification before acceptance.

## Current implementation and reuse

`ops/workshop.py` stores one revisioned companion layout per collection; objects have their own IDs and optional native location UUID links. Both interfaces consume its snapshot, but `kiosk/workshop-ui.js` and `homebox-ui/overlay/lib/workshop-tools.js` render separate editors. The Terminal already provides ancestor highlighting, rack drill-down and richer layout controls. Stage 1 extends and aligns those behaviors rather than treating them as new subsystems.

`ops/maps.py` and its native-field endpoints are a separate legacy map system. Neither its geometry nor its labels can be silently treated as the current companion layout. Native location pages and attachment APIs already support photos, so recognition photos need no separate media directory. Conditions, borrowing, hierarchy validation, native write recovery and QR normalization also already exist.

## Review and next step

Review the three linked plans as one feature set alongside their designs, including the proposed defaults for shelf order, multiple representations, photo management and shelf-check scope. The user selected subagent-driven development; do not ask them to select an execution method again. After written-plan review, use the project's sequential Luna Medium implementation and Sol High task reviews in an isolated snapshot, preserving the earlier queue and separate deployment approval.
