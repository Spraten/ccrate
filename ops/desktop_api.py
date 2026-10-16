"""Authenticated desktop workflows; native Homebox cookies remain HttpOnly.

The public gateway calls handle() before the local kiosk handlers. Every desktop
request uses its own native client; no desktop mutation uses service credentials.
"""
import base64
import hashlib
import hmac
import importlib
import io
import json
import os
import pathlib
import urllib.error
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlsplit, quote
from uuid import uuid4

from conditions import STATES, checkout_blocker, condition
from checkout import confirm_checkout
from homebox import Homebox, session_cookie
from ledger import Conflict, timestamp, uuid, UNIDENTIFIED_ACTOR
from returns import RETURN_STATES, confirm_return, recover
from item_notes import project_note_history
from workshop import submit_shelf_order
from workshop_views import build_view, resolve_workshop_code
from shelf_checks import CheckAccessDenied, shelf_check_action
from network_access import trusted_native_origins
from native_fields import update_payload

PREFIX = '/workshop-api/'
PRODUCT_GROUP_TAG_PREFIX = 'C-Crate Product group: '
READ_POSTS = {'labels/preview', 'labels/paper', 'labels/templates/result', 'imports/get', 'operation/status', 'history/group', 'workshop/checks/resolve', 'workshop/checks/request'}
MANAGER_READS = {'people', 'badges', 'recovery', 'system', 'hardware/status', 'imports', 'invitations', 'users/administration', 'users/profile', 'labels/templates', 'workshop/checks/list', 'workshop/checks/get'}
SHELF_CHECK_POSTS = {'workshop/checks/resolve', 'workshop/checks/request'}
SHELF_CHECK_WRITES = {'workshop/checks/start', 'workshop/checks/observe', 'workshop/checks/notes', 'workshop/checks/refresh', 'workshop/checks/finish', 'workshop/checks/cancel'}
SHELF_CHECK_ROUTES = SHELF_CHECK_POSTS | SHELF_CHECK_WRITES


class ApiError(Exception):
    def __init__(self, status, message, code=None):
        self.status, self.message, self.code = status, message, code


def dependency(deps, name):
    return deps[name] if isinstance(deps, dict) else getattr(deps, name)


def optional(deps, name, default=None):
    return deps.get(name, default) if isinstance(deps, dict) else getattr(deps, name, default)


def native_op(module, function, *args, **kwargs):
    return getattr(importlib.import_module(module), function)(*args, **kwargs)


def labels_service(deps):
    service=optional(deps,'label_layouts')
    if service is not None:return service
    from label_layouts import LabelLayouts
    from label_render import DEFAULT_ASSET_ROOT
    root=pathlib.Path(dependency(deps,'root'))
    return LabelLayouts(root/'work/ops/label-layouts.db',asset_root=optional(deps,'label_asset_root',DEFAULT_ASSET_ROOT))


def checkout_cart_service(deps):
    service = optional(deps, 'checkout_cart')
    if service is None:
        from checkout_cart import CheckoutCart
        service = CheckoutCart(dependency(deps, 'ledger'))
        if isinstance(deps, dict):
            deps['checkout_cart'] = service
    return service


def serve_label_asset(handler,root,name,asset_root=None):
    from urllib.parse import unquote
    from label_render import _check_manifest,DEFAULT_ASSET_ROOT
    import re
    try:
        name=unquote(name);base=_check_manifest(asset_root or DEFAULT_ASSET_ROOT)
        manifest=json.loads((base/'manifest.json').read_text());allowed=manifest.get('runtime_assets',{})
        if name!='manifest.json' and name not in allowed:raise ValueError()
        path=(base/name).resolve(strict=True);path.relative_to(base)
        if not path.is_file():raise ValueError()
        content=path.read_bytes()
        if name in allowed and hashlib.sha256(content).hexdigest()!=allowed[name]:raise ValueError()
    except Exception:
        handler.reply_json(404,{'error':'Label asset not found'});return True
    mime={'.html':'text/html; charset=utf-8','.js':'application/javascript','.css':'text/css','.ttf':'font/ttf','.txt':'text/plain; charset=utf-8','.json':'application/json'}.get(path.suffix,'application/octet-stream')
    handler.send_response(200);handler.send_header('Content-Type',mime);handler.send_header('Content-Length',str(len(content)));handler.send_header('X-Content-Type-Options','nosniff')
    handler.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data: blob:; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'")
    immutable=path.parent.name=='assets' and bool(re.search(r'[-.][A-Za-z0-9_-]{8,}\.',path.name))
    handler.send_header('Cache-Control','public, max-age=31536000, immutable' if immutable else 'no-cache')
    handler.end_headers();handler.wfile.write(content);return True


