# Workflow ownership and navigation

The companion remains an interaction layer over native Homebox. Inventory, native conditions and assigned shelves keep their existing authority; custody and durable recovery remain in the approved companion ledger.

## Behavior

- Each browser page gets a fresh UUID client identity. Badge sessions, verified kit scans and idle expiry belong to that client. A reload requires identifying again. Native inventory and layout editing remain shared.
- Back restores the originating page, query, scroll and DOM-backed draft. Edited forms ask before discarding when returning to a manager. Home/Storage/Admin navigation asks before abandoning edits or carts, then clears hidden scan modes.
- Manual Back and camera Cancel send a scan cancellation token. The server checks it before starting a badge session and can end only a matching scan. Late responses cannot restore canceled pages or end a newer badge session.
- Checkout and Return use identify, cart, review, confirmation and persistent receipt steps. Return defaults to the assigned shelf and recorded condition.
- Rejected confirmations are checked against the ledger under the writer lock. Only an absent or cancelled request unlocks correction. Pending/review/unknown outcomes preserve the key and offer Check saved result and Admin recovery. There is no automatic create/print retry.
- Confirmations guard navigation through their follow-up reads. Fetch deadlines cover both headers and response body. Read-only pages reject stale responses after navigation.
- CSV mapping and per-row drafts survive Previous/Next/Jump/summary. Save review persists explicitly; unsaved row edits block bulk creation. Choosing Discard clears local unsaved drafts; saved batch progress stays on the Pi.
- Kiosk uses touch keys; editor mode enables physical keyboard input. Close keyboard retains text. Long forms keep Back visible, and key review/confirm actions remain accessible.
- Storage shows tappable hierarchy breadcrumbs and labels direct-assignment counts accurately. Labels/history/files return to their origin.
- The laptop launcher forwards companion 17749 and native Homebox 17745 through loopback SSH, then opens `?mode=editor`. Disconnect gives local tunnel instructions; the server rejects editor `/exit`. Native Homebox links appear in editor mode.
- Camera focus uses the stable C920 device link, reads actual state, and exposes Pi controls only when the local selected camera is a C920. Manual entry remains available.

## Verification without operational mutations

From the Pi repository:

```sh
PYTHONPATH=ops:kiosk:work/hardware/python python3 -m unittest discover -s tests -q
python3 deploy/verify-workflow-http.py
python3 deploy/verify-workflow-navigation.py
```

The HTTP verifier creates temporary databases and mocks native APIs. The browser verifier intercepts every HTTP request and uses synthetic accounts/items. It never creates inventory or prints labels. Its screenshots and results go to `work/workflow-verification`.

Continue honoring `AGENTS.md`: do not run old demo-creating verification against operational Homebox. Physical camera scanning and printing require a separately intentional device check.

## Review

The complete change was reviewed for client/session ownership, cancellation, recovery, draft loss and stale asynchronous render paths. Review corrections included a late recovery-status race, workshop editor stale-response handling and maintenance error navigation. Final acceptance includes an explicit delayed recovery response and 800 × 480 navigation checks. No unresolved P1/P2 regression was found in the final reviewed patch. This is a bounded code and fixture review, not a guarantee that hardware/network faults cannot occur.

Open Admin remains the previously approved temporary prototype setting. Production authentication and additional-room authoring remain separate product work.
