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
        write(source, "kiosk/decode_codes.py", f"decoder {marker}".encode())
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
            for rel in ("ops/desktop_api.py", "kiosk/decode_codes.py", "deploy/kiosk-server.py",
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
        self.assertEqual((old_release / "kiosk/decode_codes.py").read_text(), "decoder old-source")

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
            [sys.exuë{¶‰ËkºwµçL½±…‰•±Ì¹Áäˆ¤(€€€€€€€€€€€€€€€±…‰•±Ì€ô¥µÁ½ÉÑ±¥ˆ¹ÕÑ¥°¹µ½‘Õ±•}™É½µ}ÍÁ•Œ¡ÍÁ•Œ¤(€€€€€€€€€€€€€€€ÍÁ•Œ¹±½…‘•È¹•á•}µ½‘Õ±”¡±…‰•±Ì¤(€€€€€€€€€€€…‘…ÁÑ•È€ôA…Ñ ¡±…‰•±Ì¹…‘…ÁÑ•È ¤¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡…‘…ÁÑ•È°ÉÕ¹Ñ¥µ•}É½½Ğ€¼€‰İ½É¬½ÍÕÁÙ…¸µÕÁÌ½Ñ…É•Ğ½É•±•…Í”½•á…µÁ±•Ì½­¥½Í¬µ±…‰•°ˆ¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑ…±Í”¡…‘…ÁÑ•È¹¥Í}É•±…Ñ¥Ù•}Ñ¼¡É•±•…Í”¹É•Í½±Ù” ¤¤¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡½±‘}İ½É­}É½½Ğ°½Ì¹•¹Ù¥É½¸¹•Ğ ‰]=I-M!=A}I==Pˆ¤¤((€€€‘•˜Ñ•ÍÑ}½Á•É…Ñ¥½¹…±}¹…Ñ¥Ù•}±…Õ¹¡•É}ÕÍ•Í}•á¥ÍÑ¥¹}ÉÕ¹Ñ¥µ•}‰¥¹…Éå}…¹‘}É•ÅÕ¥É•Í}‘…Ñ„¡Í•±˜¤è(€€€€€€€ÉÕ¹Ñ¥µ•}É½½Ğ€ôÍ•±˜¹É½½Ğ€¼€‰½Á•É…Ñ¥½¹…°ˆ(€€€€€€€ÉÕ¸€ôÉÕ¹Ñ¥µ•}É½½Ğ€¼€‰İ½É¬½‰…Í•±¥¹”ˆ(€€€€€€€‰¥¹…Éä€ôÉÕ¹Ñ¥µ•}É½½Ğ€¼€‰İ½É¬½¡½µ•‰½àµ‰¥¸½¡½µ•‰½àˆ(€€€€€€€™½ÈÁ…Ñ °½¹Ñ•¹Ğ¥¸€ ¡‰¥¹…Éä°ˆ‰™¥áÑÕÉ”•á•ÕÑ…‰±”ˆ¤°(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€¡ÉÕ¸€¼€‰‘…Ñ„½¡½µ•‰½à¹‘ˆˆ°ˆ‰™¥áÑÕÉ”‘…Ñ…‰…Í”ˆ¤°(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€¡ÉÕ¸€¼€‰Á•ÁÁ•Èˆ°ˆ‰™¥áÑÕÉ”Á•ÁÁ•Èˆ¤°(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€¡ÉÕ¸€¼€‰Ñ•ÍĞµ…½Õ¹Ğ¹©Í½¸ˆ°ˆ‰íôˆ¤¤è(€€€€€€€€€€€Á…Ñ ¹Á…É•¹Ğ¹µ­‘¥È¡Á…É•¹ÑÌõQÉÕ”°•á¥ÍÑ}½¬õQÉÕ”¤(€€€€€€€€€€€Á…Ñ ¹İÉ¥Ñ•}‰åÑ•Ì¡½¹Ñ•¹Ğ¤(€€€€€€€¡‘¥É}…±±Ì°•á•}…±±Ì€ômt°mt(€€€€€€€±…Õ¹¡•È€ôI==P€¼€‰‘•Á±½ä½ÉÕ¸µ¡½µ•‰½à¹Áäˆ(€€€€€€€İ¥Ñ Á…Ñ ¹‘¥Ğ¡½Ì¹•¹Ù¥É½¸°ì‰]=I-M!=A}I==PˆèÍÑÈ¡ÉÕ¹Ñ¥µ•}É½½Ğ¥ô°±•…ÈõQÉÕ”¤°p(€€€€€€€€€€€€Á…Ñ  ‰½Ì¹¡‘¥Èˆ°Í¥‘•}•™™•Ğõ±…µ‰‘„Á…Ñ è¡‘¥É}…±±Ì¹…ÁÁ•¹¡Á…Ñ ¤¤°p(€€€€€€€€€€€€Á…Ñ  ‰½Ì¹•á•Øˆ°Í¥‘•}•™™•Ğõ±…µ‰‘„€©…ÉÌè•á•}…±±Ì¹…ÁÁ•¹¡…ÉÌ¤¤è(€€€€€€€€€€€ÉÕ¹Áä¹ÉÕ¹}Á…Ñ ¡ÍÑÈ¡±…Õ¹¡•È¤°ÉÕ¹}¹…µ”ô‰}}µ…¥¹}|ˆ¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡¡‘¥É}…±±Ì°mÉÕ¹t¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡•á•}…±±ÍlÁulÁt°ÍÑÈ¡‰¥¹…Éä¤¤((€€€€€€€€¡ÉÕ¸€¼€‰‘…Ñ„½¡½µ•‰½à¹‘ˆˆ¤¹Õ¹±¥¹¬ ¤(€€€€€€€•á•}…±±Ì¹±•…È ¤(€€€€€€€İ¥Ñ Á…Ñ ¹‘¥Ğ¡½Ì¹•¹Ù¥É½¸°ì‰]=I-M!=A}I==PˆèÍÑÈ¡ÉÕ¹Ñ¥µ•}É½½Ğ¥ô°±•…ÈõQÉÕ”¤°p(€€€€€€€€€€€€Á…Ñ  ‰½Ì¹•á•Øˆ°Í¥‘•}•™™•Ğõ±…µ‰‘„€©…ÉÌè•á•}…±±Ì¹…ÁÁ•¹¡…ÉÌ¤¤è(€€€€€€€€€€€İ¥Ñ Í•±˜¹…ÍÍ•ÉÑI…¥Í•ÍI••à¡IÕ¹Ñ¥µ•ÉÉ½È°€‰É•™ÕÍ¥¹œÑ¼É•…Ñ”„¹•Ü‘…Ñ…‰…Í”ˆ¤è(€€€€€€€€€€€€€€€ÉÕ¹Áä¹ÉÕ¹}Á…Ñ ¡ÍÑÈ¡±…Õ¹¡•È¤°ÉÕ¹}¹…µ”ô‰}}µ…¥¹}|ˆ¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡•á•}…±±Ì°mt¤((€€€‘•˜Ñ•ÍÑ}­¥½Í­}Í•ÉÙ•É}ÕÍ•Í}Í•±•Ñ•‘}½‘•}™½É}¥µÁ½ÉÑÍ}…¹‘}…ÍÍ•ÑÌ¡Í•±˜¤è(€€€€€€€ÉÕ¹Ñ¥µ•}É½½Ğ€ôÍ•±˜¹É½½Ğ€¼€‰ÉÕ¹Ñ¥µ”µ­¥½Í¬ˆ(€€€€€€€½‘•}É½½Ğ€ôÍ•±˜¹É½½Ğ€¼€‰É•±•…Í”µ­¥½Í¬ˆ(€€€€€€€ÍÑ…±•}…ÍÍ•ÑÌ€ôÍ•±˜¹É½½Ğ€¼€‰ÍÑ…±”µ±…‰•°µ…ÍÍ•ÑÌˆ(€€€€€€€€¡ÉÕ¹Ñ¥µ•}É½½Ğ€¼€‰İ½É¬ˆ¤¹µ­‘¥È¡Á…É•¹ÑÌõQÉÕ”¤(€€€€€€€‘•Á•¹‘•¹å}É½½Ğ€ôÉÕ¹Ñ¥µ•}É½½Ğ€¼€‰ÁÉ½É…´µ™¥±•Ì½ÉÕ¹Ñ¥µ”½¡…É‘İ…É”½ÁåÑ¡½¸ˆ(€€€€€€€‘•Á•¹‘•¹å}É½½Ğ¹µ­‘¥È¡Á…É•¹ÑÌõQÉÕ”¤(€€€€€€€İÉ¥Ñ”¡‘•Á•¹‘•¹å}É½½Ğ°€‰¡…É‘İ…É”¹Áäˆ°ˆ‰M9Q%90€ô€‘ÕÉ…‰±”µÉÕ¹Ñ¥µ”µ½Áäq¹‘•˜É•½¹¹•Ğ¡‘•Ù¥”¤èÉ•ÑÕÉ¸M9Q%91q¹‘•˜…µ•É…}ÍÑ…ÑÕÌ ¤èÉ•ÑÕÉ¸íõq¸ˆ¤(€€€€€€€€¡½‘•}É½½Ğ€¼€‰­¥½Í¬ˆ¤¹µ­‘¥È¡Á…É•¹ÑÌõQÉÕ”¤(€€€€€€€€¡½‘•}É½½Ğ€¼€‰±…‰•°µÕ¤ˆ¤¹µ­‘¥È¡Á…É•¹ÑÌõQÉÕ”¤(€€€€€€€™…­•}µ½‘Õ±•Ì€ôíô(€€€€€€€µ½‘Õ±•}¹…µ•Ì€ô€‰±•‘•È‰…‘•ÌÍ•ÍÍ¥½¹ÌÍ…¹}½‘•Ì‘•½‘•}½‘•Ì¡½µ•‰½à¡•­½ÕĞÉ•ÑÕÉ¹Ìµ…ÁÌ¹…Ñ¥Ù•}©½‰Ì…Ñ•½É¥•Ì½‘•}É•¥ÍÑÉ…Ñ¥½¸ÍÑ½¬É•Ù¥•İÌ­¥ÑÌÍåÍÑ•µ}ÍÑ…ÑÕÌ‘•Í­Ñ½Á}…Á¤…½Õ¹ÑÌ±…‰•±ÌÁÉ½‰±•µÌ¥Ñ•µ}¹½Ñ•ÌÍ•ÑÕÁ}¹…Ñ¥Ù”¥µÁ½ÉÑÌ±…‰•±}±…å½ÕÑÌ¹•Ñİ½É­}…•ÍÌİ½É­Í¡½Àİ½É­Í¡½Á}Ù¥•İÌÍ¡•±™}¡•­ÌÁÉ½‘ÕÑÌ½¹‘¥Ñ¥½¹Ìéá¥¹ÁÀÅÉ½‘”A%0ˆ¹ÍÁ±¥Ğ ¤(€€€€€€€™½È¹…µ”¥¸µ½‘Õ±•}¹…µ•Ìè(€€€€€€€€€€€™…­”€ôÑåÁ•Ì¹5½‘Õ±•QåÁ”¡¹…µ”¤(€€€€€€€€€€€™½ÈÍåµ‰½°¥¸€ ‰1•‘•Èˆ°€‰	…‘•Ìˆ°€‰M•ÍÍ¥½¹Ìˆ°€‰!½µ•‰½àˆ°€‰9…Ñ¥Ù•)½‰Ìˆ°€‰%µÁ½ÉÑÌˆ°€‰1…‰•±1…å½ÕÑÌˆ°€‰M¡•±™¡•­Ìˆ°€‰]½É­Í¡½Àˆ°€‰½¹™±¥Ğˆ¤è(€€€€€€€€€€€€€€€Í•Ñ…ÑÑÈ¡™…­”°Íåµ‰½°°ÑåÁ”¡Íåµ‰½°°€ ¤°ì‰}}¥¹¥Ñ}|ˆè±…µ‰‘„Í•±˜°€©…ÉÌ°€¨©­İ…ÉÌè9½¹•ô¤¤(€€€€€€€€€€€™…­”¹U9%9Q%%}Q=H€ô½‰©•Ğ ¤(€€€€€€€€€€€™…­”¹IQUI9}MQQL€ô€ ¤(€€€€€€€€€€€™…­”¹MQQL€ô€ ¤(€€€€€€€€€€€¥˜¹…µ”€ôô€‰A%0ˆè(€€€€€€€€€€€€€€€™…­”¹%µ…”€ôÑåÁ•Ì¹M¥µÁ±•9…µ•ÍÁ…” ¤(€€€€€€€€€€€¥˜¹…µ”€ôô€‰Í¡•±™}¡•­Ìˆè(€€€€€€€€€€€€€€€™…­”¹¡•­•ÍÍ•¹¥•€ôÑåÁ” ‰¡•­•ÍÍ•¹¥•ˆ°€¡á•ÁÑ¥½¸°¤°íô¤(€€€€€€€€€€€€€€€™…­”¹Í¡•±™}¡•­}…Ñ¥½¸€ô™…­”¹Ñ•Éµ¥¹…±}¡•­}½¹Ñ•áĞ€ô±…µ‰‘„€©…ÉÌ°€¨©­İ…ÉÌè9½¹”(€€€€€€€€€€€™½ÈÍåµ‰½°¥¸€ ‰¹½Éµ…±¥é”ˆ°€‰É•Í½±Ù•}•ÅÕ¥Áµ•¹Ğˆ°€‰‘•½‘•}™É…µ”ˆ°€‰½¹™¥Éµ}¡•­½ÕĞˆ°€‰½¹™¥Éµ}É•ÑÕÉ¸ˆ°€‰É•½Ù•Èˆ°€‰±¥ÍÑ}µ…Àˆ°€‰Í…Ù•}É½½´ˆ°€‰Í…Ù•}½‰©•Ğˆ°€‰É•µ½Ù•}½‰©•Ğˆ°€‰É•…Ñ•}…Ñ•½Éäˆ°€‰É•½Ù•É}…Ñ•½Éäˆ°€‰É•¥ÍÑ•É}½‘”ˆ°€‰É•½Ù•É}½‘”ˆ°€‰‰É½İÍ”ˆ°€‰¥¹Ù…±¥‘…Ñ”ˆ°€‰ÍÕ‰µ¥Ñ}É•Ù¥•Üˆ°€‰É•½Ù•É}É•Ù¥•Üˆ°€‰µ…¹¥™•ÍĞˆ°€‰Í…Ù”ˆ°€‰ÍÑ…ÑÕÌˆ°€‰ÍÑ…ÉÑ}‰…­ÕÀˆ°€‰É•½¹¹•Ğˆ°€‰…µ•É…}ÍÑ…ÑÕÌˆ°€‰¡…¹‘±”ˆ°€‰½¹”ˆ°€‰½Á•É…Ñ¥½¹}ÍÑ…ÑÕÌˆ°€‰É•½Ù•Éå}É½İÌˆ°€‰Á½ÍÑ}…Ñ¥½¸ˆ°€‰É•ÅÕ•ÍÑ}É½Üˆ°€‰¡¥ÍÑ½Éäˆ°€‰É•…Ñ•}…½Õ¹Ğˆ°€‰•Ñ}ÁÉ½™¥±”ˆ°€‰ÕÁ‘…Ñ•}ÁÉ½™¥±”ˆ°€‰É•…Ñ¥½¹}¥¹ÁÕĞˆ°€‰ÁÉ½™¥±•}¥¹ÁÕĞˆ°€‰ÁÉ•Ù¥•Üˆ°€‰ÁÉ¥¹Ñ}±…‰•°ˆ°€‰ÁÉ¥¹Ñ}‰…‘”ˆ°€‰É•½Ù•É}ÁÉ¥¹Ğˆ°€‰ÁÉ½‰”ˆ°€‰Á…Á•Èˆ°€‰ÍÕ‰µ¥Ñ}ÁÉ½‰±•´ˆ°€‰É•½Ù•É}ÁÉ½‰±•´ˆ°€‰ÍÕ‰µ¥Ñ}¹½Ñ”ˆ°€‰É•½Ù•É}¹½Ñ”ˆ°€‰ÍÕ‰µ¥Ğˆ°€‰É•½Ù•É}É•…Ñ¥½¸ˆ°€‰Í…µ•}½É¥¥¸ˆ°€‰ÑÉÕÍÑ•‘}¹…Ñ¥Ù•}½É¥¥¹Ìˆ°€‰µ½Ù•}±½…Ñ¥½¸ˆ°€‰ÍÕ‰µ¥Ñ}Í¡•±™}½É‘•Èˆ°€‰É•½Ù•É}Í¡•±™}½É‘•Èˆ°€‰‰Õ¥±‘}Ù¥•Üˆ°€‰É•Í½±Ù•}İ½É­Í¡½Á}½‘”ˆ°€‰…Ñ…±½œˆ°€‰±½½­ÕÀˆ°€‰½¹‘¥Ñ¥½¸ˆ°€‰¡•­½ÕÑ}‰±½­•Èˆ°€‰Í•Ñ}½¹‘¥Ñ¥½¸ˆ¤è(€€€€€€€€€€€€€€€Í•Ñ…ÑÑÈ¡™…­”°Íåµ‰½°°±…µ‰‘„€©…ÉÌ°€¨©­İ…ÉÌè9½¹”¤(€€€€€€€€€€€™…­•}µ½‘Õ±•Ím¹…µ•t€ô™…­”(€€€€€€€•¹Ø€ôì‰]=I-M!=A}I==PˆèÍÑÈ¡ÉÕ¹Ñ¥µ•}É½½Ğ¤°€‰]=I-M!=A}=}I==PˆèÍÑÈ¡½‘•}É½½Ğ¤°(€€€€€€€€€€€€€€€‰]=I-M!=A}1	1}MMQ}I==PˆèÍÑÈ¡ÍÑ…±•}…ÍÍ•ÑÌ¥ô(€€€€€€€½É¥¥¹…±}Á…Ñ €ô±¥ÍĞ¡ÍåÌ¹Á…Ñ ¤(€€€€€€€•¹Ù}‰•™½É”€ôí­•äè½Ì¹•¹Ù¥É½¸¹•Ğ¡­•ä¤™½È­•ä¥¸•¹Ùô(€€€€€€€¡…É‘İ…É•}‰•™½É”€ôÍåÌ¹µ½‘Õ±•Ì¹•Ğ ‰¡…É‘İ…É”ˆ¤(€€€€€€€ÑÉäè(€€€€€€€€€€€İ¥Ñ Á…Ñ ¹‘¥Ğ¡½Ì¹•¹Ù¥É½¸°•¹Ø°±•…Èõ…±Í”¤°Á…Ñ ¹‘¥Ğ¡ÍåÌ¹µ½‘Õ±•Ì°™…­•}µ½‘Õ±•Ì¤è(€€€€€€€€€€€€€€€ÍåÌ¹µ½‘Õ±•Ì¹Á½À ‰¡…É‘İ…É”ˆ°9½¹”¤(€€€€€€€€€€€€€€€Í½ÕÉ”€ô€¡I==P€¼€‰‘•Á±½ä½­¥½Í¬µÍ•ÉÙ•È¹Áäˆ¤¹É•…‘}Ñ•áĞ ¤(€€€€€€€€€€€€€€€Í½ÕÉ”€ôÍ½ÕÉ”¹É•Á±…” (€€€€€€€€€€€€€€€€€€€€‰}™¥áÑÕÉ•}Í•ÉÙ•ÈõQ¡É•…‘¥¹!QQAM•ÉÙ•È ¡}™¥áÑÕÉ•}¡½ÍĞ±}™¥áÑÕÉ•}Á½ÉĞ¤±!…¹‘±•È¤ˆ°(€€€€€€€€€€€€€€€€€€€€‰}™¥áÑÕÉ•}Í•ÉÙ•Èõ}}¥µÁ½ÉÑ}| ÑåÁ•Ìœ¤¹M¥µÁ±•9…µ•ÍÁ…”¡Í•ÉÙ•É}…‘‘É•ÍÌô¡}™¥áÑÕÉ•}¡½ÍĞ±}™¥áÑÕÉ•}Á½ÉĞ¤±Í•ÉÙ•}™½É•Ù•Èõ±…µ‰‘„é9½¹”¤ˆ¤(€€€€€€€€€€€€€€€¹…µ•ÍÁ…”€ôì‰}}¹…µ•}|ˆè€‰­¥½Í­}Í•ÉÙ•É}É•Ù¥•İ}Ñ•ÍĞˆ°€‰}}™¥±•}|ˆèÍÑÈ¡I==P€¼€‰‘•Á±½ä½­¥½Í¬µÍ•ÉÙ•È¹Áäˆ¥ô(€€€€€€€€€€€€€€€•á•Œ¡½µÁ¥±”¡Í½ÕÉ”°¹…µ•ÍÁ…•l‰}}™¥±•}|‰t°€‰•á•Œˆ¤°¹…µ•ÍÁ…”¤(€€€€€€€€€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡¹…µ•ÍÁ…•l‰É•½¹¹•Ñ}¡…É‘İ…É”‰t ‰…µ•É„ˆ¤°€‰‘ÕÉ…‰±”µÉÕ¹Ñ¥µ”µ½Áäˆ¤(€€€€€€€€€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡ÍåÌ¹µ½‘Õ±•Íl‰¡…É‘İ…É”‰t¹}}™¥±•}|°ÍÑÈ¡‘•Á•¹‘•¹å}É½½Ğ€¼€‰¡…É‘İ…É”¹Áäˆ¤¤(€€€€€€€€€€€€€€€Í•±˜¹…ÍÍ•ÉÑ%¸¡ÍÑÈ¡½‘•}É½½Ğ€¼€‰­¥½Í¬ˆ¤°ÍåÌ¹Á…Ñ ¤(€€€€€€€€€€€€€€€Í•±˜¹…ÍÍ•ÉÑ%¸¡ÍÑÈ¡‘•Á•¹‘•¹å}É½½Ğ¤°ÍåÌ¹Á…Ñ ¤(€€€€€€€€€€€€€€€Í•±˜¹…ÍÍ•ÉÑ9½Ñ%¸¡ÍÑÈ¡½‘•}É½½Ğ€¼€‰İ½É¬½¡…É‘İ…É”½ÁåÑ¡½¸ˆ¤°ÍåÌ¹Á…Ñ ¤(€€€€€€€€€€€€€€€Í•±˜¹…ÍÍ•ÉÑ%¸¡ÍÑÈ¡½‘•}É½½Ğ€¼€‰½ÁÌˆ¤°ÍåÌ¹Á…Ñ ¤(€€€€€€€™¥¹…±±äè(€€€€€€€€€€€ÍåÌ¹Á…Ñ¡lét€ô½É¥¥¹…±}Á…Ñ (€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡¹…µ•ÍÁ…•l‰I==P‰t°ÉÕ¹Ñ¥µ•}É½½Ğ¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡¹…µ•ÍÁ…•l‰1	1}MMQ}I==P‰t°½‘•}É½½Ğ€¼€‰±…‰•°µÕ¤ˆ¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡¹…µ•ÍÁ…•l‰½ÁÍ}Á…Ñ ‰t°ÉÕ¹Ñ¥µ•}É½½Ğ€¼€‰İ½É¬½½ÁÌˆ¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡ÍåÌ¹Á…Ñ °½É¥¥¹…±}Á…Ñ ¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡í­•äè½Ì¹•¹Ù¥É½¸¹•Ğ¡­•ä¤™½È­•ä¥¸•¹Ùô°•¹Ù}‰•™½É”¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑ%Ì¡ÍåÌ¹µ½‘Õ±•Ì¹•Ğ ‰¡…É‘İ…É”ˆ¤°¡…É‘İ…É•}‰•™½É”¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑ9½Ñ%¸ ‰Ñ•Éµ¥¹…±}…ÍÍ•ÑÌˆ°¹…µ•ÍÁ…”¤((€€€‘•˜Ñ•ÍÑ}ÍåÍÑ•µ}ÍÑ…ÑÕÍ}…¹‘}‰…­ÕÁ}Á…Ñ¡Í}ÕÍ•}ÉÕ¹Ñ¥µ•}É½½Ğ¡Í•±˜¤è(€€€€€€€|°É•±•…Í”€ôÍ•±˜¹µ…­•}‰Õ¹‘±” ‰ÍÑ…ÑÕÌµÉ½½Ğˆ°€‰ÍÑ…ÑÕÌµµ…É­•Èˆ¤(€€€€€€€ÉÕ¹Ñ¥µ•}É½½Ğ€ôÍ•±˜¹É½½Ğ€¼€‰ÉÕ¹Ñ¥µ”µÍÑ…ÑÕÌˆ(€€€€€€€€¡ÉÕ¹Ñ¥µ•}É½½Ğ€¼€‰İ½É¬ˆ¤¹µ­‘¥È¡Á…É•¹ÑÌõQÉÕ”¤(€€€€€€€™…­•}±•‘•È€ôÑåÁ•Ì¹5½‘Õ±•QåÁ” ‰±•‘•Èˆ¤(€€€€€€€™…­•}±•‘•È¹ÕÕ¥€ô±…µ‰‘„Ù…±Õ”èÙ…±Õ”(€€€€€€€™…­•}±•‘•È¹½¹™±¥Ğ€ôÑåÁ” ‰½¹™±¥Ğˆ°€¡á•ÁÑ¥½¸°¤°íô¤(€€€€€€€™…­•}¡…É‘İ…É”€ôÑåÁ•Ì¹5½‘Õ±•QåÁ” ‰¡…É‘İ…É”ˆ¤(€€€€€€€™…­•}¡…É‘İ…É”¹É•½¹¹•Ğ€ô±…µ‰‘„‘•Ù¥”èì‰‘•Ù¥”ˆè‘•Ù¥•ô(€€€€€€€™…­•}¡…É‘İ…É”¹…µ•É…}ÍÑ…ÑÕÌ€ô±…µ‰‘„èì‰…µ•É„ˆè€‰Íå¹Ñ¡•Ñ¥Œ‰ô(€€€€€€€İ¥Ñ Á…Ñ ¹‘¥Ğ¡½Ì¹•¹Ù¥É½¸°ì‰]=I-M!=A}I==PˆèÍÑÈ¡ÉÕ¹Ñ¥µ•}É½½Ğ¥ô°±•…Èõ…±Í”¤°p(€€€€€€€€€€€€Á…Ñ ¹‘¥Ğ¡ÍåÌ¹µ½‘Õ±•Ì°ì‰±•‘•Èˆè™…­•}±•‘•È°€‰¡…É‘İ…É”ˆè™…­•}¡…É‘İ…É•ô¤è(€€€€€€€€€€€ÍÁ•Œ€ô¥µÁ½ÉÑ±¥ˆ¹ÕÑ¥°¹ÍÁ•}™É½µ}™¥±•}±½…Ñ¥½¸ ‰Í•±•Ñ•‘}ÍåÍÑ•µ}ÍÑ…ÑÕÌˆ°É•±•…Í”€¼€‰½ÁÌ½ÍåÍÑ•µ}ÍÑ…ÑÕÌ¹Áäˆ¤(€€€€€€€€€€€µ½‘Õ±”€ô¥µÁ½ÉÑ±¥ˆ¹ÕÑ¥°¹µ½‘Õ±•}™É½µ}ÍÁ•Œ¡ÍÁ•Œ¤(€€€€€€€€€€€ÍÁ•Œ¹±½…‘•È¹•á•}µ½‘Õ±”¡µ½‘Õ±”¤(€€€€€€€Á…Ñ¡Ì€ômt(€€€€€€€‘¥Í¬€ôÑåÁ•Ì¹M¥µÁ±•9…µ•ÍÁ…”¡™É•”ôÌ€¨€ÄÀÈĞ¨¨Ì°Ñ½Ñ…°ôà€¨€ÄÀÈĞ¨¨Ì¤(€€€€€€€±½‰}Á…Ñ¡Ì€ômt(€€€€€€€‘•˜™…­•}±½ˆ¡Á…Ñ °Á…ÑÑ•É¸¤è(€€€€€€€€€€€±½‰}Á…Ñ¡Ì¹…ÁÁ•¹ ¡Á…Ñ °Á…ÑÑ•É¸¤¤(€€€€€€€€€€€É•ÑÕÉ¸mt(€€€€€€€İ¥Ñ Á…Ñ ¹½‰©•Ğ¡µ½‘Õ±”¹Í¡ÕÑ¥°°€‰‘¥Í­}ÕÍ…”ˆ°Í¥‘•}•™™•Ğõ±…µ‰‘„Á…Ñ èÁ…Ñ¡Ì¹…ÁÁ•¹¡Á…Ñ ¤½È‘¥Í¬¤°p(€€€€€€€€€€€€Á…Ñ ¹½‰©•Ğ¡µ½‘Õ±”°€‰Õ¹¥Ğˆ°É•ÑÕÉ¹}Ù…±Õ”ô‰¥¹…Ñ¥Ù”ˆ¤°p(€€€€€€€€€€€€Á…Ñ ¹½‰©•Ğ¡µ½‘Õ±”°€‰É•½¹¹•Ğˆ°É•ÑÕÉ¹}Ù…±Õ”õì‰‘•Ù¥”ˆè€‰ÁÉ¥¹Ñ•È‰ô¤°p(€€€€€€€€€€€€Á…Ñ ¹½‰©•Ğ¡µ½‘Õ±”°€‰…µ•É…}ÍÑ…ÑÕÌˆ°É•ÑÕÉ¹}Ù…±Õ”õì‰…µ•É„ˆè€‰Íå¹Ñ¡•Ñ¥Œ‰ô¤°p(€€€€€€€€€€€€Á…Ñ ¹½‰©•Ğ¡µ½‘Õ±”¹Á…Ñ¡±¥ˆ¹A…Ñ °€‰±½ˆˆ°™…­•}±½ˆ¤è(€€€€€€€€€€€µ½‘Õ±”¹ÍÑ…ÑÕÌ ¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡Á…Ñ¡Ì°mÉÕ¹Ñ¥µ•}É½½Ñt¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡µ½‘Õ±”¹MQQ°ÉÕ¹Ñ¥µ•}É½½Ğ€¼€‰İ½É¬½‰…­ÕÀµÍÑ…ÑÕÌ¹©Í½¸ˆ¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑ%¸ ¡ÉÕ¹Ñ¥µ•}É½½Ğ€¼€‰İ½É¬½‰…­ÕÁÌˆ°€‰‘•Á±½åµ•¹Ğ´¨¹Ñ…È¹èˆ¤°±½‰}Á…Ñ¡Ì¤(€€€€€€€…±±Ì€ômt(€€€€€€€İ¥Ñ Á…Ñ ¹½‰©•Ğ¡µ½‘Õ±”¹ÍÕ‰ÁÉ½•ÍÌ°€‰ÉÕ¸ˆ°Í¥‘•}•™™•Ğõ±…µ‰‘„½µµ…¹°€¨©­İ…ÉÌè…±±Ì¹…ÁÁ•¹¡½µµ…¹¤¤°p(€€€€€€€€€€€€Á…Ñ ¹½‰©•Ğ¡µ½‘Õ±”°€‰Õ¹¥Ğˆ°É•ÑÕÉ¹}Ù…±Õ”ô‰¥¹…Ñ¥Ù”ˆ¤è(€€€€€€€€€€€µ½‘Õ±”¹ÍÑ…ÉÑ}‰…­ÕÀ ‰É•ÅÕ•ÍĞµ­•äˆ¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡…±±ÍlÁul´Åt°ÍÑÈ¡ÉÕ¹Ñ¥µ•}É½½Ğ€¼€‰‘•Á±½ä½‰…­ÕÀµ‘•Á±½åµ•¹Ğ¹Áäˆ¤¤((€€€‘•˜Ñ•ÍÑ}¥¹Ù…±¥‘}½µÁ½¹•¹Ñ}½É}‰Õ¹‘±•}¹•Ù•É}±…Õ¹¡•Ì¡Í•±˜¤è(€€€€€€€Í½ÕÉ”°É•±•…Í”€ôÍ•±˜¹µ…­•}‰Õ¹‘±” ‰¥¹Ù…±¥ˆ°€‰¥¹Ù…±¥µµ…É­•Èˆ¤(€€€€€€€ÉÕ¹Ñ¥µ•}É½½Ğ€ôÍ•±˜¹É½½Ğ€¼€‰ÉÕ¹Ñ¥µ”µ¥¹Ù…±¥ˆ(€€€€€€€Í•±˜¹Í•±•Ğ¡ÉÕ¹Ñ¥µ•}É½½Ğ°É•±•…Í”¤(€€€€€€€İ¥Ñ Í•±˜¹…ÍÍ•ÉÑI…¥Í•Ì¡Y…±Õ•ÉÉ½È¤è(€€€€€€€€€€€É•±•…Í•}½µµ…¹¡ÉÕ¹Ñ¥µ•}É½½Ğ°€‰ÁÉ¥¹Ñ•Èˆ¤(€€€€€€€İ¥Ñ Í•±˜¹…ÍÍ•ÉÑI…¥Í•Ì¡	Õ¹‘±•ÉÉ½È¤è(€€€€€€€€€€€É•±•…Í•}½µµ…¹¡ÉÕ¹Ñ¥µ•}É½½Ğ°€‰¹…Ñ¥Ù”ˆ°É•±•…Í”õÍ•±˜¹É½½Ğ€¼€‰µ¥ÍÍ¥¹œˆ¤(€€€€€€€ÁÕ‰±¥Œ€ôÉ•±•…Í”€¼€‰ÁÕ‰±¥Œ½¥¹‘•à¹¡Ñµ°ˆ(€€€€€€€É•±•…Í”¹¡µ½ Á¼ÜÔÔ¤(€€€€€€€€¡É•±•…Í”€¼€‰ÁÕ‰±¥Œˆ¤¹¡µ½ Á¼ÜÔÔ¤(€€€€€€€ÁÕ‰±¥Œ¹¡µ½ Á¼ØĞĞ¤(€€€€€€€ÁÕ‰±¥Œ¹Õ¹±¥¹¬ ¤(€€€€€€€€¡É•±•…Í”€¼€‰ÁÕ‰±¥Œˆ¤¹¡µ½ Á¼ÔÔÔ¤(€€€€€€€É•±•…Í”¹¡µ½ Á¼ÔÔÔ¤(€€€€€€€…±±Ì€ômt(€€€€€€€±…Õ¹¡•È€ôÉ•±•…Í”€¼€‰‘•Á±½ä½ÉÕ¸µÉ•±•…Í”¹Áäˆ(€€€€€€€İ¥Ñ Á…Ñ ¹½‰©•Ğ¡ÍåÌ°€‰…ÉØˆ°mÍÑÈ¡±…Õ¹¡•È¤°€‰…Ñ•İ…ä‰t¤°p(€€€€€€€€€€€€Á…Ñ ¹‘¥Ğ¡½Ì¹•¹Ù¥É½¸°ì‰]=I-M!=A}I==PˆèÍÑÈ¡ÉÕ¹Ñ¥µ•}É½½Ğ¥ô°±•…Èõ…±Í”¤°p(€€€€€€€€€€€€Á…Ñ  ‰½Ì¹•á•ÙÁ”ˆ°Í¥‘•}•™™•Ğõ±…µ‰‘„€©…ÉÌè…±±Ì¹…ÁÁ•¹¡…ÉÌ¤¤è(€€€€€€€€€€€İ¥Ñ Í•±˜¹…ÍÍ•ÉÑI…¥Í•Ì¡Y…±Õ•ÉÉ½È¤è(€€€€€€€€€€€€€€€ÉÕ¹Áä¹ÉÕ¹}Á…Ñ ¡ÍÑÈ¡±…Õ¹¡•È¤°ÉÕ¹}¹…µ”ô‰}}µ…¥¹}|ˆ¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡…±±Ì°mt¤((€€€‘•˜Ñ•ÍÑ}Ñ…µÁ•É•‘}¡•±Á•É}¥Í}É•©•Ñ•‘}‰•™½É•}•á•ÕÑ¥½¸¡Í•±˜¤è(€€€€€€€|°É•±•…Í”€ôÍ•±˜¹µ…­•}‰Õ¹‘±” ‰Ñ…µÁ•É•µ¡•±Á•Èˆ°€‰¡•±Á•Èµµ…É­•Èˆ¤(€€€€€€€ÉÕ¹Ñ¥µ•}É½½Ğ€ôÍ•±˜¹É½½Ğ€¼€‰ÉÕ¹Ñ¥µ”µÑ…µÁ•É•ˆ(€€€€€€€Í•±˜¹Í•±•Ğ¡ÉÕ¹Ñ¥µ•}É½½Ğ°É•±•…Í”¤(€€€€€€€Í•¹Ñ¥¹•°€ôÍ•±˜¹É½½Ğ€¼€‰¡•±Á•Èµ•á•ÕÑ•ˆ(€€€€€€€¡•±Á•È€ôÉ•±•…Í”€¼€‰‘•Á±½ä½É•±•…Í•}‰Õ¹‘±”¹Áäˆ(€€€€€€€¡•±Á•È¹¡µ½ Á¼ØĞĞ¤(€€€€€€€¡•±Á•È¹İÉ¥Ñ•}Ñ•áĞ¡˜‰™É½´Á…Ñ¡±¥ˆ¥µÁ½ÉĞA…Ñ¡q¹A…Ñ ¡íÍÑÈ¡Í•¹Ñ¥¹•°¤…Éô¤¹Ñ½Õ  ¥q¸ˆ¤(€€€€€€€¡•±Á•È¹¡µ½ Á¼ĞĞĞ¤(€€€€€€€…±±Ì€ômt(€€€€€€€±…Õ¹¡•È€ôÉ•±•…Í”€¼€‰‘•Á±½ä½ÉÕ¸µÉ•±•…Í”¹Áäˆ(€€€€€€€İ¥Ñ Á…Ñ ¹½‰©•Ğ¡ÍåÌ°€‰…ÉØˆ°mÍÑÈ¡±…Õ¹¡•È¤°€‰…Ñ•İ…ä‰t¤°p(€€€€€€€€€€€€Á…Ñ ¹‘¥Ğ¡½Ì¹•¹Ù¥É½¸°ì‰]=I-M!=A}I==PˆèÍÑÈ¡ÉÕ¹Ñ¥µ•}É½½Ğ¥ô°±•…Èõ…±Í”¤°p(€€€€€€€€€€€€Á…Ñ  ‰½Ì¹•á•ÙÁ”ˆ°Í¥‘•}•™™•Ğõ±…µ‰‘„€©…ÉÌè…±±Ì¹…ÁÁ•¹¡…ÉÌ¤¤è(€€€€€€€€€€€İ¥Ñ Í•±˜¹…ÍÍ•ÉÑI…¥Í•Ì¡Y…±Õ•ÉÉ½È¤è(€€€€€€€€€€€€€€€ÉÕ¹Áä¹ÉÕ¹}Á…Ñ ¡ÍÑÈ¡±…Õ¹¡•È¤°ÉÕ¹}¹…µ”ô‰}}µ…¥¹}|ˆ¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑ…±Í”¡Í•¹Ñ¥¹•°¹•á¥ÍÑÌ ¤¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡…±±Ì°mt¤((€€€‘•˜Ñ•ÍÑ}µ…¹¥™•ÍÑ}…¹¹½Ñ}…ÕÑ¡½É¥é•}¡•±Á•É}¹½Ñ}‰½Õ¹‘}‰å}É••¥ÁÑÌ¡Í•±˜¤è(€€€€€€€|°É•±•…Í”€ôÍ•±˜¹µ…­•}‰Õ¹‘±” ‰É••¥ÁĞµ¡•±Á•Èˆ°€‰É••¥ÁĞµµ…É­•Èˆ¤(€€€€€€€ÉÕ¹Ñ¥µ•}É½½Ğ€ôÍ•±˜¹É½½Ğ€¼€‰ÉÕ¹Ñ¥µ”µÉ••¥ÁĞµ¡•±Á•Èˆ(€€€€€€€Í•±˜¹Í•±•Ğ¡ÉÕ¹Ñ¥µ•}É½½Ğ°É•±•…Í”¤(€€€€€€€Í•¹Ñ¥¹•°€ôÍ•±˜¹É½½Ğ€¼€‰É••¥ÁĞµ¡•±Á•Èµ•á•ÕÑ•ˆ(€€€€€€€¡•±Á•È€ôÉ•±•…Í”€¼€‰‘•Á±½ä½É•±•…Í•}‰Õ¹‘±”¹Áäˆ(€€€€€€€µ…¹¥™•ÍÑ}Á…Ñ €ôÉ•±•…Í”€¼€‰µ…¹¥™•ÍĞ¹©Í½¸ˆ(€€€€€€€É•±•…Í”¹¡µ½ Á¼ÜÔÔ¤(€€€€€€€¡•±Á•È¹¡µ½ Á¼ØĞĞ¤(€€€€€€€¡•±Á•È¹İÉ¥Ñ•}Ñ•áĞ¡˜‰™É½´Á…Ñ¡±¥ˆ¥µÁ½ÉĞA…Ñ¡q¹A…Ñ ¡íÍÑÈ¡Í•¹Ñ¥¹•°¤…Éô¤¹Ñ½Õ  ¥q¸ˆ¤(€€€€€€€¡•±Á•È¹¡µ½ Á¼ĞĞĞ¤(€€€€€€€µ…¹¥™•ÍĞ€ô©Í½¸¹±½…‘Ì¡µ…¹¥™•ÍÑ}Á…Ñ ¹É•…‘}Ñ•áĞ ¤¤(€€€€€€€µ…¹¥™•ÍÑl‰™¥±•Ì‰ul‰‘•Á±½ä½É•±•…Í•}‰Õ¹‘±”¹Áä‰ul‰Í¡„ÈÔØ‰t€ôÍ¡…}‰åÑ•Ì¡¡•±Á•È¹É•…‘}‰åÑ•Ì ¤¤(€€€€€€€µ…¹¥™•ÍÑ}Á…Ñ ¹¡µ½ Á¼ØĞĞ¤(€€€€€€€µ…¹¥™•ÍÑ}Á…Ñ ¹İÉ¥Ñ•}Ñ•áĞ¡©Í½¸¹‘ÕµÁÌ¡µ…¹¥™•ÍĞ°Í½ÉÑ}­•åÌõQÉÕ”°¥¹‘•¹ĞôÈ¤€¬€‰q¸ˆ¤(€€€€€€€µ…¹¥™•ÍÑ}Á…Ñ ¹¡µ½ Á¼ĞĞĞ¤(€€€€€€€É•±•…Í”¹¡µ½ Á¼ÔÔÔ¤(€€€€€€€…±±Ì€ômt(€€€€€€€±…Õ¹¡•È€ôÉ•±•…Í”€¼€‰‘•Á±½ä½ÉÕ¸µÉ•±•…Í”¹Áäˆ(€€€€€€€İ¥Ñ Á…Ñ ¹½‰©•Ğ¡ÍåÌ°€‰…ÉØˆ°mÍÑÈ¡±…Õ¹¡•È¤°€‰…Ñ•İ…ä‰t¤°p(€€€€€€€€€€€€Á…Ñ ¹‘¥Ğ¡½Ì¹•¹Ù¥É½¸°ì‰]=I-M!=A}I==PˆèÍÑÈ¡ÉÕ¹Ñ¥µ•}É½½Ğ¥ô°±•…Èõ…±Í”¤°p(€€€€€€€€€€€€Á…Ñ  ‰½Ì¹•á•ÙÁ”ˆ°Í¥‘•}•™™•Ğõ±…µ‰‘„€©…ÉÌè…±±Ì¹…ÁÁ•¹¡…ÉÌ¤¤è(€€€€€€€€€€€İ¥Ñ Í•±˜¹…ÍÍ•ÉÑI…¥Í•Ì¡Y…±Õ•ÉÉ½È¤è(€€€€€€€€€€€€€€€ÉÕ¹Áä¹ÉÕ¹}Á…Ñ ¡ÍÑÈ¡±…Õ¹¡•È¤°ÉÕ¹}¹…µ”ô‰}}µ…¥¹}|ˆ¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑ…±Í”¡Í•¹Ñ¥¹•°¹•á¥ÍÑÌ ¤¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡…±±Ì°mt¤((€€€‘•˜Ñ•ÍÑ}Íåµ±¥¹­•‘}‘•Á±½å}‘¥É•Ñ½Éå}¥Í}É•©•Ñ•‘}‰•™½É•}É•…‘Ì¡Í•±˜¤è(€€€€€€€|°É•±•…Í”€ôÍ•±˜¹µ…­•}‰Õ¹‘±” ‰±¥¹­•µ‘•Á±½äˆ°€‰‘•Á±½äµµ…É­•Èˆ¤(€€€€€€€ÉÕ¹Ñ¥µ•}É½½Ğ€ôÍ•±˜¹É½½Ğ€¼€‰ÉÕ¹Ñ¥µ”µ±¥¹­•µ‘•Á±½äˆ(€€€€€€€Í•±˜¹Í•±•Ğ¡ÉÕ¹Ñ¥µ•}É½½Ğ°É•±•…Í”¤(€€€€€€€‘•Á±½ä€ôÉ•±•…Í”€¼€‰‘•Á±½äˆ(€€€€€€€½ÕÑÍ¥‘”€ôÍ•±˜¹É½½Ğ€¼€‰•áÑ•É¹…°µ‘•Á±½äˆ(€€€€€€€‘•Á±½ä¹¡µ½ Á¼ÜÔÔ¤(€€€€€€€É•±•…Í”¹¡µ½ Á¼ÜÔÔ¤(€€€€€€€‘•Á±½ä¹É•¹…µ”¡½ÕÑÍ¥‘”¤(€€€€€€€‘•Á±½ä¹Íåµ±¥¹­}Ñ¼¡½ÕÑÍ¥‘”°Ñ…É•Ñ}¥Í}‘¥É•Ñ½ÉäõQÉÕ”¤(€€€€€€€É•±•…Í”¹¡µ½ Á¼ÔÔÔ¤(€€€€€€€½Á•¹•€ôÍ•±˜¹ÉÕ¹}±…Õ¹¡•É}µ…¥¹}İ¥Ñ¡}É•…‘}ÍÁä (€€€€€€€€€€€É•±•…Í”°ÉÕ¹Ñ¥µ•}É½½Ğ°íÉ•±•…Í”€¼€‰µ…¹¥™•ÍĞ¹©Í½¸ˆ°É•±•…Í”€¼€‰‘•Á±½ä½É•±•…Í•}‰Õ¹‘±”¹Áä‰ô¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡½Á•¹•°mt¤((€€€‘•˜Ñ•ÍÑ}¡…É‘±¥¹­•‘}µ…¹¥™•ÍÑ}…¹‘}¡•±Á•É}…É•}É•©•Ñ•‘}‰•™½É•}Ñ¡•¥É}É•…‘Ì¡Í•±˜¤è(€€€€€€€™½È¹…µ”°Ñ…É•Ñ}¹…µ”¥¸€  ‰¡…É‘±¥¹­•µµ…¹¥™•ÍĞˆ°€‰µ…¹¥™•ÍĞ¹©Í½¸ˆ¤°(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€ ‰¡…É‘±¥¹­•µ¡•±Á•Èˆ°€‰‘•Á±½ä½É•±•…Í•}‰Õ¹‘±”¹Áäˆ¤¤è(€€€€€€€€€€€İ¥Ñ Í•±˜¹ÍÕ‰Q•ÍĞ¡Ñ…É•ĞõÑ…É•Ñ}¹…µ”¤è(€€€€€€€€€€€€€€€|°É•±•…Í”€ôÍ•±˜¹µ…­•}‰Õ¹‘±”¡¹…µ”°¹…µ”¤(€€€€€€€€€€€€€€€ÉÕ¹Ñ¥µ•}É½½Ğ€ôÍ•±˜¹É½½Ğ€¼˜‰ÉÕ¹Ñ¥µ”µí¹…µ•ôˆ(€€€€€€€€€€€€€€€Í•±˜¹Í•±•Ğ¡ÉÕ¹Ñ¥µ•}É½½Ğ°É•±•…Í”¤(€€€€€€€€€€€€€€€Ñ…É•Ğ€ôÉ•±•…Í”€¼Ñ…É•Ñ}¹…µ”(€€€€€€€€€€€€€€€½ÕÑÍ¥‘”€ôÍ•±˜¹É½½Ğ€¼˜‰í¹…µ•ôµ½ÕÑÍ¥‘”ˆ(€€€€€€€€€€€€€€€½Ì¹±¥¹¬¡Ñ…É•Ğ°½ÕÑÍ¥‘”¤(€€€€€€€€€€€€€€€½Á•¹•€ôÍ•±˜¹ÉÕ¹}±…Õ¹¡•É}µ…¥¹}İ¥Ñ¡}É•…‘}ÍÁä¡É•±•…Í”°ÉÕ¹Ñ¥µ•}É½½Ğ°íÑ…É•Ñô¤(€€€€€€€€€€€€€€€Í•±˜¹…ÍÍ•ÉÑ9½Ñ%¸¡Ñ…É•Ğ°½Á•¹•¤((€€€‘•˜Ñ•ÍÑ}¥¹Ù…±¥‘}½µÁ½¹•¹Ñ}¥Í}É•©•Ñ•‘}‰•™½É•}¡•±Á•É}±½…‘¥¹œ¡Í•±˜¤è(€€€€€€€|°É•±•…Í”€ôÍ•±˜¹µ…­•}‰Õ¹‘±” ‰¥¹Ù…±¥µ™¥ÉÍĞˆ°€‰½µÁ½¹•¹Ğµµ…É­•Èˆ¤(€€€€€€€ÉÕ¹Ñ¥µ•}É½½Ğ€ôÍ•±˜¹É½½Ğ€¼€‰ÉÕ¹Ñ¥µ”µ¥¹Ù…±¥µ™¥ÉÍĞˆ(€€€€€€€Í•±˜¹Í•±•Ğ¡ÉÕ¹Ñ¥µ•}É½½Ğ°É•±•…Í”¤(€€€€€€€¡•±Á•È€ôÉ•±•…Í”€¼€‰‘•Á±½ä½É•±•…Í•}‰Õ¹‘±”¹Áäˆ(€€€€€€€¡•±Á•È¹¡µ½ Á¼ØĞĞ¤(€€€€€€€¡•±Á•È¹İÉ¥Ñ•}Ñ•áĞ ‰¥¹Ù…±¥¡•±Á•È‰åÑ•Íq¸ˆ¤(€€€€€€€¡•±Á•È¹¡µ½ Á¼ĞĞĞ¤(€€€€€€€±…Õ¹¡•È€ôÉ•±•…Í”€¼€‰‘•Á±½ä½ÉÕ¸µÉ•±•…Í”¹Áäˆ(€€€€€€€İ¥Ñ Á…Ñ ¹½‰©•Ğ¡ÍåÌ°€‰…ÉØˆ°mÍÑÈ¡±…Õ¹¡•È¤°€‰ÁÉ¥¹Ñ•È‰t¤°p(€€€€€€€€€€€€Á…Ñ ¹‘¥Ğ¡½Ì¹•¹Ù¥É½¸°ì‰]=I-M!=A}I==PˆèÍÑÈ¡ÉÕ¹Ñ¥µ•}É½½Ğ¥ô°±•…Èõ…±Í”¤è(€€€€€€€€€€€İ¥Ñ Í•±˜¹…ÍÍ•ÉÑI…¥Í•ÍI••à¡Y…±Õ•ÉÉ½È°€‰Õ¹­¹½İ¸É•±•…Í”½µÁ½¹•¹Ğˆ¤è(€€€€€€€€€€€€€€€ÉÕ¹Áä¹ÉÕ¹}Á…Ñ ¡ÍÑÈ¡±…Õ¹¡•È¤°ÉÕ¹}¹…µ”ô‰}}µ…¥¹}|ˆ¤(()¥˜}}¹…µ•}|€ôô€‰}}µ…¥¹}|ˆè(€€€Õ¹¥ÑÑ•ÍĞ¹µ…¥¸ ¤(