# Project Decisions

Maintain confirmed decisions separately from proposals. Date: 2026-10-02. No architecture, authentication, status vocabulary, QR namespace, label contents, map storage or deployment choice has been approved yet.

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

## Pending Proposals

- DEC P001: unmodified Homebox plus companion Ops/kiosk, rather than fork.
- DEC P002: Ops SQLite for custody/events/maps rather than Homebox custom fields or attachments.
- DEC P003: native service deployment rather than containers; final service scope/network access still pending.

See the architecture proposal for options, tradeoffs and visible effects. Do not treat these entries as user approval.

## Reversible Engineering Assumptions

- Pin v0.26.2 for source investigation and temporary baseline; final deployment version is subject to review.
- Use `/home/user/Desktop/inventory-system` as an isolated reconnaissance workspace.
- Bind the temporary baseline to loopback port 17745 with synthetic test data and private generated test credentials.
- Disable release checks and analytics in the baseline. Production configuration remains undecided.

Later decisions will be asked when relevant: badge versus PIN, session timeout, return destination, kit verification, condition/availability vocabulary, map interaction, asset display codes, permanent QR namespace, labels, backups and retention.
