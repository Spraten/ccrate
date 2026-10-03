#!/usr/bin/env python3
"""Seed only the isolated synthetic baseline and prove a cold-copy restore."""
import hashlib, json, os, pathlib, shutil, signal, subprocess, time, urllib.request

ROOT = pathlib.Path('/home/user/Desktop/inventory-system')
RUN = ROOT / 'work/baseline'
BINARY = ROOT / 'work/homebox-bin/homebox'
BASE = 'http://127.0.0.1:17745'
ACCOUNT = json.loads((RUN / 'test-account.json').read_text())

def request(base, method, path, payload=None, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token.removeprefix('Bearer ')
    req = urllib.request.Request(base + path, method=method, headers=headers,
        data=json.dumps(payload).encode() if payload is not None else None)
    with urllib.request.urlopen(req, timeout=15) as response:
        raw = response.read()
    return json.loads(raw) if raw else None

def login(base):
    return request(base, 'POST', '/api/v1/users/login',
        {'username': ACCOUNT['email'], 'password': ACCOUNT['password']})['token']

def entities(base, token, locations):
    page, result = 1, []
    while True:
        response = request(base, 'GET', f'/api/v1/entities?page={page}&pageSize=100&isLocation={str(locations).lower()}', token=token)
        result.extend(response['items'])
        if len(result) >= response['total'] or not response['items']:
            return result
        page += 1

def launch(folder, port):
    data = folder / 'data'
    env = dict(os.environ, HBOX_WEB_HOST='127.0.0.1', HBOX_WEB_PORT=str(port),
        HBOX_STORAGE_PREFIX_PATH=str(data),
        HBOX_DATABASE_SQLITE_PATH=str(data/'homebox.db')+'?_pragma=busy_timeout=999&_pragma=journal_mode=WAL&_fk=1&_time_format=sqlite',
        HBOX_AUTH_API_KEY_PEPPER=(RUN/'pepper').read_text(),
        HBOX_OPTIONS_GITHUB_RELEASE_CHECK='false', HBOX_OPTIONS_ALLOW_ANALYTICS='false')
    with (folder/'homebox.log').open('ab') as log:
        proc = subprocess.Popen([str(BINARY)], cwd=folder, env=env, stdout=log,
            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    for _ in range(40):
        if proc.poll() is not None:
            raise RuntimeError('Homebox exited; inspect private runtime log')
        try:
            request(f'http://127.0.0.1:{port}', 'GET', '/api/v1/status')
            return proc
        except Exception:
            time.sleep(.25)
    proc.terminate()
    raise RuntimeError('Homebox readiness timed out')

def stop_baseline():
    pid = int((RUN/'homebox.pid').read_text())
    exe = pathlib.Path(f'/proc/{pid}/exe')
    assert exe.resolve() == BINARY.resolve(), 'Refuse to stop unrelated process'
    os.kill(pid, signal.SIGTERM)
    for _ in range(100):
        if not exe.exists():
            return
        time.sleep(.1)
    raise RuntimeError('Baseline did not stop; refuse to copy live storage')

token = login(BASE)
types = request(BASE, 'GET', '/api/v1/entity-types', token=token)
location_type = next(t['id'] for t in types if t['isLocation'])
all_entities = entities(BASE, token, True) + entities(BASE, token, False)
known = {(e['name'], (e.get('parent') or {}).get('id')): e for e in all_entities}
created = []

def ensure(name, parent=None, location=False):
    key = (name, parent)
    if key in known:
        return known[key]['id']
    payload = {'name': name, 'description': 'Synthetic kiosk demonstration data; not real equipment.'}
    if parent:
        payload['parentId'] = parent
    if location:
        payload['entityTypeId'] = location_type
    else:
        payload['quantity'] = 1
    entity = request(BASE, 'POST', '/api/v1/entities', payload, token)
    known[key] = entity
    created.append(name)
    return entity['id']

workshop = ensure('Demo Workshop', location=True)
cage = ensure('Demo Drone Cage', workshop, True)
places = {}
for name in ['Shelf A1', 'Shelf A2', 'Shelf B1', 'Shelf B2']:
    places[name] = ensure('Demo ' + name, cage, True)
for name in ['Charging Station', 'Maintenance', 'Quarantine']:
    places[name] = ensure('Demo ' + name, workshop, True)
for name, place in [('Demo Drone 001', 'Shelf A1'), ('Demo Controller 001', 'Shelf A2'),
    ('Demo Battery 001', 'Charging Station'), ('Demo Battery 002', 'Shelf B1'),
    ('Demo Radio 001', 'Shelf B2'), ('Demo Repair Tool 001', 'Maintenance')]:
    ensure(name, places[place])
expected = {e['id'] for e in entities(BASE, token, True) + entities(BASE, token, False)}

stamp = time.strftime('%Y%m%d-%H%M%S')
backup = ROOT/'work/backups'/stamp
backup.mkdir(parents=True, mode=0o700)
os.chmod(backup, 0o700)
stopped = False
try:
    stop_baseline()
    stopped = True
    shutil.copytree(RUN/'data', backup/'data')
    shutil.copy2(RUN/'pepper', backup/'pepper')
    os.chmod(backup/'pepper', 0o600)
finally:
    if stopped:
        proc = launch(RUN, 17745)
        (RUN/'homebox.pid').write_text(str(proc.pid))

manifest = {str(p.relative_to(backup)): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in (backup/'data').rglob('*') if p.is_file()}
(backup/'manifest.json').write_text(json.dumps(manifest, indent=2))
restore = ROOT/'work/restore-check'/stamp
restore.mkdir(parents=True, mode=0o700)
shutil.copytree(backup/'data', restore/'data')
restored = launch(restore, 17748)
try:
    base = 'http://127.0.0.1:17748'
    restored_token = login(base)
    actual = {e['id'] for e in entities(base, restored_token, True) + entities(base, restored_token, False)}
    assert expected == actual, 'Restore entity set differs'
finally:
    restored.terminate()
    restored.wait(timeout=15)
assert login(BASE)
report = {'created': created, 'entity_count': len(expected), 'restore_entity_match': True,
    'baseline_restarted': True, 'backup_folder': str(backup), 'restore_port': 17748,
    'backup_method': 'Graceful stop, full storage copy plus API-key pepper, restart, isolated restore API comparison',
    'limitations': ['Synthetic data only; attachment and API-key persistence recovery not yet exercised',
        'Local backup is not protection against SD-card failure']}
(ROOT/'docs/baseline-completion-results.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
