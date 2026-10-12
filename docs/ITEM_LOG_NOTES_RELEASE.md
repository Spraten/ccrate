# Item log and notes release

Published October 8, 2026, transaction `c45325ef-2319-433d-82d1-f0425cbd6165`: `committed_C`, `verified: true`.

Native C-Crate now has an expandable item activity table beside Details, with note text, person, action and local date/time filters. Filters cover the loaded companion records, up to 100 newest requests; older activity and unjournaled native changes are explicitly excluded. Original borrowing history and native maintenance Log remain available.

Equipment Terminal now offers Add Notes to Item for an identified member. Uncertain saves preserve the original request for status-only recovery. Native and Terminal Recovery can confirm a verified saved note or cancel an unstarted note without reposting it. Author identity, native maintenance UUID and the first verified content reference remain durable.

Both selectors are `homebox-ui-releases/item-notes-20261007/{public,kiosk}`. The date in the release identifier is retained from preparation. C-Crate branding, Printer/Camera controls, the shared SUPVAN/Letter label editor and Terminal return/action switching remain present. Native binary SHA-256 remains `e8502bd85b18ff14d67172dffb0006e06504eddbe38a7c3d643bdee2088dd15a`; the existing renderer is unchanged.

Verification used isolated inventory and temporary stores:

- Full source suite: 336 tests, no skips. Frontend build: 24 routes, 43 existing diagnostics, none added.
- Actual built feature checks: four ItemLog checks, two whole Terminal page checks, one native Recovery check, 12 device checks and three focused label/System/action-switch checks. Shared setup checks are recorded separately in each receipt.
- Publisher failures: 20 fixture tests. Cold-backup helper: 12 fixture tests.
- Real same-database O→C→F→C retained a new uncertain note and an existing uncertain print. F uses the previous static trees with compatible current handlers; no private database restoration or uncertain print/create replay.

A fresh private local backup passed archive readback and integrity checks for five databases. The original live release passed health after service restart. Candidate live health verified 130 assets and both public notes markers, with zero browser errors or unexpected/blocked mutations; only authentication reached a write endpoint and two preference requests were answered synthetically. No operational test notes, inventory fixtures or physical outputs were created.

Evidence is in `work/item-log-notes-isolation/`: `verification.json`, `coordinator-release-receipt.json`, `coordinator-release-apply-receipt.json`, `coordinator-cold-capture-receipt.json` and the referenced unit/build/GUI/compatibility logs. Exact accepted raw plan SHA-256 is `2951011346f252c4f0a8f5f9c5ca397e9155391dbfef92c5bbd454fb13f4bdab`; its canonical transaction digest is distinct.

Earlier fixture attempts were superseded by the recorded verification. Physical readability, scanning and user acceptance have not been tested.
