# Frontend layout batch A (UX-01 / UX-02)

## Scoped changes

- `deploy/build-homebox-ui.py`: the shell search query, submit action, and scanner now form one flex group. The shell controls row wraps below 1536px; device status and OCR launcher retain their own place in the row. Search keeps its existing query/submit handlers and labels, and its input gains a 44px minimum height. The OCR launcher's injected target was updated to match the scoped DeviceStatus class.
- `homebox-ui/overlay/assets/css/ccrate.css`: scoped header actions receive 44px hit areas. At widths below 640px the mobile sticky offset is 10rem; from 640px through 1535px the desktop sticky offset is 7rem to account for the wrapped header and sidebar content width. At 1536px and above, the existing 4rem desktop offset remains. The search group stays full-row until 1536px so the expanded sidebar does not squeeze it at 1024–1100px.
- `homebox-ui/overlay/assets/css/workshop.css`: map toolbar buttons and room-planner mode, toolbar, and canvas-tool buttons receive 44px minimum hit areas. Existing flex wrapping, map SVG touch behavior (`touch-action: none`), pan/zoom handlers, and room-planner layout are unchanged.

## Baseline and preservation

Compared only the scoped hunks against `.superpowers/frontend-layout-batch/baseline/{build-homebox-ui.py,ccrate.css,workshop.css}`. Existing unrelated edits in the dirty checkout were retained. No generated UI, operational records, services, dependencies, or printer setup were changed.

## Evidence and limits

Builder source anchors for the search group and scanner close were checked against the local patched upstream layout and each occurred once. No tests or browser captures were run by this worker. Root is capturing the after-state for the narrow and desktop layouts. Sticky offsets are breakpoint estimates based on the wrapped shell rows and need confirmation against those renders; future long localized labels/device status content could make a row taller than its offset. No service restart or deployment was performed.

## Reviewer follow-up

Preserved the 44px canvas-tool button minimum in the `max-width:1240px` container override, which otherwise reset `min-width` to zero. The browser capture remains unavailable while the local service is restarting; no restart was initiated by this worker.


## Reviewer follow-up: shell controls

The normal and legacy sidebar triggers now have scoped 44px targets. Legacy DeviceStatus carries the same scoped device-control class, and both OCR launcher targets are covered by the 44px selector. The search group remains full-row until 1536px, matching the adjusted sticky offset range. Browser confirmation is still pending.

Review correction: legacy SidebarTrigger anchor was updated after a source-preparation failure. `python deploy/dev-homebox-ui.py prepare` completed successfully afterward; service recovered to HTTP200. No unresolved source-review blockers; rendered measurements pending. Existing legacy/mobile item-edit top-1 offset is a recorded remaining audit case, not claimed fixed in this scope.

## Final measurement adjustment

Root's after-state capture measured the shell header at 165px on 390px, 113px from 800px through 1280px, and 64px at 1920px. Sticky variables now match those dimensions (10.3125rem mobile; 7.0625rem at 640–1535px; existing 4rem at wider desktop). Root also found planner room selection, quick search, inspector/palette fields and checkbox labels below target. Those controls now receive scoped 44px hit areas; checkbox graphics retain their normal size. Search was measured at 262px (390px viewport), 263px (800px), and 384px (1024px and wider), with 44px height and no page overflow. Map button targets measured 44×44px. Root will capture the final control/offset state.

Known limitation: legacy/mobile item edit toolbar offset remains based on the pre-existing native layout offset and was not changed in this shell/map batch.

## Coordinator acceptance
Fresh read-only Chromium captures `layout-accepted-*` at390/800/1024/1100/1280/1920 plus390 light theme. Search262px at390,263px at800,384px desktop/intermediate; search44px high. Visible map picker, quick-search, mode/canvas buttons and canvas checkbox labels44px high. Header165/113/64px matches165/113/64px offsets. No whole-page horizontal overflow at any captured width. Root visually inspected narrow dark/light; reviewer inspected six after screenshots. Source final review passed. No test suite added/run, operational writes or prints. No claim of full audit/legacy-mode/keyboard/zoom acceptance.
