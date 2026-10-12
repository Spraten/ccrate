"""Fixture-only direct packaged-module checks for release workflow state."""
import hashlib
import importlib
import json
import base64
import shutil
import tempfile
import sys
from pathlib import Path
from uuid import UUID, uuid4


class _NativeFixture:
    def __init__(self, location_id, item_id):
        self.base = 'http://fixture.invalid'
        self.workshop_code_origins = ()
        self.group = str(uuid4())
        self.actor_a = str(uuid4())
        self.actor_b = str(uuid4())
        self.nodes = {
            location_id: {'id': location_id, 'name': 'Fixture Shelf',
                          'entityType': {'isLocation': True}, 'parent': None,
                          'archived': False, 'quantity': 1, 'updatedAt': 'fixture-v1', 'version': 1},
            item_id: {'id': item_id, 'name': 'Fixture Quantity Item',
                      'entityType': {'isLocation': False}, 'parent': {'id': location_id},
                      'archived': False, 'quantity': 2, 'updatedAt': 'fixture-v1', 'version': 1},
        }

    def entity(self, entity_id):
        if entity_id not in self.nodes:
            raise KeyError(entity_id)
        return dict(self.nodes[entity_id])

    def entities(self, *, locations=False):
        return [dict(row) for row in self.nodes.values()
                if bool(row['entityType']['isLocation']) is locations]

    def call(self, path, method='GET', **kwargs):
        if path == '/api/v1/groups/members':
            return [{'id': self.actor_a}, {'id': self.actor_b}]
        raise ValueError('Unexpected fixture native call')


def _load_shelf(package):
    package = Path(package).resolve(strict=True)
    modules, state = _load_ops(package, ('ledger', 'shelf_checks'))
    return modules['ledger'], modules['shelf_checks'], Path(modules['shelf_checks'].__file__), state


def run_shelf_lifecycle(bundles, ledger_path):
    bundles, ledger_path = Path(bundles), Path(ledger_path)
    location_id, item_id = str(uuid4()), str(uuid4())
    client = _NativeFixture(location_id, item_id)
    context_a = {'manager': True, 'group': client.group, 'actor': client.actor_a}
    context_b = {'manager': True, 'group': client.group, 'actor': client.actor_b}
    trace = []
    first_result = None
    cancel_key = str(uuid4())
    for package_name in ('O', 'C', 'F', 'C'):
        package = bundles / package_name
        ledger_module, shelf_module, source, state = _load_shelf(package)
        try:
            ledger = ledger_module.Ledger(ledger_path)
            store = shelf_module.ShelfChecks(ledger)
            if package_name == 'O':
                draft = store.start(client, context_a, location_id=location_id,
                                    request_key=str(uuid4()))
                observed = store.observe(client, context_a, draft['id'], revision=draft['revision'],
                    entity_id=item_id, method='visual', observed_quantity=3, request_key=str(uuid4()))
                noted = store.save_notes(client, context_a, observed['id'], revision=observed['revision'],
                    notes='Fixture-only private shelf note', request_key=str(uuid4()))
                cancel_result = store.cancel(client, context_b, noted['id'], revision=noted['revision'],
                    confirmed=True, reason='Fixture cancellation after lost response', request_key=cancel_key)
                # Deliberately drop the response. Reopen on C using only request-key recovery.
                first_result = {'id': cancel_result['id'], 'key': cancel_key}
                recovered = store.request(context_b, cancel_key)
            else:
                recovered = store.request(context_b, cancel_key)
                if not first_result or recovered.get('status') != 'completed':
                    raise RuntimeError('cancel request-key result did not recover after package transition')
            check = store.get(client, context_b, first_result['id'])
            history = store.history(client, context_b, location_id=location_id)
            observation = check['observations'][0]
            with ledger.connection() as db:
                request_count = db.execute('SELECT count(*) FROM shelf_check_requests WHERE group_id=? AND request_key=?',
                                           (client.group, cancel_key)).fetchone()[0]
            if (recovered.get('status') != 'completed' or check['state'] != 'cancelled'
                    or check['notes'] != 'Fixture-only private shelf note'
                    or observation['observed_quantity'] != 3
                    or check['original_snapshot']['items'][0]['quantity'] != 2
                    or len(history) != 1 or request_count != 1):
                raise RuntimeError('Shelf observation, history, private note, quantity or one-shot recovery changed')
            st = ledger_path.stat()
            row = {'package': package_name,
                   'bundle_manifest_sha256': hashlib.sha256((package / 'manifest.json').read_bytes()).hexdigest(),
                   'module_sha256': state['module_sha256'],
                   'module_origins': state['module_origins'],
                   'ledger_store_identity': [st.st_dev, st.st_ino],
                   'result': 'passed'}
            row.update({'check_state': check['state'], 'revision': check['revision'],
                        'observed_quantity': observation['observed_quantity'],
                        'expected_quantity': check['original_snapshot']['items'][0]['quantity'],
                        'history_count': len(history), 'private_note_sha256': hashlib.sha256(
                            check['notes'].encode()).hexdigest(),
                        'cancel_request_recovered': recovered['result']['id'] == first_result['id'],
                        'cancel_request_row_count': request_count})
            trace.append(row)
        finally:
            _unload_ops(('ledger', 'shelf_checks'), state)
    identities = {tuple(row['ledger_store_identity']) for row in trace}
    report = {'scope': 'fixture-only', 'trace': trace,
            'same_ledger_store': len(identities) == 1,
            'observation_history_private_note_quantity_preserved': True,
            'cancel_response_loss_request_key_recovered_once': True,
            'trusted_context_seam': 'fixture-only manager B, canonical group and actor UUIDs',
            'cross_manager_http_claim': False,
            'store_path': str(ledger_path)}
    validate_shelf_workflow(report, [row['bundle_manifest_sha256'] for row in trace], bundles=bundles)
    return report