def manager(deps, user, group):
    path = pathlib.Path(dependency(deps, 'root'))/'work/ops/desktop-managers.json'
    try:
        entries = json.loads(path.read_text(encoding='utf-8'))['managers']
        return any(uuid(entry['user_id']) == user and uuid(entry['group_id']) == group for entry in entries)
    except (OSError, ValueError, KeyError, TypeError):
        # Configuration failure must never promote a normal member.
        return False


def authenticate(handler, deps, deadline=None):
    try:
        cookie = session_cookie(handler.headers.get('Cookie'))
    except ValueError:
        raise ApiError(401, 'Sign in to C-Crate, then return to Workshop.', 'sign_in_required') from None
    factory = optional(deps, 'homebox_factory', Homebox.from_cookie)
    client = factory(cookie, base=optional(deps, 'native_base', os.environ.get('WORKSHOP_NATIVE_BASE', 'http://127.0.0.1:17745')))
    if deadline is not None:setattr(client,'deadline',deadline)
    client.workshop_code_origins = trusted_native_origins(
        optional(deps, 'workshop_public_port', os.environ.get('WORKSHOP_PORT', '17745')))
    user = client.call('/api/v1/users/self')['item']
    actor = uuid(user['id'])
    groups = {uuid(value) for value in user.get('groupIds', [])}
    group = uuid(handler.headers.get('X-Workshop-Group') or user['defaultGroupId'])
    if group not in groups:
        raise ApiError(403, 'You are not a member of this C-Crate collection.', 'collection_forbidden')
    client.tenant = group
    collection = client.call('/api/v1/groups')
    collection = collection.get('item', collection)
    # Validate the tenant response instead of trusting only the request header.
    if uuid(collection['id']) != group:
        raise ApiError(403, 'C-Crate did not confirm this collection.', 'collection_forbidden')
    cookies = SimpleCookie(); cookies.load(cookie)
    binding = hashlib.sha256(json.dumps([actor, group, cookies['hb.auth.token'].value], separators=(',', ':')).encode()).hexdigest()
    return {'client': client, 'actor': actor, 'group': group, 'identity': binding,
            'manager': manager(deps, actor, group),
            'user': {'id': actor, 'name': user.get('name', 'C-Crate member'), 'email': user.get('email', '')},
            'collection': {'id': group, 'name': collection.get('name', 'Workshop')}}


def origin(handler, deps):
    host = handler.headers.get('Host', '')
    parsed = urlsplit('http://'+host)
    if not host or parsed.netloc != host or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or '@' in host:
        raise ApiError(403, 'Invalid Workshop address.', 'origin_forbidden')
    expected = optional(deps, 'public_scheme', 'http')+'://'+host
    value = handler.headers.get('Origin')
    allowed = optional(deps, 'allowed_origins')
    if value != expected or (allowed is not None and value not in allowed):
        raise ApiError(403, 'Open Workshop on this device address and try again.', 'origin_forbidden')
    return expected


def read_body(handler):
    if handler.headers.get('Content-Type', '').split(';', 1)[0].strip().lower() != 'application/json':
        raise ApiError(415, 'Workshop requests must use JSON.')
    try:
        size = int(handler.headers.get('Content-Length', '0'))
    except ValueError:
        raise ApiError(400, 'Invalid request size.') from None
    if not 0 < size <= 1000000:
        raise ApiError(413, 'Use a request smaller than 1 MB.')
    try:
        data = json.loads(handler.rfile.read(size))
    except (ValueError, UnicodeError):
        raise ApiError(400, 'The request is not valid JSON.') from None
    if not isinstance(data, dict):
        raise ApiError(400, 'The request must be an object.')
    return data


