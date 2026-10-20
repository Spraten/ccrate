# C-Crate frontend design rules — 2026-10-19

Status: Q1–Q26 rules already approved; audit-specific application awaits batch approval. Companion evidence: [audit](2026-10-19-frontend-audit.md).

## Preserve the current system

Homebox remains the inventory/account authority. Reuse existing components, icons, theme variables and installed system fonts. The captured active theme is `theme-business`; Homebox light is also supported. Do not impose a new palette on other selected themes.

| Computed token at Inventory | Business dark | Homebox light |
|---|---|---|
| background | `0 0% 13%` | `0 0% 100%` |
| foreground | `0 0% 82%` | `150 10% 19%` |
| primary | `210 64% 31%` | `139 16% 43%` |
| muted foreground | `0 0% 82%` | `150 5% 43%` |
| border | `0 0% 10%` | `150 10% 88%` |

Values are HSL token components from computed styles, not measured rendered text contrast. Font: `ui-sans-serif, system-ui, sans-serif` with platform emoji fallbacks. Current shell input is 36 px high; Inventory search is 48 px. Map controls measure roughly 27–34 px, shell icons 36 px. These measurements identify target-sizing work; they do not establish WCAG compliance.

Current page container uses maximum 88rem and inline `clamp(1rem, 2.5vw, 2rem)` padding. Keep existing spacing utilities; use shared page-header/action/trailing-group classes only where they remove demonstrated inconsistency. Avoid introducing a second token framework.

## Navigation and hierarchy

- Inventory is the agreed default; explicit deep links still work. Locations occurs once immediately below Workshop.
- Give title, short task explanation and page actions a consistent order. Label maker/imports provide useful existing examples.
- Use equipment, locations, bins and drawing objects in user copy; reserve implementation terminology for diagnostics.
- Search remains readable and editable at narrow widths. Group search/submit/scanner coherently; preserve device/OCR access and keyboard order. Check sticky-header offsets when header height changes.
- Adopt consistent destination names (proposed Members/Labels), without altering role scope or native routes.

## Equipment and cabinet rows

- Prioritize thumbnail, name, authoritative status, location, group count and action. Keep `×5 ▸` together at the right.
- Show total and available/checked-out/blocked/unknown counts. Record count is not quantity. Do not infer status from descriptions or a missing loan.
- Keep unavailable groups visible. A group action opens an explicit unit chooser with serial/asset identity.
- Preserve independent bin expansion, bounded hydration, partial results and honest loaded-only search. Restore browsing context within the same account/collection only.
- Long names and missing/broken photos must leave identity/actions usable; use an existing neutral placeholder.

## Actions and feedback

- One primary custody action, with cart/note secondary actions. Confirm through the common popup contract.
- Everyone verifies their matching account badge inside checkout. Preserve kit verification and backend role checks.
- Transaction note optional; standalone note required. Append trusted identity/time. Planning cart does not reserve equipment.
- Dirty dismissals offer keep/discard. Successful receipt closes and refreshes relevant rows with feedback. Errors/unknown results preserve input and request key; status/Recovery never resubmits automatically.
- Distinguish loading, loaded-empty, filtered-empty, partial/stale and error. Describe limited history/results honestly.

## Interaction acceptance

- Approved product target: actual nonoverlapping 44 px interactive hit areas; scoped sizing, wrapping and spacing. Do not claim WCAG failure from this product target alone.
- Keyboard focus visible, returned to trigger after dialogs, and preserved appropriately during map repaints. Do not steal focus after async updates.
- OCR is nonmodal: deliberate focus handoff, scoped Escape, preserved keyboard movement/background access.
- Check 390×844, 800×480, 1280×800, 1920×1080; light/dark, actual browser 200% zoom, member/manager and slow/error states. CSS zoom is only supplementary stress evidence.
- Compute rendered foreground/background contrast before a contrast-specific remedy. Retain reduced-motion preferences.

## Implementation boundary

Edit focused source overlays/builder patches, not generated development files. No dependencies, schema changes, physical printing or operational record mutation for UI verification. Use isolated fixtures. Retain receipts, native history, account boundaries and uncertain-write protection. Review scoped changes independently before calling them complete.
