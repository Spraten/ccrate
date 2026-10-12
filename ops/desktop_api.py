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
from homebox import Homebox, session_cookie
from ledger import Conflict, timestamp, uuid, UNIDENTIFIED_ACTOR
from returns import RETURN_STATES, confirm_return, recover
from item_notes import project_note_history
from workshop import submit_shelf_order
from workshop_views import build_view, resolve_workshop_code
from shelf_checks import CheckAccessDenied, shelf_check_action
from network_access import trusted_native_origins

PREFIX = '/workshop-api/'
READ_POSTS = {'labels/preview', 'labels/paper', 'labels/templates/result', 'imports/get', 'operation/status', 'workshop/checks/resolve', 'workshop/checks/request'}
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
                if prior['kind'] != kind or prior['actor_id'] != ctx['actor']:
                    raise Conflict('This confirmation key belongs to a different action or actor.')
                workshop_prior = dict(prior)
            else:
                if prior['status'] == 'completed':
                    return dict(json.loads(prior['result']), status='completed', message='This action already completed. Secret codes are shown only once.')
                raise Conflict('This action has an uncertain result. Inspect Workshop recovery before repeating it.')
        else:
            request_id = str(uuid4())
            db.execute('INSERT INTO desktop_requests(id,group_id,actor_id,kind,request_key,digest,status,result,created_at,intent) VALUES(?,?,?,?,?,?,?,?,?,?)',
                       (request_id, ctx['group'], ctx['actor'], kind, key, digest, 'pending', None, timestamp(), json.dumps(safe_intent(kind, data))))
    if workshop_prior:
        workshop = dependency(deps, 'workshop')
        saved = workshop.replay_save(ctx['group'], data, actor_id=ctx['actor'])
        receipt = workshop.save_binding(ctx['group'], key)
        if saved is None or not receipt or receipt['actor_id'] != workshop_prior['actor_id'] or receipt['digest'] != workshop_prior['digest']:
            raise Conflict('This Workshop save has no matching completed receipt; inspect recovery before repeating it.')
        if workshop_prior['status'] != 'completed':
            with ledger.transaction() as db:
                db.execute("UPDATE desktop_requests SET status='completed',result=? WHERE id=?", (json.dumps(saved), workshop_prior['id']))
        return saved
    try:
        result = perform()
        safe = redact(result)
        with ledger.transaction() as db:
            db.execute("UPDATE desktop_requests SET status='completed',result=? WHERE id=?", (json.dumps(safe), request_id))
        return result
    except Exception:
        with ledger.transaction() as db:
            db.execute("UPDATE desktop_requests SET status='review' WHERE id=?", (request_id,))
        raise


