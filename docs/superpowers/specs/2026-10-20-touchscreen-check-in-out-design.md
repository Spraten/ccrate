# Touchscreen Check-in and Check-out Design

## Purpose

Provide a clear, reliable touch workflow for borrowing and returning C-Crate
equipment at the shared workshop screen. The screen is for members completing
their own transactions; managers continue to use C-Crate's authenticated
management interface.

## Agreed user decisions

- The kiosk home screen has two primary actions: **Check out** and **Return**.
- Both actions start by scanning the acting member's badge.
- Equipment can be found by scanning its code or searching by name/ID.
- Search is a discovery aid: every item must still be physically scanned before
  the transaction can be confirmed.
- A transaction can contain multiple items. The member reviews the full list
  and confirms once.
- Checkout and return support an optional note for each item.
- Returns default to the item's assigned location and recorded condition. The
  member can report a condition issue and add a note.
- The target display is 800 × 480 landscape, with usable behavior at other
  viewport sizes.
- The kiosk has no manager or inventory-management actions.
- The implementation stays in the existing C-Crate repository and companion
  server. It must not add a service, runtime, or product dependency.

## Proposed architecture

Restore the touchscreen client as static assets served by the existing
companion server on port 17749. Keep transaction authority in the current
checkout and return handlers; the browser must not write custody records or
decide item eligibility itself. Use the badge session and scan records already
owned by the server, and submit one explicit confirmation request after the
member reviews the transaction.

For returns, add a badge-session-bound availability lookup that checks only
the item IDs the member has selected. Return the status, recorded condition,
and assigned location needed for review, but do not send the touchscreen the
full custody list or other borrowers' names.

The current source selects `work/kiosk-ui-current` or `kiosk/` for static
assets, but neither source directory presently contains the page and workflow
scripts. The implementation should establish one repository-owned static
asset location and serve the terminal from the existing companion entry point.
It must not create a second server or leave a second version to track.

### Manager security boundary

The kiosk never presents manager actions. Existing manager operations must
continue through the authenticated `/workshop-api` path, which binds requests
to the native Homebox user and checks configured manager membership. The
companion currently has `OPEN_ADMIN=True`, and it binds to `0.0.0.0` in normal
operation. Before the shared screen is considered ready, direct legacy admin
routes must no longer bypass that manager boundary. Prefer disabling the open
legacy admin mode while preserving authenticated manager routes; audit current
UI route usage during implementation and secure or migrate any remaining
manager operation before removing its old route.

This setting is a server authorization concern, not a visual hide/show rule.
The kiosk itself must not be used to grant management privileges.

## User flow

### Check out

1. The member chooses **Check out**.
2. The screen asks the member to scan their badge and shows the recognized
   member name before continuing.
3. The member scans each item. Name/ID search can locate an item, after which
   the screen asks for its physical code scan.
4. The screen adds verified items to a review list and shows availability or a
   specific reason an item cannot be borrowed. The member can remove items or
   add a note to each item.
5. The member reviews all items and confirms once.
6. The screen shows the saved result and keeps it visible until **Done**.
   **Done** clears the session and draft before returning home.

### Return

1. The member chooses **Return** and scans their badge.
2. The member scans each item to return. Search can find an item, but its
   physical code must be scanned before it can be confirmed.
3. The screen shows the recorded return location and condition. The member can
   report a changed condition and add a per-item note.
4. The member reviews all items and confirms once.
5. The screen shows the saved result until **Done**, then clears the session and
   returns home.

If a confirmation outcome is uncertain, the screen preserves the request key
and offers a status check. It must not automatically submit a second
confirmation. A stale badge/session, item availability change, missing scan,
or server rejection returns the member to review with a specific correction
message.

## Session and data rules

- Use the existing per-client badge session, generation, instance, and scan
  ownership checks. A session change invalidates the draft.
- Use the server's 120-second badge/session inactivity expiry. Clear local
  drafts on expiry, explicit **Done**, or a session change.
- Preserve the existing server batch limit of 50 distinct checkout items.
- Keep checkout availability and return condition/location validation on the
  server. A stale or rejected transaction requires review before retry.
- Return availability lookups require the current badge session and are scoped
  to the requested item IDs; they do not disclose other borrowers' names.
- A successful receipt remains visible until the user acknowledges it; an
  uncertain receipt remains recoverable through existing operation-status
  behavior.
- Return uses the identified member as the operator; do not enable anonymous
  return mode in this kiosk flow.

## Visual direction

