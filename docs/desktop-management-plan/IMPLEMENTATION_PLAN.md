# Desktop Workshop management with Homebox

Planning draft · October 4, 2026 · No production behavior changed by this proposal.

## Recommended product

Give desktop users one address and their existing Homebox login. Native Homebox remains the inventory interface. A linked Workshop workspace adds the companion features: loans, return notes, badges, room layout, guided import, label queues, recovery, and Pi administration.

“Import the features” means reuse the existing operations and data, not copy equipment or rewrite Homebox. This preserves the original interaction-layer requirement and keeps upgrades manageable.

The accompanying `prototype.html` is an interactive design preview. It uses fictional data and performs no native requests, account creation, badge issuance, printing, or backups. Its buttons demonstrate proposed flows; they are not a deployed application.

## Integration choices

| Approach | User experience | Consequences |
| --- | --- | --- |
| **Recommended: same-address Workshop workspace** | Homebox login, linked native item pages, desktop sidebar for companion tasks | Add a gateway and authenticated desktop backend; keep upstream unchanged. Verify root service-worker behavior. |
| Add tabs directly to Homebox's native sidebar | Features appear literally in the Homebox navigation | Requires a maintained frontend fork or tested response injection. No supported extension hook was found in the inspected pinned source. |
| Expose current companion as another website | Fast route to existing screens | Current open Admin and service-account execution are unsuitable for authenticated multi-user desktop management; still needs authorization work. |
| Browser extension or iframe | Additional wrapper around Homebox | Extension must be installed on each browser; native responses deny iframe embedding. Neither is the default recommendation. |

A workspace cannot silently add an item to the unchanged native sidebar. In the first release users can bookmark Workshop management and use “Open Homebox inventory” / “Edit in Homebox.” If native navigation becomes a must-have, agree on a small maintained Homebox frontend change explicitly rather than hiding it in the deployment.

## Data ownership

| Feature | Authority | Desktop behavior |
| --- | --- | --- |
| Equipment, serials, descriptions, conditions, categories | Homebox | Searchable context table; native editor links; supported API operations when needed. |
| Native storage tree, shelves, bins | Homebox | Tree beside map; clear location breadcrumb; move location distinct from moving drawing. |
| Photos, attachments, maintenance, product templates | Homebox | Native views and actions; no parallel copy. |
| Accounts and group/collection membership | Homebox | Invitations and membership actions supported by the pinned API. |
| Badge token hashes and revocation | Companion | Owner verification, issuance, explicit print, lost-badge revocation. |
| Checkout custody and return-note history | Companion ledger | Loans table, per-item timeline, authoritative attribution and completion time. |
| Floor-plan geometry | Companion | Reuse saved drawing and native location links. One room currently; multi-room is a separate model extension. |
| Import review progress | Companion import database | Resume a batch, edit/save rows, confirm valid creation, then label queue. Created equipment stays native. |
| Recovery and print outcomes | Companion durable jobs | Inspect saved intent and physical results; no automatic retries after uncertainty. |
| Desktop management roles | Companion, referenced by native UUID + group | Explicit permissions for companion endpoints; do not pretend these change native Homebox permissions. |

The existing ledger, badge, import and workshop databases are reused. A new session/permission store contains references and administrative roles, not duplicated profiles or equipment.

## Desktop information architecture

Sidebar: **Overview; Equipment; Loans & notes; People & badges; Workshop & storage; Imports; Labels; Recovery; System.**

The header shows the selected native collection, signed-in identity, and Workshop role. The initial release can be fixed to the current Workshop collection, but backend authorization must still validate every submitted native ID against that group. Switching collections later must clear or suspend drafts and never silently reuse the old group.

Use compact tables with search, filters and selection, and an item detail drawer. Preserve scroll, filter and selection on close. Reserve large badge/scan controls for the Pi kiosk. Desktop forms use physical keyboard input, with accessible labels, visible focus, Escape/Cancel, and predictable browser Back. Narrow screens collapse the sidebar into navigation rather than squeezing the desktop table.

### Equipment and notes

Equipment rows show assigned storage, condition, availability and current borrower. The drawer contains Summary, Loan, Return notes and Maintenance, plus “Edit native Homebox record.” Avoid two different editable forms for the same native property.

Keep condition separate from borrowing: a Ready item may already be borrowed. Home shelf stays recorded during checkout. A desktop administrative return identifies the signed-in operator and the borrower distinctly. It must not imply that the borrower scanned a badge.

Routine return notes use the existing `return_note` field. Author and completion time are server-derived; completed returns publish notes, pending/cancelled returns do not. If later note corrections are supported, append a correction entry rather than silently rewriting the original. That correction feature is proposed, not implemented today.

### People and badges

One row per native workshop member, with badge state and permitted companion actions. Separate the steps: membership verified → badge issued → label printed. Do not equate a successful account creation with a printed badge.

Prefer a native invitation link that lets people choose their own password, when supported. Do not require email delivery when SMTP is absent; provide the invitation link for explicit manual sharing. Existing kiosk account creation can remain as a supported alternate setup flow. Registration outside the invitation flow may create a separate collection.

