# Equipment Kiosk Architecture Proposal

Status: proposal awaiting user review, 2026-10-02. No operational database, kiosk workflow, catalog, map model or production deployment has been implemented.

## Recommended Boundary

Keep Homebox unmodified as the inventory authority. Add one small Ops service that serves locally bundled touchscreen UI assets and owns custody, transaction history, kiosk sessions, kit verification, map layouts and an offline product lookup module. Separate logical modules need not be separate network services or containers.

Homebox holds inventory identity, descriptive metadata, storage hierarchy, attachments and maintenance records. Ops references its entity UUIDs using the supported API. The product catalog contains product types and barcode aliases, not owned assets.

## Decisions Required

### DEC P001 Homebox integration boundary

Question: keep Homebox plus a companion application, or customize a Homebox fork?

Companion advantages: independent touchscreen workflows, fewer upstream merge conflicts, clear inventory/operational ownership. Costs: API failures and consistency between stores must be handled. A fork gives tighter internal access but increases migration and maintenance work. Recommendation: companion using supported APIs. Users get a purpose-built terminal and retain Homebox for inventory administration. This is a recommendation, not approval.

### DEC P002 Operational and map storage

Question: store custody, durable events and map geometry in an Ops SQLite database, or encode them in Homebox fields/attachments?

SQLite advantages: transactional batch checkout, uniqueness constraints, clear event history, migrations and querying. Costs: another store to back up and reconcile. Homebox fields/attachments reduce the number of stores but offer poor atomic transaction/history semantics and awkward map updates. Recommendation: a separate Ops SQLite database with versioned migrations; catalog as a replaceable local dataset plus separately preserved curated edits. Users would see reliable checkout history and editable maps; administrators would back up both databases. Approval required before schema implementation.

### DEC P003 Deployment

Question: native user/system services or containers for the prototype and final kiosk?

Native advantages: fewer runtime layers, straightforward logs and USB access, no container runtime currently installed. Costs: dependency packaging and service updates must be disciplined. Containers improve isolation and bundling but add daemon, device mapping and image maintenance. Recommendation: prototype with native executables and a locally hosted UI; choose final boot service and network exposure after hardware proof. The current loopback baseline is a reversible test process only.

The next hardware checks can proceed without choosing badge/PIN, returns, kit rules or map editing UX. Production service installation and operational data implementation depend on the decisions above.

## Suggested Repository

```text
inventory-system/
  kiosk/          touchscreen UI and scan adapters
  ops/            one service with workflow, inventory adapter, map and catalog modules
  catalog/        import format, provenance, licenses and dataset manifests
  deploy/         versioned packaging, service files, backup and recovery scripts
  tests/          API contracts, workflow, offline and hardware acceptance
  docs/           decisions, current state and phased feature plans
  vendor-manifest/ pinned upstream versions and checksums
```

Keep upstream source in an explicitly pinned checkout or source archive for inspection; do not copy it into the application's own source tree as a fork. Keep mutable data, secrets and build outputs outside source control. This layout is proposed; the phase0 folder is not a committed final layout.

## Integrity and Failure Behavior

The Ops database and Homebox API cannot share one SQLite transaction. Proposed handling: commit an operational transaction plus pending inventory updates in Ops, send idempotent updates through an outbox, and show failed/pending synchronization explicitly. Do not present complete checkout success before the approved success criteria are satisfied. Define this behavior with the user before checkout implementation.

Batch checkout needs atomic eligibility and custody changes in Ops, idempotency keys, duplicate-scan handling, and correction events rather than silent history edits. All kiosks would use one Ops authority if multi-kiosk support is later approved. Do not build distributed synchronization now.

Give every field one owner. Homebox owns inventory metadata; Ops owns operational state. If Homebox admins can move or delete assets outside the kiosk, reconciliation must surface conflicts. Mutation WebSocket messages can invalidate a cache, but must not be treated as guaranteed durable event delivery.

Store home location separately from temporary physical location and custody if the return policy needs it. Keep kit manifest membership separate from storage containment unless a later approved design demonstrates that one relationship suffices.

## Hardware and Offline Considerations

The observed Pi 4 offers more headroom than the handoff's Pi 3, but target the real 800 by 480 screen. Avoid Electron and needless microservices. Bundle JavaScript, fonts, QR decoder, images and documentation locally. Begin camera benchmarking around 640 by 480 and 10 to 15 FPS, then measure decode latency and CPU with browser and services active.

Browser camera APIs need a secure origin: localhost qualifies on the Pi, while a plain HTTP LAN IP usually does not. Any remote browser camera workflow needs a deliberate TLS/origin decision. Test scanning through the actual kiosk origin.

USB enumeration is verified; capture, touch accuracy and print quality are not. Use a scanner abstraction for webcam, keyboard wedge and manual fallback. Printing should be behind a small adapter so SUPVAN driver behavior does not contaminate inventory transactions.

The Pi has no detected RTC. Offline timekeeping requires a reviewed strategy, and the UI must expose clock uncertainty. SD card storage is a single point of failure; consistent backups and demonstrated restore are required before real inventory use.

## Major Risks and Next Phase

1. Intermittent SSH connectivity: investigate before relying on remote maintenance.
2. Printer driver remains unbuilt and untested on ARM64; hardware proof comes before label-dependent enrollment.
3. Internet-backed Homebox barcode lookup cannot serve the offline catalog requirement; licensed local product data and coverage must be evaluated separately.
4. Cross-store consistency and external Homebox edits need explicit ownership and failure rules.
5. The pinned API schema has drift from source routes; verify runtime contracts.
6. Touch, camera load, QR readability and recovery after unplug/reboot remain untested.

After architecture feedback, Phase 1 should verify touchscreen input, browser at kiosk resolution, camera frames and QR decoding, and one controlled printer diagnostic/test label. Stop at that checkpoint before implementing sophisticated workflows.
