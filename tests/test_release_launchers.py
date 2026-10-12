import hashlib
import importlib.util
import json
import os
import runpy
import socket
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy"))
from release_bundle import BundleError, release_command, stage_bundle


ROOT = Path(__file__).resolve().parents[1]
DEPLOY_FILES = {
    "kiosk-server.py", "workshop-gateway.py", "run-homebox.py",
    "homebox-native.service", "homebox-companion.service",
    "homebox-workshop-gateway.service", "run-release.py", "release_bundle.py",
}
KIOSK_EXTENSIONS = {".py", ".html", ".js", ".css", ".svg", ".png", ".ico",
                    ".jpg", ".jpeg", ".webmanifest", ".json", ".woff", ".woff2"}


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def canonical_hash(value):
    return sha_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def write(root, name, data, mode=0o644):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(mode)
    return path


class ReleaseLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.launcher_source = ROOT / "deploy/run-release.py"
        self.bundle_helper_source = ROOT / "deploy/release_bundle.py"

    def source_tree(self, name, marker):
        source = self.root / f"source-{name}"
        public = self.root / f"public-{name}"
        source.mkdir()
        public.mkdir()
        write(public, "index.html", f"public {marker}".encode())
        for module in ("desktop_api", "item_notes", "label_layouts", "label_render", "network_access"):
            write(source, f"ops/{module}.py", f"MARKER = {marker!r}\n".encode())
        write(source, "ops/labels.py", (ROOT / "ops/labels.py").read_bytes())
        write(source, "ops/ledger.py", b"class Conflict(Exception): pass\ndef uuid(value): return value\n")
        write(source, "ops/label_layouts.py", (ROOT / "ops/label_layouts.py").read_bytes())
        write(source, "ops/label_render.py", (ROOT / "ops/label_render.py").read_bytes())
        write(source, "ops/system_status.py", (ROOT / "ops/system_status.py").read_bytes())
        write(source, "kiosk/index.html", f"terminal {marker}".encode())
        write(source, "kiosk/scan_codes.py", f"MARKER = {marker!r}\n".encode())
        write(source, "kiosk/workshop-ui.js", f"// {marker}\n".encode())
        for rel in DEPLOY_FILES - {"run-release.py", "release_bundle.py"}:
            original = ROOT / "deploy" / rel
            write(source, f"deploy/{rel}", original.read_bytes())
        write(source, "deploy/run-release.py", self.launcher_source.read_bytes())
        write(source, "deploy/release_bundle.py", self.bundle_helper_source.read_bytes())
        for service in ("homebox-native.service", "homebox-companion.service", "homebox-workshop-gateway.service"):
            self.assertIn("application-current/deploy/run-release.py", (source / "deploy" / service).read_text())
        label = source / "work/label-ui-build"
        write(label, "render.html", f"renderer {marker}".encode())
        write(label, "fonts/DejaVuSans.ttf", b"synthetic font")
        runtime_assets = {"render.html": sha_bytes((label / "render.html").read_bytes()),
                          "fonts/DejaVuSans.ttf": sha_bytes((label / "fonts/DejaVuSans.ttf").read_bytes())}
        write(label, "manifest.json", json.dumps({"runtime_assets": runtime_assets}).encode())
        starter_documents = {}
        for profile in ("supvan", "letter"):
            for layout in ("left", "top", "compact"):
                width, height = (40, 28) if profile == "supvan" else (60, 40)
                starter_documents[f"starter:{profile}:{layout}"] = {
                    "schemaVersion": 1, "id": f"starter:{profile}:{layout}", "name": f"{profile}-{layout}",
                    "page": {"widthMm": width, "heightMm": height, "orientation": "landscape",
                             "marginTopMm": 1, "marginRightMm": 1, "marginBottomMm": 1, "marginLeftMm": 1},
                    "elements": [{"id": "item-qr", "name": "Item QR", "type": "qr", "xMm": 1,
                                  "yMm": 1, "widthMm": 18, "heightMm": 18, "rotation": 0,
                                  "locked": True, "visible": True, "content": "{{item_path}}",
                                  "ecLevel": "M", "color": "#000000", "backgroundColor": "#ffffff"}],
                    "guides": [], "variables": {}}
        write(source, "label-ui/src/starter-documents.json", json.dumps(starter_documents).encode())
        binary = self.root / f"native-{name}"
        write(self.root, binary.name, f"native {marker}".encode(), 0o755)
        return source, public, binary

    def provenance(self, source, public, binary):
        source_files = {}
        source_modes = {}
        for area in ("ops", "kiosk"):
            for path in sorted((source / area).rglob("*")):
                rel = path.relative_to(source).as_posix()
                if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                    if area != "ops" or path.suffix == ".py":
                        source_files[rel] = sha_bytes(path.read_bytes())
                        source_modes[rel] = path.stat().st_mode & 0o777
        for name in DEPLOY_FILES:
            path = source / "deploy" / name
            source_files[path.relative_to(source).as_posix()] = sha_bytes(path.read_bytes())
            source_modes[path.relative_to(source).as_posix()] = path.stat().st_mode & 0o777
        public_files = {path.relative_to(public).as_posix(): {"sha256": sha_bytes(path.read_bytes()), "size": path.stat().st_size}
                        for path in sorted(public.rglob("*")) if path.is_file()}
        label_root = source / "work/label-ui-build"
        label_files = {path.relative_to(label_root).as_posix(): {"sha256": sha_bytes(path.read_bytes()), "size": path.stat().st_size}
                       for path in sorted(label_root.rglob("*")) if path.is_file()}
        source_digest, static_digest = "d" * 64, "c" * 64
        build = {"source_manifest_digest": source_digest, "static_manifest_sha256": static_digest,
                 "execution_scope": "fixture-only"}
        tests = {"source_manifest_digest": source_digest,
                 "source_entries": {name: {"sha256": source_files[name], "mode": source_modes[name]}
                                    for name in source_files},
                 "verification": {"exit_code": 0, "tests": 1},
                 "execution_scope": "fixture-only"}
        build_raw = json.dumps(build, sort_keys=True, indent=2)
        tests_raw = json.dumps(tests, sort_keys=True, indent=2)
        return {
            "source_manifest_digest": source_digest,
            "static_manifest_sha256": static_digest,
            "build_receipt": build,
            "build_receipt_sha256": sha_bytes(build_raw.encode()),
            "build_receipt_raw": build_raw,
            "build_receipt_canonical_sha256": canonical_hash(build),
            "build_receipt_path": "fixture/build.json",
            "test_receipt": tests,
            "test_receipt_sha256": sha_bytes(tests_raw.encode()),
            "test_receipt_raw": tests_raw,
            "test_receipt_canonical_sha256": canonical_hash(tests),
            "test_receipt_path": "fixture/tests.json",
            "native_sha256": sha_bytes(binary.read_bytes()),
            "runtime_files": source_files,
            "runtime_modes": source_modes,
            "public_files": public_files,
            "label_files": label_files,
            "label_source_sha256": sha_bytes((source / "label-ui/src/starter-documents.json").read_bytes()),
        }

    def make_bundle(self, name, marker):
        source, public, binary = self.source_tree(name, marker)
        release = self.root / "releases" / name
        release.parent.mkdir(exist_ok=True)
        provenance = self.provenance(source, public, binary)
        manifest = stage_bundle(release, binary=binary, public=public, source=source, provenance=provenance)
        self.assertEqual(manifest["format"], 2)
        return source, release

    def test_format2_stage_rejects_missing_label_starters(self):
        source, public, binary = self.source_tree("no-starters", "fixture")
        provenance = self.provenance(source, public, binary)
        (source / "label-ui/src/starter-documents.json").unlink()
        destination = self.root / "incomplete-release"
        with self.assertRaisesRegex(BundleError, "label starter documents"):
            stage_bundle(destination, binary=binary, public=public, source=source, provenance=provenance)
        self.assertFalse(destination.exists())

    def select(self, runtime_root, release):
        selector = runtime_root / "work/application-current"
        selector.parent.mkdir(parents=True, exist_ok=True)
        if selector.is_symlink():
            selector.unlink()
        selector.symlink_to(release, target_is_directory=True)

    def run_packaged_launcher(self, release, runtime_root, component):
        calls = []
        launcher = release / "deploy/run-release.py"
        with patch.object(sys, "argv", [str(launcher), component]), \
             patch.dict(os.environ, {"WORKSHOP_ROOT": str(runtime_root)}, clear=False), \
             patch("os.execvpe", side_effect=lambda *args: calls.append(args)):
            runpy.run_path(str(launcher), run_name="__main__")
        self.assertEqual(len(calls), 1)
        return calls[0]

    def run_launcher_main_with_read_spy(self, release, runtime_root, watched, *, launcher_path=None):
        launcher_source = ROOT / "deploy/run-release.py"
        namespace = runpy.run_path(str(launcher_source), run_name="launcher_review_test")
        launcher_path = launcher_path or release / "deploy/run-release.py"
        physical_launcher = release.resolve() / "deploy/run-release.py"
        namespace["main"].__globals__["__file__"] = str(launcher_path)
        opened, executed = [], []
        original_open, original_resolve = os.open, Path.resolve
        def open_spy(path, *args, **kwargs):
            candidate = Path(path)
            if candidate in watched:
                opened.append(candidate)
            return original_open(path, *args, **kwargs)
        def resolve_spy(path, *args, **kwargs):
            if path.name == "run-release.py":
                return physical_launcher
            return original_resolve(path, *args, **kwargs)
        with patch.object(sys, "argv", [str(launcher_path), "gateway"]), \
             patch.dict(os.environ, {"WORKSHOP_ROOT": str(runtime_root)}, clear=False), \
             patch.object(os, "open", open_spy), patch.object(Path, "resolve", resolve_spy), \
             patch("os.execvpe", side_effect=lambda *args: executed.append(args)):
            with self.assertRaises(ValueError):
                namespace["main"]()
        self.assertEqual(executed, [])
        return opened

    def test_launchers_resolve_one_release_and_ignore_working_source(self):
        old_source, old_release = self.make_bundle("old", "old-source")
        new_source, new_release = self.make_bundle("new", "new-source")
        runtime_root = self.root / "runtime"
        self.select(runtime_root, old_release)
        old_command, old_env = release_command(runtime_root, "companion")
        self.assertEqual(old_env["WORKSHOP_CODE_ROOT"], str(old_release.resolve()))
        self.assertEqual(old_env["WORKSHOP_ROOT"], str(runtime_root))
        self.assertEqual(old_env["HOMEBOX_UI_ROOT"], str(old_release.resolve() / "public"))
        self.assertEqual(old_command[-1], str(old_release / "deploy/kiosk-server.py"))
        old_selection = (list(old_command), dict(old_env))
        self.select(runtime_root, new_release)
        self.assertEqual((old_command, old_env), old_selection)
        for component, entrypoint in (("native", "run-homebox.py"),
                                      ("companion", "kiosk-server.py"),
                                      ("gateway", "workshop-gateway.py")):
            command, env = release_command(runtime_root, component)
            self.assertEqual(command[-1], str(new_release / "deploy" / entrypoint))
            self.assertEqual(env["WORKSHOP_CODE_ROOT"], str(new_release.resolve()))
            self.assertEqual(env["WORKSHOP_ROOT"], str(runtime_root))
        for root in (old_source, new_source):
            for rel in ("ops/desktop_api.py", "kiosk/index.html", "deploy/kiosk-server.py",
                        "deploy/workshop-gateway.py", "deploy/run-release.py", "deploy/release_bundle.py"):
                path = root / rel
                if path.is_file():
                    path.chmod(0o644)
                    path.write_text("# mutated working tree\n")
        module_path = old_release / "ops/desktop_api.py"
        spec = importlib.util.spec_from_file_location("selected_desktop_api", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.MARKER, "old-source")
        self.assertEqual(Path(module.__file__).resolve(), module_path.resolve())
        self.assertEqual((old_release / "public/index.html").read_text(), "public old-source")
        self.assertEqual((old_release / "kiosk/index.html").read_text(), "terminal old-source")

    def test_fixture_process_mode_rejects_inherited_native_endpoint_before_package_access(self):
        cli = ROOT / "deploy/verify-release-rollback.py"
        result = subprocess.run(
            [sys.executable, str(cli), "--mode", "fixture-process",
             "--previous", str(self.root / "missing-o"),
             "--candidate", str(self.root / "missing-c"),
             "--fallback", str(self.root / "missing-f")],
            env={**os.environ, "HBOX_WEB_HOST": "192.0.2.55", "HBOX_WEB_PORT": "17745"},
            text=True, capture_output=True, timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("inherited HBOX endpoint configuration is refused", result.stderr)
        self.assertNotIn("missing-o", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_fixture_bundle_path_rejects_symlinked_ancestor(self):
        _, previous = self.make_bundle("symlink-parent-o", "o")
        _, candidate = self.make_bundle("symlink-parent-c", "c")
        _, fallback = self.make_bundle("symlink-parent-f", "f")
        alias = self.root / "bundle-alias"
        alias.symlink_to(self.root, target_is_directory=True)
        cli = ROOT / "deploy/verify-release-rollback.py"
        result = subprocess.run(
            [sys.executable, str(cli), "--previous", str(alias / previous.name),
             "--candidate", str(candidate), "--fallback", str(fallback)],
            env={key: value for key, value in os.environ.items()
                 if not key.startswith(("HBOX_", "WORKSHOP_", "HOMEBOX_WEB_"))},
            text=True, capture_output=True, timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("bundle path contains a symlink", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_fixture_process_mode_refuses_missing_named_fallback_receipt_before_setup(self):
        from tests.test_release_bundle import ReleaseBundleTests
        bundle_case = ReleaseBundleTests()
        bundle_case.setUp()
        self.addCleanup(bundle_case.doCleanups)
        _, previous, candidate, fallback, _ = bundle_case.selection_triple(
            previous_provenance=lambda: bundle_case.provenance(workshop_write_mode="disabled"))
        cli = ROOT / "deploy/verify-release-rollback.py"
        output_root = ROOT / "work/queue-coordinator"
        before = set(output_root.glob("whole-map-process-run-*") if output_root.exists() else ())
        result = subprocess.run(
            [sys.executable, str(cli), "--mode", "fixture-process",
             "--previous", str(previous), "--candidate", str(candidate), "--fallback", str(fallback),
             "--dependency-path", "/home/user/Desktop/inventory-system/program-files/runtime/hardware/python"],
            env={key: value for key, value in os.environ.items()
                 if not key.startswith(("HBOX_", "WORKSHOP_", "HOMEBOX_WEB_"))},
            text=True, capture_output=True, timeout=20,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("artifact-bound named fallback checks are missing or unpassed", result.stderr)
        self.assertIn("fallback_preserves_member_profile_loan_state", result.stderr)
        self.assertEqual(result.stdout, "")
        after = set(output_root.glob("whole-map-process-run-*") if output_root.exists() else ())
        self.assertEqual(after, before)

    def test_fixture_process_capability_preflight_precedes_run_setup(self):
        from tests.test_release_bundle import ReleaseBundleTests
        bundle_case = ReleaseBundleTests()
        bundle_case.setUp()
        self.addCleanup(bundle_case.doCleanups)
        _, previous, candidate, fallback, _ = bundle_case.selection_triple()
        namespace = runpy.run_path(str(ROOT / "deploy/verify-release-rollback.py"),
                                   run_name="fixture_preflight_test")
        api = namespace["_load_bundle_api"]()
        # Unit O has a v2 writer, which cannot stand in for the verifier's
        # required disabled-write previous capability.
        with self.assertRaisesRegex(BundleError, "disabled-O, v2-C"):
            namespace["_preflight_fixture_packages"]((previous, candidate, fallback), api)

    def _fixture_preflight_packages_with_passing_checks(self, bundle_case, *, previous_mode="disabled"):
        _, _, candidate, _, _ = bundle_case.selection_triple(
            previous_provenance=lambda: bundle_case.provenance(workshop_write_mode=previous_mode))
        policy = {
            "schema": 1, "evidence_scope": "fixture-only",
            "strategy": "candidate-code-with-captured-previous-public",
            "candidate_manifest_sha256": sha_bytes((candidate / "manifest.json").read_bytes()),
            "roomsv2_read_versions": [1, 2], "workshop_mutation_mode": "v2",
            "member_profile_loan_compatibility": "verified",
            "runtime_state_policy": "same-stores-no-restore", "physical_effect_policy": "never-replay",
        }
        provenance = bundle_case.provenance(workshop_write_mode="v2")
        names = __import__("release_bundle").FALLBACK_CHECKS
        provenance["test_receipt"]["fallback_checks"] = {name: "passed" for name in names}
        raw = json.dumps(provenance["test_receipt"], sort_keys=True, indent=2)
        provenance["test_receipt_raw"] = raw
        provenance["test_receipt_sha256"] = sha_bytes(raw.encode())
        provenance["test_receipt_canonical_sha256"] = canonical_hash(provenance["test_receipt"])
        fallback = bundle_case.root / "releases/fallback-with-checks"
        bundle_case.stage(fallback, provenance=provenance, fallback_policy=policy)
        previous = bundle_case.root / "releases/previous-disabled"
        bundle_case.stage(previous, provenance=bundle_case.provenance(workshop_write_mode=previous_mode))
        return previous, candidate, fallback

    def test_fixture_preflight_accepts_v2_fallback_in_both_receipt_directions(self):
        from tests.test_release_bundle import ReleaseBundleTests
        bundle_case = ReleaseBundleTests()
        bundle_case.setUp()
        self.addCleanup(bundle_case.doCleanups)
        previous, candidate, fallback = self._fixture_preflight_packages_with_passing_checks(bundle_case)
        namespace = runpy.run_path(str(ROOT / "deploy/verify-release-rollback.py"),
                                   run_name="fixture_v2_fallback_preflight_test")
        manifests, first, returning = namespace["_preflight_fixture_packages"](
            (previous, candidate, fallback), namespace["_load_bundle_api"]())
        self.assertEqual(manifests[2]["provenance"]["workshop_capability"]["write_mode"], "v2")
        self.assertEqual(first["previous_bundle_manifest_sha256"],
                         sha_bytes((previous / "manifest.json").read_bytes()))
        self.assertEqual(returning["previous_bundle_manifest_sha256"],
                         sha_bytes((fallback / "manifest.json").read_bytes()))

    def test_fixture_initial_o_must_still_disable_writes(self):
        from tests.test_release_bundle import ReleaseBundleTests
        bundle_case = ReleaseBundleTests()
        bundle_case.setUp()
        self.addCleanup(bundle_case.doCleanups)
        previous, candidate, fallback = self._fixture_preflight_packages_with_passing_checks(
            bundle_case, previous_mode="v2")
        namespace = runpy.run_path(str(ROOT / "deploy/verify-release-rollback.py"),
                                   run_name="fixture_v2_o_preflight_test")
        with self.assertRaisesRegex(BundleError, "disabled-O, v2-C"):
            namespace["_preflight_fixture_packages"](
                (previous, candidate, fallback), namespace["_load_bundle_api"]())

    def test_fixture_receipt_validation_failure_is_reported_without_name_error(self):
        from tests.test_release_bundle import ReleaseBundleTests
        bundle_case = ReleaseBundleTests()
        bundle_case.setUp()
        self.addCleanup(bundle_case.doCleanups)
        previous, candidate, fallback = self._fixture_preflight_packages_with_passing_checks(bundle_case)
        namespace = runpy.run_path(str(ROOT / "deploy/verify-release-rollback.py"),
                                   run_name="fixture_bound_bundle_error_test")
        api = list(namespace["_load_bundle_api"]())
        def reject_receipt(*_args):
            raise BundleError("deliberately invalid fallback receipt")
        api[7] = reject_receipt
        with self.assertRaisesRegex(namespace["FixtureRefusal"],
                                    "fixture fallback receipt preflight failed: deliberately invalid"):
            namespace["_fixture_receipt"](previous, candidate, fallback, tuple(api))

    def test_fixture_policy_validation_failure_is_reported_without_name_error(self):
        from tests.test_release_bundle import ReleaseBundleTests
        bundle_case = ReleaseBundleTests()
        bundle_case.setUp()
        self.addCleanup(bundle_case.doCleanups)
        previous, candidate, fallback = self._fixture_preflight_packages_with_passing_checks(bundle_case)
        namespace = runpy.run_path(str(ROOT / "deploy/verify-release-rollback.py"),
                                   run_name="fixture_bound_policy_error_test")
        api = list(namespace["_load_bundle_api"]())
        def reject_policy(*_args):
            raise BundleError("deliberately invalid fallback policy")
        api[6] = reject_policy
        with self.assertRaisesRegex(namespace["FixtureRefusal"],
                                    "fixture fallback policy preflight failed: deliberately invalid"):
            namespace["_fixture_receipt"](previous, candidate, fallback, tuple(api))

    def test_fixture_preflight_rejects_unbound_receipt_object(self):
        from tests.test_release_bundle import ReleaseBundleTests
        bundle_case = ReleaseBundleTests()
        bundle_case.setUp()
        self.addCleanup(bundle_case.doCleanups)
        package = bundle_case.root / "release"
        bundle_case.stage(package)
        manifest = json.loads(json.dumps(__import__("release_bundle").validate_bundle(package)))
        manifest["provenance"]["test_receipt"]["verification"]["tests"] += 1
        namespace = runpy.run_path(str(ROOT / "deploy/verify-release-rollback.py"),
                                   run_name="fixture_raw_receipt_test")
        with self.assertRaisesRegex(namespace["FixtureRefusal"], "content is not bound"):
            namespace["_require_receipt_bindings"](manifest)

    def test_fixture_companion_refuses_before_store_creation_without_owned_root(self):
        self._assert_fixture_entrypoint_preflight("kiosk-server.py", {
            "WORKSHOP_COMPANION_PORT": "0", "WORKSHOP_NATIVE_BASE": "http://127.0.0.1:40000"},
            "Fixture process refused before imports", "work/ops")

    def test_fixture_gateway_refuses_before_listener_without_owned_root(self):
        self._assert_fixture_entrypoint_preflight("workshop-gateway.py", {
            "WORKSHOP_PORT": "0", "WORKSHOP_NATIVE_PORT": "40000",
            "WORKSHOP_COMPANION_PORT": "40001", "HOMEBOX_UI_ROOT": ""},
            "Fixture gateway refused before project imports", "ready.json")

    def test_fixture_gateway_module_guard_runs_before_project_imports(self):
        with tempfile.TemporaryDirectory(prefix="gateway-import-guard-") as raw:
            root = Path(raw)
            marker = root / "network-access-imported"
            wrapper = root / "probe.py"
            gateway = ROOT / "deploy/workshop-gateway.py"
            wrapper.write_text(
                "import importlib.abc,pathlib,runpy,sys\n"
                f"marker=pathlib.Path({str(marker)!r})\n"
                "class Watch(importlib.abc.MetaPathFinder):\n"
                " def find_spec(self, fullname, path=None, target=None):\n"
                "  if fullname == 'network_access': marker.write_text('imported')\n"
                "sys.meta_path.insert(0,Watch())\n"
                f"runpy.run_path({str(gateway)!r},run_name='gateway_guard_test')\n")
            env = {key: value for key, value in os.environ.items()
                   if not key.startswith(("HBOX_", "WORKSHOP_", "HOMEBOX_WEB_"))}
            env.update({"WORKSHOP_FIXTURE_PROCESS": "1", "WORKSHOP_ROOT": str(root),
                        "WORKSHOP_FIXTURE_TOKEN": "untrusted", "WORKSHOP_BIND_HOST": "127.0.0.1",
                        "WORKSHOP_PORT": "0", "WORKSHOP_NATIVE_PORT": "40000",
                        "WORKSHOP_COMPANION_PORT": "40001",
                        "WORKSHOP_FIXTURE_READY_FILE": str(root / "ready.json")})
            result = subprocess.run([sys.executable, str(wrapper)], env=env,
                                    text=True, capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Fixture gateway refused before project imports", result.stderr)
            self.assertFalse(marker.exists())

    def test_fixture_kiosk_refuses_cached_gpio_module_before_store_creation(self):
        with tempfile.TemporaryDirectory(prefix="fixture-physical-module-") as raw:
            root = Path(raw)
            root.chmod(0o700)
            token = "fixture-token-" + "a" * 40
            marker = root / ".fixture-process-token"
            marker.write_text(token)
            marker.chmod(0o600)
            (root / "sitecustomize.py").write_text(
                "import sys,types\nsys.modules['gpio'] = types.ModuleType('gpio')\n")
            env = {key: value for key, value in os.environ.items()
                   if not key.startswith(("HBOX_", "WORKSHOP_", "HOMEBOX_WEB_"))}
            env.update({"WORKSHOP_FIXTURE_PROCESS": "1", "WORKSHOP_ROOT": str(root),
                        "WORKSHOP_FIXTURE_TOKEN": token, "WORKSHOP_BIND_HOST": "127.0.0.1",
                        "WORKSHOP_COMPANION_PORT": "0", "WORKSHOP_NATIVE_BASE": "http://127.0.0.1:40000",
                        "WORKSHOP_FIXTURE_READY_FILE": str(root / "work/ready.json"),
                        "PYTHONPATH": str(root)})
            result = subprocess.run([sys.executable, str(ROOT / "deploy/kiosk-server.py")],
                                    env=env, text=True, capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("cached physical modules", result.stderr)
            self.assertFalse((root / "work/ops").exists())
            self.assertEqual(result.stdout, "")

    def test_fixture_process_manager_stops_children_after_failure(self):
        import runpy
        from unittest.mock import patch
        namespace = runpy.run_path(str(ROOT / "deploy/verify-release-rollback.py"),
                                   run_name="fixture_cleanup_test")
        with tempfile.TemporaryDirectory(prefix="fixture-process-cleanup-") as raw:
            root = Path(raw)
            log_root = root / "logs"
            log_root.mkdir()
            with patch.dict(namespace["_PackagedProcesses"].__init__.__globals__,
                            {"_free_ports": lambda count: [40000, 40001, 40002]}):
                manager = namespace["_PackagedProcesses"](root / "runtime", "a" * 48,
                                                          root, log_root)
            child_log = (log_root / "child.log").open("wb")
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                     stdin=subprocess.DEVNULL, stdout=child_log,
                                     stderr=subprocess.STDOUT, start_new_session=True)
            manager.children["native"] = (child, child_log, log_root / "child.log")
            manager.stop_all()
            self.assertIsNotNone(child.poll())
            self.assertEqual(manager.children, {})

    def test_native_response_drop_proxy_refuses_unowned_native_listener(self):
        namespace = runpy.run_path(str(ROOT / "deploy/verify-release-rollback.py"),
                                   run_name="fixture_proxy_ownership_test")
        with tempfile.TemporaryDirectory(prefix="fixture-native-proxy-owner-") as raw:
            root = Path(raw)
            manager = object.__new__(namespace["_PackagedProcesses"])
            manager.children = {"native": (types.SimpleNamespace(pid=32123, poll=lambda: None), None, None)}
            manager.native_port = 40000
            manager.drop_next_note_response = False
            manager.dropped_note_response = None
            proxy = namespace["_FixtureNativeResponseDropProxy"](manager, manager.native_port)
            try:
                with patch.dict(namespace, {"_pid_owns_listener": lambda _pid, _port: False}):
                    with patch.object(namespace["urllib"].request, "urlopen") as upstream:
                        with socket.create_connection(("127.0.0.1", proxy.port), timeout=2) as client:
                            client.sendall(b"GET /api/v1/status HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
                            response = client.recv(1024)
                        self.assertIn(b"503", response)
                        upstream.assert_not_called()
            finally:
                proxy.server.shutdown()
                proxy.server.server_close()
                proxy.thread.join(timeout=2)

    def test_native_response_drop_proxy_is_closed_after_successful_manager_cleanup(self):
        namespace = runpy.run_path(str(ROOT / "deploy/verify-release-rollback.py"),
                                   run_name="fixture_proxy_cleanup_test")
        with tempfile.TemporaryDirectory(prefix="fixture-native-proxy-cleanup-") as raw:
            root = Path(raw)
            manager = object.__new__(namespace["_PackagedProcesses"])
            manager.children = {}
            manager.native_port = 40000
            manager.drop_next_note_response = False
            manager.dropped_note_response = None
            proxy = namespace["_FixtureNativeResponseDropProxy"](manager, manager.native_port)
            manager.native_proxy = proxy
            manager.stop_all(close_proxy=True)
            self.assertEqual(proxy.server.fileno(), -1)
            self.assertFalse(proxy.thread.is_alive())
            self.assertIsNone(manager.native_proxy)

    def test_native_response_drop_proxy_is_closed_when_child_cleanup_fails(self):
        namespace = runpy.run_path(str(ROOT / "deploy/verify-release-rollback.py"),
                                   run_name="fixture_proxy_failed_cleanup_test")
        class StuckChild:
            pid = 32124
            def poll(self): return None
            def terminate(self): raise OSError("fixture stop failed")
            def wait(self, timeout=None): raise subprocess.TimeoutExpired("fixture-child", timeout)
            def kill(self): raise OSError("fixture kill failed")
        with tempfile.TemporaryDirectory(prefix="fixture-native-proxy-failed-cleanup-") as raw:
            root = Path(raw)
            manager = object.__new__(namespace["_PackagedProcesses"])
            manager.native_port = 40000
            manager.drop_next_note_response = False
            manager.dropped_note_response = None
            proxy = namespace["_FixtureNativeResponseDropProxy"](manager, manager.native_port)
            manager.native_proxy = proxy
            log = (root / "native.log").open("wb")
            manager.children = {"native": (StuckChild(), log, root / "native.log")}
            with self.assertRaisesRegex(namespace["FixtureRefusal"], "fixture stop failed"):
                manager.stop_all(close_proxy=True)
            self.assertEqual(proxy.server.fileno(), -1)
            self.assertFalse(proxy.thread.is_alive())

    def test_fixture_native_shutdown_has_bounded_migration_safe_grace(self):
        import runpy
        namespace = runpy.run_path(str(ROOT / "deploy/verify-release-rollback.py"),
                                   run_name="fixture_native_shutdown_grace_test")
        class Child:
            pid = 43211
            def __init__(self): self.wait_timeouts = []
            def poll(self): return None if not self.wait_timeouts else 0
            def terminate(self): pass
            def wait(self, timeout=None):
                self.wait_timeouts.append(timeout)
                return 0
            def kill(self): raise AssertionError("native child should stop within its grace")
        with tempfile.TemporaryDirectory(prefix="fixture-native-shutdown-") as raw:
            root = Path(raw)
            child = Child()
            log = (root / "native.log").open("wb")
            manager = object.__new__(namespace["_PackagedProcesses"])
            manager.children = {"native": (child, log, root / "native.log")}
            manager.stop_all()
            self.assertEqual(child.wait_timeouts, [15])
            self.assertEqual(manager.children, {})

    def test_fixture_process_manager_attempts_all_children_after_stop_error(self):
        import runpy
        namespace = runpy.run_path(str(ROOT / "deploy/verify-release-rollback.py"),
                                   run_name="fixture_cleanup_independent_test")

        class Child:
            def __init__(self, fail=False):
                self.fail = fail
                self.terminated = False
                self.killed = False
            def poll(self):
                return 0 if self.terminated or self.killed else None
            def terminate(self):
                if self.fail:
                    raise OSError("fixture terminate error")
                self.terminated = True
            def wait(self, timeout=None):
                if not self.terminated and not self.killed:
                    raise subprocess.TimeoutExpired("fixture-child", timeout)
                return 0
            def kill(self):
                self.killed = True

        with tempfile.TemporaryDirectory(prefix="fixture-process-cleanup-all-") as raw:
            root = Path(raw)
            logs = []
            manager = object.__new__(namespace["_PackagedProcesses"])
            manager.children = {}
            manager.children["native"] = (Child(fail=True), open(root / "first.log", "wb"),
                                           root / "first.log")
            manager.children["companion"] = (Child(), open(root / "second.log", "wb"),
                                              root / "second.log")
            children = [entry[0] for entry in manager.children.values()]
            with self.assertRaisesRegex(namespace["FixtureRefusal"], "fixture terminate error"):
                manager.stop_all()
            self.assertTrue(all(child.poll() is not None for child in children))
            self.assertEqual(manager.children, {})

    def test_fixture_process_manager_retains_unresolved_child_for_retry(self):
        namespace = runpy.run_path(str(ROOT / "deploy/verify-release-rollback.py"),
                                   run_name="fixture_cleanup_retention_test")

        class StuckChild:
            pid = 43210
            def poll(self): return None
            def terminate(self): raise OSError("terminate denied")
            def wait(self, timeout=None): raise subprocess.TimeoutExpired("stuck", timeout)
            def kill(self): raise OSError("kill denied")

        with tempfile.TemporaryDirectory(prefix="fixture-stuck-child-") as raw:
            root = Path(raw)
            log = (root / "stuck.log").open("wb")
            child = StuckChild()
            manager = object.__new__(namespace["_PackagedProcesses"])
            manager.children = {"native": (child, log, root / "stuck.log")}
            with self.assertRaisesRegex(namespace["FixtureRefusal"], "remained alive"):
                manager.stop_all()
            self.assertIn("native", manager.children)

    def test_fixture_cli_returns_nonzero_when_cleanup_refusal_is_reported(self):
        namespace = runpy.run_path(str(ROOT / "deploy/verify-release-rollback.py"),
                                   run_name="fixture_cleanup_cli_test")
        with tempfile.TemporaryDirectory(prefix="fixture-cli-cleanup-") as raw:
            root = Path(raw)
            previous, candidate, fallback, dependency = (root / name for name in
                                                          ("o", "c", "f", "deps"))
            for path in (previous, candidate, fallback, dependency):
                path.mkdir()
            def report_then_refuse(*_args):
                raise namespace["FixtureRefusal"]("fixture cleanup failed; receipt recorded")
            with patch.dict(namespace["main"].__globals__, {"_run_fixture_process": report_then_refuse}):
                with patch("sys.stderr", new_callable=__import__("io").StringIO) as stderr:
                    with self.assertRaises(SystemExit) as exit_result:
                        namespace["main"](["--mode", "fixture-process", "--previous", str(previous),
                            "--candidate", str(candidate), "--fallback", str(fallback),
                            "--dependency-path", str(dependency)])
            self.assertEqual(exit_result.exception.code, 2)
            self.assertIn("fixture cleanup failed", stderr.getvalue())

    def test_fixture_runtime_cleanup_reports_actual_removal(self):
        import runpy
        namespace = runpy.run_path(str(ROOT / "deploy/verify-release-rollback.py"),
                                   run_name="fixture_runtime_cleanup_test")
        with tempfile.TemporaryDirectory(prefix="fixture-runtime-cleanup-") as raw:
            root = Path(raw) / "runtime"
            root.mkdir()
            errors = []
            removed = namespace["_remove_runtime_root"](root, errors)
            self.assertTrue(removed)
            self.assertFalse(root.exists())
            self.assertEqual(errors, [])
            root.mkdir()
            errors.clear()
            with patch("shutil.rmtree", side_effect=PermissionError("fixture removal denied")):
                removed = namespace["_remove_runtime_root"](root, errors)
            self.assertFalse(removed)
            self.assertTrue(root.exists())
            self.assertIn("fixture removal denied", errors[0])

    def test_fixture_cleanup_removes_sealed_copy_without_mutating_original_bundle(self):
        import runpy
        from tests.test_release_bundle import ReleaseBundleTests
        bundle_case = ReleaseBundleTests()
        bundle_case.setUp()
        self.addCleanup(bundle_case.doCleanups)
        original = bundle_case.root / "releases/sealed-original"
        bundle_case.stage(original)
        original_state = {}
        for path in [original, *original.rglob("*")]:
            rel = path.relative_to(original.parent).as_posix()
            if path.is_file():
                original_state[rel] = ("file", sha_bytes(path.read_bytes()), path.stat().st_mode & 0o777)
            else:
                original_state[rel] = ("dir", None, path.stat().st_mode & 0o777)

        namespace = runpy.run_path(str(ROOT / "deploy/verify-release-rollback.py"),
                                   run_name="fixture_sealed_copy_cleanup_test")
        temp_root = Path(tempfile.mkdtemp(prefix="whole-map-sealed-copy-test-"))
        self.addCleanup(lambda: shutil.rmtree(temp_root, ignore_errors=True))
        copy = temp_root / "copy"
        shutil.copytree(original, copy, symlinks=False)
        self.assertEqual(copy.stat().st_mode & 0o777, 0o555)
        errors = []
        removed = namespace["_remove_runtime_root"](temp_root, errors)
        self.assertTrue(removed)
        self.assertFalse(temp_root.exists())
        self.assertEqual(errors, [])

        after_state = {}
        for path in [original, *original.rglob("*")]:
            rel = path.relative_to(original.parent).as_posix()
            if path.is_file():
                after_state[rel] = ("file", sha_bytes(path.read_bytes()), path.stat().st_mode & 0o777)
            else:
                after_state[rel] = ("dir", None, path.stat().st_mode & 0o777)
        self.assertEqual(after_state, original_state)

    def test_packaged_native_readiness_uses_actual_status_endpoint(self):
        namespace = runpy.run_path(str(ROOT / "deploy/verify-release-rollback.py"),
                                   run_name="fixture_native_readiness_test")
        with tempfile.TemporaryDirectory(prefix="fixture-native-readiness-") as raw:
            root = Path(raw)
            release = root / "release"
            (release / "kiosk").mkdir(parents=True)
            (release / "public").mkdir()
            (release / "manifest.json").write_text("{}")
            (release / "kiosk/index.html").write_bytes(b"terminal")
            (release / "public/index.html").write_bytes(b"public")
            runtime = root / "runtime"
            renderer_link = runtime / "work/hardware/python"
            renderer_link.parent.mkdir(parents=True)
            renderer_link.symlink_to(root, target_is_directory=True)
            manager_type = namespace["_PackagedProcesses"]
            with patch.dict(namespace["_PackagedProcesses"].__init__.__globals__,
                            {"_free_ports": lambda count: [40000, 40001, 40002]}):
                manager = manager_type(runtime, "a" * 48, root, root)
            components = iter(("native", "companion", "gateway"))
            launched = []
            def launch(package, component, ready=None):
                child = types.SimpleNamespace(pid=next(components), component=component)
                launched.append(child)
                return child
            manager._launch = launch
            manager._create_native_state = lambda _manifest_hash: None
            probes = []
            def wait(child, port, url, ready=None, expected=None, origin_checks=None, timeout=None):
                probes.append((child.component, url, expected))
                if child.component == "native":
                    self.assertEqual(timeout, 90)
                    expected(b'{"status":"ok"}')
                    return port
                selected_port = 40001 if child.component == "companion" else 40002
                row = {"pid": child.pid, "host": "127.0.0.1", "port": selected_port,
                       "code_root": str(release), "terminal_root": str(release / "kiosk"),
                       "static_root": str(release / "public"), "physical_boundary": "pre-import stubs",
                       "module_origins": {}}
                ready.write_text(json.dumps(row))
                if origin_checks:
                    origin_checks(row)
                return selected_port
            manager._wait_listener = wait
            manager.start(release)
            self.assertEqual(probes[0][1], "http://127.0.0.1:40000/api/v1/status")

    def test_fixture_native_registration_override_is_applied_after_token_guard(self):
        source = (ROOT / "deploy/run-homebox.py").read_text()
        with tempfile.TemporaryDirectory(prefix="fixture-registration-guard-") as raw:
            root = Path(raw)
            runtime = root / "runtime"
            baseline = runtime / "work/baseline"
            (baseline / "data").mkdir(parents=True)
            (baseline / "data/homebox.db").write_bytes(b"")
            (baseline / "pepper").write_text("fixture pepper")
            (baseline / "test-account.json").write_text("{}")
            runtime.chmod(0o700)
            token = "fixture-registration-" + "a" * 40
            (runtime / ".fixture-process-token").write_text(token)
            (runtime / ".fixture-process-token").chmod(0o600)
            release = root / "release"
            (release / "deploy").mkdir(parents=True)
            (release / "native").mkdir()
            (release / "native/homebox").write_bytes(b"fixture executable")
            launcher = release / "deploy/run-homebox.py"
            old_cwd = os.getcwd()
            try:
                env = {"WORKSHOP_FIXTURE_PROCESS": "1", "WORKSHOP_ROOT": str(runtime),
                       "WORKSHOP_FIXTURE_TOKEN": token,
                       "HOMEBOX_WEB_HOST": "127.0.0.1", "HOMEBOX_WEB_PORT": "40000",
                       "HBOX_OPTIONS_ALLOW_REGISTRATION": "true"}
                calls = []
                def stop_exec(*_args):
                    calls.append(dict(os.environ))
                    raise RuntimeError("exec boundary")
                with patch.dict(os.environ, env, clear=True), patch("os.chdir"), \
                     patch("os.execv", side_effect=stop_exec):
                    with self.assertRaisesRegex(RuntimeError, "exec boundary"):
                        exec(compile(source, str(launcher), "exec"), {"__file__": str(launcher)})
                self.assertEqual(calls[0].get("HBOX_OPTIONS_ALLOW_REGISTRATION"), "true")
                with patch.dict(os.environ, dict(env, HBOX_STORAGE_PREFIX_PATH="/operational"), clear=True), \
                     patch("os.chdir"), patch("os.execv") as execute:
                    with self.assertRaisesRegex(RuntimeError, "Fixture native launcher refused"):
                        exec(compile(source, str(launcher), "exec"), {"__file__": str(launcher)})
                    execute.assert_not_called()
            finally:
                os.chdir(old_cwd)

    def test_fixture_service_transition_stops_old_processes_before_starting_selected_package(self):
        namespace = runpy.run_path(str(ROOT / "deploy/verify-release-rollback.py"),
                                   run_name="fixture_transition_order_test")
        with tempfile.TemporaryDirectory(prefix="fixture-transition-order-") as raw:
            root = Path(raw)
            runtime = root / "runtime"
            selected = root / "selected"
            selected.mkdir()
            pointer = runtime / "work/application-current"
            pointer.parent.mkdir(parents=True)
            pointer.symlink_to(selected, target_is_directory=True)
            manager = object.__new__(namespace["_PackagedProcesses"])
            manager.runtime = runtime
            events = []
            manager.stop_all = lambda: events.append("stop")
            manager.start = lambda release: events.append(("start", release))
            manager.run_services(["start", "homebox-native", "homebox-companion", "homebox-workshop-gateway"])
            self.assertEqual(events, ["stop", ("start", selected.resolve())])

    def test_native_port_retry_reaps_only_live_fixture_child_on_foreign_listener(self):
        namespace = runpy.run_path(str(ROOT / "deploy/verify-release-rollback.py"),
                                   run_name="fixture_native_port_retry_test")
        class Child:
            def __init__(self, pid): self.pid = pid
            def poll(self): return None
        manager = object.__new__(namespace["_PackagedProcesses"])
        manager.native_port = 36235
        manager.native_port_retries = []
        manager.children = {}
        manager.native_proxy = types.SimpleNamespace(rebind=Mock())
        launched = []
        stopped = []
        def launch(_release, _component):
            child = Child(100 + len(launched))
            launched.append(child)
            manager.children["native"] = (child, None, None)
            return child
        manager._launch = launch
        def stop_all():
            stopped.append(tuple(manager.children))
            manager.children.clear()
        manager.stop_all = stop_all
        waits = []
        def wait(child, port, *_args, **_kwargs):
            waits.append((child.pid, port))
            if len(waits) == 1:
                raise namespace["ListenerOwnershipMismatch"](child.pid, port, [999])
            return port
        manager._wait_listener = wait
        with patch.dict(namespace["_free_ports"].__globals__, {"_free_ports": lambda count: [41001]}):
            result = manager._start_native_listener(Path("/fixture/O"))
        self.assertEqual(result.pid, 101)
        self.assertEqual(waits, [(100, 36235), (101, 41001)])
        self.assertEqual(stopped, [("native",)])
        self.assertEqual(manager.native_port_retries[0]["foreign_listener_pids"], [999])
        manager.native_proxy.rebind.assert_called_once_with(41001)

    def test_native_port_retry_refuses_when_no_foreign_owner_is_observed(self):
        namespace = runpy.run_path(str(ROOT / "deploy/verify-release-rollback.py"),
                                   run_name="fixture_native_port_no_retry_test")
        class Child:
            pid = 100
            def poll(self): return None
        manager = object.__new__(namespace["_PackagedProcesses"])
        manager.native_port = 36235
        manager.native_port_retries = []
        manager.children = {"native": (Child(), None, None)}
        manager._launch = lambda *_args: manager.children["native"][0]
        stopped = []
        manager.stop_all = lambda: stopped.append(True)
        manager._wait_listener = lambda child, port, *_args, **_kwargs: (_ for _ in ()).throw(
            namespace["ListenerOwnershipMismatch"](child.pid, port, []))
        with self.assertRaises(namespace["ListenerOwnershipMismatch"]):
            manager._start_native_listener(Path("/fixture/O"))
        self.assertEqual(stopped, [])
        self.assertEqual(manager.native_port_retries, [])

    def test_fixture_native_state_assertion_rejects_changed_profile_or_loan_history(self):
        namespace = runpy.run_path(str(ROOT / "deploy/verify-release-rollback.py"),
                                   run_name="fixture_native_state_red_test")
        expected = {"member_profile_sha256": "profile-before",
                    "loan_history": [{"operation_id": "loan-1", "created_at": "fixture-date"}],
                    "native_store_identity": [1, 2], "ledger_store_identity": [3, 4]}
        changed = dict(expected, loan_history=[{"operation_id": "loan-1", "created_at": "changed-date"}])
        with self.assertRaisesRegex(namespace["FixtureRefusal"], "native member/loan state changed"):
            namespace["_assert_native_state_snapshot"](expected, changed)

    def test_fixture_http_probe_checks_owner_before_and_after_request(self):
        from unittest.mock import Mock
        namespace = runpy.run_path(str(ROOT / "deploy/verify-release-rollback.py"),
                                   run_name="fixture_http_probe_test")
        events = []
        owned = Mock(side_effect=lambda pid, port: events.append("owner") or (len(events) == 1))
        with patch.dict(namespace["_http"].__globals__, {"_pid_owns_listener": owned,
                                                          "_listener_owner_pids": lambda _port: [999]}):
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.read.return_value = b"body"
            with patch("urllib.request.urlopen", return_value=response) as request:
                with self.assertRaisesRegex(namespace["FixtureRefusal"], "ownership changed"):
                    namespace["_http"]("http://127.0.0.1:40000/", 42, 40000)
                self.assertEqual(request.call_count, 1)
                self.assertEqual(events, ["owner", "owner"])
            events.clear()
            owned.side_effect = lambda pid, port: events.append("owner") or False
            with patch("urllib.request.urlopen") as request:
                with self.assertRaisesRegex(namespace["FixtureRefusal"], "not owned"):
                    namespace["_http"]("http://127.0.0.1:40000/", 42, 40000)
                request.assert_not_called()

    def test_fixture_raw_upload_checks_owner_before_and_after_request(self):
        namespace = runpy.run_path(str(ROOT / "deploy/verify-release-rollback.py"),
                                   run_name="fixture_raw_upload_owner_test")
        events = []
        def owner(pid, port):
            events.append("owner")
            return len([event for event in events if event == "owner"]) == 1
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.status = 201
        response.read.return_value = b'{"ok":true}'
        with patch.dict(namespace["_owned_urlopen"].__globals__,
                        {"_pid_owns_listener": owner,
                         "_listener_owner_pids": lambda _port: []}):
            with patch("urllib.request.urlopen", side_effect=lambda *_a, **_k: events.append("request") or response) as request:
                with self.assertRaisesRegex(namespace["FixtureRefusal"], "ownership changed"):
                    namespace["_owned_urlopen"](Mock(), 42, 40000)
                self.assertEqual(events, ["owner", "request", "owner"])
                self.assertEqual(request.call_count, 1)
            events.clear()
            with patch.dict(namespace["_owned_urlopen"].__globals__,
                            {"_pid_owns_listener": lambda *_: events.append("owner") or False}):
                with patch("urllib.request.urlopen") as request:
                    with self.assertRaisesRegex(namespace["FixtureRefusal"], "not owned"):
                        namespace["_owned_urlopen"](Mock(), 42, 40000)
                    request.assert_not_called()
                    self.assertEqual(events, ["owner"])

    def test_fixture_http_probe_treats_absent_listener_as_transient_without_request(self):
        namespace = runpy.run_path(str(ROOT / "deploy/verify-release-rollback.py"),
                                   run_name="fixture_http_not_ready_test")
        with patch.dict(namespace["_http"].__globals__,
                        {"_pid_owns_listener": lambda _pid, _port: False,
                         "_listener_owner_pids": lambda _port: []}):
            with patch("urllib.request.urlopen") as request:
                with self.assertRaisesRegex(ConnectionError, "not ready"):
                    namespace["_http"]("http://127.0.0.1:40000/", 42, 40000)
                request.assert_not_called()

    def test_fixture_listener_owner_matches_real_loopback_socket_pid(self):
        namespace = runpy.run_path(str(ROOT / "deploy/verify-release-rollback.py"),
                                   run_name="fixture_listener_pid_test")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            self.assertTrue(namespace["_pid_owns_listener"](os.getpid(), port))
            self.assertEqual(namespace["_listener_owner_pids"](port), (os.getpid(),))
            self.assertFalse(namespace["_pid_owns_listener"](os.getpid() + 1000000, port))

    def _assert_fixture_entrypoint_preflight(self, filename, extra, expected, untouched):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            wrapper = root / "probe.py"
            wrapper.write_text(
                "import http.server,runpy,sys\n"
                "class NoListener:\n"
                " def __init__(self,*a,**k): print('BOUND',repr(a[0])); raise RuntimeError('listener stub')\n"
                "http.server.ThreadingHTTPServer=NoListener\n"
                f"runpy.run_path({str(ROOT / 'deploy' / filename)!r},run_name='__main__')\n")
            env = {key: value for key, value in os.environ.items()
                   if not key.startswith(("HBOX_", "WORKSHOP_", "HOMEBOX_WEB_"))}
            env.update({"WORKSHOP_FIXTURE_PROCESS": "1", "WORKSHOP_ROOT": str(root),
                        "WORKSHOP_FIXTURE_TOKEN": "untrusted", "WORKSHOP_BIND_HOST": "127.0.0.1",
                        "WORKSHOP_FIXTURE_READY_FILE": str(root / "ready.json"), **extra})
            result = subprocess.run([sys.executable, str(wrapper)], env=env,
                                     text=True, capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(expected, result.stderr)
            self.assertNotIn("BOUND", result.stdout)
            self.assertFalse((root / untouched).exists())

    def test_runtime_roots_survive_release_selection(self):
        source, release = self.make_bundle("runtime", "runtime-marker")
        runtime_root = self.root / "runtime-root"
        runtime_root.mkdir()
        self.select(runtime_root, release)
        expected = {
            "native": "run-homebox.py",
            "companion": "kiosk-server.py",
            "gateway": "workshop-gateway.py",
        }
        for component, entrypoint in expected.items():
            executable, argv, env = self.run_packaged_launcher(release, runtime_root, component)
            self.assertEqual(argv[-1], str(release.resolve() / "deploy" / entrypoint))
            self.assertEqual(env["WORKSHOP_ROOT"], str(runtime_root))
            self.assertEqual(env["WORKSHOP_CODE_ROOT"], str(release.resolve()))
            self.assertEqual(env["HOMEBOX_UI_ROOT"], str(release.resolve() / "public"))
        for unit in ("homebox-native.service", "homebox-companion.service", "homebox-workshop-gateway.service"):
            text = (source / "deploy" / unit).read_text()
            self.assertIn("ExecStart=/usr/bin/python3 /home/user/Desktop/inventory-system/work/application-current/deploy/run-release.py", text)
        self.assertIn("native", (source / "deploy/homebox-native.service").read_text())
        self.assertIn("companion", (source / "deploy/homebox-companion.service").read_text())
        self.assertIn("gateway", (source / "deploy/homebox-workshop-gateway.service").read_text())
        self.assertTrue((release / "label-ui/src/starter-documents.json").is_file())
        self.assertTrue((release / "label-ui/render.html").is_file())
        fake_ledger = types.ModuleType("ledger")
        fake_ledger.Conflict = type("Conflict", (Exception,), {})
        fake_ledger.uuid = lambda value: value
        with patch.dict(os.environ, {"WORKSHOP_ROOT": str(runtime_root),
                                     "WORKSHOP_CODE_ROOT": str(release.resolve())}, clear=False), \
             patch.dict(sys.modules, {"ledger": fake_ledger}):
            render_spec = importlib.util.spec_from_file_location("selected_label_render", release / "ops/label_render.py")
            render_module = importlib.util.module_from_spec(render_spec)
            render_spec.loader.exec_module(render_module)
            sys.modules["label_render"] = render_module
            layouts_spec = importlib.util.spec_from_file_location("selected_label_layouts", release / "ops/label_layouts.py")
            layouts_module = importlib.util.module_from_spec(layouts_spec)
            layouts_spec.loader.exec_module(layouts_module)
            sys.modules.pop("label_render", None)
        self.assertEqual(render_module.DEFAULT_ASSET_ROOT, release.resolve() / "label-ui")
        self.assertEqual(render_module.ROOT, runtime_root)
        self.assertEqual(render_module.NODE, runtime_root / "work/toolchains/node-v24.21.0-linux-arm64/bin/node")
        self.assertEqual(render_module.PLAYWRIGHT_PYTHON, str(runtime_root / "work/hardware/python"))
        self.assertTrue(render_module._check_manifest(render_module.DEFAULT_ASSET_ROOT).is_relative_to(release.resolve()))
        self.assertEqual(layouts_module._starter("supvan", "left")["name"], "supvan-left")
        process_calls = []
        class ProcessSpy:
            pid = 123
            returncode = 0
            def communicate(self, *_args, **_kwargs):
                return b'{"results":[]}', b''
        with patch.object(render_module.subprocess, "Popen",
                          side_effect=lambda *args, **kwargs: process_calls.append((args, kwargs)) or ProcessSpy()):
            render_module._run({"asset_root": str(release / "label-ui")}, 1)
        self.assertEqual(process_calls[0][1]["env"]["WORKSHOP_ROOT"], str(runtime_root))
        self.assertNotIn("WORKSHOP_CODE_ROOT", process_calls[0][1]["env"])
        native = release / "deploy/run-homebox.py"
        checked, changed, execs = [], [], []
        original_is_file, original_read_text = Path.is_file, Path.read_text
        def fake_is_file(path):
            checked.append(path)
            return path in {runtime_root / "work/baseline/data/homebox.db",
                            runtime_root / "work/baseline/pepper",
                            runtime_root / "work/baseline/test-account.json",
                            release / "native/homebox"}
        def fake_read_text(path, *args, **kwargs):
            if path == runtime_root / "work/baseline/pepper":
                return "synthetic-key"
            return original_read_text(path, *args, **kwargs)
        with patch.dict(os.environ, {"WORKSHOP_ROOT": str(runtime_root),
                                     "WORKSHOP_CODE_ROOT": str(release.resolve())}, clear=False), \
             patch.object(Path, "is_file", fake_is_file), \
             patch.object(Path, "read_text", fake_read_text), \
             patch("os.chdir", side_effect=lambda path: changed.append(path)), \
             patch("os.execv", side_effect=lambda *args: execs.append(args)):
            runpy.run_path(str(native), run_name="__main__")
        self.assertEqual(changed, [runtime_root / "work/baseline"])
        self.assertEqual(execs[0][0], str(release / "native/homebox"))
        self.assertIn(runtime_root / "work/baseline/pepper", checked)
        self.assertNotIn(release / "work/baseline/pepper", checked)
        self.assertEqual(env["HOMEBOX_UI_ROOT"], str(release.resolve() / "public"))
        kiosk_source = (source / "deploy/kiosk-server.py").read_text()
        self.assertIn("ROOT/'work/ops'", kiosk_source)
        self.assertIn("ROOT/'program-files/runtime/hardware/python'", kiosk_source)
        self.assertIn("CODE_ROOT/'kiosk'", kiosk_source)
        old_work_root = os.environ.get("WORKSHOP_ROOT")
        with patch.dict(os.environ, {"WORKSHOP_ROOT": str(runtime_root)}, clear=False):
            fake_ledger = types.ModuleType("ledger")
            fake_ledger.Conflict = type("Conflict", (Exception,), {})
            fake_ledger.uuid = lambda value: value
            fake_qrcode = types.ModuleType("qrcode")
            fake_pil = types.ModuleType("PIL")
            fake_pil.Image = fake_pil.ImageDraw = fake_pil.ImageFont = types.SimpleNamespace()
            with patch.dict(sys.modules, {"ledger": fake_ledger, "qrcode": fake_qrcode, "PIL": fake_pil}):
                spec = importlib.util.spec_from_file_location("selected_labels", release / "ops/labels.py")
                labels = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(labels)
            adapter = Path(labels.adapter())
        self.assertEqual(adapter, runtime_root / "work/supvan-cups/target/release/examples/kiosk-label")
        self.assertFalse(adapter.is_relative_to(release.resolve()))
        self.assertEqual(old_work_root, os.environ.get("WORKSHOP_ROOT"))

    def test_operational_native_launcher_uses_existing_runtime_binary_and_requires_data(self):
        runtime_root = self.root / "operational"
        run = runtime_root / "work/baseline"
        binary = runtime_root / "work/homebox-bin/homebox"
        for path, content in ((binary, b"fixture executable"),
                              (run / "data/homebox.db", b"fixture database"),
                              (run / "pepper", b"fixture pepper"),
                              (run / "test-account.json", b"{}")):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        chdir_calls, exec_calls = [], []
        launcher = ROOT / "deploy/run-homebox.py"
        with patch.dict(os.environ, {"WORKSHOP_ROOT": str(runtime_root)}, clear=True), \
             patch("os.chdir", side_effect=lambda path: chdir_calls.append(path)), \
             patch("os.execv", side_effect=lambda *args: exec_calls.append(args)):
            runpy.run_path(str(launcher), run_name="__main__")
        self.assertEqual(chdir_calls, [run])
        self.assertEqual(exec_calls[0][0], str(binary))

        (run / "data/homebox.db").unlink()
        exec_calls.clear()
        with patch.dict(os.environ, {"WORKSHOP_ROOT": str(runtime_root)}, clear=True), \
             patch("os.execv", side_effect=lambda *args: exec_calls.append(args)):
            with self.assertRaisesRegex(RuntimeError, "refusing to create a new database"):
                runpy.run_path(str(launcher), run_name="__main__")
        self.assertEqual(exec_calls, [])

    def test_kiosk_server_uses_selected_code_for_imports_and_assets(self):
        runtime_root = self.root / "runtime-kiosk"
        code_root = self.root / "release-kiosk"
        stale_assets = self.root / "stale-label-assets"
        (runtime_root / "work").mkdir(parents=True)
        dependency_root = runtime_root / "program-files/runtime/hardware/python"
        dependency_root.mkdir(parents=True)
        write(dependency_root, "hardware.py", b"SENTINEL = 'durable-runtime-copy'\ndef reconnect(device): return SENTINEL\ndef camera_status(): return {}\n")
        (code_root / "kiosk").mkdir(parents=True)
        (code_root / "label-ui").mkdir(parents=True)
        fake_modules = {}
        module_names = "ledger badges sessions scan_codes decode_codes homebox checkout returns maps native_jobs categories code_registration stock reviews kits system_status desktop_api accounts labels problems item_notes setup_native imports label_layouts kiosk_processes network_access workshop workshop_views shelf_checks products conditions zxingcpp qrcode PIL".split()
        for name in module_names:
            fake = types.ModuleType(name)
            for symbol in ("Ledger", "Badges", "Sessions", "Homebox", "NativeJobs", "Imports", "LabelLayouts", "ShelfChecks", "Workshop", "Conflict"):
                setattr(fake, symbol, type(symbol, (), {"__init__": lambda self, *args, **kwargs: None}))
            fake.UNIDENTIFIED_ACTOR = object()
            fake.RETURN_STATES = ()
            fake.STATES = ()
            if name == "PIL":
                fake.Image = types.SimpleNamespace()
            if name == "shelf_checks":
                fake.CheckAccessDenied = type("CheckAccessDenied", (Exception,), {})
                fake.shelf_check_action = fake.terminal_check_context = lambda *args, **kwargs: None
            for symbol in ("normalize", "resolve_equipment", "decode_frame", "confirm_checkout", "confirm_return", "recover", "list_map", "save_room", "save_object", "remove_object", "create_category", "recover_category", "register_code", "recover_code", "browse", "invalidate", "submit_review", "recover_review", "manifest", "save", "status", "start_backup", "reconnect", "camera_status", "handle", "once", "operation_status", "recovery_rows", "post_action", "request_row", "history", "create_account", "get_profile", "update_profile", "creation_input", "profile_input", "preview", "print_label", "print_badge", "recover_print", "probe", "paper", "submit_problem", "recover_problem", "submit_note", "recover_note", "submit", "recover_creation", "kiosk_pids", "same_origin", "trusted_native_origins", "move_location", "submit_shelf_order", "recover_shelf_order", "build_view", "resolve_workshop_code", "catalog", "lookup", "condition", "checkout_blocker", "set_condition"):
                setattr(fake, symbol, lambda *args, **kwargs: None)
            fake_modules[name] = fake
        env = {"WORKSHOP_ROOT": str(runtime_root), "WORKSHOP_CODE_ROOT": str(code_root),
               "WORKSHOP_LABEL_ASSET_ROOT": str(stale_assets)}
        original_path = list(sys.path)
        env_before = {key: os.environ.get(key) for key in env}
        hardware_before = sys.modules.get("hardware")
        try:
            with patch.dict(os.environ, env, clear=False), patch.dict(sys.modules, fake_modules):
                sys.modules.pop("hardware", None)
                source = (ROOT / "deploy/kiosk-server.py").read_text()
                source = source.replace(
                    "_fixture_server=ThreadingHTTPServer((_fixture_host,_fixture_port),Handler)",
                    "_fixture_server=__import__('types').SimpleNamespace(server_address=(_fixture_host,_fixture_port),serve_forever=lambda:None)")
                namespace = {"__name__": "kiosk_server_review_test", "__file__": str(ROOT / "deploy/kiosk-server.py")}
                exec(compile(source, namespace["__file__"], "exec"), namespace)
                self.assertEqual(namespace["reconnect_hardware"]("camera"), "durable-runtime-copy")
                self.assertEqual(sys.modules["hardware"].__file__, str(dependency_root / "hardware.py"))
                self.assertIn(str(code_root / "kiosk"), sys.path)
                self.assertIn(str(dependency_root), sys.path)
                self.assertNotIn(str(code_root / "work/hardware/python"), sys.path)
                self.assertIn(str(code_root / "ops"), sys.path)
        finally:
            sys.path[:] = original_path
        self.assertEqual(namespace["ROOT"], runtime_root)
        self.assertEqual(namespace["LABEL_ASSET_ROOT"], code_root / "label-ui")
        self.assertEqual(namespace["ops_path"], runtime_root / "work/ops")
        self.assertEqual(sys.path, original_path)
        self.assertEqual({key: os.environ.get(key) for key in env}, env_before)
        self.assertIs(sys.modules.get("hardware"), hardware_before)
        self.assertEqual(namespace["terminal_assets"](), code_root / "kiosk")

    def test_system_status_and_backup_paths_use_runtime_root(self):
        _, release = self.make_bundle("status-root", "status-marker")
        runtime_root = self.root / "runtime-status"
        (runtime_root / "work").mkdir(parents=True)
        fake_ledger = types.ModuleType("ledger")
        fake_ledger.uuid = lambda value: value
        fake_ledger.Conflict = type("Conflict", (Exception,), {})
        fake_hardware = types.ModuleType("hardware")
        fake_hardware.reconnect = lambda device: {"device": device}
        fake_hardware.camera_status = lambda: {"camera": "synthetic"}
        with patch.dict(os.environ, {"WORKSHOP_ROOT": str(runtime_root)}, clear=False), \
             patch.dict(sys.modules, {"ledger": fake_ledger, "hardware": fake_hardware}):
            spec = importlib.util.spec_from_file_location("selected_system_status", release / "ops/system_status.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        paths = []
        disk = types.SimpleNamespace(free=3 * 1024**3, total=8 * 1024**3)
        glob_paths = []
        def fake_glob(path, pattern):
            glob_paths.append((path, pattern))
            return []
        with patch.object(module.shutil, "disk_usage", side_effect=lambda path: paths.append(path) or disk), \
             patch.object(module, "unit", return_value="inactive"), \
             patch.object(module, "reconnect", return_value={"device": "printer"}), \
             patch.object(module, "camera_status", return_value={"camera": "synthetic"}), \
             patch.object(module.pathlib.Path, "glob", fake_glob):
            module.status()
        self.assertEqual(paths, [runtime_root])
        self.assertEqual(module.STATE, runtime_root / "work/backup-status.json")
        self.assertIn((runtime_root / "work/backups", "deployment-*.tar.gz"), glob_paths)
        calls = []
        with patch.object(module.subprocess, "run", side_effect=lambda command, **kwargs: calls.append(command)), \
             patch.object(module, "unit", return_value="inactive"):
            module.start_backup("request-key")
        self.assertEqual(calls[0][-1], str(runtime_root / "deploy/backup-deployment.py"))

    def test_invalid_component_or_bundle_never_launches(self):
        source, release = self.make_bundle("invalid", "invalid-marker")
        runtime_root = self.root / "runtime-invalid"
        self.select(runtime_root, release)
        with self.assertRaises(ValueError):
            release_command(runtime_root, "printer")
        with self.assertRaises(BundleError):
            release_command(runtime_root, "native", release=self.root / "missing")
        public = release / "public/index.html"
        release.chmod(0o755)
        (release / "public").chmod(0o755)
        public.chmod(0o644)
        public.unlink()
        (release / "public").chmod(0o555)
        release.chmod(0o555)
        calls = []
        launcher = release / "deploy/run-release.py"
        with patch.object(sys, "argv", [str(launcher), "gateway"]), \
             patch.dict(os.environ, {"WORKSHOP_ROOT": str(runtime_root)}, clear=False), \
             patch("os.execvpe", side_effect=lambda *args: calls.append(args)):
            with self.assertRaises(ValueError):
                runpy.run_path(str(launcher), run_name="__main__")
        self.assertEqual(calls, [])

    def test_tampered_helper_is_rejected_before_execution(self):
        _, release = self.make_bundle("tampered-helper", "helper-marker")
        runtime_root = self.root / "runtime-tampered"
        self.select(runtime_root, release)
        sentinel = self.root / "helper-executed"
        helper = release / "deploy/release_bundle.py"
        helper.chmod(0o644)
        helper.write_text(f"from pathlib import Path\nPath({str(sentinel)!r}).touch()\n")
        helper.chmod(0o444)
        calls = []
        launcher = release / "deploy/run-release.py"
        with patch.object(sys, "argv", [str(launcher), "gateway"]), \
             patch.dict(os.environ, {"WORKSHOP_ROOT": str(runtime_root)}, clear=False), \
             patch("os.execvpe", side_effect=lambda *args: calls.append(args)):
            with self.assertRaises(ValueError):
                runpy.run_path(str(launcher), run_name="__main__")
        self.assertFalse(sentinel.exists())
        self.assertEqual(calls, [])

    def test_manifest_cannot_authorize_helper_not_bound_by_receipts(self):
        _, release = self.make_bundle("receipt-helper", "receipt-marker")
        runtime_root = self.root / "runtime-receipt-helper"
        self.select(runtime_root, release)
        sentinel = self.root / "receipt-helper-executed"
        helper = release / "deploy/release_bundle.py"
        manifest_path = release / "manifest.json"
        release.chmod(0o755)
        helper.chmod(0o644)
        helper.write_text(f"from pathlib import Path\nPath({str(sentinel)!r}).touch()\n")
        helper.chmod(0o444)
        manifest = json.loads(manifest_path.read_text())
        manifest["files"]["deploy/release_bundle.py"]["sha256"] = sha_bytes(helper.read_bytes())
        manifest_path.chmod(0o644)
        manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
        manifest_path.chmod(0o444)
        release.chmod(0o555)
        calls = []
        launcher = release / "deploy/run-release.py"
        with patch.object(sys, "argv", [str(launcher), "gateway"]), \
             patch.dict(os.environ, {"WORKSHOP_ROOT": str(runtime_root)}, clear=False), \
             patch("os.execvpe", side_effect=lambda *args: calls.append(args)):
            with self.assertRaises(ValueError):
                runpy.run_path(str(launcher), run_name="__main__")
        self.assertFalse(sentinel.exists())
        self.assertEqual(calls, [])

    def test_symlinked_deploy_directory_is_rejected_before_reads(self):
        _, release = self.make_bundle("linked-deploy", "deploy-marker")
        runtime_root = self.root / "runtime-linked-deploy"
        self.select(runtime_root, release)
        deploy = release / "deploy"
        outside = self.root / "external-deploy"
        deploy.chmod(0o755)
        release.chmod(0o755)
        deploy.rename(outside)
        deploy.symlink_to(outside, target_is_directory=True)
        release.chmod(0o555)
        opened = self.run_launcher_main_with_read_spy(
            release, runtime_root, {release / "manifest.json", release / "deploy/release_bundle.py"})
        self.assertEqual(opened, [])

    def test_hardlinked_manifest_and_helper_are_rejected_before_their_reads(self):
        for name, target_name in (("hardlinked-manifest", "manifest.json"),
                                  ("hardlinked-helper", "deploy/release_bundle.py")):
            with self.subTest(target=target_name):
                _, release = self.make_bundle(name, name)
                runtime_root = self.root / f"runtime-{name}"
                self.select(runtime_root, release)
                target = release / target_name
                outside = self.root / f"{name}-outside"
                os.link(target, outside)
                opened = self.run_launcher_main_with_read_spy(release, runtime_root, {target})
                self.assertNotIn(target, opened)

    def test_invalid_component_is_rejected_before_helper_loading(self):
        _, release = self.make_bundle("invalid-first", "component-marker")
        runtime_root = self.root / "runtime-invalid-first"
        self.select(runtime_root, release)
        helper = release / "deploy/release_bundle.py"
        helper.chmod(0o644)
        helper.write_text("invalid helper bytes\n")
        helper.chmod(0o444)
        launcher = release / "deploy/run-release.py"
        with patch.object(sys, "argv", [str(launcher), "printer"]), \
             patch.dict(os.environ, {"WORKSHOP_ROOT": str(runtime_root)}, clear=False):
            with self.assertRaisesRegex(ValueError, "unknown release component"):
                runpy.run_path(str(launcher), run_name="__main__")


if __name__ == "__main__":
    unittest.main()
