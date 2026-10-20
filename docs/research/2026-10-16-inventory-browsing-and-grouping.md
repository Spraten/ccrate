# C-Crate inventory browsing research and feature brief

**Audience:** Staff who search, locate, issue, return, and maintain individually tracked workshop equipment, on desktop and on the Raspberry Pi kiosk.

**Horizon:** A small first improvement to product/model browsing, followed by a separate location contents improvement.

**Scope:** Grouping similar serialized equipment (Mavic 3 Classic example), displaying current unit status and recent notes, and identifying adjacent inventory-navigation opportunities. This is a code and public-source review, not moderated user research.

## Executive read

The user problem is finding a kind of equipment and then knowing which physical unit is available, where it is, and what was recently recorded about it. C-Crate already tracks checkout, condition, storage, serial identifiers, and notes against individual entities, so the product should add a shared way to browse related units without combining those records. The existing Equipment page searches names, asset codes, and storage paths but does not search model or serial values. The ordinary Homebox location page shows contents for the selected location and its immediate child locations as separate sections, while the C-Crate workshop map already has a recursive-contents option for a selected map area. That means the strongest near-term opportunities are broader equipment discovery and a practical “show this whole storage subtree” view. Public Homebox discussions contain similar requests about nested contents, but they are individual reports and do not establish prevalence for C-Crate. The delivery roadmap starts with the isolated cabinet preview, then grouped-equipment search, then OCR camera controls; the three slices can be reprioritized independently without changing their boundaries.

## Evidence and confidence

### Observed in C-Crate source

