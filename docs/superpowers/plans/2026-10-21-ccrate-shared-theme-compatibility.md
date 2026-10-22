# C-Crate Shared Theme and Visual Compatibility Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Homebox manager UI, member touchscreen UI, and future redesigned screens feel like parts of one C-Crate product while retaining their different jobs and layouts.

**Architecture:** Treat Homebox's theme definitions, CSS variables, component styles, and preference as the visual source of truth. Manager pages consume the existing Homebox styles directly. The kiosk is served as separate static HTML/CSS, so expose a stable, small theme stylesheet and apply the same theme identifiers there. Keep the prototype preview control separate from saved application preferences.

**Tech Stack:** `work/homebox-ui-next/assets/css/main.css`, `homebox-ui/overlay/assets/css/{workshop,ccrate}.css`, `work/homebox-ui-next/lib/data/{themes,theme-preference}.ts`, `composables/use-theme.ts`, `kiosk/touchscreen.{html,css}`, `deploy/build-homebox-ui.py`, and `deploy/kiosk-server.py`.

**Related plans:** `2026-10-21-ccrate-item-location-browsing.md`, `2026-10-21-ccrate-create-item-form.md`, `2026-10-21-ccrate-touchscreen-transactions.md`, `2026-10-21-ccrate-timestamped-item-notes.md`.

## Shared Visual Contract

The visual direction and current screenshot evidence are recorded in `2026-10-21-ccrate-full-frontend-audit-and-redesign.md` and `docs/reviews/2026-10-21-audit/report.md`. The user has asked us to proceed. Keep the existing Homebox system font and use an aligned-but-distinct kiosk task layout.

- The available palette is defined by Homebox `main.css`; the C-Crate `homebox` theme override comes from `ccrate.css`; shared workshop patterns come from `workshop.css`.
- Use the existing CSS tokens: `--background`, `--background-accent`, `--foreground`, `--card`, `--card-foreground`, `--primary`, `--primary-foreground`, `--secondary`, `--accent`, `--accent-foreground`, `--muted`, `--muted-foreground`, `--border`, `--input`, `--ring`, `--destructive`, and `--radius`.
- Use the app's inherited system sans-serif typography and semantic status colors. Do not add a competing font, fixed color palette, shadow system, or corner-radius scale.
- Homebox uses `useTheme()` and `lib/data/themes.ts`/`darkThemes` for the saved theme. Reuse its theme names and resolution rules rather than creating a second list.
- Keep the kiosk at 48 px minimum touch targets and the manager UI at its existing 44 px minimum. Align their color, type, border, button, field, focus, and message styles while retaining each screen's appropriate layout and information density.
- A mockup theme picker is for preview only. It must say that it does not change the saved Homebox preference.

## Global Constraints

- Do not change Homebox theme choices or theme preference semantics as part of a screen redesign.
- Do not allow the kiosk to access manager APIs or credentials solely to read a personal user preference. If the deployed system has no safe shared theme setting, use the C-Crate default on the kiosk and expose the same theme options for local preview only until a shared setting is separately designed.
- Keep Homebox as inventory, account, authorization, and history authority; preserve all existing authentication and transaction recovery behavior.
- Do not deploy or restart services during implementation.

## Review Focus

- Both interfaces use theme tokens rather than fixed page colors (`test_kiosk_styles_have_no_duplicate_theme_palette`).
- The theme contract provides the same theme IDs as `lib/data/themes.ts`, including light and dark variants (`test_kiosk_theme_ids_match_homebox_theme_registry`).
- Homebox saved theme changes still update manager views through `useTheme()`; kiosk defaults to the C-Crate theme without reading a personal account setting.
- At least one light and one dark theme preserve readable text, visible focus, semantic status, and photo contrast in both interfaces.
- Compare screenshots for inventory/item detail, Create Item, kiosk home, scan-ready, item preview, and transaction review. The layouts may differ, but typography, control shapes, surface colors, borders, and status treatment should feel related.
- Kiosk scanner focus, minimum target size, cancellation, and uncertain-transaction recovery remain unchanged.

## Validation constraint

Do not add or run automated tests unless the user asks for tests or implementation verification. For design review, use safe screenshots from synthetic kiosk fixtures and inspect the result directly. No production deployment or transaction writes are part of this plan.

---

### Task 1: Extract a stable theme contract for the kiosk

**Files:**
- Consume: `assets/css/main.css` inside the active prepared build workspace (`BUILD`, including `--build-root`); do not read from an ignored/stale development workspace.
- Modify: `homebox-ui/overlay/assets/css/ccrate.css` only if the C-Crate default token overrides need a stable shared entry point.
- Modify: `deploy/build-homebox-ui.py` to emit/copy the small stable theme stylesheet into the kiosk release assets.
- Modify: `deploy/kiosk-server.py` to serve the generated stylesheet from a stable same-origin route.

**Interfaces:**
- Consumes: the existing Homebox theme token definitions and theme registry.
- Produces: a stable kiosk-readable stylesheet containing theme variables only, plus a `/theme.css` route. It must not depend on hashed Nuxt filenames or duplicate the color values in `touchscreen.css`.

