"""Collection-scoped equipment templates and durable generated IDs."""
import hashlib
import json
import re
from uuid import uuid4

from ledger import Conflict, Ledger, timestamp, uuid

_TEMPLATE_FIELDS = {'name', 'entity_type_id', 'manufacturer', 'model_number', 'model_code', 'description', 'tag_ids', 'photo_attachment_id', 'photo_entity_id'}
_REQUIRED_TEMPLATE_FIELDS = _TEMPLATE_FIELDS - {'photo_attachment_id', 'photo_entity_id'}
_CODE_RE = re.compile(r'^[A-Z0-9]+(?:-[A-Z0-9]+)*$')


def _segment(value, label):
    normalized = re.sub(r'[^A-Z0-9]+', '-', str(value or '').strip().upper()).strip('-')
    if not normalized:
        raise ValueError(f'{label} must contain ASCII letters or digits')
    return normalized


def _code(value):
    normalized = _segment(value, 'model_code')
    if not _CODE_RE.fullmatch(normalized):
        raise ValueError('model_code must contain uppercase ASCII letters, digits, and hyphens')
    return normalized


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class EquipmentCatalog:
    def __init__(self, database):
        self.ledger = database if isinstance(database, Ledger) else Ledger(database)
        self.path = self.ledger.path
        with self.ledger.connection() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS equipment_products(
              id TEXT PRIMARY KEY, group_id TEXT NOT NULL, entity_type_id TEXT NOT NULL,
              type_prefix TEXT NOT NULL, manufacturer TEXT NOT NULL, model_number TEXT NOT NULL,
              model_code TEXT NOT NULL, high_water INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL, identity_key TEXT NOT NULL DEFAULT '', product_group TEXT NOT NULL DEFAULT '',
              UNIQUE(group_id,id));
            DROP INDEX IF EXISTS equipment_product_code_unique;
            CREATE TABLE IF NOT EXISTS equipment_product_codes(
              group_id TEXT NOT NULL, type_prefix TEXT NOT NULL, model_code TEXT NOT NULL,
              product_id TEXT NOT NULL, created_at TEXT NOT NULL,
              PRIMARY KEY(group_id,type_prefix,model_code),
              FOREIGN KEY(group_id,product_id) REFERENCES equipment_products(group_id,id));
            CREATE TABLE IF NOT EXISTS equipment_product_model_codes(
              group_id TEXT NOT NULL, entity_type_id TEXT NOT NULL, model_code TEXT NOT NULL,
              product_id TEXT NOT NULL, created_at TEXT NOT NULL,
              PRIMARY KEY(group_id,entity_type_id,model_code),
              FOREIGN KEY(group_id,product_id) REFERENCES equipment_products(group_id,id));
            CREATE TABLE IF NOT EXISTS equipment_product_display_bases(
              group_id TEXT NOT NULL, display_base TEXT NOT NULL, product_id TEXT NOT NULL,
              created_at TEXT NOT NULL, PRIMARY KEY(group_id,display_base),
              FOREIGN KEY(group_id,product_id) REFERENCES equipment_products(group_id,id));
            CREATE TABLE IF NOT EXISTS equipment_product_members(
              group_id TEXT NOT NULL, product_id TEXT NOT NULL, entity_id TEXT NOT NULL,
              PRIMARY KEY(group_id,product_id,entity_id),
              FOREIGN KEY(group_id,product_id) REFERENCES equipment_products(group_id,id));
            CREATE TABLE IF NOT EXISTS equipment_templates(
              id TEXT PRIMARY KEY, group_id TEXT NOT NULL, product_id TEXT NOT NULL,
              payload TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              FOREIGN KEY(group_id,product_id) REFERENCES equipment_products(group_id,id));
            CREATE TABLE IF NOT EXISTS equipment_template_history(
              sequence INTEGER PRIMARY KEY, group_id TEXT NOT NULL, template_id TEXT NOT NULL,
              actor_id TEXT NOT NULL, request_key TEXT NOT NULL, action TEXT NOT NULL,
              payload TEXT NOT NULL, created_at TEXT NOT NULL,
              UNIQUE(group_id,request_key));
            CREATE TABLE IF NOT EXISTS equipment_catalog_requests(
              group_id TEXT NOT NULL, request_key TEXT NOT NULL, action TEXT NOT NULL,
              request_hash TEXT NOT NULL, result_id TEXT NOT NULL, result_json TEXT NOT NULL,
              created_at TEXT NOT NULL, PRIMARY KEY(group_id,request_key));
            CREATE TABLE IF NOT EXISTS equipment_assignments(
              group_id TEXT NOT NULL, entity_id TEXT NOT NULL, product_id TEXT NOT NULL,
              display_id TEXT NOT NULL, type_prefix TEXT NOT NULL, model_code TEXT NOT NULL,
              number INTEGER NOT NULL, request_key TEXT NOT NULL, actor_id TEXT NOT NULL,
              assigned_at TEXT NOT NULL, deleted INTEGER NOT NULL DEFAULT 0,
              PRIMARY KEY(group_id,entity_id), UNIQUE(group_id,display_id),
              FOREIGN KEY(group_id,product_id) REFERENCES equipment_products(group_id,id));
            CREATE TABLE IF NOT EXISTS equipment_assignment_requests(
              group_id TEXT NOT NULL, request_key TEXT NOT NULL, request_hash TEXT NOT NULL,
              entity_id TEXT NOT NULL, product_id TEXT NOT NULL, result_json TEXT NOT NULL,
              created_at TEXT NOT NULL, PRIMARY KEY(group_id,request_key));
            CREATE TABLE IF NOT EXISTS equipment_product_model_code_history(
              sequence INTEGER PRIMARY KEY, group_id TEXT NOT NULL, product_id TEXT NOT NULL,
              actor_id TEXT NOT NULL, old_model_code TEXT NOT NULL, new_model_code TEXT NOT NULL,
              request_key TEXT NOT NULL, created_at TEXT NOT NULL,
              UNIQUE(group_id,request_key));
            CREATE TRIGGER IF NOT EXISTS no_product_model_code_history_update BEFORE UPDATE ON equipment_product_model_code_history
              BEGIN SELECT RAISE(ABORT,'product model code history is append-only'); END;
            CREATE TRIGGER IF NOT EXISTS no_product_model_code_history_delete BEFORE DELETE ON equipment_product_model_code_history
              BEGIN SELECT RAISE(ABORT,'product model code history is append-only'); END;
            ''')
            columns = {row['name'] for row in db.execute('PRAGMA table_info(equipment_products)')}
            if 'identity_key' not in columns:
                db.execute("ALTER TABLE equipment_products ADD COLUMN identity_key TEXT NOT NULL DEFAULT ''")
            if 'product_group' not in columns:
                db.execute("ALTER TABLE equipment_products ADD COLUMN product_group TEXT NOT NULL DEFAULT ''")
                for row in db.execute('SELECT * FROM equipment_products').fetchall():
                    identity = self._identity(row['entity_type_id'], row['manufacturer'], row['model_number'], '')
                    db.execute('UPDATE equipment_products SET identity_key=? WHERE group_id=? AND id=?',
                               (identity, row['group_id'], row['id']))
            db.execute('CREATE INDEX IF NOT EXISTS equipment_product_identity ON equipment_products(group_id,identity_key)')
            for row in db.execute("SELECT * FROM equipment_products WHERE identity_key=''").fetchall():
                db.execute('UPDATE equipment_products SET identity_key=? WHERE group_id=? AND id=?',
                           (self._identity(row['entity_type_id'], row['manufacturer'], row['model_number']), row['group_id'], row['id']))
                self._reserve_code(db, row['group_id'], row['type_prefix'], row['model_code'], row['id'])
            for row in db.execute('SELECT * FROM equipment_product_codes').fetchall():
                self._reserve_code(db, row['group_id'], row['type_prefix'], row['model_code'], row['product_id'])
            assignment_columns = {row['name'] for row in db.execute('PRAGMA table_info(equipment_assignments)')}
            if 'deleted' not in assignment_columns:
                db.execute('ALTER TABLE equipment_assignments ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0')

    @staticmethod
    def _identity(type_id, manufacturer, model, product_group=''):
        # Explicit collection group labels define product identity, even when model data differs.
        if product_group:
            return _digest([type_id, 'product_group', product_group])
        # Partial/blank product metadata is not enough evidence to merge ungrouped records.
        if not manufacturer.strip() or not model.strip():
            return ''
        return _digest([type_id, manufacturer.casefold(), model.casefold(), product_group])

    @staticmethod
    def _request(db, group, key, action, digest, legacy_digests=()):
        row = db.execute('SELECT * FROM equipment_catalog_requests WHERE group_id=? AND request_key=?', (group, key)).fetchone()
        if row:
            if row['action'] != action:
                raise Conflict('Request key was already used for a different catalog write')
            if row['request_hash'] != digest:
                if row['request_hash'] not in legacy_digests:
                    raise Conflict('Request key was already used for a different catalog write')
                db.execute('UPDATE equipment_catalog_requests SET request_hash=? WHERE group_id=? AND request_key=?', (digest, group, key))
            return json.loads(row['result_json'])
        return None

    @staticmethod
    def _save_request(db, group, key, action, digest, result_id, result):
        db.execute('INSERT INTO equipment_catalog_requests VALUES(?,?,?,?,?,?,?)',
                   (group, key, action, digest, result_id, json.dumps(result, sort_keys=True), timestamp()))

    def _reserve_code(self, db, group, prefix, code, product_id):
        product = db.execute('SELECT entity_type_id FROM equipment_products WHERE group_id=? AND id=?', (group, product_id)).fetchone()
        if not product:
            raise ValueError('Unknown product')
        reserved = db.execute('SELECT product_id FROM equipment_product_codes WHERE group_id=? AND type_prefix=? AND model_code=?', (group, prefix, code)).fetchone()
        model_owner = db.execute('SELECT product_id FROM equipment_product_model_codes WHERE group_id=? AND entity_type_id=? AND model_code=?', (group, product['entity_type_id'], code)).fetchone()
        display_base = f'{prefix}-{code}'
        display_owner = db.execute('SELECT product_id FROM equipment_product_display_bases WHERE group_id=? AND display_base=?', (group, display_base)).fetchone()
        if any(row and row['product_id'] != product_id for row in (reserved, model_owner, display_owner)):
            raise Conflict('type/model code or generated display base is already reserved for another product')
        now = timestamp()
        db.execute('INSERT OR IGNORE INTO equipment_product_codes VALUES(?,?,?,?,?)', (group, prefix, code, product_id, now))
        db.execute('INSERT OR IGNORE INTO equipment_product_model_codes VALUES(?,?,?,?,?)', (group, product['entity_type_id'], code, product_id, now))
        db.execute('INSERT OR IGNORE INTO equipment_product_display_bases VALUES(?,?,?,?)', (group, display_base, product_id, now))

    def _get_or_create_product(self, db, group, data, prefix, ids):
        type_id = data['entity_type_id']
        manufacturer = data['manufacturer'].strip()
        model = data['model_number'].strip()
        code = _code(data['model_code'])
        product_group = str(data.get('product_group') or '')
        identity = self._identity(type_id, manufacturer, model, product_group)
        row = db.execute('SELECT * FROM equipment_products WHERE group_id=? AND identity_key=?', (group, identity)).fetchone() if identity else None
        if row:
            product_id = row['id']
            if row['model_code'] != code:
                raise Conflict('Registered product model code cannot be changed through registration')
            self._reserve_code(db, group, prefix, code, product_id)
            db.execute('UPDATE equipment_products SET type_prefix=?,manufacturer=?,model_number=?,model_code=?,product_group=?,identity_key=?,updated_at=? WHERE group_id=? AND id=?',
                       (prefix, manufacturer, model, code, product_group, identity, timestamp(), group, product_id))
        else:
            reserved = db.execute('SELECT product_id FROM equipment_product_codes WHERE group_id=? AND type_prefix=? AND model_code=?', (group, prefix, code)).fetchone()
            if reserved:
                product_id = reserved['product_id']
                if not identity:
                    raise Conflict('Incomplete product metadata cannot identify an existing product')
                product = db.execute('SELECT * FROM equipment_products WHERE group_id=? AND id=?', (group, product_id)).fetchone()
                if product['entity_type_id'] != type_id:
                    raise Conflict('type_prefix and model_code are already reserved for another native type')
                # Same native type/code represents the same product identity only if its stable identity agrees.
                if product['identity_key'] and product['identity_key'] != identity:
                    raise Conflict('model_code is already reserved for a different product')
                db.execute('UPDATE equipment_products SET identity_key=?,manufacturer=?,model_number=?,updated_at=? WHERE group_id=? AND id=?',
                           (identity, manufacturer, model, timestamp(), group, product_id))
            else:
                product_id = str(uuid4())
                now = timestamp()
                member_count = len(set(ids))
                db.execute('INSERT INTO equipment_products(id,group_id,entity_type_id,type_prefix,manufacturer,model_number,model_code,high_water,created_at,updated_at,identity_key,product_group) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                           (product_id, group, type_id, prefix, manufacturer, model, code, member_count, now, now, identity, product_group))
                self._reserve_code(db, group, prefix, code, product_id)
        self._attach_members(db, group, product_id, ids)
        return dict(db.execute('SELECT * FROM equipment_products WHERE group_id=? AND id=?', (group, product_id)).fetchone())

    @staticmethod
    def _attach_members(db, group, product_id, ids):
        for entity_id in sorted(set(ids)):
            linked = db.execute('SELECT product_id FROM equipment_product_members WHERE group_id=? AND entity_id=?', (group, entity_id)).fetchone()
            if linked and linked['product_id'] != product_id:
                raise Conflict('Native entity is already linked to a different product')
            db.execute('INSERT OR IGNORE INTO equipment_product_members VALUES(?,?,?)', (group, product_id, entity_id))
        count = db.execute('SELECT COUNT(*) FROM equipment_product_members WHERE group_id=? AND product_id=?', (group, product_id)).fetchone()[0]
        db.execute('UPDATE equipment_products SET high_water=MAX(high_water,?) WHERE group_id=? AND id=?', (count, group, product_id))

    def refresh_product_members(self, group_id, product_id, entity_ids):
        group, product_id = uuid(group_id), uuid(product_id)
        ids = sorted({uuid(item) for item in entity_ids})
        with self.ledger.transaction() as db:
            exists = db.execute('SELECT 1 FROM equipment_products WHERE group_id=? AND id=?', (group, product_id)).fetchone()
            if not exists:
                raise ValueError('Unknown product')
            self._attach_members(db, group, product_id, ids)
            return dict(db.execute('SELECT * FROM equipment_products WHERE group_id=? AND id=?', (group, product_id)).fetchone())

    def register_product(self, group_id, actor_id, request_key, product, matching_entity_ids):
        group, actor, key = uuid(group_id), uuid(actor_id), uuid(request_key)
        data = dict(product)
        try:
            data['entity_type_id'] = uuid(data['entity_type_id'])
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError('A valid entity_type_id is required') from exc
        if not data.get('type_prefix'):
            raise ValueError('An authoritative type_prefix is required')
        prefix = _segment(data['type_prefix'], 'type_prefix')
        data['manufacturer'] = str(data.get('manufacturer') or '').strip()
        data['model_number'] = str(data.get('model_number') or '').strip()
        data['model_code'] = _code(data.get('model_code'))
        ids = sorted({uuid(item) for item in matching_entity_ids})
        digest = _digest({'product': data})
        with self.ledger.transaction() as db:
            prior = self._request(db, group, key, 'product', digest)
            if prior is not None:
                self._attach_members(db, group, prior['id'], ids)
                return dict(db.execute('SELECT * FROM equipment_products WHERE group_id=? AND id=?', (group, prior['id'])).fetchone())
            result = self._get_or_create_product(db, group, data, prefix, ids)
            self._save_request(db, group, key, 'product', digest, result['id'], result)
            return result

    def list_products(self, group_id: str, active_entity_ids: set[str]) -> list[dict]:
        group = uuid(group_id)
        active_ids = {uuid(value) for value in active_entity_ids}
        with self.ledger.connection() as db:
            products = db.execute('SELECT * FROM equipment_products WHERE group_id=? ORDER BY type_prefix,model_code,id', (group,)).fetchall()
            results = []
            for product in products:
                members = {row['entity_id'] for row in db.execute(
                    'SELECT entity_id FROM equipment_product_members WHERE group_id=? AND product_id=?',
                    (group, product['id'])) if row['entity_id'] in active_ids}
                assignments = [dict(row) for row in db.execute(
                    'SELECT entity_id,display_id,number FROM equipment_assignments '
                    'WHERE group_id=? AND product_id=? AND deleted=0 ORDER BY number,entity_id',
                    (group, product['id'])) if row['entity_id'] in members]
                results.append({
                    'id': product['id'], 'entity_type_id': product['entity_type_id'],
                    'type_prefix': product['type_prefix'], 'manufacturer': product['manufacturer'],
                    'model_number': product['model_number'], 'model_code': product['model_code'],
                    'active_item_count': len(members), 'active_assigned_count': len(assignments),
                    'next_number': product['high_water'] + 1, 'assignments': assignments,
                })
            return results

    def update_product_model_code(self, group_id: str, actor_id: str, product_id: str,
                                  model_code: str, expected_updated_at: str, request_key: str) -> dict:
        group, actor, product_id, key = map(uuid, (group_id, actor_id, product_id, request_key))
        code = _code(model_code)
        digest = _digest({'product_id': product_id, 'model_code': code, 'expected_updated_at': expected_updated_at})
        with self.ledger.transaction() as db:
            prior = self._request(db, group, key, 'product_model_code', digest)
            if prior is not None:
                return prior
            product = db.execute('SELECT * FROM equipment_products WHERE group_id=? AND id=?', (group, product_id)).fetchone()
            if not product:
                raise ValueError('Unknown product')
            if expected_updated_at is None or product['updated_at'] != expected_updated_at:
                raise Conflict('Product changed since it was read')
            old_code = product['model_code']
            self._reserve_code(db, group, product['type_prefix'], code, product_id)
            now = timestamp()
            db.execute('UPDATE equipment_products SET model_code=?,updated_at=? WHERE group_id=? AND id=?',
                       (code, now, group, product_id))
            db.execute('INSERT INTO equipment_product_model_code_history(group_id,product_id,actor_id,old_model_code,new_model_code,request_key,created_at) VALUES(?,?,?,?,?,?,?)',
                       (group, product_id, actor, old_code, code, key, now))
            result = dict(db.execute('SELECT * FROM equipment_products WHERE group_id=? AND id=?', (group, product_id)).fetchone())
            self._save_request(db, group, key, 'product_model_code', digest, product_id, result)
            return result

    def current_product_model_code(self, group_id: str, product_id: str) -> str | None:
        with self.ledger.connection() as db:
            row = db.execute('SELECT model_code FROM equipment_products WHERE group_id=? AND id=?',
                             (uuid(group_id), uuid(product_id))).fetchone()
            return row['model_code'] if row else None

    @staticmethod
    def _normalize_template(payload):
        if not isinstance(payload, dict):
            raise ValueError('Template payload must be an object')
        unknown, missing = set(payload) - _TEMPLATE_FIELDS, _REQUIRED_TEMPLATE_FIELDS - set(payload)
        if unknown:
            raise ValueError(f'Unsupported template fields: {", ".join(sorted(unknown))}')
        if missing:
            raise ValueError(f'Missing template fields: {", ".join(sorted(missing))}')
        data = dict(payload)
        for field in ('name', 'manufacturer', 'model_number', 'description'):
            if not isinstance(data[field], str):
                raise ValueError(f'{field} must be text')
            data[field] = data[field].strip()
        if not data['name']:
            raise ValueError('name is required')
        data['entity_type_id'] = uuid(data['entity_type_id'])
        data['model_code'] = _code(data['model_code'])
        if not isinstance(data['tag_ids'], list):
            raise ValueError('tag_ids must be a list')
        data['tag_ids'] = [uuid(item) for item in data['tag_ids']]
        for field in ('photo_attachment_id', 'photo_entity_id'):
            if field in data and data[field] is not None:
                data[field] = uuid(data[field])
        return data

    def save_template(self, group_id, actor_id, request_key, payload, matching_entity_ids=(), *, type_prefix=None, template_id=None, expected_updated_at=None, product_group=''):
        group, actor, key = uuid(group_id), uuid(actor_id), uuid(request_key)
        data = self._normalize_template(payload)
        if not type_prefix:
            raise ValueError('An authoritative type_prefix is required')
        prefix = _segment(type_prefix, 'type_prefix')
        ids = sorted({uuid(item) for item in matching_entity_ids})
        product_group = str(product_group or '')
        digest = _digest({'payload': data, 'type_prefix': prefix, 'product_group': product_group, 'template_id': uuid(template_id) if template_id else None, 'expected_updated_at': expected_updated_at})
        legacy_digest = _digest({'payload': data, 'type_prefix': prefix, 'matching_entity_ids': ids, 'template_id': uuid(template_id) if template_id else None, 'expected_updated_at': expected_updated_at})
        with self.ledger.transaction() as db:
            prior = self._request(db, group, key, 'template', digest, (legacy_digest,))
            if prior is not None:
                return self._template(db, group, prior['id'])
            if template_id:
                tid = uuid(template_id)
                old = db.execute('SELECT * FROM equipment_templates WHERE group_id=? AND id=?', (group, tid)).fetchone()
                if not old:
                    raise ValueError('Unknown template')
                if expected_updated_at is None or old['updated_at'] != expected_updated_at:
                    raise Conflict('Template changed since it was read')
                product_id = old['product_id']
                product = db.execute('SELECT * FROM equipment_products WHERE group_id=? AND id=?', (group, product_id)).fetchone()
                if product['entity_type_id'] != data['entity_type_id']:
                    raise Conflict('Template item type cannot change product identity')
                if str(product['product_group'] or '') != product_group:
                    raise Conflict('Template product group identity cannot change')
                identity = self._identity(data['entity_type_id'], data['manufacturer'], data['model_number'], product_group)
                duplicate = db.execute('SELECT id FROM equipment_products WHERE group_id=? AND identity_key=? AND id<>?', (group, identity, product_id)).fetchone() if identity else None
                if duplicate:
                    raise Conflict('Template metadata already identifies a different product')
                self._reserve_code(db, group, prefix, data['model_code'], product_id)
                db.execute('UPDATE equipment_products SET type_prefix=?,manufacturer=?,model_number=?,model_code=?,identity_key=?,updated_at=? WHERE group_id=? AND id=?',
                           (prefix, data['manufacturer'], data['model_number'], data['model_code'], identity, timestamp(), group, product_id))
                for entity_id in ids:
                    linked = db.execute('SELECT product_id FROM equipment_product_members WHERE group_id=? AND entity_id=?', (group, entity_id)).fetchone()
                    if linked and linked['product_id'] != product_id:
                        raise Conflict('Native entity is already linked to a different product')
                    db.execute('INSERT OR IGNORE INTO equipment_product_members VALUES(?,?,?)', (group, product_id, entity_id))
                count = db.execute('SELECT COUNT(*) FROM equipment_product_members WHERE group_id=? AND product_id=?', (group, product_id)).fetchone()[0]
                db.execute('UPDATE equipment_products SET high_water=MAX(high_water,?) WHERE group_id=? AND id=?', (count, group, product_id))
                action = 'updated'
            else:
                product_data = {field: data[field] for field in ('entity_type_id', 'manufacturer', 'model_number', 'model_code')}
                product_data['product_group'] = product_group
                product = self._get_or_create_product(db, group, product_data, prefix, ids)
                product_id, tid, action = product['id'], str(uuid4()), 'saved'
            now = timestamp()
            if template_id:
                db.execute('UPDATE equipment_templates SET payload=?,updated_at=? WHERE group_id=? AND id=?', (json.dumps(data, sort_keys=True), now, group, tid))
            else:
                db.execute('INSERT INTO equipment_templates VALUES(?,?,?,?,0,?,?)', (tid, group, product_id, json.dumps(data, sort_keys=True), now, now))
            db.execute('INSERT INTO equipment_template_history(group_id,template_id,actor_id,request_key,action,payload,created_at) VALUES(?,?,?,?,?,?,?)',
                       (group, tid, actor, key, action, json.dumps(data, sort_keys=True), now))
            result = self._template(db, group, tid)
            self._save_request(db, group, key, 'template', digest, tid, result)
            return result

    def _template(self, db, group, template_id):
        row = db.execute('SELECT * FROM equipment_templates WHERE group_id=? AND id=?', (group, uuid(template_id))).fetchone()
        if not row:
            raise ValueError('Unknown template')
        product = db.execute('SELECT * FROM equipment_products WHERE group_id=? AND id=?', (group, row['product_id'])).fetchone()
        result = json.loads(row['payload'])
        result.update(id=row['id'], product_id=row['product_id'], archived=bool(row['archived']), created_at=row['created_at'], updated_at=row['updated_at'], type_prefix=product['type_prefix'])
        return result

    def list_templates(self, group_id, include_archived=False):
        group = uuid(group_id)
        with self.ledger.connection() as db:
            rows = db.execute('SELECT id FROM equipment_templates WHERE group_id=? AND (? OR archived=0) ORDER BY lower(json_extract(payload, "$.name")),id', (group, int(bool(include_archived)))).fetchall()
            return [self._template(db, group, row['id']) for row in rows]

    def archive_template(self, group_id, actor_id, template_id, request_key):
        group, actor, key, tid = uuid(group_id), uuid(actor_id), uuid(request_key), uuid(template_id)
        with self.ledger.transaction() as db:
            prior = db.execute('SELECT * FROM equipment_template_history WHERE group_id=? AND request_key=?', (group, key)).fetchone()
            if prior:
                if prior['template_id'] != tid or prior['action'] != 'archived':
                    raise Conflict('Request key was already used for another template write')
                return self._template(db, group, tid)
            row = db.execute('SELECT * FROM equipment_templates WHERE group_id=? AND id=?', (group, tid)).fetchone()
            if not row:
                raise ValueError('Unknown template')
            now = timestamp()
            db.execute('UPDATE equipment_templates SET archived=1,updated_at=? WHERE group_id=? AND id=?', (now, group, tid))
            db.execute('INSERT INTO equipment_template_history(group_id,template_id,actor_id,request_key,action,payload,created_at) VALUES(?,?,?,?,?,?,?)', (group, tid, actor, key, 'archived', row['payload'], now))
            return self._template(db, group, tid)

    def restore_template(self, group_id, actor_id, template_id, request_key):
        group, actor, key, tid = uuid(group_id), uuid(actor_id), uuid(request_key), uuid(template_id)
        with self.ledger.transaction() as db:
            prior = db.execute('SELECT * FROM equipment_template_history WHERE group_id=? AND request_key=?', (group, key)).fetchone()
            if prior:
                if prior['template_id'] != tid or prior['action'] != 'restored':
                    raise Conflict('Request key was already used for another template write')
                return self._template(db, group, tid)
            row = db.execute('SELECT * FROM equipment_templates WHERE group_id=? AND id=?', (group, tid)).fetchone()
            if not row:
                raise ValueError('Unknown template')
            now = timestamp()
            db.execute('UPDATE equipment_templates SET archived=0,updated_at=? WHERE group_id=? AND id=?', (now, group, tid))
            db.execute('INSERT INTO equipment_template_history(group_id,template_id,actor_id,request_key,action,payload,created_at) VALUES(?,?,?,?,?,?,?)', (group, tid, actor, key, 'restored', row['payload'], now))
            return self._template(db, group, tid)

    def template_history(self, group_id, template_id):
        with self.ledger.connection() as db:
            rows = db.execute('SELECT * FROM equipment_template_history WHERE group_id=? AND template_id=? ORDER BY sequence', (uuid(group_id), uuid(template_id))).fetchall()
            return [dict(row) for row in rows]

    def assign_item(self, group_id, actor_id, entity_id, product_id, request_key):
        group, actor, entity, product_id, key = map(uuid, (group_id, actor_id, entity_id, product_id, request_key))
        request_hash = _digest([entity, product_id])
        with self.ledger.transaction() as db:
            request = db.execute('SELECT * FROM equipment_assignment_requests WHERE group_id=? AND request_key=?', (group, key)).fetchone()
            if request:
                if request['request_hash'] != request_hash:
                    raise Conflict('Request key was already used for another assignment')
                return json.loads(request['result_json'])
            existing = db.execute('SELECT * FROM equipment_assignments WHERE group_id=? AND entity_id=?', (group, entity)).fetchone()
            if existing:
                if existing['product_id'] != product_id:
                    raise Conflict('Entity is already assigned to another product')
                result = dict(existing)
            else:
                product = db.execute('SELECT * FROM equipment_products WHERE group_id=? AND id=?', (group, product_id)).fetchone()
                if not product:
                    raise ValueError('Unknown product')
                linked = db.execute('SELECT product_id FROM equipment_product_members WHERE group_id=? AND entity_id=?', (group, entity)).fetchone()
                if linked and linked['product_id'] != product_id:
                    raise Conflict('Native entity is already linked to a different product')
                db.execute('INSERT OR IGNORE INTO equipment_product_members VALUES(?,?,?)', (group, product_id, entity))
                db.execute('UPDATE equipment_products SET high_water=high_water+1,updated_at=? WHERE group_id=? AND id=?', (timestamp(), group, product_id))
                number = db.execute('SELECT high_water FROM equipment_products WHERE group_id=? AND id=?', (group, product_id)).fetchone()['high_water']
                assigned_at = timestamp()
                display = f"{product['type_prefix']}-{product['model_code']}-{number}"
                db.execute('INSERT INTO equipment_assignments(group_id,entity_id,product_id,display_id,type_prefix,model_code,number,request_key,actor_id,assigned_at,deleted) VALUES(?,?,?,?,?,?,?,?,?,?,0)',
                           (group, entity, product_id, display, product['type_prefix'], product['model_code'], number, key, actor, assigned_at))
                result = dict(db.execute('SELECT * FROM equipment_assignments WHERE group_id=? AND entity_id=?', (group, entity)).fetchone())
            db.execute('INSERT INTO equipment_assignment_requests VALUES(?,?,?,?,?,?,?)',
                       (group, key, request_hash, entity, product_id, json.dumps(result, sort_keys=True), timestamp()))
            return result

    def assignment(self, group_id, entity_id):
        with self.ledger.connection() as db:
            row = db.execute('SELECT * FROM equipment_assignments WHERE group_id=? AND entity_id=?', (uuid(group_id), uuid(entity_id))).fetchone()
            return dict(row) if row else None

    def resolve_id(self, group_id, display_id):
        with self.ledger.connection() as db:
            row = db.execute('SELECT entity_id FROM equipment_assignments WHERE group_id=? AND display_id=? COLLATE NOCASE', (uuid(group_id), str(display_id).strip())).fetchone()
            return row['entity_id'] if row else None

    def record_entity_context(self, group_id, entity_id, **_context):
        uuid(group_id); uuid(entity_id)

    def delete_assignment(self, group_id, entity_id):
        with self.ledger.transaction() as db:
            db.execute('UPDATE equipment_assignments SET deleted=1 WHERE group_id=? AND entity_id=?', (uuid(group_id), uuid(entity_id)))
