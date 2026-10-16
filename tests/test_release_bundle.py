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
            "kiosk/scan_codes.py": b"scan fixture",
            "kiosk/decode_codes.py": b"decoder fixture",
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
            "ledger store idew€^¸∂âûÀk∫wµÁ@ÄÄÄÄÄÄÄÄÄÄÅçΩπ—•π’î(ÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÅµïµâï»ÄÙÅ—Ö…ô•±îπQÖ…%πôº°πÖµî§ÏÅµïµâï»πÕ•ÈîÄÙÅ±ï∏°Ö…ç°•Ÿïë}âÂ—ïÃ§(ÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÅÖ…ç°•ŸîπÖëëô•±î°µïµâï»∞Å•ºπ	Â—ïÕ%<°Ö…ç°•Ÿïë}âÂ—ïÃ§§(ÄÄÄÄÄÄÄÅÖ…ç°•Ÿï}°ÖÕ†ÄÙÅÕ°Ö}âÂ—ïÃ°Ö…ç°•Ÿï}¡Ö—†π…ïÖë}âÂ—ïÃ†§§(ÄÄÄÄÄÄÄÅÖ…ç°•Ÿï}¡Ö—†π›•—°}Õ’ôô•‡†àπÕ°Ñ»‘ÿà§π›…•—ï}—ï·–°òâÌÖ…ç°•Ÿï}°ÖÕ°ÙÄÅÌÖ…ç°•Ÿï}¡Ö—†ππÖµïıq∏à§(ÄÄÄÄÄÄÄÅ…ïçï•¡—}¡Ö—†∞Å…ïçï•¡–ÄÙÅπÖµïÕ¡Öçïlâ}â’•±ë}çΩ±ë}âÖç≠’¡}…ïçï•¡–ât†(ÄÄÄÄÄÄÄÄÄÄÄÅÏâÕ—Ö—’ÃàËÄâçΩµ¡±ï—ïêà∞ÄâëÖ—ÖâÖÕï}•π—ïù…•—‰àËÄâΩ¨à∞ÄââÖç≠’¿àËÅÖ…ç°•Ÿï}¡Ö—†ππÖµî∞(ÄÄÄÄÄÄÄÄÄÄÄÄÄââÂ—ïÃàËÅÖ…ç°•Ÿï}¡Ö—†πÕ—Ö–†§πÕ—}Õ•ÈïÙ∞ÅÕï±òπ…ΩΩ–∞(ÄÄÄÄÄÄÄÄÄÄÄÅ¡…ïŸ•Ω’Õ}…Ω‹∞ÅçÖπë•ëÖ—ï}…Ω‹∞ÅôÖ±±âÖç≠}…Ω‹§(ÄÄÄÄÄÄÄÅÕï±òπÖÕÕï…—≈’Ö∞°…ïçï•¡—}¡Ö—†∞ÅÕï±òπ…ΩΩ–ÄºÄâ›Ω…¨ΩµÖ—ç°ïêµ…ï±ïÖÕîµçΩ±êµâÖç≠’¿µ…ïçï•¡–π©ÕΩ∏à§(ÄÄÄÄÄÄÄÅÕï±òπÖÕÕï…—≈’Ö∞°…ïçï•¡—}¡Ö—†πÕ—Ö–†§πÕ—}µΩëîÄòÄ¡º‹‹‹∞Ä¡ºÿ¿¿§(ÄÄÄÄÄÄÄÅπÖµïÕ¡ÖçïlâŸÖ±•ëÖ—ï}çΩ±ë}âÖç≠’¡}…ïçï•¡–ât°…ïçï•¡–∞ÅÕï±òπ…ΩΩ–∞(ÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÅ¡…ïŸ•Ω’Õ}…Ω‹∞ÅçÖπë•ëÖ—ï}…Ω‹∞ÅôÖ±±âÖç≠}…Ω‹§(ÄÄÄÄÄÄÄÅ›…Ωπù}µÖπ•ôïÕ–ÄÙÅë•ç–°âÖç≠’¡}µÖπ•ôïÕ–§(ÄÄÄÄÄÄÄÅ›…Ωπù}µÖπ•ôïÕ—lâÕ°Ñ»‘ÿâtÄÙÅë•ç–°âÖç≠’¡}µÖπ•ôïÕ—lâÕ°Ñ»‘ÿât§(ÄÄÄÄÄÄÄÅ›…Ωπù}µÖπ•ôïÕ—lâÕ°Ñ»‘ÿâulâ›Ω…¨ΩΩ¡ÃΩ±ïëùï»πëàâtÄÙÄâòàÄ®Äÿ–(ÄÄÄÄÄÄÄÅ›•—†ÅÕï±òπÖÕÕï…—IÖ•ÕïÕIïùï‡°	’πë±ï……Ω»∞Äâ°ÖÕ†Åµ•ÕµÖ—ç†à§Ë(ÄÄÄÄÄÄÄÄÄÄÄÅπÖµïÕ¡Öçïlâ}ŸÖ±•ëÖ—ï}âÖç≠’¡}µïµâï…Ãât°Ö…ç°•Ÿï}¡Ö—†∞Å›…Ωπù}µÖπ•ôïÕ–§(ÄÄÄÄÄÄÄÅ…ïçï•¡—lâçÖπë•ëÖ—ï}â’πë±ï}µÖπ•ôïÕ—}Õ°Ñ»‘ÿâtÄÙÄà¿àÄ®Äÿ–(ÄÄÄÄÄÄÄÅ›•—†ÅÕï±òπÖÕÕï…—IÖ•ÕïÕIïùï‡°	’πë±ï……Ω»∞Äâï·Öç–Å<ΩΩà§Ë(ÄÄÄÄÄÄÄÄÄÄÄÅπÖµïÕ¡ÖçïlâŸÖ±•ëÖ—ï}çΩ±ë}âÖç≠’¡}…ïçï•¡–ât°…ïçï•¡–∞ÅÕï±òπ…ΩΩ–∞(ÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÅ¡…ïŸ•Ω’Õ}…Ω‹∞ÅçÖπë•ëÖ—ï}…Ω‹∞ÅôÖ±±âÖç≠}…Ω‹§((ÄÄÄÅëïòÅ—ïÕ—}çÖπë•ëÖ—ï}Õ—Ö…—}ôÖ•±’…ï}…ïÕ—Ω…ïÕ}¡…ïŸ•Ω’Õ}â’πë±î°Õï±ò§Ë(ÄÄÄÄÄÄÄÅ…’π—•µî∞Å¡…ïŸ•Ω’Ã∞ÅçÖπë•ëÖ—î∞Å|ÄÙÅÕï±òπÕï±ïç—•Ωπ}¡Ö•»†§(ÄÄÄÄÄÄÄÅçÖ±±Ã∞ÅŸï…•ô•ïêÄÙÅmt∞Åmt(ÄÄÄÄÄÄÄÅëïòÅ…’π}Õï…Ÿ•çïÃ°Ö…ùÃ§Ë(ÄÄÄÄÄÄÄÄÄÄÄÅçÖ±±ÃπÖ¡¡ïπê°±•Õ–°Ö…ùÃ§§(ÄÄÄÄÄÄÄÄÄÄÄÅ•òÅ±ï∏°çÖ±±Ã§ÄÙÙÄ»Ë(ÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÅ…Ö•ÕîÅI’π—•µï……Ω»†âçÖπë•ëÖ—îÅπÖ—•ŸîÅÕ—Ö…–ÅôÖ•±ïêà§(ÄÄÄÄÄÄÄÅëïòÅŸï…•ô‰°…ï±ïÖÕî§Ë(ÄÄÄÄÄÄÄÄÄÄÄÅŸï…•ô•ïêπÖ¡¡ïπê°AÖ—†°…ï±ïÖÕî§§(ÄÄÄÄÄÄÄÄÄÄÄÅŸÖ±•ëÖ—ï}â’πë±î°…ï±ïÖÕî§(ÄÄÄÄÄÄÄÅ›•—†ÅÕï±òπÖÕÕï…—IÖ•ÕïÕIïùï‡°	’πë±ï……Ω»∞ÄâçÖπë•ëÖ—îÅπÖ—•ŸîÅÕ—Ö…–ÅôÖ•±ïêà§Ë(ÄÄÄÄÄÄÄÄÄÄÄÅÕï±òπÕï±ïç—}ô•·—’…ï}â’πë±î°…’π—•µî∞ÅçÖπë•ëÖ—î∞Å…’π}Õï…Ÿ•çïÃı…’π}Õï…Ÿ•çïÃ∞ÅŸï…•ô‰ıŸï…•ô‰§(ÄÄÄÄÄÄÄÅôÖ±±âÖç¨ÄÙÅ}%aQUI}=m…’π—•µîπ…ïÕΩ±Ÿî†•ul¡t(ÄÄÄÄÄÄÄÅÕï±òπÖÕÕï…—≈’Ö∞†°…’π—•µîÄºÄâ›Ω…¨ΩÖ¡¡±•çÖ—•Ω∏µç’……ïπ–à§π…ïÕΩ±Ÿî†§∞ÅôÖ±±âÖç¨π…ïÕΩ±Ÿî†§§(ÄÄÄÄÄÄÄÅÕï±òπÖÕÕï…—≈’Ö∞°Ÿï…•ô•ïê∞ÅmôÖ±±âÖç¨π…ïÕΩ±Ÿî†•t§(ÄÄÄÄÄÄÄÅÕï±òπÖÕÕï…—≈’Ö∞°çÖ±±Ã∞Ål(ÄÄÄÄÄÄÄÄÄÄÄÅlâÕ—Ω¿à∞Äâ°ΩµïâΩ‡µ›Ω…≠Õ°Ω¿µùÖ—ï›Ö‰à∞Äâ°ΩµïâΩ‡µçΩµ¡Öπ•Ω∏à∞Äâ°ΩµïâΩ‡µπÖ—•Ÿîât∞(ÄÄÄÄÄÄÄÄÄÄÄÅlâÕ—Ö…–à∞Äâ°ΩµïâΩ‡µπÖ—•Ÿîà∞Äâ°ΩµïâΩ‡µçΩµ¡Öπ•Ω∏à∞Äâ°ΩµïâΩ‡µ›Ω…≠Õ°Ω¿µùÖ—ï›Ö‰ât∞(ÄÄÄÄÄÄÄÄÄÄÄÅlâÕ—Ω¿à∞Äâ°ΩµïâΩ‡µ›Ω…≠Õ°Ω¿µùÖ—ï›Ö‰à∞Äâ°ΩµïâΩ‡µçΩµ¡Öπ•Ω∏à∞Äâ°ΩµïâΩ‡µπÖ—•Ÿîât∞(ÄÄÄÄÄÄÄÄÄÄÄÅlâÕ—Ö…–à∞Äâ°ΩµïâΩ‡µπÖ—•Ÿîà∞Äâ°ΩµïâΩ‡µçΩµ¡Öπ•Ω∏à∞Äâ°ΩµïâΩ‡µ›Ω…≠Õ°Ω¿µùÖ—ï›Ö‰ât∞(ÄÄÄÄÄÄÄÅt§((ÄÄÄÅëïòÅ—ïÕ—}Õï±ïç—•Ωπ}≠ïï¡Õ}¡…•ŸÖ—ï}ô•±ïÕ}âÂ—ï}•ëïπ—•çÖ∞°Õï±ò§Ë(ÄÄÄÄÄÄÄÅ…’π—•µî∞Å¡…ïŸ•Ω’Ã∞ÅçÖπë•ëÖ—î∞ÅÕïπ—•πï±ÃÄÙÅÕï±òπÕï±ïç—•Ωπ}¡Ö•»†§(ÄÄÄÄÄÄÄÅâïôΩ…îÄÙÅÌ¡Ö—†ËÅ¡Ö—†π…ïÖë}âÂ—ïÃ†§ÅôΩ»Å¡Ö—†Å•∏ÅÕïπ—•πï±ÕÙ(ÄÄÄÄÄÄÄÅçÖ±±ÃÄÙÅmt(ÄÄÄÄÄÄÄÅÕï±òπÕï±ïç—}ô•·—’…ï}â’πë±î°…’π—•µî∞ÅçÖπë•ëÖ—î∞Å…’π}Õï…Ÿ•çïÃı±ÖµâëÑÅÖ…ùÃËÅçÖ±±ÃπÖ¡¡ïπê°±•Õ–°Ö…ùÃ§§∞(ÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÅŸï…•ô‰ı±ÖµâëÑÅ¡Ö—†ËÅŸÖ±•ëÖ—ï}â’πë±î°¡Ö—†§§(ÄÄÄÄÄÄÄÅÕï±òπÖÕÕï…—≈’Ö∞†°…’π—•µîÄºÄâ›Ω…¨ΩÖ¡¡±•çÖ—•Ω∏µç’……ïπ–à§π…ïÕΩ±Ÿî†§∞ÅçÖπë•ëÖ—îπ…ïÕΩ±Ÿî†§§(ÄÄÄÄÄÄÄÅÕï±òπÖÕÕï…—≈’Ö∞°Ì¡Ö—†ËÅ¡Ö—†π…ïÖë}âÂ—ïÃ†§ÅôΩ»Å¡Ö—†Å•∏ÅÕïπ—•πï±ÕÙ∞ÅâïôΩ…î§(ÄÄÄÄÄÄÄÅÕï±òπÖÕÕï…—≈’Ö∞°çÖ±±Ã∞Ål(ÄÄÄÄÄÄÄÄÄÄÄÅlâÕ—Ω¿à∞Äâ°ΩµïâΩ‡µ›Ω…≠Õ°Ω¿µùÖ—ï›Ö‰à∞Äâ°ΩµïâΩ‡µçΩµ¡Öπ•Ω∏à∞Äâ°ΩµïâΩ‡µπÖ—•Ÿîât∞(ÄÄÄÄÄÄÄÄÄÄÄÅlâÕ—Ö…–à∞Äâ°ΩµïâΩ‡µπÖ—•Ÿîà∞Äâ°ΩµïâΩ‡µçΩµ¡Öπ•Ω∏à∞Äâ°ΩµïâΩ‡µ›Ω…≠Õ°Ω¿µùÖ—ï›Ö‰ât∞(ÄÄÄÄÄÄÄÅt§((ÄÄÄÅëïòÅ—ïÕ—}¡’â±•Õ°ï…}…ïçï•¡—}…ï©ïç—Õ}Õ—Ö±ï}â’πë±ï}°ÖÕ°ïÃ°Õï±ò§Ë(ÄÄÄÄÄÄÄÅ•µ¡Ω…–Å…’π¡‰(ÄÄÄÄÄÄÄÅ¡…ïŸ•Ω’Ã∞ÅçÖπë•ëÖ—îÄÙÅÕï±òπ…ΩΩ–ÄºÄâ¡…ïŸ•Ω’Ãà∞ÅÕï±òπ…ΩΩ–ÄºÄâçÖπë•ëÖ—îà(ÄÄÄÄÄÄÄÅÕï±òπÕ—Öùî°¡…ïŸ•Ω’Ã§(ÄÄÄÄÄÄÄÅÕï±òπ›…•—î°Õï±òπÕΩ’…çî∞ÄâΩ¡ÃΩëïÕ≠—Ω¡}Ö¡§π¡‰à∞Åàâ5I-HÄÙÄùçÖπë•ëÖ—îùq∏à§(ÄÄÄÄÄÄÄÅÕï±òπ›…•—î°Õï±òπ¡’â±•å∞Äâ•πëï‡π°—µ∞à∞ÅàâçÖπë•ëÖ—îÅô…Ωπ—ïπêà§(ÄÄÄÄÄÄÄÅÕï±òπâ•πÖ…‰π›…•—ï}âÂ—ïÃ°àâçÖπë•ëÖ—îÅπÖ—•Ÿîà§(ÄÄÄÄÄÄÄÅÕï±òπÕ—Öùî°çÖπë•ëÖ—î§(ÄÄÄÄÄÄÄÅ¡…ïŸ•Ω’Õ}µÖπ•ôïÕ–∞ÅçÖπë•ëÖ—ï}µÖπ•ôïÕ–ÄÙÅŸÖ±•ëÖ—ï}â’πë±î°¡…ïŸ•Ω’Ã§∞ÅŸÖ±•ëÖ—ï}â’πë±î°çÖπë•ëÖ—î§(ÄÄÄÄÄÄÄÅ¡…ïŸ•Ω’Õ}µÖπ•ôïÕ—lâµÖπ•ôïÕ—}Õ°Ñ»‘ÿâtÄÙÅÕ°Ö}âÂ—ïÃ†°¡…ïŸ•Ω’ÃÄºÄâµÖπ•ôïÕ–π©ÕΩ∏à§π…ïÖë}âÂ—ïÃ†§§(ÄÄÄÄÄÄÄÅçÖπë•ëÖ—ï}µÖπ•ôïÕ—lâµÖπ•ôïÕ—}Õ°Ñ»‘ÿâtÄÙÅÕ°Ö}âÂ—ïÃ†°çÖπë•ëÖ—îÄºÄâµÖπ•ôïÕ–π©ÕΩ∏à§π…ïÖë}âÂ—ïÃ†§§(ÄÄÄÄÄÄÄÅ¡’â±•Õ°ï»ÄÙÅAÖ—†°}}ô•±ï}|§π…ïÕΩ±Ÿî†§π¡Ö…ïπ—Õl≈tÄºÄâëï¡±Ω‰Ω¡’â±•Õ†µ’Õï…Ãπ¡‰à(ÄÄÄÄÄÄÄÅπÖµïÕ¡ÖçîÄÙÅ…’π¡‰π…’π}¡Ö—†°Õ—»°¡’â±•Õ°ï»§∞Å…’π}πÖµîÙâ¡’â±•Õ°}’Õï…Õ}ô•·—’…îà§(ÄÄÄÄÄÄÄÅ…ïçï•¡–ÄÙÅÏ(ÄÄÄÄÄÄÄÄÄÄÄÄâï·ïç’—•Ωπ}ÕçΩ¡îàËÄâô•·—’…îµΩπ±‰à∞(ÄÄÄÄÄÄÄÄÄÄÄÄâ¡…ïŸ•Ω’Õ}â’πë±ï}µÖπ•ôïÕ—}Õ°Ñ»‘ÿàËÅ¡…ïŸ•Ω’Õ}µÖπ•ôïÕ—lâµÖπ•ôïÕ—}Õ°Ñ»‘ÿât∞(ÄÄÄÄÄÄÄÄÄÄÄÄâçÖπë•ëÖ—ï}â’πë±ï}µÖπ•ôïÕ—}Õ°Ñ»‘ÿàËÅçÖπë•ëÖ—ï}µÖπ•ôïÕ—lâµÖπ•ôïÕ—}Õ°Ñ»‘ÿât∞(ÄÄÄÄÄÄÄÄÄÄÄÄâ¡…ïŸ•Ω’Õ}πÖ—•Ÿï}Õ°Ñ»‘ÿàËÅ¡…ïŸ•Ω’Õ}µÖπ•ôïÕ—lâ¡…ΩŸïπÖπçîâulâπÖ—•Ÿï}Õ°Ñ»‘ÿât∞(ÄÄÄÄÄÄÄÄÄÄÄÄâçÖπë•ëÖ—ï}πÖ—•Ÿï}Õ°Ñ»‘ÿàËÅçÖπë•ëÖ—ï}µÖπ•ôïÕ—lâ¡…ΩŸïπÖπçîâulâπÖ—•Ÿï}Õ°Ñ»‘ÿât∞(ÄÄÄÄÄÄÄÄÄÄÄÄâç°ïç≠ÃàËÅÌπÖµîËÅQ…’îÅôΩ»ÅπÖµîÅ•∏ÅπÖµïÕ¡ÖçïlâIEU%I}!-LâuÙ∞(ÄÄÄÄÄÄÄÅÙ(ÄÄÄÄÄÄÄÅπÖµïÕ¡ÖçïlâŸÖ±•ëÖ—ï}µÖ—ç°ïë}…ïçï•¡–ât°…ïçï•¡–∞Å¡…ïŸ•Ω’Õ}µÖπ•ôïÕ–∞ÅçÖπë•ëÖ—ï}µÖπ•ôïÕ–∞ÅÖ±±Ω›}ô•·—’…îıQ…’î§(ÄÄÄÄÄÄÄÅ›•—†ÅÕï±òπÖÕÕï…—IÖ•ÕïÕIïùï‡°	’πë±ï……Ω»∞Äâô•·—’…îµΩπ±‰ÅïŸ•ëïπçîà§Ë(ÄÄÄÄÄÄÄÄÄÄÄÅπÖµïÕ¡ÖçïlâŸÖ±•ëÖ—ï}µÖ—ç°ïë}…ïçï•¡–ât°…ïçï•¡–∞Å¡…ïŸ•Ω’Õ}µÖπ•ôïÕ–∞ÅçÖπë•ëÖ—ï}µÖπ•ôïÕ–§(ÄÄÄÄÄÄÄÅ…ïçï•¡—lâçÖπë•ëÖ—ï}â’πë±ï}µÖπ•ôïÕ—}Õ°Ñ»‘ÿâtÄÙÄà¿àÄ®Äÿ–(ÄÄÄÄÄÄÄÅ›•—†ÅÕï±òπÖÕÕï…—IÖ•ÕïÕIïùï‡°	’πë±ï……Ω»∞ÄâëΩïÃÅπΩ–Åâ•πêà§Ë(ÄÄÄÄÄÄÄÄÄÄÄÅπÖµïÕ¡ÖçïlâŸÖ±•ëÖ—ï}µÖ—ç°ïë}…ïçï•¡–ât°…ïçï•¡–∞Å¡…ïŸ•Ω’Õ}µÖπ•ôïÕ–∞ÅçÖπë•ëÖ—ï}µÖπ•ôïÕ–∞ÅÖ±±Ω›}ô•·—’…îıQ…’î§((ÄÄÄÅëïòÅ—ïÕ—}•πï…—}…ï±ïÖÕï}ç±•}ŸÖ±•ëÖ—ïÕ}â’πë±ïÕ}›•—°Ω’—}Õï±ïç—•πù}Ω…}ôÖ≠•πù}ç°ïç≠Ã°Õï±ò§Ë(ÄÄÄÄÄÄÄÅ•µ¡Ω…–ÅçΩπ—ï·—±•à(ÄÄÄÄÄÄÄÅ•µ¡Ω…–Å•º(ÄÄÄÄÄÄÄÅ•µ¡Ω…–Å…’π¡‰(ÄÄÄÄÄÄÄÅ•µ¡Ω…–ÅÕÂÃ(ÄÄÄÄÄÄÄÅô…Ω¥Å’π•——ïÕ–πµΩç¨Å•µ¡Ω…–Å¡Ö—ç†(ÄÄÄÄÄÄÄÅ|∞Å¡…ïŸ•Ω’Ã∞ÅçÖπë•ëÖ—î∞ÅôÖ±±âÖç¨∞Å|ÄÙÅÕï±òπÕï±ïç—•Ωπ}—…•¡±î†§(ÄÄÄÄÄÄÄÅç±§ÄÙÅAÖ—†°}}ô•±ï}|§π…ïÕΩ±Ÿî†§π¡Ö…ïπ—Õl≈tÄºÄâëï¡±Ω‰ΩŸï…•ô‰µ…ï±ïÖÕîµ…Ω±±âÖç¨π¡‰à(ÄÄÄÄÄÄÄÅÖ…ùÃÄÙÅmÕ—»°ç±§§∞Äà¥µ¡…ïŸ•Ω’Ãà∞ÅÕ—»°¡…ïŸ•Ω’Ã§∞Äà¥µçÖπë•ëÖ—îà∞ÅÕ—»°çÖπë•ëÖ—î§∞(ÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄà¥µôÖ±±âÖç¨à∞ÅÕ—»°ôÖ±±âÖç¨•t(ÄÄÄÄÄÄÄÅΩ’—¡’–ÄÙÅ•ºπM—…•πù%<†§(ÄÄÄÄÄÄÄÅ›•—†Å¡Ö—ç†πΩâ©ïç–°ÕÂÃ∞ÄâÖ…ùÿà∞ÅÖ…ùÃ§∞ÅçΩπ—ï·—±•àπ…ïë•…ïç—}Õ—ëΩ’–°Ω’—¡’–§Ë(ÄÄÄÄÄÄÄÄÄÄÄÅ…’π¡‰π…’π}¡Ö—†°Õ—»°ç±§§∞Å…’π}πÖµîÙâ}}µÖ•π}|à§(ÄÄÄÄÄÄÄÅ…ï¡Ω…–ÄÙÅ©ÕΩ∏π±ΩÖëÃ°Ω’—¡’–πùï—ŸÖ±’î†§§(ÄÄÄÄÄÄÄÅÕï±òπÖÕÕï…—Q…’î°…ï¡Ω…—lâô•·—’…ï}Ωπ±‰ât§(ÄÄÄÄÄÄÄÅÕï±òπÖÕÕï…—≈’Ö∞°…ï¡Ω…—lâ¡…ΩçïÕÕïÕ}Õ—Ö…—ïêât∞Ä¿§(ÄÄÄÄÄÄÄÅÕï±òπÖÕÕï…—Ö±Õî°…ï¡Ω…—lâÕï±ïç—Ω…}ï·ï…ç•Õïêât§(ÄÄÄÄÄÄÄÅÕï±òπÖÕÕï…—≈’Ö∞°…ï¡Ω…—lâçΩµ¡Ö—•â•±•—Â}ç±Ö•¥ât∞Äâ’πç±Ö•µïêà§(ÄÄÄÄÄÄÄÅÕï±òπÖÕÕï…—≈’Ö∞°Õï–°…ï¡Ω…—lâŸÖ±•ëÖ—ïë}â’πë±ïÃât§∞ÅÏâ¡…ïŸ•Ω’Ãà∞ÄâçÖπë•ëÖ—îà∞ÄâôÖ±±âÖç¨âÙ§((ÄÄÄÅëïòÅ—ïÕ—}ô•·—’…ï}…Ω±±âÖç≠}ç±•}…ï©ïç—Õ}Ω¡ï…Ö—•ΩπÖ±}â’πë±ï}¡Ö—°Ã°Õï±ò§Ë(ÄÄÄÄÄÄÄÅ•µ¡Ω…–Å…’π¡‰(ÄÄÄÄÄÄÄÅ•µ¡Ω…–ÅÕÂÃ(ÄÄÄÄÄÄÄÅô…Ω¥Å’π•——ïÕ–πµΩç¨Å•µ¡Ω…–Å¡Ö—ç†(ÄÄÄÄÄÄÄÅç±§ÄÙÅAÖ—†°}}ô•±ï}|§π…ïÕΩ±Ÿî†§π¡Ö…ïπ—Õl≈tÄºÄâëï¡±Ω‰ΩŸï…•ô‰µ…ï±ïÖÕîµ…Ω±±âÖç¨π¡‰à(ÄÄÄÄÄÄÄÅ›•—†Å¡Ö—ç†πΩâ©ïç–°ÕÂÃ∞ÄâÖ…ùÿà∞ÅmÕ—»°ç±§§∞Äà¥µ¡…ïŸ•Ω’Ãà∞ÅÕ—»°AÖ—†°}}ô•±ï}|§π…ïÕΩ±Ÿî†§π¡Ö…ïπ—Õl≈t§∞(ÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄà¥µçÖπë•ëÖ—îà∞ÅÕ—»°AÖ—†°}}ô•±ï}|§π…ïÕΩ±Ÿî†§π¡Ö…ïπ—Õl≈t§∞(ÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄà¥µôÖ±±âÖç¨à∞ÅÕ—»°AÖ—†°}}ô•±ï}|§π…ïÕΩ±Ÿî†§π¡Ö…ïπ—Õl≈t•t§Ë(ÄÄÄÄÄÄÄÄÄÄÄÅ›•—†ÅÕï±òπÖÕÕï…—IÖ•ÕïÃ°MÂÕ—ïµ·•–§Ë(ÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÅ…’π¡‰π…’π}¡Ö—†°Õ—»°ç±§§∞Å…’π}πÖµîÙâ}}µÖ•π}|à§((ÄÄÄÅëïòÅ—ïÕ—}â’πë±ï}°ÖÕ°}µ•ÕµÖ—ç°}•Õ}…ï©ïç—ïê°Õï±ò§Ë(ÄÄÄÄÄÄÄÅ…ï±ïÖÕîÄÙÅÕï±òπ…ΩΩ–ÄºÄâ…ï±ïÖÕîà(ÄÄÄÄÄÄÄÅÕï±òπÕ—Öùî°…ï±ïÖÕî§(ÄÄÄÄÄÄÄÄ°…ï±ïÖÕîÄºÄâ≠•ΩÕ¨ΩëïçΩëï}çΩëïÃπ¡‰à§πç°µΩê†¡ºÿ––§(ÄÄÄÄÄÄÄÄ°…ï±ïÖÕîÄºÄâ≠•ΩÕ¨ΩëïçΩëï}çΩëïÃπ¡‰à§π›…•—ï}âÂ—ïÃ°àâç°Öπùïêà§(ÄÄÄÄÄÄÄÅ›•—†ÅÕï±òπÖÕÕï…—IÖ•ÕïÃ°	’πë±ï……Ω»§Ë(ÄÄÄÄÄÄÄÄÄÄÄÅŸÖ±•ëÖ—ï}â’πë±î°…ï±ïÖÕî§((ÄÄÄÅëïòÅ—ïÕ—}µΩëï}µ•ÕµÖ—ç°}•Õ}…ï©ïç—ïê°Õï±ò§Ë(ÄÄÄÄÄÄÄÅ…ï±ïÖÕîÄÙÅÕï±òπ…ΩΩ–ÄºÄâ…ï±ïÖÕîà(ÄÄÄÄÄÄÄÅÕï±òπÕ—Öùî°…ï±ïÖÕî§(ÄÄÄÄÄÄÄÄ°…ï±ïÖÕîÄºÄâπÖ—•ŸîΩ°ΩµïâΩ‡à§πç°µΩê†¡ºÿ––§(ÄÄÄÄÄÄÄÅ›•—†ÅÕï±òπÖÕÕï…—IÖ•ÕïÃ°	’πë±ï……Ω»§Ë(ÄÄÄÄÄÄÄÄÄÄÄÅŸÖ±•ëÖ—ï}â’πë±î°…ï±ïÖÕî§((ÄÄÄÅëïòÅ—ïÕ—}â’πë±ï}ï·ç±’ëïÕ}¡…•ŸÖ—ï}ëÖ—Ñ°Õï±ò§Ë(ÄÄÄÄÄÄÄÅôΩ»ÅπÖµîÅ•∏Ä†â›Ω…¨ΩΩ¡ÃΩ±ïëùï»πëàà∞ÄââÖëùîµ¡…•π–π≠ï‰à∞Äâ›Ω…¨ΩâÖÕï±•πîΩ—ïÕ–µÖççΩ’π–π©ÕΩ∏à∞(ÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄâ¡ï¡¡ï»à∞Äââ…Ω›Õï»µ¡…Ωô•±îΩA…ïôï…ïπçïÃà∞ÄââÖç≠’¡ÃΩÖ…ç°•Ÿîπ—Ö»à§Ë(ÄÄÄÄÄÄÄÄÄÄÄÄ°Õï±òπÕΩ’…çîÄºÅπÖµî§πç°µΩê†¿§(ÄÄÄÄÄÄÄÅ…ï±ïÖÕîÄÙÅÕï±òπ…ΩΩ–ÄºÄâ…ï±ïÖÕîà(ÄÄÄÄÄÄÄÅô…Ω¥Å’π•——ïÕ–πµΩç¨Å•µ¡Ω…–Å¡Ö—ç†(ÄÄÄÄÄÄÄÅ•µ¡Ω…–Å…ï±ïÖÕï}â’πë±î(ÄÄÄÄÄÄÄÅ¡…Ω—ïç—ïêÄÙÅÌÕï±òπÕΩ’…çîÄºÅπÖµîÅôΩ»ÅπÖµîÅ•∏Ä†(ÄÄÄÄÄÄÄÄÄÄÄÄâ›Ω…¨ΩΩ¡ÃΩ±ïëùï»πëàà∞ÄââÖëùîµ¡…•π–π≠ï‰à∞Äâ›Ω…¨ΩâÖÕï±•πîΩ—ïÕ–µÖççΩ’π–π©ÕΩ∏à∞(ÄÄÄÄÄÄÄÄÄÄÄÄâ¡ï¡¡ï»à∞Äââ…Ω›Õï»µ¡…Ωô•±îΩA…ïôï…ïπçïÃà∞ÄââÖç≠’¡ÃΩÖ…ç°•Ÿîπ—Ö»à•Ù(ÄÄÄÄÄÄÄÅ°ÖÕ°}ô•±î∞ÅçΩ¡Â}ô•±îÄÙÅ…ï±ïÖÕï}â’πë±îπ}°ÖÕ†∞Å…ï±ïÖÕï}â’πë±îπÕ°’—•∞πçΩ¡Âô•±î(ÄÄÄÄÄÄÄÅëïòÅç°ïç≠ïë}°ÖÕ†°¡Ö—†§Ë(ÄÄÄÄÄÄÄÄÄÄÄÅ•òÅAÖ—†°¡Ö—†§Å•∏Å¡…Ω—ïç—ïêË(ÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÅ…Ö•ÕîÅÕÕï…—•Ωπ……Ω»†â¡…•ŸÖ—îÅÕïπ—•πï∞Å›ÖÃÅ…ïÖêà§(ÄÄÄÄÄÄÄÄÄÄÄÅ…ï—’…∏Å°ÖÕ°}ô•±î°¡Ö—†§(ÄÄÄÄÄÄÄÅëïòÅç°ïç≠ïë}çΩ¡‰°Õ…å∞ÅëÕ–∞Ä©Ö…ùÃ∞Ä®©≠›Ö…ùÃ§Ë(ÄÄÄÄÄÄÄÄÄÄÄÅ•òÅAÖ—†°Õ…å§Å•∏Å¡…Ω—ïç—ïêË(ÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÅ…Ö•ÕîÅÕÕï…—•Ωπ……Ω»†â¡…•ŸÖ—îÅÕïπ—•πï∞Å›ÖÃÅçΩ¡•ïêà§(ÄÄÄÄÄÄÄÄÄÄÄÅ…ï—’…∏ÅçΩ¡Â}ô•±î°Õ…å∞ÅëÕ–∞Ä©Ö…ùÃ∞Ä®©≠›Ö…ùÃ§(ÄÄÄÄÄÄÄÅ›•—†Å¡Ö—ç†πΩâ©ïç–°…ï±ïÖÕï}â’πë±î∞Äâ}°ÖÕ†à∞ÅÕ•ëï}ïôôïç–ıç°ïç≠ïë}°ÖÕ†§∞Åp(ÄÄÄÄÄÄÄÄÄÄÄÄÅ¡Ö—ç†πΩâ©ïç–°…ï±ïÖÕï}â’πë±îπÕ°’—•∞∞ÄâçΩ¡Âô•±îà∞ÅÕ•ëï}ïôôïç–ıç°ïç≠ïë}çΩ¡‰§Ë(ÄÄÄÄÄÄÄÄÄÄÄÅµÖπ•ôïÕ–ÄÙÅÕï±òπÕ—Öùî°…ï±ïÖÕî§(ÄÄÄÄÄÄÄÅÕï…•Ö±•ÈïêÄÙÅ©ÕΩ∏πë’µ¡Ã°µÖπ•ôïÕ–§(ÄÄÄÄÄÄÄÅôΩ»ÅÕïπ—•πï∞Å•∏Ä†â±ïëùï»ÅÕïπ—•πï∞à∞ÄââÖëùîÅÕïç…ï–ÅÕïπ—•πï∞à∞ÄâÖççΩ’π–ÅÕïπ—•πï∞à∞(ÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄâ¡ï¡¡ï»ÅÕïπ—•πï∞à∞Äâ¡…Ωô•±îÅÕïπ—•πï∞à∞ÄââÖç≠’¿ÅÕïπ—•πï∞à§Ë(ÄÄÄÄÄÄÄÄÄÄÄÅÕï±òπÖÕÕï…—9Ω—%∏°Õïπ—•πï∞∞ÅÕï…•Ö±•Èïê§(ÄÄÄÄÄÄÄÅÕï±òπÖÕÕï…—Ö±Õî°Öπ‰†°…ï±ïÖÕîÄºÅπÖµî§πï·•Õ—Ã†§ÅôΩ»ÅπÖµîÅ•∏Ä†(ÄÄÄÄÄÄÄÄÄÄÄÄâ›Ω…¨ΩΩ¡ÃΩ±ïëùï»πëàà∞ÄââÖëùîµ¡…•π–π≠ï‰à∞Äâ›Ω…¨ΩâÖÕï±•πîΩ—ïÕ–µÖççΩ’π–π©ÕΩ∏à∞(ÄÄÄÄÄÄÄÄÄÄÄÄâ¡ï¡¡ï»à∞Äââ…Ω›Õï»µ¡…Ωô•±îΩA…ïôï…ïπçïÃà∞ÄââÖç≠’¡ÃΩÖ…ç°•Ÿîπ—Ö»à§§§((ÄÄÄÅëïòÅ—ïÕ—}±ïùÖçÂ}—Ö…ùï—}›•—°Ω’—}µÖ—ç°•πù}ÕΩ’…çï}ôÖ•±Õ}âïôΩ…ï}Õï±ïç—•Ω∏°Õï±ò§Ë(ÄÄÄÄÄÄÄÅ±ïùÖç‰ÄÙÅÕï±òπ…ΩΩ–ÄºÄâçÖç§∏ƒà(ÄÄÄÄÄÄÄÅ±ïùÖç‰πµ≠ë•»†§(ÄÄÄÄÄÄÄÅçÖ±±ÃÄÙÅmt(ÄÄÄÄÄÄÄÅëïòÅŸÖ±•ëÖ—ï}—°ïπ}Õï±ïç–†§Ë(ÄÄÄÄÄÄÄÄÄÄÄÅŸÖ±•ëÖ—ï}â’πë±î°±ïùÖç‰§(ÄÄÄÄÄÄÄÄÄÄÄÅçÖ±±ÃπÖ¡¡ïπê†âÕï±ïç—ïêà§(ÄÄÄÄÄÄÄÅ›•—†ÅÕï±òπÖÕÕï…—IÖ•ÕïÃ°	’πë±ï……Ω»§Ë(ÄÄÄÄÄÄÄÄÄÄÄÅŸÖ±•ëÖ—ï}—°ïπ}Õï±ïç–†§(ÄÄÄÄÄÄÄÅÕï±òπÖÕÕï…—≈’Ö∞°çÖ±±Ã∞Åmt§((ÄÄÄÅëïòÅ—ïÕ—}’πµÖ—ç°ïë}â’•±ë}Ω…}—ïÕ—}…ïçï•¡—}•Õ}…ï©ïç—ïê°Õï±ò§Ë(ÄÄÄÄÄÄÄÅ¡…ΩŸïπÖπçîÄÙÅÕï±òπ¡…ΩŸïπÖπçî†§(ÄÄÄÄÄÄÄÅ¡…ΩŸïπÖπçïlâ—ïÕ—}…ïçï•¡–âulâÕΩ’…çï}µÖπ•ôïÕ—}ë•ùïÕ–âtÄÙÄâîàÄ®Äÿ–(ÄÄÄÄÄÄÄÅ¡…ΩŸïπÖπçïlâ—ïÕ—}…ïçï•¡—}…Ö‹âtÄÙÅ©ÕΩ∏πë’µ¡Ã°¡…ΩŸïπÖπçïlâ—ïÕ—}…ïçï•¡–ât∞ÅÕΩ…—}≠ïÂÃıQ…’î∞Å•πëïπ–Ù»§(ÄÄÄÄÄÄÄÅ¡…ΩŸïπÖπçïlâ—ïÕ—}…ïçï•¡—}Õ°Ñ»‘ÿâtÄÙÅÕ°Ö}âÂ—ïÃ°¡…ΩŸïπÖπçïlâ—ïÕ—}…ïçï•¡—}…Ö‹âtπïπçΩëî†§§(ÄÄÄÄÄÄÄÅ¡…ΩŸïπÖπçïlâ—ïÕ—}…ïçï•¡—}çÖπΩπ•çÖ±}Õ°Ñ»‘ÿâtÄÙÅçÖπΩπ•çÖ±}°ÖÕ†°¡…ΩŸïπÖπçïlâ—ïÕ—}…ïçï•¡–ât§(ÄÄÄÄÄÄÄÅ›•—†ÅÕï±òπÖÕÕï…—IÖ•ÕïÃ°	’πë±ï……Ω»§Ë(ÄÄÄÄÄÄÄÄÄÄÄÅÕï±òπÕ—Öùî°Õï±òπ…ΩΩ–ÄºÄââÖêµ…ïçï•¡–à∞Å¡…ΩŸïπÖπçî§((ÄÄÄÅëïòÅ—ïÕ—}’πï·¡ïç—ïë}ÕΩ’…çï}ô•±ï}Ω…}…ïçï•¡—}µ•ÕµÖ—ç°}•Õ}…ï©ïç—ïê°Õï±ò§Ë(ÄÄÄÄÄÄÄÅ¡…ΩŸïπÖπçîÄÙÅÕï±òπ¡…ΩŸïπÖπçî†§(ÄÄÄÄÄÄÄÅÕï±òπ›…•—î°Õï±òπÕΩ’…çî∞ÄâΩ¡ÃΩπΩ–µ•∏µçÖ¡—’…îπ¡‰à∞Åàâπï‹ÅÕΩ’…çîà§(ÄÄÄÄÄÄÄÅ›•—†ÅÕï±òπÖÕÕï…—IÖ•ÕïÃ°	’πë±ï……Ω»§Ë(ÄÄÄÄÄÄÄÄÄÄÄÅÕï±òπÕ—Öùî°Õï±òπ…ΩΩ–ÄºÄâç°ÖπùïêµÕΩ’…çîà∞Å¡…ΩŸïπÖπçî§((ÄÄÄÅëïòÅ—ïÕ—}¡’â±•ç}—…ïï}µ’Õ—}µÖ—ç°}çÖ¡—’…ïë}°ÖÕ°ïÕ}Öπë}Õ•ÈïÃ°Õï±ò§Ë(ÄÄÄÄÄÄÄÅ¡…ΩŸïπÖπçîÄÙÅÕï±òπ¡…ΩŸïπÖπçî†§(ÄÄÄÄÄÄÄÅ¡…ΩŸïπÖπçïlâ¡’â±•ç}ô•±ïÃâulâ•πëï‡π°—µ∞âulâÕ°Ñ»‘ÿâtÄÙÄà¿àÄ®Äÿ–(ÄÄÄÄÄÄÄÅ›•—†ÅÕï±òπÖÕÕï…—IÖ•ÕïÃ°	’πë±ï……Ω»§Ë(ÄÄÄÄÄÄÄÄÄÄÄÅÕï±òπÕ—Öùî°Õï±òπ…ΩΩ–ÄºÄââÖêµ¡’â±•åà∞Å¡…ΩŸïπÖπçî§((ÄÄÄÅëïòÅ—ïÕ—}ïÕçÖ¡•πù}ÕΩ’…çï}±•π≠}•Õ}…ï©ïç—ïê°Õï±ò§Ë(ÄÄÄÄÄÄÄÅΩ’—Õ•ëîÄÙÅÕï±òπ…ΩΩ–ÄºÄâΩ’—Õ•ëîπ¡‰à(ÄÄÄÄÄÄÄÅΩ’—Õ•ëîπ›…•—ï}âÂ—ïÃ°àâΩ’—Õ•ëîà§(ÄÄÄÄÄÄÄÄ°Õï±òπÕΩ’…çîÄºÄâΩ¡ÃΩïÕçÖ¡îπ¡‰à§πÕÂµ±•π≠}—º°Ω’—Õ•ëî§(ÄÄÄÄÄÄÄÅ›•—†ÅÕï±òπÖÕÕï…—IÖ•ÕïÃ°	’πë±ï……Ω»§Ë(ÄÄÄÄÄÄÄÄÄÄÄÅÕï±òπÕ—Öùî°Õï±òπ…ΩΩ–ÄºÄâïÕçÖ¡•πúµ±•π¨à§(((ÄÄÄÅëïòÅ—ïÕ—}ÕÂµ±•π≠ïë}µÖπ•ôïÕ—}•Õ}…ï©ïç—ïë}›•—°Ω’—}…ïÖë•πù}—Ö…ùï–°Õï±ò§Ë(ÄÄÄÄÄÄÄÅ•µ¡Ω…–Å…ï±ïÖÕï}â’πë±î(ÄÄÄÄÄÄÄÅô…Ω¥Å’π•——ïÕ–πµΩç¨Å•µ¡Ω…–Å¡Ö—ç†(ÄÄÄÄÄÄÄÅ…ï±ïÖÕîÄÙÅÕï±òπ…ΩΩ–ÄºÄâ…ï±ïÖÕîà(ÄÄÄÄÄÄÄÅÕï±òπÕ—Öùî°…ï±ïÖÕî§(ÄÄÄÄÄÄÄÅï·—ï…πÖ∞ÄÙÅÕï±òπ…ΩΩ–ÄºÄâï·—ï…πÖ∞µµÖπ•ôïÕ–π©ÕΩ∏à(ÄÄÄÄÄÄÄÅΩ…•ù•πÖ±}µÖπ•ôïÕ–ÄÙÅ…ï±ïÖÕîÄºÄâµÖπ•ôïÕ–π©ÕΩ∏à(ÄÄÄÄÄÄÄÅ…ï±ïÖÕîπç°µΩê†¡º‹‘‘§(ÄÄÄÄÄÄÄÅΩ…•ù•πÖ±}µÖπ•ôïÕ–πç°µΩê†¡ºÿ––§(ÄÄÄÄÄÄÄÅï·—ï…πÖ∞π›…•—ï}âÂ—ïÃ°Ω…•ù•πÖ±}µÖπ•ôïÕ–π…ïÖë}âÂ—ïÃ†§§(ÄÄÄÄÄÄÄÅΩ…•ù•πÖ±}µÖπ•ôïÕ–π’π±•π¨†§(ÄÄÄÄÄÄÄÅΩ…•ù•πÖ±}µÖπ•ôïÕ–πÕÂµ±•π≠}—º°ï·—ï…πÖ∞§(ÄÄÄÄÄÄÄÅ•µ¡Ω…–ÅΩÃ(ÄÄÄÄÄÄÄÅ…ïÖëÃÄÙÅmt(ÄÄÄÄÄÄÄÅ¡Ö—°}Ω¡ï∏∞ÅΩÕ}Ω¡ï∏ÄÙÅAÖ—†πΩ¡ï∏∞ÅΩÃπΩ¡ï∏(ÄÄÄÄÄÄÄÅëïòÅ—…Öçïë}¡Ö—°}Ω¡ï∏°¡Ö—†∞Ä©Ö…ùÃ∞Ä®©≠›Ö…ùÃ§Ë(ÄÄÄÄÄÄÄÄÄÄÄÅ•òÅ¡Ö—†Å•∏Ä°Ω…•ù•πÖ±}µÖπ•ôïÕ–∞Åï·—ï…πÖ∞§Ë(ÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÅ…ïÖëÃπÖ¡¡ïπê°¡Ö—†§(ÄÄÄÄÄÄÄÄÄÄÄÅ…ï—’…∏Å¡Ö—°}Ω¡ï∏°¡Ö—†∞Ä©Ö…ùÃ∞Ä®©≠›Ö…ùÃ§(ÄÄÄÄÄÄÄÅëïòÅ—…Öçïë}ΩÕ}Ω¡ï∏°¡Ö—†∞Ä©Ö…ùÃ∞Ä®©≠›Ö…ùÃ§Ë(ÄÄÄÄÄÄÄÄÄÄÄÅ•òÅAÖ—†°¡Ö—†§Å•∏Ä°Ω…•ù•πÖ±}µÖπ•ôïÕ–∞Åï·—ï…πÖ∞§Ë(ÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÅ…ïÖëÃπÖ¡¡ïπê°AÖ—†°¡Ö—†§§(ÄÄÄÄÄÄÄÄÄÄÄÅ…ï—’…∏ÅΩÕ}Ω¡ï∏°¡Ö—†∞Ä©Ö…ùÃ∞Ä®©≠›Ö…ùÃ§(ÄÄÄÄÄÄÄÅ›•—†Å¡Ö—ç†πΩâ©ïç–°AÖ—†∞ÄâΩ¡ï∏à∞Å—…Öçïë}¡Ö—°}Ω¡ï∏§∞Å¡Ö—ç†πΩâ©ïç–°ΩÃ∞ÄâΩ¡ï∏à∞Å—…Öçïë}ΩÕ}Ω¡ï∏§Ë(ÄÄÄÄÄÄÄÄÄÄÄÅ›•—†ÅÕï±òπÖÕÕï…—IÖ•ÕïÃ°	’πë±ï……Ω»§Ë(ÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÅŸÖ±•ëÖ—ï}â’πë±î°…ï±ïÖÕî§(ÄÄÄÄÄÄÄÅÕï±òπÖÕÕï…—≈’Ö∞°…ïÖëÃ∞Åmt§(((ÄÄÄÅëïòÅ—ïÕ—}ÕÂµ±•π≠ïë}…ï±ïÖÕï}•Õ}…ï©ïç—ïë}âïôΩ…ï}ô•±ï}…ïÖëÃ°Õï±ò§Ë(ÄÄÄÄÄÄÄÅô…Ω¥Å’π•——ïÕ–πµΩç¨Å•µ¡Ω…–Å¡Ö—ç†(ÄÄÄÄÄÄÄÅ—Ö…ùï–ÄÙÅÕï±òπ…ΩΩ–ÄºÄâ—Ö…ùï–à(ÄÄÄÄÄÄÄÅÕï±òπÕ—Öùî°—Ö…ùï–§(ÄÄÄÄÄÄÄÅ…ï±ïÖÕîÄÙÅÕï±òπ…ΩΩ–ÄºÄâ…ï±ïÖÕîµ±•π¨à(ÄÄÄÄÄÄÄÅ…ï±ïÖÕîπÕÂµ±•π≠}—º°—Ö…ùï–∞Å—Ö…ùï—}•Õ}ë•…ïç—Ω…‰ıQ…’î§(ÄÄÄÄÄÄÄÅ…ïÖëÃÄÙÅmt(ÄÄÄÄÄÄÄÅ¡Ö—°}Ω¡ï∏ÄÙÅAÖ—†πΩ¡ï∏(ÄÄÄÄÄÄÄÅëïòÅ—…Öçïë}Ω¡ï∏°¡Ö—†∞Ä©Ö…ùÃ∞Ä®©≠›Ö…ùÃ§Ë(ÄÄÄÄÄÄÄÄÄÄÄÅ…ïÖëÃπÖ¡¡ïπê°¡Ö—†§(ÄÄÄÄÄÄÄÄÄÄÄÅ…ï—’…∏Å¡Ö—°}Ω¡ï∏°¡Ö—†∞Ä©Ö…ùÃ∞Ä®©≠›Ö…ùÃ§(ÄÄÄÄÄÄÄÅ›•—†Å¡Ö—ç†πΩâ©ïç–°AÖ—†∞ÄâΩ¡ï∏à∞Å—…Öçïë}Ω¡ï∏§Ë(ÄÄÄÄÄÄÄÄÄÄÄÅ›•—†ÅÕï±òπÖÕÕï…—IÖ•ÕïÃ°	’πë±ï……Ω»§Ë(ÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÅŸÖ±•ëÖ—ï}â’πë±î°…ï±ïÖÕî§(ÄÄÄÄÄÄÄÅÕï±òπÖÕÕï…—≈’Ö∞°…ïÖëÃ∞Åmt§((ÄÄÄÅëïòÅ—ïÕ—}’πï·¡ïç—ïë}¡…•ŸÖ—ï}µïµâï…}•Õ}…ï©ïç—ïë}âïôΩ…ï}…ïÖê°Õï±ò§Ë(ÄÄÄÄÄÄÄÅ•µ¡Ω…–Å…ï±ïÖÕï}â’πë±î(ÄÄÄÄÄÄÄÅô…Ω¥Å’π•——ïÕ–πµΩç¨Å•µ¡Ω…–Å¡Ö—ç†(ÄÄÄÄÄÄÄÅ…ï±ïÖÕîÄÙÅÕï±òπ…ΩΩ–ÄºÄâ…ï±ïÖÕîà(ÄÄÄÄÄÄÄÅÕï±òπÕ—Öùî°…ï±ïÖÕî§(ÄÄÄÄÄÄÄÅ¡…•ŸÖ—îÄÙÅ…ï±ïÖÕîÄºÄâ›Ω…¨ΩΩ¡ÃΩ±ïëùï»πëàà(ÄÄÄÄÄÄÄÅ…ï±ïÖÕîπç°µΩê†¡º‹‘‘§(ÄÄÄÄÄÄÄÅ¡…•ŸÖ—îπ¡Ö…ïπ–πµ≠ë•»°¡Ö…ïπ—ÃıQ…’î§(ÄÄÄÄÄÄÄÅ¡…•ŸÖ—îπ›…•—ï}âÂ—ïÃ°àâ•π©ïç—ïêÅ¡…•ŸÖ—îÅÕïπ—•πï∞à§(ÄÄÄÄÄÄÄÅ¡…•ŸÖ—îπç°µΩê†¡º–––§(ÄÄÄÄÄÄÄÅ¡…•ŸÖ—îπ¡Ö…ïπ–πç°µΩê†¡º‘‘‘§(ÄÄÄÄÄÄÄÄ°…ï±ïÖÕîÄºÄâ›Ω…¨à§πç°µΩê†¡º‘‘‘§(ÄÄÄÄÄÄÄÅ…ï±ïÖÕîπç°µΩê†¡º‘‘‘§(ÄÄÄÄÄÄÄÅ•µ¡Ω…–ÅΩÃ(ÄÄÄÄÄÄÄÅ…ïÖëÃÄÙÅmt(ÄÄÄÄÄÄÄÅ¡Ö—°}Ω¡ï∏∞ÅΩÕ}Ω¡ï∏ÄÙÅAÖ—†πΩ¡ï∏∞ÅΩÃπΩ¡ï∏(ÄÄÄÄÄÄÄÅëïòÅ—…Öçïë}¡Ö—°}Ω¡ï∏°¡Ö—†∞Ä©Ö…ùÃ∞Ä®©≠›Ö…ùÃ§Ë(ÄÄÄÄÄÄÄÄÄÄÄÅ•òÅ¡Ö—†ÄÙÙÅ¡…•ŸÖ—îË(ÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÅ…ïÖëÃπÖ¡¡ïπê°¡Ö—†§(ÄÄÄÄÄÄÄÄÄÄÄÅ…ï—’…∏Å¡Ö—°}Ω¡ï∏°¡Ö—†∞Ä©Ö…ùÃ∞Ä®©≠›Ö…ùÃ§(ÄÄÄÄÄÄÄÅëïòÅ—…Öçïë}ΩÕ}Ω¡ï∏°¡Ö—†∞Ä©Ö…ùÃ∞Ä®©≠›Ö…ùÃ§Ë(ÄÄÄÄÄÄÄÄÄÄÄÅ•òÅAÖ—†°¡Ö—†§ÄÙÙÅ¡…•ŸÖ—îË(ÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÅ…ïÖëÃπÖ¡¡ïπê°AÖ—†°¡Ö—†§§(ÄÄÄÄÄÄÄÄÄÄÄÅ…ï—’…∏ÅΩÕ}Ω¡ï∏°¡Ö—†∞Ä©Ö…ùÃ∞Ä®©≠›Ö…ùÃ§(ÄÄÄÄÄÄÄÅ›•—†Å¡Ö—ç†πΩâ©ïç–°AÖ—†∞ÄâΩ¡ï∏à∞Å—…Öçïë}¡Ö—°}Ω¡ï∏§∞Å¡Ö—ç†πΩâ©ïç–°ΩÃ∞ÄâΩ¡ï∏à∞Å—…Öçïë}ΩÕ}Ω¡ï∏§Ë(ÄÄÄÄÄÄÄÄÄÄÄÅ›•—†ÅÕï±òπÖÕÕï…—IÖ•ÕïÃ°	’πë±ï……Ω»§Ë(ÄÄÄÄÄÄÄÄÄÄÄÄÄÄÄÅŸÖ±•ëÖ—ï}â’πë±î°…ï±ïÖÕî§(ÄÄÄÄÄÄÄÅÕï±òπÖÕÕï…—≈’Ö∞°…ïÖëÃ∞Åmt§((ÄÄÄÅëïòÅ—ïÕ—}¡’â±•Õ°ï…}•µ¡Ω…—}•Õ}•πï…–°Õï±ò§Ë(ÄÄÄÄÄÄÄÅ•µ¡Ω…–Å…’π¡‰(ÄÄÄÄÄÄÄÅô…Ω¥Å’π•——ïÕ–πµΩç¨Å•µ¡Ω…–Å¡Ö—ç†(ÄÄÄÄÄÄÄÅ¡’â±•Õ°ï»ÄÙÅAÖ—†°}}ô•±ï}|§π…ïÕΩ±Ÿî†§π¡Ö…ïπ—Õl≈tÄºÄâëï¡±Ω‰Ω¡’â±•Õ†µ’Õï…Ãπ¡‰à(ÄÄÄÄÄÄÄÅ›•—†Å¡Ö—ç††âÕ’â¡…ΩçïÕÃπ…’∏à∞ÅÕ•ëï}ïôôïç–ıÕÕï…—•Ωπ……Ω»†â¡’â±•Õ°ï»Åï·ïç’—ïêà§§Ë(ÄÄÄÄÄÄÄÄÄÄÄÅπÖµïÕ¡ÖçîÄÙÅ…’π¡‰π…’π}¡Ö—†°Õ—»°¡’â±•Õ°ï»§∞Å…’π}πÖµîÙâ¡’â±•Õ°}’Õï…Õ}•µ¡Ω…–à§(ÄÄÄÄÄÄÄÅÕï±òπÖÕÕï…—Q…’î°çÖ±±Öâ±î°πÖµïÕ¡ÖçïlâµÖ•∏ât§§(()•òÅ}}πÖµï}|ÄÙÙÄâ}}µÖ•π}|àË(ÄÄÄÅ’π•——ïÕ–πµÖ•∏†§