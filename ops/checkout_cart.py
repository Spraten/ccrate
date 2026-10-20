"""Persistent checkout intent; saved selections never reserve native equipment."""
import hashlib
import json

from ledger import Conflict, timestamp, uuid


class CheckoutCart:
    def __init__(self, ledger):
        self.ledger = ledger
        with ledger.transaction() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS checkout_carts(
              group_id TEXT NOT NULL,actor_id TEXT NOT NULL,revision INTEGER NOT NULL,
              items TEXT NOT NULL,updated_at TEXT NOT NULL,notes TEXT NOT NULL DEFAULT '{}',
              PRIMARY KEY(group_id,actor_id))''')
            columns = {row['name'] for row in db.execute('PRAGMA table_info(checkout_carts)')}
            if 'notes' not in columns:
                db.execute("ALTER TABLE checkout_carts ADD COLUMN notes TEXT NOT NULL DEFAULT '{}'")
            db.execute('''CREATE TABLE IF NOT EXISTS checkout_cart_requests(
              group_id TEXT NOT NULL,actor_id TEXT NOT NULL,request_key TEXT NOT NULL,
              payload_hash TEXT NOT NULL,result TEXT NOT NULL,created_at TEXT NOT NULL,
              PRIMARY KEY(group_id,actor_id,request_key))''')
            db.execute('''CREATE TABLE IF NOT EXISTS checkout_cart_receipts(
              receipt_id TEXT PRIMARY KEY,group_id TEXT NOT NULL,actor_id TEXT NOT NULL,result TEXT NOT NULL,
              created_at TEXT NOT NULL)''')

    @staticmethod
    def _items(values):
        if not isinstance(values, list) or len(values) > 50:
            raise ValueError('Select at most 50 distinct assets')
        items = [uuid(value) for value in values]
        if len(items) != len(set(items)):
            raise ValueError('Select distinct equipment')
        return items

    @staticmethod
    def _revision(value):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError('A valid checkout cart revision is required')
        return value

    @staticmethod
    def _notes(values, selected):
        if values is None:
            return None
        if not isinstance(values, dict):
            raise ValueError('Checkout notes must be an item-to-note mapping')
        notes = {}
        for key, value in values.items():
            entity_id = uuid(key)
            if entity_id not in selected:
                raise ValueError('Checkout notes must belong to selected equipment')
            if entity_id in notes:
                raise ValueError('Checkout notes must use distinct equipment IDs')
            if not isinstance(value, str):
                raise ValueError('Checkout notes must be text')
            try:
                value.encode('utf-8')
            except UnicodeEncodeError:
                raise ValueError('Checkout note contains invalid Unicode') from None
            value = value.strip()
            if len(value) > 1000:
                raise ValueError('Checkout notes may contain at most 1,000 characters')
            if value:
                notes[entity_id] = value
        return dict(sorted(notes.items()))

    @staticmethod
    def _state(db, group, actor):
        row = db.execute('SELECT revision,items,notes FROM checkout_carts WHERE group_id=? AND actor_id=?',
                         (group, actor)).fetchone()
        return {'revision': row['revision'], 'items': json.loads(row['items']),
                'notes': json.loads(row['notes'] or '{}')} if row else {'revision': 0, 'items': [], 'notes': {}}

    def get(self, group, actor):
        with self.ledger.connection() as db:
            return self._state(db, uuid(group), uuid(actor))

    def request_status(self, group, actor, request_key):
        """Return only this actor's durable cart-save receipt for recovery."""
        group, actor, request_key = uuid(group), uuid(actor), uuid(request_key)
        with self.ledger.connection() as db:
            row = db.execute('SELECT result FROM checkout_cart_requests WHERE group_id=? AND actor_id=? AND request_key=?',
                             (group, actor, request_key)).fetchone()
        if not row:
            return None
        return {'status': 'completed', 'action': 'checkout-cart', 'result': json.loads(row['result'])}

    def save(self, group, actor, items, revision, request_key, notes=None):
        group, actor = uuid(group), uuid(actor)
        items, revision, request_key = self._items(items), self._revision(revision), uuid(request_key)
        normalized_notes = self._notes(notes, set(items))
        with self.ledger.transaction() as db:
            current = self._state(db, group, actor)
            retained_notes = {key: value for key, value in current['notes'].items() if key in items}
            resulting_notes = retained_notes if normalized_notes is None else normalized_notes
            digest = hashlib.sha256(json.dumps([revision, items, normalized_notes], sort_keys=True,
                                               separators=(',', ':')).encode()).hexdigest()
            prior = db.execute('SELECT payload_hash,result FROM checkout_cart_requests WHERE group_id=? AND actor_id=? AND request_key=?',
                               (group, actor, request_key)).fetchone()
            if prior:
                legacy_digest = hashlib.sha256(json.dumps([revision, items], separators=(',', ':')).encode()).hexdigest()
                compatible = prior['payload_hash'] == digest or (normalized_notes is None and prior['payload_hash'] == legacy_digest)
                if not compatible:
                    raise Conflict('This checkout cart request key belongs to a different edit.')
                result = json.loads(prior['result'])
                result.setdefault('notes', {})
                return result
            if current['revision'] != revision:
                raise Conflict('The checkout cart changed. Reload it before saving.')
            result = {'revision': revision + 1, 'items': items, 'notes': resulting_notes}
            db.execute('''INSERT INTO checkout_carts(group_id,actor_id,revision,items,updated_at,notes) VALUES(?,?,?,?,?,?)
              ON CONFLICT(group_id,actor_id) DO UPDATE SET revision=excluded.revision,items=excluded.items,
              updated_at=excluded.updated_at,notes=excluded.notes''',
                       (group, actor, result['revision'], json.dumps(items), timestamp(), json.dumps(resulting_notes, sort_keys=True)))
            db.execute('INSERT INTO checkout_cart_requests VALUES(?,?,?,?,?,?)',
                       (group, actor, request_key, digest, json.dumps(result), timestamp()))
            return result

    def consume_completed_receipt(self, group, actor, receipt_id):
        group, actor, receipt_id = uuid(group), uuid(actor), uuid(receipt_id)
        with self.ledger.transaction() as db:
            prior = db.execute('SELECT group_id,actor_id,result FROM checkout_cart_receipts WHERE receipt_id=?', (receipt_id,)).fetchone()
            if prior:
                if (prior['group_id'], prior['actor_id']) != (group, actor):
                    raise Conflict('Checkout receipt does not belong to this member and collection.')
                result = json.loads(prior['result'])
                result.setdefault('cart', {}).setdefault('notes', {})
                return result
            operation = db.execute('SELECT * FROM operations WHERE id=? AND group_id=? AND actor_id=?',
                                   (receipt_id, group, actor)).fetchone()
            if not operation or operation['action'] != 'check_out' or operation['status'] != 'completed':
                raise Conflict('Only this member’s completed checkout receipt can consume a saved cart.')
            row = db.execute('SELECT payload FROM operation_context WHERE operation_id=?', (receipt_id,)).fetchone()
            context = json.loads(row['payload']) if row else {}
            cart_intent = context.get('checkout_cart')
            if not isinstance(cart_intent, dict) or not isinstance(cart_intent.get('items'), list):
                raise Conflict('Checkout receipt has no saved cart context.')
            revision = self._revision(cart_intent.get('revision'))
            receipt_assets = {row['entity_id'] for row in db.execute(
                'SELECT entity_id FROM operation_assets WHERE operation_id=?', (receipt_id,))}
            selected = set(self._items(cart_intent['items']))
            consumed = sorted(receipt_assets & selected)
            original = set(self._items(cart_intent['original_items'])) if 'original_items' in cart_intent else set(consumed)
            current = self._state(db, group, actor)
            skipped = current['revision'] != revision
            consumed_roots = set(consumed) & original
            if not skipped and consumed_roots:
                remaining = [item for item in current['items'] if item not in consumed_roots]
                current = {'revision': revision + 1, 'items': remaining, 'notes': current['notes']}
                db.execute('UPDATE checkout_carts SET revision=?,items=?,updated_at=? WHERE group_id=? AND actor_id=?',
                           (current['revision'], json.dumps(remaining), timestamp(), group, actor))
            removed = consumed_roots
            resulting_notes = {key: value for key, value in current['notes'].items() if skipped or key not in removed}
            result = {'consumed': [] if skipped else consumed, 'cart': dict(current, notes=resulting_notes),
                      'cart_changed': skipped}
            if not skipped and consumed_roots:
                db.execute('UPDATE checkout_carts SET revision=?,items=?,notes=?,updated_at=? WHERE group_id=? AND actor_id=?',
                           (current['revision'], json.dumps(current['items']), json.dumps(resulting_notes, sort_keys=True),
                            timestamp(), group, actor))
            db.execute('INSERT INTO checkout_cart_receipts VALUES(?,?,?,?,?)',
                       (receipt_id, group, actor, json.dumps(result), timestamp()))
            return result