def badge_qr(code):
    import qrcode
    stream = io.BytesIO(); qrcode.make(code).save(stream, format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode()


class ReturnLedger:
    """Add operator/borrower provenance to the intent before native writes start."""
    def __init__(self, ledger, borrowers):
        self.ledger, self.borrowers = ledger, borrowers

    def __getattr__(self, name):
        return getattr(self.ledger, name)

    def begin(self, group, actor, action, assets, request_key, context=None, intent=None):
        if action == 'return':
            context = dict(context or {}, desktop_previous_borrowers=[self.borrowers[key] for key in assets if key in self.borrowers])
        return self.ledger.begin(group, actor, action, assets, request_key, context=context, intent=intent)


class ActorJobs:
    """Keep CSV uploader provenance while attributing new jobs to this operator."""
    def __init__(self, jobs, actor):
        self.jobs, self.actor = jobs, actor

    def __getattr__(self, name):
        return getattr(self.jobs, name)

    def prepare(self, group, actor, kind, key, payload):
        return self.jobs.prepare(group, self.actor, kind, key, payload)


def recovery_rows(ctx, deps):
    ledger, jobs, client = dependency(deps, 'ledger'), dependency(deps, 'native_jobs'), ctx['client']
    rows = []
    for row in ledger.unresolved():
        if row['group_id'] != ctx['group']:
            continue
        detail = ledger.detail(ctx['group'], row['id'])
        detail.pop('request_hash', None); detail.pop('request_key', None)
        detail['native_assets'] = []
        for entity_id in detail['assets']:
            try:
                entity = public_entity(client, entity_id)
                detail['native_assets'].append({'id': entity_id, 'name': entity['name'], 'condition': condition(entity), 'parent': (entity.get('parent') or {}).get('name', 'Unassigned')})
            except urllib.error.HTTPError as error:
                if error.code not in (403, 404):
                    raise
                detail['native_assets'].append({'id': entity_id, 'name': 'Native equipment unavailable', 'error': 'Inspect C-Crate before resolving.'})
        rows.append(detail)
    for job in jobs.unresolved(ctx['group']):
        payload = job['payload'] or {}
        target = job['result_id'] or payload.get('entity_id')
        name = payload.get('name') or 'Native workflow task'
        asset_id = None
        if job['kind'] == 'print_badge':
            member_names = {member['id']: member['name'] for member in client.call('/api/v1/groups/members')}
            badge = next((row for row in dependency(deps, 'badges').list(ctx['group']) if row['id'] == payload.get('badge_id')), None)
            target = target or (badge['user_id'] if badge else None)
            name = 'Badge for '+member_names.get(target, 'Former C-Crate member')
        elif target:
            try:
                entity = public_entity(client, target)
                name, asset_id = entity['name'], entity.get('assetId')
            except urllib.error.HTTPError as error:
                if error.code not in (403, 404):
                    raise
                name = payload.get('name') or 'Native equipment unavailable'
        safe = {key: payload[key] for key in ('entity_id', 'badge_id', 'maintenance_id') if payload.get(key)}
        rows.append({'id': job['id'], 'action': job['kind'], 'status': job['status'], 'native_job': True, 'actor_id': job['actor_id'],
                     'created_at': job['created_at'], 'intent': safe,
                     'native_assets': [{'id': target, 'name': name, 'assetId': asset_id}], 'context': None,
                     **({'message': 'Inspect the native rack shelf order in C-Crate before resolving it. No automatic retry.'}
                        if job['kind'] == 'workshop_shelf_order' else {})})
    journal_schema(ledger)
    with ledger.connection() as db:
        requests = db.execute("SELECT id,kind,status,actor_id,created_at,intent FROM desktop_requests WHERE group_id=? AND status IN ('pending','review')", (ctx['group'],)).fetchall()
    rows.extend({'id': row['id'], 'action': row['kind'], 'status': row['status'], 'desktop_job': True, 'actor_id': row['actor_id'],
                 'native_assets': [], 'context': None, 'created_at': row['created_at'], 'intent': json.loads(row['intent']),
                 'message': 'Inspect Manage users and the saved profile before acknowledging this action. No automatic retry.' if row['kind'].startswith('users/') else 'Inspect People badges, native invitations or saved imports before acknowledging this action. No automatic retry.'} for row in requests)
    return rows


def get_action(route, query, ctx, deps):
    client, group = ctx['client'], ctx['group']
    if route == 'context':
        return {'user': ctx['user'], 'group': ctx['collection'], 'manager': ctx['manager'], 'identity': ctx['identity']}
    if route in MANAGER_READS:
        require_manager(ctx)
    if route == 'workshop/checks/list':
        values = query.get('location_id', [None])
        limits = query.get('limit', ['100'])
        if len(values) != 1 or len(limits) != 1:
            raise ValueError('Choose one shelf location and history limit')
        try:
            limit = int(limits[0])
        except (TypeError, ValueError):
            raise ValueError('History limit must be between 1 and 100') from None
        return shelf_check_action(dependency(deps, 'shelf_checks'), client,
            {'group': group, 'actor': ctx['actor'], 'manager': ctx['manager']}, 'list',
            {'location_id': values[0] or None, 'limit': limit})
    if route == 'workshop/checks/get':
        values = query.get('id', [])
        if len(values) != 1:
            raise ValueError('Choose one shelf check')
        return shelf_check_action(dependency(deps, 'shelf_checks'), client,
            {'group': group, 'actor': ctx['actor'], 'manager': ctx['manager']}, 'get', {'id': values[0]})
    if route == 'equipment':
        return entities(client)
    if route == 'locations':
        return entities(client, True)
    if route == 'types':
        return client.call('/api/v1/entity-types')
    if route == 'entity':
        entity = public_entity(client, query.get('id', [None])[0])
        return {'entity': entity, 'condition': condition(entity), 'blocker': checkout_blocker(entity), 'states': STATES, 'return_states': RETURN_STATES}
    if route == 'kit':
        return native_op('kits', 'manifest', client, query.get('id', [None])[0])
    if route == 'loans':
        members = {member['id']: member['name'] for member in client.call('/api/v1/groups/members')}
        ledger = dependency(deps, 'ledger')
        rows = ledger.custody(group)
        checkout_times = {}
        for row in rows:
            row['borrower'] = members.get(row['actor_id'], 'Former C-Crate member')
            operation_id = row['operation_id']
            if operation_id not in checkout_times:
                detail = ledger.detail(group, operation_id)
                checkout_times[operation_id] = next((event['created_at'] for event in detail['events'] if event['kind'] == 'completed'), detail['created_at'])
            row['checked_out_at'] = checkout_times[operation_id]
            try:
                entity = public_entity(client, row['entity_id'])
                row['entity_name'] = entity['name']; row['assetId'] = entity.get('assetId'); row['parent'] = entity.get('parent')
                photos = [attachment for attachment in entity.get('attachments', []) if attachment.get('type') == 'photo']
                photo = next((attachment for attachment in photos if attachment.get('primary')), photos[0] if photos else None)
                row['imageId'] = photo['id'] if photo else None
                row['thumbnailId'] = (photo.get('thumbnail') or {}).get('id') if photo else None
            except urllib.error.HTTPError as error:
                if error.code not in (403, 404):
                    raise
                row['entity_name'] = 'Native equipment unavailable'; row['unavailable'] = True
        return rows
    if route == 'history':
        return history(ctx, deps, query.get('entity', [None])[0])
    if route == 'people':
        path = pathlib.Path(dependency(deps, 'root'))/'work/ops/desktop-managers.json'
        try:
            owner = json.loads(path.read_text()).get('owner_id')
        except (OSError, ValueError):
            owner = None
        return [dict(member, workshop_manager=manager(deps, member['id'], group), protected_owner=member['id'] == owner) for member in client.call('/api/v1/groups/members')]
    if route == 'badges':
        return dependency(deps, 'badges').list(group)
    if route == 'users/administration':
        return client.call('/api/v1/groups/members/administration')
    if route == 'users/profile':
        return native_op('accounts', 'get_profile', client, query.get('id', [None])[0])
    if route == 'invitations':
        # Native tokens are shown only during explicit invitation creation.
        return [{name: value for name, value in row.items() if name != 'token'} for row in client.call('/api/v1/groups/invitations')]
    if route == 'recovery':
        return recovery_rows(ctx, deps)
    if route == 'system':
        return native_op('system_status', 'status')
    if route == 'hardware/status':
        return {'printer': native_op('hardware', 'reconnect', 'printer'),
                'camera': native_op('hardware', 'camera_status')}
    if route == 'workshop':
        return dependency(deps, 'workshop').snapshot(client, group)
    if route == 'labels/templates':
        import time
        if ctx.get('label_deadline') is not None and time.monotonic()>=ctx['label_deadline']:raise TimeoutError('Label request exceeded its 20-second budget')
        layouts=labels_service(deps);jobs=optional(deps,'native_jobs')
        if jobs and hasattr(layouts,'reconcile_reviews'):
            try:layouts.reconcile_reviews(group,jobs)
            except (OSError,TimeoutError):pass
        result=layouts.list(group)
        if ctx.get('label_deadline') is not None and time.monotonic()>=ctx['label_deadline']:raise TimeoutError('Label request exceeded its 20-second budget')
        return result
    if route == 'workshop/view':
        nested_values = query.get('nested', ['0'])
        if len(nested_values) != 1 or nested_values[0] not in ('0', '1'):
            raise ApiError(400, 'Choose whether to include nested equipment.')
        nested = nested_values[0]
        room_values = query.get('room_id', [None])
        if len(room_values) != 1:
            raise ApiError(400, 'Choose one workshop room.')
        room = room_values[0] or None
        if room is not None:
            try:
                room = uuid(room)
            except (ValueError, TypeError):
                raise ApiError(400, 'Choose an available workshop room.') from None
        workshop = dependency(deps, 'workshop').get(group)
        if room is not None and room not in {item.get('id') for item in workshop.get('document', {}).get('rooms', [])}:
            raise ApiError(400, 'Choose an available workshop room.')
        return build_view(client, workshop, dependency(deps, 'ledger').custody(group),
                          entity_id=query.get('id', [None])[0], include_nested=nested == '1',
                          room_id=room, can_view_loans=ctx['manager'])
    if route == 'imports':
        return dependency(deps, 'imports').list(group)
    raise ApiError(404, 'Unknown Workshop page.')


def operation_status(ctx, deps, data):
    ledger, jobs, group = dependency(deps, 'ledger'), dependency(deps, 'native_jobs'), ctx['group']
    key = uuid(data.get('request_key'))
    checks = optional(deps, 'shelf_checks')
    if checks is not None:
        with ledger.connection() as db:
            shelf_request = db.execute('SELECT 1 FROM shelf_check_requests WHERE group_id=? AND request_key=?',
                                       (group, key)).fetchone()
        if shelf_request:
            if any(name in data for name in ('actor', 'actor_id', 'group', 'group_id', 'manager')):
                raise ValueError('Shelf-check identity is supplied by Workshop')
            require_manager(ctx)
            check_request = checks.request({'group': group, 'actor': ctx['actor'], 'manager': ctx['manager']}, key)
            return check_request
    row = ledger.request(group, key)
    if row:
        return {'id': row['id'], 'status': row['status'], 'action': row['action']}
    with ledger.connection() as db:
        row = db.execute('SELECT id,status,kind FROM native_jobs WHERE group_id=? AND request_key=?', (group, key)).fetchone()
    if row:
        return {'id': row['id'], 'status': row['status'], 'action': row['kind'], 'native_job': True}
    row = request_row(ledger, group, key)
    workshop=optional(deps,'workshop')
    if row and row['kind']!='workshop/save':
        return {'id': row['id'], 'status': row['status'], 'action': row['kind'], 'desktop_job': True,
                'result': json.loads(row['result']) if row['result'] else None}
    if workshop is not None:
        receipt=workshop.save_status(group,key,actor_id=ctx['actor'])
        if receipt['status']=='completed':
            binding=workshop.save_binding(group,key)
            if row and (row['actor_id']!=binding['actor_id'] or row['kind']!='workshop/save' or row['digest']!=binding['digest']):
                raise Conflict('This confirmation key belongs to a different save or action.')
            if row and row['status']!='completed':
                with ledger.transaction() as db:
                    db.execute("UPDATE desktop_requests SET status='completed',result=? WHERE id=?",
                               (json.dumps(receipt['result']),row['id']))
            return receipt
    return {'id': row['id'], 'status': row['status'], 'action': row['kind'], 'desktop_job': True,
            'result': json.loads(row['result']) if row['result'] else None} if row else {'status': 'not_started'}


def post_action(route, data, ctx, deps, address):
    client, group, actor = ctx['client'], ctx['group'], ctx['actor']
    ledger, jobs, badges = dependency(deps, 'ledger'), dependency(deps, 'native_jobs'), dependency(deps, 'badges')
    if route == 'operation/status':
        return operation_status(ctx, deps, data)
    if route in SHELF_CHECK_ROUTES:
        require_manager(ctx)
        store = dependency(deps, 'shelf_checks')
        check_ctx = {'group': group, 'actor': actor, 'manager': ctx['manager']}
        return shelf_check_action(store, client, check_ctx, route.rsplit('/', 1)[1], data)
    if route == 'workshop/resolve':
        code = data.get('code')
        if not isinstance(code, str):
            raise ValueError('Enter a native equipment code.')
        return resolve_workshop_code(client, code)
    require_manager(ctx)
    if route in ('users/create', 'users/update'):
        if not client.call('/api/v1/groups/members/administration')['canManage']:
            raise ApiError(403, 'A collection owner is required to manage users.')
        if route == 'users/create':
            native_op('accounts', 'creation_input', data)
            return once(ctx, deps, route, data, lambda: native_op('accounts', 'create_account', client, data), lambda value: {'id': value['id'], 'name': value['name']})
        user_id = uuid(data.get('user_id'))
        native_op('accounts', 'profile_input', data)
        if request_row(ledger, group, data.get('request_key')) is None:
            current = native_op('accounts', 'get_profile', client, user_id)
            if not current['editable']:
                raise ApiError(403, "This person's profile is managed in their primary collection.")
            if current['updatedAt'] != data.get('updatedAt'):
                raise ApiError(409, 'This profile changed. Reload it before saving.')
        return once(ctx, deps, route, data, lambda: native_op('accounts', 'update_profile', client, user_id, data), lambda value: {'id': value['id'], 'name': value['name']})
    if route == 'hardware/reconnect':
        return native_op('hardware', 'reconnect', data.get('device'))
    if route == 'permissions/set':
        user_id = uuid(data.get('user_id'))
        enabled = data.get('enabled')
        if type(enabled) is not bool:
            raise ValueError('Choose whether to allow management.')
        if user_id not in {member['id'] for member in client.call('/api/v1/groups/members')}:
            raise ValueError('Choose a current C-Crate member.')
        path = pathlib.Path(dependency(deps, 'root'))/'work/ops/desktop-managers.json'
        configuration = json.loads(path.read_text())
        if not enabled and (user_id == actor or user_id == configuration.get('owner_id')):
            raise ValueError('Keep your own management access and the Workshop Admin access enabled.')
        def save_permission():
            entries = [entry for entry in configuration['managers'] if not (entry['user_id'] == user_id and entry['group_id'] == group)]
            if enabled:
                entries.append({'user_id': user_id, 'group_id': group})
            configuration['managers'] = entries
            temporary = path.with_suffix('.tmp')
            with temporary.open('w', encoding='utf-8') as output:
                os.chmod(temporary, 0o600)
                json.dump(configuration, output, indent=2)
                output.flush(); os.fsync(output.fileno())
            os.replace(temporary, path)
            return {'user_id': user_id, 'enabled': enabled, 'status': 'completed'}
        return once(ctx, deps, route, data, save_permission)
    if route.startswith('labels/'):
        import time
        if ctx.get('label_deadline') is not None and time.monotonic()>=ctx['label_deadline']:raise TimeoutError('Label request exceeded its 20-second budget')
        layouts=labels_service(deps)
        if route=='labels/templates/save':return layouts.save(group,actor,data)
        if route=='labels/templates/result':
            result=layouts.save_result(group,actor,data.get('request_key'))
            if ctx.get('label_deadline') is not None and time.monotonic()>=ctx['label_deadline']:raise TimeoutError('Label result lookup exceeded the 20-second request budget')
            return result
        if route=='labels/preview':
            if not data.get('mode') and data.get('entity_id'):
                entity=public_entity(client,data.get('entity_id'))
                if entity.get('isLocation') or (entity.get('entityType') or {}).get('isLocation'):
                    return native_op('labels','preview',client,data.get('entity_id'))
                raise ValueError('Choose a saved template and review the item before printing')
            return layouts.preview(client,group,actor,data,deadline=ctx.get('label_deadline'))
        if route=='labels/print':
            if not data.get('review_id'):
                entity=public_entity(client,data.get('entity_id'))
                if entity.get('isLocation') or (entity.get('entityType') or {}).get('isLocation'):
                    return native_op('labels','print_label',client,jobs,group,actor,data.get('request_key'),data.get('entity_id'))
            return native_op('labels','print_label',client,jobs,group,actor,data.get('request_key'),data.get('entity_id'),layouts=layouts,review_id=data.get('review_id'))
        if route=='labels/paper':return native_op('labels','paper',client,layouts,group,actor,data,deadline=ctx.get('label_deadline'))
        raise ApiError(404,'Unknown label action.')
    if route == 'badges/issue':
        user_id = uuid(data.get('user_id')); members = client.call('/api/v1/groups/members')
        if user_id not in {member['id'] for member in members}:
            raise ApiError(400, 'Choose a current member of this collection.')
        def issue():
            result = badges.issue(group, user_id, [member['id'] for member in members])
            return dict(result, qr=badge_qr(result['code']), status='completed')
        return once(ctx, deps, route, data, issue, lambda value: {'id': value['id'], 'user_id': value['user_id'], 'code': None})
    if route == 'badges/revoke':
        badge_id = uuid(data.get('id'))
        badge = next((row for row in badges.list(group) if row['id'] == badge_id), None)
        if not badge:
            raise ApiError(404, 'Badge not found in this collection.')
        def revoke_badge():
            revoked = badges.revoke(group, badge_id)
            sessions = optional(deps, 'sessions')
            if sessions is not None:
                sessions.revoke_user(badge['user_id'])
            return {'id': badge_id, 'revoked': revoked, 'status': 'completed'}
        return once(ctx, deps, route, data, revoke_badge)
    if route == 'badges/print':
        return native_op('labels', 'print_badge', client, badges, jobs, group, actor, data.get('request_key'), data.get('badge_id'), data.get('code'))
    if route == 'badges/reprint':
        return native_op('labels', 'reprint_badge', client, badges, jobs, group, actor,
                         data.get('request_key'), data.get('badge_id'))
    if route == 'badges/replace':
        badge_id = uuid(data.get('badge_id'))
        members = client.call('/api/v1/groups/members')
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
