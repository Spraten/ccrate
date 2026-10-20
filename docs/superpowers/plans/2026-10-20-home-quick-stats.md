# Home Quick Stats Implementation Plan

> **For agentic workers:** Use subagent-driven development. Tasks use checkbox steps and require scoped review before proceeding.

**Goal:** Replace the Home page’s purchase-value stat with a useful, accessible overview of equipment condition, custody status, and storage distribution.

**Architecture:** Keep Homebox authoritative for equipment, condition, locations, and native totals; use the authenticated C-Crate API to combine current native equipment with the existing custody and recovery ledgers. Return one collection-scoped summary to the browser so the UI does not issue one status request per item. Render charts in the live UI overlay using small native SVG/CSS components, with no new dependency.

**Tech Stack:** Python 3 companion API, existing Homebox client and C-Crate ledger, Vue/Nuxt overlay, existing `deploy/build-homebox-ui.py` source integration.

**Spec:** Product-review decision record in the project review board for this request; implementation decisions are captured below because the review was not persisted as a separate report.

## Global Constraints

- Remove the existing **Total Value** purchase-price card; retain Total Items, Total Locations, and Total Tags.
- Count native equipment records, not `quantity` units, so chart populations align with custody operations and grouped Inventory.
- Exclude archived native records and storage-location entities from condition, availability, location, and actionable data-quality counts.
- Treat condition and custody as separate dimensions: Broken is a condition, while Checked out / In stock (checked in) / Blocked / Unknown are mutually exclusive availability states.
- Use the existing C-Crate condition function, custody ledger, and unresolved-operation ledger; do not infer missing conditions as Ready.
- Location counts use each item’s immediate assigned location exactly once, with an Unassigned bucket and a full directory path for display. Do not roll the same item into both a bin and its ancestors.
- Keep the API read-only, authenticated, collection-scoped, and free of borrower identity or item-level private fields.
- Do not add dependencies, alter native Homebox schemas, rebuild the Go backend, deploy, restart services, or change operational data.
- If the summary request fails, show an unavailable/error state rather than zero counts. Show an update time when data is cached.

## Review Focus

- Empty collections and zero-count buckets: display a clear empty state without invalid percentages or blank errors.
- Missing, duplicated, or invalid condition fields: classify as Unreviewed/Unknown, never Ready.
- A checked-out item whose condition is Broken: count it as Checked out in the availability chart and Broken in the condition chart.
- An unresolved operation: count it as Blocked/recovery and do not silently count it as In stock.
- Many nested locations, long names, and unassigned items: preserve direct-location counts and usable full paths without double counting.
- Quantity greater than one: count one native record in the charts and surface it in the existing blocked availability semantics.

## Design direction

Use the existing Homebox type scale, light/dark tokens, and card language. The memorable visual element is a pair of small labeled donut charts; the location distribution is a compact ranked bar list because many bins make pie slices and legends hard to read. Every visualization includes visible counts and a text equivalent, so color never carries meaning alone.

Design tokens: inherit the active theme’s `--background`, `--card`, `--foreground`, `--muted`, `--primary`, `--accent`, and `--destructive` values instead of hard-coding hex colors. This dashboard must follow every built-in Homebox theme, not only C-Crate’s default green theme. Keep the existing sans-serif type scale and left-align headings, category labels, and values; use tabular numerals for counts. The review against the design brief chose this over a fixed palette because preserving user-selected theme contrast is more important than forcing one brand color onto the charts.

```text
Quick Statistics
[Items] [Locations] [Tags] [Needs attention] [Unreviewed] [No photo] [Unassigned]

Inventory breakdown
[Condition donut + count legend] [Availability donut + count legend]
[Top direct locations as ranked bars, with full paths and Other/Unassigned]
```

## File map

- `ops/home_statistics.py` — read-only projection for collection equipment, conditions, availability, locations, and action-oriented counts.
- `ops/desktop_api.py` — authenticated `home/statistics` read route, using existing collection context and C-Crate ledgers.
- `homebox-ui/overlay/components/Home/QuickStatistics.vue` — responsive cards/charts, explicit loading/error/empty states, text equivalents, and refresh when the summary is re-requested.
- `deploy/build-homebox-ui.py` — durable homepage integration replacing the native stat grid with the overlay component; no generated workspace edits.
- `tests/` — no test files are added in this implementation pass. Validation is limited to source review and existing build/preparation commands because this user request did not ask to run or add tests.

## Task 1: Collection-scoped aggregate read

**Files:**
- Create: `ops/home_statistics.py`
- Modify: `ops/desktop_api.py`
- Do not modify Homebox Go source or database schema.

