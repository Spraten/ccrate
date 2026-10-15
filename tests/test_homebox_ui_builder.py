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


@contextlib.contextmanager
def isolated_builder_prepare(build_root, materializer_work_root):
    """Keep prepare()'s real materialization isolated from shared generated caches."""
    import homebox_patchset

    previous_build = BUILDER.BUILD
    previous_source_lock = homebox_patchset._source_lock
    previous_materialize_locked = homebox_patchset._materialize_locked

    def source_lock(_path):
        materializer_work_root.mkdir(parents=True, exist_ok=True)
        return previous_source_lock(materializer_work_root / ".homebox-source-patchset.lock")

    def materialize_locked(upstream, base, patches, digest, _work):
        materializer_work_root.mkdir(parents=True, exist_ok=True)
        return previous_materialize_locked(
            upstream, base, patches, digest, materializer_work_root
        )

    BUILDER.BUILD = build_root
    homebox_patchset._source_lock = source_lock
    homebox_patchset._materialize_locked = materialize_locked
    try:
        yield
    finally:
        BUILDER.BUILD = previous_build
        homebox_patchset._source_lock = previous_source_lock
        homebox_patchset._materialize_locked = previous_materialize_locked


class HomeboxUiBuilderTests(unittest.TestCase):
    def test_typecheck_tool_failure_is_not_misclassified_as_upstream_diagnostics(self):
        known_diagnostic = (
            "frontend/example.ts(4,8): error TS2307: Cannot find module 'upstream-module'.\n"
            " ERROR  Process exited with non-zero status (2)\n"
        )
        tool_failure = "ERR_PNPM_RECURSIVE_EXEC_FIRST_FAIL Command \"nuxi\" not found\n"
        baseline = {"pin": "a" * 40, "diagnostics": [["frontend/example.ts", "TS2307", "Cannot find module 'upstream-module'."]]}

        self.assertFalse(BUILDER.has_frontend_tool_failure(known_diagnostic))
        self.assertTrue(BUILDER.has_frontend_tool_failure(known_diagnostic + tool_failure))
        for tool_error in (
            "Error: ENOSPC: no space left on device\n",
            "Error: EACCES: permission denied\n",
        ):
            self.assertTrue(BUILDER.has_frontend_tool_failure(known_diagnostic + tool_error))
        self.assertTrue(BUILDER.is_only_known_upstream_typecheck_failure(known_diagnostic, baseline, "a" * 40))
        self.assertFalse(BUILDER.is_only_known_upstream_typecheck_failure(known_diagnostic + tool_failure, baseline, "a" * 40))
        self.assertFalse(BUILDER.is_only_known_upstream_typecheck_failure(known_diagnostic + "Error: ENOSPC: no space left on device\n", baseline, "a" * 40))
        spawn_failure = " ERROR  spawn vue-tsc ENOENT\n"
        self.assertTrue(BUILDER.has_frontend_tool_failure(known_diagnostic + spawn_failure))
        self.assertFalse(BUILDER.is_only_known_upstream_typecheck_failure(known_diagnostic + spawn_failure, baseline, "a" * 40))
        for exit_code in ("3", "139"):
            nonstandard = re.sub(r"\(2\)", f"({exit_code})", known_diagnostic)
            self.assertFalse(BUILDER.is_only_known_upstream_typecheck_failure(nonstandard, baseline, "a" * 40))

    def test_pnpm_launcher_prefers_cmd_on_windows_when_both_exist(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            toolchain = pathlib.Path(directory)
            extensionless = toolchain / "pnpm/node_modules/.bin/pnpm"
            windows_launcher = extensionless.with_suffix(".cmd")
            windows_launcher.parent.mkdir(parents=True)
            windows_launcher.write_text("@echo off")

            self.assertEqual(BUILDER.resolve_pnpm_launcher(toolchain, platform="nt"), windows_launcher)
            self.assertEqual(BUILDER.resolve_pnpm_launcher(toolchain, platform="posix"), extensionless)

            extensionless.write_text("#!/bin/sh")
            self.assertEqual(BUILDER.resolve_pnpm_launcher(toolchain, platform="nt"), windows_launcher)
            windows_launcher.unlink()
            self.assertEqual(BUILDER.resolve_pnpm_launcher(toolchain, platform="nt"), extensionless)

    def test_cli_typecheck_waiver_requires_expected_outer_status(self):
        diagnostic = "frontend/example.ts(4,8): error TS2307: Cannot find module 'upstream-module'.\n"
        wrapper = " ERROR  Process exited with non-zero status (2)\n"
        output = diagnostic + wrapper
        baseline = {
            "pin": "a" * 40,
            "diagnostics": [["frontend/example.ts", "TS2307", "Cannot find module 'upstream-module'."]],
        }

        def run_case(returncode, should_build):
            with tempfile.TemporaryDirectory(dir=ROOT) as directory:
                test_root = pathlib.Path(directory)
                toolchain_root = test_root / "toolchain"
                (toolchain_root / "node-path.txt").parent.mkdir(parents=True)
                (toolchain_root / "node-path.txt").write_text(str(test_root / "node"))
                (test_root / "homebox-ui").mkdir()
                (test_root / "homebox-ui/upstream-typecheck.json").write_text(json.dumps(baseline))
                (test_root / "work").mkdir()

                previous = {
                    "BUILD": BUILDER.BUILD,
                    "ROOT": BUILDER.ROOT,
                    "TOOLCHAIN_ROOT": BUILDER.TOOLCHAIN_ROOT,
                    "UPSTREAM_ROOT": BUILDER.UPSTREAM_ROOT,
                    "prepare": BUILDER.prepare,
                    "run_frontend_command": BUILDER.run_frontend_command,
                    "source_commit": BUILDER.source_commit,
                    "subprocess_run": BUILDER.subprocess.run,
                    "argv": sys.argv,
                }
                commands = []
                BUILDER.ROOT = test_root
                BUILDER.BUILD = test_root / "frontend"
                BUILDER.TOOLCHAIN_ROOT = toolchain_root
                BUILDER.UPSTREAM_ROOT = test_root / "upstream"
                BUILDER.prepare = lambda: None
                BUILDER.run_frontend_command = lambda command, *, cwd, env: commands.append(command)
                BUILDER.source_commit = lambda _path: "a" * 40
                BUILDER.subprocess.run = lambda command, **kwargs: subprocess.CompletedProcess(
                    command, returncode, stdout=output, stderr=""
                )
                sys.argv = ["build-homebox-ui.py", "--toolchain-root", str(toolchain_root)]
                try:
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        if should_build:
                            BUILDER.build()
                        else:
                            with self.assertRaisesRegex(RuntimeError, "introduced errors"):
                                BUILDER.build()
                finally:
                    BUILDER.BUILD = previous["BUILD"]
                    BUILDER.ROOT = previous["ROOT"]
                    BUILDER.TOOLCHAIN_ROOT = previous["TOOLCHAIN_ROOT"]
                    BUILDER.UPSTREAM_ROOT = previous["UPSTREAM_ROOT"]
                    BUILDER.prepare = previous["prepare"]
                    BUILDER.run_frontend_command = previous["run_frontend_command"]
                    BUILDER.source_commit = previous["source_commit"]
                    BUILDER.subprocess.run = previous["subprocess_run"]
                    sys.argv = previous["argv"]
                self.assertEqual(any(command[1:] == ["run", "build"] for command in commands), should_build)

        run_case(-9, should_build=False)
        run_case(1, should_build=True)

    def test_cli_full_build_uses_a_fresh_disposable_root_and_scopes_typecheck_log(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            test_root = pathlib.Path(directory)
            build_root = test_root / "disposable-frontend"
            toolchain_root = test_root / "toolchain"
            repo_work = test_root / "work"
            repo_work.mkdir()
            default_typecheck_log = repo_work / "homebox-ui-typecheck.log"
            default_typecheck_log.write_text("keep default build log")
            (toolchain_root / "node-path.txt").parent.mkdir(parents=True)
            (toolchain_root / "node-path.txt").write_text(str(test_root / "node"))
            pnpm_launcher = toolchain_root / "pnpm/node_modules/.bin/pnpm"
            pnpm_launcher.parent.mkdir(parents=True)
            if os.name == "nt":
                pnpm_launcher = pnpm_launcher.with_suffix(".cmd")
            pnpm_launcher.write_text("mock pnpm launcher")
            wasi_binding = toolchain_root / "oxc-wasi/node_modules/@oxc-parser/binding-wasm32-wasi"
            wasi_binding.mkdir(parents=True)
            oxc_binding = pathlib.Path("node_modules/.pnpm/oxc-parser@0.72.3/node_modules/oxc-parser/bindings.js")

            previous_build = BUILDER.BUILD
            previous_root = BUILDER.ROOT
            previous_toolchain = BUILDER.TOOLCHAIN_ROOT
            previous_upstream = BUILDER.UPSTREAM_ROOT
            previous_prepare = BUILDER.prepare
            previous_runner = BUILDER.run_frontend_command
            previous_subprocess_run = BUILDER.subprocess.run
            previous_argv = sys.argv
            prepared_roots = []
            commands = []
            stdout = io.StringIO()

            def prepare():
                prepared_roots.append(BUILDER.BUILD)
                binding = BUILDER.BUILD / oxc_binding
                binding.parent.mkdir(parents=True)
                binding.write_text("nativeBinding = requireNative()")

            def run_command(command, *, cwd, env):
                prepared_roots.append(cwd)
                commands.append(command)
                if command[1:3] == ["install", "--frozen-lockfile"]:
                    self.assertIn("--ignore-scripts", command)
                    self.assertIn("requireNative()", (cwd / oxc_binding).read_text())
                if command[1:] == ["exec", "nuxt", "prepare"]:
                    configured_binding = (cwd / oxc_binding).read_text()
                    self.assertNotIn("requireNative()", configured_binding)
                    self.assertIn(repr(str(wasi_binding)), configured_binding)

            BUILDER.prepare = prepare
            BUILDER.run_frontend_command = run_command
            BUILDER.subprocess.run = lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout="", stderr="")
            BUILDER.ROOT = test_root
            sys.argv = [
                "build-homebox-ui.py",
                "--build-root",
                str(build_root),
                "--toolchain-root",
                str(toolchain_root),
            ]
            try:
                with contextlib.redirect_stdout(stdout):
                    BUILDER.build()
            finally:
                BUILDER.BUILD = previous_build
                BUILDER.ROOT = previous_root
                BUILDER.TOOLCHAIN_ROOT = previous_toolchain
                BUILDER.UPSTREAM_ROOT = previous_upstream
                BUILDER.prepare = previous_prepare
                BUILDER.run_frontend_command = previous_runner
                BUILDER.subprocess.run = previous_subprocess_run
                sys.argv = previous_argv

            self.assertEqual(prepared_roots, [build_root.resolve()] * 4)
            self.assertEqual(
                [command[1:] for command in commands],
                [["install", "--frozen-lockfile", "--ignore-scripts"], ["exec", "nuxt", "prepare"], ["run", "build"]],
            )
            self.assertTrue(all(command[0] == str(pnpm_launcher) for command in commands))
            self.assertIn("Installing frontend dependencies in disposable workspace", stdout.getvalue())
            self.assertIn("Nuxt preparation complete", stdout.getvalue())
            self.assertTrue((build_root / "homebox-ui-typecheck.log").is_file())
            self.assertEqual(default_typecheck_log.read_text(), "keep default build log")
            self.assertTrue(build_root.is_dir())

    def test_cli_rejects_a_nonempty_disposable_build_root_without_touching_it(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            test_root = pathlib.Path(directory)
            build_root = test_root / "disposable-frontend"
            build_root.mkdir()
            sentinel = build_root / "keep-me.txt"
            sentinel.write_text("existing workspace")
            previous_argv = sys.argv
            stderr = io.StringIO()
            sys.argv = ["build-homebox-ui.py", "--build-root", str(build_root)]
            try:
                with contextlib.redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as raised:
                        BUILDER.build()
            finally:
                sys.argv = previous_argv

            self.assertEqual(raised.exception.code, 2)
            self.assertIn("must be empty", stderr.getvalue())
            self.assertEqual(sentinel.read_text(), "existing workspace")


    def test_create_item_actions_are_after_photo_preview_without_changing_form_actions(self):
        source = '''      <PhotoUploader />
      <div class="mt-4 flex flex-row-reverse">
        <ButtonGroup>
          <Button :disabled="loading" type="submit" class="group">{{ $t("global.create") }}</Button>
          <Button variant="outline" :disabled="loading" type="button" @click="create(false)">{{ $t("global.create_and_add") }}</Button>
        </ButtonGroup>
      </div>

      <PhotoUploaderPreview
        :photos="form.photos"
        @delete="deletePhotoAt"
        @rotate="rotatePhotoAt"
        @set-primary="setPrimaryPhotoAt"
      />
'''
        generated = BUILDER.move_create_actions_after_photo_preview(source)

        self.assertLess(generated.index("<PhotoUploaderPreview"), generated.index('type="submit"'))
        self.assertLess(generated.index("<PhotoUploaderPreview"), generated.index('@click="create(false)"'))
        actions = source[source.index('      <div class="mt-4 flex flex-row-reverse">'):source.index('\n\n      <PhotoUploaderPreview')]
        self.assertEqual(generated.count(actions), 1)
        self.assertEqual(generated.count('type="submit"'), 1)
        self.assertEqual(generated.count('@click="create(false)"'), 1)
        self.assertEqual(BUILDER.move_create_actions_after_photo_preview(generated), generated)

    def test_create_action_move_fails_clearly_when_photo_preview_markup_shifts(self):
        source = '''      <div class="mt-4 flex flex-row-reverse">
        <ButtonGroup>
          <Button type="submit">Create</Button>
          <Button @click="create(false)">Create & Add</Button>
        </ButtonGroup>
      </div>

      <PhotoUploaderPreview
        :photos="form.photos"
      >
'''
        with self.assertRaisesRegex(RuntimeError, "photo preview"):
            BUILDER.move_create_actions_after_photo_preview(source)

    def test_create_action_move_rejects_paired_photo_preview_markup(self):
        source = '''      <div class="mt-4 flex flex-row-reverse">
        <ButtonGroup>
          <Button type="submit">Create</Button>
          <Button @click="create(false)">Create & Add</Button>
        </ButtonGroup>
      </div>

      <PhotoUploaderPreview
        :photos="form.photos"
      >
        <div>Preview content</div>
      </PhotoUploaderPreview>

      <LaterComponent
      />
'''
        with self.assertRaisesRegex(RuntimeError, "self-closing photo preview"):
            BUILDER.move_create_actions_after_photo_preview(source)

    def test_create_action_buttons_must_belong_to_the_same_actions_block(self):
        source = '''      <PhotoUploader />
      <div class="mt-4 flex flex-row-reverse">
        <ButtonGroup>
          <Button :disabled="loading" type="button" class="group">{{ $t("global.create") }}</Button>
        </ButtonGroup>
      </div>

      <PhotoUploaderPreview
        :photos="form.photos"
      />
      <Button type="submit">{{ $t("global.create") }}</Button>
      <Button type="button" @click="create(false)">{{ $t("global.create_and_add") }}</Button>
'''
        with self.assertRaisesRegex(RuntimeError, "both existing create actions"):
            BUILDER.move_create_actions_after_photo_preview(source)

    def test_create_action_wrapper_cannot_borrow_buttons_from_a_later_block(self):
        source = '''      <PhotoUploader />
      <div class="mt-4 flex flex-row-reverse">
      </div>
      <div class="other-actions">
        <ButtonGroup>
          <Button type="submit">{{ $t("global.create") }}</Button>
          <Button type="button" @click="create(false)">{{ $t("global.create_and_add") }}</Button>
        </ButtonGroup>
      </div>

      <PhotoUploaderPreview
        :photos="form.photos"
      />
'''
        with self.assertRaises(RuntimeError):
            BUILDER.move_create_actions_after_photo_preview(source)

    def test_camera_ocr_build_injection_uses_local_engine_and_edit_revision(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            previous_build = BUILDER.BUILD
            BUILDER.BUILD = pathlib.Path(directory)
            page = BUILDER.BUILD / "pages/item/[id]/index/edit.vue"
            modal = BUILDER.BUILD / "components/Entity/CreateModal.vue"
            page.parent.mkdir(parents=True)
            modal.parent.mkdir(parents=True)
            page.write_text('''  import { recognizeNameFromFileLocally } from "~/components/Form/camera";
  const nameOcrMessage = ref("");
  async function suggestItemNameFromPhoto(file: File) {
    try {
      const suggestion = await recognizeNameFromFileLocally(file);
      if (!suggestion) {
        nameOcrMessage.value = t("components.form.camera.name_not_found");
        return;
      }
      item.value.name = suggestion;
      nameOcrMessage.value = t("components.form.camera.name_suggested");
    } catch {
      nameOcrMessage.value = t("components.form.camera.name_unavailable");
    }
  }
                  <FormTextField
                    v-model="item[field.ref]"
                    class="min-w-0 flex-1"
                  />
                  <Button type="button" variant="outline">
                    {{ $t("components.form.camera.suggest_name") }}
                  </Button>
                </div>
                <FormTextField
                  v-else-if="field.type === 'text'"
''')
            modal.write_text('''  import { recognizeNameFromFileLocally } from "~/components/Form/camera";
  const { openDialog, closeDialog, registerOpenDialogCallback } = useDialog();
  const nameOcrMessage = ref("");
  async function suggestNameFromPhoto(file: File) {
    try {
      const suggestion = await recognizeNameFromFileLocally(file);
      if (!suggestion) {
        nameOcrMessage.value = t("components.form.camera.name_not_found");
        return;
      }
      form.name = suggestion;
      nameOcrMessage.value = t("components.form.camera.name_suggested");
    } catch {
      nameOcrMessage.value = t("components.form.camera.name_unavailable");
    }
  }
          <FormTextField
          v-model="form.name"
          class="min-w-0 flex-1"
          />
          {{ $t("components.form.camera.suggest_name") }}
      <p v-if="nameOcrMessage" class="text-sm text-muted-foreground" role="status">{{ nameOcrMessage }}</p>
    form.name = "";
''')
            locale = BUILDER.BUILD / "locales/en.json"
            locale.parent.mkdir(parents=True)
            locale.write_text(json.dumps({"components": {"form": {"camera": {}}}}))
            try:
                BUILDER.camera_ocr_frontend()
            finally:
                BUILDER.BUILD = previous_build

            generated = page.read_text()
            camera = json.loads(locale.read_text())["components"]["form"]["camera"]
            self.assertIn('from "~/lib/local-ocr"', generated)
            self.assertIn('getRevision: () => nameEditRevision.value', generated)
            self.assertIn('@update:model-value="nameEditRevision++"', generated)
            self.assertIn('nameOcrMessage.value = t("components.form.camera.ocr_running")', generated)
            self.assertIn('setName: (value: string) => { item.value.name = value; }', generated)
            self.assertIn("not uploaded", camera["local_ocr_notice"])
            self.assertIn("name_preserved", camera)
            generated_modal = modal.read_text()
            self.assertIn('from "~/lib/local-ocr"', generated_modal)
            self.assertIn('getRevision: () => nameEditRevision.value', generated_modal)
            self.assertIn('@update:model-value="nameEditRevision++"', generated_modal)
            self.assertIn('nameOcrMessage.value = t("components.form.camera.ocr_running")', generated_modal)
            self.assertIn('setName: (value: string) => { form.name = value; }', generated_modal)
            self.assertIn('const { activeDialog, openDialog, closeDialog, registerOpenDialogCallback } = useDialog();', generated_modal)
            self.assertIn('watch(activeDialog, value => { if (value !== DialogID.CreateEntity) { nameOcrGeneration++; nameOcrMessage.value = ""; } }, { flush: "sync" });', generated_modal)
            self.assertIn('isCurrent: () => request === nameOcrGeneration', generated_modal)
            self.assertIn('nameOcrGeneration++;\n    nameOcrMessage.value = "";\n    form.name = "";', generated_modal)

    def test_orc_popover_is_mounted_globally_and_uses_local_ocr_helper(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            previous_build = BUILDER.BUILD
            BUILDER.BUILD = pathlib.Path(directory)
            layout = BUILDER.BUILD / "layouts/default.vue"
            layout.parent.mkdir(parents=True)
            layout.write_text('''<template>\n  <Sidebar />\n  <SidebarInset class="min-h-dvh max-w-full overflow-hidden bg-background-accent">\n    <div v-if="preferences.displayLegacyHeader">\n      <AppHeaderDecor />\n      <SidebarTrigger class="absolute left-2 top-2 hidden lg:flex" variant="default" />\n      <DeviceStatus v-if="preferences.displayLegacyHeader && terminalHeader" :enabled="preferences.displayLegacyHeader && terminalHeader" class="absolute right-6 top-3 z-30 hidden lg:flex" />\n    </div>\n    <div class="flex min-w-0 grow items-center justify-end gap-2">\n      <DeviceStatus v-if="!preferences.displayLegacyHeader || !terminalHeader" :enabled="!preferences.displayLegacyHeader || !terminalHeader" class="shrink-0" />\n      <button>Header action</button>\n    </div>\n    <NuxtPage />\n      </SidebarInset>\n</template>\n<script lang="ts" setup>\n  import AppHeaderDecor from "~/components/App/HeaderDecor.vue";\n  const search = ref("");\n</script>\n''')
            try:
                BUILDER.ocr_popover_frontend()
            finally:
                BUILDER.BUILD = previous_build

            generated = layout.read_text()
            self.assertEqual(generated.count("<OcrPopover"), 1)
            device_status = generated.index('<DeviceStatus v-if="!preferences.displayLegacyHeader')
            regular_target = generated.index('<div id="orc-launcher-toolbar"')
            self.assertGreater(regular_target, device_status)
            sidebar_trigger = generated.index('<SidebarTrigger class="absolute left-2 top-2 hidden lg:flex"')
            legacy_target = generated.index('<div id="orc-launcher-legacy"')
            self.assertGreater(legacy_target, sidebar_trigger)
            self.assertEqual(generated.count('<OcrPopover :launcher-target="orcLauncherTarget" />'), 1)
            self.assertIn('preferences.value.displayLegacyHeader && terminalHeader.value ? "#orc-launcher-legacy" : "#orc-launcher-toolbar"', generated)
            self.assertIn('import OcrPopover from "~/components/Workshop/OcrPopover.vue";', generated)
            component = (ROOT / "homebox-ui/overlay/components/Workshop/OcrPopover.vue").read_text()
            self.assertIn('from "~/lib/local-ocr"', component)
            self.assertIn('<Teleport defer :to="props.launcherTarget">', component)
            self.assertIn(':aria-pressed="enabled"', component)
            self.assertIn('Enable text capture', component)
            self.assertIn('Text capture {{ enabled ? "on" : "off" }}', component)
            self.assertIn('Text capture <span class="text-xs font-normal text-muted-foreground"', component)
            self.assertIn('v-if="enabled && !open"', component)
            self.assertIn('@click="toggleEnabled"', component)
            self.assertIn('@click="show"', component)
            body_portal = component.index('<Teleport to="body">')
            self.assertGreater(component.index('<section', body_portal), body_portal)
            self.assertIn('class="relative flex aspect-[4/3]', component)
            self.assertIn('isOcrCaptureCurrent(generation, cameraGeneration', component)
            self.assertIn('isOcrScanCurrent(generation, scanGeneration', component)
            self.assertIn('function cancelPendingScan()', component)
            self.assertIn('function close() { stopCamera(); cancelPendingScan();', component)
            self.assertIn('function cancelPendingCopy()', component)
            self.assertIn('isOcrScanCurrent(generation, copyGeneration', component)
            self.assertIn('tabindex="0"', component)
            self.assertIn('@keydown="moveByKeyboard"', component)
            self.assertIn('window.addEventListener("resize", clampPosition)', component)

    def test_prepare_api_test_rewrite_is_idempotent_when_first_fixture_is_already_patched(self):
        source = '''    const { displayId: omittedItemDisplayID, shortCode: omittedItemShortCode, ...itemForUpdate } = item;
    void omittedItemDisplayID;
    void omittedItemShortCode;
    const itemUpdate = {
      ...itemForUpdate,
      entityTypeId: item.entityType?.id || "",
      parentId: item.parent?.id || null,
    };
    const child1ItemUpdate = {
      ...child1Item,
      entityTypeId: child1Item.entityType?.id || "",
      parentId: parent.id,
    };
    const child2ItemUpdate = {
      ...child2Item,
      entityTypeId: child2Item.entityType?.id || "",
      parentId: parent.id,
    };
    const itemUpdate = {
      ...parent,
      entityTypeId: parent.entityType?.id || "",
      parentId: parentLocation.id,
    };
'''
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            previous_build = BUILDER.BUILD
            BUILDER.BUILD = pathlib.Path(directory)
            target = BUILDER.BUILD / "lib/api/__test__/user/items.test.ts"
            target.parent.mkdir(parents=True)
            target.write_text(source)
            try:
                BUILDER.strip_item_response_short_codes_from_update_tests()
            finally:
                BUILDER.BUILD = previous_build
            self.assertIn("...itemForUpdate", target.read_text())
            self.assertIn("...child1ForUpdate", target.read_text())

    def test_generated_location_selector_preserves_hierarchy_and_parent_filtering(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            test_root = pathlib.Path(directory)
            with isolated_builder_prepare(
                test_root / "homebox-ui-build",
                test_root / "homebox-materializer-work",
            ):
                BUILDER.prepare()

            selector = (pathlib.Path(directory) / "homebox-ui-build/components/Location/Selector.vue").read_text()
            helper = (pathlib.Path(directory) / "homebox-ui-build/lib/location-selector-tree.js").read_text()
            self.assertIn("v-for=\"location in visibleLocations\"", selector)
            self.assertIn("@click.stop.prevent=\"toggleExpanded(location.id)\"", selector)
            self.assertIn("paddingLeft: `${location.depth}rem`", selector)
            self.assertIn('from "~~/lib/location-selector-tree"', selector)
            self.assertIn("buildLocationTree(rows.value", selector)
            self.assertIn("getVisibleLocationTree(", selector)
            self.assertIn("excludeIds?: string[]", selector)
            self.assertIn("currentLocation?: EntitySummary", selector)
            self.assertIn("isLocation of [true, false]", selector)
            self.assertIn("fuzzysort.go(search.value", selector)
            self.assertIn("function selectLocation(location: EntitySummary)", selector)
            self.assertIn("export function buildLocationTree", helper)
            self.assertIn("excludeIds", helper)
            self.assertIn("options.currentLocation.id", helper)
            self.assertIn("if (row.archived) return false", helper)
            self.assertIn("excluded.has(current.id) || seen.has(current.id)", helper)
            self.assertIn("export function getLocationLabel", helper)

    def test_prepare_accepts_barcode_aware_create_entity_dialog_type(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            test_root = pathlib.Path(directory)
            with isolated_builder_prepare(
                test_root / "homebox-ui-build",
                test_root / "homebox-materializer-work",
            ):
                BUILDER.prepare()

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
            self.assertNotIn("<ItemSelector", create_modal)
            self.assertIn('<div class="flex items-end gap-2">\n        <FormTextField', create_modal)

            nuxt_config = (pathlib.Path(directory) / "homebox-ui-build/nuxt.config.ts").read_text()
            self.assertEqual(nuxt_config.count("  modules: ["), 1)
            self.assertLess(nuxt_config.index('"shadcn-nuxt"'), nuxt_config.index('(_options, nuxt) =>'))
            self.assertIn('nuxt.hook("components:dirs"', nuxt_config)
            self.assertTrue((pathlib.Path(directory) / "homebox-ui-build/components/ui/button/index.ts").exists())

            package = json.loads((pathlib.Path(directory) / "homebox-ui-build/package.json").read_text())
            self.assertNotIn("pnpm", package)
            workspace_config = (pathlib.Path(directory) / "homebox-ui-build/pnpm-workspace.yaml").read_text()
            self.assertIn("overrides:", workspace_config)
            self.assertIn("'@vue/runtime-core': 3.5.20", workspace_config)

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
        self.assertIn("frontend command failed with exit code 7", stderr.getvalue().lower())


if __name__ == "__main__":
    unittest.main()
