"""Short-lived badge and item proof isolated from physical kiosk sessions."""
import threading
import urllib.error
from uuid import uuid4

from checkout import confirm_checkout
from checkout_cart import CheckoutCart
from conditions import condition, checkout_blocker
from kits import manifest
from ledger import Conflict, uuid
from scan_codes import normalize, resolve_equipment
from sessions import Session


class WebItemActions:
    """Own independent, account/collection/popup-bound checkout proofs."""

    TIMEOUT_SECONDS = 120
    MAX_PER_ACCOUNT_COLLECTION = 4
    MAX_TOTAL = 256

    def __init__(self, clock=None, checkout=None):
        import time
        self.clock = clock or time.monotonic
        self.checkout_operation = checkout or confirm_checkout
        self.lock = threading.RLock()
        self.proofs = {}
        self.attempts = {}

    def _owner(self, ctx):
        return (uuid(ctx['group']), uuid(ctx['actor']), str(ctx['identity']))

    def _drop(self, verification_id):
        proof = self.proofs.pop(verification_id, None)
        if proof:
            self.attempts.pop((proof['group'], proof['attempt_id']), None)

    def _prune(self):
        for verification_id, proof in list(self.proofs.items()):
            if not proof['session'].active():
                self._drop(verification_id)

    @staticmethod
    def _item_ids(value):
        if not isinstance(value, list) or not 1 <= len(value) <= 50:
            raise ValueError('Choose between 1 and 50 checkout items.')
        result = [uuid(item) for item in value]
        if len(result) != len(set(result)):
            raise ValueError('Choose each checkout item once.')
        return sorted(result)

    def verify_badge(self, ctx, badges, data):
        if not isinstance(data, dict) or set(data) != {'attempt_id', 'badge_code', 'item_ids'}:
            raise ValueError('Badge verification needs an attempt, badge and selected items.')
        attempt_id = uuid(data['attempt_id'])
        if not isinstance(data['badge_code'], str) or not data['badge_code'] or len(data['badge_code']) > 256:
            raise ValueError('Scan a valid C-Crate member badge.')
        roots = self._item_ids(data['item_ids'])
        group, actor, identity = self._owner(ctx)
        with self.lock:
            self._prune()
            existing_id = self.attempts.get((group, attempt_id))
            if existing_id:
                existing = self.proofs[existing_id]
                owner = (group, actor, identity)
                if existing['owner'] != owner:
                    raise Conflict('This popup attempt is already bound to another account or item selection.')
                if existing['roots'] != roots:
                    self._invalidate(existing)
                    raise Conflict('This popup attempt is already bound to another account or item selection.')
                if existing['badge_code'] != data['badge_code']:
                    raise Conflict('This popup attempt is already bound to another account or item selection.')
                current_members = ctx['client'].call('/api/v1/groups/members')
                current_ids = {uuid(row['id']) for row in current_members}
                if existing['badges'].resolve(group, existing['badge_code'], current_ids) != actor:
                    raise Conflict('Badge is revoked or its holder is no longer a collection member. Scan a current badge.')
                return self._verification_response(existing)
        members = ctx['client'].call('/api/v1/groups/members')
        member_ids = {uuid(row['id']) for row in members}
        if actor not in member_ids:
            raise Conflict('Your account is no longer a collection member.')
        member = next(row for row in members if uuid(row['id']) == actor)
        badge_actor = badges.resolve(group, data['badge_code'], member_ids)
        if badge_actor != actor:
            raise Conflict('Scan a badge that matches your signed-in collection account.')

        entities = {}
        kit_versions = {}
        root_manifests = {}
        required = set()
        for root in roots:
            kit = manifest(ctx['client'], root)
            if kit['blockers']:
                raise Conflict(kit['blockers'][0]['name'] + ': ' + kit['blockers'][0]['reason'])
            required.update(row['id'] for row in kit['entities'])
            entities.update((row['id'], row) for row in kit['entities'])
            kit_versions.update(kit['versions'])
            root_manifests[root] = self._manifest_snapshot(kit)
        if len(required) > 50:
            raise ValueError('A verified checkout can contain at most 50 tracked records.')

        with self.lock:
            self._prune()
            attempt_key = (group, attempt_id)
            existing_id = self.attempts.get(attempt_key)
            if existing_id:
                existing = self.proofs[existing_id]
                owner = (group, actor, identity)
                if existing['owner'] != owner:
                    raise Conflict('This popup attempt is already bound to another account or item selection.')
                if existing['roots'] != roots:
                    self._invalidate(existing)
                    raise Conflict('This popup attempt is already bound to another account or item selection.')
                if existing['badge_code'] != data['badge_code']:
                    raise Conflict('This popup attempt is already bound to another account or item selection.')
                return self._verification_response(existing)
            active_count = sum(1 for proof in self.proofs.values() if proof['group'] == group and proof['actor'] == actor)
            if active_count >= self.MAX_PER_ACCOUNT_COLLECTION or len(self.proofs) >= self.MAX_TOTAL:
                raise Conflict('Too many active checkout verifications. Cancel an unused popup and try again.')
            verification_id = str(uuid4())
            session = Session(timeout=self.TIMEOUT_SECONDS, clock=self.clock)
            generation = session.start(actor)
            proof = {
                'id': verification_id, 'attempt_id': attempt_id, 'owner': (group, actor, identity),
                'group': group, 'actor': actor, 'identity': identity, 'roots': roots,
                'borrower': {'id': actor, 'name': member.get('name') or 'C-Crate member'},
                'required': sorted(required), 'entities': entities, 'kit_versions': kit_versions,
                'root_manifests': root_manifests,
                'badge_code': data['badge_code'], 'badges': badges, 'session': session, 'generation': generation,
                'created': self.clock(), 'consumed': False,
            }
            self.proofs[verification_id] = proof
            self.attempts[attempt_key] = verification_id
            return self._verification_response(proof)

    def _verification_response(self, proof):
        return {
            'verification_id': proof['id'], 'borrower': dict(proof['borrower']),
            'expires_in': self.TIMEOUT_SECONDS, 'required_items': list(proof['required']),
            'kit_versions': dict(proof['kit_versions']),
        }

    @staticmethod
    def _manifest_snapshot(kit):
        return {
            'kit': bool(kit['kit']),
            'entities': sorted(row['id'] for row in kit['entities']),
            'versions': dict(kit['versions']),
        }

    def _manifests_current(self, ctx, proof):
        try:
            for root in proof['roots']:
                current = manifest(ctx['client'], root)
                if self._manifest_snapshot(current) != proof['root_manifests'][root]:
                    return False
            return True
        except Exception:
            return False

    def _invalidate(self, proof):
        with self.lock:
            if self.proofs.get(proof['id']) is proof:
                proof['session'].end(proof['generation'])
                self._drop(proof['id'])

    def _get(self, ctx, verification_id):
        try:
            key = uuid(verification_id)
        except (ValueError, TypeError):
            raise ValueError('Checkout verification is missing or expired.') from None
        with self.lock:
            proof = self.proofs.get(key)
            if not proof or not proof['session'].active():
                self._drop(key)
                raise Conflict('Checkout verification expired. Scan the badge again.')
            if proof['owner'] != self._owner(ctx):
                raise Conflict('Checkout verification belongs to another account or collection.')
            if proof['consumed']:
                raise Conflict('This checkout verification was already used.')
            return proof

    def verify_item(self, ctx, data):
        if not isinstance(data, dict) or set(data) != {'verification_id', 'code'}:
            raise ValueError('Scan one native item code for this checkout.')
        proof = self._get(ctx, data['verification_id'])
        raw = data['code']
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError('Scan a native equipment label.')
        code = normalize(raw)
        candidates = list(proof['entities'].values())
        entity = next((row for row in candidates if code.get('kind') == 'entity' and row.get('id') == code.get('entity_id')), None)
        if not entity and code.get('kind') == 'asset':
            matched = [row for row in candidates if row.get('assetId') == code.get('asset_id') or row.get('barcode') == raw.strip()]
            if len({row['id'] for row in matched}) > 1:
                raise Conflict('This item code matches more than one selected record. Scan its native UUID label.')
            if matched:
                entity = matched[0]
        if not entity and code.get('kind') not in ('asset', 'entity'):
            resolved = resolve_equipment(raw, code, candidates)
            entity = resolved.get('entity') if isinstance(resolved, dict) else None
        if not entity or entity.get('id') not in proof['required']:
            raise Conflict('Scan the selected item or every component in its current kit.')
        if not proof['session'].active(activity=True) or not proof['session'].record_scan(entity['id']):
            raise Conflict('Checkout verification expired. Scan the badge again.')
        return {'verified_items': sorted(proof['session'].scans(proof['generation'])), 'required_items': list(proof['required'])}

    @staticmethod
    def _checkout_input(data):
        if not isinstance(data, dict) or set(data) - {'verification_id', 'assets', 'notes', 'request_key', 'cart'}:
            raise ValueError('Checkout request contains unsupported fields.')
        assets = WebItemActions._item_ids(data.get('assets'))
        request_key = uuid(data.get('request_key'))
        notes = CheckoutCart._notes(data.get('notes', {}), set(assets))
        cart = data.get('cart')
        cart_notes = {}
        if cart is not None:
            if not isinstance(cart, dict) or set(cart) - {'revision', 'items', 'notes'}:
                raise ValueError('Checkout cart context is invalid.')
            revision, items = cart.get('revision'), WebItemActions._item_ids(cart.get('items'))
            if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
                raise ValueError('Checkout cart revision is invalid.')
            cart_notes = CheckoutCart._notes(cart.get('notes', {}), set(items))
            cart = {'revision': revision, 'items': items}
            if cart_notes:
                cart['notes'] = cart_notes
            if 'notes' not in data:
                notes = cart_notes
        return assets, notes, request_key, cart

    @staticmethod
    def _intent(notes, cart):
        intent = {}
        if notes:
            intent['checkout_notes'] = notes
        if cart is not None:
            intent['checkout_cart'] = cart
        return intent or None

    def _replay(self, ctx, ledger, assets, notes, request_key, cart):
        prior = ledger.request(ctx['group'], request_key)
        if not prior:
            return None
        expected = ledger.request_digest(ctx['group'], ctx['actor'], 'check_out', assets, self._intent(notes, cart))
        if prior['actor_id'] != ctx['actor'] or prior['action'] != 'check_out' or prior['request_hash'] != expected:
            raise Conflict('This confirmation key belongs to a different checkout.')
        if prior['status'] == 'completed':
            count = len(ledger.detail(ctx['group'], prior['id'])['assets'])
            receipt = {'id': prior['id'], 'status': 'completed', 'action': 'check_out', 'count': count}
            if cart is not None:
                receipt['cart_consumption'] = CheckoutCart(ledger).consume_completed_receipt(ctx['group'], ctx['actor'], prior['id'])
            return receipt
        return {'id': prior['id'], 'status': prior['status'], 'action': 'check_out'}

    def checkout(self, ctx, ledger, data):
        assets, notes, request_key, cart = self._checkout_input(data)
        replay = self._replay(ctx, ledger, assets, notes, request_key, cart)
        if replay is not None:
            return replay
        proof = self._get(ctx, data.get('verification_id'))
        if assets != proof['required']:
            self._invalidate(proof)
            raise Conflict('Selected checkout items changed. Review them and scan the badge again.')
        if cart is not None and cart['items'] != proof['roots']:
            self._invalidate(proof)
            raise Conflict('Saved cart selection changed. Review it and scan the badge again.')
        if not self._manifests_current(ctx, proof):
            self._invalidate(proof)
            raise Conflict('The selected item or kit changed. Review its current contents and scan again.')
        verified = proof['session'].scans(proof['generation'])
        if not set(proof['required']) <= verified:
            raise Conflict('Scan every selected item and kit component before checkout.')
        members = ctx['client'].call('/api/v1/groups/members')
        member_ids = {uuid(row['id']) for row in members}
        if proof['actor'] not in member_ids or proof['badges'].resolve(proof['group'], proof['badge_code'], member_ids) != proof['actor']:
            raise Conflict('Badge is revoked or its holder is no longer a collection member. Scan a current badge.')
        with self.lock:
            current = self.proofs.get(proof['id'])
            if current is not proof or proof['consumed']:
                raise Conflict('Checkout verification changed. Scan the badge again.')
            proof['consumed'] = True
        def verification_valid():
            try:
                if not self._manifests_current(ctx, proof):
                    return False
                current_members = ctx['client'].call('/api/v1/groups/members')
                current_ids = {uuid(row['id']) for row in current_members}
                return (proof['session'].snapshot() == (proof['actor'], proof['generation'])
                        and proof['owner'] == self._owner(ctx)
                        and proof['actor'] in current_ids
                        and proof['badges'].resolve(proof['group'], proof['badge_code'], current_ids) == proof['actor'])
            except Exception:
                return False
        try:
            receipt = self.checkout_operation(
                ctx['client'], ledger, proof['group'], proof['actor'], assets, request_key,
                verification_valid,
                verified, proof['kit_versions'], cart,
                notes if 'notes' in data or (cart is not None and cart.get('notes')) else None,
            )
            if cart is not None and receipt.get('status') == 'completed':
                receipt = dict(receipt, cart_consumption=CheckoutCart(ledger).consume_completed_receipt(proof['group'], proof['actor'], receipt['id']))
            return receipt
        finally:
            with self.lock:
                self._drop(proof['id'])

    def cancel(self, ctx, data):
        if not isinstance(data, dict) or set(data) != {'verification_id'}:
            raise ValueError('Choose the checkout popup to cancel.')
        proof = self._get(ctx, data['verification_id'])
        with self.lock:
            proof['session'].end(proof['generation'])
            self._drop(proof['id'])
        return {'cancelled': True}

    @staticmethod
    def note(ctx, jobs, data):
        if not isinstance(data, dict) or set(data) != {'entity_id', 'note', 'request_key'}:
            raise ValueError('Item note request must contain only equipment, note and request key.')
        from item_notes import submit_note
        return submit_note(ctx['client'], jobs, ctx['group'], ctx['actor'], data['request_key'],
                           {'entity_id': data['entity_id'], 'note': data['note']},
                           (ctx.get('user') or {}).get('name') or 'C-Crate member')

    def checkin(self, ctx, ledger, data):
        if not isinstance(data, dict) or set(data) != {'targets', 'verified', 'kit_versions', 'request_key'}:
            raise ValueError('Check-in needs targets, kit verification and a request key.')
        if not isinstance(data['targets'], list):
            raise ValueError('Choose equipment to check in.')
        targets = []
        allowed = {'entity_id', 'destination_id', 'return_note', 'problem_description'}
        for target in data['targets']:
            if not isinstance(target, dict) or set(target) - allowed:
                raise ValueError('Check-in target contains unsupported fields.')
            item = {'entity_id': target.get('entity_id')}
            if 'destination_id' in target:
                item['destination_id'] = target['destination_id']
            if 'return_note' in target:
                item['return_note'] = target['return_note']
            if 'problem_description' in target:
                description = target['problem_description']
                if not isinstance(description, str) or not description.strip():
                    raise ValueError('Describe the problem before reporting it.')
                if len(description) > 1000:
                    raise ValueError('Problem description must be at most 1000 characters.')
                try:
                    description.encode('utf-8')
                except UnicodeEncodeError:
                    raise ValueError('Problem description contains invalid Unicode.') from None
                item.update(condition='Needs Attention', note=description.strip())
            targets.append(item)

        from returns import confirm_return, normalize_targets
        if not isinstance(data['verified'], list):
            raise ValueError('Verified check-in scans must be a list of native item IDs.')
        verified = [uuid(value) for value in data['verified']]
        if len(verified) != len(set(verified)):
            raise ValueError('Verified check-in scans must use distinct item IDs.')
        if not isinstance(data['kit_versions'], dict):
            raise ValueError('Current kit manifest versions are required.')
        kit_versions = {uuid(key): value for key, value in data['kit_versions'].items()}
        if any(not isinstance(value, str) for value in kit_versions.values()):
            raise ValueError('Current kit manifest versions are invalid.')
        normalized = normalize_targets(targets)
        group, actor, key = uuid(ctx['group']), uuid(ctx['actor']), uuid(data['request_key'])
        prior = ledger.request(group, key)
        if prior:
            expected = ledger.request_digest(group, actor, 'return',
                                             [target['entity_id'] for target in normalized], normalized)
            if prior['actor_id'] != actor or prior['action'] != 'return' or prior['request_hash'] != expected:
                raise Conflict('This confirmation key belongs to a different check-in.')
            if prior['status'] == 'completed':
                return {'id': prior['id'], 'status': 'completed', 'action': 'return',
                        'count': len(normalized)}

        # The API adapter runs this check while holding the shared mutation lock.
        # Check every target before confirm_return can journal or mutate any one.
        if not ctx['manager']:
            held = {row['entity_id']: row['actor_id'] for row in ledger.custody(group)}
            if any(held.get(target['entity_id']) != actor for target in normalized):
                raise Conflict('Members can check in only equipment currently borrowed by their account.')
        return confirm_return(ctx['client'], ledger, group, actor, normalized, key, lambda: True,
                              verified, kit_versions)

    @staticmethod
    def status(ctx, ledger, values):
        if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], str):
            raise ValueError('Choose checkout status IDs.')
        raw_ids = values[0].split(',')
        if not 1 <= len(raw_ids) <= 50:
            raise ValueError('Check status for between 1 and 50 items.')
        ids = [uuid(value) for value in raw_ids]
        if len(ids) != len(set(ids)):
            raise ValueError('Check status for distinct items.')
        group, actor = uuid(ctx['group']), uuid(ctx['actor'])
        loans = {row['entity_id']: row for row in ledger.custody(group)}
        unresolved = {}
        for operation in ledger.unresolved():
            if operation['group_id'] != group:
                continue
            label = 'Return' if operation['action'] == 'return' else 'Checkout'
            reason = f'{label} operation requires recovery ({operation["status"]})'
            for row in ledger.detail(group, operation['id'])['assets']:
                unresolved[row] = reason
        members = {uuid(row['id']): row.get('name') or 'C-Crate member'
                   for row in ctx['client'].call('/api/v1/groups/members')}
        result = []
        for entity_id in ids:
            try:
                entity = ctx['client'].entity(entity_id)
            except urllib.error.HTTPError as error:
                if error.code not in (403, 404):
                    raise
                result.append({'id': entity_id, 'availability': 'unknown',
                               'can_checkin': False, 'can_add_note': False})
                continue
            try:
                found_id = uuid(entity.get('id'))
            except (ValueError, TypeError):
                found_id = None
            if found_id != entity_id:
                result.append({'id': entity_id, 'availability': 'unknown',
                               'can_checkin': False, 'can_add_note': False})
                continue
            location = bool((entity.get('entityType') or {}).get('isLocation'))
            loan = loans.get(entity_id)
            blocker = checkout_blocker(entity)
            recovery_reason = unresolved.get(entity_id)
            entry = {'id': entity_id,
                     'can_checkin': bool(loan and not recovery_reason
                                         and (ctx['manager'] or loan['actor_id'] == actor)),
                     'can_add_note': not location and not entity.get('archived') and entity.get('quantity') == 1}
            if loan:
                entry['availability'] = 'checked_out'
                entry['loan'] = {'borrower_id': loan['actor_id'],
                                 'borrower_name': members.get(loan['actor_id'], 'Former C-Crate member'),
                                 'operation_id': loan['operation_id']}
                if recovery_reason or blocker:
                    entry['blocker'] = '; '.join(value for value in (recovery_reason, blocker) if value)
            elif recovery_reason:
                entry['availability'] = 'blocked'
                entry['blocker'] = '; '.join(value for value in (recovery_reason, blocker) if value)
            elif condition(entity) == 'Unreviewed':
                entry['availability'] = 'unknown'
                entry['blocker'] = blocker or 'Equipment condition is missing or unrecognized'
            elif blocker:
                entry['availability'] = 'blocked'
                entry['blocker'] = blocker
            else:
                entry['availability'] = 'available'
            result.append(entry)
        return {'items': result}
