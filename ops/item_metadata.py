"""Collection-scoped notes and links for native Homebox items."""
import hashlib
import json
import re

from ledger import Conflict, timestamp, uuid


def _field(value):
    if not isinstance(value, str):
        raise ValueError('Field names must be text.')
    value = re.sub(r'\s+', ' ', value.strip()).casefold()
    if not value or len(value) > 120:
        raise ValueError('Enter a valid field name.')
    return value


class ItemMetadata:
    def __init__(self, ledger):
        self.ledger = ledger
        with ledger.connection() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS item_field_notes(
              group_id TEXT NOT NULL, entity_id TEXT NOT NULL, field_name TEXT NOT NULL,
              note TEXT NOT NULL, actor_id TEXT NOT NULL, request_key TEXT NOT NULL,
              PRIMARY KEY(group_id,entity_id,field_name));
            CREATE TABLE IF NOT EXISTS item_relations(
              group_id TEXT NOT NULL, entity_a TEXT NOT NULL, entity_b TEXT NOT NULL,
              actor_id TEXT NOT NULL, request_key TEXT NOT NULL, created_at TEXT NOT NULL,
              PRIMARY KEY(group_id,entity_a,entity_b), CHECK(entity_a < entity_b));
            CREATE TABLE IF NOT EXISTS item_metadata_requests(
              group_id TEXT NOT NULL, request_key TEXT NOT NULL, request_hash TEXT NOT NULL,
              PRIMARY KEY(group_id,request_key));
            ''')

    def _request(self, db, group, key, action, payload):
        key = uuid(key)
        digest = hashlib.sha256(json.dumps([action, payload], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        row = db.execute('SELECT request_hash FROM item_metadata_requests WHERE group_id=? AND request_key=?', (group, key)).fetchone()
        if row:
            if row['request_hash'] != digest:
                raise Conflict('Request key was already used for another metadata change.')
            return False
        db.execute('INSERT INTO item_metadata_requests VALUES(?,?,?)', (group, key, digest))
        return True

    def save_field_notes(self, group_id, actor_id, entity_id, fields, request_key):
        group, actor, entity = uuid(group_id), uuid(actor_id), uuid(entity_id)
        if not isinstance(fields, list) or len(fields) > 100:
            raise ValueError('Provide up to 100 field notes.')
        normalized = {}
        for entry in fields:
            if not isinstance(entry, dict) or not isinstance(entry.get('note'), str):
                raise ValueError('Each field note needs a name and note.')
            name = _field(entry.get('name'))
            note = entry['note'].strip()
            if len(note) > 2000:
                raise ValueError('Field notes must be 2000 characters or fewer.')
            if name in normalized:
                raise ValueError('Field names must be unique.')
            if note:
                normalized[name] = note
        payload = [entity, sorted(normalized.items())]
        with self.ledger.transaction() as db:
            if not self._request(db, group, request_key, 'field_notes', payload):
                return self.field_notes(group, entity)
            db.execute('DELETE FROM item_field_notes WHERE group_id=? AND entity_id=?', (group, entity))
            db.executemany('INSERT INTO item_field_notes VALUES(?,?,?,?,?,?)',
                [(group, entity, name, note, actor, uuid(request_key)) for name, note in normalized.items()])
        return normalized

    def field_notes(self, group_id, entity_id):
        with self.ledger.connection() as db:
            return {r['field_name']: r['note'] for r in db.execute(
                'SELECT field_name,note FROM item_field_notes WHERE group_id=? AND entity_id=? ORDER BY field_name',
                (uuid(group_id), uuid(entity_id)))}

    def add_related(self, group_id, actor_id, entity_a, entity_b, request_key):
        group, actor, a, b = uuid(group_id), uuid(actor_id), uuid(entity_a), uuid(entity_b)
        if a == b: raise ValueError('Choose two different items.')
        a, b = sorted((a, b)); payload = [a, b]
        with self.ledger.transaction() as db:
            if self._request(db, group, request_key, 'related_add', payload):
                db.execute('INSERT OR IGNORE INTO item_relations VALUES(?,?,?,?,?,?)',
                           (group, a, b, actor, uuid(request_key), timestamp()))

    def remove_related(self, group_id, actor_id, entity_a, entity_b, request_key):
        group, actor, a, b = uuid(group_id), uuid(actor_id), uuid(entity_a), uuid(entity_b)
        if a == b: raise ValueError('Choose two different items.')
        a, b = sorted((a, b)); payload = [a, b]
        with self.ledger.transaction() as db:
            if self._request(db, group, request_key, 'related_remove', payload):
                db.execute('DELETE FROM item_relations WHERE group_id=? AND entity_a=? AND entity_b=?', (group, a, b))

    def related_items(self, group_id, entity_id):
        group, entity = uuid(group_id), uuid(entity_id)
        with self.ledger.connection() as db:
            rows = db.execute('SELECT entity_a,entity_b FROM item_relations WHERE group_id=? AND (entity_a=? OR entity_b=?) ORDER BY entity_a,entity_b', (group, entity, entity)).fetchall()
        return [r['entity_b'] if r['entity_a'] == entity else r['entity_a'] for r in rows]
