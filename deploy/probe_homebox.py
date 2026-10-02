import hashlib, json, os, pathlib, secrets, signal, subprocess, time, urllib.request, urllib.error

root = pathlib.Path('/home/user/Desktop/inventory-system')
work = root / 'work'
archive = work / 'homebox_Linux_arm64.tar.gz'
expected = 'a7197a54b830a21be0142c5b4b3dd3a730d5d6a0599aa680d089b4e128d82f12'
assert hashlib.sha256(archive.read_bytes()).hexdigest() == expected, 'Release checksum mismatch'
binary = work / 'homebox-bin/homebox'
run = work / 'baseline'
run.mkdir(exist_ok=True, mode=0o700)
os.chmod(run, 0o700)
pepper = run / 'pepper'
if not pepper.exists():
    pepper.write_text(secrets.token_urlsafe(48))
    os.chmod(pepper, 0o600)
env = dict(os.environ, HBOX_WEB_HOST='127.0.0.1', HBOX_WEB_PORT='17745',
           HBOX_STORAGE_PREFIX_PATH=str(run / 'data'),
           HBOX_DATABASE_SQLITE_PATH=str(run / 'data/homebox.db')+'?_pragma=busy_timeout=999&_pragma=journal_mode=WAL&_fk=1&_time_format=sqlite',
           HBOX_AUTH_API_KEY_PEPPER=pepper.read_text(), HBOX_OPTIONS_GITHUB_RELEASE_CHECK='false',
           HBOX_OPTIONS_ALLOW_ANALYTICS='false', HBOX_LOG_LEVEL='info')
base = 'http://127.0.0.1:17745'
results = []
def request(method, path, payload=None, token=None, record=True, content_type='application/json'):
    headers = {'Content-Type': content_type}
    if token: headers['Authorization'] = 'Bearer '+token
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base+path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            raw = response.read(); code = response.status
    except urllib.error.HTTPError as e:
        code, raw = e.code, e.read()
    if record:
        results.append({'method':method, 'path':path, 'status':code})
        print(method, path, code, flush=True)
    try: data = json.loads(raw)
    except (ValueError, UnicodeDecodeError): data = raw
    return code, data

if os.environ.get('PHASE0_RESTART') == '1' and (run/'homebox.pid').exists():
    pid = int((run/'homebox.pid').read_text())
    exe = pathlib.Path('/proc')/str(pid)/'exe'
    if exe.exists() and exe.resolve() == binary.resolve():
        os.kill(pid, signal.SIGTERM)
        for _ in range(50):
            if not exe.exists(): break
            time.sleep(0.1)
        assert not exe.exists(), 'Old baseline process failed to stop'

try:
    request('GET', '/api/v1/status', record=False)
except Exception:
    log = open(run / 'homebox.log', 'ab')
    proc = subprocess.Popen([str(binary)], cwd=run, env=env, stdin=subprocess.DEVNULL,
                            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    (run / 'homebox.pid').write_text(str(proc.pid))
    for _ in range(30):
        try:
            request('GET', '/api/v1/status', record=False); break
        except Exception: time.sleep(0.5)
    else: raise RuntimeError('Homebox startup failed; inspect '+str(run / 'homebox.log'))

code, status = request('GET', '/api/v1/status')
print('BUILD', json.dumps(status), flush=True)
assert code == 200
assert request('GET', '/')[0] == 200
credentials = run / 'test-account.json'
if credentials.exists(): account = json.loads(credentials.read_text())
else:
    account = {'email':'recon@example.invalid', 'name':'Recon test user', 'password':secrets.token_urlsafe(24)}
    credentials.write_text(json.dumps(account)); os.chmod(credentials, 0o600)
    assert request('POST', '/api/v1/users/register', account)[0] == 204
code, login = request('POST', '/api/v1/users/login', {'username':account['email'], 'password':account['password']})
assert code == 200
token = login['token'].removeprefix('Bearer ')
assert request('GET', '/api/v1/entities')[0] == 401
code, key = request('POST', '/api/v1/users/self/api-keys', {'name':'phase0-probe'}, token)
assert code == 201
api_token = key['token']
code, types = request('GET', '/api/v1/entity-types', token=api_token)
assert code == 200
location_type = next(t['id'] for t in types if t['isLocation'])
code, shelf = request('POST', '/api/v1/entities', {'name':'Recon shelf', 'entityTypeId':location_type}, api_token)
assert code == 201
code, asset = request('POST', '/api/v1/entities', {'name':'Recon battery', 'quantity':1, 'parentId':shelf['id']}, api_token)
assert code == 201
aid = asset['id']
for path in ['/api/v1/entities?isLocation=true', '/api/v1/entities?parentIds='+shelf['id'],
             '/api/v1/entities/'+aid, '/api/v1/entities/'+aid+'/path', '/api/v1/entities/tree?withItems=true',
             '/api/v1/templates', '/api/v1/entities/'+aid+'/maintenance', '/swagger/doc.json',
             '/api/v1/qrcode?data=phase0-test', '/api/v1/entities/export', '/api/v1/group/exports']:
    request('GET', path, token=api_token)
assert request('PATCH', '/api/v1/entities/'+aid, {'quantity':2}, api_token)[0] == 200
request('POST', '/api/v1/entities/'+aid+'/maintenance', {'name':'Recon inspection'}, api_token)
assert request('POST', '/api/v1/entities/'+aid+'/maintenance',
               {'name':'Recon inspection', 'completedDate':'2026-10-02T12:00:00-04:00','cost':'0'}, api_token)[0] == 201
code, detail = request('GET', '/api/v1/entities/'+aid, token=api_token)
update = {'name':detail['name'], 'description':detail['description'], 'quantity':detail['quantity'],
          'parentId':shelf['id'], 'entityTypeId':detail['entityType']['id'], 'assetId':detail['assetId'],
          'tagIds':[t['id'] for t in detail.get('tags',[])], 'manufacturer':'Recon manufacturer',
          'serialNumber':'RECON-001', 'modelNumber':'Test model',
          'fields':[{'name':'Recon field','type':'text','textValue':'preserved'}]}
assert request('PUT','/api/v1/entities/'+aid,update,api_token)[0] == 200
code, detail = request('GET','/api/v1/entities/'+aid,token=api_token)
assert detail['serialNumber'] == 'RECON-001' and detail['fields'][0]['textValue'] == 'preserved'
request('GET', '/api/v1/labelmaker/entity/'+aid, token=api_token)
request('GET', '/api/v1/entities/fields', token=api_token)
request('GET', '/api/v1/assets/'+asset['assetId'], token=api_token)
assert request('DELETE', '/api/v1/users/self/api-keys/'+key['id'], token=token)[0] == 204
assert request('GET', '/api/v1/entities', token=api_token)[0] == 401
(root/'docs/api-probe-results.json').write_text(json.dumps({'build':status, 'results':results}, indent=2))
pid = int((run/'homebox.pid').read_text())
subprocess.run(['ps','-p',str(pid),'-o','pid,rss,pcpu,etime,comm'])
print('BASELINE_READY loopback port 17745; test credentials kept private on Pi', flush=True)
