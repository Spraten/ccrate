"""Focused regression tests for disposable Homebox UI build preparation."""
import contextlib
import importlib.util
import io
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_homebox_ui", ROOT / "deploy/build-homebox-ui.py")
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


class HomeboxUiBuilderTests(unittest.TestCase):
    def test_prepare_accepts_barcode_aware_create_entity_dialog_type(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            previous_build = BUILDER.BUILD
            BUILDER.BUILD = pathlib.Path(directory) / "homebox-ui-build"
            try:
                BUILDER.prepare()
            finally:
                BUILDER.BUILD = previous_build

            dialog_utils = (pathlib.Path(directory) / "homebox-ui-build/components/ui/dialog-provider/utils.ts").read_text()
            self.assertIn("barcode?: string", dialog_utils)
            self.assertIn("parentId?: string", dialog_utils)
            self.assertIn("product?: BarcodeProduct", dialog_utils)

            nuxt_config = (pathlib.Path(directory) / "homebox-ui-build/nuxt.config.ts").read_text()
            self.assertEqual(nuxt_config.count("  modules: ["), 1)
            self.assertLess(nuxt_config.index('"shadcn-nuxt"'), nuxt_config.index('(_options, nuxt) =>'))
            self.assertIn('nuxt.hook("components:dirs"', nuxt_config)
            self.assertTrue((pathlib.Path(directory) / "homebox-ui-build/components/ui/button/index.ts").exists())

            node = shutil.which("node")
            if not node:
                self.skipTest("Node.js is required to exercise the generated Nuxt hook fixture")
            match = re.search(r'nuxt\.hook\("components:dirs",\s*(dirs => \{.*?\n      \})\);', nuxt_config, re.S)
            self.assertIsNotNone(match, "expected a components filter inside the trailing Nuxt module")
            fixture = (
                "const dirs = []; "
                "const shadcn = dirs => dirs.push({path: '/build/components/ui/button', extensions: ['ts', 'vue']}); "
                "const ccrate = (" + match.group(1) + "); "
                "shadcn(dirs); ccrate(dirs); process.stdout.write(JSON.stringify(dirs));"
            )
            result = subprocess.run([node, "-e", fixture], capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout, '[{"path":"/build/components/ui/button","extensions":["vue"]}]')

    def test_wasi_filter_is_narrow_and_keeps_command_failure_status(self):
        notice = "ERROR (node:31459) ExperimentalWarning: WASI is an experimental feature and might change at any time\n"
        unrelated = "ExperimentalWarning: another API is experimental\n"
        self.assertEqual(BUILDER.filter_known_wasi_warning(notice + unrelated), unrelated)

        stdout, stderr = io.StringIO(), io.StringIO()
        command = [
            sys.executable,
            "-c",
            "import sys; "
            "print('ordinary output'); "
            + "print(" + repr(notice.rstrip("\n")) + ", file=sys.stderr); "
            + "print(" + repr(unrelated.rstrip("\n")) + ", file=sys.stderr); "
            + "sys.exit(7)",
        ]
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with self.assertRaises(subprocess.CalledProcessError) as raised:
                BUILDER.run_frontend_command(command, cwd=ROOT, env=os.environ.copy())

        self.assertEqual(raised.exception.returncode, 7)
        self.assertIn("ordinary output", stdout.getvalue())
        self.assertNotIn("WASI is an experimental feature", stderr.getvalue())
        self.assertIn("another API is experimental", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
