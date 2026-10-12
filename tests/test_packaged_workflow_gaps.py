import importlib.util
import importlib
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'packaged_workflow_gaps', PROJECT / 'deploy/verify-packaged-workflow-gaps.py')
GAPS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GAPS
SPEC.loader.exec_module(GAPS)


class PackagedWorkflowGapTests(unittest.TestCase):
    def test_shelf_observation_history_private_note_quantity_and_lost_cancel_recover_across_ocfc(self):
        packages = PROJECT / 'work/queue-coordinator/whole-map-ocf-workflow-gap-live-note-20261010'
        with tempfile.TemporaryDirectory(prefix='packaged-shelf-proof-') as root:
            result = GAPS.run_shelf_lifecycle(packages, Path(root) / 'ledger.db')
        self.assertEqual([row['package'] for row in result['trace']], ['O', 'C', 'F', 'C'])
        self.assertTrue(result['same_ledger_store'])
        self.assertTrue(result['observation_history_private_note_quantity_preserved'])
        self.assertTrue(result['cancel_response_loss_request_key_recovered_once'])
        self.assertEqual(result['trusted_context_seam'], 'fixture-only manager B, canonical group and actor UUIDs')
        GAPS.validate_shelf_workflow(result, [row['bundle_manifest_sha256'] for row in result['trace']])
        broken = dict(result, cancel_response_loss_request_key_recovered_once=False)
        with self.assertRaisesRegex(ValueError, 'cancellation request recovery'):
            GAPS.validate_shelf_workflow(broken, [row['bundle_manifest_sha256'] for row in result['trace']])

    def test_packaged_label_raster_review_intent_and_cancel_survive_ocfc_without_print(self):
        packages = PROJECT / 'work/queue-coordinator/whole-map-ocf-workflow-gap-live-note-20261010'
        with tempfile.TemporaryDirectory(prefix='packaged-label-proof-') as root:
            result = GAPS.run_label_lifecycle(packages, Path(root) / 'ledger.db', Path(root) / 'reviews.db')
        self.assertEqual([row['package'] for row in result['trace']], ['O', 'C', 'F', 'C'])
        self.assertTrue(result['same_ledger_store'])
        self.assertTrue(result['reviewed_raster_intent_recovery_preserved'])
        self.assertEqual(result['physical_print_calls'], 0)
        self.assertEqual([row['job_status'] for row in result['trace']],
                         ['prepared', 'prepared', 'prepared', 'cancelled'])
        self.assertEqual([row['review_read_from_persisted_store'] for row in result['trace']],
                         [True, True, True, True])
        self.assertEqual([row['cancel_recovered_here'] for row in result['trace']],
                         [False, False, False, True])
        self.assertEqual(len({row['job_id'] for row in result['trace']}), 1)
        self.assertEqual(len({row['review_id'] for row in result['trace']}), 1)
        broken = dict(result, physical_print_calls=1)
        with self.assertRaisesRegex(ValueError, 'zero-output'):
            GAPS.validate_label_workflow(broken, [row['bundle_manifest_sha256'] for row in result['trace']])

    def test_label_validator_rejects_failed_rows_missing_modules_and_changed_bindings(self):
        packages = PROJECT / 'work/queue-coordinator/whole-map-ocf-workflow-gap-live-note-20261010'
        with tempfile.TemporaryDirectory(prefix='label-validator-proof-') as root:
            result = GAPS.run_label_lifecycle(packages, Path(root) / 'ledger.db', Path(root) / 'reviews.db')
        expected = [row['bundle_manifest_sha256'] for row in result['trace']]
        mutations = (
            lambda d: d['trace'][1].update(result='failed'),
            lambda d: d['trace'][2].update(module_sha256={}),
            lambda d: d['review_metadata'].update(template_hash='0' * 64),
            lambda d: d['trace'][2].update(job_id='not-a-uuid'),
            lambda d: d['trace'][2].update(physical_print_calls=True),
            lambda d: d['trace'][0].update(physical_print_calls=1),
            lambda d: d['trace'][1].update(module_origins={**d['trace'][1].get('module_origins', {}),
                                                           'label_render': 'ops/label_render.py.canonical'}),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                import copy
                changed = copy.deepcopy(result)
                mutate(changed)
                with self.assertRaises(ValueError):
                    GAPS.validate_label_workflow(changed, expected)

    def test_label_validator_binds_module_origins_and_bytes_to_selected_packages(self):
        packages = PROJECT / 'work/queue-coordinator/whole-map-ocf-workflow-gap-live-note-20261010'
        with tempfile.TemporaryDirectory(prefix='label-module-binding-') as root:
            result = GAPS.run_label_lifecycle(packages, Path(root) / 'ledger.db', Path(root) / 'reviews.db')
        expected = [row['bundle_manifest_sha256'] for row in result['trace']]
        GAPS.validate_label_workflow(result, expected, bundles=packages)
        import copy
        for mutation in (
            lambda d: d['trace'][1]['module_sha256'].update(label_render='0' * 64),
            lambda d: d['trace'][2]['module_origins'].update(label_render='ops/native_jobs.py'),
        ):
            changed = copy.deepcopy(result)
            mutation(changed)
            with self.assertRaises(ValueError):
                GAPS.validate_label_workflow(changed, expected, bundles=packages)

    def test_module_component_note_client_recovers_once_in_fixture_store(self):
        packages = PROJECT / 'work/queue-coordinator/whole-map-ocf-workflow-gap-live-note-20261010'
        with tempfile.TemporaryDirectory(prefix='packaged-note-proof-') as root:
            result = GAPS.run_uncertain_note_lifecycle(packages, Path(root) / 'ledger.db')
        self.assertEqual([row['package'] for row in result['trace']], ['O', 'C', 'F', 'C'])
        self.assertTrue(result['same_ledger_store'])
        self.assertTrue(result['uncertain_item_note_exactly_once_recovery_preserved'])
        self.assertEqual((result['native_entry_count'], result['native_post_count']), (1, 1))
        self.assertEqual([row['job_status'] for row in result['trace']][0], 'absent')
        self.assertIn(result['trace'][1]['job_status'], ('sent', 'review'))
        self.assertEqual([row['job_status'] for row in result['trace']][2:],
                         ['completed', 'completed'])
        self.assertEqual([row['recovery_performed_here'] for row in result['trace']],
                         [False, False, True, False])
        self.assertEqual(result['note_created_under'], 'C')
        self.assertEqual(result['final_candidate_state'], 'completed')
        self.assertEqual(result['native_post_call_count'], 1)

    def test_live_native_note_transition_uses_authenticated_api_and_recovers_only_on_f(self):
        packages = PROJECT / 'work/queue-coordinator/whole-map-ocf-workflow-gap-live-note-20261010'
        import uuid

        class ManagerBoundary:
            def __init__(self):
                self.native_port = 19091
                self.children = {'native': (type('Child', (), {'pid': 4567})(), None, None)}
                self.native_state = {'group_id': str(uuid.uuid4()), 'member_id': str(uuid.uuid4()),
                                     'entity_id': str(uuid.uuid4())}
                self.item = {'id': self.native_state['entity_id'], 'name': 'Fixture note item',
                             'archived': False, 'entityType': {'isLocation': False}}
                self.entries = []
                self.requests = []

            def _native_auth(self):
                return 'fixture-token'

            def _api_json(self, base, path, method='GET', payload=None, *, token=None, child=None, port=None):
                self.requests.append((base, path, method, token, child, port))
                if base != f'http://127.0.0.1:{self.native_port}' or token != 'fixture-token' or port != self.native_port:
                    raise AssertionError('native note did not use the authenticated fixture process boundary')
                if path == f"/api/v1/entities/{self.item['id']}" and method == 'GET':
                    return dict(self.item)
                if path != f"/api/v1/entities/{self.item['id']}/maintenance":
                    raise AssertionError(f'unexpected native note path: {path}')
                if method == 'GET':
                    return [dict(row) for row in self.entries]
                if method == 'POST':
                    row = {'id': str(uuid.uuid4()), **payload}
                    self.entries.append(row)
                    return {'item': row}
                raise AssertionError(f'unexpected native method: {method}')

        manager = ManagerBoundary()
        with tempfile.TemporaryDirectory(prefix='live-native-note-boundary-') as root:
            ledger = Path(root) / 'ledger.db'
            state = None
            rows = []
            for package_name in ('O', 'C', 'F', 'C'):
                state, row = GAPS.advance_live_uncertain_note(
                    manager, packages, package_name, ledger, state)
                rows.append(row)
            report = GAPS.finish_live_uncertain_note(manager, rows, state, bundles=packages)
        self.assertEqual([row['job_status'] for row in rows], ['absent', 'review', 'completed', 'completed'])
        self.assertEqual([row['native_post_count'] for row in rows], [0, 1, 1, 1])
        self.assertEqual([row['recovery_performed_here'] for row in rows], [False, False, True, False])
        self.assertEqual(len(manager.entries), 1)
        self.assertTrue(all(row[3] == 'fixture-token' and row[5] == manager.native_port
                            for row in manager.requests))

    def test_selected_package_loader_restores_preloaded_project_modules_and_path(self):
        canonical_ops = str(PROJECT / 'ops')
        original_path = list(sys.path)
        original_render = sys.modules.pop('label_render', None)
        sys.path.insert(0, canonical_ops)
        canonical_render = None
        try:
            canonical_render = importlib.import_module('label_render')
            before = list(sys.path)
            before_render = sys.modules['label_render']
            package = PROJECT / 'work/queue-coordinator/whole-map-ocf-workflow-gap-live-note-20261010/C'
            modules, state = GAPS._load_ops(package, ('label_layouts',))
            selected_render = sys.modules['label_render']
            self.assertNotEqual(Path(selected_render.__file__).resolve(),
                                Path(canonical_render.__file__).resolve())
            self.assertEqual(Path(selected_render.__file__).resolve(),
                             (package / 'ops/label_render.py').resolve())
            self.assertEqual(Path(modules['label_layouts'].__file__).resolve(),
                             (package / 'ops/label_layouts.py').resolve())
            GAPS._unload_ops(('label_layouts',), state)
            self.assertIs(sys.modules['label_render'], before_render)
            self.assertEqual(sys.path, before)
        finally:
            sys.path[:] = original_path
            sys.modules.pop('label_render', None)
            if original_render is not None:
                sys.modules['label_render'] = original_render

    def test_publisher_named_checks_run_through_pure_receipt_validation(self):
        packages = PROJECT / 'work/queue-coordinator/whole-map-ocf-workflow-gap-live-note-20261010'
        with tempfile.TemporaryDirectory(prefix='publisher-pure-receipt-') as root:
            result = GAPS.validate_publisher_checks(
                [packages / name for name in 'OCF'], Path(root), profile_loan_preserved=True)
        self.assertEqual(result['receipt_validation'], 'passed')
        self.assertTrue(result['legacy_bundle_rejected'])
        self.assertTrue(result['checks']['matched_previous_release_preserves_new_fixture_profiles_and_loans'])
        self.assertTrue(result['checks']['legacy_missing_member_api_is_not_a_rollback_target'])


if __name__ == '__main__':
    unittest.main()
