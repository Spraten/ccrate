#!/usr/bin/env python3
"""Run an isolated local Homebox test stack and bootstrap its first user once."""
import json
import os
import pathlib
import secrets
import signal
import sqlite3
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

CODE_ROOT = pathlib.Path(os.environ.get('WORKSHOP_CODE_ROOT', '/app')).resolve()
DATA_ROOT = pathlib.Path(os.environ.get('WORKSHOP_ROOT', '/data')).resolve()
NATIVE_BINARY = pathlib.Path(os.environ.get('WORKSHOP_NATIVE_BINARY', '/app/native/homebox')).resolve()
NATIVE_BASE = 'http://127.0.0.1:17747'
REGISTRATION = '/api/v1/users/register'
LOGIN = '/api/v1/users/login'
SELF = '/api/v1/users/self'
STATUS = '/api/v1/status'


class BootstrapError(RuntimeError):
    pass


class BootstrapRecoveryRequired(BootstrapError):
    pass


class AuthenticationError(BootstrapError):
    pass


def validate_data_root(root, *, expected_root=DATA_ROOT, mount_check=os.path.ismount):
    """Require the exact, mounted data location selected for this local stack."""
    root = pathlib.Path(root)
    expected = pathlib.Path(expected_root)
    if not root.is_absolute() or root != expected or root.is_symlink():
        raise BootstrapError('Local test data must use its dedicated data directory')
    try:
        if root.resolve(strict=True) != root or not root.is_dir() or not mount_check(root):
            raise BootstrapError('Local test data path is unavailable or not isolated')
    except OSError as error:
        raise BootstrapError('Local test data path is unavailable') from error
    return root


def _private_regular(path):
    try:
        info = path.lstat()
    except OSError:
        return False
    return (stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.getuid()
            and info.st_mode & 0o077 == 0)


def _atomic_json(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, separators=(',', ':'))
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