def binding(handler, ctx):
    provided = handler.headers.get('X-Workshop-Identity', '')
    if not hmac.compare_digest(provided, ctx['identity']):
        raise ApiError(409, 'Your C-Crate account or collection changed. Reload Workshop before confirming.', 'identity_changed')


def require_manager(ctx):
    if not ctx['manager']:
        raise ApiError(403, 'A Workshop manager account is required for this action.', 'manager_required')


def entities(client, locations=False):
    # Do not reuse stock.browse(): its global kiosk cache is not tenant scoped.
    rows = []
    for summary in client.entities(locations):
        entity = client.entity(summary['id'])
        rows.append(dict(entity, condition=condition(entity), blocker=checkout_blocker(entity)))
    return rows


def public_entity(client, value):
    return client.entity(uuid(value))


def custom_group_change(client, route, data):
    name = data.get('group_name')
    if not isinstance(name, str):
        raise ValueError('Enter a product group name.')
    name = ' '.join(name.split())
    if not name or len(PRODUCT_GROUP_TAG_PREFIX + name) > 255:
        raise ValueError('Product group name must fit in a native tag.')
    full_name = PRODUCT_GROUP_TAG_PREFIX + name
    entity = public_entity(client, data.get('entity_id'))
    if (entity.get('entityType') or {}).get('isLocation'):
        raise ValueError('Choose equipment, not a storage location.')

    native_tags = client.call('/api/v1/tags')
    ids = [tag['id'] for tag in native_tags]
    if len(ids) != len(set(ids)):
        raise Conflict('Duplicate native tags need review in C-Crate.')
    candidates = [tag for tag in native_tags
                  if tag['name'].casefold().startswith(PRODUCT_GROUP_TAG_PREFIX.casefold())
                  and ' '.join(tag['name'][len(PRODUCT_GROUP_TAG_PREFIX):].split()).casefold() == name.casefold()]
    if route != 'equipment/groups/remove' and (len(candidates) > 1 or (candidates and
        candidates[0].get('parentId') not in (None, '', '00000000-0000-0000-0000-000000000000'))):
        raise Conflict('Product group tag name collides with a native tag; review it in C-Crate.')
    group_tags = [tag for tag in entity.get('tags', [])
                  if tag['name'].strip().casefold().startswith(PRODUCT_GROUP_TAG_PREFIX.casefold())]
    if len(group_tags) > 1 or len({tag['id'] for tag in entity.get('tags', [])}) != len(entity.get('tags', [])):
        raise Conflict('Duplicate product group tags need review in C-Crate.')
    existing = group_tags[0] if group_tags else None
    if existing and ' '.join(existing['name'][len(PRODUCT_GROUP_TAG_PREFIX):].split()).casefold() != name.casefold():
        raise Conflict('Remove the current product group before assigning another.')
    if existing and existing['id'] not in {tag['id'] for tag in candidates}:
        raise Conflict('Product group membership needs review in C-Crate.')

    if route == 'equipment/groups/remove':
        if not existing:
            raise Conflict('This equipment is not in that product group.')
        desired_ids = [tag['id'] for tag in entity.get('tags', []) if tag['id'] != existing['id']]
    else:
        if existing:
            return {'id': entity['id'], 'tags': entity.get('tags', [])}
        tag = candidates[0] if candidates else None
        if tag is None:
            try:
                tag = client.call('/api/v1/tags', 'POST',
                                  {'name': full_name, 'description': 'C-Crate product group', 'color': '#64748b'})
            except urllib.error.HTTPError:
                raise
            except (OSError, TimeoutError):
                reread = [item for item in client.call('/api/v1/tags') if item['name'] == full_name]
                if len(reread) != 1:
                    raise Conflict('Product group tag creation needs review in C-Crate.') from None
                tag = reread[0]
        desired_ids = [item['id'] for item in entity.get('tags', [])] + [tag['id']]

    payload = update_payload(entity)
    payload['tagIds'] = desired_ids
    client.call('/api/v1/entities/' + entity['id'], 'PUT', payload)
    updated = client.entity(entity['id'])
    if updated['id'] != entity['id'] or {tag['id'] for tag in updated.get('tags', [])} != set(desired_ids):
        raise Conflict('C-Crate did not confirm the product group change.')
    for key in entity:
        if key not in ('tags', 'updatedAt', 'updatedBy') and updated.get(key) != entity[key]:
            raise Conflict('Native equipment metadata changed during the product group update; review it in C-Crate.')
    return {'id': updated['id'], 'tags': updated.get('tags', [])}



