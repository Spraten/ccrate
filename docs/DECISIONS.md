# Project Decisions

Maintain confirmed decisions separately from proposals. Date: 2026-10-02. The companion interaction-layer boundary is approved. Authentication, status vocabulary, QR namespace, label contents, map storage and deployment remain undecided.

## DEC 001 Phased Collaboration

- Question: implement broadly or work through design checkpoints?
- Options considered: broad independent implementation; incremental implementation with user decisions and checkpoints.
- User choice: the handoff requires incremental implementation and explicitly says to stop after initial architecture reconnaissance.
- Implementation consequence: Phase 0 only; product decisions are pending, not inferred from examples.
- Revisit: user may change the collaboration process.
- Source: supplied project handoff, sections 2, 3, 78 and 86.

## DEC 002 Hardware Availability

- Question: can camera and printer tests proceed on real devices?
- Options considered: simulated devices; physical devices attached to the Pi.
- User choice: user connected webcam and printer during this session.
- Implementation consequence: USB identities were verified; Phase 1 can test real hardware.
- Revisit: yes; peripherals can be disconnected or changed.

## DEC 003 Homebox Companion Interaction Layer

- Date: 2026-10-02.
- Question: customize Homebox or build a companion, and where should inventory behavior live?
- Options considered: upstream fork; companion with independent operational authority; companion using native Homebox data and behavior.
- User choice: unmodified Homebox with a companion interaction layer that makes workflows convenient and keeps as much as possible native to Homebox.
- Implementation consequence: use supported APIs and native entities, fields, types, templates, relationships, attachments and maintenance first. Do not patch Homebox, write its database directly, or duplicate inventory as another authority.
- Additional persistence: not approved by this decision. Demonstrate a concrete native capability gap and review the smallest extension before implementing extra storage. Durable accountability must not be silently reduced to overwriteable fields or notes.
- Revisit: yes, by explicit user decision with the integration gap explained.
- Source: user's approval of Homebox with a companion interaction layer.

## DEC 004 Temporary Printer Diagnostic Access

- Date: 2026-10-02.
- Question: grant scoped temporary printer access for the hardware proof or postpone printing?
- Options considered: temporary user ACL; defer printer tests. Persistent access rules are a later decision.
- User choice: authorized sudo access using the Pi account credential.
- Implementation consequence: grant only user read/write access to the matched SUPVAN hidraw device; no permanent service or system-wide permission rule. Credential is not stored in project files.
- Revisit: yes; ACL expires on unplug/reboot and can be removed.

## Pending Architecture Proposals

- DEC P001: resolved by DEC 003.
- DEC P002: prior blanket Ops SQLite recommendation superseded; evaluate native Homebox first, then propose persistence only for demonstrated gaps.
- DEC P003: native service deployment rather than containers; final service scope/network access still pending.

See the architecture proposal for options, tradeoffs and visible effects. Do not treat these entries as user approval.

## Reversible Engineering Assumptions

- Pin v0.26.2 for source investigation and temporary baseline; final deployment version is subject to review.
- Use `/home/user/Desktop/inventory-system` as an isolated reconnaissance workspace.
- Bind the temporary baseline to loopback port 17745 with synthetic test data and private generated test credentials.
- Disable release checks and analytics in the baseline. Production configuration remains undecided.

Later decisions will be asked when relevant: badge versus PIN, session timeout, return destination, kit verification, condition/availability vocabulary, map interaction, asset display codes, permanent QR namespace, labels, backups and retention.


## DEC 005 Kiosk Home Layout

- Date: 2026-10-02.
- Question: six direct task buttons or three main buttons plus More?
- Options: six buttons; three plus More.
- User choice: six large buttons, with smaller Admin entry.
- Consequence: Check Out, Return, Find Item, Browse Stock, Report Problem and Add Equipment are directly accessible. Workflow rules remain undecided.
- Revisit: yes, during shell review.

## Prototype engineering assumptions

- Plain locally served HTML/CSS/JavaScript and Python standard-library HTTP server for a disposable loopback shell. No production runtime choice or deployment policy implied.
- Synthetic baseline account used only server-side for read-only inventory views. No production session, identity or inactivity policy implemented.