Revoke a lost badge before replacement. Existing badge lists never display reusable QR secrets. Show a new QR only in its issuance workflow. Remove-member and badge-revoke actions are distinct and require review of unresolved loans. Guard against removing the last Workshop manager.

**Native limitation:** the pinned Homebox API supports self-profile/password changes, invitations and member removal, but not a normal collection-manager API for editing arbitrary user profiles, resetting everyone's passwords or assigning collection roles. The existing Workshop Admin account is not a native server-wide superuser. Do not elevate it globally merely to enable companion management.

### Imports and labels

Column mapping → review table → saved valid-item summary → explicit native creation → label queue. Saved row drafts and batch progress must remain recoverable. Bulk edits should apply only to explicitly selected rows, state the count, and show a review of invalid/blocked exceptions. Do not bulk-mark Ready without the physical inspection requirement.

Every print confirmation says **“Print on the Pi label printer”**, with item count, current stock size, and preview. A laptop's default printer is unrelated. The queue stops on an uncertain result and retains already completed output. Printer disconnect, browser reload or repeated click cannot automatically duplicate output.

### Workshop and storage

Show map, selected-object properties and native storage hierarchy together on a wide screen. Select rack → shelves → bins → equipment. Drawing geometry edits do not move native storage. “Link storage” chooses an existing UUID or performs a deliberately confirmed creation. Removing a drawing leaves its storage intact. Layout save uses revision checks to reject concurrent overwrites.

The current one-room model should be structured so room IDs can be added later, without implementing multiple rooms in this first migration.

### Recovery and system

Recovery is a task queue with saved intent, current known state, and the physical inspection needed for a decision. An unresolved operation on one item should not disable unrelated inventory work. Preserve the same request key across uncertain outcomes; no “Try again” that creates a new operation.

System shows Pi service/device readiness and backup status. Backup creation needs an explicit review because it pauses the kiosk. Device focus controls and kiosk-exit actions remain local to the Pi; a remote administrator should not accidentally close its touchscreen browser. Backups and credentials are not exposed as anonymous downloads.

## Authentication and architecture

The inspected native Homebox v0.26.2 already uses `hb.auth.token` and `hb.auth.remember` HttpOnly cookies scoped to `/`, with native session validation. A desktop backend can forward the native cookie to `/api/v1/users/self` and derive user UUID, membership and selected collection. Never trust a browser-supplied display name, role or `user_id` as proof of access.

The current companion has `OPEN_ADMIN=True`; `?mode=editor` is a presentation flag, not authentication. It authenticates native calls through the saved Workshop Admin service account. Simply changing its bind address would expose administration with the wrong identity model.

Proposed routing, contingent on the feasibility tests below:

```
Laptop / phone / tablet
  → current Pi address :17745 (gateway)
      /                         → native Homebox on loopback :17747
      /workshop                 → desktop Workshop workspace
      /workshop-api/...         → authenticated desktop operations

Pi touchscreen
  → local companion :17749      → existing badge workflows and durable operations
```

Keep native Homebox at the URL root because its assets, API, navigation, and compiled frontend assume root paths. Do not move it under `/homebox` without a verified base-path build. The gateway preserves the existing public :17745 address. Update every internal native base URL and attachment redirect allowlist when changing its internal port.

Use actual signed-in native user context for desktop inventory mutations where possible. Pi service identity remains only for specifically authorized kiosk/hardware actions. Audit the operator separately from the beneficiary/borrower. Do not store desktop passwords or expose service credentials/tokens in browser responses.

Define Workshop manager permissions by immutable native user UUID plus collection, bootstrapped explicitly to the current workshop account. Check permissions server-side for reads and writes, including badge lists, history, imports, recovery and system status. Logout, revocation, expiry and account/group changes invalidate administrative context. Other open tabs must reauthenticate/revalidate queued actions; drafts must not migrate to another person silently.

Validate Origin/CSRF for cookie-authenticated writes. Do not “fix” current origin restrictions by accepting any Origin or trusting arbitrary forwarded headers. Derive externally reachable deep links from the validated deployment origin; hardcoded `127.0.0.1` links point at the laptop itself.

Native collection membership is comparatively flat. Companion roles do **not** prevent a member editing inventory through native Homebox. True cross-application read-only/operator roles need a separate native capability/policy investigation, not UI-only button hiding.

### Feasibility gate before production changes

1. Test native login/cookie validation and logout using an isolated native instance; prove there is no second password store or native token leak.
2. Check actual browser service-worker registration. The compiled native `/sw.js` has root navigation fallback excluding only `/api` and API caching. A controlling worker could intercept `/workshop` navigation. Resolve namespace/worker isolation in a controlled test before choosing the final gateway path; avoid caching private desktop responses.
3. Confirm deep links, native assets, authentication redirects and uploads remain correct behind the gateway. Do not rely on iframe embedding; native response denies it.
4. Verify the selected collection and every affected entity/operation belong to the permitted group.
5. Decide whether existing HTTP LAN access is sufficient for the first deployment or configure a trusted HTTPS origin. Desktop camera scanning needs a secure browser context; manual entry and mouse selection must work without it. Do not promise remote webcam scanning over ordinary HTTP.
6. Keep the current direct Homebox URL and local kiosk working until a tested gateway cutover and rollback are ready.