**Interface:**
- `build_home_statistics(items, locations, loans, unresolved_assets, total_locations, total_tags) -> dict`
- `GET /workshop-api/home/statistics` returns `{generated_at, totals:{items,locations,tags}, condition_counts, availability_counts, location_counts, attention_counts}`.
- `condition_counts` contains every native condition state plus `Unreviewed`.
- `availability_counts` contains `available`, `checked_out`, `blocked`, and `unknown`; a ledger loan takes precedence over condition for this chart, matching existing item-action status.
- `location_counts` contains at most five named direct locations plus `Other` and `Unassigned`, with `{id,name,path,count}` rows. `Other` has a count and no location ID.
- `attention_counts` contains `needs_attention` (non-Ready active conditions excluding Unreviewed), `unreviewed`, `missing_photo`, and `unassigned_location`.

- [ ] Add the pure projection `build_home_statistics` using the existing `condition()` / `checkout_blocker()` semantics; identify archived items, locations, native records, direct parents, photo attachments, current loans, and unresolved assets without returning item identities.
- [ ] Resolve full location paths from the current collection’s location tree; break malformed parent cycles safely and preserve missing parent as Unassigned.
- [ ] Add `home/statistics` to the authenticated GET dispatcher; derive group, native client, ledger custody, and unresolved operations from current request context only.
- [ ] Keep the response bounded: location buckets are top-five plus `Other` and `Unassigned`; return no names of equipment or borrowers.
- [ ] Review the diff for data scoping, precedence, record/quantity semantics, and failure behavior before moving to UI work.

## Task 2: Home Quick Stats UI

**Files:**
- Create: `homebox-ui/overlay/components/Home/QuickStatistics.vue`
- Modify: `deploy/build-homebox-ui.py` to replace the existing Quick Statistics card grid with the overlay component.
- Modify no files under `upstream/homebox/` or generated `work/` directories.

**Interfaces:**
- Component uses `useWorkshop().request('home/statistics')` and displays the exact aggregate response from Task 1.
- Donut visualization is implemented with inline SVG/CSS, labeled legends, and percentage/count text; no chart library.
- Location visualization is a ranked horizontal bar list showing the five most populated direct locations plus Other and Unassigned.

- [ ] Replace the Total Value stat while retaining the native item, location, and tag count cards.
- [ ] Add the actionable summary counts for Needs attention, Unreviewed, Missing photo, and Unassigned location.
- [ ] Render condition and availability donuts with visible labels, counts, and percentages; Broken remains a condition category.
- [ ] Render location counts as ranked bars using complete directory paths; label the counting rule as direct storage location.
- [ ] Provide loading, unavailable/error, no-items, single-category, and zero-count behavior; do not fabricate zero values on failed requests.
- [ ] Keep the charts legible on narrow screens and light/dark themes; ensure keyboard and screen-reader users can read every category/count without relying on chart color.

## Task 3: Integration review and handoff

**Files:**
- Review only: `ops/home_statistics.py`, `ops/desktop_api.py`, `homebox-ui/overlay/components/Home/QuickStatistics.vue`, `deploy/build-homebox-ui.py`.
- Record results in `.superpowers/sdd/2026-10-20-home-quick-stats/`.

- [ ] Inspect the builder-generated homepage source in a temporary source workspace, without installing dependencies or modifying generated workspaces.
- [ ] Perform source-level checks for member scoping, omitted private data, count consistency, unassigned/archived handling, and accessible non-color labels.
- [ ] Record that runtime tests, a full build, deployment, and service restart were not run in this pass.
- [ ] Obtain a final independent review and report any residual risks before handoff.

## Decision log

- “Remove the ‘total’ value” is interpreted as removing the current **Total Value** purchase-price card; the separate Total Items count remains because it is the useful inventory denominator.
- “Checked in” is displayed as **In stock (checked in)**; it is a current availability state. **Broken** stays in the condition chart because it can overlap with a checkout loan.
- Condition and availability donuts remain small and categorical; the location chart uses ranked bars to avoid an unreadable pie with many bins. This preserves the requested location distribution while improving comparison and long-label readability.
- The initial scope adds four actionable counts: Needs attention, Unreviewed, Missing photo, and Unassigned location. It defers warranty trends, asset value trends, and historical timelines until their data semantics and user value are established.
- No dependency or Homebox Go rebuild is introduced. If a future representative-size performance review shows the companion’s native reads are too slow, optimize the aggregate route separately rather than issuing per-item browser requests.
- Work in the current `codex/sdd-worktree-setup` checkout with scoped file snapshots because it contains the already-approved dirty feature work that a new HEAD-only worktree would omit. Do not stage or commit the shared tree.
