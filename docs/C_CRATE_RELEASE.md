# C-Crate release — October 7, 2026

The native Homebox header and Equipment Terminal now display **C-Crate**. The
native header shows connection-only Printer and Camera status and opens a
read-only details panel. The two existing desktop shortcuts received display
text updates; their commands, icons and layout were preserved.

Transaction `20a9a6ff-9fd4-48c9-b9d6-decfd239ff53` committed and passed live
verification. The selected overlays are
`homebox-ui-releases/header-c-crate-prepared/public` and
`homebox-ui-releases/terminal-c-crate-prepared/kiosk`. Native backend
`0.26.2-caci.2` and binary (SHA-256
`e8502bd85b18ff14d67172dffb0006e06504eddbe38a7c3d643bdee2088dd15a`) were
unchanged. All three services are active. A prior transaction attempt rolled
back and passed health checks; its failure cause was not established.

Authenticated live smoke verified the manager context, C-Crate header, status
controls and panel, Terminal branding, and selected assets. It reported zero
browser errors, blocked mutations and physical prints. The only actual write was
login; two native settings requests were synthetically fulfilled by the smoke
guard. Inventory remained 1 equipment, 6 locations and 3 members. The same
disposable native database passed baseline → candidate → baseline compatibility
checks. Verification also includes 221 baseline and 222 candidate unit tests,
12 device checks, 8 Terminal checks and 12 transaction/preparation fixtures.

The baseline full desktop suite is **not a pass**: 38 checks passed before the
existing Recovery inspect-operation-row timeout. Its outcome remains partial;
the separate same-database compatibility result passed. The release gate was a
fresh bounded source/static and rollback validation. It does not establish
historical companion/build provenance, and the earlier immutable handoff was
left unchanged. A private backup stayed on the Pi; no physical printing or
inventory mutation occurred.

Receipts: [live release verification](../work/c-crate-release-preparation/live-release-verification.json),
[final review](../work/c-crate-release-preparation/final-review.md),
[authenticated live smoke](../work/c-crate-release-preparation/candidate-transaction-live-smoke.log),
[transaction receipts](../work/c-crate-release-preparation/transaction-receipts.jsonl),
and [same-database compatibility](../work/c-crate-release-preparation/same-database-coordinator.log).
