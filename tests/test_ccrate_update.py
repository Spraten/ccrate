import subprocess
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock
from pathlib import Path

from deploy import ccrate_update as update


class SourceUpdateTests(unittest.TestCase):
    def git(self, cwd, *args):
        return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()

    def repository(self, path, files):
        path.mkdir(parents=True)
        self.git(path, 'init', '-q')
        self.git(path, 'config', 'user.email', 'fixture@example.invalid')
        self.git(path, 'config', 'user.name', 'Fixture')
        for name, content in files.items():
            target = path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        self.git(path, 'add', '.')
        self.git(path, 'commit', '-qm', 'fixture')
        return self.git(path, 'rev-parse', 'HEAD')

    def test_stages_exact_project_and_pinned_submodule_commits_without_checkout_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'checkout'
            submodule = Path(temp) / 'upstream-repo'
            sub_hash = self.repository(submodule, {'backend.go': 'pinned backend'})
            root_hash = self.repository(root, {'.gitmodules': '[submodule "upstream/homebox"]\n\tpath = upstream/homebox\n\turl = fixture\n', 'app.py': 'pinned project'})
            self.git(root, 'branch', '-M', 'main')
            self.git(root, 'update-index', '--add', '--cacheinfo', f'160000,{sub_hash},upstream/homebox')
            self.git(root, 'commit', '-qm', 'pin submodule')
            root_hash = self.git(root, 'rev-parse', 'HEAD')
            (root / 'app.py').write_text('uncommitted checkout edit')
            destination = Path(temp) / 'candidate'

            actual_sub_hash = update.stage_source_commit(root, submodule, root_hash, destination)

            self.assertEqual(actual_sub_hash, sub_hash)
            self.assertEqual((destination / 'app.py').read_text(), 'pinned project')
            self.assertEqual((destination / 'upstream/homebox/backend.go').read_text(), 'pinned backend')
            self.assertEqual((root / 'app.py').read_text(), 'uncommitted checkout edit')

    def test_failed_builder_leaves_no_success_receipts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'checkout'
            root.mkdir()
            self.git(root, 'init', '-q')
            self.git(root, 'config', 'user.email', 'fixture@example.invalid')
            self.git(root, 'config', 'user.name', 'Fixture')
            (root / '.gitmodules').write_text('[submodule "upstream/homebox"]\n\tpath = upstream/homebox\n\turl = fixture\n')
            (root / 'source.py').write_text('source')
            self.git(root, 'add', '.gitmodules', 'source.py')
            self.git(root, 'commit', '-qm', 'source')
            submodule = root / 'upstream/homebox'
            submodule.mkdir(parents=True)
            self.git(submodule, 'init', '-q')
            self.git(submodule, 'config', 'user.email', 'fixture@example.invalid')
            self.git(submodule, 'config', 'user.name', 'Fixture')
            (submodule / 'backend.go').write_text('backend')
            self.git(submodule, 'add', 'backend.go')
            self.git(submodule, 'commit', '-qm', 'backend')
            sub_hash = self.git(submodule, 'rev-parse', 'HEAD')
            self.git(root, 'update-index', '--add', '--cacheinfo', f'160000,{sub_hash},upstream/homebox')
            self.git(root, 'commit', '-qm', 'pin')
            self.git(root, 'branch', '-M', 'main')
            bare = Path(temp) / 'origin.git'
            self.git(Path(temp), 'clone', '--bare', str(root), str(bare))
            self.git(root, 'remote', 'add', 'origin', str(bare))
            (root / 'work/toolchains').mkdir(parents=True)
            (root / 'program-files/runtime/hardware/python').mkdir(parents=True)

            def fail(_root, candidate, _commit):
                (candidate / 'work').mkdir(exist_ok=True)
                raise subprocess.CalledProcessError(1, ['builder'])

            with mock.patch.object(update.shutil, 'disk_usage', return_value=SimpleNamespace(free=4 * 1024 ** 3)):
                with self.assertRaises(subprocess.CalledProcessError):
                    update.prepare_candidate(root, builder=fail)
                with self.assertRaises(subprocess.CalledProcessError):
                    update.prepare_candidate(root, builder=fail)
            commit = self.git(root, 'rev-parse', 'refs/remotes/origin/main')
            candidates = list((root / 'work/manager-updates' / commit).iterdir())
            self.assertEqual(len(candidates), 2)
            for candidate in candidates:
                self.assertFalse((candidate / 'work/build-provenance.json').exists())
                self.assertFalse((candidate / 'work/test-provenance.json').exists())

    def test_workshop_compatibility_fixture_uses_candidate_code_and_disposable_database(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            candidate = Path(temp)
            shutil.copytree(source / 'ops', candidate / 'ops')
            (candidate / 'work').mkdir()
            names = update._run_workshop_fixture(candidate)
        self.assertEqual([row['name'] for row in names], [
            'workshop_read_v1', 'workshop_read_v2', 'workshop_write_v2'])
        self.assertTrue(all(row['result'] == 'passed' for row in names))

    def test_low_space_refuses_before_fetching_or_staging(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with mock.patch.object(update.shutil, 'disk_usage', return_value=SimpleNamespace(free=1024)), \
                 mock.patch.object(update, '_run') as run:
                with self.assertRaisesRegex(RuntimeError, 'must be free'):
                    update.prepare_candidate(root)
            run.assert_not_called()

    def test_public_identity_records_full_project_and_submodule_commits(self):
        with tempfile.TemporaryDirectory() as temp:
            public = Path(temp) / 'public'
            public.mkdir()
            path = update.write_source_identity(public, 'a' * 40, 'b' * 40)
            self.assertEqual(path.read_text(), '{\n  "schema": 1,\n  "source_commit": "' + 'a' * 40 + '",\n  "homebox_commit": "' + 'b' * 40 + '"\n}\n')


if __name__ == '__main__':
    unittest.main()
