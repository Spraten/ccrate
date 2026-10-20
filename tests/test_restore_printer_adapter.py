import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'deploy/restore-printer-adapter.sh'


class RestorePrinterAdapterScriptTests(unittest.TestCase):
    def run_with_shims(self, rust_version, git_status=''):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / 'checkout'
        (root / 'deploy').mkdir(parents=True)
        (root / 'work/supvan-cups/.git').mkdir(parents=True)
        script = root / 'deploy/restore-printer-adapter.sh'
        script.write_bytes(SCRIPT.read_bytes())
        script.chmod(0o755)
        (root / 'deploy/kiosk-label.rs').write_text('// fixture adapter source\n')
        shim = Path(temp.name) / 'bin'
        shim.mkdir()
        scripts = {
            'cargo': '#!/bin/sh\necho cargo-called >&2\nexit 90\n',
            'rustc': f'#!/bin/sh\necho "rustc {rust_version}"\n',
            'pkg-config': '#!/bin/sh\nexit 0\n',
            'git': '#!/bin/sh\ncase "$*" in *"status --porcelain --untracked-files=all"*) echo "$GIT_STATUS";; *) echo git-called >&2; exit 91;; esac\n',
        }
        for name, content in scripts.items():
            path = shim / name
            path.write_text(content)
            path.chmod(0o755)
        env = dict(os.environ, PATH=f'{shim}:/usr/bin:/bin', GIT_STATUS=git_status)
        proc = subprocess.run([str(root / 'deploy/restore-printer-adapter.sh')], text=True, capture_output=True, env=env)
        return proc, root

    def test_rejects_old_rust_before_repository_or_build_changes(self):
        proc, root = self.run_with_shims('1.85.0 (fixture)')
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('requires Rust 1.88 or newer', proc.stderr)
        self.assertIn('trixie-backports', proc.stderr)
        self.assertFalse((root / 'work/printer-adapter-build').exists())

    def test_dirty_source_checkout_is_refused_before_build(self):
        proc, root = self.run_with_shims('1.88.0 (fixture)', ' M crates/supvan-proto/src/lib.rs')
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('Refusing to change a dirty printer source checkout', proc.stderr)
        self.assertFalse((root / 'work/printer-adapter-build').exists())


if __name__ == '__main__':
    unittest.main()
