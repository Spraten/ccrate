# Guided workshop shelf checks design

Status: proposed design for written review, October 7, 2026. Parent scope and constraints: [Workshop redesign](2026-10-07-workshop-redesign-design.md). Uses Stage 1's native path, contents and code-resolution semantics; multiple room plans are optional.

## User workflow and scope

A manager selects or scans an active native shelf/location, chooses Direct contents or Include nested contents, and starts a check. Direct contents is the default. The scope is frozen for that draft and shown on every observation screen. Support any active native location, regardless of its display name or Storage kind; checking equipment containers directly is outside this stage.

Capture the expected active equipment UUIDs, quantities and their recorded paths at start. For nested checks, traverse the full mixed hierarchy and deduplicate equipment UUIDs. Show current borrowing separately: equipment checked out at the snapshot is not expected to be physically on the shelf, although it remains assigned there. Kit containers and components follow ordinary native containment for this check; it does not certify checkout/return kit completeness.

The manager scans individual asset identities or marks a listed item as visually observed. Reuse existing scanner normalization; manufacturer codes selecting multiple assets require explicit identity resolution. A repeated observation of the same UUID does not increase the count. For quantity-one items, observing the UUID records one observed unit. For other quantities, require an explicit nonnegative integer tally; scanning selects the record without inventing a count. Expected and observed quantities appear separately, and differences are reviewable. Unknown, archived or foreign-collection items produce a review message and never create or attach equipment. Scanning a different location does not change the active shelf.

The review groups equipment into Observed here, Not observed, Checked out, and Unexpected here. An observed checked-out item appears under Observed here with a custody-conflict flag, not under a category implying its loan has ended. Unexpected items show their current assigned native path. “Not observed” is an observation outcome, not a new Missing equipment condition. Pending native operations are visible so a manager can distinguish uncertain history from a physical discrepancy.

Finish saves the check and discrepancy notes only. It never changes native parent, condition, custody, kit manifests or item quantities. Follow-up actions open existing native move/condition/return workflows and require their own confirmations. Cancellation keeps an abandoned draft record with its last saved observations; completed checks are immutable.

## Durable data and identity

Use a focused shelf-check store in the existing private companion SQLite operational area; do not create a duplicate inventory directory. Each check has stable UUID, collection UUID, initiating native manager UUID, native location UUID, scope, start time, state, revision, expected-item snapshot, observations with UUID/method/observed quantity/timestamps, notes and completion/cancellation time. Expected and observed item IDs reference Homebox. Snapshot names/paths describe the time of the check, and current record links resolve by UUID. Preserve the original start snapshot separately from the latest reviewed comparison so refresh does not erase evidence of changes during a check.

States are `draft`, `completed`, and `cancelled`; only a draft accepts changes. A check owns a server-side revision. Each confirmed start/update/finish/cancel has a durable request key and result lookup so lost responses or repeated clicks cannot create duplicate checks or observations. A replay returns the committed result for the same intent; another payload with the same key is rejected. No automatic retry of an uncertain write. Unsaved visual changes are marked until confirmed saved.

Management access is required for starting, observing, finishing and viewing detailed checks. A draft belongs to its initiating manager; another manager may view it but cannot silently adopt the actor or modify it. If that manager loses access, their draft is suspended. Cancellation by another authorized manager is a separately confirmed action recording that manager as the cancelling actor. Native user removal preserves historical actor UUID and displays a former-member label.

Check records and observations stay on the Pi and enter its existing private backup inventory. Retain completed/cancelled check history until explicitly authorized cleanup; no automatic purge is introduced. Arbitrary image uploads, discrepancy emails, scheduled audits and exports are outside this stage.

## Changing inventory during a check

Before completion, re-read the location, scoped active equipment, native parent/quantity/version values and current custody. If relevant membership, parent, quantity, archive or custody values differ from the reviewed snapshot, require Refresh review before accepting completion. Preserve observations and the original start snapshot; refreshed rows show what changed, including new expected items and items no longer assigned. Rename-only changes refresh displayed names without invalidating an observation identity. Deleted/archived target locations suspend completion and keep the draft readable for review/cancellation.

Completion records the exact latest reviewed membership/custody fingerprint. Use the existing application write lock while checking that fingerprint and committing local history to prevent competing companion changes. Native changes outside that lock can still race; record the reviewed versions and completion time, present the check as a point-in-time observation, and do not claim an atomic native inventory audit. No native inventory write is part of completion.

## Architecture and acceptance

Add a focused shelf-check domain/persistence unit using standard Python and SQLite, with shared business operations called by the existing desktop and Terminal API adapters. UI adapters consume the same grouped review and revision values. Reuse existing context, manager checks, scanner, hierarchy/status reads, per-request recovery pattern and native record links. Changes to native inventory occur only through existing services.

Fixture checks cover direct versus deep mixed descendants; expected checked-out items; physically observed checked-out items; repeated scans; quantity-three equipment requiring a tally and rejecting negative/noninteger tallies; multiple manufacturer-code matches; unknown/foreign/archived records; changed parents/quantities/custody; original snapshots retained after refresh; deleted shelf; renamed records; stale draft revisions; restart/lost reply; cancelled/completed immutability; revoked access; and former initiating managers. Assert every start/observe/finish path causes zero native mutations and zero physical outputs.

Disposable browser verification covers touch scanning with synthetic frames, manual observation, pause/reopen, refreshed review, cancellation and completed-history viewing in both interfaces. Test backup inclusion and restoration using temporary operational data. A physical shelf check and camera/label acceptance require a person at the workshop; simulated frames do not establish that result.