def history(ctx, deps, entity_id=None):
    client, group = ctx['client'], ctx['group']
    if entity_id:
        public_entity(client, entity_id)
    rows = dependency(deps, 'ledger').history(group, entity_id)+dependency(deps, 'native_jobs').history(group, entity_id)
    names = {member['id']: member['name'] for member in client.call('/api/v1/groups/members')}
    labels = {entity['id']: entity['name'] for entity in client.entities()+client.entities(True)}
    labels.update(names)
    for row in rows:
        row['actor'] = 'Unidentified returner' if row['actor_id'] == UNIDENTIFIED_ACTOR else names.get(row['actor_id'], 'Former C-Crate member')
        row['asset_names'] = [labels.get(key, 'Deleted native record') for key in row['assets']]
        if row['action'] == 'return':
            detail = dependency(deps, 'ledger').detail(group, row['id'])
            row['previous_borrowers'] = (detail['context'] or {}).get('desktop_previous_borrowers', [])
        elif row['action'] == 'add_note' and entity_id:
            project_note_history(row, client, dependency(deps, 'native_jobs'), group, entity_id)
    return sorted(rows, key=lambda row: row['created_at'], reverse=True)[:100]


def group_history(ctx, deps, data):
    values = data.get('entity_ids')
    if not isinstance(values, list) or not 1 <= len(values) <= 100:
        raise ValueError('Choose 1 to 100 distinct equipment records.')
    if not all(isinstance(value, str) for value in values):
        raise ValueError('Choose valid equipment record IDs.')
    ids = [uuid(value) for value in values]
    if len(ids) != len(set(ids)):
        raise ValueError('Choose distinct equipment records.')
    available = {uuid(entity['id']) for entity in ctx['client'].entities(False)}
    if any(entity_id not in available for entity_id in ids):
        raise ApiError(403, 'C-Crate denied access to this collection or record.', 'collection_forbidden')
    return dependency(deps, 'ledger').group_return_notes(ctx['group'], ids, limit=100)


