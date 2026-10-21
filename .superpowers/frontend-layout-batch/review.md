# Frontend layout batch review — UX-01 / UX-02

Review scope: the scoped baseline diff, worker report, current source overlays/builder, generated `work/homebox-ui-dev` sources, and the 2026-10-19 frontend audit/design rules. Read-only code review; no tests, browser actions, service actions, deployment, or operational writes were performed by this reviewer.

## Current verdict

**Final scoped source review passes with no remaining findings in these hunks.** Search grouping, sizing coverage and builder integration are sound. The findings from the first review are superseded by the fixes recorded below. The six supplied after captures support UX-01 acceptance and the map-button sizing change. The final metrics confirm 44 px room-picker/quick-search fields and matching 165/113 px header variables. The last checkbox-target capture remains pending.

## Final field follow-up — resolved

The current source scopes inspector/palette flex alignment to `label:has(input[type=checkbox])`. Ordinary `.field` labels keep their existing stacked display. Canvas checkbox labels now have `min-height:2.75rem`. Both corrections are present in generated `work/homebox-ui-dev/assets/css/workshop.css`, with no later rule removing the canvas label minimum. The source concern is resolved; the coordinator is capturing the final checkbox targets.

## Superseded findings and confirmed corrections

- **Resolved — shell sidebar targets.** Both normal and legacy `SidebarTrigger` instances now carry `.ccrate-header-sidebar-trigger`, covered by the scoped 2.75rem minimum width/height rule. The generated layout includes both classes.
- **Resolved — legacy device/OCR targets.** Legacy `DeviceStatus` now carries `.ccrate-header-device`, and the sizing rule covers both OCR launcher targets. The shared native button component remains unchanged.
- **Resolved — container override.** The later `@container (max-width:1240px)` canvas-tool rule now keeps both 2.75rem minima. The generated CSS contains the correction.
- **Resolved — legacy OCR builder anchor.** `shell_frontend()` adds the sidebar class before `ocr_popover_frontend()` runs; the latter now matches the exact updated legacy trigger string. The generated layout contains the legacy trigger followed by exactly one legacy OCR launcher. This review inspected the successful generated source; it did not run preparation or restart the service.
- **Resolved — early search unwrapping concern.** Search keeps a full-row basis below 1536px; the matching desktop header-height override covers 640–1535px. Desktop device-status mode remains correctly tied to its existing 1024px breakpoint.

## Source conclusions

- The search input, submit and scanner are one coherent flex group. Existing query binding, Enter handler, click handlers, translated button labels and order remain present.
- OCR's toolbar injection anchor was updated together with the DeviceStatus class. The final generated template has one toolbar launcher and a balanced search-group wrapper.
- Builder order is correct: upstream source and overlay copies precede `shell_frontend()`, then `ocr_popover_frontend()`, then input class replacement. Later location, item, nest and branding patches do not replace the shell controls. Generated `work/homebox-ui-dev/layouts/default.vue` reflects the intended change.
- CSS sizing is scoped; no dependencies, navigation redesign, API/mutation logic or map pan/zoom handlers are changed by these hunks. Existing `touch-action:none` remains on map/canvas.
- Header sticky offsets use the same CSS variables consumed by the item edit toolbar, but fixed breakpoint estimates still require actual header-height/scroll evidence. Capture 1024/1100px and the 1536px transition to confirm the wrapped/shared row boundaries with the desktop sidebar expanded.

## Pre-existing acceptance caveat

Item edit toolbar positioning (`work/homebox-ui-dev/pages/item/[id]/index/edit.vue:709`) uses `top-1` whenever the legacy-header preference is enabled, while the shell hides the ordinary header only at `lg` (1024px). Below 1024px the ordinary header is therefore visible even with that preference, so the toolbar can scroll beneath it. This condition predates the reviewed patch; the larger mobile header makes legacy/mobile offset coverage relevant to the audit. Confirm or document this mode when reporting acceptance.

## Supplied after evidence reviewed

The reviewer opened all six supplied `work/frontend-review/layout-after-{390,800,1024,1100,1280,1920}.png` screenshots and read `layout-after-metrics.json`.

| Step | Captured state | Review |
|---|---|---|
| 1 | 390×844 map and mobile shell | Healthy search group: 262×44 px input; device/OCR controls remain visible on their own row, followed by search/submit/scanner. |
| 2 | 800×480 map and expanded sidebar | Healthy search group: 263.375×44 px input; sidebar and header coexist without page overflow. |
| 3 | 1024px and 1100px map | Healthy: 384×44 px input; the former risky transition retains a separate search row. |
| 4 | 1280×800 map | Healthy: 384×44 px search input; map toolbar and canvas buttons wrap within their panels. |
| 5 | 1920×1080 map | Healthy: 384×44 px search input within a single header row; toolbar and canvas remain clear. |

The supplied metrics record no horizontal page overflow at all six widths and at least 44 px width/height for every visible measured map button. No overlap is visible in the accepted screenshots. Search handlers and accessible labels are preserved in source; keyboard operation was not exercised by this reviewer.

The first after capture exposed a 30.39 px room picker/quick-search and short checkbox labels, plus measured header heights of 165/113 px against 160/112 px variables. `layout-final-metrics.json` now confirms room picker and quick-search heights of 44 px at all six widths, no page overflow, and header variables of 10.3125rem (165 px) / 7.0625rem (113 px), matching actual heights. At 1920px, the existing 4rem variable matches the 64 px header. These final metrics predate the last checkbox-label correction; source and generated CSS for that correction have been reviewed.

## Evidence still needed for acceptance

Final screenshot/metrics for the last checkbox-label correction. Visible shell targets, keyboard search/scanner reachability and a scrolled item-edit toolbar still need direct measurement or interaction evidence. The audit also requires light/dark and actual browser 200% zoom; ordinary screenshots and source review alone do not establish that full matrix.
