# C-Crate project pause and resume

## Current stopping point

The front-end rework is paused on `main`. The branch contains the latest local work plus 139 commits not yet present on GitHub `origin/main`; this checkpoint should be pushed before the project is considered safely parked. The redesign is in progress, not a finished release. The generated UI has been built before; changes from this final pause pass are being built now.

Recent work covers the inventory browse/preview, item and location detail density, Create Item grouping, timestamped item notes, kiosk checkout/return cancellation and review states, item preview cards, shared Homebox theme CSS, manager-controlled touchscreen theme selection, Netum return scan Enter handling, dashboard statistics, member loan indicators, and workshop borrowing history.

Evidence is under:

- `docs/reviews/2026-10-21-audit/` — original manager/kiosk audit captures.
- `docs/reviews/2026-10-22-manager-audit/` — authenticated manager screens, including initial and expanded Create Item.
- `docs/reviews/2026-10-22-kiosk-audit/` — isolated kiosk home, badge, checkout, and return states.
- `docs/reviews/2026-10-22-frontend-redesign/` — responsive idle kiosk and theme captures.
- `docs/superpowers/plans/2026-10-21-ccrate-full-frontend-audit-and-redesign.md` — umbrella scope, completed work, and remaining review.

## Resume instructions

From a clone of the GitHub repository:

```bash
git switch main
git pull --ff-only origin main
```

Read `docs/superpowers/plans/2026-10-21-ccrate-full-frontend-audit-and-redesign.md` first, then the screen-specific plans in `docs/superpowers/plans/`. Check `git status --short` before editing so local user files are preserved. Rebuild the generated Homebox UI with:

```bash
python3 deploy/build-homebox-ui.py
```

The runtime on the Raspberry Pi was not restarted or deployed as part of this redesign. To activate a future release, follow the repository's normal package-managed deployment procedure in `README.md` and `docs/`; do not copy only the generated `.output` folder as the source of truth. Retain Homebox as the inventory authority and use the existing safe checkout/return recovery flow. The current plan defers automated tests unless specifically requested.

## Open work and evidence limits

- Recheck the latest screenshots after the current dashboard, member, and borrowing-history refinements are built.
- Capture Create Item photo-preview and confirmed-success states in a safe disposable fixture; the current capture has empty fields and no uploaded photo.
- The disposable manager browser blocked a history/group write, so its checkout-cart screen is blank and does not verify production behavior.
- Physical scanner, printer, camera, transaction confirmation, and uncertain-result recovery still need hardware/operational validation.
- Typecheck reports 38 existing upstream diagnostics; the last completed build reported no added diagnostics. Recheck after resuming.
- No claim is made that the full front-end redesign or a production deployment is complete.
