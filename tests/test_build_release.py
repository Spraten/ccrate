import importlib.util
import hashlib
import json
import shutil
import stat
import sys
import tarfile
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_release", ROOT / "deploy/build-release.py")
build_release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_release)


class BuildReleaseTests(unittest.TestCase):
    def setUp(self):
        temp_root = ROOT / "work/test-build-release"
        temp_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temp_root)
        self.root = Path(self.temp.name) / "source"
        self.cache = Path(self.temp.name) / "cache"
        self.toolchain = Path(self.temp.name) / "toolchain"
        for path, content in {
            "deploy/build-homebox-backend.py": "backend builder v1",
            "deploy/build-homebox-ui.py": "frontend builder v1",
            "deploy/build-label-ui.py": "labels builder v1",
            "homebox-backend/overlay.go": "native overlay v1",
            "upstream/homebox/PIN": "homebox-commit-1",
            "upstream/homebox/backend/main.go": "backend source v1",
            "upstream/homebox/frontend/app.vue": "frontend source v1",
            "homebox-ui/overlay/bridge.ts": "kiosk bridge v1",
            "homebox-ui/pnpm-lock.yaml": "frontend lock v1",
            "homebox-ui/upstream-typecheck.json": "{}",
            "kiosk/member-avatar.js": "avatar bridge v1",
            "kiosk/branding/logo.svg": "branding v1",
            "label-ui/vendor/print-design-pro/src/index.ts": "vendor v1",
            "label-ui/vendor/print-design-pro/LICENSE": "MIT",
            "label-ui/src/app.ts": "label source v1",
            "label-ui/public/fonts/font.ttf": "font v1",
            "label-ui/public/licenses/LICENSE.txt": "font license v1",
            "label-ui/patches/0001.patch": "patch v1",
            "label-ui/pnpm-lock.yaml": "label lock v1",
            "label-ui/package.json": "{}",
            "label-ui/vite.config.ts": "vite config v1",
            "label-ui/editor.html": "editor shell v1",
            "label-ui/render.html": "render shell v1",
        }.items():
            file = self.root / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(content)
        self.tools = {"go": "go1.26.0", "target": "linux/arm64", "node": "v24.21.0", "pnpm": "10.28.0"}
        self.calls = []

    def tearDown(self):
        self.temp.cleanup()

    def test_candidate_verification_scopes_receipt_to_builder_bundle_and_updater_checks(self):
        commands = build_release.verification_commands(sys.executable)
        self.assertEqual(commands, [[
            sys.executable, "-m", "unittest", "tests.test_build_release",
            "tests.test_update_ccrate",
            "tests.test_release_bundle.ReleaseBundleTests.test_format2_backup_restores_selected_release",
            "tests.test_release_bundle.ReleaseBundleTests.test_production_backup_restores_sealed_selection_and_receipt_binding",
            "-v",
        ]])

    def test_restored_selector_target_is_relative_to_selector_directory(self):
        import importlib.util
        import os
        fcntl = types.ModuleType("fcntl")
        fcntl.LOCK_EX, fcntl.LOCK_UN = 1, 2
        fcntl.flock = lambda *_args, **_kwargs: None
        restore_path = ROOT / "deploy/restore-cold-backup.py"
        spec = importlib.util.spec_from_file_location("restore_cold_backup_test", restore_path)
        restore = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"fcntl": fcntl}):
            spec.loader.exec_module(restore)
        root = Path(self.temp.name) / "restore-root"
        selected = root / "work/releases/previous"
        selected.mkdir(parents=True)
        targets = []
        with patch.object(Path, "symlink_to", side_effect=lambda target, **kwargs: targets.append(target)), \
             patch.object(restore.os, "replace") as replace:
            restore._restore_selector(root, selected)
        self.assertEqual([Path(target) for target in targets], [Path("releases/previous")])
        replace.assert_called_once()

    def run_builder(self, component, *, source_root, toolchain_root, output_path):
        self.calls.append(component)
        output_path.mkdir(parents=True, exist_ok=True)
        if component == "backend":
            # Minimal ELF64 little-endian AArch64 header; no Go/Docker runner is needed here.
            artifact = bytearray(64)
            artifact[:6] = b"\x7fELF\x02\x01"
            artifact[18:20] = b"\xb7\x00"
            (output_path / "homebox").write_bytes(artifact)
            return {"target": "linux/arm64", "frontend_mode": "external"}
        (output_path / "index.html").write_text(component)
        return {"component": component}

    def build_all(self):
        return {
            name: build_release.build_component(name, source_root=self.root,
                toolchain_root=self.toolchain, cache_root=self.cache)
            for name in ("backend", "frontend", "labels")
        }

    def test_frontend_edit_does_not_invalidate_backend_or_labels(self):
        with patch.object(build_release, "_invoke_builder", side_effect=self.run_builder):
            first = self.build_all()
            self.assertEqual(self.calls, ["backend", "frontend", "labels"])
            self.calls.clear()
            (self.root / "homebox-ui/overlay/bridge.ts").write_text("frontend changed")
            second = self.build_all()
        self.assertEqual(first["backend"]["fingerprint"], second["backend"]["fingerprint"])
        self.assertEqual(first["labels"]["fingerprint"], second["labels"]["fingerprint"])
        self.assertNotEqual(first["frontend"]["fingerprint"], second["frontend"]["fingerprint"])
        self.assertEqual(self.calls, ["frontend"])
        self.assertTrue(second["backend"]["cache_hit"])
        self.assertTrue(second["labels"]["cache_hit"])

    def test_backend_edit_invalidates_backend(self):
        with patch.object(build_release, "_invoke_builder", side_effect=self.run_builder):
            first = build_release.build_component("backend", source_root=self.root,
                toolchain_root=self.toolchain, cache_root=self.cache)
            (self.root / "homebox-backend/overlay.go").write_text("backend changed")
            second = build_release.build_component("backend", source_root=self.root,
                toolchain_root=self.toolchain, cache_root=self.cache)
        self.assertNotEqual(first["fingerprint"], second["fingerprint"])
        self.assertEqual(self.calls, ["backend", "backend"])

    def test_toolchain_and_lock_changes_invalidate_cache(self):
        with patch.object(build_release, "_invoke_builder", side_effect=self.run_builder):
            first = build_release.build_component("frontend", source_root=self.root,
                toolchain_root=self.toolchain, cache_root=self.cache, tools=self.tools)
            self.tools["node"] = "v24.22.0"
            second = build_release.build_component("frontend", source_root=self.root,
                toolchain_root=self.toolchain, cache_root=self.cache, tools=self.tools)
            (self.root / "homebox-ui/pnpm-lock.yaml").write_text("changed lock")
            third = build_release.build_component("frontend", source_root=self.root,
                toolchain_root=self.toolchain, cache_root=self.cache, tools=self.tools)
        self.assertEqual(len({first["fingerprint"], second["fingerprint"], third["fingerprint"]}), 3)
        self.assertEqual(self.calls, ["frontend", "frontend", "frontend"])

    def test_corrupt_cache_is_rebuilt(self):
        with patch.object(build_release, "_invoke_builder", side_effect=self.run_builder):
            built = build_release.build_component("labels", source_root=self.root,
                toolchain_root=self.toolchain, cache_root=self.cache)
            artifact = Path(built["output_path"]) / "index.html"
            artifact.write_text("corrupt")
            rebuilt = build_release.build_component("labels", source_root=self.root,
                toolchain_root=self.toolchain, cache_root=self.cache)
        self.assertEqual(self.calls, ["labels", "labels"])
        self.assertFalse(rebuilt["cache_hit"])
        self.assertEqual((Path(rebuilt["output_path"]) / "index.html").read_text(), "labels")

    def test_backend_artifact_is_arm64_and_external_mode_needs_no_current_frontend(self):
        with patch.object(build_release, "_invoke_builder", side_effect=self.run_builder):
            result = build_release.build_component("backend", source_root=self.root,
                toolchain_root=self.toolchain, cache_root=self.cache)
        artifact = Path(result["output_path"]) / "homebox"
        raw = artifact.read_bytes()
        self.assertEqual(raw[:6], b"\x7fELF\x02\x01")
        self.assertEqual(int.from_bytes(raw[18:20], "little"), 183)
        self.assertEqual(result["outputs"]["homebox"]["size"], len(raw))
        self.assertEqual(set(result["outputs"]["homebox"]), {"sha256", "size", "mode"})
        receipt = result["build_receipt"]
        self.assertEqual(receipt["frontend_mode"], "external")
        self.assertEqual(self.calls, ["backend"])

    def test_release_backend_invokes_external_arm64_builder_without_frontend_tree(self):
        output = Path(self.temp.name) / "direct-backend-output"
        output.mkdir()
        observed = {}

        def fake_run(command, *, cwd, env, check):
            observed.update(command=command, env=env)
            binary = bytearray(64)
            binary[:6] = b"\x7fELF\x02\x01"
            binary[18:20] = b"\xb7\x00"
            destination = Path(command[command.index("--output") + 1])
            (destination / "homebox").write_bytes(binary)

        with patch.object(build_release.subprocess, "run", side_effect=fake_run):
            build_release._invoke_builder("backend", source_root=self.root,
                toolchain_root=self.toolchain, output_path=output)
        self.assertIn("--external-frontend", observed["command"])
        self.assertEqual(observed["env"]["CCRATE_GOOS"], "linux")
        self.assertEqual(observed["env"]["CCRATE_GOARCH"], "arm64")
        self.assertFalse((self.root / "work/homebox-ui-current").exists())
        self.assertEqual(int.from_bytes((output / "homebox").read_bytes()[18:20], "little"), 183)

    def _release_fixture(self):
        source = Path(self.temp.name) / "release-source"
        source.mkdir()
        for directory in ("ops", "kiosk"):
            shutil.copytree(ROOT / directory, source / directory)
        deploy = source / "deploy"
        deploy.mkdir()
        names = {"kiosk-server.py", "workshop-gateway.py", "run-homebox.py",
                 "homebox-native.service", "homebox-companion.service",
                 "homebox-workshop-gateway.service", "run-release.py", "release_bundle.py"}
        for name in names:
            shutil.copy2(ROOT / "deploy" / name, deploy / name)
        starter = source / "label-ui/src/starter-documents.json"
        starter.parent.mkdir(parents=True)
        starter.write_text("{}\n")
        label_build = source / "work/label-ui-build"
        label_build.mkdir(parents=True)
        (label_build / "render.html").write_text("renderer")
        (label_build / "manifest.json").write_text('{"runtime_assets":{}}\n')
        frontend = Path(self.temp.name) / "frontend-output"
        frontend.mkdir()
        (frontend / "index.html").write_text("<html>release</html>")
        labels = Path(self.temp.name) / "label-output"
        shutil.copytree(label_build, labels)
        backend = Path(self.temp.name) / "backend-output"
        backend.mkdir()
        raw = bytearray(64)
        raw[:6] = b"\x7fELF\x02\x01"
        raw[18:20] = b"\xb7\x00"
        binary = backend / "homebox"
        binary.write_bytes(raw)
        binary.chmod(0o755)
        components = {}
        for name, path in (("backend", backend), ("frontend", frontend), ("labels", labels)):
            components[name] = {"fingerprint": hashlib.sha256(name.encode()).hexdigest(),
                                "output_path": str(path), "outputs": build_release._outputs(path),
                                "build_receipt": {"component": name}, "tools": {}, "cache_hit": False}
        return source, components

    def _verification_for(self, source, artifacts):
        fcntl_stub = types.ModuleType("fcntl")
        fcntl_stub.LOCK_EX, fcntl_stub.LOCK_UN = 1, 2
        fcntl_stub.flock = lambda *_args: None
        with patch.dict(sys.modules, {"fcntl": fcntl_stub}):
            sys.path.insert(0, str(ROOT / "deploy"))
            try:
                import release_bundle
                runtime = release_bundle._runtime_files(source, release_bundle.LAUNCHER_DEPLOY_FILES)
            finally:
                sys.path.pop(0)
                sys.modules.pop("release_bundle", None)
        entries = {dest.as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path, dest in runtime}
        modes = {dest.as_posix(): stat.S_IMODE(path.stat().st_mode) for path, dest in runtime}
        public = {name: {"sha256": row["sha256"], "size": row["size"]}
                  for name, row in build_release._manifest_files(artifacts["public"]).items()}
        labels = {name: {"sha256": row["sha256"], "size": row["size"]}
                  for name, row in build_release._manifest_files(artifacts["labels"]).items()}
        native = hashlib.sha256(Path(artifacts["binary"]).read_bytes()).hexdigest()
        source_digest = build_release._json_hash({"files": entries, "modes": modes})
        closure = build_release._json_hash({
            "runtime_files": entries, "runtime_modes": modes, "public_files": public,
            "label_files": labels,
            "label_source_sha256": hashlib.sha256((source / "label-ui/src/starter-documents.json").read_bytes()).hexdigest(),
            "native_sha256": native,
        })
        return {"source_manifest_digest": source_digest, "source_entries": entries,
                "source_modes": modes, "public_files": public, "label_files": labels,
                "native_sha256": native, "closure_sha256": closure,
                "release_metadata": artifacts.get("release_metadata"),
                "verification": {"exit_code": 0, "tests": 1, "commands": []}}

    def _verified_package(self, *, private=False, mutate_after_capture=False):
        source, components = self._release_fixture()
        commit, pin = "a" * 40, "b" * 40
        metadata = {"format": 1, "application": "ccrate", "commit": commit,
                    "upstream_pin": pin, "built_at": "2026-10-13T00:00:00Z"}
        public = Path(self.temp.name) / "captured-public"
        shutil.copytree(components["frontend"]["output_path"], public)
        (public / "ccrate-release.json").write_text(json.dumps(metadata) + "\n")
        initial = {"public": public, "labels": Path(components["labels"]["output_path"]),
                   "binary": Path(components["backend"]["output_path"]) / "homebox",
                   "release_metadata": metadata}
        verification = self._verification_for(source, initial)
        sentinel = source / "private-key.pem"
        if private:
            sentinel.write_text("PRIVATE-SENTINEL-DO-NOT-PUBLISH")
            verification = self._verification_for(source, initial)
        if mutate_after_capture:
            (source / "ops/desktop_api.py").write_text("mutated after verification\n")
        output = Path(self.temp.name) / "release-output"
        output.parent.mkdir(parents=True, exist_ok=True)
        fcntl_stub = types.ModuleType("fcntl")
        fcntl_stub.LOCK_EX, fcntl_stub.LOCK_UN = 1, 2
        fcntl_stub.flock = lambda *_args: None
        with patch.dict(sys.modules, {"fcntl": fcntl_stub}), \
             patch.object(build_release, "_source_revision", return_value=(commit, pin)), \
             patch.object(build_release, "capture_verification",
                          side_effect=lambda root, artifacts: self._verification_for(root, artifacts)):
            descriptor = build_release.package_release(source, components, verification, output)
        return output, descriptor

    def test_failed_or_empty_verification_cannot_publish(self):
        source, components = self._release_fixture()
        output = Path(self.temp.name) / "failed-output"
        for receipt in ({}, {"verification": {"exit_code": 1, "tests": 3}},
                        {"verification": {"exit_code": 0, "tests": 0}}):
            with self.subTest(receipt=receipt), self.assertRaises(RuntimeError):
                build_release.package_release(source, components, receipt, output)
        self.assertFalse(output.exists())

    def test_package_binds_actual_source_and_artifacts(self):
        source, components = self._release_fixture()
        commit, pin = "a" * 40, "b" * 40
        metadata = {"format": 1, "application": "ccrate", "commit": commit,
                    "upstream_pin": pin, "built_at": "2026-10-13T00:00:00Z"}
        public = Path(self.temp.name) / "captured-public"
        shutil.copytree(components["frontend"]["output_path"], public)
        (public / "ccrate-release.json").write_text(json.dumps(metadata) + "\n")
        verification = self._verification_for(source, {
            "public": public, "labels": Path(components["labels"]["output_path"]),
            "binary": Path(components["backend"]["output_path"]) / "homebox"})
        (source / "ops/desktop_api.py").write_text("changed source\n")
        output = Path(self.temp.name) / "mutated-output"
        fcntl_stub = types.ModuleType("fcntl")
        fcntl_stub.LOCK_EX, fcntl_stub.LOCK_UN = 1, 2
        fcntl_stub.flock = lambda *_args: None
        with patch.dict(sys.modules, {"fcntl": fcntl_stub}), \
             patch.object(build_release, "_source_revision", return_value=(commit, pin)), \
             self.assertRaisesRegex(RuntimeError, "does not bind the current runtime source"):
            build_release.package_release(source, components, verification, output)
        self.assertFalse(output.exists())

    def test_package_refuses_changed_cached_label_bytes(self):
        source, components = self._release_fixture()
        label_output = Path(components["labels"]["output_path"])
        (label_output / "render.html").write_text("changed after component verification")
        output = Path(self.temp.name) / "changed-cache-output"
        with self.assertRaisesRegex(RuntimeError, "changed after build or cache verification"):
            build_release.package_release(source, components,
                {"verification": {"exit_code": 0, "tests": 1}}, output)
        self.assertFalse(output.exists())

    @unittest.skipIf(sys.platform == "win32", "release execute-mode validation requires POSIX mode bits")
    def test_package_excludes_private_inputs(self):
        output, descriptor = self._verified_package(private=True)
        with tarfile.open(output / descriptor["archive"], "r:gz") as package:
            names = package.getnames()
            self.assertTrue(names and all(name == "candidate" or name.startswith("candidate/") for name in names))
            self.assertNotIn("candidate/private-key.pem", names)
        for receipt in ("build-receipt.json", "test-receipt.json"):
            self.assertNotIn("PRIVATE-SENTINEL-DO-NOT-PUBLISH", (output / receipt).read_text())

    @unittest.skipIf(sys.platform == "win32", "release execute-mode validation requires POSIX mode bits")
    def test_release_descriptor_matches_archive(self):
        output, descriptor = self._verified_package()
        archive = output / descriptor["archive"]
        self.assertEqual(descriptor["format"], 1)
        self.assertEqual(descriptor["application"], "ccrate")
        self.assertEqual(descriptor["architecture"], "linux-arm64")
        self.assertEqual(descriptor["commit"], "a" * 40)
        self.assertEqual(descriptor["upstream_pin"], "b" * 40)
        self.assertEqual(descriptor["compressed_bytes"], archive.stat().st_size)
        self.assertEqual(descriptor["sha256"], hashlib.sha256(archive.read_bytes()).hexdigest())
        self.assertEqual(descriptor["manifest_sha256"], hashlib.sha256((output / "candidate/manifest.json").read_bytes()).hexdigest())
        self.assertEqual(json.loads((output / "release.json").read_text()), descriptor)
        with tarfile.open(archive, "r:gz") as package:
            members = package.getmembers()
            self.assertEqual(descriptor["expanded_bytes"], sum(item.size for item in members if item.isfile()))
            self.assertTrue(all(item.name == "candidate" or item.name.startswith("candidate/") for item in members))
            manifest = json.load(package.extractfile("candidate/manifest.json"))
            release_metadata = json.load(package.extractfile("candidate/public/ccrate-release.json"))
        self.assertEqual(manifest["format"], 2)
        self.assertEqual(release_metadata["commit"], descriptor["commit"])

if __name__ == "__main__":
    unittest.main()
