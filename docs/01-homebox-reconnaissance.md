# Homebox Integration Reconnaissance

Date: 2026-10-02. Pinned Homebox release v0.26.2, commit `e01dd737238a3fa7e1a6454b37de6c6fc88c86e4`. The official latest-release API and release page identified this release at inspection time. Source was cloned at this tag without modifications.

## Release Verification and Baseline

ARM64 artifact: `homebox_Linux_arm64.tar.gz`.

SHA256: `a7197a54b830a21be0142c5b4b3dd3a730d5d6a0599aa680d089b4e128d82f12`.

Checksum matched the official checksums list locally and on the Pi. The Pi successfully started the unmodified release with an isolated database. `GET /api/v1/status` returned 200, health true, version 0.26.2 and the pinned commit. `GET /` returned 200. Registration returned 204 and login 200. Unauthenticated entity access returned 401.

The first API-key request failed with 401 because the probe added a Bearer prefix to the login token's existing prefix. Normalizing it resolved the failure. Live probes then verified API-key creation (201), entity-type listing, location and asset creation (201), location filtering, parent filtering, detail/path/tree retrieval, quantity PATCH and rich metadata/custom-field PUT (200), QR generation and label rendering (200), CSV export (200), template listing, collection-export listing, asset ID resolution, key deletion (204), and rejection of the revoked key (401).

Maintenance POST without either date returned 500; the server log reported that completedDate or scheduledDate must be set. Supplying completedDate and cost returned 201. Validate this requirement in the adapter and surface a helpful error; the schema only marks name required. This failure is retained in `api-probe-results.json` as evidence, not hidden as a successful test.

The source/API table below includes additional inspected integration points. Attachment upload/download, template creation, collection export creation/import/restore, mutation subscriptions and printer transport were not tested live. Upstream source remains unchanged.

## API and Source Findings

Prefix all paths below with `/api/v1`. Inspect `backend/app/api/routes.go` alongside the versioned schema; they disagree in some places. For example, source registers `/currencies` and `/users/self/change-password`, while the schema names `/currency` and `/users/change-password`. Source also registers `/labelmaker/entity/{id}`, absent from the published schema. Do not generate an integration client solely from the schema without contract tests.

| Area | Integration points and actual source semantics |
|---|---|
| Inventory | GET and POST `/entities`; GET, PUT, PATCH and DELETE `/entities/{id}` |
| Locations | Unified entities with an entity type whose `isLocation` flag is true; query `/entities?isLocation=true` |
| Relationships | `parentId` controls parent; `/entities/{id}/path` returns ancestry; `/entities/tree?withItems=true` includes items |
| Types | GET/POST `/entity-types`; PUT/DELETE `/entity-types/{id}` |
| Fields | Entity PUT supports structured custom fields; GET `/entities/fields` and `/entities/fields/values?field=...` enumerate field metadata |
| Attachments | POST `/entities/{id}/attachments`; GET/PUT/DELETE `/entities/{id}/attachments/{attachment_id}`; external links are also supported |
| Maintenance | GET/POST `/entities/{id}/maintenance`; global GET `/maintenance`; PUT/DELETE `/maintenance/{id}` |
| Templates | GET/POST `/templates`; GET/PUT/DELETE `/templates/{id}`; POST `/templates/{id}/create-item` |
| Asset lookup | GET `/assets/{id}` resolves Homebox's display asset identifier |
| QR and labels | GET `/qrcode`; label rendering routes for entity, item, asset, location; generating an image is separate from supporting the SUPVAN transport |
| CSV | GET `/entities/export`; POST `/entities/import` |
| Collection backups | POST/GET `/group/exports`; GET `/group/exports/{id}` and download route; POST `/group/import`; restore remains untested |
| API keys | GET/POST `/users/self/api-keys`; DELETE `/users/self/api-keys/{id}`; keys authenticate as the owning user |
| Events | Authenticated `/ws/events` emits mutation notifications; the migration guide describes `entity.mutation` with group ID, not a durable custody ledger |
| Retail barcodes | GET `/products/search-from-barcode?productEAN=...` invokes external UPCItemDB and Open Facts sources, plus optional BarcodeSpider; unsuitable for the offline core workflow |

## Payload and Identifier Constraints

Entity creation uses name, description, quantity, parentId, entityTypeId and tagIds. Rich metadata such as manufacturer, model, serial and fields is supplied through full update or templates. PATCH supports parent, type, quantity and tags; it is not a generic partial update of every field.

