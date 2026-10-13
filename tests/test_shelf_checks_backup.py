"""Private backup coverage for the shelf-check Ledger, using only a fixture root."""
import ast
import hashlib
import json
import os
import pathlib
import runpy
import sqlite3
import tarfile
import tempfile
import types
import unittest
from uuid import uuid4

from ledger import Ledger
from shelf_checks import ShelfChecks


SCRIPT = pathlib.Path(__file__).resolve().parents[1] / 'deploy' / 'backup-deployment.py'
OPERATIONAL_ROOT = '/home/user/Desktop/inventory-system'


class NativeFixture:
    def __init__(self):
        self.nodes = {}
        self.actor = None

    def add(self, name, *, location=False, parent=None, quantity=1):
        entity_id = str(uuid4())
        self.nodes[entity_id] = {
            'id': entity_id, 'name': name, 'entityType': {'isLocation': location},
            'parent': {'id': parent} if parent else None, 'archived': False,
            'quantity': quantity, 'assetId': '', 'serialNumber': '', 'fields': [],
        }
        return entity_id

    def entity(self, entity_id):
        return dict(self.nodes[entity_id])

    def entities(self, locations=False):
        return [dict(row) for row in self.nodes.values()
                if row['entityType']['isLocation'] is locations]

    def call(self, path, method='GET', **kwargs):
        if path == '/api/v1/groups/members':
            return [{'id': self.actor, 'name': 'Fixture manager'}]
        raise AssertionError(f'Unexpected synthetic native call: {path}')


def populate_backup_members(root):
    """Create only the paths that the current backup script selects."""
    directories = ['.git', 'ops', 'kiosk', 'deploy', 'docs', 'upstream/homebox',
                   'work/baseline/data', 'work/ops', 'work/homebox-bin',
                   'work/supvan-cups/target/release/examples', 'work/hardware/python',
                   'label-ui/src', 'label-ui/vendor', 'label-ui/public', 'label-ui/patches',
                   'work/label-ui-build']
    for name in directories:
        (root / name).mkdir(parents=True, exist_ok=True)
        (root / name / 'fixture.txt').write_text('fixture')
    files = ['AGENTS.md', 'work/baseline/pepper', 'work/baseline/test-account.json',
             'work/homebox-bin/homebox',
             'work/supvan-cups/target/release/examples/kiosk-label',
             'label-ui/package.json', 'label-ui/pnpm-lock.yaml', 'label-ui/vite.config.ts',
             'label-ui/editor.html', 'label-ui/render.html', 'label-ui/vendor-manifest.json']
    for name in files:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'fixture binary or data\n')


def run_fixture_backup(source: pathlib.Path, root: pathlib.Path) -> pathlib.Path:
    """Execute the backup program with its root rewritten in memory and calls trapped."""
    source_text = source.read_text()
    tree = ast.parse(source_text, filename=str(source))

    class IsolateRoot(ast.NodeTransformer):
        def visit_Constant(self, node):
            if node.value == OPERATIONAL_ROOT:
                return ast.copy_location(ast.Constant(str(root)), node)
            return node

        def visit_Import(self, node):
            # Inject a recording subprocess facade below instead of importing the real one.
            kept = [alias for alias in node.names if alias.name != 'subprocess']
            return ast.copy_location(ast.Import(names=kept), node) if kept else None

    tree = ast.fix_missing_locations(IsolateRoot().visit(tree))
    calls = []
    output = []

    class FakeSubprocess:
        @staticmethod
        def run(args, **kwargs):
            calls.append(('run', list(args)))
            return types.SimpleNamespace(returncode=0)

        @staticmethod
        def check_output(args, **kwargs):
            calls.append(('check_output', list(args)))
            return 'fixture-commit\n'

    namespace = {'__name__': '__main__', 'subprocess': FakeSubprocess,
                 'print': lambda *args, **kwargs: output.append(args)}
    previous_umask = os.umask(0)
    os.umask(previous_umask)
    try:
        exec(compile(tree, str(source), 'exec'), namespace)
    finally:
        os.umask(previous_umask)
    backups = sorted((root / 'work/backups').glob('deployment-*.tar.gz'))
    if len(backups) != 1:
        raise AssertionError(f'Expected one fixture backup, found {len(backups)}')
    run_fixture_backup.intercepted_calls = calls
    run_fixture_backup.intercepted_prints = output
    return backups[0]


class ShelfChecksBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='shelf-checks-backup-')
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        populate_backup_members(self.root)
        self.group, self.actor = str(uuid4()), str(uuid4())
        self.ctx = {'group': self.group, 'actor': self.actor, 'manager': True}
        self.native = NativeFixture()
        self.native.actor = self.actor
        self.location = self.native.add('Fixture Shelf', location=True)
        self.asset = self.native.add('Fixture Drill', parent=self.location, quantity=2)
        self.ledger = Ledger(self.root / 'work/ops/ledger.db')
        self.store = ShelfChecks(self.ledger)
        self.keys = {}

    @staticmethod
    def key():
        return str(uuid4())

    def start(self, request_key=None):
        request_key = request_key or self.key()
        check = self.store.start(self.native, self.ctx, location_id=self.location,
                                 request_key=request_key)
        self.keys[request_key] = check
        return check

    def test_backup_selection_includes_ledger(self):
        backup = runpy.run_path(str(SCRIPT), run_name='backup_deployment_test')
        selected = set(backup['BASE_MEMBERS'])
        optional = backup['OPTIONAL_DATABASES']
        for name in optional:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(path)
            connection.close()
        databases = set(backup['database_inventory'](self.root))
        self.assertIn('work/ops', selected)
        self.assertIn('work/ops/ledger.db', databases)
        self.assertTrue(set(optional).issubset(databases))

    def test_transaction_backup_does_not_restart_services(self):
        backup = runpy.run_path(str(SCRIPT), run_name='backup_transaction_fixture')
        for name in ('work/ops/ledger.db', 'work/baseline/data/homebox.db'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(path)
            connection.close()
        calls = []

        class SyntheticSubprocess:
            @staticmethod
            def run(args, **kwargs):
                calls.append(list(args))
                return types.SimpleNamespace(returncode=0)

            @staticmethod
            def check_output(args, **kwargs):
                return 'synthetic-revision\n'

        # runpy returns a globals copy, while the function resolves globals from
        # its original execution namespace. Patch that namespace at the boundary.
        backup['create_cold_backup'].__globals__['subprocess'] = SyntheticSubprocess
        result = backup['create_cold_backup'](self.root, manage_services=False)
        self.assertEqual(result['status'], 'completed')
        self.assertFalse(any(args[:3] == ['systemctl', '--user', 'start']
                             or args[:3] == ['systemctl', '--user', 'stop'] for args in calls))

    def test_private_backup_restores_original_review_and_results(self):
        saved = {}

        draft = self.start()
        original = draft['original_snapshot']
        changed_key = self.key()
        self.native.nodes[self.asset]['quantity'] = 3
        changed = self.store.observe(self.native, self.ctx, draft['id'], revision=draft['revision'],
                                     entity_id=self.asset, method='visual', observed_quantity=2,
                                     request_key=changed_key)
        saved['draft'] = changed
        saved['draft_original'] = original
        saved['draft_request_key'] = changed_key
        saved['draft_result'] = self.store.request(self.ctx, changed_key)['result']
        refresh_key = self.key()
        reviewed = self.store.refresh(self.native, self.ctx, changed['id'],
                                      revision=changed['revision'], request_key=refresh_key)
        saved['refreshed'] = reviewed
        saved['refresh_key'] = refresh_key
        saved['refresh_result'] = self.store.request(self.ctx, refresh_key)['result']

        finish_key = self.key()
        completed = self.store.finish(self.native, self.ctx, reviewed['id'],
                                      revision=reviewed['revision'],
                                      review_fingerprint=reviewed['review_fingerprint'],
                                      request_key=finish_key)
        saved['completed'] = completed
        saved['finish_key'] = finish_key
        saved['finish_result'] = self.store.request(self.ctx, finish_key)['result']

        cancelled_draft = self.start()
        cancel_key = self.key()
        cancelled = self.store.cancel(self.native, self.ctx, cancelled_draft['id'],
                                      revision=cancelled_draft['revision'], confirmed=True,
                                      reason='Fixture cancellation', request_key=cancel_key)
        saved['cancelled'] = cancelled
        saved['cancel_key'] = cancel_key
        saved['cancel_result'] = self.store.request(self.ctx, cancel_key)['result']

        # Keep a writer open with WAL autocheckpoint disabled so the backup must checkpoint it.
        wal_writer = sqlite3.connect(self.ledger.path)
        wal_writer.execute('PRAGMA journal_mode=WAL')
        wal_writer.execute('PRAGMA wal_autocheckpoint=0')
        wal_writer.execute('INSERT INTO shelf_check_schema_meta(singleton,version) VALUES(1,2) '
                           'ON CONFLICT(singleton) DO UPDATE SET version=excluded.version')
        wal_writer.commit()
        self.assertTrue(pathlib.Path(str(self.ledger.path) + '-wal').exists())
        wal_writer.close()

        backup = run_fixture_backup(SCRIPT, self.root)
        with tarfile.open(backup, 'r:gz') as archive:
            names = set(archive.getnames())
            self.assertIn('work/ops/ledger.db', names)
            manifest = json.load(archive.extractfile('deployment-manifest.json'))
            restored_db = self.root / 'restored/work/ops/ledger.db'
            restored_db.parent.mkdir(parents=True)
            restored_db.write_bytes(archive.extractfile('work/ops/ledger.db').read())
            backup_info = archive.getmember('deployment-manifest.json')
            self.assertEqual(backup_info.mode & 0o777, 0o600)

        self.assertIn('work/ops', manifest['members'])
        self.assertEqual(manifest['sha256']['work/ops/ledger.db'],
                         hashlib.sha256(restored_db.read_bytes()).hexdigest())
        with sqlite3.connect(restored_db) as restored_sql:
            self.assertEqual(restored_sql.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

        reopened = ShelfChecks(Ledger(restored_db))
        for key, original_key, result_key in (
                (saved['draft']['id'], 'draft_original', 'draft_result'),
                (saved['completed']['id'], 'draft_original', 'finish_result'),
                (saved['cancelled']['id'], None, 'cancel_result')):
            check = reopened.get(self.native, self.ctx, key)
            self.assertEqual(check['actor_id'], self.actor)
            if original_key:
                self.assertEqual(check['original_snapshot'], saved[original_key])
            self.assertEqual(check['state'], saved['completed']['state'] if key == saved['completed']['id']
                             else saved['cancelled']['state'] if key == saved['cancelled']['id'] else 'draft')
            if key == saved['draft']['id']:
                self.assertEqual(check['original_snapshot'], saved['draft_original'])
                self.assertEqual(check['reviewed_snapshot'], saved['refreshed']['reviewed_snapshot'])
                self.assertEqual(check['observations'], saved['refreshed']['observations'])
        self.assertEqual(reopened.get(self.native, self.ctx, saved['completed']['id'])['original_snapshot'],
                         saved['completed']['original_snapshot'])
        for request_key, result in ((saved['draft_request_key'], saved['draft_result']),
                                    (saved['refresh_key'], saved['refresh_result']),
                                    (saved['finish_key'], saved['finish_result']),
                                    (saved['cancel_key'], saved['cancel_result'])):
            self.assertEqual(reopened.request(self.ctx, request_key)['result'], result)
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        self.assertEqual(run_fixture_backup.intercepted_calls, [
            ('run', ['systemctl', '--user', 'stop', 'homebox-workshop-gateway.service',
                     'homebox-companion.service', 'homebox-native.service']),
            ('check_output', ['git', 'rev-parse', 'HEAD']),
            ('check_output', ['git', '-C', 'upstream/homebox', 'rev-parse', 'HEAD']),
            ('run', ['systemctl', '--user', 'start', 'homebox-native.service',
                     'homebox-companion.service', 'homebox-workshop-gateway.service']),
        ])
        self.assertEqual(run_fixture_backup.intercepted_prints, [(json.dumps({
            'status': 'completed', 'backup': backup.name, 'bytes': backup.stat().st_size,
            'database_integrity': 'ok'}),)])


if __name__ == '__main__':
    unittest.main()
