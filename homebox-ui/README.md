# Native Homebox workshop integration

`overlay/` adds native Vue components and routes to the pinned Homebox frontend.
`deploy/build-homebox-ui.py` copies upstream into `work/homebox-ui-build`, applies
checked patch anchors, and builds static output without editing the submodule.

- Collection → Members has User, Email, Kiosk Badge and Items columns. Each member
  has a stable generated SVG avatar seeded only by their native user identity.
  Equipment Terminal uses the same local avatar generator. Reprint badge
  prints another copy of the same active badge; Manage badges handles issuance,
  revocation and access. Item counts expand to show photos, checkout dates, elapsed
  time and native item/history links for each member.
- Home shows current checked-out items, borrowers and loan links below its statistics.
  The count follows the selected collection and refreshes every 30 seconds while
  visible, when returning to the page, or with the refresh button.
- Item Details shows borrowing status. Loans & return notes is a normal item tab.
- The existing label dialog includes a Pi printer preview and explicit one-label action.
- Workshop sidebar routes use the native layout, collection and theme. Complex map,
  import and recovery workflows reuse the companion view logic with scoped DOM,
  native routing, teardown and the shared authenticated request helper.
- Equipment Terminal remains linked from the sidebar and opens its own terminal page.

Build on this Pi with `python3 deploy/build-homebox-ui.py`. The private build
toolchain lives in `work/toolchains`; `node-path.txt` selects its Node directory.
Dependencies are installed into the staging directory using the checked-in
`pnpm-lock.yaml`. Vue packages are aligned to the upstream app's 3.5.20 version.
The upstream oxc-parser 0.72.3 WASI package handles the Pi's CPU during builds.

The pinned upstream has 51 existing TypeScript diagnostics. They were reproduced
on an unmodified copy with the same dependencies. `upstream-typecheck.json`
records that baseline and source commit; the builder rejects additional errors
or a different upstream revision. Full diagnostic output stays under `work/`.

The gateway serves `work/homebox-ui-current` and forwards native APIs unchanged.
Publish a verified `.output/public` directory into `work/homebox-ui-releases/`
and atomically select it with that symlink. Keep the previous release for rollback.
Backups include the overlay and the selected frontend's actual files.

Verify with the temporary-fixture unit suite, `deploy/verify-desktop-integration.py`
(disposable Homebox database), and `deploy/verify-shared-tools-live.py` (read only).
Badge/print/create writes keep durable request IDs; uncertain outcomes require
Recovery. Never use the operational database for mutation tests.

Badge reprinting keeps encrypted copies of newly issued QR credentials in the
private operational database, using the Pi's `cryptography` runtime and a private
`work/ops/badge-print.key` (mode 0600). Both stay on the Pi and are included in
private deployment backups. Restore the key and database together. Public lists
and request journals contain no QR credentials. Existing badges without a saved
QR require an explicitly confirmed replacement; no credential is guessed.

Shelf-check drafts, completed and cancelled history, observations, snapshots,
audit events and request results are stored in `work/ops/ledger.db`. The existing
private deployment backup includes `work/ops` and checkpoints and hashes that
database before archiving it. Backups stay under the Pi's private
`work/backups/` directory (directory mode 0700; archive mode 0600); retain them
there according to the workshop's manual retention practice. No automatic
cleanup is configured. For SD-card failure protection, copy a backup through an
approved private channel to separate storage. Restore the Ledger only into a
fresh, isolated fixture first, and restore the matching database and badge key
together when badge reprinting is needed. Never overwrite a running operational
database as part of recovery.