- Equipment search matches `name`, `assetId`, and storage path; rows show each record’s condition and borrowing state. It currently omits `manufacturer`, `modelNumber`, and `serialNumber` from search. `homebox-ui/overlay/lib/workshop-tools.js:162-163`.
- The Workshop equipment endpoint fetches full native entities, which contain `manufacturer`, `modelNumber`, `serialNumber`, and tags. Search can use those values without adding another per-item detail request. `ops/desktop_api.py:178-185,425-426`.
- Checkout availability is evaluated per entity and requires an active, unheld, unblocked, ready record with `quantity === 1`. `homebox-ui/overlay/lib/workshop-tools.js:122-125`.
- Item return notes are shown with author and time per entity; the broader notes page can search across equipment. `homebox-ui/overlay/lib/workshop-tools.js:165-167`.
- Homebox’s location page renders items in the current location and immediate child locations as distinct sections. `upstream/homebox/frontend/pages/location/[id]/index/index.vue:350-355`.
- C-Crate already injects `Location/ChildContents.vue` into the native location page through `deploy/build-homebox-ui.py:399-415`. It recursively previews direct items and child locations, but users must expand children individually; each expansion reads both items and location detail. `homebox-ui/overlay/components/Location/ChildContents.vue:23-48,57-98`; its builder contract is covered by `tests/test_location_child_preview.py`.
- C-Crate Workshop view supports `nested=1`, and its view builder can include nested equipment. `ops/desktop_api.py:497-510`; `ops/workshop_views.py:280-314,459-562` validates ancestry and returns per-record status. This is limited to the selected Workshop area and returns a flattened descendant list rather than items partitioned under each bin.
- The OCR popover requests the browser’s environment-facing camera, shows a live preview, and captures at the video’s reported dimensions. It currently exposes no zoom/focus controls. `homebox-ui/overlay/components/Workshop/OcrPopover.vue:54-114,267-290`.
- The current workspace has staged OCR changes adding structured recognition, colored line labels, and image boxes. This is present in the staged diff but has not been verified in this review; existing OCR plan is `docs/superpowers/plans/2026-10-16-ocr-lines-and-confidence.md`.
- Browser media tracks expose capability/settings discovery and `applyConstraints`, but camera properties vary by device/browser. [MDN: `getCapabilities()`](https://developer.mozilla.org/en-US/docs/Web/API/MediaStreamTrack/getCapabilities), [MDN: `MediaTrackConstraints`](https://developer.mozilla.org/en-US/docs/Web/API/MediaTrackConstraints), [W3C Image Capture](https://www.w3.org/TR/image-capture/).
- C-Crate’s theme already has a muted green palette and inherits Homebox theme variables. `homebox-ui/overlay/assets/css/ccrate.css:1-30`; Workshop controls use the same variables in `homebox-ui/overlay/assets/css/workshop.css:1-20`.

### External signal (public, anecdotal)

- Homebox Discussion [#1284](https://github.com/sysadminsmedia/homebox/discussions/1284) reports that a location view can show storage boxes without showing the individual assets inside them. It is a single discussion and not a frequency estimate.
- Homebox Issue [#1742](https://github.com/sysadminsmedia/homebox/issues/1742) is titled “Inconsistent location/item view for nested items.” It signals hierarchy comprehension problems in a related product, not measured C-Crate user pain.
- Homebox Issue [#546](https://github.com/sysadminsmedia/homebox/issues/546) asks to add a child item from its parent view, a related navigation/management request.

### Inference and unknowns

- **Inference, high confidence:** Serialized units need to stay separate because checkout, condition, location, and notes apply to a physical unit.
- **Inference, medium confidence:** Exact manufacturer/model metadata can group repeated models without merging records; custom labels cover incomplete metadata without relying on approximate text similarity.
- **Unknown:** Whether “recent notes” should include return notes only, maintenance entries, or both. Start with return notes in the proposal because that is the C-Crate note stream most directly tied to workshop custody; keep maintenance clearly separate unless the user asks to combine them.
- **Plan choice:** Derive groups automatically from exact normalized manufacturer/model fields. Use explicit manager-defined custom groups only when those fields are incomplete or inconsistent.
- **Unknown:** How often staff need the cabinet-wide view, whether they want an expandable list or a dense table, and how much depth they want shown by default. Validate with one real cabinet and its bins before building a map-like interface.

## Ranked workflow problems

| Rank | Problem and user goal | Surface / what breaks | Evidence | Severity | Frequency signal | Confidence | Recommended move |
|---|---|---|---|---|---|---|---|
| 1 | Find all units of a model and choose a usable one | Equipment search cannot query model or serial; users must know the exact item name | C-Crate search fields and stock cache | High | User explicitly described repeated Mavic models | High for this user, not yet measured across staff | Search model/manufacturer/serial and show a model group with per-unit status |
| 2 | See what is inside a cabinet and its bins without opening every bin | Existing recursive preview requires a separate expansion and item/detail read for each bin | Existing `ChildContents` component and builder test; user’s cabinet example; one related public Homebox discussion | High | User report plus one public report only | Medium | Batch direct contents for all immediate bins and show them together; keep deeper descendants lazy |
| 3 | Read recent item notes in context of related models | Notes exist per item and cross-item search exists, but there is no model/group context | Existing item tabs and notes page | Medium | Implied by user’s request | Medium | Show recent return notes across group members, each linked to its source unit |
| 4 | Understand availability without mistaking quantity for physical units | Availability rules are per record and include more than “not checked out” | Checkout status rules | High | Safety/correctness property of current workflow | High | Derive counts with checkout’s existing status rules, then show the unit rows |

## Proposed grouped-equipment workflow

```text
Equipment
┌──────────────────────────────────────────────────────────────────────┐
│ Search equipment, model, serial, or storage…    Status: Any        │
├──────────────────────────────────────────────────────────────────────┤
│ Mavic 3 Classic        3 units · 2 available · 1 checked out         │
│ DJI · Mavic 3 Classic                                               │
│   Ready      SN …1842   Cage / Bin 4             Available   Notes  │
│   Ready      SN …7310   Cage / Bin 4             Available   Notes  │
│   Ready      SN …9921   With Alex                Checked out Notes  │
└──────────────────────────────────────────────────────────────────────┘
```

1. Staff search `Mavic 3 Classic`, even when the item names differ slightly.
2. Results show a group heading and an explicit count of physical records. Records with matching normalized manufacturer/model fields group automatically; a manager-defined custom group can override this for inconsistent metadata. Similar text alone never merges records.
3. Each unit row shows its item name, serial or asset code, complete storage path, condition, and current availability/borrower state.
4. Opening a unit keeps the existing item page and actions. Opening the group shows all its units plus the newest return notes, with every note labeled by unit, serial/asset code, author, and time.
5. Staff choose one available unit for checkout. The normal checkout flow rechecks that unit’s live status.
6. Empty states offer a clear action: “No units in this group yet” / “Add equipment to group.” Similar ungrouped records can be proposed as candidates for explicit review.

## First-version product and design proposal

### Scope

- Search equipment by item name, asset code, storage path, manufacturer, model number, and serial number.
- Group exact normalized manufacturer/model pairs automatically; allow staff with existing management rights to define a custom group for incomplete/inconsistent metadata.
- Show total physical records and status counts: available, checked out, needs review/blocked, and archived. These are record counts, not the sum of Homebox `quantity` values.
- List each member as an independent record with its own serial, storage, condition, checkout state, and item link.
- Show a small recent return-note timeline for the group; label and link every entry to its physical unit.
- Preserve native Homebox entity IDs, fields, tags, location, history, authorization, and normal checkout. No new database or native Homebox schema change in the first proposal.

### Data direction

Derive the default group from a non-empty manufacturer/model pair after trimming, case-folding, and collapsing repeated whitespace; preserve punctuation and accents. This gives the user an immediate group without writes or setup. For records whose model metadata is missing or inconsistent, a manager may use a reserved `C-Crate Product group: ` native tag as an explicit custom group. Verify the full-entity update preserves unrelated fields/tags before implementing that fallback. If the safety check fails, omit custom groups; the derived model grouping remains deliverable. Do not use fuzzy matching or add companion persistence silently.

### Compact visual direction

Ground the view in C-Crate’s existing workshop theme, not a new visual identity. Use the current surfaces and green action color; let the member rows and their storage paths carry the visual hierarchy.

- **Shelf white** `#FFFFFF`: primary rows and reading surface.
- **Workbench mist** `#F7F8F7`: page and grouped-result background.
- **Graphite green** `#2C3530`: headings and main text.
- **Tool green** `#5C7F67`: primary action and selected group indicator.
- **Soft green** `#E9F1EC`: selected/filter state, not a status substitute.
- **Quiet text** `#68736E`: secondary location and note metadata.
- **Type:** inherit the existing Homebox UI font and scale; use weight and spacing to distinguish model headings from item rows rather than adding a decorative display face.
- **Alignment:** left align all names, statuses, storage paths, and note text. Right-align compact counts only when they are column data. Do not center long inventory text.

Two content layouts were considered:

```text
A. Expanded grouped rows (recommended)
Search / status filters
Model heading + counts
  Unit row: status | serial | location | latest note
  Unit row: status | serial | location | latest note

B. Group cards with a separate detail page
Search / status filters
[Model card] [Model card] [Model card]
Open card → separate member table and note timeline
```

**Choose A for the first release.** The task is comparing physical units, and expanded rows expose the useful differences immediately. Keep groups collapsed only when there are many units; preserve a single screen-to-scan on the standard desktop and keep the same hierarchy in a stacked mobile layout. Avoid a dashboard of equal cards or status color alone: the words “Available,” “Checked out,” and “Needs review” must remain visible.

### Design self-review

The memorable element is the model heading with an immediately scannable set of physical unit rows. Palette and type inherit the product’s actual theme, avoiding a generic new-page style. The main risk is density: keep each row to the details that distinguish a unit, and move longer notes into a short timeline or item link instead of growing the table into a full history screen.

## Broader workflow opportunities

### Fix this week / low-risk exploration

- Extend Equipment search to model, manufacturer, serial, and full storage path; this is useful even before persistent grouping is selected.
- Add clear storage path and status facets to group/member results; maintain one filter vocabulary across Equipment, checkout selection, and return.
- Improve the existing recursive “Child locations” preview: show the immediate bins and their direct items together, loaded through one paginated parent-filtered query, with expand/collapse controls. Keep deeper descendants on demand and add name/status filtering only if the current one-screen view needs it.

### Fix this quarter / separate feature candidates

- **Location subtree browser:** one screen for cabinet → bins → equipment; show direct vs descendant contents, location counts, and item-level stock state. Preserve “move” actions at the individual item level and show a confirmation before bulk moves.
- **Model intake and cleanup:** when adding/importing a serialized item, suggest an existing product group based on model/manufacturer and let the user confirm. Flag blank/duplicate serials but do not block them or merge records.
- **Recent activity across a group or location:** show return notes and condition/maintenance as distinct event types, each tied back to the item that generated it.
- **Find this item:** add scannable storage breadcrumb, nearby/sibling bins, and label/QR navigation from a result. Avoid replacing the existing authoritative parent/location hierarchy.
- **Fast stock review:** location-level counts by available, checked out, and needs review, with the ability to open the exact records that make up each count.

### Needs deeper research

- Ask 3–5 staff to find a named serialized item, choose one available unit, and find an item note. Record whether the current search or grouped result changes their choice.
- Ask staff to find an item in the gray cabinet using the current UI, then compare a recursive list with a spatial cabinet map. Observe time, wrong-bin selections, and whether bin order matters.
- Clarify who may create product groups, whether equipment can belong to multiple groups, and whether group names need to be shared across collections.
- Decide whether “recent notes” is return-only, all maintenance, or a combined chronological activity stream with type labels.
- Test the OCR camera’s active video track for hardware `zoom`, `focusMode`, focus distance; add only controls the selected camera reports. Use digital crop as an explicitly labeled zoom fallback; manual focus cannot be promised on unsupported cameras.

## Research source map

| Source | Contribution | Limit |
|---|---|---|
| C-Crate `workshop-tools.js`, `ops/desktop_api.py`, `ops/workshop_views.py`, `ChildContents.vue`, builder and its contract test, and OCR popover/helper | Direct evidence about search, item status, recursive location preview, OCR capture, and camera lifecycle | Source review does not measure user frequency, large-collection performance, or actual device controls |
| User’s current examples: repeated Mavic 3 Classic units; gray cabinet with 20+ bins | Direct evidence of the requesting user’s needs and desired screen outcome | One user’s report; validate with other staff before generalizing |
| Homebox GitHub Discussion #1284, Issue #1742, Issue #546 | Related public requests about nested location contents and parent/child navigation | Anecdotal reports from a different product context; no prevalence estimate |
| Saved Product Design context | Preflight found no saved user-context file or design references | Design grounding therefore comes from the current repository and user examples |

No internal support, telemetry, or interview data was available in this review.

## First-version decisions adopted for planning

- Derive groups from exact normalized manufacturer/model fields with no writes or setup. A reserved `C-Crate Product group: ` native tag is a manager-only fallback for incomplete/inconsistent fields. Before implementing that fallback, prove the full-entity update preserves every unrelated field and tag using the pinned Homebox API and isolated fakes. If that check fails, omit custom groups; exact model groups remain deliverable.
- Keep recent group notes to C-Crate return notes in the first version. Keep maintenance events in their existing surface.
- Start cabinet pages with every immediate bin and direct item visible; use one parent-filtered paginated query and load deeper descendants only on demand.
- Put OCR camera controls into the first version. Use supported hardware controls when advertised, a clearly labeled 1×–4× digital crop fallback for zoom, and an explicit autofocus/unavailable explanation when focus cannot be controlled. Validate the target C920/browser manually.
- Treat the order as independent delivery slices: cabinet contents, grouped equipment, then OCR controls, each with its own focused checks and review. The camera controls may be moved earlier if the OCR workflow becomes the immediate operational priority.

These defaults complete the planning scope without claiming user research beyond the current user’s examples. The API safety check and real-camera capability check remain implementation verification tasks, not open product questions.
