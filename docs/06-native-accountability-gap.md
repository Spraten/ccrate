# Native accountability gap and proposed extension

Date: 2026-10-02. Investigated unmodified Homebox v0.26.2 at e01dd737238a3fa7e1a6454b37de6c6fc88c86e4. This is a proposal; additional persistent storage is not approved or implemented.

## Requirement

The handoff requires durable checkout/return transactions, custody, operator identity and activity history. A later user must be able to determine who took an asset, when it was returned and whether an interrupted operation completed.

## Native capabilities and evidence

- EntityUpdate supports custom fields, notes, native identity metadata and parent/location relationships. These can represent current state, but the field update itself does not create the required custody transaction history. Source: backend/internal/data/repo/repo_entities.go, EntityUpdate and EntityPatch.
- publishMutationEvent publishes EventEntityMutation with GroupMutationEvent containing only GID. Source: same repository file, publishMutationEvent.
- EventBus uses an in-memory channel and subscriber functions. It has no persistent transaction store or replay. Source: backend/internal/core/services/reporting/eventbus/eventbus.go.
- The schema directory contains entities, fields, users, maintenance and other inventory records, but no native checkout/return or custody transaction schema. Scoped searches of handlers and schemas found no checkout/borrow/custody API.
- Maintenance entries provide dated records, but their API permits PUT and DELETE. They model maintenance rather than checkout transactions; treating every loan as maintenance would change the meaning of native maintenance screens.
- Native users provide names, IDs and group memberships. User settings exist, but their API is self-scoped. Whether borrowers are native users or native person entities is a pending product decision.

## Options

1. A small companion SQLite ledger for operational events only. Homebox stays unmodified and authoritative for asset identity, metadata, locations and attachments. The ledger references native UUIDs and records checkout/return attempts, operator, completion and recovery status. It does not copy the asset catalog. This supports durable accountability but adds a database that must be backed up and reconciled with API writes.
2. Native custom fields only for basic current custody. Minimal persistence footprint, but updates overwrite history and cannot satisfy the handoff's durable transaction/recovery requirements by themselves. This would explicitly reduce scope.
3. Defer checkout until a different native integration solution is selected. No new storage, but no operational checkout yet.

## Recommendation

Option 1, constrained to the native capability gap. Record operation intent and completion with idempotency/recovery handling; keep Homebox updates behind the supported API. A local ledger and Homebox cannot share a database transaction, so interrupted writes require explicit reconciliation before success is shown. Detailed schema and recovery tests follow only after approval.

Badge registry, maps, catalog and other storage are separate decisions; approval of a transaction ledger would not authorize copying inventory or creating every proposed Ops database table.

## Pending approval

User must choose the accountability approach before checkout implementation proceeds. No new database created by this investigation.
