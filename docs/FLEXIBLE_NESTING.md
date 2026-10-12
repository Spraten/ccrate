# Flexible nesting

Status: published October 6, 2026 as `native-20261006T210239Z`, with the
verified hierarchy backend and both selected frontend releases.

The native entity parent edge is the authority. An item or location has zero or
one parent, and that parent can be another item or location. A room can contain a
vacuum directly, a box can contain a shelf, and rooms/shelves/bins can continue
below the Cage without prescribed levels. Names and categories do not determine
which entities can contain other entities.

Both interfaces provide **Inside (optional)** and **Add inside** actions. Parent
choices show the complete mixed path. Editing and moving preserve the native UUID,
metadata, attachments, QR identity, and every child's immediate parent. Returning
equipment can retain its assigned parent, select another item/location, or clear
its parent. The existing custody, kit verification, notes and durable recovery
workflow still applies. CSV review supports the same optional parent; unmatched
source parent names require explicit review rather than silent reassignment.

The pinned backend overlay fixes the native child-sync move bug, removes the
10-level tree cap, includes item ancestors of locations, and returns the actual
ancestor type for breadcrumbs. All native create, template-create, PUT and PATCH
parent writes validate tenant ownership, active immediate parents, self/descendant
cycles, and cyclic saved ancestry. A shared writer lock prevents concurrent
opposing moves from creating a cycle. PATCH accepts `clearParent: true`; omitting
`parentId` retains the old PATCH behavior. Do not combine `clearParent` with a
nonempty parent. The template endpoint's HTTP validator and published JSON
contract also allow a missing/null parent.

Builds copy the pinned upstream checkout into `work`; they never edit upstream.
Go is locally pinned by `docs/go-toolchain-install.json`; no system toolchain is
replaced. The original binary and selected frontend must be retained for rollback.
Terminal static assets also come from `work/kiosk-ui-current`, selected with the
same release, so later source edits do not appear before their backend is ready.
Backups include the backend overlay and the original operational database.

Validation uses disposable native instances, simulated browser/hardware fixtures,
and a private copy of the real SQLite database. No demo records or physical prints
are needed. `deploy/verify-nesting-api.py` exercises mixed 71-level paths, all write
routes, archived/foreign parents, contents/metadata and concurrent cycles.
`deploy/verify-nesting-shadow.py` checks exact native inventory/member fingerprints
and database integrity against a private clone. Run isolated UI verification with
`HOMEBOX_VERIFY_NATIVE_BINARY` pointing to the staged binary. The deployed release passed 218 fixture unit tests, 9 native API scenarios,
36 isolated integration checks, 8 Terminal browser scenarios, and 26 live read-only
checks. No added TypeScript diagnostics; 43 pre-existing upstream diagnostics
remain. The cutover and final live fingerprint both preserve the exact existing
2 equipment, 4 locations and 2 members. No physical prints or live fixture writes.

The live collection was read without mutation on October 6: it contains both
**The Cage** and **the Cage** beneath **Storage Room**. Preserve both unless the
user explicitly requests consolidation; similar names do not imply duplicate data.
