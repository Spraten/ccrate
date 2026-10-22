# C-Crate project pause and resume

## Current stopping point

The front-end rework is paused on `main`. The design checkpoint is commit `5f15135` (`ui: checkpoint C-Crate frontend redesign`), followed by this pause/resume note. Local `main` is ahead of GitHub `origin/main`. The push was attempted but could not authenticate: the configured GitHub credential helper points to `/home/user/.local/share/github-cli/usr/bin/gh`, which is missing. Keep this checkout as the current copy until the push succeeds. The redesign is in progress, not a finished release.

Recent work covers the inventory browse/preview, item and location detail density, Create Item grouping, timestamped item notes, kiosk checkout/return cancellation and review states, item preview cards, shared Homebox theme CSS, manager-controlled touchscreen theme selection, Netum return scan Enter handling, dashboard statistics, member loan indicators, and workshop borrowing history.

Evidence is under:

- `docs/reviews/2026-10-21-audit/` — original manager/kiosk audit captures.
- `docs/reviews/2026-10-22-manager-audit/` — authenticated manager screens, including initial and expanded Create Item.
- `docs/reviews/2026-10-22-kiosk-audit/` — isolated kiosk home, badge, checkout, and return states.
- `docs/reviews/2026-10-22-frontend-redesign/` — responsive idle kiosk and theme captures.
- `docs/superpowers/plans/2026-10-21-ccrate-full-frontend-audit-and-redesign.md` — umbrella scope, completed work, and remaining review.

## Resume instructions

The GitHub CLI executable is missing at the configured helper path. On this Debian machine, install it through apt, authenticate in a browser, then push from this checkout:

```bash
sudo apt update
sudo apt install gh
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git
git push origin main
git rev-list --left-right --count origin/main...main
```

The final command should print `0 0`. The pending push is a fast-forward from the observed `origin/main` (`a98cabe`); do not force-push. Once uploaded, another machine can use `git clone https://github.com/Spraten/ccrate.git` and `git switch main`.

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
