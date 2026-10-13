"""Prepare a source-pinned, privately built C-Crate release candidate."""
import hashlib
import importlib.util
import json
import fcntl
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
MIN_FREE_BYTES = 3 * 1024 ** 3
SERVICE_FILES = (
    'homebox-native.service', 'homebox-companion.service',
    'homebox-workshop-gateway.service',
)
STATUS_NAME = 'manager-update-status.json'


def _write_status(root, *, stage, started_at, outcome='running', commit=None, log_path=None, error=None,
                  details=None):
    path = Path(root) / 'work' / STATUS_NAME
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    record = {'schema': 1, 'stage': stage, 'started_at': started_at,
              'updated_at': __import__('time').time(), 'pid': os.getpid(),
              'outcome': outcome, 'commit': commit, 'log_path': str(log_path) if log_path else None, 'error': error}
    if details:
        record.update(details)
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex)
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(record, stream, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return record


def _run(args, *, cwd=None, stdout=subprocess.PIPE):
    return subprocess.run(args, cwd=cwd, check=True, stdout=stdout,
                          stderr=subprocess.STDOUT if stdout is not subprocess.PIPE else subprocess.PIPE)


def _git(repo, *args, text=True):
    result = _run(['git', '-C', str(repo), *args])
    return result.stdout.decode() if not text else result.stdout.decode().strip()


def _extract_archive(repo, commit, destination):
    raw = _run(['git', '-C', str(repo), 'archive', '--format=tar', commit]).stdout
    destination.mkdir(parents=True)
    with tarfile.open(fileobj=__import__('io').BytesIO(raw), mode='r:') as archive:
        for member in archive:
            rel = PurePosixPath(member.name)
            if rel.is_absolute() or '..' in rel.parts or member.issym() or member.islnk() or not (member.isdir() or member.isfile()):
                raise RuntimeError(f'Unsafe source archive member: {member.name}')
            target = destination.joinpath(*rel.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise RuntimeError(f'Unreadable source archive member: {member.name}')
            with source, target.open('xb') as output:
                shutil.copyfileobj(source, output)
            target.chmod(member.mode & 0o755)


def stage_source_commit(project_repo, submodule_repo, commit, destination):
    """Archive one immutable project commit and its exact upstream gitlink."""
    commit = _git(project_repo, 'rev-parse', f'{commit}^{{commit}}')
    listing = _git(project_repo, 'ls-tree', commit, 'upstream/homebox')
    fields = listing.split()
    if len(fields) < 3 or fields[0] != '160000' or fields[1] != 'commit':
        raise RuntimeError('The pinned project commit has no upstream/homebox gitlink')
    submodule_commit = fields[2]
    try:
        _git(submodule_repo, 'cat-file', '-e', f'{submodule_commit}^{{commit}}')
    except subprocess.CalledProcessError:
        _run(['git', '-C', str(submodule_repo), 'fetch', 'origin', submodule_commit])
        _git(submodule_repo, 'cat-file', '-e', f'{submodule_commit}^{{commit}}')
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _extract_archive(project_repo, commit, destination)
    upstream = destination / 'upstream/homebox'
    if upstream.exists():
        if not upstream.is_dir() or any(upstream.iterdir()):
            raise RuntimeError('Project archive unexpectedly contains upstream submodule files')
        upstream.rmdir()
    _run(['git', 'clone', '--no-hardlinks', '--no-checkout', str(submodule_repo), str(upstream)])
    _run(['git', '-C', str(upstream), 'checkout', '--detach', submodule_commit])
    return submodule_commit


def write_source_identity(public, project_commit, submodule_commit):
    if not all(isinstance(value, str) and len(value) in (40, 64)
               and all(c in '0123456789abcdef' for c in value)
               for value in (project_commit, submodule_commit)):
        raise ValueError('Source commits must be full Git object IDs')
    path = Path(public) / 'ccrate-release.json'
    path.write_text(json.dumps({'schema': 1, 'source_commit': project_commit,
                                'homebox_commit': submodule_commit}, indent=2) + '\n')
    return path


def _hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _preflight_space(root):
    free = shutil.disk_usage(root).free
    if free < MIN_FREE_BYTES:
        raise RuntimeError(f'At least {MIN_FREE_BYTES // (1024 ** 3)} GiB must be free for a private source build; found {free // (1024 ** 3)} GiB')


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def _inventory(root):
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError(f'Missing or linked build artifact directory: {root}')
    rows = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise RuntimeError(f'Linked build artifact refused: {path}')
        if path.is_file():
            rows[path.relative_to(root).as_posix()] = {'sha256': _hash(path), 'size': path.stat().st_size}
    if not rows:
        raise RuntimeError(f'Empty build artifact directory: {root}')
    return rows


def _link_private_dependencies(root, candidate):
    links = (
        (root / 'work/toolchains', candidate / 'work/toolchains'),
        (root / 'program-files/runtime/hardware/python',
         candidate / 'program-files/runtime/hardware/python'),
    )
    for source, target in links:
        if not source.is_dir():
            raise RuntimeError(f'Required installed build dependency is missing: {source}')
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            if target.is_symlink() and target.resolve(strict=True) == source.resolve(strict=True):
                continue
            raise RuntimeError(f'Candidate dependency path already exists: {target}')
        target.symlink_to(source.resolve(), target_is_directory=True)


def _preserve_installed_units(root, candidate):
    from deploy.release_bundle import validate_bundle
    selector = Path(root) / 'work/application-current'
    if not selector.is_symlink():
        raise RuntimeError('Installed application selector is missing or is not a symlink')
    release = selector.resolve(strict=True)
    allowed = (Path(root) / 'work/application-releases').resolve(strict=True)
    release.relative_to(allowed)
    manifest = validate_bundle(release)
    if manifest.get('format') != 2:
        raise RuntimeError('Installed release is not a valid launcher-capable format-2 bundle')
    origin = {'previous_manifest_sha256': _hash(release / 'manifest.json'), 'service_units': {}}
    for name in SERVICE_FILES:
        source = release / 'deploy' / name
        info = source.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise RuntimeError(f'Installed service definition is not a regular file: {name}')
        target = candidate / 'deploy' / name
        if target.exists() and not target.is_symlink():
            staged = target.lstat()
            if not stat.S_ISREG(staged.st_mode) or staged.st_uid != os.getuid() or staged.st_nlink != 1:
                raise RuntimeError(f'Existing staged service target is unsafe: {name}')
            target.chmod(staged.st_mode | stat.S_IWUSR)
        shutil.copyfile(source, target)
        target.chmod(info.st_mode & 0o777)
        origin['service_units'][name] = _hash(source)
    return origin


def _overlay_maintained_helpers(root, candidate):
    rows = {}
    for name in ('release_bundle.py', 'run-release.py'):
        source = Path(root) / 'deploy' / name
        target = candidate / 'deploy' / name
        if source.is_symlink() or not source.is_file():
            raise RuntimeError(f'Maintained release helper is missing or linked: {source}')
        if target.exists() and not target.is_symlink():
            staged = target.lstat()
            if not stat.S_ISREG(staged.st_mode) or staged.st_uid != os.getuid() or staged.st_nlink != 1:
                raise RuntimeError(f'Existing staged helper target is unsafe: {name}')
            target.chmod(staged.st_mode | stat.S_IWUSR)
        shutil.copyfile(source, target)
        target.chmod(source.stat().st_mode & 0o777)
        rows[f'deploy/{name}'] = _hash(target)
    return rows


def _log_run(candidate, name, args, *, cwd, env=None):
    logs = candidate / 'work/manager-logs'
    logs.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = logs / f'{name}.log'
    with path.open('wb') as stream:
        subprocess.run(args, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT, check=True)
    return path


def _build_environment(candidate, *, node_bin=None, test_paths=(), loopback=False):
    home = candidate / 'work/build-home'
    temp = candidate / 'work/build-tmp'
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp.mkdir(mode=0o700, parents=True, exist_ok=True)
    env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': str(home),
           'TMPDIR': str(temp), 'LANG': os.environ.get('LANG', 'C.UTF-8'),
           'LC_ALL': os.environ.get('LC_ALL', 'C.UTF-8'), 'GOOS': 'linux',
           'GOARCH': 'arm64', 'CGO_ENABLED': '1'}
    if node_bin:
        env['PATH'] = str(node_bin) + os.pathsep + env['PATH']
    if test_paths:
        env['PYTHONPATH'] = os.pathsep.join(map(str, test_paths))
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        env['CCRATE_UPSTREAM_ROOT'] = str(candidate / 'upstream/homebox')
    if not loopback:
        # Keep only network proxy configuration for dependency downloads.
        for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
                    'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy'):
            if key in os.environ:
                env[key] = os.environ[key]
    return env