Use C-Crate's existing workshop-console palette and system sans-serif stack:

| Token | Value | Use |
| --- | --- | --- |
| Surface | `#FFFFFF` | Main content and action surfaces |
| Canvas | `#F6F8F7` | Quiet page background |
| Ink | `#2C3530` | Headings and primary text |
| Workshop green | `#5C7F62` | Primary actions and verified state |
| Pale green | `#E7F0E8` | Secondary selected state |
| Amber | `#A56822` | Attention and review blockers |

Use the existing system sans-serif fonts to stay consistent and work without
network access. Keep content left aligned, reserve strong color for actions
and transaction status, and provide large controls (at least 44 px) with clear
focus states. At 800 × 480, the screen favors one task at a time and a compact
review list rather than dashboard cards or decorative statistics.

Home concept:

```text
┌──────────────────────────────────────────────────────────────┐
│ C-Crate                                      [member/session] │
│                                                              │
│       ┌─────────────────────┐  ┌─────────────────────┐       │
│       │     Check out       │  │       Return        │       │
│       │  Borrow equipment   │  │  Return equipment   │       │
│       └─────────────────────┘  └─────────────────────┘       │
└──────────────────────────────────────────────────────────────┘
```

Review concept:

```text
┌──────────────────────────────────────────────────────────────┐
│ Return · 3 items                                  [Back]      │
│ Scan or search for another item                               │
│ ┌────────────────────────────────────────────┬─────────────┐ │
│ │ Item · condition · return location         │ Review      │ │
│ │ Per-item note and remove action             │ Confirm     │ │
│ │ ...                                        │             │ │
│ └────────────────────────────────────────────┴─────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

## Approaches considered

1. **Restore the existing companion terminal in the same repository**
   (recommended): reuses badge, scan, checkout, return, and recovery APIs and
   the existing 17749 screen. It addresses the absent client without adding a
   process or deployment target.
2. **Put the transaction flow inside the manager-facing Homebox overlay**:
   shares its authenticated UI components but mixes an operational shared
   screen with manager navigation and Homebox login state.
3. **Add a separate kiosk application or service**: isolates presentation but
   creates another version and runtime to deploy and maintain, contrary to the
   one-codebase constraint.

## Out of scope

- Inventory editing, badge administration, imports, labels, workshop maps, or
  manager recovery tools on the kiosk.
- Anonymous return, camera-based OCR, and changes to how an item's location is
  managed.
- Changes to the Homebox inventory schema or transaction ledger.
- Replacing existing service/runtime installation or deployment mechanisms.

## Acceptance criteria

- The existing companion serves the kiosk entry page and static assets from
  this repository, without adding a process or dependency.
- Home offers only the two primary actions; each flow requires a badge before
  item selection.
- Search alone cannot satisfy physical scan verification.
- A batch can be edited, reviewed, and confirmed once; item notes remain
  attached to their items.
- Checkout/return validation, idempotency, stale-session protection, and
  uncertain-outcome recovery continue to be enforced by the server.
- Return lookup is bound to the current badge and selected item IDs and does
  not return other borrowers' names or a complete custody list.
- The completed result remains visible until **Done**; leaving or expiring a
  session clears its draft.
- At 800 × 480 landscape, all primary actions are visible and touch-usable
  without horizontal scrolling; other sizes remain usable.
- Kiosk routes expose no manager actions, and direct manager mutations require
  the authenticated manager boundary even while the companion is reachable on
  the network.
- Existing manager UI capabilities continue to work after legacy open admin
  access is removed or replaced with an equally enforced manager check.

## Risks and implementation notes

- Existing documentation and scripts disagree about whether the root page is
  the terminal or the companion shell. Preserve the established 17749 entry
  point, inspect the currently deployed asset selection, and avoid a second
  application path.
- The source has tests that expect the terminal assets to be absent alongside
  older verifiers that expect a terminal UI. Update these contracts as part of
  implementation so there is one intended behavior.
- Disabling `OPEN_ADMIN` may reveal legacy manager UI requests that have not
  migrated to authenticated `/workshop-api` routes. Inventory those consumers
  before changing the boundary and keep every required manager operation
  available only through a verified manager context.
- Browser checks with synthetic members/items can validate the flow; physical
  touchscreen and barcode-reader acceptance still requires the actual screen
  and scanner.
- The existing `/api/custody` route returns borrower names for all open loans.
  The touchscreen must not consume that route; implement and use the scoped
  return lookup instead.