## DEC 006 Prototype Badge Authentication

Date: 2026-10-02. Options: badge only; badge plus PIN. User chose badge only. No PIN step in prototype. Badge identity source and issuance remain pending. Revisit before production.

## DEC 007 Camera Activation

Date: 2026-10-02. Options: Scan button; always-on camera. User chose Scan button. Camera starts on demand and stops on cancel or resolved inventory entity. No always-on capture. Revisit after user testing.


## DEC 008 Native Badge Identity

Date: 2026-10-02. Options: Homebox accounts; borrower records. User chose Homebox accounts, one native identity per person. Companion badge identification references current Homebox group members; it does not create a separate people directory. Badge issuance and revocation design follow separately. Revisit: yes.

## DEC 009 Operational Event Ledger

Date: 2026-10-02. Options: limited ledger; native fields with reduced history/recovery; defer. User approved a small SQLite companion event ledger for checkout/return accountability. It references native entity/user UUIDs and stores operational intent, outcomes and recovery state. Homebox remains inventory authority; no copied asset catalog or upstream database writes. This approval does not authorize unrelated catalog/map/badge storage. Revisit: yes, with migration/backup impact reviewed.


## DEC 010 Location During Checkout

Date: 2026-10-02. Options: preserve assigned shelf; move to Checked Out with separate home tracking. User chose preserve assigned shelf. Custody is shown separately by the companion; checkout does not modify the native parent/location. Revisit: yes.

## DEC 011 Badge Token Registry

Date: 2026-10-02. Options: hashed random tokens with individual revocation; stateless signed badges. User approved a small badge table in the companion database referencing native Homebox users. No copied names, emails, passwords or profiles. Individual issuance/revocation supported; current group membership checked at resolution. Revisit: yes.

## Reversible prototype badge code

LAB:U:<random token> is used only by the tested badge module. No permanent badge labels issued. Permanent namespace/label contents remain a later review decision.


## DEC 012 Temporary Open Administration

Date: 2026-10-02. Options: require Homebox login; open Admin during prototype setup. User chose open Admin temporarily. Issuance/revocation endpoints are loopback-only and same-origin guarded; anyone at the terminal can administer badges during this approved setup mode. Production Admin permissions are still pending. Revisit before deployment.

## DEC 013 Session After Confirmation

Date: 2026-10-02. Options: end after confirmed checkout/return; remain active. User chose end immediately after confirmation. Future transaction completion must clear kiosk identity; manual End session is already available. Idle timeout pending.


## DEC 014 Routine Return Destination

Date: 2026-10-02. User chose the assigned Homebox shelf as the default return destination. A location scan is needed only for a different destination. Destination updates will use the native API and recovery journaling; this decision does not duplicate location records.

## DEC 015 Idle Badge Session

Date: 2026-10-02. User chose two minutes of inactivity. Server enforcement uses monotonic time; touches and scans count as activity, background polls do not. Expired sessions cannot be revived by activity. The UI clears the identified person and returns home on expiry. Confirmation still must end the session per DEC 013.

## DEC 016 Equipment States

Date: 2026-10-02. User requested Archived, Retired, Broken and Trashed in addition to Ready, Needs Attention, Maintenance and Quarantined. User clarified that Retired means no longer used and blocked from checkout. Only Ready is checkout eligible. Homebox native archival support and custom fields will be used where appropriate; Trashed preserves a historical record rather than deleting an entity. Existing assets without a recorded state need an explicit initialization policy before checkout.


## DEC 017 Existing Asset Review

Date: 2026-10-02. User chose Admin review before checkout. Missing, malformed, unknown or duplicate condition fields resolve to Unreviewed and remain blocked. No automatic Ready initialization. The reversible native text field is named Equipment condition. Native archived=true always blocks checkout. Explicit Admin confirmation is required to change a state.


## DEC 018 Recommended Choices Delegation

Date: 2026-10-02. User cannot reliably see question cards and explicitly instructed: "if you need approval just choose whatever you recommended". Use recommended choices for outstanding and ensuing project decisions, explain them in progress updates, and record them here. This supersedes the handoff's repeated decision/checkpoint stops. Continue within the original project scope; request only information or physical actions that cannot be inferred. Revisit: user can change any choice.