## Implementation order

| Phase | Deliverable | Exit check |
| --- | --- | --- |
| 0 | Isolated authentication, gateway and service-worker spike | Native login/logout, group checks, deep links and routing proven; architecture selected. |
| 1 | Authenticated desktop shell, explicit manager permissions, read-only Equipment / loans / notes | Two users, two groups, two tabs; denied APIs; no kiosk regression. |
| 2 | People/badges and administrative returns | Correct actor attribution; revocation; last-manager safeguard; reviewed print. |
| 3 | Desktop Imports, label queue and Recovery | Resume and partial completion; no duplicate creates/prints; safe recovery. |
| 4 | Workshop/storage desktop editing and System | Concurrent-save conflicts, location integrity, local-only hardware actions, backup review. |
| 5 | Complete browser walkthrough, independent review, docs and controlled deployment | All acceptance checks pass; backup/rollback ready; current native/kiosk access retained. |

Reuse operations in `ops/returns.py`, `ops/ledger.py`, `ops/native_jobs.py`, `ops/badges.py`, `ops/imports.py`, `ops/workshop.py`, `ops/labels.py`. Introduce a separate authenticated desktop request context rather than weakening local badge/session handlers. Extract reusable UI/data helpers progressively; do not transplant the large inline touchscreen page wholesale into a desktop layout.

## Verification and review

Keep all mutation tests isolated. Operational Homebox receives no synthetic accounts, inventory, badge tokens or physical print jobs during browser automation. Live checks are read-only and bounded.

Meaningful checks:
- Two users, two groups, manager/member, simultaneous tabs and kiosk/browser sessions.
- Native logout, expiry, removed member and role change; no stale-tab writes under a changed actor.
- Direct bookmarked routes, browser Back/forward, reload, keyboard-only navigation, dialogs/Cancel, 1440/1024/800/390px layouts.
- Valid native deep links from a laptop, including photos and import-created records.
- Interrupted or rejected creation, return, account enrollment, badge issuance and printing; preserve key, draft, progress and attribution.
- Printer unavailable/partial output; no automatic repeat after uncertainty.
- CSV duplicate identities, unsaved rows, bulk selection bounds and archived/missing destinations.
- Layout revision conflicts, native parent changes and deleting a drawing without deleting inventory.
- Service-worker-controlled native visit followed by desktop navigation/offline reload; private reads must not be cached.
- Native unavailable, gateway restart and Pi reboot, with local kiosk recovery.

After implementation, a separate read-only reviewer inspects the complete diff and callers, returns actionable findings, and does not edit or deploy. The author fixes findings, reruns relevant tests, and asks for another review when material changes warrant it. Do not treat “No findings” as proof against every possible failure.

## Skills and plugins

Already available:
- **frontend-design:** visual hierarchy, restrained desktop layout, responsive critique.
- **webapp-testing:** Python Playwright interactions, screenshots, browser errors and fixture flows. Existing Pi browser runtime can be reused.
- **review-agent:** independent, read-only, defect-first review after each meaningful implementation slice.
- **GitHub plugin:** installed; available for repository/PR/CI work when used. No PR or external review was created for this planning task.

Optional suggestions from the plugin directory:
- **Superpowers:** additional planning, debugging, test and collaboration workflows.
- **Codex Security:** focused security scan/review for the new authentication boundary.

Both optional plugins were suggested, but installation/connection is not yet confirmed. They are not prerequisites for this plan or for the available local code review and browser testing. Plugins help the development workflow; they do not add native Homebox navigation features by themselves.

## Evidence and current limits

- Repository on the Pi: `/home/user/Desktop/inventory-system`; read `AGENTS.md` before changes.
- Inspected companion: `deploy/kiosk-server.py`, `ops/homebox.py`, `ops/accounts.py`, `kiosk/index.html`, `kiosk/workflow-ui.js`, `kiosk/import-ui.js`, `kiosk/workshop-ui.js`.
- Inspected upstream: pinned v0.26.2 under `upstream/homebox`; native hardcoded navigation in `frontend/layouts/default.vue`. Native cookie/session and API capabilities were inspected from source by the architecture check.
- Primary upstream references: [v0.23.0 basic user management](https://github.com/sysadminsmedia/homebox/releases/tag/v0.23.0), [pinned frontend](https://github.com/sysadminsmedia/homebox/tree/v0.26.2/frontend).
- Current companion is still local-only; native Homebox remains directly reachable on the Pi network on :17745. This planning task has not changed those services, permissions, user records or databases.

The first production milestone should be authenticated read-only desktop context and verified gateway routing. That creates a reliable base for moving the management actions without regressing the touchscreen or duplicating Homebox.