- [ ] **Step 1: Trace the normal UI build output and kiosk static-serving root.** Select one stable generated asset location and route without changing the deployment target.
- [ ] **Step 2: Emit the theme stylesheet from existing CSS sources during the normal UI build.** Keep the Homebox root and theme token declarations plus the C-Crate default override; preserve source values and theme identifiers.
- [ ] **Step 3: Serve the generated stylesheet as `/theme.css` with a `text/css` response from the kiosk companion.** Keep it same-origin and independent of hashed Nuxt assets.
- [ ] **Step 4: Review the source diff and generated CSS structure.** Confirm the complete theme selector set and semantic tokens are preserved, and the asset contains no separately invented values.
- [ ] **Step 5: Commit** `feat: share Homebox theme tokens with kiosk`.

### Task 2: Align the interactive mockup with the theme contract

**Files:**
- Modify: `docs/mockups/c-crate-ui-mockup.html`.

**Interfaces:**
- Consumes: the real Homebox `main.css` and C-Crate `ccrate.css` theme classes, plus the design direction and current prototype screenshot in the full audit plan/report.
- Produces: the same approved layout and preview-only theme control, rendered with Homebox's system type, semantic colors, focus ring, radius, and surface treatment. The preview theme IDs must correspond to Homebox's available themes; no fixed secondary palette.

- [ ] Keep the currently approved information hierarchy and split-view layout. Replace the unsupported emoji glyph boxes with a consistent intentional icon/photo fallback, not new decorative artwork.
- [ ] Remove prototype-only font, fixed focus color, shadow, and palette values. Resolve styling from the imported Homebox/C-Crate token definitions. Keep the preview-only label and do not write theme preference outside mockup-local state.
- [ ] Inspect the C-Crate default, one light, and one dark preview screenshot at desktop and narrow widths. Record any remaining mismatch.
- [ ] Commit `ui: align mockup with Homebox theme tokens`.

### Task 3: Align kiosk theme resolution and base controls

**Files:**
- Modify: `kiosk/touchscreen.html`, `kiosk/touchscreen.css`, `kiosk/touchscreen.js`.
- Modify: `deploy/kiosk-server.py` only if the stable theme route needs a request handler adjustment.

**Interfaces:**
- Consumes: the stable theme stylesheet, C-Crate theme identifiers, current kiosk flow state.
- Produces: kiosk screens styled through the shared tokens for page background, surfaces, text, borders, primary controls, focus, and semantic state. The page uses C-Crate theme by default and never reads manager credentials or personal user preferences.

- [ ] **Step 1: Load `/theme.css`, set the kiosk root to the C-Crate `theme-homebox` by default, and replace fixed surface/control colors with shared semantic variables.** Keep semantic attention/error states distinct where the source theme provides them.
- [ ] **Step 2: Preserve scanner behavior, visible focus, and 48 px minimum targets while aligning type, surfaces, borders, controls, and status language with Homebox.**
- [ ] **Step 3: Review the source diff and safe light/dark fixture screenshots.**
- [ ] **Step 4: Commit** `ui: align kiosk controls with Homebox themes`.

### Task 4: Bring manager redesigns back to native Homebox styling

**Files:**
- Modify: `deploy/build-homebox-ui.py` transforms for item/location browsing and Create Item.
- Modify: `homebox-ui/overlay/components/Workshop/EntityIdentityHeader.vue`, `homebox-ui/overlay/components/Location/ChildContents.vue`, `homebox-ui/overlay/components/Workshop/ItemLog.vue` as needed.

**Interfaces:**
- Consumes: Homebox theme preference, native page/component data, existing shared workshop styles.
- Produces: redesigned manager screens using Homebox buttons, cards, inputs, typography, borders, focus rings, and the active theme. Avoid page-specific shadows, hard-coded surfaces, new font choices, and unrelated roundness.

- [ ] **Step 1: Build the approved item/location and Create Item layouts** from existing Homebox components and `.workshop-native` patterns. Keep split view, responsive back navigation, compact fields, and photo placement without adding a separate design system.
- [ ] **Step 2: Review authenticated screenshots in the selected theme and compare them with the kiosk treatment.**
- [ ] **Step 3: Commit** `ui: keep redesigned manager views native to Homebox`.

### Task 5: Review cross-interface visual compatibility

**Files:**
- Update: the related plans' visual review notes and snapshots only if a specific mismatch requires a code fix.

- [ ] **Step 1: Capture** inventory/item detail, Create Item, kiosk home, badge scan, item review, and confirmation screens at manager desktop and kiosk touch sizes.
- [ ] **Step 2: Repeat** in the C-Crate default, one light theme, and one dark theme.
- [ ] **Step 3: Compare** typography, surfaces, card edges, controls, focus, status colors, spacing, and visual hierarchy. Log mismatches that make the screens feel like different products.
- [ ] **Step 4: Correct** only the mismatches found; preserve each workflow's layout and target sizes.
- [ ] **Step 5: Record** the reviewed theme/screen matrix with the implementation.