## DEC 019 Return By Any Native Badge Holder

Date: 2026-10-02. Options: any current member; borrower only. Recommended option accepted under DEC 018. A current Homebox group member can return a colleague's equipment; the operation records the actual returner's native UUID and the previous checkout remains in history.

## DEC 020 Return Condition and Recovery

Date: 2026-10-02. Recommendation under DEC 018: unchanged condition and assigned parent are the fast path. Changed return conditions are Needs Attention, Broken, Maintenance or Quarantined, with an optional native note. Normal return cannot mark blocked equipment Ready or retire/trash it; Admin reviews those transitions. No automatic physical relocation for an issue; a user can scan an explicit active native location. Any unresolved native write keeps custody and requires Admin recovery. Cancellation is allowed only if native values remain unchanged. Finish verifies target values and completes the existing ledger operation.

## Operational Schema Version 1

An additive operation_context table stores return intent snapshots (native IDs, before/after condition, before/after parent, previous-note hash and reported note) for recovery. No inventory catalog or people profiles are copied. SQLite user_version is now 1; newer schema versions are rejected. A consistent integrity-checked pre-migration SQLite backup was saved in work/backups. Legacy custody and idempotency behavior are covered by migration tests. Revisit: future migrations must be explicit and backed up.

## DEC 021 Workshop Map Storage and Editor

Date: 2026-10-02. Options: companion map tables; native custom fields; native layout attachment. Recommendation under DEC 018: native location custom fields for room geometry and object placement, keeping links, labels and layout within Homebox backup/export. Start with a simple touchscreen grid and button-based positioning; the versioned geometry includes dimensions and rotation for later editing. Do not invent the physical room layout: Admin places native locations on the map. Native inventory locations remain intact when a visual object is removed.


## DEC022 - Native catalog and creation safety

2026-10-03. Under delegated judgement, use Homebox templates for offline GTIN product defaults. Create individually tracked assets Unreviewed unless explicitly inspected. Preserve serial/manufacturer/model natively. Temporary native markers plus a durable pending intent prevent blind duplicate creation. Finished intents are purged.

## DEC023 - Native issue records

2026-10-03. Problem reporting requires a badge, blocks checkout with an approved problem condition, preserves assigned shelf and creates a scheduled native maintenance entry. It does not mark repair completed. Uncertain responses require Admin verification and must not cause duplicate maintenance records.


## DEC024 - Verified native kits

2026-10-03. Under delegated judgement, manifests store native UUID references in a versioned custom field. Nested manifests are flattened for one atomic cart, with cycles and excessive size rejected. Scan the kit and every expected component. Complete-kit return is required while a kit is checked out. Definition and checkout do not relocate native records.

## DEC025 - Stable labels and deliberate photos

2026-10-03. Asset/location QR codes contain native record paths only; changing location, condition and borrower are not encoded. Badge print code/raster stays in memory; only a hash and native references enter the journal. Unknown printer outcomes require physical inspection and explicit recovery. Equipment photos are deliberate captures stored as native attachments; scan frames are not stored.

## DEC026 - Managed user services and private recovery

2026-10-03. Enable user services at boot with scoped SUPVAN access, and desktop autostart of the existing fullscreen launcher. Create cold matching native/operational/runtime backups and verify in isolation. Copying the private recovery archive off the Pi is pending explicit approval after automatic approval review rejected the requested PC copy.

## DEC027 - Original scope audit

2026-10-03. Handoff section75 explicitly says not to build consumable inventory and other future possibilities yet. These remain future work, not unfinished core features. All core phases still require their stated evidence and physical acceptance.

## DEC-028 — Storage warning and complete native search
Date: 3 October 2026. User delegated recommended implementation choices.
The original recovery plan requires disk warning. System Status warns below 2 GiB free or 10% capacity, with a critical message below 512 MiB. No files are deleted automatically and no operations are silently marked complete. Thresholds are reversible. Search includes native serial, model, manufacturer, category, descriptions and tags, as required by section34. Available means Ready, unarchived, individually tracked quantity1 and without current custody; blocked quantity records remain browsable.