def validate_shelf_workflow(report, expected_manifest_hashes, *, bundles=None):
    expected_packages = ['O', 'C', 'F', 'C']
    trace = report.get('trace') if isinstance(report, dict) else None
    if (report.get('scope') != 'fixture-only' or report.get('same_ledger_store') is not True
            or report.get('observation_history_private_note_quantity_preserved') is not True):
        raise ValueError('Shelf observation/history/private-note/quantity assertion failed')
    if report.get('cancel_response_loss_request_key_recovered_once') is not True:
        raise ValueError('Shelf cancellation request recovery assertion failed')
    if report.get('trusted_context_seam') != 'fixture-only manager B, canonical group and actor UUIDs':
        raise ValueError('Shelf manager context must be identified as fixture-only')
    if report.get('cross_manager_http_claim') is not False:
        raise ValueError('Shelf fixture seam cannot claim cross-manager packaged HTTP behavior')
    trace = _validate_transition_trace(report, expected_manifest_hashes, bundles=bundles,
                                      required_modules={'ledger', 'shelf_checks'})
    if [row.get('package') for row in trace] != expected_packages:
        raise ValueError('Shelf report must bind O/C/F/C to one Ledger store')
    for row in trace:
        if (row.get('check_state') != 'cancelled'
                or row.get('observed_quantity') != 3 or row.get('expected_quantity') != 2
                or type(row.get('observed_quantity')) is not int
                or type(row.get('expected_quantity')) is not int
                or type(row.get('history_count')) is not int or row.get('history_count') != 1
                or row.get('cancel_request_recovered') is not True
                or type(row.get('cancel_request_row_count')) is not int or row.get('cancel_request_row_count') != 1
                or not _valid_sha256(row.get('private_note_sha256'))):
            raise ValueError('Shelf state or one-shot cancellation recovery is incomplete')
    return True


def _load_ops(package, names):
    package = Path(package).resolve(strict=True)
    paths = [str(package / 'ops'), str(package / 'kiosk')]
    tracked = {path.stem for folder in ('ops', 'kiosk')
               for path in (package / folder).glob('*.py')}
    tracked.update(names)
    old_path = list(sys.path)
    prior = {name: sys.modules[name] for name in tracked if name in sys.modules}
    for name in tracked:
        sys.modules.pop(name, None)
    sys.path[:0] = paths
    try:
        modules = {name: importlib.import_module(name) for name in names}
        origins, hashes = {}, {}
        for name in sorted(tracked):
            module = sys.modules.get(name)
            filename = getattr(module, '__file__', None)
            if not filename:
                continue
            source = Path(filename).resolve(strict=True)
            try:
                relative = source.relative_to(package).as_posix()
            except ValueError:
                raise RuntimeError(f'{name} dependency escaped the selected immutable package') from None
            if relative not in {f'ops/{name}.py', f'kiosk/{name}.py'}:
                raise RuntimeError(f'{name} origin is not the selected package module')
            origins[name] = relative
            hashes[name] = hashlib.sha256(source.read_bytes()).hexdigest()
        missing = set(names) - set(origins)
        if missing:
            raise RuntimeError(f'project modules did not load from selected immutable package: {sorted(missing)}')
        state = {'package': package, 'tracked': tracked, 'prior': prior,
                 'sys_path': old_path, 'module_origins': origins, 'module_sha256': hashes}
        return modules, state
    except BaseException:
        sys.path[:] = old_path
        for name in tracked:
            sys.modules.pop(name, None)
        sys.modules.update(prior)
        raise


def _unload_ops(names, state):
    for name in state['tracked']:
        sys.modules.pop(name, None)
    sys.modules.update(state['prior'])
    sys.path[:] = state['sys_path']


class _PrintClient:
    def __init__(self, item):
        self.item = item
        self.physical_print_calls = 0

    def entity(self, _entity_id):
        return dict(self.item)


