# C-Crate Full Frontend Audit and Redesign Plan

> **For agentic workers:** This is the umbrella plan for the UI work. Complete the audit and have the user review the resulting design direction before implementing. Existing per-screen plans are subordinate and must be reconciled with audit findings first.

**Goal:** Make C-Crate easier and more comfortable to use across the manager interface and member touchscreen, with a coherent appearance and clear workflows throughout.

**Product surfaces:**
- Manager UI: Homebox pages and C-Crate overlay components, including dashboard, inventory and search, item/location details, Create Item, notes, member/admin tools, labels, and workshop pages.
- Member UI: standalone touchscreen kiosk, including home, badge scan, checkout, return, item lookup/review, receipt, and recovery states.

**Known pain to verify during audit:** no clear way to cancel checkout/return; recurring “C-Crate unavailable; no confirmation received”; slow search; Create Item feels visually uncomfortable; item/location screens have redundant controls and excessive empty space; item notes need trustworthy timestamps.

**Style source:** Use the Homebox theme and component system described in `2026-10-21-ccrate-shared-theme-compatibility.md`. The current mockup is a concept, not the visual authority. Reconcile it against actual C-Crate screens before adopting its layouts or styles.

## Guardrails

- First audit both interfaces from captured screens and real user tasks. Do not claim a visual audit from source code alone.
- Homebox remains authoritative for inventory, users, locations, attachments, permissions, and history.
- Never send writes to the operational Homebox instance during audit or demo. Use synthetic fixtures or read-only browsing.
- Never auto-repeat uncertain item saves, badge issuance, checkout, return, or print operations; preserve existing request identity and recovery behavior.
- Use Homebox's active theme tokens, theme choices, type, radius, components, and semantic states. Avoid a separate kiosk or prototype design system.
- Preserve the kiosk's scanner ergonomics and 48 px minimum controls; preserve manager screen keyboard and responsive behavior.
- Keep the existing upstream build-and-overlay workflow and avoid adding dependencies.

## Audit Method

Capture each screen at realistic viewport sizes and follow the tasks through the visible UI. Use only a read-only account for inventory surfaces and synthetic data for any flow that would write. Save the accepted screenshots and a short note for each step. Record a named blocker when a state cannot safely be reached.

For each screen or step, assess:

1. Can a new user tell where they are and what to do next?
2. Are the most common actions easy to find, with duplicate or low-value controls removed?
3. Do photos, names, availability, location, and other key facts appear before secondary metadata?
4. Are loading, empty, error, success, cancel, and uncertain states clear and recoverable?
5. Are fields and actions sized and grouped for the relevant device and task?
6. Do both interfaces share the same active theme, typography, surfaces, control shapes, borders, focus, and status language?
7. Are keyboard use, touch size, focus visibility, contrast, and screen-reader labels apparent or in need of interaction testing?

## Stage 1: Capture and Inventory the Current Experience

**Screens/flows to capture:**

- Manager: Home dashboard; inventory list and search results; selected item detail; location list/detail and contents; Create Item initial, expanded optional fields, photo preview, and success; item notes and editor; checked-out items; member/badge management; relevant workshop/label tools; profile appearance/theme control.
- Touchscreen: home; badge ready/failure; item ready/failure; checkout and return review; cancel/back; successful receipt; uncertain confirmation and status recovery.
- Capture desktop manager and touchscreen-sized layouts. Include one light and one dark theme if they can be selected safely.

**Repository inventory already found:**

- Homebox page routes are in `work/homebox-ui-next/pages/`; C-Crate adds manager pages under `homebox-ui/overlay/pages/` and shared controls under `homebox-ui/overlay/components/Workshop/`.
- Member screens are in `kiosk/touchscreen.html`, `touchscreen.css`, `touchscreen.js`, `checkout-ui.js`, and `return-ui.js`.
- Homebox theme definitions and appearance behavior are in `work/homebox-ui-next/assets/css/main.css`, `homebox-ui/overlay/assets/css/ccrate.css`, `homebox-ui/overlay/assets/css/workshop.css`, `work/homebox-ui-next/lib/data/themes.ts`, and `composables/use-theme.ts`.

**Initial screenshot pass:** Captured and inspected the signed-out manager login and the kiosk home, badge gate, checkout scan/review, and return scan/review screens. See `docs/reviews/2026-10-21-audit/report.md`. Kiosk interactions used an isolated fixture with blocked transaction writes. Authenticated manager pages remain uncaptured because the available login attempt did not open them; continue those captures in a session with a valid manager login before calling the complete frontend audit finished.