def journal_schema(ledger):
    with ledger.transaction() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS desktop_requests(
          id TEXT PRIMARY KEY, group_id TEXT NOT NULL,actor_id TEXT NOT NULL,
          kind TEXT NOT NULL,request_key TEXT NOT NULL,digest TEXT NOT NULL,
          status TEXT NOT NULL,result TEXT,created_at TEXT NOT NULL,
          UNIQUE(group_id,request_key))''')
        if 'intent' not in {row['name'] for row in db.execute('PRAGMA table_info(desktop_requests)')}:
            db.execute("ALTER TABLE desktop_requests ADD COLUMN intent TEXT NOT NULL DEFAULT '{}'")
        db.execute('''CREATE TABLE IF NOT EXISTS desktop_request_events(
          sequence INTEGER PRIMARY KEY,request_id TEXT NOT NULL,
          actor_id TEXT NOT NULL,kind TEXT NOT NULL,detail TEXT NOT NULL,created_at TEXT NOT NULL)''')
        db.execute('''CREATE TRIGGER IF NOT EXISTS no_desktop_request_event_update BEFORE UPDATE ON desktop_request_events
          BEGIN SELECT RAISE(ABORT,'events are append-only'); END''')
        db.execute('''CREATE TRIGGER IF NOT EXISTS no_desktop_request_event_delete BEFORE DELETE ON desktop_request_events
          BEGIN SELECT RAISE(ABORT,'events are append-only'); END''')


def request_row(ledger, group, key):
    journal_schema(ledger)
    with ledger.connection() as db:
        row = db.execute('SELECT * FROM desktop_requests WHERE group_id=? AND request_key=?', (group, uuid(key))).fetchone()
    return dict(row) if row else None


def safe_intent(kind, data):
    """Keep enough recovery context without persisting CSV, tokens or passwords."""
    fields = {
        'badges/issue': ('user_id',), 'badges/revoke': ('id',), 'badges/reprint': ('badge_id',), 'badges/replace': ('badge_id',), 'permissions/set': ('user_id', 'enabled'),
        'invitation/create': ('uses',), 'imports/upload': ('filename', 'source'),
        'imports/map': ('id', 'location_id', 'type_id'), 'imports/save': ('id', 'index'),
        'workshop/move': ('id', 'parent_id', 'updated_at'),
        'users/create': ('name',), 'users/update': ('user_id', 'updatedAt'),
    }.get(kind, ())
    result = {key: data[key] for key in fields if key in data and isinstance(data[key], (str, int, bool, type(None)))}
    if kind == 'workshop/save':
        document = data.get('document')
        if isinstance(document, dict) and document.get('version') == 2 and isinstance(document.get('rooms'), list):
            result['room_summaries'] = [
                {'id': room.get('id'), 'name': room.get('name'), 'object_count': len(room.get('objects', []))}
                for room in document['rooms'][:20] if isinstance(room, dict)
            ]
            canonical = json.dumps(document, sort_keys=True, separators=(',', ':'))
            result['document_digest'] = hashlib.sha256(canonical.encode()).hexdigest()
        elif isinstance(data.get('layout'), dict):
            result.update(layout_name=data['layout'].get('name'), revision=data.get('revision'), object_count=len(data['layout'].get('objects', [])))
    if kind == 'users/create':
        result['user_id'] = uuid(data.get('request_key'))
    if kind == 'users/update':
        profile = native_op('accounts', 'profile_input', data)
        result['profile_digest'] = hashlib.sha256(json.dumps([profile[key] for key in ('name','email','avatar','notes')], separators=(',', ':')).encode()).hexdigest()
    return result


def once(ctx, deps, kind, data, perform, redact=lambda value: value):
    """Durably refuse duplicate/uncertain non-entity actions without storing tokens."""
    ledger = dependency(deps, 'ledger'); journal_schema(ledger)
    key = uuid(data.get('request_key'))
    intent = {name: value for name, value in data.items() if name != 'request_key'}
    digest = (dependency(deps, 'workshop').request_digest(ctx['actor'], data) if kind == 'workshop/save' else
              hashlib.sha256(json.dumps([ctx['actor'], kind, intent], sort_keys=True, separators=(',', ':')).encode()).hexdigest())
    workshop_prior = None
    with ledger.transaction() as db:
        prior = db.execute('SELECT * FROM desktop_requests WHERE group_id=? AND request_key=?', (ctx['group'], key)).fetchone()
        if prior:
            if prior['digest'] != digest:
                raise Conflict('This confirmation key belongs to a different action.')
            if kind == 'workshop/save':
                }Ó}m¢G§²ÚîÆ­yÑpi/v1/groups/members')
        def replace_badge():
            result = badges.replace(group, badge_id, [member['id'] for member in members])
            sessions = optional(deps, 'sessions')
            if sessions is not None:
                sessions.revoke_user(result['user_id'])
            return dict(result, qr=badge_qr(result['code']), status='completed')
        return once(ctx, deps, route, data, replace_badge, lambda value: {'id': value['id'], 'user_id': value['user_id'], 'code': None})
    if route == 'invitation/create':
        uses = data.get('uses', 1)
        if type(uses) is not int or not 1 <= uses <= 20:
            raise ValueError('Choose 1 to 20 invitation uses.')
        def invite():
            result = client.call('/api/v1/groups/invitations', 'POST', {'uses': uses, 'expiresAt': (datetime.now(timezone.utc)+timedelta(days=7)).isoformat()})
            return dict(result, join_url=address+'/?token='+quote(result['token']), status='completed')
        return once(ctx, deps, route, data, invite, lambda value: {key: value for key, value in value.items() if key not in ('token', 'join_url')})
    if route == 'condition':
        public_entity(client, data.get('entity_id'))
        return native_op('reviews', 'submit_review', client, jobs, group, actor, data.get('request_key'), data)
    if route == 'return':
        targets = data.get('targets')
        if not isinstance(targets, list) or not all(isinstance(target, dict) for target in targets):
            raise ValueError('Choose a list of equipment to return.')
        previous = {row['entity_id']: {'entity_id': row['entity_id'], 'user_id': row['actor_id'], 'checkout_operation_id': row['operation_id']} for row in ledger.custody(group)}
        return confirm_return(client, ReturnLedger(ledger, previous), group, actor, targets, data.get('request_key'), lambda: True, data.get('verified'), data.get('kit_versions'))
    if route.startswith('imports/'):
        imports = dependency(deps, 'imports'); action = route.split('/', 1)[1]
        if action == 'upload':
            return once(ctx, deps, route, data, lambda: imports.upload(group, actor, data), lambda value: {'id': value['id'], 'status': 'completed'})
        if action == 'get':
            return imports.sync(client, jobs, group, data)
        if action == 'map':
            return once(ctx, deps, route, data, lambda: imports.map(client, group, data), lambda value: {'id': value['id'], 'status': 'completed'})
        if action in ('save', 'create', 'label'):
            if action == 'save':
                return once(ctx, deps, route, data, lambda: imports.save(client, jobs, group, data), lambda value: {'id': value['id'], 'status': 'completed'})
            if action == 'label':
                return imports.label(client,ActorJobs(jobs,actor),group,data,actor=actor,layouts=labels_service(deps))
            return getattr(imports, action)(client, ActorJobs(jobs, actor), group, data)
        raise ApiError(404, 'Unknown import action.')
    if route == 'workshop/save':
        workshop = dependency(deps, 'workshop')
        if not isinstance(data, dict) or type(data.get('schema_version')) is not int or data['schema_version'] != 2:
            raise ValueError('This Workshop save is outdated. Reload before saving.')
        prior = request_row(ledger, group, data.get('request_key'))
        if prior is None:
            replay = workshop.replay_save(group, data, actor_id=actor)
            if replay is not None:
                return replay
            workshop.validate_save(client, group, data)
        return once(ctx, deps, route, data, lambda: workshop.save(client, group, data, actor_id=actor))
    if route == 'workshop/shelf-order':
        return submit_shelf_order(client, jobs, group, actor, data.get('request_key'), data)
    if route == 'workshop/move':
        if request_row(ledger, group, data.get('request_key')) is None:
            entity = public_entity(client, data.get('id'))
            if entity.get('archived'):
                raise ValueError('Choose an active item or location.')
            parent = uuid(data['parent_id']) if data.get('parent_id') else None
            if parent != (entity.get('parent') or {}).get('id') and data.get('updated_at') != entity.get('updatedAt'):
                raise Conflict('This item or location changed. Reload it before moving.')
            if parent:
                destination = public_entity(client, parent)
                if destination.get('archived'):
                    raise ValueError('Choose an active destination item or location.')
            native_op('hierarchy', 'validate_parent', client, parent, entity['id'])
        return once(ctx, deps, route, data, lambda: native_op('workshop', 'move_location', client, data))
    if route == 'locations/create':
        return native_op('setup_native', 'submit', client, jobs, group, actor, 'create_location', data.get('request_key'), data.get('input', {}))
    if route == 'recovery/resolve':
        if data.get('desktop_job'):
            job_id = uuid(data.get('id'))
            if data.get('outcome') not in ('complete', 'cancel') or data.get('inspected') is not True:
                raise ValueError('Inspect the native result and confirm inspected before resolving this action.')
            journal_schema(ledger)
            with ledger.transaction() as db:
                row = db.execute("SELECT * FROM desktop_requests WHERE group_id=? AND id=? AND status IN ('pending','review')", (group, job_id)).fetchone()
                if not row:
                    raise Conflict('This action is already resolved or belongs to another collection.')
                result = None
                if row['kind'] in ('users/create','users/update'):
                    intent = json.loads(row['intent']); user_id = intent['user_id']
                    try: profile = native_op('accounts', 'get_profile', client, user_id)
                    except urllib.error.HTTPError as error:
                        if error.code != 404: raise
                        profile = None
                    if row['kind'] == 'users/create':
                        matches = profile is not None
                    else:
                        matches = profile is not None and hashlib.sha256(json.dumps([profile['name'], profile['email'].lower(), profile['avatar'], profile['notes']], separators=(',', ':')).encode()).hexdigest() == intent['profile_digest']
                    if (data['outcome'] == 'complete') != matches:
                        raise ValueError('Inspect Manage users: choose complete only when the saved account/profile matches this action. Cancellation does not undo saved changes.')
                    if profile: result = {'id':profile['id'],'name':profile['name']}
                state = 'completed' if data['outcome'] == 'complete' else 'cancelled'
                db.execute('UPDATE desktop_requests SET status=?,result=? WHERE id=?', (state, json.dumps(dict(result or {'id': job_id}, status=state, acknowledged_by=actor)), job_id))
                db.execute('INSERT INTO desktop_request_events(request_id,actor_id,kind,detail,created_at) VALUES(?,?,?,?,?)',
                           (job_id, actor, 'desktop_recovery_resolved', json.dumps({'outcome': data['outcome'], 'inspected': True}), timestamp()))
            return {'id': job_id, 'status': state}
        if data.get('outcome') not in ('complete', 'cancel'):
            raise ValueError('Choose complete or cancel.')
        if data.get('native_job'):
            job = jobs.detail(group, data.get('id'))
            if job['status'] not in ('prepared', 'sent', 'review'):
                raise Conflict('This native task is already resolved.')
            with ledger.transaction() as db:
                jobs.event(db, job['id'], 'desktop_recovery_requested', {'actor_id': actor, 'outcome': data['outcome']})
            module, function = ('item_notes', 'recover_note') if job['kind'] == 'add_note' else ('code_registration', 'recover_code') if job['kind'] == 'register_code' else ('categories', 'recover_category') if job['kind'] == 'create_type' else ('reviews', 'recover_review') if job['kind'] in ('review_condition', 'complete_maintenance') else ('labels', 'recover_print') if job['kind'] in ('print_label', 'print_badge') else ('problems', 'recover_problem') if job['kind'] == 'report_problem' else ('workshop', 'recover_shelf_order') if job['kind'] == 'workshop_shelf_order' else ('setup_native', 'recover_creation')
            if module=='labels':result=native_op(module,function,client,jobs,group,data.get('id'),data.get('outcome'),layouts=labels_service(deps))
            else:result = native_op(module, function, client, jobs, group, data.get('id'), data.get('outcome'))
            with ledger.transaction() as db:
                jobs.event(db, job['id'], 'desktop_recovery_resolved', {'actor_id': actor, 'outcome': data['outcome']})
            return result
        record = ledger.detail(group, data.get('id'))
        if record['status'] not in ('pending', 'review'):
            raise Conflict('This operation is already resolved.')
        ledger.record(record['id'], 'desktop_recovery_requested', {'actor_id': actor, 'outcome': data['outcome']})
        result = recover(client, ledger, group, data.get('id'), data.get('outcome'))
        with ledger.transaction() as db:
            ledger.event(db, record['id'], 'desktop_recovery_resolved', {'actor_id': actor, 'outcome': data['outcome']})
        return result
    if route == 'backup/start':
        if os.environ.get('WORKSHOP_LOCAL_TEST') == '1':
            raise ValueError('Backup is unavailable in local test; no external backup destination is configured')
        return once(ctx, deps, route, data, lambda: native_op('system_status', 'start_backup', data.get('request_key')))
    raise ApiError(404, 'Unknown Workshop action.')


def handle(handler, deps):
    parsed = urlsplit(handler.path)
    if not parsed.path.startswith(PREFIX):
        return False
    asset_prefix=PREFIX+'label-assets/'
    if parsed.path.startswith(asset_prefix):
        if handler.command!='GET':handler.send_error(405);return True
        return serve_label_asset(handler,dependency(deps,'root'),parsed.path[len(asset_prefix):],optional(deps,'label_asset_root'))
    try:
        if handler.command not in ('GET', 'POST'):
            raise ApiError(405, 'Use GET or POST for Workshop requests.')
        route = parsed.path[len(PREFIX):].rstrip('/')
        import time
        label_deadline=time.monotonic()+20 if route.startswith('labels/') else None
        if handler.command == 'GET':
            if route=='labels/templates':
                lock=dependency(deps,'lock')
                if not lock.acquire(timeout=2):raise ApiError(503,'Label service is busy. Try again.')
                try:
                    ctx=authenticate(handler,deps,deadline=label_deadline);ctx['label_deadline']=label_deadline
                    result=get_action(route,parse_qs(parsed.query),ctx,deps)
                finally:lock.release()
            else:
                ctx = authenticate(handler, deps)
                query = parse_qs(parsed.query, keep_blank_values=True)
                if route.startswith('workshop/checks/') and any(handler.headers.get(name) for name in ('X-Workshop-Actor', 'X-Workshop-Manager')):
                    raise ApiError(400, 'Shelf-check identity is supplied by Workshop.')
                if route.startswith('workshop/checks/') and any(name in query for name in ('actor', 'actor_id', 'group', 'group_id', 'manager')):
                    raise ApiError(400, 'Shelf-check identity is supplied by Workshop.')
                if route.startswith('workshop/checks/') and route in MANAGER_READS:
                    require_manager(ctx)
                if route == 'workshop/view' or route.startswith('workshop/checks/'):
                    binding(handler, ctx)
                result = get_action(route, query, ctx, deps)
        else:
            address = origin(handler, deps); data = read_body(handler)
            # Re-authentication happens after acquiring the kiosk's mutation
            # lock, so a queued request cannot write using stale membership.
            lock=dependency(deps,'lock')
            if route.startswith('labels/'):
                if not lock.acquire(timeout=2):raise ApiError(503,'Label service is busy. Try again.')
                try:
                    ctx=authenticate(handler,deps,deadline=label_deadline);binding(handler,ctx);ctx['label_deadline']=label_deadline
                    result=post_action(route,data,ctx,deps,address)
                finally:lock.release()
            else:
                with lock:
                    ctx = authenticate(handler, deps); binding(handler, ctx)
                    if route == 'history/group':
                        result = group_history(ctx, deps, data)
                    elif route in ('equipment/groups/assign', 'equipment/groups/remove'):
                        require_manager(ctx)
                        result = custom_group_change(ctx['client'], route, data)
                    else:
                        result = post_action(route, data, ctx, deps, address)
                    if route in {'condition', 'return', 'imports/create', 'workshop/move', 'locations/create', 'recovery/resolve'}:
                        native_op('stock', 'invalidate')
        handler.reply_json(200, result)
    except ApiError as error:
        handler.reply_json(error.status, {'error': error.message, 'code': error.code})
    except urllib.error.HTTPError as error:
        if error.code == 401:
            handler.reply_json(401, {'error': 'C-Crate sign-in expired. Sign in again.', 'code': 'sign_in_required'})
        elif error.code == 403:
            handler.reply_json(403, {'error': 'C-Crate denied access to this collection or record.', 'code': 'collection_forbidden'})
        elif error.code == 404:
            handler.reply_json(404, {'error': 'Native C-Crate record not found.'})
        elif 400 <= error.code < 500:
            handler.reply_json(400, {'error': 'C-Crate rejected the request. Check the details before confirming again.'})
        else:
            handler.reply_json(503, {'error': 'C-Crate is temporarily unavailable. Check recovery before repeating a write.'})
    except Conflict as error:
        handler.reply_json(409, {'error': str(error), 'code': 'needs_review'})
    except CheckAccessDenied as error:
        handler.reply_json(403, {'error': str(error), 'code': 'manager_required'})
    except (ValueError, KeyError, TypeError) as error:
        handler.reply_json(400, {'error': str(error) if isinstance(error, ValueError) else 'The request or native record needs review.'})
    except (OSError, TimeoutError):
        if route in {'labels/templates','labels/preview','labels/paper','labels/templates/result'}:handler.reply_json(503,{'error':'Label service is busy or timed out. Select fewer items or preview again.'})
        else:handler.reply_json(503, {'error': 'The service is temporarily unavailable. Check saved results before repeating a write.'})
    except Exception:
        handler.reply_json(500, {'error': 'The operation could not be confirmed. Check recovery before repeating a write.'})
    return True
