"""Atomic local journal primitives for guided workshop shelf checks."""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from ledger import Conflict, Ledger, timestamp, uuid as ledger_uuid
from workshop_views import resolve_workshop_code, scoped_equipment


class CheckAccessDenied(PermissionError):
    """The current trusted context cannot access this shelf-check request."""


def terminal_check_context(client, *, open_admin: bool) -> dict:
    """Bind the Terminal adapter to the configured native service identity."""
    if open_admin is not True:
        raise CheckAccessDenied('Shelf checks are disabled in setup mode')
    try:
        native = client.call('/api/v1/users/self')['item']
        group = ledger_uuid(native['defaultGroupId'])
        actor = ledger_uuid(native['id'])
        if group not in {ledger_uuid(value) for value in native.get('groupIds', [])}:
            raise CheckAccessDenied('Service account is not a member of its default collection')
        client.tenant = group
        collection = client.call('/api/v1/groups')
        collection = collection.get('item', collection)
        if ledger_uuid(collection['id']) != group:
            raise CheckAccessDenied('Native collection changed')
        members = client.call('/api/v1/groups/members')
        if not any(ledger_uuid(row['id']) == actor for row in members):
            raise CheckAccessDenied('Service account is not an active collection member')
    except CheckAccessDenied:
        raise
    except (KeyError, TypeError, ValueError, AttributeError):
        raise CheckAccessDenied('Native service identity is unavailable') from None
    return {'actor': actor, 'group': group, 'manager': True}


def shelf_check_action(store, client, ctx: dict, route: str, data: dict) -> dict | list:
    """Shared route operation dispatch after each adapter establishes its trust context."""
    if any(key in data for key in ('actor', 'actor_id', 'group', 'group_id', 'manager')):
        raise ValueError('Shelf-check identity is supplied by Workshop')
    if route == 'list':
        limit = data.get('limit', 100)
        if type(limit) is not int:
            raise ValueError('History limit must be an integer')
        return store.history(client, ctx, location_id=data.get('location_id'), limit=limit)
    if route == 'get':
        return store.get(client, ctx, data.get('id'))
    if route == 'resolve':
        return store.resolve(client, ctx, data.get('id'), raw=data.get('raw'),
                             selected_entity_id=data.get('selected_entity_id'))
    if route == 'request':
        return store.request(ctx, data.get('request_key'))
    if route == 'start':
        return store.start(client, ctx, location_id=data.get('location_id'),
                           include_nested=data.get('include_nested', False), request_key=data.get('request_key'))
    if route == 'observe':
        return store.observe(client, ctx, data.get('id'), revision=data.get('revision'),
                             entity_id=data.get('entity_id'), method=data.get('method'),
                             observed_quantity=data.get('observed_quantity'), request_key=data.get('request_key'))
    if route == 'notes':
        return store.save_notes(client, ctx, data.get('id'), revision=data.get('revision'),
                                notes=data.get('notes'), request_key=data.get('request_key'))
    if route == 'refresh':
        return store.refresh(client, ctx, data.get('id'), revision=data.get('revision'),
                             request_key=data.get('request_key'))
    if route == 'finish':
        return store.finish(client, ctx, data.get('id'), revision=data.get('revision'),
                            review_fingerprint=data.get('review_fingerprint'), request_key=data.get('request_key'))
    if route == 'cancel':
        return store.cancel(client, ctx, data.get('id'), revision=data.get('revision'),
                            confirmed=data.get('confirmed'), reason=data.get('reason'), request_key=data.get('request_key'))
    raise ValueError('Unknown shelf-check action')


