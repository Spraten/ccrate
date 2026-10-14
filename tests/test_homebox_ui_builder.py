"""Focused regression tests for disposable Homebox UI build preparation."""
import contextlib
import importlib.util
import io
import json
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

            create_modal = (pathlib.Path(directory) / "homebox-ui-build/components/Entity/CreateModal.vue").read_text()
            import_block = create_modal[create_modal.index("  import type {"):create_modal.index('  } from "~~/lib/api/types/data-contracts";')]
            form_start = create_modal.index("  const form = reactive({")
            form_block = create_modal[form_start:create_modal.index("\n  });", form_start)]
            self.assertEqual(import_block.count("EntitySummary,"), 1)
            self.assertEqual(form_block.count('modelNumber: "",'), 1)
            self.assertEqual(create_modal.count("modelNumber: form.modelNumber,"), 3)
            self.assertEqual(create_modal.count('v-model="form.modelNumber"'), 1)

            nuxt_config = (pathlib.Path(directory) / "homebox-ui-build/nuxt.config.ts").read_text()
            self.assertEqual(nuxt_config.count("  modules: ["), 1)
            self.assertLess(nuxt_config.index('"shadcn-nuxt"'), nuxt_config.index('(_options, nuxt) =>'))
            self.assertIn('nuxt.hook("components:dirs"', nuxt_config)
            self.assertTrue((pathlib.Path(directory) / "homebox-ui-build/components/ui/button/index.ts").exists())

            node = shutil.which("node")
            if not node:
                self.skipTest("Node.js is required to exercise the generated Nuxt hook fixture")
            match = re.search(r'(\(_options, nuxt\) => \{.*?\n    \})', nuxt_config, re.S)
            self.assertIsNotNone(match, "expected a trailing inline Nuxt module")
            module_block = re.search(r"  modules: \[(.*?)\n  \],", nuxt_config, re.S)
            self.assertIsNotNone(module_block, "expected the generated Nuxt modules list")
            module_entries = re.findall(r'"([^"\n]+)"|(\(_options, nuxt\) => \{.*?\n    \})', module_block.group(1), re.S)
            configured_modules = [
                {"name": name} if name else {"inline": inline}
                for name, inline in module_entries
            ]
            self.assertEqual(configured_modules[-1], {"inline": match.group(1)})
            self.assertLess(
                next(index for index, entry in enumerate(configured_modules) if entry.get("name") == "shadcn-nuxt"),
                len(configured_modules) - 1,
            )
            self.assertIn("nuxt@4.2.2", (ROOT / "upstream/homebox/frontend/pnpm-lock.yaml").read_text())
            fixture = (
                "const configured = JSON.parse(process.argv[1]); const dirs = []; const hooks = []; "
                "const nuxt = {hook(name, callback) { if (name === 'components:dirs') hooks.push(callback); }}; "
                "const installed = { 'shadcn-nuxt': (_options, nuxt) => nuxt.hook('components:dirs', dirs => dirs.push({path: '/build/components/ui/button', extensions: ['ts', 'vue']})) }; "
                "const modules = configured.map(entry => entry.name ? (installed[entry.name] || (() => {})) : eval('(' + entry.inline + ')')); "
                "for (const setup of modules) setup({}, nuxt); "
                "for (const hook of hooks) hook(dirs); "
                "process.stdout.write(JSON.stringify(dirs));"
            )
            result = subprocess.run([node, "-e", fixture, json.dumps(configured_modules)], capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout, '[{"path":"/build/components/ui/button","extensions":["vue"]}]')

    def test_wasi_filter_is_narrow_and_keeps_command_failure_status(self):
        notice = "ERROR (node:31459) ExperimentalWarning: WASI is an experimental feature and might change at any time\n"
        unrelated = "ExperimentalWarning: another API is experimental\n"
        self.assertEqual(BUILDER.filter_known_wasi_warning(notice + unrelated), unrelated)
        extended_notice = notice.rstrip("\n") + " | unrelated failure\n"
        self.assertEqual(BUILDER.filter_known_wasi_warning(extended_notice), extended_notice)

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
