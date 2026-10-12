import ast
from pathlib import Path
import stat
import tempfile
import unittest


SOURCE = Path(__file__).parents[1] / 'deploy/install-homebox-shortcuts.py'
EXEC = '/usr/bin/chromium --user-data-dir=/home/user/.config/homebox-browser --new-window http://127.0.0.1:17745'
CONTENT = f'[Desktop Entry]\nType=Application\nName=C-Crate\nExec={EXEC}\n'
LEGACY = 'Homebox.desktop'


def load_installer():
    tree = ast.parse(SOURCE.read_text())
    wanted = {'install_shortcut', 'desktop_entry_exec', 'regular_or_missing'}
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    namespace = {'desktop': None, 'stat': stat}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), 'exec'), namespace)
    return namespace


class ShortcutInstallerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.desktop = Path(self.temp.name)
        self.installer = load_installer()
        self.installer['desktop'] = self.desktop
        self.install = self.installer['install_shortcut']
        self.destination = self.desktop / 'C-Crate.desktop'

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, path=None, legacy=LEGACY):
        self.install(path or self.destination, legacy, CONTENT, EXEC)

    def test_regular_legacy_migrates_and_repeat_is_idempotent(self):
        old = self.desktop / LEGACY
        old.write_text(CONTENT)
        self.invoke()
        self.assertFalse(old.exists())
        self.assertEqual(self.destination.read_text(), CONTENT)
        self.assertEqual(self.destination.stat().st_mode & 0o777, 0o755)
        self.invoke()
        self.assertEqual(self.destination.read_text(), CONTENT)

    def test_unrelated_exec_with_command_in_comment_is_preserved(self):
        old = self.desktop / LEGACY
        unrelated = f'[Desktop Entry]\nType=Application\nName=Other\nComment={EXEC}\nExec=/usr/bin/other\n'
        old.write_text(unrelated)
        self.invoke()
        self.assertEqual(old.read_text(), unrelated)
        self.assertEqual(self.destination.read_text(), CONTENT)

    def test_unrelated_destination_with_command_in_comment_is_preserved(self):
        unrelated = f'[Desktop Entry]\nType=Application\nName=Other\nComment={EXEC}\nExec=/usr/bin/other\n'
        self.destination.write_text(unrelated)
        with self.assertRaises((AssertionError, OSError)):
            self.invoke()
        self.assertEqual(self.destination.read_text(), unrelated)

    def test_destination_symlink_is_rejected_without_touching_target(self):
        target = self.desktop / 'target'
        target.write_text(CONTENT)
        self.destination.symlink_to(target)
        with self.assertRaises((AssertionError, OSError)):
            self.invoke()
        self.assertTrue(self.destination.is_symlink())
        self.assertEqual(target.read_text(), CONTENT)

    def test_dangling_destination_symlink_is_rejected(self):
        target = self.desktop / 'missing'
        self.destination.symlink_to(target)
        with self.assertRaises((AssertionError, OSError)):
            self.invoke()
        self.assertTrue(self.destination.is_symlink())
        self.assertFalse(target.exists())

    def test_legacy_symlink_is_rejected_without_touching_target(self):
        target = self.desktop / 'target'
        target.write_text(CONTENT)
        old = self.desktop / LEGACY
        old.symlink_to(target)
        with self.assertRaises((AssertionError, OSError)):
            self.invoke()
        self.assertTrue(old.is_symlink())
        self.assertEqual(target.read_text(), CONTENT)
        self.assertFalse(self.destination.exists())

    def test_dangling_legacy_symlink_is_rejected(self):
        old = self.desktop / LEGACY
        old.symlink_to(self.desktop / 'missing')
        with self.assertRaises((AssertionError, OSError)):
            self.invoke()
        self.assertTrue(old.is_symlink())
        self.assertFalse(self.destination.exists())

    def test_nonregular_entries_are_rejected(self):
        old = self.desktop / LEGACY
        old.mkdir()
        with self.assertRaises((AssertionError, OSError)):
            self.invoke()
        old.rmdir()
        self.destination.mkdir()
        with self.assertRaises((AssertionError, OSError)):
            self.invoke()
        self.assertTrue(self.destination.is_dir())


if __name__ == '__main__':
    unittest.main()