def run_label_lifecycle(bundles, ledger_path, review_path):
    bundles, ledger_path, review_path = map(Path, (bundles, ledger_path, review_path))
    group, actor, entity_id = (str(uuid4()) for _ in range(3))
    client = _PrintClient({'id': entity_id, 'name': 'Fixture label item', 'assetId': 'FIXTURE-01',
                           'updatedAt': 'fixture-v1', 'archived': False,
                           'entityType': {'isLocation': False}})
    rows, job_id, review_id = [], None, None
    for index, package_name in enumerate(('O', 'C', 'F', 'C')):
        package = bundles / package_name
        names = ('ledger', 'native_jobs', 'label_layouts', 'labels')
        modules, state = _load_ops(package, names)
        try:
            ledger = modules['ledger'].Ledger(ledger_path)
            jobs = modules['native_jobs'].NativeJobs(ledger)
            layouts = modules['label_layouts'].LabelLayouts(
                review_path, asset_root=package / 'label-ui')
            if package_name == 'O':
                response = layouts.preview(client, group, actor, {
                    'mode': 'item', 'entity_id': entity_id,
                    'template_id': 'starter:supvan:left', 'template_revision': 0})
                review_id = response['review_id']
                if not review_id:
                    raise RuntimeError('packaged preview did not persist a review ID')
                ticket = layouts.review(group, actor, review_id)
                if not ticket or hashlib.sha256(ticket['png']).hexdigest() != response['sha256']:
                    raise RuntimeError('reviewed label raster hash differs from preview')
                prepared = jobs.prepare(group, actor, 'print_label', str(uuid4()),
                    {'entity_id': entity_id, 'review_id': review_id})
                job_id = prepared['id']
                layouts.attach_review(group, actor, review_id, job_id)
            if not job_id or not review_id:
                raise RuntimeError('review intent was not initialized before a package transition')
            # Read fresh SQLite bytes and metadata through each selected package instance.
            ticket = layouts.review(group, actor, review_id)
            if ticket is None or ticket.get('attached_job') != job_id:
                raise RuntimeError('persisted label review is missing or detached after transition')
            metadata = {key: ticket[key] for key in (
                'review_id', 'template_id', 'template_revision', 'template_hash', 'sha256',
                'profile', 'label_mm', 'dpi', 'width', 'height', 'item_id', 'item_updated_at')}
            raster_sha = hashlib.sha256(ticket['png']).hexdigest()
            if raster_sha != ticket.get('sha256') or ticket['item_id'] != entity_id:
                raise RuntimeError('persisted label raster or item metadata changed after transition')
            before = jobs.detail(group, job_id)
            if before['status'] != 'prepared':
                raise RuntimeError('prepared print intent resolved before final C recovery')
            cancel_here = index == 3
            if cancel_here:
                recovered = modules['labels'].recover_print(
                    client, jobs, group, job_id, 'cancel', layouts=layouts)
                after = jobs.detail(group, job_id)
                if recovered.get('status') != 'cancelled' or after.get('status') != 'cancelled':
                    raise RuntimeError('final C failed to recover the prepared print cancellation')
                if layouts.review(group, actor, review_id) is not None:
                    raise RuntimeError('final C did not resolve the reviewed label after cancellation')
            else:
                after = jobs.detail(group, job_id)
                if after.get('status') != 'prepared':
                    raise RuntimeError('prepared print intent did not remain unresolved across transition')
            st = ledger_path.stat()
            rows.append({'package': package_name,
                         'bundle_manifest_sha256': hashlib.sha256((package / 'manifest.json').read_bytes()).hexdigest(),
                         'module_sha256': state['module_sha256'],
                         'module_origins': state['module_origins'],
                         'ledger_store_identity': [st.st_dev, st.st_ino],
                         'job_id': job_id, 'job_status': after['status'],
                         'job_status_before_action': before['status'],
                         'review_id': review_id, 'item_id': entity_id,
                         'review_metadata': metadata,
                         'review_read_from_persisted_store': True,
                         'reviewed_raster_sha256': raster_sha,
                         'review_metadata_sha256': hashlib.sha256(json.dumps(
                             metadata, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                         'cancel_recovered_here': cancel_here,
                         'review_resolved_after_transition': cancel_here,
                         'physical_print_calls': client.physical_print_calls, 'result': 'passed'})
        finally:
            _unload_ops(names, state)
    report = {'scope': 'fixture-only', 'trace': rows,
            'same_ledger_store': len({tuple(row['ledger_store_identity']) for row in rows}) == 1,
            'reviewed_raster_intent_recovery_preserved': True,
            'physical_print_calls': client.physical_print_calls,
            'review_metadata': rows[0]['review_metadata'],
            'claim': 'real packaged label layout preview, native job intent and cancellation recovery; physical output disabled'}
    validate_label_workflow(report, [row['bundle_manifest_sha256'] for row in rows], bundles=bundles)
    return report


class _NoteClient:
    def __init__(self, group, entity_id):
        self.group = group
        self.tenant = group
        self.entity_id = entity_id
        self.item = {'id': entity_id, 'name': 'Fixture note item', 'archived': False,
                     'entityType': {'isLocation': False}}
        self.entries = []
        self.posts = 0
        self.after_post = False

    def entity(self, entity_id):
        if entity_id != self.entity_id:
            raise KeyError(entity_id)
        return dict(self.item)

    def call(self, path, method='GET', data=None):
        if path != f'/api/v1/entities/{self.entity_id}/maintenance':
            raise ValueError('Unexpected note fixture endpoint')
        if method == 'GET':
            return [dict(row) for row in self.entries]
        if method != 'POST':
            raise ValueError('Unexpected note fixture method')
        self.posts += 1
        row = {'id': str(uuid4()), **data}
        self.entries.append(row)
        if self.after_post:
            self.after_post = False
            raise OSError('fixture dropped response after native entry commit')
        return {'item': dict(row)}


class _LiveHomeboxMaintenanceClient:
    """Authenticated adapter to the owned disposable native listener."""
    def __init__(self, manager, *, drop_after_commit=False):
        self.manager = manager
        self.base = f'http://127.0.0.1:{manager.native_port}'
        self.child = manager.children['native'][0]
        self.token = manager._native_auth()
        self.drop_after_commit = drop_after_commit
        self.post_calls = 0
        self.post_commits = 0

    def entity(self, entity_id):
        return self.manager._api_json(self.base, f'/api/v1/entities/{entity_id}',
            token=self.token, child=self.child, port=self.manager.native_port)

    def call(self, path, method='GET', data=None):
        if not path.startswith('/api/v1/entities/') or not path.endswith('/maintenance'):
            raise ValueError('Unexpected live fixture maintenance endpoint')
        if method == 'POST':
            self.post_calls += 1
        result = self.manager._api_json(self.base, path, method,
            data if method == 'POST' else None, token=self.token,
            child=self.child, port=self.manager.native_port)
        if method == 'POST':
            self.post_commits += 1
            if self.drop_after_commit:
                self.drop_after_commit = False
                raise OSError('fixture dropped response after live native POST committed')
        return result


def advance_live_uncertain_note(manager, bundles, package_name, ledger_path, state=None):
    """Advance one note proof stage while the named package is selected and live."""
    packages = ('O', 'C', 'F', 'C')
    index = len(state['trace']) if state is not None else 0
    if index >= len(packages) or package_name != packages[index]:
        raise ValueError('live note proof must follow O/C/F/C selected-process order')
    bundles, ledger_path = Path(bundles), Path(ledger_path)
    if state is None:
        native = manager.native_state
        state = {'key': str(uuid4()), 'group_id': native['group_id'],
                 'actor_id': native['member_id'], 'entity_id': native['entity_id'],
                 'note': 'Fixture note committed through disposable native API',
                 'actual_post_calls': 0, 'actual_post_commits': 0, 'trace': []}
    package = bundles / package_name
    names = ('ledger', 'native_jobs', 'item_notes')
    modules, module_state = _load_ops(package, names)
    try:
        ledger = modules['ledger'].Ledger(ledger_path)
        jobs = modules['native_jobs'].NativeJobs(ledger)
        client = _LiveHomeboxMaintenanceClient(manager,
            drop_after_commit=(index == 1))
        group, actor, entity_id, note = (state[name] for name in
                                         ('group_id', 'actor_id', 'entity_id', 'note'))
        payload = {'entity_id': entity_id, 'note': note}
        if index == 0:
            detail = jobs.lookup(group, actor, 'add_note', state['key'], payload)
            if detail is not None:
                raise RuntimeError('O unexpectedly contains the new fixture item note')
        elif index == 1:
            try:
                modules['item_notes'].submit_note(client, jobs, group, actor,
                    state['key'], payload, 'Fixture Operator')
            except modules['ledger'].Conflict:
                pass
            else:
                raise RuntimeError('live native dropped response did not leave an uncertain note')
            detail = jobs.lookup(group, actor, 'add_note', state['key'], payload)
            if not detail or detail['status'] != 'review' or not detail['context'].get('note_creation_started'):
                raise RuntimeError('C did not retain a started note journal in review')
            state['job_id'] = detail['id']
        else:
            detail = jobs.detail(group, state['job_id'])
            if index == 2:
                if detail['status'] != 'review' or not detail['context'].get('note_creation_started'):
                    raise RuntimeError('F did not reopen the unresolved C note journal')
                before = client.call(f'/api/v1/entities/{entity_id}/maintenance')
                if len(before) != 1:
                    raise RuntimeError('F could not verify exactly one committed live maintenance entry')
                result = modules['item_notes'].recover_note(client, jobs, group,
                                                            state['job_id'], 'complete')
                detail = jobs.detail(group, state['job_id'])
                if result.get('status') != 'completed' or detail['status'] != 'completed':
                    raise RuntimeError('F packaged item_notes did not complete note recovery')
            elif detail['status'] != 'completed':
                raise RuntimeError('final C did not reopen the completed fallback note')
        entries = client.call(f'/api/v1/entities/{entity_id}/maintenance')
        if (len(entries) != (0 if index == 0 else 1)
                or client.post_calls != (1 if index == 1 else 0)):
            raise RuntimeError('live native maintenance entry count or one-POST boundary changed')
        state['actual_post_calls'] += client.post_calls
        state['actual_post_commits'] += client.post_commits
        status = detail['status'] if detail else 'absent'
        if index == 1 and status not in ('sent', 'review'):
            raise RuntimeError('C note response loss did not remain unresolved')
        if index >= 2 and status != 'completed':
            raise RuntimeError('recovered note did not stay completed')
        st = ledger_path.stat()
        row = {'package': package_name,
               'bundle_manifest_sha256': hashlib.sha256((package / 'manifest.json').read_bytes()).hexdigest(),
               'module_sha256': module_state['module_sha256'],
               'module_origins': module_state['module_origins'],
               'ledger_store_identity': [st.st_dev, st.st_ino],
               'job_id': state.get('job_id'), 'job_exists': detail is not None,
               'job_status': status, 'native_entry_count': len(entries),
               'native_post_count': state['actual_post_commits'],
               'native_post_call_count': state['actual_post_calls'],
               'candidate_exposed_before_create': index >= 1,
               'note_created_here': index == 1,
               'journal_unresolved_after_transition': index == 1,
               'recovery_performed_here': index == 2,
               'recovery_from_status': 'review' if index == 2 else None,
               'result': 'passed'}
        if state.get('job_id'):
            for prior in state['trace']:
                prior['job_id'] = state['job_id']
        state['trace'].append(row)
        return state, row
    finally:
        _unload_ops(names, module_state)


def finish_live_uncertain_note(manager, rows, state, *, bundles):
    if state['actual_post_calls'] != 1 or state['actual_post_commits'] != 1:
        raise ValueError('live native note must have exactly one committed POST and no retry')
    if len(rows) != 4 or rows != state['trace']:
        raise ValueError('live note report must contain the exact four selected-package stages')
    report = {'scope': 'fixture-only', 'trace': rows,
              'same_ledger_store': len({tuple(row['ledger_store_identity']) for row in rows}) == 1,
              'uncertain_item_note_exactly_once_recovery_preserved': True,
              'native_entry_count': rows[-1]['native_entry_count'],
              'native_post_count': state['actual_post_commits'],
              'native_post_call_count': state['actual_post_calls'],
              'note_created_under': 'C', 'recovered_under': 'F',
              'final_candidate_state': rows[-1]['job_status'],
              'native_endpoint': f'http://127.0.0.1:{manager.native_port}/api/v1/entities/*/maintenance',
              'native_api_boundary': 'authenticated owned disposable native Homebox listener with PID checks',
              'response_loss_injected_after_native_commit': True,
              'claim': 'packaged item_notes recovery using authenticated disposable native Homebox API'}
    return report


def run_uncertain_note_lifecycle(bundles, ledger_path):
    bundles, ledger_path = Path(bundles), Path(ledger_path)
    group, actor, entity_id = (str(uuid4()) for _ in range(3))
    client = _NoteClient(group, entity_id)
    key, job_id, rows = str(uuid4()), None, []
    for index, package_name in enumerate(('O', 'C', 'F', 'C')):
        package = bundles / package_name
        names = ('ledger', 'native_jobs', 'item_notes')
        modules, state = _load_ops(package, names)
        try:
            ledger = modules['ledger'].Ledger(ledger_path)
            jobs = modules['native_jobs'].NativeJobs(ledger)
            recover_here = package_name == 'F'
            recovery_from_status = None
            if package_name == 'C' and index == 1:
                # The note begins only after the candidate package is exposed.
                client.after_post = True
                try:
                    modules['item_notes'].submit_note(client, jobs, group, actor, key,
                        {'entity_id': entity_id, 'note': 'Fixture note committed before response loss'},
                        'Fixture Operator')
                except modules['ledger'].Conflict:
                    pass
                else:
                    raise RuntimeError('lost native note response was not marked uncertain')
                pending = jobs.lookup(group, actor, 'add_note', key,
                    {'entity_id': entity_id, 'note': 'Fixture note committed before response loss'})
                job_id = pending['id']
                if pending['status'] not in ('sent', 'review'):
                    raise RuntimeError('uncertain note intent was not durable')
            if package_name == 'O':
                detail = None
                if client.posts != 0 or client.entries:
                    raise RuntimeError('new item note was written before candidate exposure')
            else:
                if not job_id:
                    raise RuntimeError('candidate did not create the uncertain note intent')
                detail = jobs.detail(group, job_id)
                recovery_from_status = detail['status'] if recover_here else None
                if index == 1 and (detail['status'] not in ('sent', 'review')
                                   or not detail['context'].get('note_creation_started')):
                    raise RuntimeError('candidate did not retain the lost-response note as unresolved')
                if package_name == 'F':
                    if detail['status'] not in ('sent', 'review'):
                        raise RuntimeError('fallback did not reopen the unresolved candidate note')
                    recovered = modules['item_notes'].recover_note(client, jobs, group, job_id, 'complete')
                    detail = jobs.detail(group, job_id)
                    if recovered.get('status') != 'completed' or detail['status'] != 'completed':
                        raise RuntimeError('fallback did not recover the uncertain native note')
                elif index == 3 and detail['status'] != 'completed':
                    raise RuntimeError('final candidate did not retain the fallback completed note')
            expected_counts = (0, 1, 1, 1)
            if (client.posts != expected_counts[index]
                    or len(client.entries) != expected_counts[index]
                    or (detail is not None and detail['status'] not in (('sent', 'review') if index == 1 else ('completed',)))):
                raise RuntimeError('uncertain note POST/entry count or journal status changed across transition')
            st = ledger_path.stat()
            rows.append({'package': package_name,
                         'bundle_manifest_sha256': hashlib.sha256((package / 'manifest.json').read_bytes()).hexdigest(),
                         'module_sha256': state['module_sha256'],
                         'module_origins': state['module_origins'],
                         'ledger_store_identity': [st.st_dev, st.st_ino],
                         'job_id': job_id, 'job_exists': detail is not None,
                         'job_status': detail['status'] if detail is not None else 'absent',
                         'native_entry_count': len(client.entries),
                         'native_post_count': client.posts,
                         'candidate_exposed_before_create': index >= 1,
                         'note_created_here': index == 1,
                         'journal_unresolved_after_transition': index == 1,
                         'recovery_performed_here': recover_here,
                         'recovery_from_status': recovery_from_status,
                         'result': 'passed'})
        finally:
            _unload_ops(names, state)
    rows[0]['job_id'] = job_id
    report = {'scope': 'fixture-only', 'trace': rows,
            'same_ledger_store': len({tuple(row['ledger_store_identity']) for row in rows}) == 1,
            'uncertain_item_note_exactly_once_recovery_preserved': True,
            'native_entry_count': len(client.entries), 'native_post_count': client.posts,
            'native_post_call_count': client.posts,
            'note_created_under': 'C', 'recovered_under': 'F',
            'final_candidate_state': rows[-1]['job_status'],
            'claim': 'real packaged item-note journal/recovery with fixture native maintenance API and dropped response'}
    return report


def _valid_sha256(value):
    return (isinstance(value, str) and len(value) == 64
            and all(char in '0123456789abcdef' for char in value.lower()))


def _valid_uuid(value):
    try:
        return isinstance(value, str) and UUID(value).int != 0
    except (TypeError, ValueError, AttributeError):
        return False


def _valid_store_identity(value):
    return (isinstance(value, (list, tuple)) and len(value) == 2
            and all(type(part) is int and part > 0 for part in value))


def _validate_module_bindings(trace, required, bundles=None):
    package_list = ([Path(bundles) / name for name in 'OCF']
                    if isinstance(bundles, (str, Path))
                    else list(bundles) if bundles is not None else None)
    if package_list is not None and len(package_list) != 3:
        raise ValueError('module source binding requires exact O/C/F package roots')
    for index, row in enumerate(trace):
        hashes, origins = row.get('module_sha256'), row.get('module_origins')
        if (not isinstance(hashes, dict) or not isinstance(origins, dict)
                or not hashes or set(hashes) != set(origins)
                or not required.issubset(hashes)):
            raise ValueError('workflow source/module hashes and origins are incomplete')
        package_name = ('O', 'C', 'F', 'C')[index]
        package = package_list[('O', 'C', 'F').index(package_name)] if package_list else None
        for name, origin in origins.items():
            if (not isinstance(name, str) or not name.isidentifier()
                    or not isinstance(origin, str) or origin.startswith('/')
                    or '..' in Path(origin).parts
                    or origin not in (f'ops/{name}.py', f'kiosk/{name}.py')
                    or not _valid_sha256(hashes[name])):
                raise ValueError('workflow source/module origin or SHA-256 is invalid')
            if package is not None:
                source = package / origin
                if (not source.is_file() or source.is_symlink()
                        or hashlib.sha256(source.read_bytes()).hexdigest() != hashes[name]):
                    raise ValueError('workflow source/module hash is not bound to the selected package')


def _validate_transition_trace(report, expected_manifest_hashes, *, bundles=None, required_modules=()):
    trace = report.get('trace') if isinstance(report, dict) else None
    if (not isinstance(report, dict) or report.get('scope') != 'fixture-only'
            or report.get('same_ledger_store') is not True
            or not isinstance(trace, list) or len(trace) != 4
            or any(not isinstance(row, dict) for row in trace)
            or [row.get('package') for row in trace] != ['O', 'C', 'F', 'C']
            or [row.get('bundle_manifest_sha256') for row in trace] != expected_manifest_hashes
            or any(not isinstance(value, str) or not _valid_sha256(value)
                   for value in expected_manifest_hashes)
            or len({tuple(row.get('ledger_store_identity', [])) for row in trace
                    if isinstance(row, dict)}) != 1):
        raise ValueError('workflow report must bind O/C/F/C to one Ledger store')
    if any(not isinstance(row, dict) or row.get('result') != 'passed'
           or not _valid_store_identity(row.get('ledger_store_identity'))
           for row in trace):
        raise ValueError('workflow rows must pass and bind a valid Ledger identity')
    _validate_module_bindings(trace, set(required_modules), bundles)
    return trace


def validate_label_workflow(report, expected_manifest_hashes, *, bundles=None):
    trace = _validate_transition_trace(report, expected_manifest_hashes, bundles=bundles,
        required_modules={'ledger', 'native_jobs', 'label_layouts', 'labels', 'label_render'})
    if (report.get('reviewed_raster_intent_recovery_preserved') is not True
            or type(report.get('physical_print_calls')) is not int
            or report.get('physical_print_calls') != 0):
        raise ValueError('reviewed label raster, intent, recovery or zero-output assertion failed')
    review = report.get('review_metadata')
    expected_metadata = {'review_id', 'template_id', 'template_revision', 'template_hash',
                         'sha256', 'profile', 'label_mm', 'dpi', 'width', 'height',
                         'item_id', 'item_updated_at'}
    if (not isinstance(review, dict) or set(review) != expected_metadata
            or not _valid_uuid(review.get('review_id')) or not _valid_uuid(review.get('item_id'))
            or review.get('template_id') != 'starter:supvan:left'
            or type(review.get('template_revision')) is not int or review.get('template_revision') != 0
            or not _valid_sha256(review.get('template_hash'))
            or not _valid_sha256(review.get('sha256'))
            or review.get('profile') != 'supvan' or review.get('label_mm') != [40, 28]
            or type(review.get('dpi')) not in (int, float) or review.get('dpi') != 203.2
            or type(review.get('width')) is not int or review.get('width') != 320
            or type(review.get('height')) is not int or review.get('height') != 224
            or not isinstance(review.get('item_updated_at'), str) or not review['item_updated_at']):
        raise ValueError('reviewed label metadata does not bind its raster hash')
    statuses = ['prepared', 'prepared', 'prepared', 'cancelled']
    ids = {key: [] for key in ('job_id', 'review_id', 'item_id')}
    for index, row in enumerate(trace):
        metadata = row.get('review_metadata')
        raster_sha = row.get('reviewed_raster_sha256')
        if (not isinstance(metadata, dict) or metadata != review
                or not _valid_sha256(raster_sha) or raster_sha != metadata.get('sha256')
                or row.get('review_metadata_sha256') != hashlib.sha256(json.dumps(
                    metadata, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                or row.get('review_read_from_persisted_store') is not True
                or row.get('job_status_before_action') != 'prepared'
                or row.get('job_status') != statuses[index]
                or row.get('cancel_recovered_here') is not (index == 3)
                or row.get('review_resolved_after_transition') is not (index == 3)
                or type(row.get('physical_print_calls')) is not int
                or row.get('physical_print_calls') != 0):
            raise ValueError('persisted reviewed raster, metadata or intent changed across O/C/F/C')
        ids['job_id'].append(row.get('job_id'))
        ids['review_id'].append(row.get('review_id'))
        ids['item_id'].append(row.get('item_id'))
    if any(not _valid_uuid(value) for values in ids.values() for value in values) or any(
            len(set(values)) != 1 or values[0] != review[key]
            for key, values in ids.items() if key in ('review_id', 'item_id')):
        raise ValueError('label job, review and item IDs must be stable valid UUIDs')
    if len(set(ids['job_id'])) != 1:
        raise ValueError('label job ID changed across package transitions')
    return True


def validate_note_workflow(report, expected_manifest_hashes, *, bundles=None):
    trace = _validate_transition_trace(report, expected_manifest_hashes, bundles=bundles,
        required_modules={'ledger', 'native_jobs', 'item_notes'})
    if (report.get('uncertain_item_note_exactly_once_recovery_preserved') is not True
            or report.get('note_created_under') != 'C' or report.get('recovered_under') != 'F'
            or report.get('final_candidate_state') != 'completed'
            or type(report.get('native_entry_count')) is not int or report.get('native_entry_count') != 1
            or type(report.get('native_post_count')) is not int or report.get('native_post_count') != 1
            or type(report.get('native_post_call_count')) is not int or report.get('native_post_call_count') != 1
            or report.get('native_api_boundary') != 'authenticated owned disposable native Homebox listener with PID checks'
            or report.get('response_loss_injected_after_native_commit') is not True
            or not isinstance(report.get('native_endpoint'), str)
            or not report['native_endpoint'].startswith('http://127.0.0.1:')
            or not report['native_endpoint'].endswith('/api/v1/entities/*/maintenance')):
        raise ValueError('uncertain item note did not recover exactly once across O/C/F/C')
    statuses = ['absent', None, 'completed', 'completed']
    ids = [row.get('job_id') for row in trace]
    if not all(_valid_uuid(value) for value in ids) or len(set(ids)) != 1:
        raise ValueError('uncertain note job ID must be one stable valid UUID')
    for index, row in enumerate(trace):
        expected_count = (0, 1, 1, 1)[index]
        status_ok = (row.get('job_status') in ('sent', 'review') if index == 1
                     else row.get('job_status') == statuses[index])
        if (not status_ok
                or row.get('job_exists') is not (index != 0)
                or type(row.get('native_entry_count')) is not int
                or row.get('native_entry_count') != expected_count
                or type(row.get('native_post_count')) is not int
                or row.get('native_post_count') != expected_count
                or type(row.get('native_post_call_count')) is not int
                or row.get('native_post_call_count') != expected_count
                or row.get('candidate_exposed_before_create') is not (index >= 1)
                or row.get('note_created_here') is not (index == 1)
                or row.get('journal_unresolved_after_transition') is not (index == 1)
                or row.get('recovery_performed_here') is not (index == 2)
                or (index == 1 and row.get('job_status') != 'review')
                or (index == 2 and row.get('recovery_from_status') not in ('sent', 'review'))
                or (index != 2 and row.get('recovery_from_status') is not None)):
            raise ValueError('uncertain note stage, exact counters or recovery transition changed')
    return True


def validate_publisher_checks(packages, scratch_root, *, profile_loan_preserved):
    packages = tuple(Path(path).resolve(strict=True) for path in packages)
    if len(packages) != 3:
        raise ValueError('Publisher fixture requires exact O/C/F packages')
    scratch = Path(scratch_root)
    scratch.mkdir(mode=0o700, parents=True, exist_ok=True)
    legacy = scratch / 'fixture-legacy-without-member-api'
    def remove_fixture_package(path):
        if not path.exists():
            return
        for current, directories, files in __import__('os').walk(path):
            current_path = Path(current)
            current_path.chmod(0o700)
            for name in files:
                try:
                    (current_path / name).chmod(0o600)
                except OSError:
                    pass
            for name in directories:
                try:
                    (current_path / name).chmod(0o700)
                except OSError:
                    pass
        shutil.rmtree(path)
    if legacy.exists():
        remove_fixture_package(legacy)
    shutil.copytree(packages[0], legacy)
    (legacy / 'ops').chmod(0o700)
    (legacy / 'ops/desktop_api.py').chmod(0o600)
    (legacy / 'ops/desktop_api.py').unlink()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'deploy'))
    try:
        import release_bundle
        try:
            release_bundle.validate_bundle(legacy)
        except release_bundle.BundleError:
            legacy_rejected = True
        else:
            legacy_rejected = False
        if not legacy_rejected:
            raise ValueError('legacy bundle missing member API was accepted as a release')
        namespace = __import__('runpy').run_path(
            str(Path(__file__).resolve().parents[1] / 'deploy/publish-users.py'),
            run_name='publisher_pure_fixture_validation')
        manifests = [release_bundle.validate_bundle(path) for path in packages]
        for manifest, path in zip(manifests, packages):
            manifest['manifest_sha256'] = hashlib.sha256((path / 'manifest.json').read_bytes()).hexdigest()
            manifest['bundle_path'] = str(path)
        required = namespace['REQUIRED_CHECKS']
        checks = {name: True for name in required}
        checks['matched_previous_release_preserves_new_fixture_profiles_and_loans'] = bool(profile_loan_preserved)
        checks['legacy_missing_member_api_is_not_a_rollback_target'] = legacy_rejected
        receipt = {'execution_scope': 'fixture-only',
                   **{f'{label}_bundle_manifest_sha256': manifests[index]['manifest_sha256']
                      for index, label in enumerate(('previous', 'candidate', 'fallback'))},
                   **{f'{label}_native_sha256': manifests[index]['provenance']['native_sha256']
                      for index, label in enumerate(('previous', 'candidate', 'fallback'))},
                   'fallback_policy_sha256': hashlib.sha256(json.dumps(
                       manifests[2]['fallback_policy'], sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                   'checks': checks}
        namespace['validate_matched_receipt'](receipt, *manifests, allow_fixture=True)
        return {'checks': {name: checks[name] for name in sorted(required)},
                'receipt_validation': 'passed', 'legacy_bundle_rejected': True,
                'scope': 'fixture-only'}
    finally:
        sys.path.remove(str(Path(__file__).resolve().parents[1] / 'deploy'))
        if legacy.exists():
            remove_fixture_package(legacy)