class BootstrapStore:
    def __init__(self, root=DATA_ROOT, *, expected_root=DATA_ROOT, mount_check=os.path.ismount):
        self.root = validate_data_root(root, expected_root=expected_root, mount_check=mount_check)
        self.run_root = self.root / 'work' / 'baseline'
        self.database_path = self.run_root / 'data' / 'homebox.db'
        self.account_path = self.run_root / 'test-account.json'
        self.pepper_path = self.run_root / 'pepper'
        self.state_path = self.root / 'work' / 'local-test' / 'bootstrap.json'
        self.marker_path = self.root / '.ccrate-local-test-volume.json'
        self.manager_config_path = self.root / 'work' / 'ops' / 'desktop-managers.json'

    def prepare_volume(self):
        if not self.marker_path.exists():
            if any(self.root.iterdir()):
                raise BootstrapError('Existing data has no local-test marker; refusing to adopt it')
            _atomic_json(self.marker_path, {'format': 'ccrate-local-test-v1', 'volume_id': str(uuid.uuid4())})
        if not _private_regular(self.marker_path):
            raise BootstrapError('Local-test volume marker is missing, linked, or has unsafe permissions')
        try:
            marker = json.loads(self.marker_path.read_text(encoding='utf-8'))
            uuid.UUID(marker['volume_id'])
        except (OSError, ValueError, TypeError, KeyError):
            raise BootstrapError('Local-test volume marker is invalid') from None
        if marker.get('format') != 'ccrate-local-test-v1':
            raise BootstrapError('Data volume belongs to a different application')
        self.validate_bootstrap_files()
        self.validate_database()

    def load_state(self):
        if not self.state_path.exists():
            return None
        if not _private_regular(self.state_path):
            raise BootstrapError('Bootstrap intent has unsafe file permissions')
        try:
            value = json.loads(self.state_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            raise BootstrapError('Bootstrap intent is damaged') from None
        if not isinstance(value, dict) or value.get('format') != 1 or value.get('status') not in (
                'prepared', 'registration_started', 'complete'):
            raise BootstrapError('Bootstrap intent is incomplete or unsupported')
        return value

    def validate_bootstrap_files(self):
        state = self.load_state()
        artifacts = (self.account_path, self.pepper_path, self.database_path)
        if state is None:
            extras = [path for path in self.root.iterdir() if path != self.marker_path]
            if extras or any(path.exists() for path in artifacts):
                raise BootstrapError('Incomplete local-test bootstrap artifacts; refusing account creation')
            return None
        if not _private_regular(self.account_path) or not _private_regular(self.pepper_path):
            raise BootstrapError('Bootstrap credentials or native pepper are missing or unsafe')
        try:
            account = json.loads(self.account_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            raise BootstrapError('Bootstrap credentials are damaged') from None
        if (not isinstance(account, dict) or not isinstance(account.get('email'), str)
                or not account['email'] or not isinstance(account.get('password'), str)
                or len(account['password']) < 24 or len(self.pepper_path.read_text()) < 32
                or state.get('email') != account['email']):
            raise BootstrapError('Bootstrap credentials do not match the saved intent')
        if state['status'] in ('registration_started', 'complete') and not self.database_path.is_file():
            raise BootstrapError('Native database is missing after registration was started')
        if state['status'] == 'complete' and (not isinstance(state.get('user_id'), str) or not state['user_id']):
            raise BootstrapError('Completed bootstrap has no native user identity')
        return state

    def validate_database(self):
        if not self.database_path.exists():
            return
        state = self.load_state()
        if state is None:
            raise BootstrapError('Existing native database has no matching bootstrap intent')
        try:
            uri = self.database_path.as_uri() + '?mode=ro'
            with sqlite3.connect(uri, uri=True, timeout=2) as connection:
                check = connection.execute('PRAGMA integrity_check').fetchone()
                if not check or check[0] != 'ok':
                    raise BootstrapError('Native database integrity check failed')
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if 'users' not in tables:
                    raise BootstrapError('Native database has no recognized users table')
                if state['status'] == 'prepared':
                    if connection.execute('SELECT count(*) FROM users').fetchone()[0] != 0:
                        raise BootstrapError('Prepared local-test database already contains an account')
                elif state['status'] == 'complete':
                    row = connection.execute('SELECT email FROM users WHERE id=?', (state['user_id'],)).fetchone()
                    if not row or row[0].casefold() != state['email'].casefold():
                        raise BootstrapError('Saved native identity is missing or no longer matches')
        except BootstrapError:
            raise
        except (sqlite3.Error, OSError, ValueError) as error:
            raise BootstrapError('Native database is damaged or unreadable') from error

    def account(self):
        self.validate_bootstrap_files()
        try:
            return json.loads(self.account_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            raise BootstrapError('Local test account credentials are unavailable') from None

    def create_intent(self):
        if any(path.exists() for path in (self.account_path, self.pepper_path, self.database_path, self.state_path)):
            raise BootstrapError('Partial local-test setup exists; refusing to overwrite it')
        account = {
            'name': 'Local Test Admin',
            'email': 'local-admin@local.invalid',
            'password': secrets.token_urlsafe(36),
        }
        attempt_id = str(uuid.uuid4())
        _atomic_json(self.account_path, account)
        self.run_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(self.pepper_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='ascii') as stream:
            stream.write(secrets.token_urlsafe(48))
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        directory = os.open(self.run_root, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        _atomic_json(self.state_path, {
            'format': 1, 'status': 'prepared', 'request_id': attempt_id,
            'email': account['email'], 'created_at': int(time.time()),
        })
        return account

    def ensure_account(self, register, authenticate):
        self.prepare_volume()
        state = self.validate_bootstrap_files()
        if state is None:
            account = self.create_intent()
            state = self.load_state()
        else:
            account = self.account()
        status = state['status']
        if status == 'prepared':
            self.validate_database()
            state = dict(state, status='registration_started')
            _atomic_json(self.state_path, state)
            register(account)
        try:
            identity = authenticate(account)
        except Exception as error:
            if status == 'registration_started' or state['status'] == 'registration_started':
                raise BootstrapRecoveryRequired(
                    'The one-time account request has an unknown outcome. Inspect the local database before recovery; registration will not be repeated.'
                ) from error
            raise
        user_id = identity.get('id') if isinstance(identity, dict) else None
        email = identity.get('email') if isinstance(identity, dict) else None
        if not user_id or not isinstance(email, str) or email.casefold() != account['email'].casefold():
            raise BootstrapError('Native login did not return the expected local account')
        if status == 'complete' and user_id != state.get('user_id'):
            raise BootstrapError('Native account identity changed; inspect the local database')
        if status != 'complete':
            state = dict(state, status='complete', user_id=user_id)
            _atomic_json(self.state_path, state)
        self.validate_database()
        return identity


def stop_children(children, *, grace_seconds=5):
    alive = [child for child in children if child.poll() is None]
    for child in reversed(alive):
        try:
            child.terminate()
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + max(0, grace_seconds)
    for child in reversed(alive):
        try:
            child.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            try:
                child.kill()
            except ProcessLookupError:
                pass
            child.wait()


def ensure_manager_config(store, identity):
    """Grant the seed account manager access once, then validate without rewriting."""
    state = store.validate_bootstrap_files()
    if state is None or state.get('status') != 'complete':
        raise BootstrapError('A completed local-test account is required before manager setup')
    user_id = identity.get('id') if isinstance(identity, dict) else None
    email = identity.get('email') if isinstance(identity, dict) else None
    group_id = identity.get('defaultGroupId') if isinstance(identity, dict) else None
    group_ids = identity.get('groupIds') if isinstance(identity, dict) else None
    if (not user_id or user_id != state.get('user_id') or not isinstance(email, str)
            or email.casefold() != state.get('email', '').casefold()
            or not isinstance(group_id, str) or not group_id
            or not isinstance(group_ids, list) or group_id not in group_ids):
        raise BootstrapError('Native seed account or default collection does not match the saved bootstrap identity')

    path = store.manager_config_path
    setup = state.get('manager_setup')
    if path.exists():
        if not _private_regular(path):
            raise BootstrapError('Desktop manager configuration is unsafe')
        try:
            config = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            raise BootstrapError('Desktop manager configuration is damaged') from None
        managers = config.get('managers') if isinstance(config, dict) else None
        if (not isinstance(managers, list) or config.get('owner_id') != user_id
                or not any(isinstance(entry, dict) and entry.get('user_id') == user_id
                           and entry.get('group_id') == group_id for entry in managers)):
            raise BootstrapError('Desktop manager configuration does not match the saved local owner and collection')
        if setup != 'complete':
            _atomic_json(store.state_path, dict(state, manager_setup='complete'))
        return

    if setup is not None:
        raise BootstrapError('Confirmed desktop manager configuration is missing; refusing to restore privileges')

    # Older local-test volumes may have completed native registration before this
    # companion setup existed. Record the migration intent before creating config.
    _atomic_json(store.state_path, dict(state, manager_setup='started'))
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    payload = {'owner_id': user_id, 'managers': [{'user_id': user_id, 'group_id': group_id}]}
    encoded = (json.dumps(payload, separators=(',', ':')) + '\n').encode('utf-8')
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise BootstrapError('Desktop manager configuration appeared during bootstrap; refusing to overwrite it') from None
    with os.fdopen(fd, 'wb') as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    _atomic_json(store.state_path, dict(state, manager_setup='complete'))


def _request(path, *, method='GET', data=None, token=None, timeout=5):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = token
    body = json.dumps(data).encode('utf-8') if data is not None else None
    request = urllib.request.Request(NATIVE_BASE + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        if method == 'POST' and path == REGISTRATION:
            # A response, including an error response, still proves the request was sent.
            raise BootstrapRecoveryRequired('Native registration returned an error; the request will not be repeated') from error
        if method == 'POST' and path == LOGIN:
            raise AuthenticationError('Local test account could not sign in') from error
        raise


def register_account(account):
    _request(REGISTRATION, method='POST', data={key: account[key] for key in ('name', 'email', 'password')}, timeout=30)


def authenticate_account(account):
    response = _request(LOGIN, method='POST', data={'username': account['email'], 'password': account['password']}, timeout=30)
    token = response.get('token') if isinstance(response, dict) else None
    if not isinstance(token, str) or not token.startswith('Bearer '):
        raise AuthenticationError('Native login returned no session token')
    wrapped = _request(SELF, token=token)
    identity = wrapped.get('item') if isinstance(wrapped, dict) else None
    return identity if isinstance(identity, dict) else {}


def _native_environment(allow_registration):
    root = DATA_ROOT / 'work' / 'baseline'
    environment = dict(os.environ, HBOX_WEB_HOST='127.0.0.1', HBOX_WEB_PORT='17747',
                HBOX_WEB_WRITE_TIMEOUT='60s', HBOX_STORAGE_PREFIX_PATH='data',
                HBOX_DATABASE_SQLITE_PATH=str(root / 'data' / 'homebox.db') + '?_pragma=busy_timeout=999&_pragma=journal_mode=WAL&_fk=1&_time_format=sqlite',
                HBOX_AUTH_API_KEY_PEPPER=(root / 'pepper').read_text().strip(),
                HBOX_OPTIONS_GITHUB_RELEASE_CHECK='false', HBOX_OPTIONS_ALLOW_ANALYTICS='false',
                HBOX_OPTIONS_ALLOW_REGISTRATION='true' if allow_registration else 'false')
    environment.pop('WORKSHOP_UI_DEV_PORT', None)
    return environment


def _wait_native(child, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise RuntimeError(f'Native Homebox exited during startup ({child.returncode})')
        try:
            with urllib.request.urlopen(NATIVE_BASE + STATUS, timeout=2) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(.25)
    raise RuntimeError('Native Homebox did not become ready')


def _wait_http(url, child, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise RuntimeError(f'{child.args[-1]} exited during startup ({child.returncode})')
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(.25)
    raise RuntimeError(f'Service did not become ready at {url}')


def _healthcheck():
    for url in ('http://127.0.0.1:17745/api/v1/status', 'http://127.0.0.1:17749/api/session'):
        with urllib.request.urlopen(url, timeout=3) as response:
            if response.status != 200:
                return False
    return True


def run():
    if os.environ.get('WORKSHOP_LOCAL_TEST') != '1':
        raise BootstrapError('This supervisor only runs an isolated local-test instance')
    live_ui = os.environ.get('WORKSHOP_LOCAL_UI_DEV', '1') != '0'
    native_mode = os.environ.get('WORKSHOP_LOCAL_TEST_NATIVE') == '1'
    if native_mode:
        expected = pathlib.Path.home() / '.local' / 'share' / 'ccrate-local-test' / 'data'
        if DATA_ROOT != expected or DATA_ROOT.is_symlink():
            raise BootstrapError('Native local-test data must use ~/.local/share/ccrate-local-test/data')
        DATA_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(DATA_ROOT, 0o700)
    store = BootstrapStore(DATA_ROOT, expected_root=DATA_ROOT,
                           mount_check=(lambda _path: True) if native_mode else os.path.ismount)
    store.prepare_volume()
    state = store.validate_bootstrap_files()
    if state is None:
        store.create_intent()
        state = store.validate_bootstrap_files()
    store.database_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    allow_registration = state is None or state['status'] == 'prepared'
    processes = []
    stopping = False

    def stop(_signum=None, _frame=None):
        nonlocal stopping
        stopping = True
        stop_children(processes)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    env = dict(os.environ, WORKSHOP_NATIVE_PORT='17747', WORKSHOP_COMPANION_PORT='17749', WORKSHOP_PORT='17745')
    env.pop('WORKSHOP_UI_DEV_HOST', None)
    env.pop('WORKSHOP_UI_DEV_PORT', None)
    try:
        if live_ui:
            preparation = subprocess.Popen(
                [sys.executable, str(CODE_ROOT / 'deploy' / 'dev-homebox-ui.py'), 'prepare'],
                cwd=CODE_ROOT, env=env)
            processes.append(preparation)
            if preparation.wait() != 0:
                raise RuntimeError(f'Dev UI preparation failed ({preparation.returncode})')
            processes.remove(preparation)
        native = subprocess.Popen([str(NATIVE_BINARY)], cwd=DATA_ROOT / 'work' / 'baseline',
                                  env=_native_environment(allow_registration))
        processes.append(native)
        _wait_native(native)
        identity = store.ensure_account(register_account, authenticate_account)
        if allow_registration:
            stop_children([native])
            processes.remove(native)
            native = subprocess.Popen([str(NATIVE_BINARY)], cwd=DATA_ROOT / 'work' / 'baseline',
                                      env=_native_environment(False))
            processes.append(native)
            _wait_native(native)
            identity = store.ensure_account(register_account, authenticate_account)
        ensure_manager_config(store, identity)
        companion = subprocess.Popen([sys.executable, str(CODE_ROOT / 'deploy' / 'kiosk-server.py')], cwd=CODE_ROOT, env=env)
        processes.append(companion)
        _wait_http('http://127.0.0.1:17749/api/session', companion)
        gateway_env = env
        if live_ui:
            dev_ui = subprocess.Popen([sys.executable, str(CODE_ROOT / 'deploy' / 'dev-homebox-ui.py'), 'serve'],
                                      cwd=CODE_ROOT, env=env)
            processes.append(dev_ui)
            _wait_http('http://127.0.0.1:17751/', dev_ui, timeout=120)
            gateway_env = dict(env, WORKSHOP_UI_DEV_PORT='17751')
        gateway = subprocess.Popen([sys.executable, str(CODE_ROOT / 'deploy' / 'workshop-gateway.py')], cwd=CODE_ROOT, env=gateway_env)
        processes.append(gateway)
        _wait_http('http://127.0.0.1:17745/api/v1/status', gateway)
        _wait_http('http://127.0.0.1:17749/api/session', companion)
        print('C-Crate local test is ready at http://localhost:17745', flush=True)
        while not stopping:
            for process in processes:
                code = process.poll()
                if code is not None:
                    raise RuntimeError(f'A local-test service exited unexpectedly ({code})')
            time.sleep(.5)
    finally:
        stop_children(processes)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--healthcheck':
        raise SystemExit(0 if _healthcheck() else 1)
    try:
        run()
    except Exception as error:
        print(f'Local test startup stopped safely: {error}', file=sys.stderr, flush=True)
        raise SystemExit(1)
