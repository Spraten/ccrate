import hashlib
import json
import sys
import tempfile
import unittest
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if sys.platform == "win32":
    fcntl_stub = types.ModuleType("fcntl")
    fcntl_stub.LOCK_EX, fcntl_stub.LOCK_UN = 1, 2
    fcntl_stub.flock = lambda *_args: None
    sys.modules.setdefault("fcntl", fcntl_stub)
sys.path.insert(0, str(ROOT / "deploy"))
sys.path.insert(0, str(ROOT / "tests"))
TEMP_ROOT = ROOT / ".tmp-task5-tests"
TEMP_ROOT.mkdir(exist_ok=True)
tempfile.tempdir = str(TEMP_ROOT)

from release_bundle import BundleError, _verify_staged_workshop, stage_bundle, validate_bundle


class UpdateCompatibilityTests(unittest.TestCase):
    def setUp(self):
        from test_release_bundle import ReleaseBundleTests
        self.fixture = ReleaseBundleTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.temp.cleanup)


    def _stage_upgrade_pair(self):
        candidate = self.fixture.root / "candidate"
        stage_bundle(candidate, binary=self.fixture.binary, public=self.fixture.public,
                     source=self.fixture.source, provenance=self.fixture.provenance(),
                     verification=_verify_staged_workshop)
        (self.fixture.public / "index.html").write_bytes(b"captured previous UI")
        previous = self.fixture.root / "previous"
        stage_bundle(previous, binary=self.fixture.binary, public=self.fixture.public,
                     source=self.fixture.source,
                     provenance=self.fixture.provenance(workshop_reads=(1, 2), workshop_write_mode="disabled"))
        return previous, candidate

    def _make_backup(self, previous):
        import contextlib
        import io
        import shutil
        import sqlite3
        import tarfile
        root = self.fixture.root / "runtime"
        root.mkdir()
        work = root / "work"
        work.mkdir(mode=0o700)
        for name in ("work/ops/ledger.db", "work/baseline/data/homebox.db"):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with contextlib.closing(sqlite3.connect(path)) as db:
                with db:
                    db.execute("CREATE TABLE fixture (value TEXT)")
                    db.execute("INSERT INTO fixture VALUES ('fixture store')")
        required = ["AGENTS.md", ".git", "ops", "kiosk", "deploy", "docs",
                    "upstream/homebox", "work/baseline/data", "work/baseline/pepper",
                    "work/baseline/test-account.json", "work/ops", "work/homebox-bin/homebox",
                    "work/hardware/python", "work/supvan-cups/target/release/examples/kiosk-label"]
        required_files = {"AGENTS.md", "work/baseline/pepper", "work/baseline/test-account.json",
                          "work/homebox-bin/homebox",
                          "work/supvan-cups/target/release/examples/kiosk-label"}
        for name in required:
            path = root / name
            if name not in ("work/ops", "work/baseline/data"):
                if name in required_files:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"fixture backup member")
                else:
                    path.mkdir(parents=True, exist_ok=True)
        old_release = root / "work/releases/previous"
        old_release.parent.mkdir(parents=True)
        shutil.copytree(previous, old_release)
        (work / "application-current").symlink_to(Path("releases/previous"), target_is_directory=True)
        selected_files = {path.relative_to(old_release).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in old_release.rglob("*") if path.is_file()}
        tracked = ("work/ops/ledger.db", "work/baseline/data/homebox.db",
                   "work/homebox-bin/homebox", "work/supvan-cups/target/release/examples/kiosk-label")
        hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in tracked}
        backup_manifest = {
            "format": 2, "created_at": "20261013T000000Z", "commit": "fixture",
            "homebox_pin": "fixture", "members": required + ["work/releases/previous"],
            "sha256": hashes,
            "selected_release": {
                "relative_path": "work/releases/previous",
                "manifest_sha256": hashlib.sha256((old_release / "manifest.json").read_bytes()).hexdigest(),
                "files": selected_files,
            },
        }
        archive_path = work / "backup.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            for name in required:
                archive.add(root / name, arcname=name, recursive=True)
            archive.add(old_release, arcname="work/releases/previous", recursive=True)
            raw = json.dumps(backup_manifest, sort_keys=True).encode()
            member = tarfile.TarInfo("deployment-manifest.json")
            member.size, member.mode = len(raw), 0o600
            archive.addfile(member, io.BytesIO(raw))
        archive_path.chmod(0o600)
        return root, archive_path

    def test_staged_artifact_runs_workshop_v1_read_v2_read_and_v2_write(self):
        package = self.fixture.root / "candidate"
        manifest = stage_bundle(package, binary=self.fixture.binary, public=self.fixture.public,
                                source=self.fixture.source, provenance=self.fixture.provenance(),
                                verification=_verify_staged_workshop)
        capability = manifest["provenance"]["workshop_capability"]
        receipt = manifest["provenance"]["test_receipt"]["workshop_compatibility"]
        raw_receipt = json.dumps(manifest["provenance"]["test_receipt"],
                                 sort_keys=True, indent=2) + "\n"
        self.assertEqual(capability["read_versions"], [1, 2])
        self.assertEqual(capability["write_mode"], "v2")
        self.assertEqual(receipt["closure_sha256"], capability["closure_sha256"])
        self.assertEqual(hashlib.sha256(raw_receipt.encode()).hexdigest(),
                         manifest["provenance"]["test_receipt_sha256"])
        self.assertEqual([row["name"] for row in receipt["tests"]],
                         ["workshop_read_v1", "workshop_read_v2", "workshop_write_v2"])
        if sys.platform != "win32":
            self.assertEqual(validate_bundle(package), manifest)

    def test_failed_or_incomplete_staged_checks_cannot_be_sealed_as_compatible(self):
        package = self.fixture.root / "candidate"
        with self.assertRaisesRegex(BundleError, "did not pass every required case"):
            stage_bundle(package, binary=self.fixture.binary, public=self.fixture.public,
                         source=self.fixture.source, provenance=self.fixture.provenance(),
                         verification=lambda _root: {"workshop_read_v1": "passed"})
        self.assertFalse(package.exists())

    def test_compatibility_evidence_is_bound_to_the_copied_workshop_code(self):
        package = self.fixture.root / "candidate"
        original = (self.fixture.source / "ops/workshop.py").read_bytes()
        (self.fixture.source / "ops/workshop.py").write_bytes(original + b"\nraise RuntimeError('changed artifact')\n")
        # Source provenance must first be refreshed to represent the changed candidate.
        provenance = self.fixture.provenance()
        with self.assertRaisesRegex(RuntimeError, "changed artifact"):
            stage_bundle(package, binary=self.fixture.binary, public=self.fixture.public,
                         source=self.fixture.source, provenance=provenance,
                         verification=_verify_staged_workshop)
        self.assertFalse(package.exists())



    @unittest.skipIf(sys.platform == "win32", "sealed bundle mode validation requires POSIX permissions")
    def test_fallback_uses_candidate_code_and_previous_ui(self):
        from release_bundle import assemble_fallback
        previous, candidate = self._stage_upgrade_pair()
        fallback = self.fixture.root / "fallback"
        assemble_fallback(previous, candidate, fallback, verification=_verify_staged_workshop)
        o, c, f = (validate_bundle(path) for path in (previous, candidate, fallback))
        self.assertEqual(f["files"]["native/homebox"]["sha256"], c["files"]["native/homebox"]["sha256"])
        self.assertEqual(f["files"]["ops/workshop.py"]["sha256"], c["files"]["ops/workshop.py"]["sha256"])
        self.assertEqual(f["files"]["public/index.html"]["sha256"], o["files"]["public/index.html"]["sha256"])
        self.assertEqual(f["provenance"]["test_receipt"]["assembly_origins"]["public"], "previous")
        self.assertEqual(f["fallback_policy"]["evidence_scope"], "fixture-only")
        self.assertEqual(f["fallback_policy"]["member_profile_loan_compatibility"], "unverified")

    @unittest.skipIf(sys.platform == "win32", "backup restore requires POSIX symlinks and permissions")
    def test_matched_proof_requires_actual_snapshot_and_checks(self):
        from release_bundle import assemble_fallback, verify_upgrade_pair
        previous, candidate = self._stage_upgrade_pair()
        fallback = self.fixture.root / "fallback"
        assemble_fallback(previous, candidate, fallback, verification=_verify_staged_workshop)
        root, archive = self._make_backup(previous)
        receipt = verify_upgrade_pair(root, previous, candidate, fallback, archive)
        self.assertEqual(receipt["execution_scope"], "fixture-only")
        self.assertTrue(receipt["snapshot"]["restored_actual_snapshot"])
        self.assertEqual(receipt["snapshot"]["selected_release_manifest_sha256"], receipt["previous_bundle_manifest_sha256"])
        self.assertFalse(receipt["checks"]["matched_previous_release_preserves_new_fixture_profiles_and_loans"])
        self.assertFalse(receipt["checks"]["fallback_preserves_member_profile_loan_state"])
        self.assertFalse(receipt["checks"]["same_runtime_stores_no_restore_or_physical_replay"])
        proof_files = list((root / "work").glob("update-proof-*.json"))
        self.assertEqual(len(proof_files), 1)
        self.assertEqual(proof_files[0].stat().st_mode & 0o777, 0o600)
        publisher = __import__("runpy").run_path(str(ROOT / "deploy/publish-users.py"),
                                                   run_name="task5_publish_gate")
        def bound(path):
            manifest = validate_bundle(path)
            return {**manifest, "manifest_sha256": hashlib.sha256((path / "manifest.json").read_bytes()).hexdigest(),
                    "bundle_path": str(path)}
        with self.assertRaisesRegex(BundleError, "fixture-only evidence cannot authorize"):
            publisher["validate_matched_receipt"](receipt, bound(previous), bound(candidate), bound(fallback))
        from release_bundle import FALLBACK_CHECKS, _validate_fallback_receipt
        synthetic_all_true = {
            "execution_scope": "fixture-only",
            "previous_bundle_manifest_sha256": hashlib.sha256((previous / "manifest.json").read_bytes()).hexdigest(),
            "candidate_bundle_manifest_sha256": hashlib.sha256((candidate / "manifest.json").read_bytes()).hexdigest(),
            "fallback_bundle_manifest_sha256": hashlib.sha256((fallback / "manifest.json").read_bytes()).hexdigest(),
            "previous_native_sha256": bound(previous)["provenance"]["native_sha256"],
            "candidate_native_sha256": bound(candidate)["provenance"]["native_sha256"],
            "fallback_native_sha256": bound(fallback)["provenance"]["native_sha256"],
            "fallback_policy_sha256": hashlib.sha256(json.dumps(
                bound(fallback)["fallback_policy"], sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "checks": {name: True for name in FALLBACK_CHECKS},
        }
        with self.assertRaisesRegex(BundleError, "lacks verified native member/profile/loan"):
            _validate_fallback_receipt(synthetic_all_true, previous, candidate, fallback)

    @unittest.skipIf(sys.platform == "win32", "backup restore requires POSIX symlinks and permissions")
    def test_changed_store_or_artifact_invalidates_proof(self):
        from release_bundle import assemble_fallback, verify_upgrade_pair
        previous, candidate = self._stage_upgrade_pair()
        fallback = self.fixture.root / "fallback"
        assemble_fallback(previous, candidate, fallback, verification=_verify_staged_workshop)
        root, archive = self._make_backup(previous)
        changed = candidate / "ops/workshop.py"
        changed.chmod(0o644)
        changed.write_bytes(changed.read_bytes() + b"\n# changed after sealing\n")
        with self.assertRaises(BundleError):
            verify_upgrade_pair(root, previous, candidate, fallback, archive)
        self.assertEqual(list((root / "work").glob("update-proof-*.json")), [])

    @unittest.skipIf(sys.platform == "win32", "packaged verifier requires POSIX filesystem and process behavior")
    def test_packaged_rollback_process(self):
        import os
        import subprocess
        previous, candidate = self._stage_upgrade_pair()
        from release_bundle import assemble_fallback
        fallback = self.fixture.root / "fallback"
        assemble_fallback(previous, candidate, fallback, verification=_verify_staged_workshop)
        dependency = self.fixture.root / "dependency"
        dependency.mkdir()
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(("HBOX", "WORKSHOP", "HOMEBOX_WEB"))}
        environment["TMPDIR"] = str(TEMP_ROOT)
        command = [sys.executable, str(ROOT / "deploy/verify-release-rollback.py"),
                   "--mode", "fixture-process", "--previous", str(previous),
                   "--candidate", str(candidate), "--fallback", str(fallback),
                   "--dependency-path", str(dependency)]
        result = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True,
                                text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("artifact-bound named fallback checks are missing or unpassed", result.stderr)
        self.assertNotIn("processes_started", result.stdout)

    @unittest.skipIf(sys.platform == "win32", "backup restore requires POSIX symlinks and permissions")
    def test_verification_never_contacts_operational_endpoints_or_hardware(self):
        import urllib.request
        import subprocess
        from unittest.mock import patch
        from release_bundle import assemble_fallback, verify_upgrade_pair
        previous, candidate = self._stage_upgrade_pair()
        fallback = self.fixture.root / "fallback"
        assemble_fallback(previous, candidate, fallback, verification=_verify_staged_workshop)
        root, archive = self._make_backup(previous)
        with patch.object(urllib.request, "urlopen", side_effect=AssertionError("network access")) as urlopen, \
                patch.object(subprocess, "run", side_effect=AssertionError("process or hardware effect")) as run:
            receipt = verify_upgrade_pair(root, previous, candidate, fallback, archive)
        urlopen.assert_not_called()
        run.assert_not_called()
        self.assertEqual(receipt["execution_scope"], "fixture-only")
        self.assertFalse(receipt["checks"]["same_runtime_stores_no_restore_or_physical_replay"])


if __name__ == "__main__":
    unittest.main()
