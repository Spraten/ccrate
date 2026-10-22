# C-Crate frontend redesign — kiosk home

**Captured:** 2026-10-22
**Viewports:** 1280 × 657 and 390 × 844
**Theme:** current Homebox `theme-homebox` and C-Crate default CSS tokens, generated using the normal theme extraction logic into a temporary local preview directory.
**Actions:** screenshots taken with JavaScript disabled so the idle home view is isolated. No account, badge, or transaction requests were made.

## Screens

| Step | Screenshot | Notes |
|---|---|---|
| 1 | [Before: kiosk home](01-kiosk-home-before.png) | Current `main` baseline before this change, rendered with the same theme CSS: clear checkout/return actions, but no cue for the next step or logo mark. |
| 2 | [After: desktop](02-kiosk-home-after-desktop.png) | Adds the existing C-Crate mark, a task heading and badge instruction, centers the idle task group in the available viewport, and enlarges both actions. |
| 3 | [After: narrow touch screen](03-kiosk-home-after-mobile.png) | The mark and member state fit in the header; actions stack at 390 px and the prompt wraps without clipping. |
| 4 | [After: Night theme](04-kiosk-home-after-night.png) | Theme-supplied text and logo color stay readable on the dark surface; primary actions use the selected theme's primary colors. |

## Findings and limits

- The added instruction tells a member to select a task before scanning a badge, making the first step visible while the kiosk is idle.
- Checkout and return remain the two primary actions. Their minimum height is 136 px at desktop and 96 px at the narrow breakpoint, both above the 48 px target.
- The design continues to use Homebox semantic surface, text, action, border, and focus tokens; no second palette was introduced.
- The header reuses the current C-Crate mark as inline SVG with `currentColor`, so it stays visible in the active theme without an additional asset or color override.
- The logo is explicitly filled with `currentColor`; a source review caught and corrected a black-fill issue, and the fresh Night screenshot confirms the mark remains visible.
- Screenshots establish static layout only. They do not validate actual scanner behavior, browser focus after a task is selected, or a production theme preference.
- The Homebox C-Crate default and Night themes were inspected on the kiosk home; manager screens and additional light/dark variants remain unreviewed.
