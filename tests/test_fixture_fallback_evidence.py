import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
WORK = PROJECT / 'work/queue-coordinator'
SPEC = importlib.util.spec_from_file_location('verify_release_rollback_fixture',
    PROJECT / 'deploy/verify-release-rollback.py')
VERIFIER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFIER
SPEC.loader.exec_module(VERIFIER)


class FixtureFallbackEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='test-fallback-evidence-', dir=WORK)
        self.root = Path(self.temp.name)
        self.evidence_path = self.root / 'evidence.json'
        bundle_root = WORK / 'whole-map-ocf-workflow-gap-live-note-20261010'
        self.packages = tuple(bundle_root / name for name in 'OCF')
        self._reset_reports()

    def tearDown(self):
        self.temp.cleanup()

    def _reset_reports(self):
        self.evidence = json.loads((WORK / 'fallback-evidence-live-note-20261010.json').read_text())
        self.rooms = json.loads((WORK / 'packaged-room-fallback-evidence-live-note-20261010.json').read_text())
        self.native = json.loads((WORK / 'native-ocf-process-live-note-20261010.json').read_text())
        for label, report in (('rooms', self.rooms), ('native_process', self.native)):
            target = self.root / f'{label}.json'
            target.write_text(json.dumps(report, sort_keys=True))
            relative = target.relative_to(WORK).as_posix()
            self.evidence['assertion_sources'][label] = {
                **self.evidence['assertion_sources'][label], 'path': relative,
                'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}
        self._write_evidence()

    def _write_report(self, label):
        report = self.rooms if label == 'rooms' else self.native
        target = self.root / f'{label}.json'
        target.write_text(json.dumps(report, sort_keys=True))
        self.evidence['assertion_sources'][label]['sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
        self._write_evidence()

    def _write_evidence(self):
        self.evidence_path.write_text(json.dumps(self.evidence, sort_keys=True))

    def test_packaged_report_binds_shelf_label_note_and_publisher_assertions(self):
        required = {
            'shelf_observation_history_private_note_quantity',
            'shelf_draft_cancel_response_loss_request_key_recovery',
            'reviewed_label_raster_intent_recovery_zero_print_calls',
            'uncertain_item_note_after_native_commit_exactly_once_recovery',
            'matched_previous_release_preserves_new_fixture_profiles_and_loans',
            'legacy_missing_member_api_is_not_a_rollback_target',
        }
        missing = required - set(self.native.get('workflow_assertions', {}))
        self.assertFalse(missing, f'packaged workflow proof is missing {sorted(missing)}')

    def _room(self, mutator):
        mutator(self.rooms)
        self._write_report('rooms')

    def _native(self, mutator):
        mutator(self.native)
        self._write_report('native_process')

    def test_bound_evidence_accepts_complete_reports(self):
        checks = VERIFIER._load_fallback_evidence(self.evidence_path, self.packages)
        self.assertEqual(set(checks), set(self.evidence['checks']))

    def test_same_evidence_binds_f_to_c_return_preflight(self):
        checks = VERIFIER._load_fallback_evidence(
            self.evidence_path, (self.packages[2], self.packages[1], self.packages[2]))
        self.assertEqual(set(checks), set(self.evidence['checks']))

    def test_rejects_missing_empty_and_changed_rooms_identity_rows(self):
        mutations = (
            lambda d: d.update(rooms_store_identity_trace=[{}, {}, {}, {}]),
            lambda d: d['rooms_store_identity_trace'][0].pop('device'),
            lambda d: d['rooms_store_identity_trace'][1].update(device=0),
            lambda d: d['rooms_store_identity_trace'][2].update(inode=0),
            lambda d: d['rooms_store_identity_trace'][3].update(inode=d['rooms_store_identity_trace'][3]['inode'] + 1),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self._reset_reports()
                self._room(mutate)
                with self.assertRaises(VERIFIER.FixtureRefusal):
                    VERIFIER._load_fallback_evidence(self.evidence_path, self.packages)

    def test_rejects_missing_empty_changed_native_identities_and_profile_hash(self):
        mutations = (
            lambda d: d['trace'][0].pop('native_store_identity'),
            lambda d: d['trace'][0].update(native_store_identity=[]),
            lambda d: d['trace'][1].update(ledger_store_identity=[0, 0]),
            lambda d: d['trace'][2].update(native_store_identity=[99, 99]),
            lambda d: d['trace'][3].pop('member_profile_sha256'),
            lambda d: d['trace'][1].update(member_profile_sha256='not-a-hash'),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self._reset_reports()
                self._native(mutate)
                with self.assertRaises(VERIFIER.FixtureRefusal):
                    VERIFIER._load_fallback_evidence(self.evidence_path, self.packages)

    def test_rejects_missing_invalid_or_changed_loan_bindings(self):
        mutations = (
            lambda d: d['trace'][0].pop('loan_operation_id'),
            lambda d: d['trace'][0].update(loan_operation_id='not-a-uuid'),
            lambda d: d['trace'][1].update(loan_operation_id='00000000-0000-0000-0000-000000000000'),
            lambda d: d['trace'][2].pop('loan_created_at'),
            lambda d: d['trace'][0].update(loan_confirmed_at='yesterday'),
            lambda d: d['trace'][3].update(loan_created_at='2026-10-09T20:46:34+00:00'),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self._reset_reports()
                self._native(mutate)
                with self.assertRaises(VERIFIER.FixtureRefusal):
                    VERIFIER._load_fallback_evidence(self.evidence_path, self.packages)

    def test_rejects_replicated_nil_uuid_and_boolean_zero_counters(self):
        cases = (
            ('native_nil_uuid', lambda d: [row.update(loan_operation_id='00000000-0000-0000-0000-000000000000') for row in d['trace']]),
            ('native_boolean_counter', lambda d: d.update(restore_replay_calls=False)),
            ('rooms_boolean_counter', lambda d: d['audit'].update(database_copy_calls=False)),
        )
        for label, mutate in cases:
            with self.subTest(label=label):
                self._reset_reports()
                if label.startswith('native'):
                    self._native(mutate)
                else:
                    self._room(mutate)
                with self.assertRaises(VERIFIER.FixtureRefusal):
                    VERIFIER._load_fallback_evidence(self.evidence_path, self.packages)

    def test_rejects_malformed_report_objects_and_missing_trace_rows(self):
        cases = (
            ('rooms', lambda d: d.update(assertions=[])),
            ('rooms', lambda d: d.update(audit=None)),
            ('rooms', lambda d: d.update(rooms_store_identity={'device': 1, 'inode': 1})),
            ('native_process', lambda d: d.update(trace=[{}, {}, {}, {}])),
            ('native_process', lambda d: d.pop('process_assertions')),
        )
        for label, mutate in cases:
            with self.subTest(label=label, mutate=mutate):
                self._reset_reports()
                if label == 'rooms':
                    self._room(mutate)
                else:
                    self._native(mutate)
                with self.assertRaises(VERIFIER.FixtureRefusal):
                    VERIFIER._load_fallback_evidence(self.evidence_path, self.packages)

    def test_rejects_native_state_assertions_that_diverge_from_trace(self):
        mutations = (
            lambda d: d['process_assertions'][7].update(native_store_identity=[99, 99]),
            lambda d: d['process_assertions'][7].update(ledger_store_identity=[88, 88]),
            lambda d: d['process_assertions'][7].update(profile_sha256='0' * 64),
            lambda d: d['process_assertions'][7].update(loan_operation_id='00000000-0000-4000-8000-000000000000'),
            lambda d: d['process_assertions'][7].update(loan_created_at='2026-10-09T20:47:34+00:00'),
            lambda d: d['process_assertions'][7].update(loan_confirmed_at='2026-10-09T20:47:35+00:00'),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self._reset_reports()
                self._native(mutate)
                with self.assertRaises(VERIFIER.FixtureRefusal):
                    VERIFIER._load_fallback_evidence(self.evidence_path, self.packages)

    def test_rejects_unpassed_or_unbound_packaged_process_assertions(self):
        mutations = (
            lambda d: d['process_assertions'][0].update(result='failed'),
            lambda d: d['process_assertions'][1].pop('bundle_manifest_sha256'),
            lambda d: d['process_assertions'][2].update(pid=0),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self._reset_reports()
                self._native(mutate)
                with self.assertRaises(VERIFIER.FixtureRefusal):
                    VERIFIER._load_fallback_evidence(self.evidence_path, self.packages)

    def test_rejects_missing_false_or_unbound_workflow_assertions(self):
        mutations = (
            lambda d: d.pop('workflow_assertions'),
            lambda d: d['workflow_assertions'].pop('shelf_observation_history_private_note_quantity'),
            lambda d: d['workflow_assertions'].update(uncertain_item_note_after_native_commit_exactly_once_recovery=False),
            lambda d: d['shelf_workflow']['trace'][1].update(bundle_manifest_sha256='0' * 64),
            lambda d: d['label_workflow'].update(physical_print_calls=1),
            lambda d: d['uncertain_note_workflow'].update(native_post_count=2),
            lambda d: d['uncertain_note_workflow'].pop('native_api_boundary'),
            lambda d: d['uncertain_note_workflow'].update(response_loss_injected_after_native_commit=False),
            lambda d: d['uncertain_note_workflow'].update(native_post_call_count=True),
            lambda d: d['uncertain_note_workflow'].update(native_endpoint='http://fixture.invalid/fake'),
            lambda d: d['publisher_checks'].update(receipt_validation='skipped'),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self._reset_reports()
                self._native(mutate)
                with self.assertRaises(VERIFIER.FixtureRefusal):
                    VERIFIER._load_fallback_evidence(self.evidence_path, self.packages)

    def test_rejects_label_and_note_workflow_mutations_inside_bound_report(self):
        mutations = (
            lambda d: d['label_workflow']['trace'][1].update(result='failed'),
            lambda d: d['label_workflow']['trace'][2].update(module_sha256={}),
            lambda d: d['label_workflow']['review_metadata'].update(template_hash='0' * 64),
            lambda d: d['label_workflow']['trace'][2].update(job_id='not-a-uuid'),
            lambda d: d['label_workflow']['trace'][1].update(physical_print_calls=True),
            lambda d: d['label_workflow']['trace'][2]['module_origins'].update(label_render='ops/native_jobs.py'),
            lambda d: d['uncertain_note_workflow']['trace'][1].update(native_post_count=True),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self._reset_reports()
                mutate(self.native)
                self._native(lambda report: None)
                with self.assertRaises(VERIFIER.FixtureRefusal):
                    VERIFIER._load_fallback_evidence(self.evidence_path, self.packages)


if __name__ == '__main__':
    unittest.main()