PUT sets a complete entity representation, including metadata, tags and custom fields. A safe integration must GET, build a complete update payload, preserve unrelated fields, and verify the result. A partial PUT can lose data. This does not solve concurrent edits; the Ops ownership and reconciliation strategy requires review.

Use the immutable entity UUID as the integration reference. Homebox display asset IDs use its own numeric/formatted representation, so examples such as BAT-0182 must not be assumed to fit its native asset ID. A separate display-code mapping or custom field is a future decision before permanent labels.

The migration guide says entity detail children contain location children; to list stored items, query entities with parentIds. Kit membership must not be assumed equivalent to physical storage hierarchy. Future kit design must test parent behavior and preserve home-location intent.

## Configuration and Recovery

The baseline binds `HBOX_WEB_HOST=127.0.0.1`, `HBOX_WEB_PORT=17745`, stores files under `work/baseline/data`, and uses its own SQLite path. Release checks and analytics are disabled. A generated API key pepper is stored with restrictive permissions and remains stable across restarts. No secret is in these reports.

Source defaults to SQLite with WAL. A raw copy of a running database file alone is not a verified backup. Future backup design must capture a consistent database, attachments, configuration and pepper, plus Ops/catalog/map state. Collection export is promising but experimental in release-line documentation; verify a restore before accepting it as recovery.

Correct release-check configuration is `HBOX_OPTIONS_GITHUB_RELEASE_CHECK=false`; the first probe used a misnamed environment variable. The final baseline was restarted with the correct setting, and status returned an empty latest-release value. Analytics and telemetry were disabled. Short-run RSS was approximately 136 MiB after API probing; startup CPU is not a sustained kiosk benchmark.

Baseline startup is handled by the reconnaissance probe; process PID and log are in `work/baseline`. Production reboot startup, registration policy, integration-account permissions, TLS origin for browser camera access and backups remain unresolved.

## Existing Build and Tests

Homebox has a Go backend, embedded Nuxt web frontend, Go repository/service/handler tests, and frontend Vitest/Playwright tooling. Pinned source specifies Go 1.26.0 and pnpm 10.28.0. No upstream test suite was executed: the Pi lacked build runtimes, and Phase 0 used the official release rather than changing upstream code. Runtime probes are the baseline verification, not a substitute for future workflow tests.

## SUPVAN Feasibility

Candidate: `heeen/supvan-cups`, inspected commit `9fd7af09580c3e710202e5471e77e0b88db0e3bb`, workspace version 0.5.1, MIT license. The source README explicitly lists T50M Pro support, USB hidraw and Bluetooth transports, an IPP printer service, and mock testing. The observed USB VID matches its declared SUPVAN VID 1820.

The code is Rust 2024 with Linux native dependencies such as DBus, libc and LZMA. No inspected manifest declares an x86-only requirement. This makes ARM64 a plausible build target, not a proven compatible driver. Its current Cargo manifest names ipp-printer-app 0.10.0; the fetched GitHub HTML README described an older framework version, so use pinned source and Cargo.lock for reproducibility. On this Pi `/dev/hidraw0` is root-owned mode 0600; the regular user cannot access it without a reviewed device-permission setup. Do not solve this by running the whole kiosk as root.

Next proof: check hidraw permissions, capture loaded label metadata, build a pinned driver with dependencies preserved for offline installation, run a diagnostic and print one test label. Check QR readability, orientation, dimensions, repeatability, reconnect and reboot behavior. Do not configure unattended print retries or consume multiple labels without defining the test.

## Sources

- [Pinned release](https://github.com/sysadminsmedia/homebox/releases/tag/v0.26.2)
- [Pinned routes](https://github.com/sysadminsmedia/homebox/blob/v0.26.2/backend/app/api/routes.go)
- [Pinned migration guide](https://github.com/sysadminsmedia/homebox/blob/v0.26.2/docs/src/content/docs/en/advanced/entity-merge-upgrade.mdx)
- [Pinned entity repository](https://github.com/sysadminsmedia/homebox/blob/v0.26.2/backend/internal/data/repo/repo_entities.go)
- [Pinned product lookup](https://github.com/sysadminsmedia/homebox/blob/v0.26.2/backend/app/api/handlers/v1/v1_ctrl_product_search.go)
- [Printer candidate source](https://github.com/heeen/supvan-cups/tree/9fd7af09580c3e710202e5471e77e0b88db0e3bb)