## Stage 2: Produce a Prioritized Audit Report

For every captured flow, create a numbered step with screenshot, task, good parts, issues, accessibility risks, and evidence limits. Sort findings by user impact:

- **Blocker:** prevents a member/manager from finishing or recovering a common task safely.
- **High:** causes repeated errors, uncertainty, or significant delay.
- **Medium:** adds avoidable effort or visual discomfort.
- **Polish:** consistency and clarity improvements without major task impact.

Each finding must identify the exact screen/state, observed problem, who it affects, and suggested correction. Separate screenshot-evident issues from items that need keyboard, touch, scanner, or screen-reader interaction to confirm.

## Stage 3: Agree on One Cross-Interface Design Direction

Use audit evidence plus the user's existing choices: calm practical workshop feel, compact information, useful photos and previews, reduced redundant buttons and whitespace, native theme support, readable touch states, and consistent appearance between manager and kiosk screens.

### Design direction — approved to proceed

The user asked to use the Homebox/C-Crate CSS theme system so theme changes carry across both interfaces, and has now explicitly asked us to start implementation. Treat the following as the design contract for the first slices; do not pause for another plan approval.

**Color tokens:** values below describe the current C-Crate `theme-homebox` appearance only. Implementations must consume Homebox's semantic CSS variables so every registered theme can replace these values; the hex references are not kiosk constants.

| Role | Homebox token | C-Crate default reference |
|---|---|---|
| Page canvas | `--background-accent` | `#F7F8F7` |
| Content surface | `--card` | `#FFFFFF` |
| Main text | `--foreground` | `#2C3530` |
| Primary action | `--primary` | `#5C7F67` |
| Quiet separators and fields | `--border`, `--input` | `#DDE3E0` |
| Critical status | `--destructive` | resolve from the selected Homebox theme |

The token source is `work/homebox-ui-next/assets/css/main.css`, with the C-Crate default override in `homebox-ui/overlay/assets/css/ccrate.css`. Other themes must retain their own values. Never copy the reference hex values into kiosk CSS.

**Type:** retain Homebox's existing system sans-serif stack, type scale, and weight conventions. Keep headings concise and left aligned; use sentence case and plain task language. The touchscreen can enlarge labels and controls for distance and touch without inventing a second type family.

**Layout:** manager screens remain native Homebox pages, using a compact results-and-detail composition where specified in the item/location plan. The kiosk keeps its focused task layout: one scan/lookup area, a visibly grouped item preview/review, and a stable action shelf. Let content determine height; avoid filling the screen with empty decorative cards.

```text
Manager (wide)                       Touchscreen transaction
┌───────────────┬──────────────────┐ ┌────────────────────────────────┐
│ Results       │ Selected entity  │ │ Current task   Member status   │
│ search + list │ photo + key facts│ │ Scan / search                     │
│               │ compact details  │ │ Item preview and notes           │
└───────────────┴──────────────────┘ ├────────────────────────────────┤
                                     │ Cancel/back   Review / confirm │
                                     └────────────────────────────────┘
```

**Principles:** put the physical object and its current status before secondary metadata; keep one obvious next action; place cancel/back beside the task context; make disabled, loading, failed, and uncertain states visually distinct; preserve safe status recovery; and keep a familiar Homebox visual language without forcing a kiosk into manager navigation.

**Design review:** this direction is grounded in C-Crate's existing CSS tokens and the inspected screenshots. It avoids the generic SaaS card treatment by grouping only information that belongs together, and avoids a new bespoke palette by resolving colors at runtime from the active theme.

The current interactive prototype already imports Homebox theme CSS, but its visual pass still declares a Nunito font stack, a fixed yellow focus color, a custom shadow token, and a manually copied theme list. Before using it to approve production layouts, reconcile those remnants with the source font, focus token, radius/surface treatment, and actual Homebox theme registry. Keep its theme picker labeled preview-only.

Before implementation:

- Update the interactive mockup to match the real Homebox component and theme system, including active themes and light/dark behavior.
- Show the manager and kiosk screens side by side in the same theme, with desktop and touch layouts.
- Keep native screen patterns recognizable; don't force the kiosk into a manager dashboard layout.
- Revise the per-screen plans and TODO list to include audit findings, implementation scope, and acceptance checks.
- The user has approved proceeding with this direction and delegated implementation. Keep using captured screenshots and the token contract to review each slice; do not add a new approval checkpoint before starting.

