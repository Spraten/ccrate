"""Collection-scoped equipment templates and durable generated IDs."""
import json
import re
from uuid import uuid4

from ledger import Conflict, Ledger, timestamp, uuid

_TEMPLATE_FIELDS = {'name', 'entity_type_id', 'manufacturer', 'model_number', 'model_code', 'description', 'tag_ids', 'photo_attachment_id'}
_REQUIRED_TEMPLATE_FIELDS = _TEMPLATE_FIELDS - {'photo_attachment_id'}
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
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              UNIQUE(group_id,id));
            CREATE UNIQUE INDEX IF NOT EXISTS equipment_product_code_unique
              ON equipment_products(group_id,entity_type_id,model_code);
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
            CREATE TABLE IF NOT EXISTS equipment_assignments(
              group_id TEXT NOT NULL, entity_id TEXT NOT NULL, product_id TEXT NOT NULL,
              display_id TEXT NOT NULL, type_prefix TEXT NOT NULL, model_code TEXT NOT NULL,
              number INTEGER NOT NULL, request_key TEXT NOT NULL, actor_id TEXT NOT NULL,
              assigned_at TEXT NOT NULL,
              PRIMARY KEY(group_id,entity_id), UNIQUE(group_id,display_id),
              UNIQUE(group_id,request_key),
              FOREIGN KEY(group_id,product_id) REFERENCES equipment_products(group_id,id));
            ''')

    @staticmethod
    def _group(value):
        return uuid(value)

    def _product_dict(self, row):
        return dict(row)

    def register_product(self, group_id, actor_id, request_key, product, matching_entity_ids):
        group, actor, key = uuid(group_id), uuid(actor_id), uuid(request_key)
        data = dict(product)
        try:
            type_id = uuid(data['entity_type_id'])
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError('A valid entity_type_id is required') from exc
        manufacturer = str(data.get('manufacturer') or '').strip()
        model = str(data.get('model_number') or '').strip()
        code = _code(data.get('model_code'))
        prefix = _segment(data.get('type_prefix') or data.get('entity_type_name') or 'ITEM', 'type_prefix')
        ids = sorted({uuid(item) for item in matching_entity_ids})
        with self.ledger.transaction() as db:
            existing = db.execute('SELECT * FROM equipment_products WHERE group_id=? AND entity_type_id=? AND model_code=?', (group, type_id, code)).fetchone()
            if existing:
                if (existing['manufacturer'].casefold(), existing['model_number'].casefold()) != (manufacturer.casefold(), model.casefold()):
                    raise Conflict('model_code is already reserved for a different product')
                product_id = existing['id']
                db.execute('UPDATE equipment_products SET updated_at=? WHERE id=?', (timestamp(), product_id))
            else:
                product_id = str(uuid4())
                now = timestamp()
                db.execute('INSERT INTO equipment_products VALUES(?,?,?,?,?,?,?,?,?,?)',
                           (product_id, group, type_id, prefix, manufacturer, model, code, len(ids), now, now))
            for entity_id in ids:
                linked = db.execute('SELECT product_id FROM equipment_product_members WHERE group_id=? AND entity_id=?', (group, entity_id)).fetchone()
                if linked and linked['product_id'] != product_id:
                    raise Conflict('Native entity is already linked to a different product')
                db.execute('INSERT OR IGNORE INTO equipment_product_members VALUES(?,?,?)', (group, product_id, entity_id))
            member_count = db.execute('SELECT COUNT(*) FROM equipment_product_members WHERE group_id=? AND product_id=?', (group, product_id)).fetchone()[0]
            db.execute('UPDATE equipment_products SET high_water=MAX(high_water,?),updated_at=? WHERE group_id=? AND id=?', (member_count, timestamp(), group, product_id))
            row = db.execute('SELECT * FROM equipment_products WHERE id=? AND group_id=?', (product_id, group)).fetchone()
            return self._product_dict(row)

    def save_template(self, group_id, actor_id, request_key, payload, matching_entity_ids=()):
        group, actor, key = uuid(group_id), uuid(actor_id), uuid(request_key)
        if not isinstance(payload, dict):
            raise ValueError('Template payload must be an object')
        unknown = set(payload) - _TEMPLATE_FIELDS
        missing = _REQUIRED_TEMPLATE_FIELDS - set(payload)
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
        if 'photo_attachment_id' in data and data['photo_attachment_id'] is not None:
            data['photo_attachment_id'] = uuid(data['photo_attachment_id'])
        product_data = {field: data[field] for field in ('entity_type_id', 'manufacturer', 'model_number', 'model_code')}
        with self.ledger.transaction() as db:
            prior = db.execute('SELECT * FROM equipment_template_history WHERE group_id=? AND request_key=?', (group, key)).fetchone()
            if prior:
                saved = json.loads(prior['payload'])
                if saved != data:
                    raise Conflict('Request key was already used for a different template write')
                return self._template(db, group, prior['template_id'])
        product = self.register_product(group, actor, key, product_data, matching_entity_ids)
        with self.ledger.transaction() as db:
            template_id = str(uuid4())
            now = timestamp()
            db.execute('INSERT INTO equipment_templates VALUES(?,?,?,?,0,?,?)',
                       (template_id, group, product['id'], json.dumps(data, sort_keys=True), now, now))
            db.execute('INSERT INTO equipment_template_history(group_id,template_id,actor_id,request_key,action,payload,created_at) VALUES(?,?,?,?,?,?,?)',
                       (group, template_id, actor, key, 'saved', json.dumps(data, sort_keys=True), now))
            return self._template(db, group, template_id)

    def _template(self, db, group, template_id):
        row = db.execute('SELECT * FROM equipment_templates WHERE group_id=? AND id=?', (group, uuid(template_id))).fetchone()
        if not row:
            raise ValueError('Unknown template')
        product = db.execute('SELECT * FROM equipment_products WHERE group_id=? AND id=?', (group, row['product_id'])).fetchone()
        result = json.loads(row['payload'])
        result.update(id=row['id'], product_id=row['product_id'], archived=bool(row['archived']), created_at=row['created_at'], updated_at=row['updated_at'], type_prefix=product['type_prefix'])
        return result

    def list_templates(self, group_id):
        group = uuid(group_id)
        with self.ledger.connection() as db:
            rows = db.execute('SELECT id FROM equipment_templates WHERE group_id=? AND archived=0 ORDER BY lower(json_extract(payload, "$.name")),id', (group,)).fetchall()
            return [self._template(db, group, row['id']) for row in rows]

    def archive_template(self, group_id, actor_id, template_id, request_key):
        group, actor, key, template_id = uuid(group_id), uuid(actor_id), uuid(request_key), uuid(template_id)
        with self.ledger.transaction() as db:
            prior = db.execute('SELECT * FROM equipment_template_history WHERE group_id=? AND request_key=?', (group, key)).fetchone()
            if prior:
                if prior['template_id'] != template_id or prior['action'] != 'archived':
                    raise Conflict('Request key was already used for another template write')
                return self._template(db, group, template_id)
            row = db.execute('SELECT * FROM equipment_templates WHERE group_id=? AND id=?', (group, template_id)).fetchone()
            if not row:
                raise ValueError('Unknown template')
            now = timestamp()
            db.execute('UPDATE equipment_templates SET archived=1,updated_at=? WHERE group_id=? AND id=?', (now, group, template_id))
            db.execute('INSERT INTO equipment_template_history(group_id,template_id,actor_id,request_key,action,payload,created_at) VALUES(?,?,?,?,?,?,?)',
                       (group, template_id, actor, key, 'archived', row['payload'], now))
            return self._template(db, group, template_id)

    def template_history(self, group_id, template_id):
        with self.ledger.connection() as db:
            rows = db.execute('SELECT * FROM equipment_template_history WHERE group_id=? AND template_id=? ORDER BY sequence', (uuid(group_id), uuid(template_id))).fetchall()
            return [dict(row) for row in rows]

    def assign_item(self, group_id, actor_id, entity_id, product_id, request_key):
        group, actor, entity, product_id, key = map(uuid, (group_id, actor_id, entity_id, product_id, request_key))
        with self.ledger.transaction() as db:
            prior = db.execute('SELECT * FROM equipment_assignments WHERE group_id=? AND request_key=?', (group, key)).fetchone()
            if prior:
                if prior['entity_id'] != entity or prior['product_id'] != product_id:
                    raise Conflict('Request key was already used for another assignment')
                return dict(prior)
            existing = db.execute('SELECT * FROM equipment_assignments WHERE group_id=? AND entity_id=?', (group, entity)).fetchone()
            if existing:
                if existing['product_id'] != product_id:
                    raise Conflict('Entity is already assigned to another product')
                return dict(existing)
            product = db.execute('SELECT * FROM equipment_products WHERE group_id=? AND id=?', (group, product_id)).fetchone()
            if not product:
                raise ValueError('Unknown product')
            linked = db.execute('SELECT product_id FROM equipment_product_members WHERE group_id=? AND entity_id=?', (group, entity)).fetchone()
            if linked and linked['product_id'] != product_id:
                raise Conflict('Native entity is already linked to a different product')
            db.execute('INSERT OR IGNORE INTO equipment_product_members VALUES(?,?,?)', (group, product_id, entity))
            db.execute('UPDATE equipment_products SET high_water=high_water+1,updated_at=? WHERE group_id=? AND id=?', (timestamp(), group, product_id))
            updated = db.execute('SELECT high_water FROM equipment_products WHERE group_id=? AND id=?', (group, product_id)).fetchone()
            number = updated['high_water']
            display = f"{product['type_prefix']}-{product['model_code']}-{number}"
            assigned_at = timestamp()
            db.execute('INSERT INTO equipment_assignments VALUES(?,?,?,?,?,?,?,?,?,?)',
                       (group, entity, product_id, display, product['type_prefix'], product['model_code'], number, key, actor, assigned_at))
            return dict(db.execute('SELECT * FROM equipment_assignments WHERE group_id=? AND entity_id=?', (group, entity)).fetchone())

    def assignment(self, group_id, entity_id):
        with self.ledger.connection() as db:
            row = db.execute('SELECT * FROM equipment_assignments WHERE group_id=? AND entity_id=?', (uuid(group_id), uuid(entity_id))).fetchone()
            return dict(row) if row else None

    def resolve_id(self, group_id, display_id):
        with self.ledger.connection() as db:
            row = db.execute('SELECT entity_id FROM equipment_assignments WHERE group_id=? AND display_id=? COLLATE NOCASE', (uuid(group_id), str(display_id).strip())).fetchone()
            return row['entity_id'] if row else None

    # Fixture/support helpers model Homebox changes and external deletion without
    # rewriting assigned IDs. Membership records remain a separate native UUID index.
    def record_entity_context(self, group_id, entity_id, **_context):
        uuid(group_id); uuid(entity_id)

    def delete_assignment(self, group_id, entity_id):
        with self.ledger.transaction() as db:
            db.execute('DELETE FROM equipment_assignments WHERE group_id=? AND entity_id=?', (uuid(group_id), uuid(entity_id)))