def _prepare_ui_dependencies(candidate):
    builder_path = candidate / 'deploy/build-homebox-ui.py'
    spec = importlib.util.spec_from_file_location('ccrate_candidate_ui_builder', builder_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = candidate
    module.BUILD = candidate / 'work/homebox-ui-build'
    module.TOOLCHAIN_ROOT = candidate / 'work/toolchains'
    module.UPSTREAM_ROOT = candidate
    module.prepare()
    toolchain = candidate / 'work/toolchains'
    node_root = Path((toolchain / 'node-path.txt').read_text().strip())
    node = node_root / 'bin/node'
    pnpm = toolchain / 'pnpm/node_modules/.bin/pnpm'
    if not node.is_file() or not pnpm.is_file():
        raise RuntimeError('Installed Node or pnpm toolchain is incomplete')
    env = _build_environment(candidate, node_bin=node.parent)
    _log_run(candidate, 'ui-dependencies', [str(pnpm), 'install', '--frozen-lockfile', '--ignore-scripts'],
             cwd=module.BUILD, env=env)
    return node, pnpm, env


def _run_workshop_fixture(candidate, evidence_root=None, *, extended=False):
    """Execute candidate Workshop code against a disposable SQLite database."""
    candidate = Path(candidate)
    evidence_root = candidate if evidence_root is None else Path(evidence_root)
    script_root = evidence_root / 'work'
    script_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    script = script_root / 'manager-workshop-fixture.py'
    script.write_text('''import json, pathlib, sqlite3, sys, tempfile
ops = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ops))
from ledger import Conflict
from workshop import Workshop
if pathlib.Path(sys.modules['workshop'].__file__).resolve() != ops / 'workshop.py':
    raise RuntimeError('Workshop module did not load from candidate source')
group = '11111111-1111-4111-8111-111111111111'
actor = '22222222-2222-4222-8222-222222222222'
def require(value, message):
    if not value: raise RuntimeError(message)
with tempfile.TemporaryDirectory(prefix='workshop-proof-', dir=pathlib.Path(sys.argv[2]).resolve()) as temp:
    path = pathlib.Path(temp) / 'workshop.db'
    store = Workshop(path)
    legacy = {'name':'Legacy room','width':20,'height':16,'unit':'ft','approximate':True,'objects':[]}
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO plans VALUES(?,?,?)',(group,4,json.dumps(legacy)))
    with sqlite3.connect(path) as db:
        before = db.execute('SELECT document FROM plans WHERE group_id=?',(group,)).fetchone()[0]
    old = store.get(group)
    with sqlite3.connect(path) as db:
        after = db.execute('SELECT document FROM plans WHERE group_id=?',(group,)).fetchone()[0]
    require(old['stored_schema_version']==1 and old['layout']==legacy and before==after,'Legacy v1 read rewrote stored data')
    class NoNativeWrites:
        writes = 0
        def entities(self,*args): raise RuntimeError('Fixture attempted a native entity read')
        def entity(self,*args): raise RuntimeError('Fixture attempted a native entity read')
        def __getattr__(self,name):
            if name.startswith(('create','update','delete','write','post','put')):
                def refuse(*args,**kwargs):
                    self.writes += 1
                    raise RuntimeError('Fixture attempted a native write')
                return refuse
            raise AttributeError(name)
    client = NoNativeWrites()
    body = {'schema_version':2,'revision':4,'document':{'version':2,'rooms':[]},'request_key':'33333333-3333-4333-8333-333333333333'}
    saved = store.save(client,group,body,actor_id=actor)
    require(saved['revision']==5 and store.get(group)['stored_schema_version']==2,'Version-2 read/write failed')
    stale = dict(body,request_key='44444444-4444-4444-8444-444444444444')
    try: store.save(client,group,stale,actor_id=actor)
    except Conflict: pass
    else: raise RuntimeError('Stale Workshop save was accepted')
    require(client.writes==0,'Fixture attempted a native write')
rows=[{'name':'workshop_read_v1','result':'passed'},
      {'name':'workshop_read_v2','result':'passed'},
      {'name':'workshop_write_v2','result':'passed'}]
if sys.argv[3]=='extended':
    rows.extend([{'name':'stale_write_conflict','result':'passed'},
                 {'name':'native_write_count_zero','result':'passed'}])
print(json.dumps(rows))
''')
    temp_root = script_root / 'fixture-tmp'
    temp_root.mkdir(mode=0o700, exist_ok=True)
    os.chmod(temp_root, 0o700)
    env = _build_environment(evidence_root, loopback=True)
    result = subprocess.run([sys.executable, '-I', '-B', str(script),
                             str(candidate / 'ops'), str(temp_root), 'extended' if extended else 'standard'],
                            cwd=evidence_root, env=env, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f'Candidate Workshop fixture failed: {result.stderr.strip() or result.stdout.strip()}')
    rows = json.loads(result.stdout)
    expected = ['workshop_read_v1', 'workshop_read_v2', 'workshop_write_v2']
    if extended:
        expected.extend(['stale_write_conflict', 'native_write_count_zero'])
    if [row.get('name') for row in rows] != expected:
        raise RuntimeError('Candidate Workshop fixture did not return required named results')
    return rows


def _build_and_stage(root, candidate, commit, submodule_commit, *, reuse_existing=False,
                     already_staged=False):
    (candidate / 'work/manager-logs').mkdir(mode=0o700, parents=True, exist_ok=True)
    installed_origin = _preserve_installed_units(root, candidate)
    maintained_overlays = _overlay_maintained_helpers(root, candidate)
    spec = importlib.util.spec_from_file_location(
        'ccrate_candidate_release_bundle', candidate / 'deploy/release_bundle.py')
    release_bundle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(release_bundle)

    _link_private_dependencies(root, candidate)
    if reuse_existing:
        env = _build_environment(candidate)
        if not already_staged:
            outputs = (
                (Path(root) / 'work/homebox-ui-build/.output/public', candidate / 'work/homebox-ui-build/.output/public'),
                (Path(root) / 'work/label-ui-build', candidate / 'work/label-ui-build'),
                (Path(root) / 'work/homebox-backend-build', candidate / 'work/homebox-backend-build'),
            )
            for source, target in outputs:
                _inventory(source)
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                shutil.copytree(source, target, ignore=shutil.ignore_patterns('node_modules', '.git', '__pycache__'))
        print('Validating existing private build outputs…', flush=True)
        node = pnpm = None
    else:
        print('Building C-Crate UI…', flush=True)
        node, pnpm, env = _prepare_ui_dependencies(candidate)
        _log_run(candidate, 'ui-build', [sys.executable, 'deploy/build-homebox-ui.py',
                  '--toolchain-root', str(candidate / 'work/toolchains'), '--upstream-root', str(candidate)],
                 cwd=candidate, env=env)
    public = candidate / 'work/homebox-ui-build/.output/public'
    if not (public / 'index.html').is_file():
        raise RuntimeError('UI build did not produce index.html')
    write_source_identity(public, commit, submodule_commit)
    (candidate / 'work/homebox-ui-current').parent.mkdir(parents=True, exist_ok=True)
    if not (candidate / 'work/homebox-ui-current').exists():
        shutil.copytree(public, candidate / 'work/homebox-ui-current')

    if not reuse_existing:
        print('Building label editor…', flush=True)
        _log_run(candidate, 'label-build', [sys.executable, 'deploy/build-label-ui.py',
                  '--source-root', str(candidate), '--output', 'work/label-ui-build',
                  '--toolchain-root', str(candidate / 'work/toolchains')], cwd=candidate, env=env)

        print('Building native Homebox backend…', flush=True)
        _log_run(candidate, 'backend-build', [sys.executable, 'deploy/build-homebox-backend.py'],
                 cwd=candidate, env=env)

    results = None if reuse_existing else {'backend_exit': 0, 'ui_exit': 0, 'label_exit': 0}
    build_rows = json.loads((candidate / 'work/homebox-backend-build/build-receipt.json').read_text())
    label_rows = json.loads((candidate / 'work/label-ui-build/manifest.json').read_text())
    binary = candidate / 'work/homebox-backend-build/homebox'
    if not binary.is_file() or not os.access(binary, os.X_OK) or build_rows.get('binary_sha256') != _hash(binary):
        raise RuntimeError('Native build receipt does not match its executable output')
    if build_rows.get('upstream') != submodule_commit:
        raise RuntimeError('Existing backend receipt does not match the pinned upstream gitlink')

    def snapshot():
        source_files = release_bundle._runtime_files(
            candidate, deploy_files=release_bundle.LAUNCHER_DEPLOY_FILES)
        runtime_files = {dest.as_posix(): _hash(path) for path, dest in source_files}
        runtime_modes = {dest.as_posix(): path.stat().st_mode & 0o777 for path, dest in source_files}
        public_files = _inventory(public)
        label_files = _inventory(candidate / 'work/label-ui-build')
        starter_hash = _hash(candidate / 'label-ui/src/starter-documents.json')
        native_hash = _hash(binary)
        return (source_files, runtime_files, runtime_modes, public_files,
                label_files, starter_hash, native_hash)

    before_tests = snapshot()
    source_files, runtime_files, runtime_modes, public_files, label_files, starter_hash, native_hash = before_tests
    closure = release_bundle._workshop_closure_digest(
        runtime_files, runtime_modes, public_files, label_files, starter_hash, native_hash)

    print('Running the disposable Workshop compatibility fixture…', flush=True)
    tests = []
    compatibility = _run_workshop_fixture(candidate)
    if snapshot()[1:] != before_tests[1:]:
        raise RuntimeError('Candidate source or build artifacts changed during compatibility testing')
    total_tests = sum(row['tests'] for row in tests) + len(compatibility)

    static_manifest = {'public': public_files, 'labels': label_files}
    static_sha = hashlib.sha256(_canonical(static_manifest)).hexdigest()
    source_manifest = {'project_commit': commit, 'homebox_commit': submodule_commit,
                       'installation_overlays': {'previous': installed_origin,
                                                 'maintained_helpers': maintained_overlays},
                       'runtime_files': runtime_files, 'runtime_modes': runtime_modes,
                       'public_files': public_files, 'label_files': label_files,
                       'label_starter_sha256': starter_hash}
    source_digest = hashlib.sha256(_canonical(source_manifest)).hexdigest()
    build = {'source_manifest_digest': source_digest, 'static_manifest_sha256': static_sha,
             'execution_scope': ('manager-validated-existing-builds' if reuse_existing else 'manager-private-source-build'),
             'build_results': (None if reuse_existing else results),
             'commands': {'ui': ['deploy/build-homebox-ui.py', '--toolchain-root',
                                 str(candidate / 'work/toolchains'), '--upstream-root', str(candidate)],
                          'label': ['deploy/build-label-ui.py', '--source-root', str(candidate),
                                    '--output', 'work/label-ui-build', '--toolchain-root',
                                    str(candidate / 'work/toolchains')],
                          'backend': ['deploy/build-homebox-backend.py']},
             'ui_build': ({'node': subprocess.check_output([str(node), '--version'], text=True).strip(),
                           'pnpm': subprocess.check_output([str(pnpm), '--version'], env=env,
                                                           text=True).strip(),
                           'lock_sha256': _hash(candidate / 'homebox-ui/pnpm-lock.yaml')}
                          if not reuse_existing else {'reused_output_sha256': _hash(public / 'index.html')}),
             'label_build': label_rows,
             'backend_receipt': build_rows, 'native_sha256': native_hash,
             'public_files': public_files, 'label_files': label_files,
             'source_commit': commit, 'homebox_commit': submodule_commit}
    build['installation_overlays'] = {'previous': installed_origin,
                                      'maintained_helpers': maintained_overlays}
    test_receipt = {'source_manifest_digest': source_digest, 'static_manifest_sha256': static_sha,
                    'source_entries': {name: {'sha256': runtime_files[name], 'mode': runtime_modes[name]}
                                       for name in runtime_files},
                    'verification': {'exit_code': 0, 'tests': total_tests},
                    'runs': tests, 'execution_scope': 'manager-private-source-fixtures',
                    'workshop_compatibility': {'closure_sha256': closure, 'tests': compatibility}}
    build_raw = json.dumps(build, sort_keys=True, indent=2)
    test_raw = json.dumps(test_receipt, sort_keys=True, indent=2)
    build_path = candidate / 'work/build-provenance.json'
    test_path = candidate / 'work/test-provenance.json'
    build_path.write_text(build_raw)
    test_path.write_text(test_raw)
    provenance = {
        'source_manifest_digest': source_digest, 'static_manifest_sha256': static_sha,
        'build_receipt': build, 'build_receipt_raw': build_raw,
        'build_receipt_sha256': hashlib.sha256(build_raw.encode()).hexdigest(),
        'build_receipt_canonical_sha256': hashlib.sha256(_canonical(build)).hexdigest(),
        'build_receipt_path': build_path.relative_to(root).as_posix(),
        'test_receipt': test_receipt, 'test_receipt_raw': test_raw,
        'test_receipt_sha256': hashlib.sha256(test_raw.encode()).hexdigest(),
        'test_receipt_canonical_sha256': hashlib.sha256(_canonical(test_receipt)).hexdigest(),
        'test_receipt_path': test_path.relative_to(root).as_posix(),
        'native_sha256': native_hash, 'runtime_files': runtime_files,
        'runtime_modes': runtime_modes, 'public_files': public_files,
        'label_files': label_files,
        'label_source_sha256': starter_hash,
        'workshop_capability': {'schema': 1, 'read_versions': [1, 2], 'write_mode': 'v2',
                                'closure_sha256': closure,
                                'test_names': ['workshop_read_v1', 'workshop_read_v2', 'workshop_write_v2']},
    }
    releases = root / 'work/application-releases'
    releases.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination = releases / f'{commit}-manager-{candidate.name}'
    print('Sealing the verified source candidate…', flush=True)
    release_bundle.stage_bundle(destination, binary=binary, public=public,
                               source=candidate, provenance=provenance)
    release_bundle.validate_bundle(destination)
    receipt = {'schema': 1, 'source_commit': commit, 'homebox_commit': submodule_commit,
               'release': destination.relative_to(root).as_posix(),
               'release_manifest_sha256': _hash(destination / 'manifest.json'),
               'source_manifest_digest': source_digest,
               'focused_tests': {'exit_code': 0, 'tests': total_tests},
               'build_results': results}
    (candidate / 'work/candidate-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return {'candidate': destination}


def prepare_candidate(root=ROOT, *, commit=None, builder=None):
    root = Path(root).resolve(strict=True)
    started = __import__('time').time()
    lock_path = root / 'work/.manager-update.lock'
    lock_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(lock_fd)
        raise RuntimeError('Another source update preparation is already running') from exc
    try:
        result = _prepare_candidate_locked(root, commit=commit, builder=builder, started=started)
        _write_status(root, stage='candidate-ready', started_at=started, outcome='success', commit=commit)
        return result
    except BaseException as exc:
        _write_status(root, stage='failed', started_at=started, outcome='failed',
                      commit=commit, error=str(exc)[:500])
        raise
    finally:
        os.close(lock_fd)


def _prepare_candidate_locked(root, *, commit, builder, started, existing_candidate=None):
    # A durable activation intent must survive candidate preparation failures.
    # Check it before writing preflight status, which would otherwise replace it.
    if builder is None:
        from deploy.ccrate_manager import _assert_no_pending_manager_transaction
        _assert_no_pending_manager_transaction(root, allow_running_build=True)
    _write_status(root, stage='preflight', started_at=started, commit=commit)
    _preflight_space(root)
    if commit is not None and (len(commit) not in (40, 64)
                               or any(c not in '0123456789abcdef' for c in commit)):
        raise ValueError('Approved source must be a full lowercase Git object ID')
    _run(['git', '-C', str(root), 'fetch', '--no-tags', 'origin', 'main'])
    remote_commit = _git(root, 'rev-parse', 'FETCH_HEAD^{commit}')
    commit = remote_commit if commit is None else _git(root, 'rev-parse', f'{commit}^{{commit}}')
    if commit != remote_commit:
        _run(['git', '-C', str(root), 'merge-base', '--is-ancestor', commit, remote_commit])
    updates = root / 'work/manager-updates'
    updates.mkdir(mode=0o700, parents=True, exist_ok=True)
    if updates.is_symlink() or not updates.is_dir():
        raise RuntimeError('Manager update staging directory is unsafe')
    os.chmod(updates, 0o700)
    commit_root = updates / commit
    commit_root.mkdir(mode=0o700, exist_ok=True)
    if commit_root.is_symlink() or not commit_root.is_dir():
        raise RuntimeError('Pinned commit staging directory is unsafe')
    os.chmod(commit_root, 0o700)
    if existing_candidate is None:
        candidate = commit_root / uuid.uuid4().hex
        _write_status(root, stage='source-staging', started_at=started, commit=commit)
        submodule_commit = stage_source_commit(root, root / 'upstream/homebox', commit, candidate)
        (candidate / 'work').mkdir(mode=0o700, exist_ok=True)
    else:
        candidate = Path(existing_candidate).resolve(strict=True)
        if candidate.parent != commit_root.resolve(strict=True) or candidate.is_symlink():
            raise RuntimeError('Resume staging path is outside the pinned commit workspace')
        listing = _git(root, 'ls-tree', commit, 'upstream/homebox').split()
        if len(listing) < 3 or listing[0:2] != ['160000', 'commit']:
            raise RuntimeError('Pinned source commit has no upstream gitlink')
        submodule_commit = listing[2]
        if _git(candidate / 'upstream/homebox', 'rev-parse', 'HEAD') != submodule_commit:
            raise RuntimeError('Resume stage upstream checkout does not match the pinned gitlink')
        _write_status(root, stage='resuming-staged-source', started_at=started, commit=commit,
                      log_path=str(candidate / 'work/manager-logs'))
    print(f'Pinned source commit: {commit}', flush=True)
    if builder is None:
        _write_status(root, stage='build-and-test', started_at=started, commit=commit,
                      log_path=str(candidate / 'work/manager-logs'))
        release = _build_and_stage(root, candidate, commit, submodule_commit)
    else:
        release = builder(root, candidate, commit)
    _write_status(root, stage='candidate-ready', started_at=started,
                  commit=commit, log_path=str(candidate / 'work/manager-logs'))
    return release


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description='Build and seal a candidate from trusted origin/main.')
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--commit', help='Prepare this approved full commit ID after confirming it is on fetched origin/main.')
    args = parser.parse_args(argv)
    if args.commit and (len(args.commit) not in (40, 64) or any(c not in '0123456789abcdef' for c in args.commit)):
        parser.error('--commit must be a full lowercase Git object ID')
    try:
        release = prepare_candidate(args.root, commit=args.commit)
    except Exception as error:
        print(f'Source candidate preparation failed: {error}', file=sys.stderr)
        return 1
    print(f'Source candidate ready: {release}')
    return 0