class ShelfChecks:
    SCHEMA_VERSION = 2

    def __init__(self, ledger: Ledger):
        self.ledger = ledger
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        statements = (
            '''CREATE TABLE IF NOT EXISTS shelf_checks(
                id TEXT PRIMARY KEY,
                group_id TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                location_id TEXT NOT NULL,
                include_nested INTEGER NOT NULL DEFAULT 0 CHECK(include_nested IN (0,1)),
                started_at TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('draft','completed','cancelled')),
                revision INTEGER NOT NULL CHECK(revision >= 0),
                original_snapshot_json TEXT NOT NULL,
                reviewed_snapshot_json TEXT,
                review_fingerprint TEXT,
                notes TEXT NOT NULL DEFAULT '',
                completed_at TEXT,
                cancelled_at TEXT,
                cancelled_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )''',
            '''CREATE TABLE IF NOT EXISTS shelf_check_observations(
                check_id TEXT NOT NULL,
                group_id TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                method TEXT NOT NULL,
                observed_quantity INTEGER NOT NULL CHECK(observed_quantity >= 0),
                first_observed_at TEXT NOT NULL,
                last_observed_at TEXT NOT NULL,
                current_path_json TEXT NOT NULL DEFAULT '[]',
                PRIMARY KEY(check_id, entity_id)
            )''',
            '''CREATE TABLE IF NOT EXISTS shelf_check_events(
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                check_id TEXT,
                group_id TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                action TEXT NOT NULL,
                intent_sha256 TEXT NOT NULL,
                revision INTEGER,
                created_at TEXT NOT NULL
            )''',
            '''CREATE TABLE IF NOT EXISTS shelf_check_requests(
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id TEXT NOT NULL,
                request_key TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                action TEXT NOT NULL,
                intent_sha256 TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(group_id, request_key)
            )''',
            '''CREATE TABLE IF NOT EXISTS shelf_check_schema_meta(
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                version INTEGER NOT NULL
            )''',
            '''CREATE TRIGGER IF NOT EXISTS shelf_check_events_immutable_update
                BEFORE UPDATE ON shelf_check_events
                BEGIN SELECT RAISE(ABORT, 'shelf check events are append-only'); END''',
            '''CREATE TRIGGER IF NOT EXISTS shelf_check_events_immutable_delete
                BEFORE DELETE ON shelf_check_events
                BEGIN SELECT RAISE(ABORT, 'shelf check events are append-only'); END''',
            '''CREATE TRIGGER IF NOT EXISTS shelf_check_events_replace_guard
                BEFORE INSERT ON shelf_check_events
                WHEN EXISTS(SELECT 1 FROM shelf_check_events WHERE sequence=NEW.sequence)
                BEGIN SELECT RAISE(ABORT, 'shelf check events are append-only'); END''',
            '''CREATE TRIGGER IF NOT EXISTS shelf_check_requests_immutable_update
                BEFORE UPDATE ON shelf_check_requests
                BEGIN SELECT RAISE(ABORT, 'shelf check requests are immutable'); END''',
            '''CREATE TRIGGER IF NOT EXISTS shelf_check_requests_immutable_delete
                BEFORE DELETE ON shelf_check_requests
                BEGIN SELECT RAISE(ABORT, 'shelf check requests are immutable'); END''',
            '''CREATE TRIGGER IF NOT EXISTS shelf_check_requests_replace_guard
                BEFORE INSERT ON shelf_check_requests
                WHEN EXISTS(SELECT 1 FROM shelf_check_requests
                    WHERE sequence=NEW.sequence OR
                          (group_id=NEW.group_id AND request_key=NEW.request_key))
                BEGIN SELECT RAISE(ABORT, 'shelf check requests are immutable'); END''',
            '''CREATE TRIGGER IF NOT EXISTS shelf_checks_identity_replace_guard
                BEFORE INSERT ON shelf_checks
                WHEN EXISTS(SELECT 1 FROM shelf_checks WHERE id=NEW.id)
                BEGIN SELECT RAISE(ABORT, 'shelf check identity is immutable'); END''',
            '''CREATE TRIGGER IF NOT EXISTS shelf_checks_original_snapshot_immutable
                BEFORE UPDATE OF original_snapshot_json ON shelf_checks
                WHEN NEW.original_snapshot_json IS NOT OLD.original_snapshot_json
                BEGIN SELECT RAISE(ABORT, 'original shelf snapshot is immutable'); END''',
            '''CREATE TRIGGER IF NOT EXISTS shelf_checks_terminal_immutable_update
                BEFORE UPDATE ON shelf_checks
                WHEN OLD.state IN ('completed','cancelled')
                BEGIN SELECT RAISE(ABORT, 'terminal shelf checks are immutable'); END''',
            '''CREATE TRIGGER IF NOT EXISTS shelf_checks_immutable_delete
                BEFORE DELETE ON shelf_checks
                BEGIN SELECT RAISE(ABORT, 'shelf check history is retained'); END''',
        )
        with self.ledger.transaction() as db:
            for statement in statements:
                db.execute(statement)
            observation_columns = {row['name'] for row in db.execute(
                'PRAGMA table_info(shelf_check_observations)')}
            if 'current_path_json' not in observation_columns:
                db.execute("ALTER TABLE shelf_check_observations ADD COLUMN "
                           "current_path_json TEXT NOT NULL DEFAULT '[]'")
            row = db.execute(
                'SELECT version FROM shelf_check_schema_meta WHERE singleton=1').fetchone()
            if row is None:
                db.execute('INSERT INTO shelf_check_schema_meta(singleton,version) VALUES(1,?)',
                           (self.SCHEMA_VERSION,))
            elif row['version'] == 1 and self.SCHEMA_VERSION == 2:
                db.execute('UPDATE shelf_check_schema_meta SET version=? WHERE singleton=1',
                           (self.SCHEMA_VERSION,))
            elif row['version'] != self.SCHEMA_VERSION:
                raise ValueError('Unsupported shelf-check schema metadata version')

    @staticmethod
    def _trusted_context(ctx: dict[str, Any]) -> tuple[str, str]:
        if not isinstance(ctx, dict) or ctx.get('manager') is not True:
            raise CheckAccessDenied('Current shelf-check management access is required')
        try:
            group, actor = ctx['group'], ctx['actor']
            canonical_group, canonical_actor = ledger_uuid(group), ledger_uuid(actor)
        except (KeyError, TypeError, ValueError, AttributeError):
            raise CheckAccessDenied('Current shelf-check identity is unavailable') from None
        if (type(group) is not str or group != canonical_group or
                type(actor) is not str or actor != canonical_actor):
            raise CheckAccessDenied('Current shelf-check identity is not canonical')
        return canonical_group, canonical_actor

    @staticmethod
    def _request_key(value: str) -> str:
        try:
            return ledger_uuid(value)
        except (TypeError, ValueError, AttributeError):
            raise ValueError('Shelf-check request key must be a UUID') from None

    @classmethod
    def _canonical_json(cls, value: Any) -> str:
        cls._validate_json(value)
        return json.dumps(value, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=False, allow_nan=False)

    @classmethod
    def _validate_json(cls, value: Any) -> None:
        if value is None or type(value) in (str, bool, int):
            return
        if type(value) is float:
            if not math.isfinite(value):
                raise ValueError('Shelf-check JSON cannot contain a non-finite number')
            return
        if type(value) is list:
            for item in value:
                cls._validate_json(item)
            return
        if type(value) is dict:
            if any(type(key) is not str for key in value):
                raise ValueError('Shelf-check JSON object keys must be strings')
            for item in value.values():
                cls._validate_json(item)
            return
        raise ValueError('Shelf-check value must contain JSON-compatible data')

    @staticmethod
    def _intent_digest(intent_json: str) -> str:
        return hashlib.sha256(intent_json.encode('utf-8')).hexdigest()

    def request(self, ctx: dict, request_key: str) -> dict:
        group, actor = self._trusted_context(ctx)
        key = self._request_key(request_key)
        with self.ledger.connection() as db:
            row = db.execute('''SELECT actor_id,action,result_json
                FROM shelf_check_requests WHERE group_id=? AND request_key=?''',
                (group, key)).fetchone()
        if row is None:
            return {'status': 'not_started'}
        if row['actor_id'] != actor:
            raise CheckAccessDenied('Shelf-check request belongs to another manager')
        return {'status': 'completed', 'action': row['action'],
                'result': json.loads(row['result_json'])}

    def _apply(self, ctx: dict, action: str, intent: dict, request_key: str,
               change: Callable[[sqlite3.Connection], dict]) -> dict:
        group, actor = self._trusted_context(ctx)
        key = self._request_key(request_key)
        if type(action) is not str or not action or len(action) > 80:
            raise ValueError('Shelf-check action is invalid')
        if not callable(change):
            raise TypeError('Shelf-check change must be callable')
        intent_json = self._canonical_json(intent)
        intent_digest = self._intent_digest(intent_json)

        with self.ledger.transaction() as db:
            foreign = db.execute('''SELECT 1 FROM shelf_check_requests
                WHERE request_key=? AND group_id<>? LIMIT 1''', (key, group)).fetchone()
            if foreign:
                raise CheckAccessDenied('Shelf-check request is bound to another collection')
            prior = db.execute('''SELECT actor_id,action,intent_sha256,result_json
                FROM shelf_check_requests WHERE group_id=? AND request_key=?''',
                (group, key)).fetchone()
            if prior is not None:
                if prior['actor_id'] != actor:
                    raise Conflict('Shelf-check request key belongs to another manager')
                if prior['action'] != action or prior['intent_sha256'] != intent_digest:
                    raise Conflict('Shelf-check request key was already used for another intent')
                return json.loads(prior['result_json'])

            result = change(db)
            if type(result) is not dict:
                raise TypeError('Shelf-check mutation must return a dictionary result')
            result_json = self._canonical_json(result)
            check_id = result.get('id', result.get('check_id'))
            if check_id is not None:
                try:
                    canonical_check_id = ledger_uuid(check_id)
                except (TypeError, ValueError, AttributeError):
                    raise ValueError('Shelf-check result contains an invalid check UUID') from None
                if type(check_id) is not str or canonical_check_id != check_id:
                    raise ValueError('Shelf-check result check UUID must be canonical')
            revision = result.get('revision')
            if revision is not None and (type(revision) is not int or revision < 0):
                raise ValueError('Shelf-check result revision is invalid')
            created_at = timestamp()
            db.execute('''INSERT INTO shelf_check_events
                (check_id,group_id,actor_id,action,intent_sha256,revision,created_at)
                VALUES(?,?,?,?,?,?,?)''',
                (check_id, group, actor, action, intent_digest, revision, created_at))
            db.execute('''INSERT INTO shelf_check_requests
                (group_id,request_key,actor_id,action,intent_sha256,result_json,created_at)
                VALUES(?,?,?,?,?,?,?)''',
                (group, key, actor, action, intent_digest, result_json, created_at))
            return json.loads(result_json)

    @staticmethod
    def _check_id(value: str) -> str:
        try:
            return ledger_uuid(value)
        except (TypeError, ValueError, AttributeError):
            raise ValueError('Shelf-check id must be a UUID') from None

    @classmethod
    def _check_result(cls, db: sqlite3.Connection, check_id: str, group: str,
                      *, client=None, caller_actor: str | None = None) -> dict:
        row = db.execute('SELECT * FROM shelf_checks WHERE id=? AND group_id=?',
                         (check_id, group)).fetchone()
        if row is None:
            raise ValueError('Unknown shelf check')
        result = dict(row)
        result['original_snapshot'] = json.loads(result.pop('original_snapshot_json'))
        expected_ids = {item['id'] for item in result['original_snapshot']['items']}
        reviewed = result.pop('reviewed_snapshot_json')
        result['reviewed_snapshot'], result['changes'] = cls._review_parts(reviewed)
        result['observations'] = []
        for observation in db.execute('''SELECT entity_id,method,observed_quantity,
                first_observed_at,last_observed_at,current_path_json FROM shelf_check_observations
                WHERE check_id=? AND group_id=? ORDER BY entity_id''', (check_id, group)):
            item = dict(observation)
            item['expected'] = item['entity_id'] in expected_ids
            item['current_path'] = json.loads(item.pop('current_path_json'))
            item['status'] = ('not_observed' if item['observed_quantity'] == 0 else
                              'observed' if item['expected'] else 'unexpected_here')
            result['observations'].append(item)
        result['actor_label'] = 'Former C-Crate member'
        owner_active = False
        if client is not None:
            members = client.call('/api/v1/groups/members')
            owner = next((item for item in members if item.get('id') == result['actor_id']), None)
            if owner:
                owner_active = True
                result['actor_label'] = owner.get('name') or result['actor_label']
        result['can_edit'] = bool(caller_actor == result['actor_id'] and result['state'] == 'draft')
        result['point_in_time'] = result['state'] == 'completed'
        result['suspended_reason'] = None
        current = None
        if client is not None:
            row = db.execute('SELECT * FROM shelf_checks WHERE id=? AND group_id=?',
                             (check_id, group)).fetchone()
            try:
                current = cls._capture_snapshot(client, db, row)
            except (ValueError, KeyError, TypeError):
                result['suspended_reason'] = 'The shelf or its current ancestry is unavailable.'
            if not owner_active and not result['suspended_reason']:
                result['suspended_reason'] = 'The original manager is no longer a collection member.'
        result['can_edit'] = bool(result['can_edit'] and owner_active and
                                  not result['suspended_reason'])
        if (result['state'] == 'draft' and current is not None and
                result['reviewed_snapshot'] is not None):
            result['changes'] = cls._snapshot_changes(
                result['original_snapshot'], current, result['reviewed_snapshot'], result['changes'])
        source = (result['reviewed_snapshot'] if result['state'] in ('completed', 'cancelled')
                  and result['reviewed_snapshot'] is not None else current or result['reviewed_snapshot']
                  or result['original_snapshot'])
        result['groups'] = cls._groups(result, source)
        ids = ({item['id'] for item in result['original_snapshot']['items']} |
               {item['id'] for item in source.get('items', [])} |
               {item['entity_id'] for item in result['observations']})
        result['pending_operations'] = []
        if ids:
            pending = db.execute('''SELECT DISTINCT o.* FROM operations o JOIN operation_assets a
                ON a.operation_id=o.id WHERE o.group_id=? AND o.status IN ('pending','review')
                AND a.entity_id IN (%s) ORDER BY o.created_at,o.id''' %
                ','.join('?' for _ in ids), (group, *sorted(ids))).fetchall()
            result['pending_operations'] = [dict(item) for item in pending]
        return result

    @classmethod
    def _snapshot_changes(cls, original: dict, current: dict, previous_review: dict,
                          previous_changes: list | dict | None = None) -> list[dict]:
        baseline = {item['id']: item for item in original['items']}
        latest = {item['id']: item for item in current.get('items', [])}
        added = [latest[key] for key in sorted(latest.keys() - baseline.keys())]
        removed = [baseline[key] for key in sorted(baseline.keys() - latest.keys())]
        old_changes = previous_changes if isinstance(previous_changes, list) else []
        removed_ids = {item['id'] for item in removed}
        for change in old_changes:
            if change.get('kind') not in ('added', 'removed'):
                continue
            for item in change.get('items', []):
                if item.get('id') not in latest and item.get('id') not in baseline and \
                        item.get('id') not in removed_ids:
                    removed.append(item)
                    removed_ids.add(item['id'])
        removed.sort(key=lambda item: item['id'])
        changed, renamed = [], []
        for key in sorted(baseline.keys() & latest.keys()):
            before, after = baseline[key], latest[key]
            fields = [field for field in ('parent_id', 'quantity', 'archived', 'custody')
                      if before.get(field) != after.get(field)]
            if cls._path_ids(before.get('path')) != cls._path_ids(after.get('path')):
                fields.append('path')
            if fields:
                changed.append({'id': key, 'before': before, 'after': after, 'fields': fields})
            elif before.get('name') != after.get('name') or before.get('path') != after.get('path'):
                renamed.append({'id': key, 'before': before, 'after': after})
        observed_before = {item['id']: item for item in previous_review.get('observed_records', [])}
        observed_after = {item['id']: item for item in current.get('observed_records', [])}
        observed_changes = []
        for key in sorted(observed_before.keys() | observed_after.keys()):
            before, after = observed_before.get(key), observed_after.get(key)
            if before is None or after is None:
                observed_changes.append({'id': key, 'before': before, 'after': after,
                                         'fields': ['availability']})
                continue
            fields = [field for field in ('active', 'parent_id', 'quantity', 'archived', 'custody')
                      if before.get(field) != after.get(field)]
            if cls._path_ids(before.get('path')) != cls._path_ids(after.get('path')):
                fields.append('path')
            elif before.get('path') != after.get('path'):
                fields.append('path_name')
            if before.get('name') != after.get('name') and not fields:
                fields.append('name')
            if fields:
                observed_changes.append({'id': key, 'before': before, 'after': after,
                                         'fields': fields})
        for change in old_changes:
            if change.get('kind') == 'observed':
                known = {cls._canonical_json(item) for item in observed_changes}
                for item in change.get('items', []):
                    encoded = cls._canonical_json(item)
                    if encoded not in known:
                        observed_changes.append(item)
                        known.add(encoded)
        changes = [{'kind': 'added', 'items': added}, {'kind': 'removed', 'items': removed},
                   {'kind': 'changed', 'items': changed}, {'kind': 'renamed', 'items': renamed},
                   {'kind': 'observed', 'items': observed_changes}]
        old_location, new_location = original['location'], current['location']
        if (old_location.get('parent_id') != new_location.get('parent_id') or
                old_location.get('archived') != new_location.get('archived') or
                cls._path_ids(old_location.get('path')) != cls._path_ids(new_location.get('path'))):
            changes.append({'kind': 'location', 'items': [{'before': original['location'],
                                                            'after': current['location']}]})
        elif old_location.get('path') != new_location.get('path') or \
                old_location.get('name') != new_location.get('name'):
            changes.append({'kind': 'location_renamed',
                            'items': [{'before': old_location, 'after': new_location}]})
        return changes

    @classmethod
    def _groups(cls, result: dict, snapshot: dict) -> dict:
        groups = {key: [] for key in ('observed_here', 'not_observed', 'checked_out', 'unexpected_here')}
        original = {item['id']: item for item in result['original_snapshot']['items']}
        observations = {item['entity_id']: item for item in result['observations']}
        items = {item['id']: item for item in snapshot.get('items', [])}
        for entity_id in sorted(items):
            item = items[entity_id]
            obs = observations.get(entity_id)
            if obs and obs['observed_quantity'] > 0:
                groups['observed_here'].append({**item, 'expected': True,
                    'expected_quantity': item['quantity'], 'observed_quantity': obs['observed_quantity'],
                    'quantity_difference': obs['observed_quantity'] - item['quantity'],
                    'original_quantity': original.get(entity_id, {}).get('quantity'),
                    'original_path': original.get(entity_id, {}).get('path'),
                    'current_path': item.get('path'), 'available': True,
                    'custody_conflict': bool(item.get('custody', {}).get('checked_out'))})
            elif item.get('custody', {}).get('checked_out'):
                groups['checked_out'].append({**item, 'expected': True, 'available': True,
                    'expected_quantity': item['quantity'], 'observed_quantity': 0,
                    'quantity_difference': -item['quantity'], 'physical_expected': False,
                    'original_quantity': original.get(entity_id, {}).get('quantity'),
                    'original_path': original.get(entity_id, {}).get('path'),
                    'current_path': item.get('path')})
            else:
                groups['not_observed'].append({**item, 'expected': True, 'available': True,
                    'expected_quantity': item['quantity'], 'observed_quantity': 0,
                    'quantity_difference': -item['quantity'], 'physical_expected': True,
                    'original_quantity': original.get(entity_id, {}).get('quantity'),
                    'original_path': original.get(entity_id, {}).get('path'),
                    'current_path': item.get('path')})
        for item in snapshot.get('observed_records', []):
            entity_id = item['id']
            obs = observations.get(entity_id)
            if entity_id in items or obs is None or obs['observed_quantity'] == 0:
                continue
            if item.get('active'):
                expected_quantity = original.get(entity_id, {}).get('quantity', 0)
                entry = {**item, 'expected': entity_id in original,
                    'expected_quantity': expected_quantity,
                    'observed_quantity': obs['observed_quantity'], 'available': True,
                    'quantity_difference': obs['observed_quantity'] - expected_quantity,
                    'original_quantity': original.get(entity_id, {}).get('quantity'),
                    'physical_expected': True,
                    'original_path': original.get(entity_id, {}).get('path') or obs.get('current_path'),
                    'current_path': item.get('path'), 'custody_conflict':
                    bool(item.get('custody', {}).get('checked_out'))}
                groups['observed_here' if entry['custody_conflict'] else 'unexpected_here'].append(entry)
            else:
                groups['observed_here'].append({**item, 'expected': entity_id in original,
                    'expected_quantity': original.get(entity_id, {}).get('quantity', 0),
                    'observed_quantity': obs['observed_quantity'], 'available': False,
                    'quantity_difference': obs['observed_quantity'] -
                        original.get(entity_id, {}).get('quantity', 0),
                    'original_quantity': original.get(entity_id, {}).get('quantity'),
                    'physical_expected': False,
                    'original_path': original.get(entity_id, {}).get('path') or obs.get('current_path'),
                    'current_path': item.get('path') or obs.get('current_path'),
                    'custody_conflict': bool(item.get('custody', {}).get('checked_out'))})
        for obs in result['observations']:
            if obs['entity_id'] not in items and obs['entity_id'] not in {
                    row['id'] for row in snapshot.get('observed_records', [])} and obs['observed_quantity'] > 0:
                groups['observed_here'].append({'id': obs['entity_id'], 'expected': False,
                    'expected_quantity': 0, 'observed_quantity': obs['observed_quantity'],
                    'quantity_difference': obs['observed_quantity'], 'physical_expected': False,
                    'available': False, 'original_path': obs['current_path'],
                    'current_path': obs['current_path'], 'custody_conflict': False})
        return groups

    @classmethod
    def _owned_draft(cls, db: sqlite3.Connection, group: str, actor: str,
                     check_id: str, revision: int | None = None) -> sqlite3.Row:
        row = db.execute('SELECT * FROM shelf_checks WHERE id=? AND group_id=?',
                         (check_id, group)).fetchone()
        if row is None:
            raise ValueError('Unknown shelf check')
        if row['actor_id'] != actor:
            raise CheckAccessDenied('Shelf check belongs to another manager')
        if row['state'] != 'draft':
            raise Conflict('Only a draft shelf check can be changed')
        if revision is not None:
            if type(revision) is not int or revision < 0:
                raise ValueError('Shelf-check revision is invalid')
            if row['revision'] != revision:
                raise Conflict('Shelf check changed; refresh before saving')
        return row

    @staticmethod
    def _snapshot_entity(client, entity: dict) -> dict:
        resolved = resolve_workshop_code(client, entity['id'])
        candidate = next((row for row in resolved['candidates']
                          if row.get('id') == entity['id'] and not row.get('is_location')), None)
        path = candidate.get('path') if candidate else None
        if (resolved.get('entity_id') != entity['id'] or candidate is None or not path or
                path[-1].get('id') != entity['id']):
            raise ValueError('Expected equipment changed or is unavailable')
        quantity = entity.get('quantity', 1)
        if type(quantity) is not int or quantity < 0:
            raise ValueError('Native equipment quantity is invalid')
        parent = entity.get('parent')
        return {'id': entity['id'], 'name': entity.get('name') or '',
                'quantity': quantity, 'parent_id': parent.get('id') if isinstance(parent, dict) else None,
                'archived': bool(entity.get('archived', False)),
                'native_updated_at': entity.get('updatedAt'),
                'native_version': entity.get('version'), 'path': path}

    @classmethod
    def _snapshot_fingerprint(cls, snapshot: dict) -> str:
        items = []
        for item in snapshot['items']:
            value = {key: item.get(key) for key in
                     ('id', 'parent_id', 'quantity', 'archived', 'custody')}
            value['path'] = [{'id': part.get('id')} for part in item.get('path', [])]
            items.append(value)
        observed = []
        for item in snapshot.get('observed_records', []):
            value = {key: item.get(key) for key in
                     ('id', 'active', 'parent_id', 'quantity', 'archived', 'custody')}
            value['path'] = [{'id': part.get('id')} for part in item.get('path', [])]
            observed.append(value)
        location = snapshot['location']
        payload = {'location_id': location['id'],
                   'location_parent_id': location.get('parent_id'),
                   'location_archived': location.get('archived', False),
                   'location_path': [{'id': part.get('id')}
                                     for part in location.get('path', [])],
                   'include_nested': snapshot['include_nested'], 'items': items,
                   'observed_records': observed}
        return hashlib.sha256(cls._canonical_json(payload).encode()).hexdigest()

    @staticmethod
    def _path_ids(path: list[dict] | None) -> list[str | None]:
        return [item.get('id') for item in path or []]

    @classmethod
    def _capture_snapshot(cls, client, db, row) -> dict:
        location_id = row['location_id']
        resolution = resolve_workshop_code(client, location_id)
        location = next((item for item in resolution.get('candidates', [])
                         if item.get('id') == location_id and item.get('is_location')), None)
        if (resolution.get('entity_id') != location_id or location is None or
                not location.get('path') or location['path'][-1].get('id') != location_id):
            raise ValueError('Shelf-check location or ancestry is unavailable')
        location_entity = client.entity(location_id)
        items = [cls._snapshot_entity(client, entity) for entity in
                 scoped_equipment(client, location_id, include_nested=bool(row['include_nested']))]
        for item in items:
            custody = db.execute('SELECT actor_id,operation_id FROM custody '
                                 'WHERE group_id=? AND entity_id=?',
                                 (row['group_id'], item['id'])).fetchone()
            item['custody'] = ({'checked_out': True, 'actor_id': custody['actor_id'],
                                'operation_id': custody['operation_id']} if custody else
                               {'checked_out': False, 'actor_id': None, 'operation_id': None})
        items.sort(key=lambda item: item['id'])
        expected_ids = {item['id'] for item in items}
        observed_records = []
        for observation in db.execute('''SELECT entity_id,current_path_json
            FROM shelf_check_observations WHERE check_id=? AND group_id=? ORDER BY entity_id''',
            (row['id'], row['group_id'])):
            entity_id = observation['entity_id']
            if entity_id in expected_ids:
                continue
            try:
                entity = client.entity(entity_id)
            except (KeyError, TypeError, ValueError):
                entity = {'id': entity_id, 'name': '', 'quantity': 0, 'parent': None,
                          'archived': True, 'entityType': {'isLocation': False}}
            resolved = resolve_workshop_code(client, entity_id)
            candidate = next((item for item in resolved.get('candidates', [])
                              if item.get('id') == entity_id and not item.get('is_location')), None)
            path = candidate.get('path') if candidate else None
            active = bool(not entity.get('archived') and path and path[-1].get('id') == entity_id)
            quantity = entity.get('quantity', 1)
            if type(quantity) is not int or quantity < 0:
                quantity = 0
            parent = entity.get('parent')
            record = {'id': entity_id, 'name': entity.get('name') or '', 'active': active,
                      'quantity': quantity,
                      'parent_id': parent.get('id') if isinstance(parent, dict) else None,
                      'archived': bool(entity.get('archived', False)),
                      'native_updated_at': entity.get('updatedAt'),
                      'native_version': entity.get('version'),
                      'path': path or json.loads(observation['current_path_json'])}
            custody = db.execute('SELECT actor_id,operation_id FROM custody '
                                 'WHERE group_id=? AND entity_id=?',
                                 (row['group_id'], entity_id)).fetchone()
            record['custody'] = ({'checked_out': True, 'actor_id': custody['actor_id'],
                                  'operation_id': custody['operation_id']} if custody else
                                 {'checked_out': False, 'actor_id': None, 'operation_id': None})
            observed_records.append(record)
        parent = location_entity.get('parent')
        return {'location': {'id': location_id, 'name': location.get('name') or '',
                             'path': location.get('path') or [],
                             'parent_id': parent.get('id') if isinstance(parent, dict) else None,
                             'archived': bool(location_entity.get('archived', False)),
                             'native_updated_at': location_entity.get('updatedAt'),
                             'native_version': location_entity.get('version')},
                'include_nested': bool(row['include_nested']), 'items': items,
                'observed_records': observed_records}

    @classmethod
    def _review_record(cls, snapshot: dict, changes: dict | None = None) -> dict:
        return {'snapshot': snapshot, 'changes': changes or
                {kind: {'items': []} for kind in ('added', 'removed', 'changed', 'renamed')}}

    @classmethod
    def _review_parts(cls, raw: str | None) -> tuple[dict | None, dict]:
        empty = {kind: {'items': []} for kind in ('added', 'removed', 'changed', 'renamed')}
        if not raw:
            return None, empty
        value = json.loads(raw)
        if isinstance(value, dict) and isinstance(value.get('snapshot'), dict):
            return value['snapshot'], value.get('changes') or empty
        return value, empty

    def start(self, client, ctx: dict, *, location_id: str, include_nested: bool = False,
              request_key: str) -> dict:
        group, actor = self._trusted_context(ctx)
        if type(include_nested) is not bool:
            raise ValueError('Nested scope must be a boolean')
        try:
            location = ledger_uuid(location_id)
        except (TypeError, ValueError, AttributeError):
            raise ValueError('Choose an available native location') from None

        def create(db):
            resolved_location = resolve_workshop_code(client, location)
            location_candidate = next((row for row in resolved_location['candidates']
                                       if row.get('id') == location), None)
            if (resolved_location.get('entity_id') != location or location_candidate is None or
                    not location_candidate.get('is_location') or
                    not location_candidate.get('path') or
                    location_candidate['path'][-1].get('id') != location):
                raise ValueError('Choose an available native location')
            location_entity = client.entity(location)
            entities = scoped_equipment(client, location, include_nested=include_nested)
            items = [self._snapshot_entity(client, entity) for entity in entities]
            items.sort(key=lambda row: row['id'])
            for item in items:
                custody = db.execute('''SELECT actor_id,operation_id FROM custody
                    WHERE group_id=? AND entity_id=?''', (group, item['id'])).fetchone()
                item['custody'] = ({'checked_out': True, 'actor_id': custody['actor_id'],
                                   'operation_id': custody['operation_id']} if custody else
                                  {'checked_out': False, 'actor_id': None, 'operation_id': None})
            location_parent = location_entity.get('parent')
            snapshot = {'location': {'id': location, 'name': location_candidate.get('name') or '',
                                     'path': location_candidate.get('path') or [],
                                     'parent_id': location_parent.get('id') if isinstance(location_parent, dict) else None,
                                     'archived': bool(location_entity.get('archived', False)),
                                     'native_updated_at': location_entity.get('updatedAt'),
                                     'native_version': location_entity.get('version')},
                        'include_nested': include_nested, 'items': items}
            snapshot_json = self._canonical_json(snapshot)
            fingerprint = self._snapshot_fingerprint(snapshot)
            started = timestamp()
            check_id = str(uuid4())
            db.execute('''INSERT INTO shelf_checks
                (id,group_id,actor_id,location_id,include_nested,started_at,state,revision,
                 original_snapshot_json,reviewed_snapshot_json,review_fingerprint,notes,created_at,updated_at)
                VALUES(?,?,?,?,?,?,'draft',0,?,?,?,'',?,?)''',
                (check_id, group, actor, location, int(include_nested), started,
                 snapshot_json, self._canonical_json(self._review_record(snapshot)), fingerprint,
                 started, started))
            return self._check_result(db, check_id, group, client=client, caller_actor=actor)

        return self._apply(ctx, 'start', {'location_id': location,
                           'include_nested': include_nested}, request_key, create)

    def resolve(self, client, ctx: dict, check_id: str, *, raw: str,
                selected_entity_id: str | None = None) -> dict:
        group, actor = self._trusted_context(ctx)
        check_id = self._check_id(check_id)
        with self.ledger.connection() as db:
            row = db.execute('SELECT * FROM shelf_checks WHERE id=? AND group_id=?',
                             (check_id, group)).fetchone()
            if row is None:
                raise ValueError('Unknown shelf check')
            if row['actor_id'] != actor:
                raise CheckAccessDenied('Shelf check belongs to another manager')
            snapshot = json.loads(row['original_snapshot_json'])
            expected = {item['id'] for item in snapshot['items']}
        resolution = resolve_workshop_code(client, raw)
        candidates = []
        for candidate in resolution.get('candidates', []):
            if not candidate.get('is_location') and candidate.get('path'):
                candidates.append({'id': candidate['id'], 'name': candidate.get('name') or '',
                                   'path': candidate['path'],
                                   'expected': candidate['id'] in expected})
        candidate_ids = {candidate['id'] for candidate in candidates}
        selected = None
        location_candidate = next((candidate for candidate in resolution.get('candidates', [])
                                   if candidate.get('is_location')), None)
        if selected_entity_id is not None:
            selected = self._check_id(selected_entity_id)
            if selected not in candidate_ids:
                raise ValueError('Selected equipment is not one of the eligible candidates')
        elif resolution.get('entity_id') in candidate_ids:
            selected = resolution['entity_id']
        message = resolution.get('message') or ''
        if location_candidate is not None:
            message = 'A location cannot be recorded as observed equipment.'
        elif resolution.get('entity_id') and resolution['entity_id'] not in expected and candidates:
            message = 'Active equipment is outside the frozen scope and can be recorded as unexpected.'
        elif resolution.get('candidates') and not candidates:
            message = 'This code does not identify active equipment in this collection.'
        return {'kind': resolution.get('kind', 'invalid'), 'entity_id': selected,
                'candidates': candidates, 'message': message}

    def observe(self, client, ctx: dict, check_id: str, *, revision: int, entity_id: str,
                method: str, observed_quantity: int | None = None, request_key: str) -> dict:
        group, actor = self._trusted_context(ctx)
        check_id = self._check_id(check_id)
        if type(revision) is not int or revision < 0:
            raise ValueError('Shelf-check revision is invalid')
        try:
            entity_id = ledger_uuid(entity_id)
        except (TypeError, ValueError, AttributeError):
            raise ValueError('Expected equipment id must be a UUID') from None
        if method not in ('scan', 'visual'):
            raise ValueError('Observation method must be scan or visual')

        def save(db):
            row = self._owned_draft(db, group, actor, check_id, revision)
            current_location = resolve_workshop_code(client, row['location_id'])
            location_candidate = next((candidate for candidate in current_location.get('candidates', [])
                                       if candidate.get('id') == row['location_id']), None)
            location_path = location_candidate.get('path') if location_candidate else None
            if (current_location.get('entity_id') != row['location_id'] or location_candidate is None or
                    not location_candidate.get('is_location') or not location_path or
                    location_path[-1].get('id') != row['location_id']):
                raise ValueError('Shelf-check location or ancestry is unavailable')
            current = resolve_workshop_code(client, entity_id)
            candidate = next((candidate for candidate in current.get('candidates', [])
                              if candidate.get('id') == entity_id), None)
            current_path = candidate.get('path') if candidate else None
            if (current.get('entity_id') != entity_id or candidate is None or
                    candidate.get('is_location') or not current_path or
                    current_path[-1].get('id') != entity_id):
                raise ValueError('Expected equipment is no longer active equipment')
            current_snapshot = json.loads(row['original_snapshot_json'])
            expected_item = next((item for item in current_snapshot['items']
                                  if item['id'] == entity_id), None)
            if expected_item is not None:
                expected_quantity = expected_item['quantity']
            else:
                try:
                    native_entity = client.entity(entity_id)
                except (KeyError, TypeError, ValueError):
                    raise ValueError('Equipment is unavailable in this collection') from None
                expected_quantity = native_entity.get('quantity', 1)
                if type(expected_quantity) is not int or expected_quantity < 0:
                    raise ValueError('Native equipment quantity is invalid')
            quantity = observed_quantity
            if quantity is None and expected_quantity == 1:
                quantity = 1
            if type(quantity) is not int or quantity < 0:
                raise ValueError('Observed quantity must be an explicit nonnegative integer')
            now = timestamp()
            db.execute('''INSERT INTO shelf_check_observations
                (check_id,group_id,entity_id,method,observed_quantity,first_observed_at,last_observed_at,
                 current_path_json)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(check_id,entity_id) DO UPDATE SET
                    method=excluded.method,observed_quantity=excluded.observed_quantity,
                    last_observed_at=excluded.last_observed_at,
                    current_path_json=excluded.current_path_json''',
                (check_id, group, entity_id, method, quantity, now, now,
                 self._canonical_json(current_path)))
            next_revision = revision + 1
            db.execute('UPDATE shelf_checks SET revision=?,updated_at=? WHERE id=? AND revision=?',
                       (next_revision, now, check_id, revision))
            return self._check_result(db, check_id, group, client=client, caller_actor=actor)

        intent = {'check_id': check_id, 'revision': revision, 'entity_id': entity_id,
                  'method': method, 'observed_quantity': observed_quantity}
        return self._apply(ctx, 'observe', intent, request_key, save)

    def save_notes(self, client, ctx: dict, check_id: str, *, revision: int,
                   notes: str, request_key: str) -> dict:
        group, actor = self._trusted_context(ctx)
        check_id = self._check_id(check_id)
        if type(notes) is not str or len(notes) > 1000:
            raise ValueError('Notes must be plain text of at most 1000 characters')
        if type(revision) is not int or revision < 0:
            raise ValueError('Shelf-check revision is invalid')

        def save(db):
            row = self._owned_draft(db, group, actor, check_id, revision)
            members = client.call('/api/v1/groups/members')
            if not any(item.get('id') == row['actor_id'] for item in members):
                raise Conflict('This shelf check is suspended; its original manager is no longer active')
            try:
                self._capture_snapshot(client, db, row)
            except (ValueError, KeyError, TypeError) as exc:
                raise Conflict('This shelf check is suspended; refresh is required before editing') from exc
            now = timestamp()
            next_revision = revision + 1
            db.execute('UPDATE shelf_checks SET notes=?,revision=?,updated_at=? WHERE id=? AND revision=?',
                       (notes, next_revision, now, check_id, revision))
            return self._check_result(db, check_id, group, client=client, caller_actor=actor)

        return self._apply(ctx, 'save_notes', {'check_id': check_id, 'revision': revision,
                           'notes': notes}, request_key, save)

    def refresh(self, client, ctx: dict, check_id: str, *, revision: int,
                request_key: str) -> dict:
        group, actor = self._trusted_context(ctx)
        check_id = self._check_id(check_id)
        if type(revision) is not int or revision < 0:
            raise ValueError('Shelf-check revision is invalid')

        def apply(db):
            row = self._owned_draft(db, group, actor, check_id, revision)
            try:
                current = self._capture_snapshot(client, db, row)
            except (ValueError, KeyError, TypeError) as exc:
                raise Conflict('Shelf or current ancestry is unavailable; this check cannot refresh') from exc
            original = json.loads(row['original_snapshot_json'])
            previous, prior_changes = self._review_parts(row['reviewed_snapshot_json'])
            previous = previous or original
            changes = self._snapshot_changes(original, current, previous, prior_changes)
            fingerprint = self._snapshot_fingerprint(current)
            now = timestamp()
            db.execute('''UPDATE shelf_checks SET reviewed_snapshot_json=?,review_fingerprint=?,
                revision=?,updated_at=? WHERE id=? AND revision=?''',
                (self._canonical_json(self._review_record(current, changes)), fingerprint,
                 revision + 1, now, check_id, revision))
            return self._check_result(db, check_id, group, client=client, caller_actor=actor)

        return self._apply(ctx, 'refresh', {'check_id': check_id, 'revision': revision},
                           request_key, apply)

    def finish(self, client, ctx: dict, check_id: str, *, revision: int,
               review_fingerprint: str, request_key: str) -> dict:
        group, actor = self._trusted_context(ctx)
        check_id = self._check_id(check_id)
        if type(revision) is not int or revision < 0:
            raise ValueError('Shelf-check revision is invalid')
        if type(review_fingerprint) is not str or len(review_fingerprint) != 64:
            raise ValueError('Review fingerprint is invalid')

        def apply(db):
            row = self._owned_draft(db, group, actor, check_id, revision)
            try:
                current = self._capture_snapshot(client, db, row)
            except (ValueError, KeyError, TypeError) as exc:
                raise Conflict('Shelf or current ancestry is unavailable; this check cannot finish') from exc
            fingerprint = self._snapshot_fingerprint(current)
            if row['review_fingerprint'] != review_fingerprint or fingerprint != review_fingerprint:
                raise Conflict('Native facts changed; refresh the review before completing')
            now = timestamp()
            _, changes = self._review_parts(row['reviewed_snapshot_json'])
            if isinstance(changes, dict):
                changes_list = [{'kind': key, 'items': value.get('items', [])}
                                for key, value in changes.items()]
            else:
                changes_list = changes
            db.execute('''UPDATE shelf_checks SET state='completed',completed_at=?,revision=?,
                reviewed_snapshot_json=?,review_fingerprint=?,updated_at=? WHERE id=? AND revision=?''',
                (now, revision + 1, self._canonical_json(self._review_record(current, changes_list)),
                 fingerprint, now, check_id, revision))
            result = self._check_result(db, check_id, group, client=client, caller_actor=actor)
            result['point_in_time'] = True
            return result

        return self._apply(ctx, 'finish', {'check_id': check_id, 'revision': revision,
                           'review_fingerprint': review_fingerprint}, request_key, apply)

    def cancel(self, client, ctx: dict, check_id: str, *, revision: int, confirmed: bool,
               reason: str, request_key: str) -> dict:
        group, actor = self._trusted_context(ctx)
        check_id = self._check_id(check_id)
        if type(revision) is not int or revision < 0:
            raise ValueError('Shelf-check revision is invalid')
        if type(confirmed) is not bool or type(reason) is not str or not 1 <= len(reason.strip()) <= 1000:
            raise ValueError('Cancellation requires confirmation and a reason')

        def apply(db):
            row = db.execute('SELECT * FROM shelf_checks WHERE id=? AND group_id=?',
                             (check_id, group)).fetchone()
            if row is None:
                raise ValueError('Unknown shelf check')
            if row['state'] != 'draft':
                raise Conflict('Only a draft shelf check can be cancelled')
            if row['revision'] != revision:
                raise Conflict('Shelf check changed; refresh before saving')
            if row['actor_id'] != actor and not confirmed:
                raise ValueError('A different manager must confirm cancellation')
            now = timestamp()
            db.execute('''UPDATE shelf_checks SET state='cancelled',cancelled_at=?,cancelled_by=?,
                revision=?,updated_at=? WHERE id=? AND revision=?''',
                (now, actor, revision + 1, now, check_id, revision))
            result = self._check_result(db, check_id, group, client=client, caller_actor=actor)
            result['cancel_reason'] = reason.strip()
            return result

        return self._apply(ctx, 'cancel', {'check_id': check_id, 'revision': revision,
                           'confirmed': confirmed, 'reason': reason}, request_key, apply)

    def get(self, client, ctx: dict, check_id: str) -> dict:
        group, actor = self._trusted_context(ctx)
        check_id = self._check_id(check_id)
        with self.ledger.connection() as db:
            result = self._check_result(db, check_id, group, client=client, caller_actor=actor)
            if result['state'] == 'cancelled':
                for saved in db.execute('''SELECT result_json FROM shelf_check_requests
                    WHERE group_id=? AND action='cancel' ORDER BY sequence DESC''', (group,)):
                    saved_result = json.loads(saved['result_json'])
                    if saved_result.get('id') == check_id:
                        result['cancel_reason'] = saved_result.get('cancel_reason')
                        break
            return result

    def history(self, client, ctx: dict, *, location_id: str | None = None,
                limit: int = 100) -> list[dict]:
        group, _ = self._trusted_context(ctx)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('History limit must be between 1 and 100')
        location = self._check_id(location_id) if location_id is not None else None
        with self.ledger.connection() as db:
            if location is None:
                rows = db.execute('SELECT id FROM shelf_checks WHERE group_id=? '
                                  'ORDER BY created_at DESC,id DESC LIMIT ?', (group, limit)).fetchall()
            else:
                rows = db.execute('SELECT id FROM shelf_checks WHERE group_id=? AND location_id=? '
                                  'ORDER BY created_at DESC,id DESC LIMIT ?',
                                  (group, location, limit)).fetchall()
        return [self.get(client, ctx, row['id']) for row in rows]
