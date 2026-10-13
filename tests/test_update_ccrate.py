import hashlib
import importlib.util
import io
import json
import os
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

DEPLOY = Path(__file__).resolve().parents[1] / "deploy"
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(DEPLOY))
sys.path.insert(0, str(TESTS))

if os.name == "nt" and "fcntl" not in sys.modules:
    import types
    fcntl_fixture = types.ModuleType("fcntl")
    fcntl_fixture.LOCK_EX = 1
    fcntl_fixture.LOCK_NB = 2
    fcntl_fixture.LOCK_UN = 4
    fcntl_fixture.flock = lambda *_args, **_kwargs: None
    sys.modules["fcntl"] = fcntl_fixture

TEST_TEMP = TESTS / ".update-test-tmp"
TEST_TEMP.mkdir(exist_ok=True)
tempfile.tempdir = str(TEST_TEMP)

_SPEC = importlib.util.spec_from_file_location("update_ccrate", DEPLOY / "update-ccrate.py")
update_ccrate = importlib.util.module_from_spec(_SPEC)
sys.modules["update_ccrate"] = update_ccrate
_SPEC.loader.exec_module(update_ccrate)
from release_bundle import validate_bundle

if os.name == "nt":
    # Windows ACL filesystems cannot represent the POSIX executable bits in sealed bundles.
    update_ccrate.validate_bundle = lambda package: json.loads(
        (Path(package) / "manifest.json").read_text(encoding="utf-8"))


COMMIT = "a" * 40
TAG = "ccrate-" + COMMIT[:12]
UPSTREAM = "e01dd737238a3fa7e1a6454b37de6c6fc88c86e4"


class Response(io.BytesIO):
    def __init__(self, body, url, headers=None):
        super().__init__(body)
        self.url = url
        self.headers = headers or {}

    def geturl(self):
        return self.url


def response_json(value, url):
    return Response(json.dumps(value).encode(), url, {"Content-Length": str(len(json.dumps(value)))})


class UpdateCcrateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._cleanup_temp, self.temp)
        self.tmp = Path(self.temp.name)
        from test_release_bundle import ReleaseBundleTests
        self.fixture = ReleaseBundleTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self._cleanup_temp, self.fixture.temp)
        (self.fixture.public / "ccrate-release.json").write_text(json.dumps({
            "format": 1, "application": "ccrate", "commit": COMMIT,
            "upstream_pin": UPSTREAM, "built_at": "2026-10-12T00:00:00Z",
        }))
        self.package = self.fixture.root / "release-package"
        self.fixture.stage(self.package)
        self.manifest = json.loads((self.package / "manifest.json").read_text(encoding="utf-8"))
        self.manifest_sha = hashlib.sha256((self.package / "manifest.json").read_bytes()).hexdigest()
        self.root = self.tmp / "install"
        self.root.mkdir()
        (self.root / "work").mkdir()
        (self.root / "work" / "store-sentinel").write_bytes(b"do not change")

    @staticmethod
    def _cleanup_temp(temp):
        root = Path(temp.name)
        if root.exists():
            for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
                if not path.is_symlink():
                    try:
                        path.chmod(0o700 if path.is_dir() else 0o600)
                    except OSError:
                        pass
            try:
                root.chmod(0o700)
            except OSError:
                pass
        temp.cleanup()

    def _archive(self, members=None):
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w:gz") as archive:
            if members is None:
                for path in sorted(self.package.rglob("*")):
                    relative = path.relative_to(self.package).as_posix()
                    info = archive.gettarinfo(str(path), arcname=f"candidate/{relative}")
                    if path.is_file():
                        with path.open("rb") as source:
                            archive.addfile(info, source)
                    else:
                        archive.addfile(info)
            else:
                for name, kind, data in members:
                    info = tarfile.TarInfo(name)
                    if kind == "file":
                        info.size = len(data)
                        archive.addfile(info, io.BytesIO(data))
                    elif kind == "dir":
                        info.type = tarfile.DIRTYPE
                        archive.addfile(info)
                    elif kind == "symlink":
                        info.type = tarfile.SYMTYPE
                        info.linkname = data.decode()
                        archive.addfile(info)
                    elif kind == "hardlink":
                        info.type = tarfile.LNKTYPE
                        info.linkname = data.decode()
                        archive.addfile(info)
                    elif kind == "fifo":
                        info.type = tarfile.FIFOTYPE
                        archive.addfile(info)
        return output.getvalue()

    def _descriptor(self, archive):
        return {
            "format": 1, "application": "ccrate", "architecture": "linux-arm64",
            "commit": COMMIT, "upstream_pin": UPSTREAM,
            "archive": f"ccrate-linux-arm64-{COMMIT[:12]}.tar.gz",
            "compressed_bytes": len(archive), "expanded_bytes": sum(p.stat().st_size for p in self.package.rglob("*") if p.is_file()),
            "sha256": hashlib.sha256(archive).hexdigest(), "manifest_sha256": self.manifest_sha,
        }

    def _release(self, archive=None, descriptor=None):
        archive = self._archive() if archive is None else archive
        descriptor = self._descriptor(archive) if descriptor is None else descriptor
        return {
            "tag": TAG, "descriptor": descriptor,
            "descriptor_asset_url": "https://api.github.com/repos/Spraten/ccrate/releases/assets/1",
            "archive_asset_url": "https://api.github.com/repos/Spraten/ccrate/releases/assets/2",
            "archive_asset_digest": "sha256:" + descriptor["sha256"],
        }, archive

    def _installed_root(self, selected=None):
        root = self.tmp / "installed"
        (root / "work").mkdir(parents=True, exist_ok=True)
        if selected:
            releases = root / "work" / "releases"
            releases.mkdir()
            previous = releases / "previous"
            import shutil
            shutil.copytree(selected, previous)
            current = root / "work" / "application-current"
            current.write_text(str(previous))
            baseline = root / "work" / "baseline"
            (baseline / "data").mkdir(parents=True)
            (baseline / "data" / "homebox.db").write_bytes(b"db")
            (baseline / "pepper").write_text("synthetic")
            (baseline / "test-account.json").write_text("{}")
            (root / "work" / "ops").mkdir()
            (root / "work" / "ops" / "ledger.db").write_bytes(b"ledger")
        return root

    def test_rejects_wrong_repository_tag_digest_or_architecture(self):
        good_archive = self._archive()
        descriptor = self._descriptor(good_archive)
        release_api = "https://api.github.com/repos/Spraten/ccrate/releases/tags/" + TAG
        tag_ref_api = "https://api.github.com/repos/Spraten/ccrate/git/ref/tags/" + TAG
        requests = []

        def opener(request, timeout=None):
            url = request.full_url if hasattr(request, "full_url") else request
            requests.append(url)
            if "/releases/tags/" in url:
                return response_json({"tag_name": TAG, "target_commitish": COMMIT,
                                      "assets": [
                                          {"id": 1, "name": "release.json", "size": len(json.dumps(descriptor).encode()),
                                           "digest": "sha256:" + hashlib.sha256(json.dumps(descriptor).encode()).hexdigest()},
                                          {"id": 2, "name": descriptor["archive"],
                                           "size": len(good_archive), "digest": "sha256:" + descriptor["sha256"]},
                                      ]}, release_api)
            if "/git/ref/tags/" in url:
                return response_json({"object": {"type": "commit", "sha": COMMIT}}, tag_ref_api)
            if url.endswith("/assets/1"):
                body = json.dumps(descriptor).encode()
                return Response(body, url)
            raise AssertionError("Unexpected network request: " + url)

        release = update_ccrate.fetch_release(TAG, opener=opener)
        self.assertEqual(release["descriptor"], descriptor)
        self.assertTrue(all("Spraten/ccrate/" in url for url in requests))
        self.assertEqual(requests[:2], [release_api, tag_ref_api])
        for field, value in (("architecture", "linux-x86_64"),
                             ("commit", "b" * 40),
                             ("sha256", "0" * 64)):
            wrong = dict(descriptor, **{field: value})
            with self.subTest(field=field), self.assertRaises(update_ccrate.UpdateError):
                update_ccrate._validate_descriptor(TAG, wrong, {
                    "name": descriptor["archive"], "size": len(good_archive),
                    "digest": "sha256:" + descriptor["sha256"]})
        wrong_repo = Response(json.dumps({"tag_name": TAG, "target_commitish": COMMIT,
                                           "assets": []}).encode(),
                              "https://api.github.com/repos/attacker/ccrate/releases/tags/" + TAG)
        with self.assertRaises(update_ccrate.UpdateError):
            update_ccrate._decode_release(TAG, wrong_repo)

    def test_partial_download_keeps_active_release(self):
        release, archive = self._release()
        current = self.root / "work" / "application-current"
        current.write_bytes(b"active selector sentinel")
        old_bytes = current.read_bytes()
        before = (self.root / "work" / "store-sentinel").read_bytes()

        def opener(request, timeout=None):
            url = request.full_url if hasattr(request, "full_url") else request
            if url.endswith("/assets/2"):
                return Response(archive[:max(1, len(archive) // 2)], url,
                                {"Content-Length": str(len(archive))})
            raise AssertionError(url)

        with self.assertRaises(update_ccrate.UpdateError):
            update_ccrate.stage_download(self.root, release, opener=opener)
        self.assertEqual(current.read_bytes(), old_bytes)
        self.assertEqual((self.root / "work" / "store-sentinel").read_bytes(), before)
        self.assertEqual(list((self.root / "work" / "update-downloads").glob("*")), [])

    @unittest.skipIf(os.name == "nt", "sealed package directory modes require POSIX rename semantics")
    def test_staged_candidate_is_digest_bound_and_keeps_descriptor(self):
        release, archive = self._release()
        candidate = update_ccrate.stage_download(
            self.root, release,
            opener=lambda request, timeout=None: Response(archive, request.full_url))
        self.assertEqual(candidate.parent.name, TAG + "-" + release["descriptor"]["sha256"][:16])
        self.assertEqual(hashlib.sha256((candidate / "manifest.json").read_bytes()).hexdigest(), self.manifest_sha)
        self.assertEqual(json.loads((candidate.parent / "release.json").read_text()), release["descriptor"])
        self.assertTrue((candidate.parent / release["descriptor"]["archive"]).is_file())

    def test_candidate_requires_artifact_matched_workshop_v2_writer(self):
        capability = self.manifest["provenance"]["workshop_capability"]
        self.assertEqual(capability["read_versions"], [1, 2])
        update_ccrate._require_candidate_writer(self.manifest)
        incompatible = json.loads(json.dumps(self.manifest))
        incompatible["provenance"]["workshop_capability"]["write_mode"] = "v1"
        with self.assertRaises(update_ccrate.UpdateError):
            update_ccrate._require_candidate_writer(incompatible)
        incompatible = json.loads(json.dumps(self.manifest))
        incompatible["provenance"]["test_receipt"]["workshop_compatibility"]["tests"][2]["result"] = "skipped"
        with self.assertRaises(update_ccrate.UpdateError):
            update_ccrate._require_candidate_writer(incompatible)

    def test_tar_escape_links_duplicates_and_devices_are_refused(self):
        cases = {
            "escape": [("candidate/../escape", "file", b"bad")],
            "absolute": [("/candidate/file", "file", b"bad")],
            "symlink": [("candidate/link", "symlink", b"target")],
            "hardlink": [("candidate/link", "hardlink", b"target")],
            "device": [("candidate/device", "fifo", b"")],
            "duplicate": [("candidate/file", "file", b"one"), ("candidate/file", "file", b"two")],
            "second-root": [("candidate/file", "file", b"one"), ("other/file", "file", b"two")],
        }
        for name, members in cases.items():
            with self.subTest(name=name):
                archive = self._archive(members)
                release, _ = self._release(archive)
                before = (self.root / "work" / "store-sentinel").read_bytes()
                with self.assertRaises(update_ccrate.UpdateError):
                    update_ccrate.stage_download(self.root, release,
                                                 opener=lambda request, timeout=None:
                                                 Response(archive, request.full_url))
                self.assertEqual((self.root / "work" / "store-sentinel").read_bytes(), before)
                downloads = self.root / "work" / "update-downloads"
                self.assertFalse(downloads.exists() and any(downloads.iterdir()))

    def test_check_never_stops_services(self):
        root = self._installed_root()
        old = root / "work" / "releases" / "old"
        old.parent.mkdir()
        import shutil
        shutil.copytree(self.package, old)
        (root / "work" / "application-current").write_text(str(old))
        calls = []
        output = StringIO()
        with mock.patch.object(update_ccrate.platform, "machine", return_value="aarch64"), \
             mock.patch.object(update_ccrate.platform, "system", return_value="Linux"), \
             mock.patch.object(update_ccrate, "_current_release", return_value=(old, None)), \
             mock.patch.object(update_ccrate, "_runtime_issues", return_value=[]), \
             mock.patch.object(update_ccrate.shutil, "disk_usage", return_value=SimpleNamespace(free=10**12)), \
             mock.patch.object(update_ccrate, "fetch_release", return_value={"tag": TAG}), \
             mock.patch.object(update_ccrate, "stage_download", return_value=self.package), \
             mock.patch.object(update_ccrate, "apply_update", side_effect=lambda *a, **k: calls.append("apply")), \
             redirect_stdout(output):
            self.assertEqual(update_ccrate.main(["--root", str(root), "--version", TAG, "--check"]), 0)
            result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(result["previous_path"], str(old.resolve()))
        self.assertEqual(calls, [])

    def test_legacy_or_missing_runtime_requires_operator_repair(self):
        candidate = self.package
        empty = self._installed_root()
        result = update_ccrate.preflight(empty, candidate)
        self.assertEqual(result["status"], "migration_required")
        self.assertTrue(result["reasons"])

        legacy = self._installed_root()
        (legacy / "work" / "application-current").write_text("legacy selector")
        result = update_ccrate.preflight(legacy, candidate)
        self.assertEqual(result["status"], "migration_required")

        sealed = self._installed_root()
        with mock.patch.object(update_ccrate.platform, "machine", return_value="x86_64"), \
             mock.patch.object(update_ccrate.platform, "system", return_value="Linux"), \
             mock.patch.object(update_ccrate, "_current_release", return_value=(self.package, None)):
            self.assertEqual(update_ccrate.preflight(sealed, candidate)["status"], "unsupported_arch")
        no_runtime = self._installed_root()
        with mock.patch.object(update_ccrate.platform, "machine", return_value="aarch64"), \
             mock.patch.object(update_ccrate.platform, "system", return_value="Linux"), \
             mock.patch.object(update_ccrate, "_current_release", return_value=(self.package, None)), \
             mock.patch.object(update_ccrate, "_runtime_issues", return_value=["runtime missing"]):
            self.assertEqual(update_ccrate.preflight(no_runtime, candidate)["status"], "runtime_missing")

        small_disk = self._installed_root()
        with mock.patch.object(update_ccrate.platform, "machine", return_value="aarch64"), \
             mock.patch.object(update_ccrate.platform, "system", return_value="Linux"), \
             mock.patch.object(update_ccrate, "_current_release", return_value=(self.package, None)), \
             mock.patch.object(update_ccrate, "_runtime_issues", return_value=[]), \
             mock.patch.object(update_ccrate.shutil, "disk_usage", return_value=SimpleNamespace(free=0)):
            self.assertEqual(update_ccrate.preflight(small_disk, candidate)["status"], "insufficient_space")

    def test_limits_are_explicit_and_rejected_before_large_allocations(self):
        self.assertEqual(update_ccrate.MAX_ARCHIVE_BYTES, 512 * 1024 * 1024)
        self.assertEqual(update_ccrate.MAX_EXPANDED_BYTES, 1024 * 1024 * 1024)
        self.assertEqual(update_ccrate.MAX_MEMBERS, 20_000)
        self.assertEqual(update_ccrate.MAX_DESCRIPTOR_BYTES, 256 * 1024)
        archive = b"tiny"
        descriptor = self._descriptor(archive)
        for field, value in (("compressed_bytes", update_ccrate.MAX_ARCHIVE_BYTES + 1),
                             ("expanded_bytes", update_ccrate.MAX_EXPANDED_BYTES + 1)):
            with self.subTest(field=field), self.assertRaises(update_ccrate.UpdateError):
                update_ccrate._validate_descriptor(TAG, dict(descriptor, **{field: value}), {
                    "name": descriptor["archive"], "size": len(archive),
                    "digest": "sha256:" + descriptor["sha256"]})
        with self.assertRaises(update_ccrate.UpdateError):
            update_ccrate._read_response(Response(b"", "https://api.github.com/repos/Spraten/ccrate/releases/assets/1",
                                                  {"Content-Length": str(update_ccrate.MAX_DESCRIPTOR_BYTES + 1)}),
                                        update_ccrate.MAX_DESCRIPTOR_BYTES)
        archive = self._archive([("candidate/one", "file", b"1"), ("candidate/two", "file", b"2")])
        archive_path = self.tmp / "too-many.tar.gz"
        archive_path.write_bytes(archive)
        with mock.patch.object(update_ccrate, "MAX_MEMBERS", 1), self.assertRaises(update_ccrate.UpdateError):
            update_ccrate._archive_members(archive_path, {"expanded_bytes": 2})

    def test_cli_requires_exactly_one_mode_and_import_has_no_side_effects(self):
        self.assertRaises(SystemExit, update_ccrate.parse_args, ["--root", str(self.root), "--version", TAG])
        self.assertRaises(SystemExit, update_ccrate.parse_args,
                          ["--root", str(self.root), "--version", TAG, "--check", "--apply"])
        self.assertTrue(callable(update_ccrate.main))


if __name__ == "__main__":
    unittest.main()
