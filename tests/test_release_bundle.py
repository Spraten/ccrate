import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy"))
from release_bundle import (BundleError, recover_interrupted, select_bundle,
                            stage_bundle, validate_bundle)

_FIXTURE_OCF = {}


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def canonical_hash(value):
    return sha_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


class ReleaseBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.public = self.root / "public"
        self.source.mkdir()
        self.public.mkdir()
        self.binary = self.root / "homebox"
        self.binary.write_bytes(b"native fixture")
        self.binary.chmod(0o755)
        self.write(self.public, "index.html", b"public frontend")
        for name, data in {
            "kiosk/index.html": b"kiosk frontend",
            "kiosk/scan_codes.py": b"scan fixture",
            "kiosk/branding/logo.svg": b"asset fixture",
            "ops/desktop_api.py": b"api fixture",
            "ops/item_notes.py": b"notes fixture",
            "ops/label_layouts.py": b"layouts fixture",
            "ops/label_render.py": b"renderer fixture",
            "deploy/kiosk-server.py": b"server fixture",
            "deploy/workshop-gateway.py": b"gateway fixture",
            "deploy/run-homebox.py": b"launcher fixture",
            "deploy/homebox-native.service": b"native service",
            "deploy/homebox-companion.service": b"companion service",
            "deploy/homebox-workshop-gateway.service": b"gateway service",
            "deploy/run-release.py": (Path(__file__).resolve().parents[1] / "deploy/run-release.py").read_bytes(),
            "deploy/release_bundle.py": (Path(__file__).resolve().parents[1] / "deploy/release_bundle.py").read_bytes(),
            "work/label-ui-build/editor.html": b"label editor",
            "work/label-ui-build/render.html": b"renderer fixture",
            "work/label-ui-build/fonts/DejaVuSans.ttf": b"synthetic font",
            "label-ui/src/starter-documents.json": b'{"starter:supvan:left":{"name":"fixture starter"}}',
        }.items():
            self.write(self.source, name, data)
        for name in ("workshop.py", "ledger.py", "native_fields.py"):
            self.write(self.source, f"ops/{name}", (Path(__file__).resolve().parents[1] / "ops" / name).read_bytes())
        # A private sentinel is present but the allowlisted packager must never open it.
        for name, data in {
            "work/ops/ledger.db": b"ledger sentinel",
            "badge-print.key": b"badge secret sentinel",
            "work/baseline/test-account.json": b"account sentinel",
            "pepper": b"pepper sentinel",
            "browser-profile/Preferences": b"profile sentinel",
            "backups/archive.tar": b"backup sentinel",
        }.items():
            self.write(self.source, name, data)

    def write(self, root, name, content):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_packaged_native_snapshot_requires_null_password_evidence(self):
        import runpy
        verifier = runpy.run_path(str(Path(__file__).resolve().parents[1] / "deploy/verify-release-rollback.py"),
                                  run_name="verify_release_rollback_null_password_test")
        require_null_password = verifier.get("_require_null_password_evidence")
        self.assertTrue(callable(require_null_password), "packaged member password evidence check is missing")
        with self.assertRaises(verifier["FixtureRefusal"]):
            require_null_password({})

    def test_packaged_label_review_requires_hash_bound_grayscale_raster(self):
        import runpy
        verifier = runpy.run_path(str(Path(__file__).resolve().parents[1] / "deploy/verify-release-rollback.py"),
                                  run_name="verify_release_rollback_label_review_test")
        verify_label_review = verifier.get("_verify_label_review_artifact")
        self.assertTrue(callable(verify_label_review), "packaged reviewed-label raster check is missing")
        with self.assertRaises(verifier["FixtureRefusal"]):
            verify_label_review({}, b"", "fixture-item")

    def test_packaged_shelf_check_requires_saved_observation_quantity_and_private_note(self):
        import runpy
        verifier = runpy.run_path(str(Path(__file__).resolve().parents[1] / "deploy/verify-release-rollback.py"),
                                  run_name="verify_release_rollback_shelf_check_test")
        verify_shelf = verifier.get("_verify_shelf_check_artifact")
        self.assertTrue(callable(verify_shelf), "packaged Shelf check preservation assertion is missing")
        with self.assertRaises(verifier["FixtureRefusal"]):
            verify_shelf({}, "fixture-item", 1, "fixture note")

    def test_packaged_renderer_dependency_must_be_a_fixture_owned_exact_symlink(self):
        import runpy
        verifier = runpy.run_path(str(Path(__file__).resolve().parents[1] / "deploy/verify-release-rollback.py"),
                                  run_name="verify_release_rollback_renderer_dependency_test")
        verify_link = verifier.get("_verify_fixture_dependency_link")
        self.assertTrue(callable(verify_link), "fixture renderer dependency binding check is missing")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = root / "runtime"
            runtime.mkdir()
            dependency = root / "dependency"
            dependency.mkdir()
            link = runtime / "work/hardware/python"
            link.parent.mkdir(parents=True)
            link.symlink_to(dependency, target_is_directory=True)
            self.assertEqual(verify_link(runtime, dependency), str(dependency.resolve()))
            link.unlink()
            other = root / "other"
            other.mkdir()
            link.symlink_to(other, target_is_directory=True)
            with self.assertRaises(verifier["FixtureRefusal"]):
                verify_link(runtime, dependency)

    def test_packaged_uncertain_note_requires_one_exposed_write_and_read_only_recovery(self):
        import runpy
        verifier = runpy.run_path(str(Path(__file__).resolve().parents[1] / "deploy/verify-release-rollback.py"),
                                  run_name="verify_release_rollback_uncertain_note_test")
        verify_note = verifier.get("_verify_uncertain_note_evidence")
        self.assertTrue(callable(verify_note), "packaged uncertain item-note evidence check is missing")
        with self.assertRaises(verifier["FixtureRefusal"]):
            verify_note({}, [], [], {}, "fixture note")
        job = {"id": "fixture-job", "kind": "add_note", "status": "review",
               "context": {"note_creation_started": True}}
        event = {"kind": "native_write_started"}
        note = {"id": "fixture-entry", "name": "Item note",
                "description": "fixture note\n\n[Kiosk note fixture-job]"}
        dropped = {"status": 201, "content_type": "application/json; charset=utf-8",
                   "body_bytes": 32, "body_sha256": "a" * 64}
        evidence = verify_note(job, [event], [note], dropped, "fixture note")
        self.assertEqual(evidence["write_started_count"], 1)
        self.assertEqual(evidence["dropped_response_status"], 201)
        with self.assertRaises(verifier["FixtureRefusal"]):
            verify_note(job, [event, event], [note], dropped, "fixture note")

    def test_superseded_fallback_evidence_missing_owner_identity_is_rejected(self):
        import runpy
        verifier = runpy.run_path(str(Path(__file__).resolve().parents[1] / "deploy/verify-release-rollback.py"),
                                  run_name="verify_release_rollback_current_evidence_test")
        work = Path(__file__).resolve().parents[1] / "work/queue-coordinator"
        packages_root = work / "whole-map-ocf-restage-status-fix3/bundles"
        packages = tuple(packages_root / role for role in "OCF")
        current = work / "evidence-status-fix9/fallback-evidence-bound-status-fix9.json"
        stale = work / "fallback-evidence-bound-status-fix3.json"
        self.assertTrue(current.is_file(), "current probe-bound fallback evidence has not been staged")
        with self.assertRaises(verifier["FixtureRefusal"]):
            verifier["_load_fallback_evidence"](stale, packages)
        with self.assertRaisesRegex(verifier["FixtureRefusal"], "cross-manager single-write"):
            verifier["_load_fallback_evidence"](current, packages)
        report = json.loads(current.read_text())
        native_path = work / report["assertion_sources"]["native_process"]["path"]
        native = json.loads(native_path.read_text())
        self.assertEqual(native["uncertain_note_created_after_package_exposure"], "C")
        self.assertEqual(native["uncertain_note_attempt_count"], 1)
        self.assertIsNone(native["trace"][0]["uncertain_note_job_id"])
        self.assertEqual(len({row["uncertain_note_job_id"] for row in native["trace"][1:]}), 1)
        self.assertEqual(native["compatibility_assertions"], [{
            "name": "legacy_missing_member_api_is_not_a_rollback_target",
            "result": "passed", "execution_scope": "synthetic-fixture-only",
            "synthetic_missing_member_api_path": "ops/accounts.py",
            "launches_before_rejection": 0,
            "historical_release_manifest_sha256": None,
            "claims_caci1_compatibility": False,
        }])
        acceptance = native.get('acceptance_assertions', [])
        names = {row.get('name') for row in acceptance}
        self.assertEqual(len(acceptance), 9)
        for name in ('matched_previous_release_preserves_new_fixture_profiles_and_loans',
                     'packaged_cross_manager_dropped_cancel_recovery',
                     'packaged_cross_tenant_attachment_rejected'):
            with self.subTest(name=name):
                self.assertIn(name, names)

    def test_explicit_refresh_skips_only_stale_acceptance_rows(self):
        import runpy
        verifier = runpy.run_path(str(Path(__file__).resolve().parents[1] / "deploy/verify-release-rollback.py"),
                                  run_name="verify_release_rollback_refresh_evidence_test")
        work = Path(__file__).resolve().parents[1] / "work/queue-coordinator"
        packages = tuple(work / "whole-map-ocf-restage-status-fix3/bundles" / role for role in "OCF")
        current = work / "evidence-status-fix9/fallback-evidence-bound-status-fix9.json"
        verifier["_load_fallback_evidence"](current, packages, skip_stale_acceptance=True)
        current_report = json.loads(current.read_text())
        current_native = json.loads((work / current_report["assertion_sources"]["native_process"]["path"]).read_text())
        validate_shape = verifier["_validate_fixture_acceptance_shape"]
        validate_shape(current_native["acceptance_assertions"])
        with self.assertRaises(verifier["FixtureRefusal"]):
            validate_shape(None)
        evidence_root = work / "evidence-status-fix10"
        evidence_root.mkdir(mode=0o700, exist_ok=True)
        malformed = json.loads(current.read_text())
        malformed["package_bindings"]["C"]["manifest_sha256"] = "b" * 64
        mismatched = evidence_root / "refresh-with-wrong-package-binding.json"
        mismatched.write_text(json.dumps(malformed))
        with self.assertRaisesRegex(verifier["FixtureRefusal"], "exact O/C/F"):
            verifier["_load_fallback_evidence"](mismatched, packages, skip_stale_acceptance=True)

    def test_fresh_refresh_receipt_passes_strict_acceptance_validation(self):
        import runpy
        verifier = runpy.run_path(str(Path(__file__).resolve().parents[1] / "deploy/verify-release-rollback.py"),
                                  run_name="verify_release_rollback_fresh_refresh_evidence_test")
        work = Path(__file__).resolve().parents[1] / "work/queue-coordinator"
        packages = tuple(work / "whole-map-ocf-restage-status-fix3/bundles" / role for role in "OCF")
        fresh = work / "evidence-status-fix10/fallback-evidence-bound-status-fix10.json"
        self.assertTrue(fresh.is_file(), "fresh refresh receipt has not been staged")
        checks = verifier["_load_fallback_evidence"](fresh, packages)
        self.assertEqual(set(checks), set(verifier["_load_bundle_api"]()[0]))
        report = json.loads(fresh.read_text())
        native = json.loads((work / report["assertion_sources"]["native_process"]["path"]).read_text())
        manager_rows = [row for row in native["acceptance_assertions"]
                        if row["name"] == "packaged_cross_manager_dropped_cancel_recovery"]
        self.assertEqual([row["transition"] for row in manager_rows], ["C", "F", "C"])
        self.assertTrue(all(row.get("owner_id") for row in manager_rows))

    def test_fixture_acceptance_evidence_requires_all_identity_and_state_fields(self):
        import copy
        import runpy
        verifier = runpy.run_path(str(Path(__file__).resolve().parents[1] / "deploy/verify-release-rollback.py"),
                                  run_name="verify_release_rollback_acceptance_fields_test")
        work = Path(__file__).resolve().parents[1] / "work/queue-coordinator"
        binding = json.loads((work / "evidence-status-fix10/fallback-evidence-bound-status-fix10.json").read_text())
        native_source = binding["assertion_sources"]["native_process"]
        native = json.loads((work / native_source["path"]).read_text())
        native_expected = {
            role: {
                "bundle_manifest_sha256": row["manifest_sha256"],
                "native_sha256": row["native_sha256"],
                "fallback_policy_sha256": row["fallback_policy_sha256"],
            }
            for role, row in binding["package_bindings"].items()
        }
        acceptance = native["acceptance_assertions"]
        verifier["_validate_fixture_acceptance_assertions"](acceptance, native_expected)
        required_fields = {
            "profile/member identity": ("matched_previous_release_preserves_new_fixture_profiles_and_loans", "member_id"),
            "profile digest": ("matched_previous_release_preserves_new_fixture_profiles_and_loans", "member_profile_sha256"),
            "loan operation identity": ("matched_previous_release_preserves_new_fixture_profiles_and_loans", "loan_operation_id"),
            "native store identity": ("matched_previous_release_preserves_new_fixture_profiles_and_loans", "native_store_identity"),
            "ledger store identity": ("matched_previous_release_preserves_new_fixture_profiles_and_loans", "ledger_store_identity"),
            "completed loan history": ("matched_previous_release_preserves_new_fixture_profiles_and_loans", "loan_events"),
            "second manager identity": ("packaged_cross_manager_dropped_cancel_recovery", "manager_id"),
            "owner identity": ("packaged_cross_manager_dropped_cancel_recovery", "owner_id"),
            "check identity": ("packaged_cross_manager_dropped_cancel_recovery", "check_id"),
            "request identity": ("packaged_cross_manager_dropped_cancel_recovery", "request_key"),
            "cancel actor identity": ("packaged_cross_manager_dropped_cancel_recovery", "cancelled_by"),
            "tenant entity identity": ("packaged_cross_tenant_attachment_rejected", "entity_id"),
            "ledger before counts": ("packaged_cross_tenant_attachment_rejected", "ops_ledger_before"),
            "ledger after counts": ("packaged_cross_tenant_attachment_rejected", "ops_ledger_after"),
        }
        with self.subTest(missing="all acceptance rows"):
            with self.assertRaises(verifier["FixtureRefusal"]):
                verifier["_validate_fixture_acceptance_rows"]({"acceptance_assertions": None}, native_expected)
        for label, (name, field) in required_fields.items():
            malformed = copy.deepcopy(acceptance)
            for row in malformed:
                if row["name"] == name:
                    row.pop(field, None)
            with self.subTest(missing=label):
                with self.assertRaises(verifier["FixtureRefusal"]):
                    verifier["_validate_fixture_acceptance_assertions"](malformed, native_expected)
        for label, mutation in (
                ("owner differs from invited manager", lambda row: row.update(owner_id=row["manager_id"])),
                ("owner ID is stable across transitions",
                 lambda row: row.update(owner_id="different-owner") if row.get("transition") == "F" else None),
                ("cancel actor is the invited manager", lambda row: row.update(cancelled_by="different-manager")),
                ("write count is an integer not bool", lambda row: row.update(write_attempt_count=True))):
            malformed = copy.deepcopy(acceptance)
            for row in malformed:
                if row["name"] == "packaged_cross_manager_dropped_cancel_recovery":
                    mutation(row)
            with self.subTest(malformed=label):
                with self.assertRaises(verifier["FixtureRefusal"]):
                    verifier["_validate_fixture_acceptance_assertions"](malformed, native_expected)

    def test_synthetic_incomplete_legacy_shape_is_rejected_before_launch_without_caci1_claim(self):
        import runpy
        verifier = runpy.run_path(str(Path(__file__).resolve().parents[1] / "deploy/verify-release-rollback.py"),
                                  run_name="verify_release_rollback_legacy_shape_test")
        packages = Path(__file__).resolve().parents[1] / "work/queue-coordinator/whole-map-ocf-restage-status-fix3/bundles"
        result = verifier["_synthetic_incomplete_legacy_package_assertion"](
            packages / "O", verifier["_load_bundle_api"]()[4], verifier["_load_bundle_api"]()[1])
        self.assertEqual(result["name"], "legacy_missing_member_api_is_not_a_rollback_target")
        self.assertEqual(result["result"], "passed")
        self.assertEqual(result["synthetic_missing_member_api_path"], "ops/accounts.py")
        self.assertEqual(result["launches_before_rejection"], 0)
        self.assertIn("ops/accounts.py", result["rejection_reason"])
        self.assertIsNone(result["historical_release_manifest_sha256"])
        self.assertFalse(result["claims_caci1_compatibility"])

    def provenance(self, *, workshop_reads=(1, 2), workshop_write_mode="v2"):
        runtime_files = {}
        for area in ("ops", "kiosk"):
            for path in sorted((self.source / area).rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                    if area != "ops" or path.suffix == ".py":
                        runtime_files[path.relative_to(self.source).as_posix()] = sha_bytes(path.read_bytes())
        for path in sorted((self.source / "deploy").iterdir()):
            runtime_files[path.relative_to(self.source).as_posix()] = sha_bytes(path.read_bytes())
        source_digest = "d" * 64
        static_digest = "c" * 64
        runtime_modes = {name: (self.source / name).stat().st_mode & 0o777 for name in runtime_files}
        public_files = {p.relative_to(self.public).as_posix(): {"sha256": sha_bytes(p.read_bytes()), "size": p.stat().st_size}
                        for p in sorted(self.public.rglob("*")) if p.is_file()}
        label_root = self.source / "work/label-ui-build"
        label_files = {p.relative_to(label_root).as_posix(): {"sha256": sha_bytes(p.read_bytes()), "size": p.stat().st_size}
                       for p in sorted(label_root.rglob("*")) if p.is_file()}
        label_manifest = label_root / "manifest.json"
        runtime_assets = {name: row["sha256"] for name, row in label_files.items() if name != "manifest.json"}
        label_manifest.write_text(json.dumps({"runtime_assets": runtime_assets}))
        label_files = {p.relative_to(label_root).as_posix(): {"sha256": sha_bytes(p.read_bytes()), "size": p.stat().st_size}
                       for p in sorted(label_root.rglob("*")) if p.is_file()}
        binary_sha = sha_bytes(self.binary.read_bytes())
        build = {"source_manifest_digest": source_digest, "static_manifest_sha256": static_digest,
                 "execution_scope": "fixture-only"}
        closure = canonical_hash({
            "runtime_files": runtime_files, "runtime_modes": runtime_modes,
            "public_files": public_files, "label_files": label_files,
            "label_source_sha256": sha_bytes((self.source / "label-ui/src/starter-documents.json").read_bytes()),
            "native_sha256": binary_sha,
        })
        named = ["workshop_read_v1"] if 1 in workshop_reads else []
        if 2 in workshop_reads:
            named.append("workshop_read_v2")
        if workshop_write_mode == "v2":
            named.append("workshop_write_v2")
        elif workshop_write_mode == "disabled":
            named.append("workshop_write_disabled")
        else:
            named.append("workshop_write_v1")
        tests = {"source_manifest_digest": source_digest,
                 "source_entries": {name: {"sha256": runtime_files[name], "mode": runtime_modes[name]}
                                   for name in runtime_files},
                 "verification": {"exit_code": 0, "tests": len(named)},
                 "execution_scope": "fixture-only",
                 "workshop_compatibility": {"closure_sha256": closure,
                                             "tests": [{"name": name, "result": "passed"}
                                                       for name in named]}}
        build_raw = json.dumps(build, sort_keys=True, indent=2)
        tests_raw = json.dumps(tests, sort_keys=True, indent=2)
        return {
            "source_manifest_digest": source_digest,
            "static_manifest_sha256": static_digest,
            "build_receipt": build,
            "build_receipt_sha256": sha_bytes(build_raw.encode()),
            "build_receipt_raw": build_raw,
            "build_receipt_canonical_sha256": canonical_hash(build),
            "build_receipt_path": "fixture/build-receipt.json",
            "test_receipt": tests,
            "test_receipt_sha256": sha_bytes(tests_raw.encode()),
            "test_receipt_raw": tests_raw,
            "test_receipt_canonical_sha256": canonical_hash(tests),
            "test_receipt_path": "fixture/test-receipt.json",
            "native_sha256": binary_sha,
            "runtime_files": runtime_files,
            "runtime_modes": runtime_modes,
            "public_files": public_files,
            "label_files": label_files,
            "label_source_sha256": sha_bytes((self.source / "label-ui/src/starter-documents.json").read_bytes()),
            "workshop_capability": {"schema": 1, "read_versions": list(workshop_reads),
                                    "write_mode": workshop_write_mode, "closure_sha256": closure,
                                    "test_names": named},
        }

    def test_incompatible_workshop_writer_is_rejected_before_selection(self):
        runtime, previous, candidate, fallback, _ = self.selection_triple()
        legacy = self.root / "releases/pre-v2-writer"
        self.stage(legacy, self.provenance(workshop_reads=(1,), workshop_write_mode="v1"))
        (runtime / "work/application-current").unlink()
        (runtime / "work/application-current").symlink_to(legacy, target_is_directory=True)
        calls = []
        with self.assertRaises(BundleError):
            select_bundle(runtime, candidate, fallback=fallback,
                          fallback_receipt=self.fallback_receipt(legacy, candidate, fallback),
                          run_services=lambda args: calls.append(list(args)), verify=lambda path: None)
        self.assertEqual(calls, [])
        self.assertEqual((runtime / "work/application-current").resolve(), legacy.resolve())

    def test_workshop_named_tests_bind_exact_code_and_static_closure(self):
        provenance = self.provenance()
        provenance["test_receipt"]["workshop_compatibility"]["closure_sha256"] = "0" * 64
        provenance["test_receipt_raw"] = json.dumps(provenance["test_receipt"], sort_keys=True, indent=2)
        provenance["test_receipt_sha256"] = sha_bytes(provenance["test_receipt_raw"].encode())
        provenance["test_receipt_canonical_sha256"] = canonical_hash(provenance["test_receipt"])
        with self.assertRaises(BundleError):
            self.stage(self.root / "unmatched-workshop-evidence", provenance)

    def test_read_only_workshop_fallback_can_be_capability_matched(self):
        release = self.root / "read-only-fallback"
        manifest = self.stage(release, self.provenance(workshop_write_mode="disabled"))
        self.assertEqual(manifest["provenance"]["workshop_capability"]["write_mode"], "disabled")
        self.assertEqual(validate_bundle(release), manifest)

    def test_workshop_room_rollback_uses_one_store_and_preserves_native_history(self):
        import runpy
        import shutil
        original = (self.source / "ops/workshop.py").read_bytes()
        disabled = original + b"\n\ndef _fixture_disabled_save(*args, **kwargs):\n    raise ValueError('Workshop writes disabled')\nWorkshop.save = _fixture_disabled_save\n"
        self.write(self.source, "ops/workshop.py", disabled)
        runtime, previous, candidate, fallback, _ = self.selection_triple(
            after_previous=lambda: (self.source / "ops/workshop.py").write_bytes(original),
            previous_provenance=lambda: self.provenance(workshop_write_mode="disabled"),
            with_sentinels=False)
        return_fallback = self.root / "releases/return-fallback"
        shutil.copytree(fallback, return_fallback)
        harness = runpy.run_path(str(Path(__file__).resolve().parents[1] / "deploy/verify-workshop-rooms.py"),
                                 run_name="verify_workshop_rooms_task6_test")
        test_room_bundle_rollback = harness.get("test_room_bundle_rollback")
        self.assertTrue(callable(test_room_bundle_rollback), "Task6 same-store rollback verifier is missing")
        native_db = self.root / "native-fixture.sqlite"
        owned_root = runtime.parent
        owner_stat = owned_root.lstat()
        fixture = {"owned_root": owned_root, "owner_identity": (owner_stat.st_dev, owner_stat.st_ino,
                   owner_stat.st_uid), "runtime": runtime, "fallback": fallback,
                   "fallback_receipt": self.fallback_receipt(previous, candidate, fallback),
                   "return_fallback": return_fallback,
                   "return_fallback_receipt": self.fallback_receipt(fallback, candidate, return_fallback),
                   "workshop_db": self.root / "runtime/work/ops/workshop.db",
                   "native_db": native_db, "private_paths": [], "scope": "fixture-only"}
        candidate_workshop_bytes = (candidate / "ops/workshop.py").read_bytes()
        (self.source / "ops/workshop.py").write_text("raise RuntimeError('working source changed')\n")
        blocked_parts = {'printer', 'printing', 'label_output', 'hardware', 'gpio'}
        is_physical = lambda name: bool(blocked_parts.intersection(part.lower() for part in name.split('.')))
        preloaded = {name: module for name, module in sys.modules.items() if is_physical(name)}
        for name in preloaded:
            sys.modules.pop(name, None)
        try:
            test_room_bundle_rollback(fixture, previous, candidate)
        finally:
            for name in tuple(sys.modules):
                if is_physical(name):
                    sys.modules.pop(name, None)
            sys.modules.update(preloaded)
        self.assertEqual((candidate / "ops/workshop.py").read_bytes(), candidate_workshop_bytes)
        self.assertEqual((runtime / "work/application-current").resolve(), candidate.resolve())
        self.assertTrue(fixture["room_rollback_checks"]["selected_f_reopened"])
        self.assertTrue(fixture["room_rollback_checks"]["f_to_c_reopened"])
        checks = fixture["room_rollback_checks"]
        self.assertEqual(checks["candidate_saves"], 2)
        self.assertEqual(checks["replay_calls"], 0)
        self.assertEqual(checks["monitored_shutil_store_copy_calls"], 0)
        self.assertEqual(checks["physical_import_attempts"], 0)
        self.assertTrue(checks["full_unresolved_operation_preserved"])
        self.assertIn("synthetic Rooms identity/effect tables", checks["native_evidence_scope"])
        self.assertIn("not native member/loan compatibility evidence", checks["native_evidence_scope"])

    def test_room_rollback_refuses_unsafe_paths_before_open_or_constructor(self):
        import builtins
        import importlib.util
        import runpy
        import sqlite3
        from unittest.mock import patch
        root = self.root / "owned-fresh-fixture"
        root.mkdir(mode=0o700)
        owner_stat = root.lstat()
        runtime = root / "runtime"
        (runtime / "work").mkdir(parents=True, mode=0o700)
        (runtime / "work").chmod(0o700)
        runtime.chmod(0o700)
        previous, candidate, fallback = (root / name for name in ("previous", "candidate", "fallback"))
        for bundle in (previous, candidate, fallback):
            bundle.mkdir(mode=0o700)
        (runtime / "work/application-current").symlink_to(previous, target_is_directory=True)
        database = runtime / "work/ops/workshop.db"
        native_db = root / "native-fixture.sqlite"
        fixture = {"owned_root": root, "owner_identity": (owner_stat.st_dev, owner_stat.st_ino,
                    owner_stat.st_uid), "runtime": runtime, "fallback": fallback,
                    "return_fallback": fallback, "fallback_receipt": {},
                    "return_fallback_receipt": {}, "workshop_db": database, "native_db": native_db,
                    "private_paths": [runtime / "work/ops/ledger.db"]}
        verifier = runpy.run_path(str(Path(__file__).resolve().parents[1] / "deploy/verify-workshop-rooms.py"),
                                  run_name="verify_workshop_rooms_safety_test")
        check = verifier["test_room_bundle_rollback"]
        import release_bundle

        cases = []
        outside = self.root / "outside-store.sqlite"
        outside_target = root.parent / "escape-target"
        outside_target.mkdir()
        cases.append(("outside store", lambda: fixture.__setitem__("native_db", outside),
                      lambda: fixture.__setitem__("native_db", native_db)))
        cases.append(("parent traversal store", lambda: fixture.__setitem__("native_db", root / ".." / outside.name),
                      lambda: fixture.__setitem__("native_db", native_db)))
        escape_link = root / "escape"
        cases.append(("symlink parent traversal store", lambda: (escape_link.symlink_to(outside_target, target_is_directory=True),
                      fixture.__setitem__("native_db", root / "escape" / ".." / outside.name)),
                      lambda: (fixture.__setitem__("native_db", native_db), escape_link.unlink())))
        outside_runtime = self.root / "outside-runtime"
        outside_runtime.mkdir()
        cases.append(("outside runtime", lambda: fixture.__setitem__("runtime", outside_runtime),
                      lambda: fixture.__setitem__("runtime", runtime)))
        preexisting_state = runtime / "work/stale-state.marker"
        cases.append(("runtime contains pre-existing state", lambda: preexisting_state.write_text("stale"),
                      lambda: preexisting_state.unlink()))
        cases.append(("stale store", lambda: database.parent.mkdir(parents=True, exist_ok=True)
                      or database.write_bytes(b"existing private store"), lambda: database.unlink()))
        private_ledger = runtime / "work/ops/ledger.db"
        cases.append(("existing private store", lambda: (private_ledger.parent.mkdir(parents=True, exist_ok=True),
                      private_ledger.write_bytes(b"existing ledger")), lambda: private_ledger.unlink()))
        cases.append(("symlink store", lambda: (native_db.parent.mkdir(parents=True, exist_ok=True),
                      native_db.symlink_to(outside)), lambda: native_db.unlink()))
        symlink_parent = root / "native-escape"
        cases.append(("symlink parent", lambda: (symlink_parent.symlink_to(outside.parent, target_is_directory=True),
                      fixture.__setitem__("native_db", symlink_parent / "store.sqlite")),
                      lambda: (fixture.__setitem__("native_db", native_db), symlink_parent.unlink())))
        for name, prepare, cleanup in cases:
            with self.subTest(path_case=name):
                prepare()
                with patch("builtins.open", side_effect=AssertionError("opened before path refusal")), \
                     patch.object(Path, "open", side_effect=AssertionError("Path.open before refusal")), \
                     patch.object(sqlite3, "connect", side_effect=AssertionError("SQLite opened before refusal")), \
                     patch.object(importlib.util, "spec_from_file_location",
                                  side_effect=AssertionError("bundle import before refusal")), \
                     patch.object(release_bundle, "validate_bundle",
                                  side_effect=AssertionError("bundle read before refusal")):
                    with self.assertRaises((ValueError, RuntimeError)):
                        check(fixture, previous, candidate)
                cleanup()
        fixture["owner_identity"] = (owner_stat.st_dev, owner_stat.st_ino + 1, owner_stat.st_uid)
        with patch("builtins.open", side_effect=AssertionError("opened before owner refusal")), \
             patch.object(sqlite3, "connect", side_effect=AssertionError("SQLite before owner refusal")), \
             patch.object(release_bundle, "validate_bundle",
                          side_effect=AssertionError("bundle read before owner refusal")):
            with self.assertRaises((ValueError, RuntimeError)):
                check(fixture, previous, candidate)

    def test_room_fixture_physical_import_guard_stops_package_before_execution(self):
        import importlib
        import runpy
        import sys
        verifier = runpy.run_path(str(Path(__file__).resolve().parents[1] / "deploy/verify-workshop-rooms.py"),
                                  run_name="verify_workshop_rooms_import_guard_test")
        guard_type = verifier.get("_FixturePhysicalImportGuard")
        self.assertTrue(callable(guard_type), "fixture must expose its physical-import refusal boundary")
        package_root = self.root / "physical-import-probe"
        package = package_root / "hardware"
        package.mkdir(parents=True)
        marker = self.root / "physical-package-executed.marker"
        (package / "__init__.py").write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n")
        (package / "printer.py").write_text("OUTPUT = True\n")
        guard = guard_type()
        previous_modules = {name: module for name, module in sys.modules.items()
                            if name == "hardware" or name.startswith("hardware.")}
        for name in previous_modules:
            sys.modules.pop(name, None)
        sys.path.insert(0, str(package_root))
        sys.meta_path.insert(0, guard)
        try:
            with self.assertRaisesRegex(RuntimeError, "physical output imports are blocked"):
                importlib.import_module("hardware.printer")
            self.assertFalse(marker.exists(), "blocked package initializer must not execute")
            self.assertEqual(guard.blocked_imports, 1)
        finally:
            sys.meta_path.remove(guard)
            sys.path.remove(str(package_root))
            for name in tuple(sys.modules):
                if name == "hardware" or name.startswith("hardware."):
                    sys.modules.pop(name, None)
            sys.modules.update(previous_modules)

    def test_room_fixture_cached_physical_module_is_refused_before_action(self):
        import runpy
        import sys
        import types

        verifier = runpy.run_path(str(Path(__file__).resolve().parents[1] / "deploy/verify-workshop-rooms.py"),
                                  run_name="verify_workshop_rooms_cached_module_test")
        guard_type = verifier.get("_FixturePhysicalImportGuard")
        self.assertTrue(callable(guard_type), "fixture physical-import guard is missing")
        guard = guard_type()
        marker = self.root / "cached-hardware-action.marker"
        cached = types.ModuleType("hardware")
        cached.perform_action = lambda: marker.write_text("physical action")
        prior = sys.modules.get("hardware")
        sys.modules["hardware"] = cached
        try:
            def guarded_action():
                guard.reject_cached_modules()
                sys.modules["hardware"].perform_action()
            with self.assertRaisesRegex(RuntimeError, "cached physical modules are blocked"):
                guarded_action()
            self.assertFalse(marker.exists(), "cached physical action must not run before refusal")
        finally:
            sys.modules.pop("hardware", None)
            if prior is not None:
                sys.modules["hardware"] = prior

    def stage(self, destination, provenance=None, fallback_policy=None):
        return stage_bundle(destination, binary=self.binary, public=self.public,
                            source=self.source, provenance=provenance or self.provenance(),
                            fallback_policy=fallback_policy)

    def test_bundle_includes_imported_python_and_all_frontends(self):
        release = self.root / "release"
        manifest = self.stage(release)
        expected = {
            "native/homebox", "public/index.html", "kiosk/index.html",
            "kiosk/scan_codes.py", "kiosk/branding/logo.svg", "ops/desktop_api.py",
            "ops/item_notes.py", "ops/label_layouts.py", "ops/label_render.py",
            "deploy/kiosk-server.py", "deploy/workshop-gateway.py", "deploy/run-homebox.py",
            "deploy/homebox-native.service", "deploy/homebox-companion.service",
            "deploy/homebox-workshop-gateway.service", "label-ui/editor.html",
            "deploy/run-release.py", "deploy/release_bundle.py", "label-ui/src/starter-documents.json",
        }
        self.assertTrue(expected <= set(manifest["files"]))
        self.assertFalse(any(name.startswith("work/") for name in manifest["files"]))
        self.assertEqual(validate_bundle(release), manifest)

    def selection_pair(self, *, after_previous=None, previous_provenance=None, with_sentinels=True):
        previous = self.root / "releases/previous"
        candidate = self.root / "releases/candidate"
        self.write(self.source, "ops/desktop_api.py", b"MARKER = 'previous api'\n")
        previous_provenance = previous_provenance() if callable(previous_provenance) else previous_provenance
        self.stage(previous, previous_provenance)
        if after_previous:
            after_previous()
        self.write(self.source, "kiosk/index.html", b"candidate terminal")
        self.write(self.public, "index.html", b"candidate public")
        self.write(self.source, "ops/desktop_api.py", b"MARKER = 'candidate api'\n")
        self.binary.write_bytes(b"candidate native")
        self.stage(candidate)
        runtime = self.root / "runtime"
        (runtime / "work").mkdir(parents=True)
        selector = runtime / "work/application-current"
        selector.symlink_to(previous, target_is_directory=True)
        sentinels = {
            runtime / "work/baseline/data/homebox.db": b"database bytes",
            runtime / "work/baseline/pepper": b"pepper bytes",
            runtime / "work/ops/ledger.db": b"journal bytes",
            runtime / "work/backups/archive.tar": b"backup bytes",
        }
        if with_sentinels:
            for path, data in sentinels.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        fallback = self.root / "releases/fixture-fallback"
        candidate_public = (self.public / "index.html").read_bytes()
        candidate_terminal = (self.source / "kiosk/index.html").read_bytes()
        (self.public / "index.html").write_bytes((previous / "public/index.html").read_bytes())
        (self.source / "kiosk/index.html").write_bytes((previous / "kiosk/index.html").read_bytes())
        policy = {
            "schema": 1, "evidence_scope": "fixture-only",
            "strategy": "candidate-code-with-captured-previous-public",
            "candidate_manifest_sha256": sha_bytes((candidate / "manifest.json").read_bytes()),
            "roomsv2_read_versions": [1, 2], "workshop_mutation_mode": "v2",
            "member_profile_loan_compatibility": "verified",
            "runtime_state_policy": "same-stores-no-restore",
            "physical_effect_policy": "never-replay",
        }
        self.stage(fallback, fallback_policy=policy)
        (self.public / "index.html").write_bytes(candidate_public)
        (self.source / "kiosk/index.html").write_bytes(candidate_terminal)
        _FIXTURE_OCF[runtime.resolve()] = (fallback, previous, candidate)
        return runtime, previous, candidate, sentinels

    def select_fixture_bundle(self, root, candidate, **kwargs):
        fallback, previous, candidate_path = _FIXTURE_OCF[Path(root).resolve()]
        return select_bundle(root, candidate, fallback=fallback,
                             fallback_receipt=self.fallback_receipt(previous, candidate_path, fallback),
                             **kwargs)

    def selection_triple(self, evidence_scope="fixture-only", *, after_previous=None,
                         previous_provenance=None, with_sentinels=True):
        runtime, previous, candidate, sentinels = self.selection_pair(
            after_previous=after_previous, previous_provenance=previous_provenance,
            with_sentinels=with_sentinels)
        fallback = self.root / "releases/fallback"
        # F retains candidate handlers/native capability with the captured O
        # frontend and Terminal static tree.
        (self.public / "index.html").write_bytes(b"public frontend")
        (self.source / "kiosk/index.html").write_bytes(b"kiosk frontend")
        policy = {
            "schema": 1,
            "evidence_scope": evidence_scope,
            "strategy": "candidate-code-with-captured-previous-public",
            "candidate_manifest_sha256": sha_bytes((candidate / "manifest.json").read_bytes()),
            "roomsv2_read_versions": [1, 2],
            "workshop_mutation_mode": "v2",
            "member_profile_loan_compatibility": "verified",
            "runtime_state_policy": "same-stores-no-restore",
            "physical_effect_policy": "never-replay",
        }
        self.stage(fallback, fallback_policy=policy)
        return runtime, previous, candidate, fallback, sentinels

    def fallback_receipt(self, previous, candidate, fallback):
        rows = {}
        for label, path in (("previous", previous), ("candidate", candidate), ("fallback", fallback)):
            manifest = validate_bundle(path)
            rows[f"{label}_bundle_manifest_sha256"] = sha_bytes((path / "manifest.json").read_bytes())
            rows[f"{label}_native_sha256"] = manifest["provenance"]["native_sha256"]
        rows["fallback_policy_sha256"] = canonical_hash(validate_bundle(fallback)["fallback_policy"])
        return {
            "execution_scope": validate_bundle(fallback)["fallback_policy"]["evidence_scope"],
            **rows,
            "checks": {
                "fallback_candidate_compatible_handlers": True,
                "fallback_reads_rooms_v1_v2_writes_v2_or_disables_mutation": True,
                "fallback_preserves_member_profile_loan_state": True,
                "same_runtime_stores_no_restore_or_physical_replay": True,
            },
        }

    def test_candidate_exposure_failure_selects_compatible_fallback(self):
        runtime, previous, candidate, fallback, sentinels = self.selection_triple()
        calls, verified = [], []

        def run_services(args):
            calls.append(list(args))

        def verify(release):
            verified.append(Path(release))
            validate_bundle(release)
            if Path(release) == candidate:
                raise RuntimeError("candidate health failed after exposure")

        with self.assertRaisesRegex(BundleError, "candidate health failed after exposure"):
            select_bundle(runtime, candidate, fallback=fallback,
                          fallback_receipt=self.fallback_receipt(previous, candidate, fallback),
                          run_services=run_services, verify=verify)

        self.assertEqual((runtime / "work/application-current").resolve(), fallback.resolve())
        self.assertEqual(verified, [candidate.resolve(), fallback.resolve()])
        self.assertEqual(calls, [
            ["stop", "homebox-workshop-gateway", "homebox-companion", "homebox-native"],
            ["start", "homebox-native", "homebox-companion", "homebox-workshop-gateway"],
            ["stop", "homebox-workshop-gateway", "homebox-companion", "homebox-native"],
            ["start", "homebox-native", "homebox-companion", "homebox-workshop-gateway"],
        ])
        for path, data in sentinels.items():
            self.assertEqual(path.read_bytes(), data)

    def test_exposure_intent_is_durable_before_candidate_start(self):
        import release_bundle
        runtime, _, candidate, fallback, _ = self.selection_triple()
        phases_at_start = []

        def run_services(args):
            if args[0] == "start" and (runtime / "work/application-current").resolve() == candidate.resolve():
                journal = runtime / "work/application-release-journal.jsonl"
                phases_at_start.extend(json.loads(line)["phase"] for line in journal.read_text().splitlines())

        import os
        from unittest.mock import patch
        actual_fsync = os.fsync
        fsync_calls = []
        def record_fsync(fd):
            fsync_calls.append(fd)
            return actual_fsync(fd)
        with patch.object(release_bundle.os, "fsync", side_effect=record_fsync):
            select_bundle(runtime, candidate, fallback=fallback,
                          fallback_receipt=self.fallback_receipt(runtime.joinpath("work/application-current").resolve(), candidate, fallback),
                          run_services=run_services,
                          verify=lambda release: validate_bundle(release))
        self.assertIn("candidate_exposure_possible", phases_at_start)
        self.assertLess(phases_at_start.index("candidate_exposure_possible"),
                        phases_at_start.index("candidate_started"))
        self.assertGreaterEqual(len(fsync_calls), 2)

    def test_interrupted_exposed_candidate_recovers_to_fallback(self):
        runtime, _, candidate, fallback, _ = self.selection_triple()
        calls, verified = [], []

        def interrupt_on_candidate_start(args):
            calls.append(list(args))
            if args[0] == "start" and (runtime / "work/application-current").resolve() == candidate.resolve():
                raise KeyboardInterrupt("simulated process interruption")

        with self.assertRaises(KeyboardInterrupt):
            previous = (runtime / "work/application-current").resolve()
            select_bundle(runtime, candidate, fallback=fallback,
                          fallback_receipt=self.fallback_receipt(previous, candidate, fallback),
                          run_services=interrupt_on_candidate_start,
                          verify=lambda release: verified.append(Path(release)))

        def recover_services(args):
            calls.append(list(args))

        result = recover_interrupted(runtime, run_services=recover_services,
                                      verify=lambda release: verified.append(Path(release)))
        self.assertEqual(result, "fallback_verified")
        self.assertEqual((runtime / "work/application-current").resolve(), fallback.resolve())
        self.assertEqual(verified, [fallback.resolve()])
        self.assertEqual(calls[-2:], [
            ["stop", "homebox-workshop-gateway", "homebox-companion", "homebox-native"],
            ["start", "homebox-native", "homebox-companion", "homebox-workshop-gateway"],
        ])

    def test_interrupted_recovery_refuses_missing_or_malformed_journal(self):
        runtime, previous, _, _, _ = self.selection_triple()
        calls = []
        with self.assertRaises(BundleError):
            recover_interrupted(runtime, run_services=lambda args: calls.append(args), verify=lambda path: None)
        self.assertEqual(calls, [])

        journal = runtime / "work/application-release-journal.jsonl"
        journal.write_text('{"phase": "candidate_exposure_possible"}\n')
        with self.assertRaises(BundleError):
            recover_interrupted(runtime, run_services=lambda args: calls.append(args), verify=lambda path: None)
        self.assertEqual(calls, [])
        self.assertEqual((runtime / "work/application-current").resolve(), previous.resolve())

    def test_interrupted_journal_missing_exposure_marker_preserves_ambiguous_selector(self):
        runtime, previous, candidate, fallback, _ = self.selection_triple()
        def interrupt(args):
            if args[0] == "start":
                raise KeyboardInterrupt("interrupted candidate start")
        with self.assertRaises(KeyboardInterrupt):
            select_bundle(runtime, candidate, fallback=fallback,
                          fallback_receipt=self.fallback_receipt(previous, candidate, fallback),
                          run_services=interrupt, verify=lambda path: None)
        journal = runtime / "work/application-release-journal.jsonl"
        rows = [json.loads(line) for line in journal.read_text().splitlines()]
        rows = [row for row in rows if row["phase"] != "candidate_exposure_possible"]
        journal.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows))
        calls = []
        with self.assertRaisesRegex(BundleError, "phase|progress|ambiguous"):
            recover_interrupted(runtime, run_services=lambda args: calls.append(args), verify=lambda path: None)
        self.assertEqual(calls, [])
        self.assertEqual((runtime / "work/application-current").resolve(), candidate.resolve())

    def test_no_f_public_selector_refuses_before_service_callback(self):
        runtime, _, candidate, _ = self.selection_pair()
        calls = []
        with self.assertRaisesRegex(BundleError, "fallback|F bundle|O/C/F"):
            select_bundle(runtime, candidate, run_services=lambda args: calls.append(args),
                          verify=lambda path: None)
        self.assertEqual(calls, [])

    def test_fallback_receipt_rejects_unbound_fields_before_stopping(self):
        runtime, previous, candidate, fallback, _ = self.selection_triple()
        receipt = self.fallback_receipt(previous, candidate, fallback)
        receipt["unbound_private_sentinel"] = "must not be persisted"
        calls = []
        with self.assertRaisesRegex(BundleError, "fallback receipt schema"):
            select_bundle(runtime, candidate, fallback=fallback, fallback_receipt=receipt,
                          run_services=lambda args: calls.append(list(args)),
                          verify=lambda release: None)
        self.assertEqual(calls, [])
        self.assertFalse((runtime / "work/application-release-journal.jsonl").exists())

    def test_fallback_must_bind_candidate_code_and_previous_public_tree(self):
        runtime, previous, candidate, _, _ = self.selection_triple()
        fallback = self.root / "releases/fallback-wrong-code"
        (self.source / "ops/desktop_api.py").write_text("INCOMPATIBLE = True\n")
        policy = {
            "schema": 1,
            "evidence_scope": "fixture-only",
            "strategy": "candidate-code-with-captured-previous-public",
            "candidate_manifest_sha256": sha_bytes((candidate / "manifest.json").read_bytes()),
            "roomsv2_read_versions": [1, 2],
            "workshop_mutation_mode": "v2",
            "member_profile_loan_compatibility": "verified",
            "runtime_state_policy": "same-stores-no-restore",
            "physical_effect_policy": "never-replay",
        }
        self.stage(fallback, fallback_policy=policy)
        receipt = self.fallback_receipt(previous, candidate, fallback)
        calls = []
        with self.assertRaisesRegex(BundleError, "candidate-compatible code"):
            select_bundle(runtime, candidate, fallback=fallback, fallback_receipt=receipt,
                          run_services=lambda args: calls.append(list(args)), verify=lambda release: None)
        self.assertEqual(calls, [])

    def test_interrupted_recovery_rejects_replaced_work_directory(self):
        import shutil
        runtime, _, candidate, fallback, _ = self.selection_triple()
        previous = (runtime / "work/application-current").resolve()

        def interrupt(args):
            if args[0] == "start" and (runtime / "work/application-current").resolve() == candidate.resolve():
                raise KeyboardInterrupt("simulated interruption")

        with self.assertRaises(KeyboardInterrupt):
            select_bundle(runtime, candidate, fallback=fallback,
                          fallback_receipt=self.fallback_receipt(previous, candidate, fallback),
                          run_services=interrupt, verify=lambda release: None)
        original = runtime / "work"
        archived = runtime / "work-original"
        original.rename(archived)
        shutil.copytree(archived, original)
        calls = []
        with self.assertRaisesRegex(BundleError, "work directory changed|transaction directory changed"):
            recover_interrupted(runtime, run_services=lambda args: calls.append(list(args)),
                                verify=lambda release: None)
        self.assertEqual(calls, [])
        self.assertTrue((original / "application-current").is_dir())
        self.assertFalse((original / "application-current").is_symlink())

    def test_interrupted_recovery_rechecks_fallback_bundle_after_callbacks(self):
        runtime, _, candidate, fallback, _ = self.selection_triple()
        previous = (runtime / "work/application-current").resolve()

        def interrupt(args):
            if args[0] == "start" and (runtime / "work/application-current").resolve() == candidate.resolve():
                raise KeyboardInterrupt("simulated interruption")

        with self.assertRaises(KeyboardInterrupt):
            select_bundle(runtime, candidate, fallback=fallback,
                          fallback_receipt=self.fallback_receipt(previous, candidate, fallback),
                          run_services=interrupt, verify=lambda release: None)

        def mutate_fallback(args):
            if args[0] == "stop":
                target = fallback / "ops/desktop_api.py"
                target.chmod(0o644)
                target.write_text("DRIFT = True\n")

        calls = []
        with self.assertRaisesRegex(BundleError, "fallback bundle changed"):
            recover_interrupted(runtime, run_services=lambda args: (calls.append(list(args)), mutate_fallback(args)),
                                verify=lambda release: None)
        self.assertEqual(calls, [["stop", "homebox-workshop-gateway", "homebox-companion", "homebox-native"]])
        self.assertEqual((runtime / "work/application-current").resolve(), candidate.resolve())

    def test_selection_failure_restores_entire_previous_bundle(self):
        runtime, previous, candidate, sentinels = self.selection_pair()
        services, verified = [], []
        def run_services(args):
            services.append(list(args))
        def verify(release):
            verified.append(Path(release))
            expected = "candidate api" if Path(release) == candidate else "previous api"
            namespace = {}
            exec((Path(release) / "ops/desktop_api.py").read_text(), namespace)
            self.assertEqual(namespace["MARKER"], expected)
            self.assertEqual((Path(release) / "native/homebox").read_bytes(),
                             b"candidate native" if expected == "candidate api" else b"native fixture")
            self.assertEqual((Path(release) / "public/index.html").read_bytes(),
                             b"candidate public" if expected == "candidate api" else b"public frontend")
            self.assertEqual((Path(release) / "kiosk/index.html").read_bytes(),
                             b"candidate terminal" if expected == "candidate api" else b"kiosk frontend")
            if Path(release) == candidate:
                raise RuntimeError("candidate verification failed")
            validate_bundle(release)
        with self.assertRaisesRegex(BundleError, "candidate verification failed"):
            self.select_fixture_bundle(runtime, candidate, run_services=run_services, verify=verify)
        selected = (runtime / "work/application-current").resolve()
        self.assertEqual(selected, _FIXTURE_OCF[runtime.resolve()][0].resolve())
        self.assertEqual(services, [
            ["stop", "homebox-workshop-gateway", "homebox-companion", "homebox-native"],
            ["start", "homebox-native", "homebox-companion", "homebox-workshop-gateway"],
            ["stop", "homebox-workshop-gateway", "homebox-companion", "homebox-native"],
            ["start", "homebox-native", "homebox-companion", "homebox-workshop-gateway"],
        ])
        self.assertEqual(verified, [candidate.resolve(), _FIXTURE_OCF[runtime.resolve()][0].resolve()])
        for path, data in sentinels.items():
            self.assertEqual(path.read_bytes(), data)
        self.assertEqual((selected / "native/homebox").read_bytes(), b"candidate native")
        self.assertEqual((selected / "public/index.html").read_bytes(), b"public frontend")
        self.assertEqual((selected / "kiosk/index.html").read_bytes(), b"kiosk frontend")

    def test_failed_rollback_is_reported_without_data_restore(self):
        runtime, previous, candidate, sentinels = self.selection_pair()
        calls = []
        def run_services(args):
            calls.append(list(args))
            if args[0] == "start" and len(calls) == 4:
                raise RuntimeError("previous services failed to start")
        def verify(release):
            if Path(release) == candidate:
                raise RuntimeError("candidate verification failed")
        with self.assertRaises(BundleError) as caught:
            self.select_fixture_bundle(runtime, candidate, run_services=run_services, verify=verify)
        message = str(caught.exception)
        self.assertIn("candidate verification failed", message)
        self.assertIn("services failed to start", message)
        fallback = _FIXTURE_OCF[runtime.resolve()][0]
        self.assertIn(str(fallback.resolve()), message)
        self.assertEqual((runtime / "work/application-current").resolve(), fallback.resolve())
        for path, data in sentinels.items():
            self.assertEqual(path.read_bytes(), data)

    def test_rollback_stop_failure_keeps_candidate_selected_and_does_not_start_old(self):
        runtime, previous, candidate, _ = self.selection_pair()
        calls, verified = [], []
        def run_services(args):
            calls.append(list(args))
            if len(calls) == 3:
                raise RuntimeError("candidate services would not stop")
        def verify(release):
            verified.append(Path(release))
            if Path(release) == candidate:
                raise RuntimeError("candidate verification failed")
            validate_bundle(release)
        with self.assertRaisesRegex(BundleError, "candidate services would not stop") as caught:
            self.select_fixture_bundle(runtime, candidate, run_services=run_services, verify=verify)
        self.assertIn("candidate verification failed", str(caught.exception))
        self.assertIn(str(candidate.resolve()), str(caught.exception))
        self.assertEqual((runtime / "work/application-current").resolve(), candidate.resolve())
        self.assertEqual(verified, [candidate.resolve()])
        self.assertEqual(calls, [
            ["stop", "homebox-workshop-gateway", "homebox-companion", "homebox-native"],
            ["start", "homebox-native", "homebox-companion", "homebox-workshop-gateway"],
            ["stop", "homebox-workshop-gateway", "homebox-companion", "homebox-native"],
        ])

    def test_missing_previous_bundle_never_stops_services(self):
        _, _, candidate, _ = self.selection_pair()
        runtime = self.root / "no-previous-runtime"
        (runtime / "work").mkdir(parents=True)
        calls = []
        with self.assertRaises(BundleError):
            select_bundle(runtime, candidate, run_services=lambda args: calls.append(args), verify=lambda path: None)
        self.assertEqual(calls, [])

    def test_initial_stop_failure_aborts_without_retry_or_pointer_change(self):
        runtime, previous, candidate, _ = self.selection_pair()
        calls, verified = [], []
        def run_services(args):
            calls.append(list(args))
            if len(calls) == 1:
                raise RuntimeError("initial gateway stop failed")
        def verify(release):
            verified.append(Path(release))
            validate_bundle(release)
        with self.assertRaisesRegex(BundleError, "initial gateway stop failed"):
            self.select_fixture_bundle(runtime, candidate, run_services=run_services, verify=verify)
        self.assertEqual((runtime / "work/application-current").resolve(), previous.resolve())
        self.assertEqual(verified, [])
        self.assertEqual(calls, [
            ["stop", "homebox-workshop-gateway", "homebox-companion", "homebox-native"],
        ])

    def test_selector_drift_after_stop_is_preserved_without_candidate_start(self):
        runtime, previous, candidate, _ = self.selection_pair()
        selector = runtime / "work/application-current"
        foreign = self.root / "foreign-release"
        self.stage(foreign)
        calls = []
        def run_services(args):
            calls.append(list(args))
            if len(calls) == 1:
                selector.unlink()
                selector.symlink_to(foreign, target_is_directory=True)
        with self.assertRaisesRegex(BundleError, "selector changed"):
            self.select_fixture_bundle(runtime, candidate, run_services=run_services, verify=lambda path: None)
        self.assertEqual(selector.resolve(), foreign.resolve())
        self.assertEqual(calls, [["stop", "homebox-workshop-gateway", "homebox-companion", "homebox-native"]])

    def test_candidate_manifest_drift_after_stop_prevents_candidate_start(self):
        runtime, previous, candidate, _ = self.selection_pair()
        candidate_file = candidate / "ops/desktop_api.py"
        calls = []
        def run_services(args):
            calls.append(list(args))
            if len(calls) == 1:
                candidate_file.chmod(0o644)
                candidate_file.write_text("TAMPERED = True\n")
        with self.assertRaisesRegex(BundleError, "selection failed|candidate bundle changed"):
            self.select_fixture_bundle(runtime, candidate, run_services=run_services, verify=lambda path: None)
        self.assertEqual((runtime / "work/application-current").resolve(), previous.resolve())
        self.assertEqual(calls, [
            ["stop", "homebox-workshop-gateway", "homebox-companion", "homebox-native"],
            ["start", "homebox-native", "homebox-companion", "homebox-workshop-gateway"],
        ])

    def test_pointer_replace_failure_restarts_previous_without_second_replace(self):
        import release_bundle
        from unittest.mock import patch
        runtime, previous, candidate, _ = self.selection_pair()
        calls, verified = [], []
        real_replace = release_bundle.os.replace
        replace_calls = []
        def fail_first_replace(src, dst):
            replace_calls.append((Path(src), Path(dst)))
            if len(replace_calls) == 1:
                raise OSError("injected pointer replace failure")
            real_replace(src, dst)
        def run_services(args):
            calls.append(list(args))
        def verify(path):
            verified.append(Path(path))
            validate_bundle(path)
        with patch.object(release_bundle.os, "replace", side_effect=fail_first_replace):
            with self.assertRaisesRegex(BundleError, "injected pointer replace failure"):
                self.select_fixture_bundle(runtime, candidate, run_services=run_services, verify=verify)
        self.assertEqual((runtime / "work/application-current").resolve(), previous.resolve())
        self.assertEqual(len(replace_calls), 1)
        self.assertEqual(calls, [
            ["stop", "homebox-workshop-gateway", "homebox-companion", "homebox-native"],
            ["start", "homebox-native", "homebox-companion", "homebox-workshop-gateway"],
        ])
        self.assertEqual(verified, [previous.resolve()])

    def test_selector_directory_fsync_failure_recovers_before_candidate_start(self):
        import release_bundle
        from unittest.mock import patch
        runtime, previous, candidate, _ = self.selection_pair()
        fallback, _, _ = _FIXTURE_OCF[runtime.resolve()]
        calls = []
        real_fsync = release_bundle._directory_fsync
        count = 0
        def fail_selector_fsync(path):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("selector directory fsync failed")
            return real_fsync(path)
        with patch.object(release_bundle, "_directory_fsync", side_effect=fail_selector_fsync):
            with self.assertRaisesRegex(BundleError, "selector directory fsync failed"):
                self.select_fixture_bundle(runtime, candidate,
                    run_services=lambda args: calls.append(list(args)), verify=lambda path: None)
        self.assertEqual((runtime / "work/application-current").resolve(), previous.resolve())
        self.assertEqual(calls, [
            ["stop", "homebox-workshop-gateway", "homebox-companion", "homebox-native"],
            ["start", "homebox-native", "homebox-companion", "homebox-workshop-gateway"],
        ])

    def test_exposure_journal_write_or_fsync_failure_preserves_candidate_for_reconciliation(self):
        import release_bundle
        from unittest.mock import patch
        for failure in ("write", "fsync"):
            with self.subTest(failure=failure):
                base_root = self.root
                self.root = base_root / f"marker-{failure}"
                self.root.mkdir()
                runtime, previous, candidate, fallback, _ = self.selection_triple()
                calls = []
                original_append = release_bundle._append_transaction_event
                def fail_exposure(path, envelope, phase):
                    if phase != "candidate_exposure_possible":
                        return original_append(path, envelope, phase)
                    if failure == "write":
                        original_write = release_bundle.os.write
                        def write_then_fail(fd, data):
                            if b'"phase":"candidate_exposure_possible"' in data:
                                raise OSError("injected journal write failure")
                            return original_write(fd, data)
                        with patch.object(release_bundle.os, "write", side_effect=write_then_fail):
                            return original_append(path, envelope, phase)
                    original_fsync = release_bundle.os.fsync
                    failed = {"done": False}
                    def fsync_then_fail(fd):
                        if not failed["done"]:
                            failed["done"] = True
                            raise OSError("injected journal fsync failure")
                        return original_fsync(fd)
                    with patch.object(release_bundle.os, "fsync", side_effect=fsync_then_fail):
                        return original_append(path, envelope, phase)
                with patch.object(release_bundle, "_append_transaction_event", side_effect=fail_exposure):
                    with self.assertRaisesRegex(BundleError, "durable|reconciliation"):
                        select_bundle(runtime, candidate, fallback=fallback,
                            fallback_receipt=self.fallback_receipt(previous, candidate, fallback),
                            run_services=lambda args: calls.append(list(args)), verify=lambda path: None)
                self.assertEqual(calls, [
                    ["stop", "homebox-workshop-gateway", "homebox-companion", "homebox-native"],
                ])
                self.assertEqual((runtime / "work/application-current").resolve(), candidate.resolve())
                phases = [json.loads(row)["phase"] for row in
                          (runtime / "work/application-release-journal.jsonl").read_text().splitlines()]
                self.assertEqual(phases[-1], "candidate_selected")
                self.assertEqual(len(calls), 1)
                self.root = base_root

    def test_partial_candidate_start_failure_selects_and_verifies_f(self):
        runtime, previous, candidate, fallback, _ = self.selection_triple()
        calls, verified, partially_started = [], [], []
        def run_services(args):
            calls.append(list(args))
            if args[0] == "start" and (runtime / "work/application-current").resolve() == candidate.resolve():
                partially_started.extend(["homebox-native", "homebox-companion"])
                raise RuntimeError("gateway failed after partial candidate start")
            if args[0] == "start" and (runtime / "work/application-current").resolve() == fallback.resolve():
                partially_started.clear()
        def verify(release):
            verified.append(Path(release))
            validate_bundle(release)
        with self.assertRaisesRegex(BundleError, "partial candidate start"):
            select_bundle(runtime, candidate, fallback=fallback,
                fallback_receipt=self.fallback_receipt(previous, candidate, fallback),
                run_services=run_services, verify=verify)
        self.assertEqual((runtime / "work/application-current").resolve(), fallback.resolve())
        self.assertEqual(verified, [fallback.resolve()])
        self.assertEqual(partially_started, [])
        phases = [json.loads(row)["phase"] for row in
                  (runtime / "work/application-release-journal.jsonl").read_text().splitlines()]
        self.assertEqual(phases[-1], "fallback_verified")

    def test_failed_f_recovery_reports_primary_and_recovery_errors(self):
        runtime, previous, candidate, fallback, _ = self.selection_triple()
        calls, verified = [], []
        def run_services(args):
            calls.append(list(args))
            if args[0] == "start" and (runtime / "work/application-current").resolve() == fallback.resolve():
                raise RuntimeError("F gateway failed to start")
        def verify(release):
            verified.append(Path(release))
            if Path(release) == candidate:
                raise RuntimeError("candidate health failed")
        with self.assertRaises(BundleError) as caught:
            select_bundle(runtime, candidate, fallback=fallback,
                fallback_receipt=self.fallback_receipt(previous, candidate, fallback),
                run_services=run_services, verify=verify)
        self.assertIn("candidate health failed", str(caught.exception))
        self.assertIn("F gateway failed to start", str(caught.exception))
        self.assertIn(str(fallback.resolve()), str(caught.exception))
        self.assertEqual((runtime / "work/application-current").resolve(), fallback.resolve())
        self.assertEqual(verified, [candidate.resolve()])
        phases = [json.loads(row)["phase"] for row in
                  (runtime / "work/application-release-journal.jsonl").read_text().splitlines()]
        self.assertEqual(phases[-1], "recovery_failed")

    def test_candidate_started_record_failure_selects_f_with_valid_journal(self):
        import release_bundle
        from unittest.mock import patch
        for failure in ("before_write", "fsync_after_write"):
            with self.subTest(failure=failure):
                base_root = self.root
                self.root = base_root / f"candidate-start-record-{failure}"
                self.root.mkdir()
                runtime, previous, candidate, fallback, _ = self.selection_triple()
                calls, verified = [], []
                real_append = release_bundle._append_transaction_event
                def append_with_fault(path, envelope, phase):
                    if phase != "candidate_started":
                        return real_append(path, envelope, phase)
                    if failure == "before_write":
                        raise OSError("injected candidate_started write failure")
                    real_fsync = release_bundle.os.fsync
                    failed = {"done": False}
                    def fail_append_fsync_then_allow_cleanup(fd):
                        if not failed["done"]:
                            failed["done"] = True
                            raise OSError("injected candidate_started fsync failure")
                        return real_fsync(fd)
                    with patch.object(release_bundle.os, "fsync",
                                      side_effect=fail_append_fsync_then_allow_cleanup):
                        return real_append(path, envelope, phase)
                def run_services(args):
                    calls.append((list(args), (runtime / "work/application-current").resolve()))
                def verify(release):
                    verified.append(Path(release))
                    validate_bundle(release)
                with patch.object(release_bundle, "_append_transaction_event", side_effect=append_with_fault):
                    with self.assertRaisesRegex(BundleError, "candidate_started"):
                        select_bundle(runtime, candidate, fallback=fallback,
                            fallback_receipt=self.fallback_receipt(previous, candidate, fallback),
                            run_services=run_services, verify=verify)
                self.assertEqual((runtime / "work/application-current").resolve(), fallback.resolve())
                self.assertEqual(verified, [fallback.resolve()])
                self.assertFalse(any(args[0] == "start" and selected == candidate.resolve()
                                     for args, selected in calls))
                events = release_bundle._read_transaction_events(
                    runtime / "work/application-release-journal.jsonl", runtime)
                phases = [row["phase"] for row in events]
                expected = ["transaction_prepared", "stop_requested", "post_stop_preflight_passed",
                            "candidate_selected", "candidate_exposure_possible"]
                expected.extend(["fallback_selected", "fallback_started", "fallback_verified"])
                self.assertEqual(phases, expected)
                self.root = base_root

    def test_partial_journal_write_is_truncated_before_fallback_or_fails_closed(self):
        import release_bundle
        from unittest.mock import patch
        base_root = self.root
        for cleanup in ("success", "truncate_failure", "fsync_failure"):
            with self.subTest(cleanup=cleanup):
                self.root = base_root / f"partial-journal-{cleanup}"
                self.root.mkdir()
                runtime, previous, candidate, fallback, _ = self.selection_triple()
                calls, verified, write_state = [], [], {"count": 0, "prior_length": None}
                real_append = release_bundle._append_transaction_event
                real_write = release_bundle.os.write
                def partial_then_error(fd, data):
                    write_state["count"] += 1
                    if write_state["count"] == 1:
                        return real_write(fd, data[:12])
                    if write_state["count"] == 2:
                        raise OSError("injected failure after partial journal write")
                    return real_write(fd, data)
                def append_with_partial_write(path, envelope, phase):
                    if phase != "candidate_started":
                        return real_append(path, envelope, phase)
                    write_state["prior_length"] = Path(path).stat().st_size
                    if cleanup == "truncate_failure":
                        with patch.object(release_bundle.os, "write", side_effect=partial_then_error), \
                                patch.object(release_bundle.os, "ftruncate",
                                             side_effect=OSError("injected journal truncate failure")):
                            return real_append(path, envelope, phase)
                    if cleanup == "fsync_failure":
                        real_ftruncate = release_bundle.os.ftruncate
                        real_fsync = release_bundle.os.fsync
                        truncated = {"done": False}
                        def truncate_then_mark(fd, length):
                            result = real_ftruncate(fd, length)
                            truncated["done"] = True
                            return result
                        def fsync_after_truncate_fails(fd):
                            if truncated["done"]:
                                raise OSError("injected journal cleanup fsync failure")
                            return real_fsync(fd)
                        with patch.object(release_bundle.os, "write", side_effect=partial_then_error), \
                                patch.object(release_bundle.os, "ftruncate", side_effect=truncate_then_mark), \
                                patch.object(release_bundle.os, "fsync", side_effect=fsync_after_truncate_fails):
                            return real_append(path, envelope, phase)
                    with patch.object(release_bundle.os, "write", side_effect=partial_then_error):
                        return real_append(path, envelope, phase)
                def run_services(args):
                    calls.append((list(args), (runtime / "work/application-current").resolve()))
                def verify(release):
                    verified.append(Path(release))
                    validate_bundle(release)
                with patch.object(release_bundle, "_append_transaction_event", side_effect=append_with_partial_write):
                    with self.assertRaises(BundleError) as caught:
                        select_bundle(runtime, candidate, fallback=fallback,
                            fallback_receipt=self.fallback_receipt(previous, candidate, fallback),
                            run_services=run_services, verify=verify)
                journal = runtime / "work/application-release-journal.jsonl"
                raw = journal.read_bytes()
                if cleanup == "success":
                    self.assertIn("injected failure after partial journal write", str(caught.exception))
                    self.assertEqual((runtime / "work/application-current").resolve(), fallback.resolve())
                    self.assertEqual(verified, [fallback.resolve()])
                    events = release_bundle._read_transaction_events(journal, runtime)
                    phases = [row["phase"] for row in events]
                    self.assertNotIn("candidate_started", phases)
                    self.assertEqual(phases[-1], "fallback_verified")
                    self.assertEqual(raw.count(b"\n"), len(phases))
                    self.assertGreater(write_state["prior_length"], 0)
                else:
                    self.assertIn("reconciliation", str(caught.exception))
                    self.assertEqual((runtime / "work/application-current").resolve(), candidate.resolve())
                    self.assertEqual(verified, [])
                    self.assertEqual(len(calls), 1)
                    self.assertEqual(raw.endswith(b"\n"), cleanup == "fsync_failure")
                    if cleanup == "fsync_failure":
                        events = release_bundle._read_transaction_events(journal, runtime)
                        self.assertEqual(events[-1]["phase"], "candidate_exposure_possible")
                self.assertFalse(any(args[0] == "start" and selected == candidate.resolve()
                                     for args, selected in calls))
                self.root = base_root

    def test_interrupted_o_recovery_can_resume_repeatedly_from_post_stop_phase(self):
        import release_bundle
        from unittest.mock import patch
        runtime, previous, candidate, fallback, _ = self.selection_triple()
        real_append = release_bundle._append_transaction_event
        def interrupt_after_post_stop(path, envelope, phase):
            result = real_append(path, envelope, phase)
            if phase == "post_stop_preflight_passed":
                raise KeyboardInterrupt("interrupt after post-stop preflight")
            return result
        with patch.object(release_bundle, "_append_transaction_event", side_effect=interrupt_after_post_stop):
            with self.assertRaises(KeyboardInterrupt):
                select_bundle(runtime, candidate, fallback=fallback,
                    fallback_receipt=self.fallback_receipt(previous, candidate, fallback),
                    run_services=lambda args: None, verify=lambda path: None)
        self.assertEqual((runtime / "work/application-current").resolve(), previous.resolve())
        phase_rows = []
        def interrupt_first_o_start(args):
            if args[0] == "start":
                phase_rows.append("start")
                if len(phase_rows) == 1:
                    raise KeyboardInterrupt("interrupt first O recovery start")
        with self.assertRaises(KeyboardInterrupt):
            recover_interrupted(runtime, run_services=interrupt_first_o_start, verify=lambda path: None)
        events = release_bundle._read_transaction_events(
            runtime / "work/application-release-journal.jsonl", runtime)
        self.assertEqual(events[-1]["phase"], "previous_started")
        result = recover_interrupted(runtime, run_services=interrupt_first_o_start,
                                     verify=lambda path: validate_bundle(path))
        self.assertEqual(result, "previous_verified")
        events = release_bundle._read_transaction_events(
            runtime / "work/application-release-journal.jsonl", runtime)
        phases = [row["phase"] for row in events]
        self.assertEqual(phases[-4:], ["recovery_attempted", "previous_selected",
                                       "previous_started", "previous_verified"])
        self.assertEqual((runtime / "work/application-current").resolve(), previous.resolve())

    def test_interrupted_f_recovery_can_resume_repeatedly_from_fallback_started(self):
        import release_bundle
        runtime, previous, candidate, fallback, _ = self.selection_triple()
        def select_services(args):
            if (args[0] == "start"
                    and (runtime / "work/application-current").resolve() == fallback.resolve()):
                raise KeyboardInterrupt("interrupt after initial fallback start edge")
        with self.assertRaises(KeyboardInterrupt):
            select_bundle(runtime, candidate, fallback=fallback,
                fallback_receipt=self.fallback_receipt(previous, candidate, fallback),
                run_services=select_services,
                verify=lambda path: (_ for _ in ()).throw(RuntimeError("candidate health failure"))
                if Path(path) == candidate else validate_bundle(path))
        events = release_bundle._read_transaction_events(
            runtime / "work/application-release-journal.jsonl", runtime)
        self.assertEqual(events[-1]["phase"], "fallback_started")
        recovery_starts = []
        def interrupt_first_f_start(args):
            if args[0] == "start":
                recovery_starts.append("start")
                if len(recovery_starts) == 1:
                    raise KeyboardInterrupt("interrupt first F recovery start")
        with self.assertRaises(KeyboardInterrupt):
            recover_interrupted(runtime, run_services=interrupt_first_f_start, verify=lambda path: None)
        events = release_bundle._read_transaction_events(
            runtime / "work/application-release-journal.jsonl", runtime)
        self.assertEqual(events[-1]["phase"], "fallback_started")
        result = recover_interrupted(runtime, run_services=interrupt_first_f_start,
                                     verify=lambda path: validate_bundle(path))
        self.assertEqual(result, "fallback_verified")
        events = release_bundle._read_transaction_events(
            runtime / "work/application-release-journal.jsonl", runtime)
        phases = [row["phase"] for row in events]
        self.assertEqual(phases[-4:], ["recovery_attempted", "fallback_selected",
                                       "fallback_started", "fallback_verified"])
        self.assertEqual((runtime / "work/application-current").resolve(), fallback.resolve())

    def test_recovery_restart_set_covers_every_nonterminal_phase(self):
        import release_bundle
        self.assertEqual(release_bundle.RECOVERY_RESTART_PHASES,
                         release_bundle.JOURNAL_PHASES - release_bundle.TERMINAL_PHASES)

    def test_post_stop_preflight_failure_recovers_from_stop_requested(self):
        import release_bundle
        runtime, previous, candidate, fallback, _ = self.selection_triple()
        calls = []
        def mutate_candidate_after_stop(args):
            calls.append(list(args))
            if args[0] == "stop":
                (candidate / "manifest.json").chmod(0o600)
                (candidate / "manifest.json").write_text("{}\n")
        with self.assertRaises(BundleError) as caught:
            select_bundle(runtime, candidate, fallback=fallback,
                fallback_receipt=self.fallback_receipt(previous, candidate, fallback),
                run_services=mutate_candidate_after_stop,
                verify=lambda path: validate_bundle(path))
        events = release_bundle._read_transaction_events(
            runtime / "work/application-release-journal.jsonl", runtime)
        phases = [row["phase"] for row in events]
        self.assertEqual(phases[:3], ["transaction_prepared", "stop_requested", "pre_exposure_failure"],
                         str(caught.exception))
        self.assertEqual(phases[-1], "previous_verified")
        self.assertEqual((runtime / "work/application-current").resolve(), previous.resolve())
        self.assertTrue(any(args[0] == "start" for args in calls))

    def test_recovery_can_resume_from_recovery_failed(self):
        import release_bundle
        runtime, previous, candidate, fallback, _ = self.selection_triple()
        def fail_candidate_and_first_f_start(path):
            if Path(path) == candidate or Path(path) == fallback:
                raise RuntimeError("injected candidate/F recovery health failure")
        with self.assertRaises(BundleError):
            select_bundle(runtime, candidate, fallback=fallback,
                fallback_receipt=self.fallback_receipt(previous, candidate, fallback),
                run_services=lambda args: (_ for _ in ()).throw(RuntimeError("injected F start failure"))
                if args[0] == "start" and (runtime / "work/application-current").resolve() == fallback.resolve()
                else None,
                verify=fail_candidate_and_first_f_start)
        events = release_bundle._read_transaction_events(
            runtime / "work/application-release-journal.jsonl", runtime)
        self.assertEqual(events[-1]["phase"], "recovery_failed")
        result = recover_interrupted(runtime, run_services=lambda args: None,
                                     verify=lambda path: validate_bundle(path))
        self.assertEqual(result, "fallback_verified")
        events = release_bundle._read_transaction_events(
            runtime / "work/application-release-journal.jsonl", runtime)
        phases = [row["phase"] for row in events]
        self.assertEqual(phases[-5:], ["recovery_failed", "recovery_attempted", "fallback_selected",
                                       "fallback_started", "fallback_verified"])
        self.assertEqual((runtime / "work/application-current").resolve(), fallback.resolve())

    def test_preflight_and_candidate_replace_failures_keep_journal_resumable(self):
        import release_bundle
        from unittest.mock import patch
        for failure in ("preflight", "candidate_replace"):
            with self.subTest(failure=failure):
                base_root = self.root
                self.root = base_root / failure
                self.root.mkdir()
                runtime, previous, candidate, fallback, _ = self.selection_triple()
                selector = runtime / "work/application-current"
                calls = []
                real_write, real_replace = release_bundle.os.write, release_bundle.os.replace
                def fail_pre_exposure_row(fd, data):
                    if b'"phase":"pre_exposure_failure"' in data:
                        raise OSError(f"injected {failure} journal append failure")
                    return real_write(fd, data)
                def stop_services(args):
                    calls.append((list(args), selector.resolve()))
                    if failure == "preflight" and args[0] == "stop":
                        selector.unlink()
                        selector.symlink_to(candidate, target_is_directory=True)
                def fail_candidate_replace(src, dst):
                    if Path(dst) == selector:
                        raise OSError("injected candidate pointer replacement failure")
                    return real_replace(src, dst)
                with patch.object(release_bundle.os, "write", side_effect=fail_pre_exposure_row):
                    if failure == "candidate_replace":
                        with patch.object(release_bundle.os, "replace", side_effect=fail_candidate_replace):
                            with self.assertRaises(BundleError) as caught:
                                select_bundle(runtime, candidate, fallback=fallback,
                                    fallback_receipt=self.fallback_receipt(previous, candidate, fallback),
                                    run_services=stop_services, verify=lambda path: validate_bundle(path))
                    else:
                        with self.assertRaises(BundleError) as caught:
                            select_bundle(runtime, candidate, fallback=fallback,
                                fallback_receipt=self.fallback_receipt(previous, candidate, fallback),
                                run_services=stop_services, verify=lambda path: validate_bundle(path))
                message = str(caught.exception)
                self.assertIn("injected", message)
                self.assertIn("pre_exposure_failure", message)
                self.assertIn(str(selector.resolve()), message)
                self.assertIn("services are stopped", message)
                self.assertIn("no recovery callbacks ran", message)
                self.assertEqual([args[0] for args, _ in calls], ["stop"])
                self.assertEqual(selector.resolve(), candidate.resolve() if failure == "preflight"
                                 else previous.resolve())
                journal = runtime / "work/application-release-journal.jsonl"
                events = release_bundle._read_transaction_events(journal, runtime)
                self.assertEqual(events[-1]["phase"], "stop_requested" if failure == "preflight"
                                 else "post_stop_preflight_passed")
                # A normal restart can consume the untouched valid history and
                # restore O without relying on the failed journal append.
                result = recover_interrupted(runtime, run_services=lambda args: calls.append((list(args),
                                             selector.resolve())), verify=lambda path: validate_bundle(path))
                self.assertEqual(result, "previous_verified")
                self.assertEqual(selector.resolve(), previous.resolve())
                self.root = base_root

    def test_repeated_journal_write_failure_preserves_primary_and_recording_errors(self):
        import release_bundle
        from unittest.mock import patch
        runtime, previous, candidate, fallback, _ = self.selection_triple()
        calls = []
        real_write = release_bundle.os.write
        def fail_selected_and_recovery_rows(fd, data):
            if (b'"phase":"fallback_selected"' in data
                    or b'"phase":"recovery_failed"' in data):
                raise OSError("persistent review journal write failure")
            return real_write(fd, data)
        def verify(path):
            if Path(path) == candidate:
                raise RuntimeError("review primary candidate health failure")
        with patch.object(release_bundle.os, "write", side_effect=fail_selected_and_recovery_rows):
            with self.assertRaises(BundleError) as caught:
                select_bundle(runtime, candidate, fallback=fallback,
                    fallback_receipt=self.fallback_receipt(previous, candidate, fallback),
                    run_services=lambda args: calls.append((list(args),
                        (runtime / "work/application-current").resolve())), verify=verify)
        message = str(caught.exception)
        self.assertIn("review primary candidate health failure", message)
        self.assertIn("persistent review journal write failure", message)
        self.assertIn("recovery_failed", message)
        self.assertIn(str(fallback.resolve()), message)
        self.assertEqual((runtime / "work/application-current").resolve(), fallback.resolve())
        self.assertFalse(any(args[0] == "start" and selected == fallback.resolve()
                             for args, selected in calls))

    def test_prestart_recovery_rechecks_previous_after_verifier_callback(self):
        import release_bundle
        from unittest.mock import patch
        for drift in ("pointer", "manifest"):
            with self.subTest(drift=drift):
                base_root = self.root
                self.root = base_root / drift
                self.root.mkdir()
                runtime, previous, candidate, _ = self.selection_pair()
                selector = runtime / "work/application-current"
                foreign = self.root / f"foreign-{drift}"
                self.stage(foreign)
                calls = []
                real_replace = release_bundle.os.replace
                replace_calls = []
                def fail_first_replace(src, dst):
                    replace_calls.append((src, dst))
                    if len(replace_calls) == 1:
                        raise OSError("injected pointer replace failure")
                    real_replace(src, dst)
                def run_services(args):
                    calls.append(list(args))
                def verify(path):
                    if Path(path) == previous:
                        if drift == "pointer":
                            selector.unlink()
                            selector.symlink_to(foreign, target_is_directory=True)
                        else:
                            source = previous / "ops/desktop_api.py"
                            source.chmod(0o644)
                            source.write_text("DRIFT = True\n")
                with patch.object(release_bundle.os, "replace", side_effect=fail_first_replace):
                    with self.assertRaisesRegex(BundleError, "recovery failed|rollback failed") as caught:
                        self.select_fixture_bundle(runtime, candidate, run_services=run_services, verify=verify)
                if drift == "pointer":
                    self.assertEqual(selector.resolve(), foreign.resolve())
                    self.assertIn("selector changed", str(caught.exception))
                else:
                    self.assertTrue("release file mode differs" in str(caught.exception) or "previous bundle changed" in str(caught.exception))
                    self.assertEqual(selector.resolve(), previous.resolve())
                self.assertEqual(calls, [
                    ["stop", "homebox-workshop-gateway", "homebox-companion", "homebox-native"],
                    ["start", "homebox-native", "homebox-companion", "homebox-workshop-gateway"],
                ])
                self.root = base_root

    def test_work_directory_redirection_is_detected_before_pointer_mutation(self):
        runtime, previous, candidate, _ = self.selection_pair()
        work = runtime / "work"
        foreign_work = self.root / "foreign-work"
        foreign_work.mkdir()
        foreign_pointer = foreign_work / "application-current"
        foreign_bundle = self.root / "foreign-release"
        self.stage(foreign_bundle)
        foreign_pointer.symlink_to(foreign_bundle, target_is_directory=True)
        calls = []
        def run_services(args):
            calls.append(list(args))
            if len(calls) == 1:
                work.rename(runtime / "work-original")
                work.symlink_to(foreign_work, target_is_directory=True)
        with self.assertRaisesRegex(BundleError, "work directory changed|transaction directory changed"):
            self.select_fixture_bundle(runtime, candidate, run_services=run_services, verify=lambda path: None)
        self.assertEqual(foreign_pointer.resolve(), foreign_bundle.resolve())
        self.assertEqual(calls, [["stop", "homebox-workshop-gateway", "homebox-companion", "homebox-native"]])

    def test_foreign_pointer_drift_during_verification_is_not_overwritten(self):
        runtime, previous, candidate, _ = self.selection_pair()
        selector = runtime / "work/application-current"
        foreign = self.root / "foreign-release"
        self.stage(foreign)
        calls, verifies = [], []
        def run_services(args):
            calls.append(list(args))
        def verify(release):
            verifies.append(Path(release))
            selector.unlink()
            selector.symlink_to(foreign, target_is_directory=True)
            raise RuntimeError("candidate verification failed")
        with self.assertRaisesRegex(BundleError, "selector changed"):
            self.select_fixture_bundle(runtime, candidate, run_services=run_services, verify=verify)
        self.assertEqual(selector.resolve(), foreign.resolve())
        self.assertEqual(calls, [
            ["stop", "homebox-workshop-gateway", "homebox-companion", "homebox-native"],
            ["start", "homebox-native", "homebox-companion", "homebox-workshop-gateway"],
        ])
        self.assertEqual(verifies, [candidate.resolve()])

    def test_publisher_help_works_without_pythonpath_or_operational_actions(self):
        import os
        import subprocess
        publisher = Path(__file__).resolve().parents[1] / "deploy/publish-users.py"
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        result = subprocess.run(["python3", str(publisher), "--help"], env=env,
                                text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--verification-receipt", result.stdout)

    def test_publisher_rebinds_receipt_after_backup_before_service_callback(self):
        import runpy
        import subprocess
        from unittest.mock import patch
        runtime, previous, candidate, fallback, _ = self.selection_triple(evidence_scope="production-matched")
        foreign = self.root / "foreign-release"
        self.stage(foreign)
        publisher = Path(__file__).resolve().parents[1] / "deploy/publish-users.py"
        namespace = runpy.run_path(str(publisher), run_name="publish_users_main_fixture")
        namespace["main"].__globals__["ROOT"] = runtime
        old_manifest = validate_bundle(previous)
        new_manifest = validate_bundle(candidate)
        fallback_manifest = validate_bundle(fallback)
        old_manifest["manifest_sha256"] = sha_bytes((previous / "manifest.json").read_bytes())
        new_manifest["manifest_sha256"] = sha_bytes((candidate / "manifest.json").read_bytes())
        fallback_manifest["manifest_sha256"] = sha_bytes((fallback / "manifest.json").read_bytes())
        receipt = {
            "execution_scope": "production-matched",
            "previous_bundle_manifest_sha256": old_manifest["manifest_sha256"],
            "candidate_bundle_manifest_sha256": new_manifest["manifest_sha256"],
            "fallback_bundle_manifest_sha256": fallback_manifest["manifest_sha256"],
            "previous_native_sha256": old_manifest["provenance"]["native_sha256"],
            "candidate_native_sha256": new_manifest["provenance"]["native_sha256"],
            "fallback_native_sha256": fallback_manifest["provenance"]["native_sha256"],
            "fallback_policy_sha256": canonical_hash(fallback_manifest["fallback_policy"]),
            "checks": {name: True for name in namespace["REQUIRED_CHECKS"]},
        }
        receipt_path = self.root / "matched-receipt.json"
        receipt_path.write_text(json.dumps(receipt))
        selector = runtime / "work/application-current"
        service_calls, commands = [], []
        namespace["main"].__globals__["_run_services"] = lambda args: service_calls.append(list(args))
        namespace["main"].__globals__["_build_cold_backup_receipt"] = lambda *args: (
            self.root / "backup-receipt.json", {"status": "synthetic"})
        namespace["main"].__globals__["validate_cold_backup_receipt"] = lambda *args: None
        def fake_run(args, **kwargs):
            commands.append(list(args))
            if str(args[1]).endswith("backup-deployment.py"):
                selector.unlink()
                selector.symlink_to(foreign, target_is_directory=True)
                return subprocess.CompletedProcess(args, 0,
                    stdout=json.dumps({"status": "completed", "database_integrity": "ok",
                                       "backup": "fixture.tar.gz", "bytes": 1}))
            return subprocess.CompletedProcess(args, 0, stdout="{}")
        with patch("subprocess.run", side_effect=fake_run), patch("shutil.copy2"):
            with self.assertRaisesRegex(BundleError, "changed during preflight|does not bind"):
                namespace["main"](["--candidate", str(candidate),
                                   "--fallback", str(fallback),
                                   "--verification-receipt", str(receipt_path), "--apply"])
        self.assertEqual(len(commands), 2)
        self.assertEqual(service_calls, [])

    def test_publisher_binds_durable_cold_backup_receipt_hash_to_selector(self):
        import contextlib
        import io
        import runpy
        import subprocess
        from unittest.mock import patch
        runtime, previous, candidate, fallback, _ = self.selection_triple(evidence_scope="production-matched")
        publisher = Path(__file__).resolve().parents[1] / "deploy/publish-users.py"
        namespace = runpy.run_path(str(publisher), run_name="publish_users_backup_binding_test")
        namespace["main"].__globals__["ROOT"] = runtime
        bound = []
        backup_receipt = {"status": "synthetic", "archive_sha256": "a" * 64}
        expected_digest = hashlib.sha256(json.dumps(
            backup_receipt, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        namespace["main"].__globals__["_build_cold_backup_receipt"] = lambda *args: (
            runtime / "work/matched-release-cold-backup-receipt.json", backup_receipt)
        namespace["main"].__globals__["validate_cold_backup_receipt"] = lambda *args: None
        namespace["main"].__globals__["select_bundle"] = lambda *args, **kwargs: bound.append(kwargs)
        def fake_run(args, **kwargs):
            return subprocess.CompletedProcess(args, 0, stdout=json.dumps({
                "status": "completed", "database_integrity": "ok",
                "backup": "fixture.tar.gz", "bytes": 1}))
        rows = {}
        for label, path in (("previous", previous), ("candidate", candidate), ("fallback", fallback)):
            manifest = validate_bundle(path)
            rows[f"{label}_bundle_manifest_sha256"] = sha_bytes((path / "manifest.json").read_bytes())
            rows[f"{label}_native_sha256"] = manifest["provenance"]["native_sha256"]
        receipt = {
            "execution_scope": "production-matched",
            **rows,
            "fallback_policy_sha256": canonical_hash(validate_bundle(fallback)["fallback_policy"]),
            "checks": {name: True for name in namespace["REQUIRED_CHECKS"]},
        }
        receipt_path = self.root / "matched-production-receipt.json"
        receipt_path.write_text(json.dumps(receipt))
        with patch("subprocess.run", side_effect=fake_run), patch("shutil.copy2"), \
                contextlib.redirect_stdout(io.StringIO()):
            namespace["main"](["--candidate", str(candidate), "--fallback", str(fallback),
                               "--verification-receipt", str(receipt_path), "--apply"])
        self.assertEqual(len(bound), 1)
        self.assertEqual(bound[0].get("backup_receipt_sha256"), expected_digest)

    def test_cold_backup_receipt_binds_O_C_F_and_archive_manifest(self):
        import io
        import runpy
        import tarfile
        import time
        runtime, previous, candidate, fallback, _ = self.selection_triple()
        backups = self.root / "work/backups"
        backups.mkdir(parents=True)
        created = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        database_hash = "a" * 64
        required_members = ["AGENTS.md", ".git", "ops", "kiosk", "deploy", "docs",
                            "upstream/homebox", "work/baseline/data", "work/baseline/pepper",
                            "work/baseline/test-account.json", "work/ops", "work/homebox-bin/homebox",
                            "work/hardware/python", "work/supvan-cups/target/release/examples/kiosk-label"]
        backup_manifest = {
            "format": 1,
            "created_at": created,
            "commit": "fixture-commit",
            "homebox_pin": "fixture-pin",
            "members": required_members,
            "sha256": {"work/ops/ledger.db": database_hash,
                       "work/baseline/data/homebox.db": database_hash,
                       "work/homebox-bin/homebox": database_hash,
                       "work/supvan-cups/target/release/examples/kiosk-label": database_hash},
        }
        archived_bytes = b"synthetic archived bytes"
        manifest_raw = json.dumps(backup_manifest, sort_keys=True).encode()
        archive_path = backups / "deployment-fixture.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            member = tarfile.TarInfo("deployment-manifest.json")
            member.size = len(manifest_raw)
            member.mode = 0o600
            archive.addfile(member, io.BytesIO(manifest_raw))
            for name in required_members:
                member = tarfile.TarInfo(name)
                if name in ("AGENTS.md", "work/baseline/pepper", "work/baseline/test-account.json",
                            "work/homebox-bin/homebox",
                            "work/supvan-cups/target/release/examples/kiosk-label"):
                    member.size = len(archived_bytes)
                    archive.addfile(member, io.BytesIO(archived_bytes))
                else:
                    member.type = tarfile.DIRTYPE
                    archive.addfile(member)
            for name in backup_manifest["sha256"]:
                if name in required_members:
                    continue
                member = tarfile.TarInfo(name)
                member.size = len(archived_bytes)
                archive.addfile(member, io.BytesIO(archived_bytes))
        archive_path.chmod(0o600)
        archive_hash = sha_bytes(archive_path.read_bytes())
        archive_path.with_suffix(".sha256").write_text(f"{archive_hash}  {archive_path.name}\n")
        archive_path.with_suffix(".sha256").chmod(0o600)

        def bound(path):
            manifest = validate_bundle(path)
            return {**manifest, "manifest_sha256": sha_bytes((path / "manifest.json").read_bytes()),
                    "bundle_path": str(path)}

        publisher = Path(__file__).resolve().parents[1] / "deploy/publish-users.py"
        namespace = runpy.run_path(str(publisher), run_name="publish_users_backup_receipt_test")
        previous_row, candidate_row, fallback_row = map(bound, (previous, candidate, fallback))
        with self.assertRaises(BundleError):
            namespace["_build_cold_backup_receipt"](
                {"status": "completed", "database_integrity": "ok", "backup": archive_path.name,
                 "bytes": archive_path.stat().st_size}, self.root,
                previous_row, candidate_row, fallback_row)
        # The producer hashes the actual database/native files; construct a
        # complete synthetic tar with matching declared bytes for the green path.
        backup_manifest["sha256"] = {name: sha_bytes(b"synthetic archived bytes")
                                     for name in backup_manifest["sha256"]}
        manifest_raw = json.dumps(backup_manifest, sort_keys=True).encode()
        with tarfile.open(archive_path, "w:gz") as archive:
            member = tarfile.TarInfo("deployment-manifest.json")
            member.size = len(manifest_raw)
            member.mode = 0o600
            archive.addfile(member, io.BytesIO(manifest_raw))
            for name in required_members:
                member = tarfile.TarInfo(name)
                if name in ("AGENTS.md", "work/baseline/pepper", "work/baseline/test-account.json",
                            "work/homebox-bin/homebox",
                            "work/supvan-cups/target/release/examples/kiosk-label"):
                    member.size = len(archived_bytes); archive.addfile(member, io.BytesIO(archived_bytes))
                else:
                    member.type = tarfile.DIRTYPE; archive.addfile(member)
            for name in backup_manifest["sha256"]:
                if name in required_members:
                    continue
                member = tarfile.TarInfo(name); member.size = len(archived_bytes)
                archive.addfile(member, io.BytesIO(archived_bytes))
        archive_hash = sha_bytes(archive_path.read_bytes())
        archive_path.with_suffix(".sha256").write_text(f"{archive_hash}  {archive_path.name}\n")
        receipt_path, receipt = namespace["_build_cold_backup_receipt"](
            {"status": "completed", "database_integrity": "ok", "backup": archive_path.name,
             "bytes": archive_path.stat().st_size}, self.root,
            previous_row, candidate_row, fallback_row)
        self.assertEqual(receipt_path, self.root / "work/matched-release-cold-backup-receipt.json")
        self.assertEqual(receipt_path.stat().st_mode & 0o777, 0o600)
        namespace["validate_cold_backup_receipt"](receipt, self.root,
                                                  previous_row, candidate_row, fallback_row)
        wrong_manifest = dict(backup_manifest)
        wrong_manifest["sha256"] = dict(backup_manifest["sha256"])
        wrong_manifest["sha256"]["work/ops/ledger.db"] = "f" * 64
        with self.assertRaisesRegex(BundleError, "hash mismatch"):
            namespace["_validate_backup_members"](archive_path, wrong_manifest)
        receipt["candidate_bundle_manifest_sha256"] = "0" * 64
        with self.assertRaisesRegex(BundleError, "exact O/C/F"):
            namespace["validate_cold_backup_receipt"](receipt, self.root,
                                                      previous_row, candidate_row, fallback_row)

    def test_candidate_start_failure_restores_previous_bundle(self):
        runtime, previous, candidate, _ = self.selection_pair()
        calls, verified = [], []
        def run_services(args):
            calls.append(list(args))
            if len(calls) == 2:
                raise RuntimeError("candidate native start failed")
        def verify(release):
            verified.append(Path(release))
            validate_bundle(release)
        with self.assertRaisesRegex(BundleError, "candidate native start failed"):
            self.select_fixture_bundle(runtime, candidate, run_services=run_services, verify=verify)
        fallback = _FIXTURE_OCF[runtime.resolve()][0]
        self.assertEqual((runtime / "work/application-current").resolve(), fallback.resolve())
        self.assertEqual(verified, [fallback.resolve()])
        self.assertEqual(calls, [
            ["stop", "homebox-workshop-gateway", "homebox-companion", "homebox-native"],
            ["start", "homebox-native", "homebox-companion", "homebox-workshop-gateway"],
            ["stop", "homebox-workshop-gateway", "homebox-companion", "homebox-native"],
            ["start", "homebox-native", "homebox-companion", "homebox-workshop-gateway"],
        ])

    def test_selection_keeps_private_files_byte_identical(self):
        runtime, previous, candidate, sentinels = self.selection_pair()
        before = {path: path.read_bytes() for path in sentinels}
        calls = []
        self.select_fixture_bundle(runtime, candidate, run_services=lambda args: calls.append(list(args)),
                      verify=lambda path: validate_bundle(path))
        self.assertEqual((runtime / "work/application-current").resolve(), candidate.resolve())
        self.assertEqual({path: path.read_bytes() for path in sentinels}, before)
        self.assertEqual(calls, [
            ["stop", "homebox-workshop-gateway", "homebox-companion", "homebox-native"],
            ["start", "homebox-native", "homebox-companion", "homebox-workshop-gateway"],
        ])

    def test_publisher_receipt_rejects_stale_bundle_hashes(self):
        import runpy
        previous, candidate = self.root / "previous", self.root / "candidate"
        self.stage(previous)
        self.write(self.source, "ops/desktop_api.py", b"MARKER = 'candidate'\n")
        self.write(self.public, "index.html", b"candidate frontend")
        self.binary.write_bytes(b"candidate native")
        self.stage(candidate)
        previous_manifest, candidate_manifest = validate_bundle(previous), validate_bundle(candidate)
        previous_manifest["manifest_sha256"] = sha_bytes((previous / "manifest.json").read_bytes())
        candidate_manifest["manifest_sha256"] = sha_bytes((candidate / "manifest.json").read_bytes())
        publisher = Path(__file__).resolve().parents[1] / "deploy/publish-users.py"
        namespace = runpy.run_path(str(publisher), run_name="publish_users_fixture")
        receipt = {
            "execution_scope": "fixture-only",
            "previous_bundle_manifest_sha256": previous_manifest["manifest_sha256"],
            "candidate_bundle_manifest_sha256": candidate_manifest["manifest_sha256"],
            "previous_native_sha256": previous_manifest["provenance"]["native_sha256"],
            "candidate_native_sha256": candidate_manifest["provenance"]["native_sha256"],
            "checks": {name: True for name in namespace["REQUIRED_CHECKS"]},
        }
        namespace["validate_matched_receipt"](receipt, previous_manifest, candidate_manifest, allow_fixture=True)
        with self.assertRaisesRegex(BundleError, "fixture-only evidence"):
            namespace["validate_matched_receipt"](receipt, previous_manifest, candidate_manifest)
        receipt["candidate_bundle_manifest_sha256"] = "0" * 64
        with self.assertRaisesRegex(BundleError, "does not bind"):
            namespace["validate_matched_receipt"](receipt, previous_manifest, candidate_manifest, allow_fixture=True)

    def test_inert_release_cli_validates_bundles_without_selecting_or_faking_checks(self):
        import contextlib
        import io
        import runpy
        import sys
        from unittest.mock import patch
        _, previous, candidate, fallback, _ = self.selection_triple()
        cli = Path(__file__).resolve().parents[1] / "deploy/verify-release-rollback.py"
        args = [str(cli), "--previous", str(previous), "--candidate", str(candidate),
                "--fallback", str(fallback)]
        output = io.StringIO()
        with patch.object(sys, "argv", args), contextlib.redirect_stdout(output):
            runpy.run_path(str(cli), run_name="__main__")
        report = json.loads(output.getvalue())
        self.assertTrue(report["fixture_only"])
        self.assertEqual(report["processes_started"], 0)
        self.assertFalse(report["selector_exercised"])
        self.assertEqual(report["compatibility_claim"], "unclaimed")
        self.assertEqual(set(report["validated_bundles"]), {"previous", "candidate", "fallback"})

    def test_fixture_rollback_cli_rejects_operational_bundle_paths(self):
        import runpy
        import sys
        from unittest.mock import patch
        cli = Path(__file__).resolve().parents[1] / "deploy/verify-release-rollback.py"
        with patch.object(sys, "argv", [str(cli), "--previous", str(Path(__file__).resolve().parents[1]),
                                         "--candidate", str(Path(__file__).resolve().parents[1]),
                                         "--fallback", str(Path(__file__).resolve().parents[1])]):
            with self.assertRaises(SystemExit):
                runpy.run_path(str(cli), run_name="__main__")

    def test_bundle_hash_mismatch_is_rejected(self):
        release = self.root / "release"
        self.stage(release)
        (release / "kiosk/index.html").chmod(0o644)
        (release / "kiosk/index.html").write_bytes(b"changed")
        with self.assertRaises(BundleError):
            validate_bundle(release)

    def test_mode_mismatch_is_rejected(self):
        release = self.root / "release"
        self.stage(release)
        (release / "native/homebox").chmod(0o644)
        with self.assertRaises(BundleError):
            validate_bundle(release)

    def test_bundle_excludes_private_data(self):
        for name in ("work/ops/ledger.db", "badge-print.key", "work/baseline/test-account.json",
                     "pepper", "browser-profile/Preferences", "backups/archive.tar"):
            (self.source / name).chmod(0)
        release = self.root / "release"
        from unittest.mock import patch
        import release_bundle
        protected = {self.source / name for name in (
            "work/ops/ledger.db", "badge-print.key", "work/baseline/test-account.json",
            "pepper", "browser-profile/Preferences", "backups/archive.tar")}
        hash_file, copy_file = release_bundle._hash, release_bundle.shutil.copyfile
        def checked_hash(path):
            if Path(path) in protected:
                raise AssertionError("private sentinel was read")
            return hash_file(path)
        def checked_copy(src, dst, *args, **kwargs):
            if Path(src) in protected:
                raise AssertionError("private sentinel was copied")
            return copy_file(src, dst, *args, **kwargs)
        with patch.object(release_bundle, "_hash", side_effect=checked_hash), \
             patch.object(release_bundle.shutil, "copyfile", side_effect=checked_copy):
            manifest = self.stage(release)
        serialized = json.dumps(manifest)
        for sentinel in ("ledger sentinel", "badge secret sentinel", "account sentinel",
                         "pepper sentinel", "profile sentinel", "backup sentinel"):
            self.assertNotIn(sentinel, serialized)
        self.assertFalse(any((release / name).exists() for name in (
            "work/ops/ledger.db", "badge-print.key", "work/baseline/test-account.json",
            "pepper", "browser-profile/Preferences", "backups/archive.tar")))

    def test_legacy_target_without_matching_source_fails_before_selection(self):
        legacy = self.root / "caci.1"
        legacy.mkdir()
        calls = []
        def validate_then_select():
            validate_bundle(legacy)
            calls.append("selected")
        with self.assertRaises(BundleError):
            validate_then_select()
        self.assertEqual(calls, [])

    def test_unmatched_build_or_test_receipt_is_rejected(self):
        provenance = self.provenance()
        provenance["test_receipt"]["source_manifest_digest"] = "e" * 64
        provenance["test_receipt_raw"] = json.dumps(provenance["test_receipt"], sort_keys=True, indent=2)
        provenance["test_receipt_sha256"] = sha_bytes(provenance["test_receipt_raw"].encode())
        provenance["test_receipt_canonical_sha256"] = canonical_hash(provenance["test_receipt"])
        with self.assertRaises(BundleError):
            self.stage(self.root / "bad-receipt", provenance)

    def test_unexpected_source_file_or_receipt_mismatch_is_rejected(self):
        provenance = self.provenance()
        self.write(self.source, "ops/not-in-capture.py", b"new source")
        with self.assertRaises(BundleError):
            self.stage(self.root / "changed-source", provenance)

    def test_public_tree_must_match_captured_hashes_and_sizes(self):
        provenance = self.provenance()
        provenance["public_files"]["index.html"]["sha256"] = "0" * 64
        with self.assertRaises(BundleError):
            self.stage(self.root / "bad-public", provenance)

    def test_escaping_source_link_is_rejected(self):
        outside = self.root / "outside.py"
        outside.write_bytes(b"outside")
        (self.source / "ops/escape.py").symlink_to(outside)
        with self.assertRaises(BundleError):
            self.stage(self.root / "escaping-link")


    def test_symlinked_manifest_is_rejected_without_reading_target(self):
        import release_bundle
        from unittest.mock import patch
        release = self.root / "release"
        self.stage(release)
        external = self.root / "external-manifest.json"
        original_manifest = release / "manifest.json"
        release.chmod(0o755)
        original_manifest.chmod(0o644)
        external.write_bytes(original_manifest.read_bytes())
        original_manifest.unlink()
        original_manifest.symlink_to(external)
        import os
        reads = []
        path_open, os_open = Path.open, os.open
        def traced_path_open(path, *args, **kwargs):
            if path in (original_manifest, external):
                reads.append(path)
            return path_open(path, *args, **kwargs)
        def traced_os_open(path, *args, **kwargs):
            if Path(path) in (original_manifest, external):
                reads.append(Path(path))
            return os_open(path, *args, **kwargs)
        with patch.object(Path, "open", traced_path_open), patch.object(os, "open", traced_os_open):
            with self.assertRaises(BundleError):
                validate_bundle(release)
        self.assertEqual(reads, [])


    def test_symlinked_release_is_rejected_before_file_reads(self):
        from unittest.mock import patch
        target = self.root / "target"
        self.stage(target)
        release = self.root / "release-link"
        release.symlink_to(target, target_is_directory=True)
        reads = []
        path_open = Path.open
        def traced_open(path, *args, **kwargs):
            reads.append(path)
            return path_open(path, *args, **kwargs)
        with patch.object(Path, "open", traced_open):
            with self.assertRaises(BundleError):
                validate_bundle(release)
        self.assertEqual(reads, [])

    def test_unexpected_private_member_is_rejected_before_read(self):
        import release_bundle
        from unittest.mock import patch
        release = self.root / "release"
        self.stage(release)
        private = release / "work/ops/ledger.db"
        release.chmod(0o755)
        private.parent.mkdir(parents=True)
        private.write_bytes(b"injected private sentinel")
        private.chmod(0o444)
        private.parent.chmod(0o555)
        (release / "work").chmod(0o555)
        release.chmod(0o555)
        import os
        reads = []
        path_open, os_open = Path.open, os.open
        def traced_path_open(path, *args, **kwargs):
            if path == private:
                reads.append(path)
            return path_open(path, *args, **kwargs)
        def traced_os_open(path, *args, **kwargs):
            if Path(path) == private:
                reads.append(Path(path))
            return os_open(path, *args, **kwargs)
        with patch.object(Path, "open", traced_path_open), patch.object(os, "open", traced_os_open):
            with self.assertRaises(BundleError):
                validate_bundle(release)
        self.assertEqual(reads, [])

    def test_publisher_import_is_inert(self):
        import runpy
        from unittest.mock import patch
        publisher = Path(__file__).resolve().parents[1] / "deploy/publish-users.py"
        with patch("subprocess.run", side_effect=AssertionError("publisher executed")):
            namespace = runpy.run_path(str(publisher), run_name="publish_users_import")
        self.assertTrue(callable(namespace["main"]))


if __name__ == "__main__":
    unittest.main()
