# C-Crate todo

## Frontend audit before redesign

- [x] Initial screenshot audit of the signed-out manager entry and kiosk home, badge gate, checkout, and return flow. Screenshots and findings are in `docs/reviews/2026-10-21-audit/report.md`. Kiosk interaction used synthetic fixture data with confirmation writes blocked.
- [x] Capture authenticated manager item/location/create screens and dashboard, labels, members, workshop tools, and appearance against the current generated source. Screenshots and fixture limits are in `docs/reviews/2026-10-22-manager-audit/`.
- [ ] Capture Create Item photo-preview and confirmed-success states in a safe disposable fixture; current captures show empty fields and no uploaded photo.
- [ ] Re-capture the manager dashboard, member, and borrowing-history screens after the final pause-pass source changes are built; inspect the after state before release.
- [x] Reconcile the interactive mockup and per-screen plans with the approved Homebox theme direction. The broader authenticated-manager screenshot audit is still pending before calling the full redesign complete.

## Touchscreen check-in and checkout

- [ ] High priority: investigate recurring “C-Crate unavailable; no confirmation received”. The companion returns this generic HTTP 503 for caught OSError exceptions in POST handlers and does not log the underlying exception there. Identify the affected action and root cause, add safe diagnostics without badge codes or credentials, and provide clear recovery guidance. Do not automatically resubmit uncertain transactions. Reported 2026-10-21; cause not yet established.
- [ ] Fix NETUM badge scanning. Investigate why scans are missed; make the screen ready to receive a badge scan when an action is selected and show clear scan feedback. Confirm with the physical scanner.
- [x] Add a visible Cancel / Back option to both checkout and return. Abandoning an unfinished transaction clears its badge session and draft; uncertain submissions keep safe status recovery.
- [x] Make inventory search responsive with debounced bounded native queries, clear loading/no-result/error states, stale-response rejection, and full-ID lookup. Manager search offers opt-in broad ID/custom-field matching while ordinary searches remain narrow. Broad search loads the full selected-filter collection and may take longer; partial kiosk UUID search is unavailable. Latency was not measured.
- [x] Redesign member checkout and return around clearer scan readiness, item review, cancel/back navigation, and safe recovery for uncertain confirmations. The screenshots use an isolated fixture; physical Netum scanning still needs hands-on confirmation.
- [x] Rework the kiosk idle screen with the shared C-Crate mark, a visible “choose a task, then scan” prompt, larger Homebox-themed actions, and a responsive one-column touch layout. Fresh before/after screenshots are in `docs/reviews/2026-10-22-frontend-redesign/report.md`.

## Item and location screens

- [x] Redesign item and location browsing with a desktop results/preview split, mobile result-first detail, compact identity/contents, and reduced redundant controls. The authenticated-manager screenshot review is still pending.

## Create Item screen

- [x] Redesign Create Item with essential fields visible, optional fields under “More details,” recovery controls available, and clearer completion actions. No live create operation was run.

## Item notes

- [x] Add timestamped item notes as a compact, newest-first history with explicit unknown time/author states and an Add note action opening the existing editor.

## Remaining manager views

- [x] Reduce empty space in the label maker by hiding preview and Letter-sheet panels until their previews exist, and explain how to enable the preview beside its action. Print controls and submission behavior are unchanged.

## Shared visual direction

- Follow `docs/superpowers/plans/2026-10-21-ccrate-shared-theme-compatibility.md` and the full frontend audit plan. Theme compatibility is a prerequisite for any visual rewrite.
- Use Homebox/C-Crate's existing theme system as the source of truth: `assets/css/main.css` for theme variables, `workshop.css` and `ccrate.css` for shared components and C-Crate adjustments, `useTheme()` for the saved appearance, and `lib/data/themes.ts` for available themes. Do not introduce a second palette, theme list, font, or corner-radius system.
- Manager views should inherit Homebox's existing typography, surface styles, buttons, fields, borders, focus rings, semantic colors, and active theme. Reuse native components and `.workshop-native` patterns where they fit.
- The touchscreen kiosk has its own static HTML/CSS, so it needs an explicit bridge to the same theme tokens and theme identifiers. Keep the member flow and its larger touch targets, but make colors, type, borders, control shapes, and feedback states read as the same C-Crate product. Do not copy a separate fixed hex palette into kiosk styles.
- Use the existing theme preference for Homebox views. For kiosk screens, determine an approved way to apply the same theme choice or provide the same theme options without creating a divergent palette. Keep any prototype theme control preview-only and label it clearly.
- Keep content left aligned and compact; use real item photos as the visual anchor. On item lists, show useful matches with thumbnails and key facts. Keep manager search responsive from desktop split view to narrow touchscreens.
- Review the manager and kiosk screens side by side in the C-Crate theme and at least one light and one dark variant. Keep their navigation and density appropriate to their jobs while aligning their visual language.

Recorded from user feedback on 2026-10-21. The authenticated screenshot pass and frontend build have been completed for the current checkpoint; automated tests were not run. Remaining work: finish the after-state screenshot review, capture Create Item photo/success states, validate with physical scanner/printer/camera and transaction recovery, investigate the recurring unavailable error, and compare manager/kiosk themes side by side at desktop and touch viewports.
