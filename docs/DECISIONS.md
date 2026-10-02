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

## Pending Proposals

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
