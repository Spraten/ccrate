# Multiple workshop room plans design

Status: proposed design for written review, October 7, 2026. Parent scope and constraints: [Workshop redesign](2026-10-07-workshop-redesign-design.md). Depends on the connected map/storage stage; usable independently of shelf checks.

## User workflow

A room picker shows named floor plans within the selected native collection. Managers can create an empty plan, rename its drawing title, and optionally link its root to an existing native location such as Storage Room or the Cage. Creating a plan does not create a native room. Optional native location creation remains a separate confirmed operation. A plan may represent an overview or an inset such as a Cage plan, so room plans need not describe disjoint physical spaces.

Selection by item/location starts from native UUID ancestry. Prefer the nearest linked ancestor, then present all drawings for that ancestor across plans. Auto-open only when there is one valid match; multiple matches show plan names, native paths and drawing captions. Users can explicitly switch plans without changing native containment. A saved bookmark carries a room-plan UUID and optional entity/drawing UUID, never a name.

Plan root links describe what the plan represents. New storage links must be that root or a descendant through the mixed hierarchy. Unrooted plans can link any active location in the collection. If a native move makes a previously linked drawing fall outside its root, preserve it, mark the mismatch for review and do not treat it as valid placement until the manager confirms a compatible root or changes its map link. No automatic native move follows a drawing move.

## Data and migration

Retain the existing private companion database and a collection-wide revision for conflict detection. Introduce document version 2 with `rooms`: each entry has stable room-plan UUID, optional `location_id` root link, name, width, height, unit `ft`, approximate flag and its drawing objects. Drawing-object UUIDs remain unique across the collection. Each plan retains 4–200 ft dimensions and at most 200 objects. Set a reviewed initial collection limit of 20 plans to bound reads; raising it is a later compatibility decision.

Treat the current unversioned single-layout document as version 1. Read it through a version-2 view containing exactly one room without writing the database. Derive that room's stable UUID with UUIDv5 using the collection UUID as namespace and `workshop:legacy-room` as name. Preserve every existing object UUID, location link, caption, coordinate, rotation, unit and approximate flag; leave its native root unlinked rather than guessing from its name. The first explicit manager save stores version 2 atomically and increments the existing revision exactly once. Empty collections remain empty. Reopening/restarting does not create another room or repeat migration.

Before writing, both clients must understand version 2. The API returns explicit schema version; saves with an older client version are rejected with a reload message. Release the server and both clients as a matching bundle. Do not retain a write-capable legacy single-room endpoint that could overwrite all other plans. Existing entry URLs open the previously selected valid plan or the first saved plan, and removed/inaccessible UUIDs show a chooser instead of silently choosing by name.

Legacy native-field map geometry is preserved untouched, available through its existing supported read/review path. Its integer grid is not feet, so no automatic conversion to a companion room is allowed. This stage adds no cross-store synchronization.

## Editing and history safeguards

Room switching keeps a dirty draft scoped to its plan and collection. Explicit Save saves the collection revision atomically; another session's save causes a conflict with the draft retained. Navigation away and identity changes retain the Stage 1 guards. Renaming the plan title never renames its linked native location; native location renames update the secondary root label on refresh.

Moving a drawing between plans preserves its ID and location UUID. The manager chooses the target plan and coordinates; reject invalid bounds or root incompatibility before saving. No automatic rescaling, copying, cropping or native relocation occurs. Plan removal is permitted only for an empty plan, after explicit confirmation; otherwise explain that drawings must first be moved or individually removed. Removing a plan does not delete native locations, attachments, inventory or legacy fields. These actions are implemented only after the required confirmation and separate destructive-action authorization rules are satisfied.

## Architecture and verification

Extend `ops/workshop.py` persistence/version validation and the focused read/query unit from Stage 1. Extend the existing desktop and Terminal adapters with a room picker, scoped drafts and selection parameters. Existing authenticated context, same-origin management writes, request recovery and revision checking remain mandatory; native UUIDs from another collection cannot be linked.

Prove transaction/restart-safe migration against populated and empty fixture databases; compare all old drawing values and native metadata before/after. Test stale clients, two-session saves, cross-room duplicate UUIDs, invalid bounds, root mismatches after native moves, ambiguous representations, dangling bookmarks and collection switches. Disposal-instance browser tests must find the same item in both interfaces and preserve a dirty draft while switching rooms. Verify a matching rollback bundle can restore the selected application artifacts without silently reverting completed inventory or check history; never let an old writer truncate version-2 data.