## Stage 4: Implement in User-Impact Order

Reorder and refine the existing plans after the audit. Likely order, subject to findings:

1. Shared theme and component contract, needed before either UI is restyled.
2. Safe touchscreen cancellation, scan readiness/feedback, item previews, and uncertain-result recovery.
3. Search responsiveness across manager and kiosk.
4. Manager item/location browsing and detail hierarchy.
5. Create Item simplification.
6. Timestamped item notes.

For each slice, preserve Homebox authority and recovery rules, and review screenshots in the shared themes and intended viewport sizes. Keep slices independent and do not batch unrelated features into one large visual rewrite. Automated test additions or execution are deferred unless the user asks for tests or verification; do not run them as part of this work by default.

**Work started and progress:** the audit screenshots and prioritized findings are recorded in `docs/reviews/2026-10-21-audit/`. The stable Homebox token asset/route, theme-aligned interactive mockup, and kiosk token styling are implemented in commits `cfb6113`, `6084472`, `2a980cd`, `a7a8cbe`, and `34f41be`. The kiosk now has explicit cancel/back and review states, retained receipts until cleanup acknowledgment, and same-member status recovery after expiry; the latter received multiple source reviews and was hardened in `c7537ca`, `964f1f5`, `13e2ee4`, `cef74e9`, `88720e6`, `d59089a`, `3b6eb6e`, `332e353`, `59edaeb`, and `fbdca28`.

The current `main` implementation now also includes compact item/location identity and activity layouts, a responsive inventory list/preview, a grouped Create Item form and clearer completion actions, timestamped note history with explicit unknown attribution, and query-based manager/kiosk search. Relevant commits: `179ef08`, `ab80393`, `ea7ff1e`, `f053d67`, `575d4f4`, `a2d8f03`, `6e75d43`, `104216c`, `4937665`, `7db033e`, `894698d`, `9759a77`, `a91fb9c`, and `2905c44`. Manager search now keeps ordinary Homebox queries narrow and offers an explicit **Include ID and custom field matches** action. Selecting it scans the currently filtered collection so partial assigned IDs and custom-field-only matches can appear; that broader search may take longer. Exact and partial full-ID search is preserved in this mode. Kiosk search supports names and complete UUIDs, not partial UUIDs. The wider redesign remains active: the fresh manager screenshot pass is recorded below; Create Item's expanded/photo/success states and a few device- and transaction-dependent states still need review.

**Follow-up source review:** the existing authenticated fixture screenshots under `work/frontend-review/` are dated 2026-10-19 and show an older frontend baseline. The label-maker capture has a large empty preview panel and a Letter-sheet panel before any preview exists. Commit `21a6210` hides both panels until preview content exists and shows a short inline instruction beside the preview action, reducing dead space without changing print actions. These old captures are not accepted as evidence of the current rendering; refresh the screen captures after a current local preview is available.

**Current screenshot review:** `docs/reviews/2026-10-22-frontend-redesign/report.md` records idle-kiosk captures at desktop and mobile sizes and in Homebox's Night theme. `docs/reviews/2026-10-22-manager-audit/report.md` now records a fresh authenticated pass across the dashboard, inventory, create-item dialog, item/location details, members, labels, appearance, and workshop routes. `docs/reviews/2026-10-22-kiosk-audit/` records isolated checkout/return review captures and scanner Enter behavior. The pass also fixed missing inventory component registration, improved inventory default selection and labels, hid empty item metadata by default, clarified location tree actions and label-maker empty/search states, added item preview cards, persisted a manager-selected kiosk theme per collection, and added Enter submission for Netum return scans. The disposable manager browser blocked mutation endpoints except fixture login and theme preference; checkout-cart is blank under that policy and remains unverified there. Physical scanner, printer, camera, and transaction confirmation still require device/operational validation. The generated frontend build completes; the upstream typecheck still reports 38 existing diagnostics and no new ones.

## Acceptance Criteria

- Every planned C-Crate screen has an audit entry or a clearly named capture blocker.
- Findings are tied to screenshots and ranked by user impact.
- The final approved prototype and both implementations use the Homebox theme system instead of a parallel fixed palette.
- A user can find the common action on each screen, see useful item/location identity, and understand loading, empty, error, cancel, success, and uncertain states.
- Manager and kiosk interfaces look related while preserving their separate task layouts and target sizes.
- All previously reported safety and authorization behavior remains intact.
