# Equipment Kiosk Architecture

Updated 2026-10-02. Approved direction: unmodified Homebox with a companion interaction layer, keeping as much as possible native to Homebox. See DEC 003. Extra persistence and final deployment are not approved.

## Approved Boundary

Homebox remains the inventory source of truth. The companion makes scanner and touchscreen workflows convenient, translates actions into supported API calls, and displays the resulting Homebox state.

Use native entities, location hierarchy, custom fields, entity types, templates, attachments and maintenance wherever they satisfy the requirement. Do not patch upstream code, write Homebox database tables directly, or maintain a second authoritative inventory.

A small server adapter may protect credentials and coordinate API calls; this does not imply a separate Ops database. Temporary session/cart state can remain in memory unless an approved recovery requirement demands otherwise.

## Native Capability Review

| Feature | Native-first approach | Question still to resolve |
|---|---|---|
| Search and asset overview | Entities, metadata, parent paths | Required search fields and filters |
| Enrollment | Entity creation, full metadata update, templates | Offline product lookup is a demonstrated gap |
| Locations and moves | Location entity types and parentId | Home versus current location semantics |
| Condition | Structured native custom fields | Vocabulary and transitions |
| Inspection | Maintenance records and attachments | Date validation and routing rules |
| Kits | Evaluate native relationships and templates | Manifest membership versus storage containment |
| Checkout | Evaluate native fields and APIs | Atomic batches, conflicts and durable custody history |
| Workshop map | Evaluate attachments/fields for layout | Editing and concurrency |
| Labels | Native QR/label rendering with hardware adapter | Namespace, content and printer transport |

These are investigation directions, not confirmed implementations. An overwriteable field is not a durable transaction ledger. When Homebox cannot meet a requirement safely, demonstrate the gap and review the smallest companion-only extension before implementing extra storage or changing the intended workflow.

## Integrity and Failure Behavior

Preserve unrelated metadata in full PUT requests and use PATCH only for supported fields. Runtime contract tests must address the source/schema differences identified during reconnaissance. Mutation notifications can refresh UI caches but do not constitute durable history.

Several Homebox API calls do not automatically form an atomic batch. Before checkout implementation, verify conflict handling, safe retries, partial-failure recovery and accountability. Do not claim custom fields alone solve those requirements.

Homebox remains authoritative for every supported field. Future caches must be disposable. Additional companion data must be scoped to reviewed native gaps.

## Proposed Source Organization

```text
inventory-system/
  kiosk/          touchscreen interface and scan adapters
  companion/      Homebox API adapter and workflow/hardware coordination
  deploy/         packaging and recovery
  tests/          API, workflow, offline and hardware acceptance
  docs/           decisions and current state
  upstream/homebox/ pinned unmodified Git submodule
```

The desktop Git repository currently contains reconnaissance documents, the probe and pinned upstream source. Mutable baseline files and secrets remain ignored by Git. Logical modules need not become separate services.

## Hardware and Offline Considerations

The Pi 4 has approximately 4 GB RAM and an 800 by 480 display. Bundle UI assets and scanner code locally; benchmark camera decoding with browser and services active. USB enumeration is verified, but touch input, camera capture, QR decoding and print quality are not.

Homebox retail barcode lookup calls Internet services, so offline enrollment needs a local alternative. Dataset provenance, licensing and storage remain future decisions. Product records must stay distinct from owned assets.

Use a suitable browser origin for camera access; localhost on the Pi is appropriate for initial tests. The printer hidraw device is root-only: review scoped USB permissions rather than running the kiosk as root. No hardware RTC was detected; offline timekeeping and tested backups remain unresolved.

## Deployment and Next Checkpoint

Native executables and locally served UI are still the suggested prototype approach. Containers remain an alternative; boot services, network exposure and TLS are undecided. The current baseline is a reversible loopback test process.

Next: Phase 1 hardware proof for touch, camera capture and decoding, printer diagnostics and one controlled test label. Demonstrate findings before implementing workflows. Resolve persistence when a feature exposes a specific Homebox limitation.
