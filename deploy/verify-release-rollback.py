#!/usr/bin/env python3
"""Validate bundles inertly or run the packaged Oâ†’Câ†’Fâ†’C fixture process proof."""
import argparse
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
import shutil
import socket
import stat
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from urllib.parse import urlsplit, urlunsplit


PROJECT = Path(__file__).resolve().parents[1]
OPERATIONAL_ROOT = Path('/home/user/Desktop/inventory-system').resolve()


class FixtureRefusal(ValueError):
    pass


class ListenerOwnershipMismatch(FixtureRefusal):
    def __init__(self, pid, port, owners):
        self.pid, self.port, self.owners = pid, port, tuple(owners)
        super().__init__(f'listener at {port} is not owned by launched fixture process {pid}; '
                         f'observed listener owner pid(s) {list(self.owners)}')


def _reject_operational(path):
    raw = Path(path)
    if '..' in raw.parts:
        raise FixtureRefusal('bundle paths cannot use traversal or symlinks')
    # Inspect each existing component before resolve() can erase evidence of a
    # symlinked parent directory.
    current = raw.absolute()
    chain = list(reversed(current.parents)) + [current]
    for component in chain:
        try:
            if stat.S_ISLNK(component.lstat().st_mode):
                raise FixtureRefusal('bundle path contains a symlink')
        except FileNotFoundError:
            break
    resolved = raw.resolve(strict=True)
    if resolved.is_relative_to(OPERATIONAL_ROOT):
        raise FixtureRefusal('operational project paths are not accepted by fixture verifier')
    try:
        resolved.relative_to(Path(tempfile.gettempdir()).resolve())
    except ValueError as exc:
        raise FixtureRefusal('fixture bundles must be in a temporary directory') from exc
    if not resolved.is_dir() or resolved.stat().st_uid != os.getuid():
        raise FixtureRefusal('fixture bundle must be an owned directory')
    return resolved


def _manifest_hash(path):
    return hashlib.sha256((path / 'manifest.json').read_bytes()).hexdigest()


def _artifact_binding(path):
    manifest = json.loads((Path(path) / 'manifest.json').read_text())
    policy = manifest.get('fallback_policy')
    return {
        'bundle_manifest_sha256': _manifest_hash(path),
        'native_sha256': manifest.get('provenance', {}).get('native_sha256'),
        'fallback_policy_sha256': (hashlib.sha256(json.dumps(
            policy, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            if policy is not None else None),
    }


def _require_receipt_bindings(manifest):
    provenance = manifest.get('provenance', {})
    for label in ('build', 'test'):
        value = provenance.get(f'{label}_receipt')
        raw_sha = provenance.get(f'{label}_receipt_sha256')
        canonical_sha = provenance.get(f'{label}_receipt_canonical_sha256')
        path = provenance.get(f'{label}_receipt_path')
        canonical = hashlib.sha256(json.dumps(
            value, sort_keys=True, separators=(',', ':')).encode()).hexdigest() if isinstance(value, dict) else None
        if (not isinstance(raw_sha, str) or len(raw_sha) != 64
                or not isinstance(path, str) or not path
                or not isinstance(canonical_sha, str) or canonical != canonical_sha):
            raise FixtureRefusal(f'{label} receipt content is not bound to the package manifest')


def _owned_dependency(path):
    raw = Path(path)
    if '..' in raw.parts:
        raise FixtureRefusal('dependency path cannot use traversal')
    absolute = raw.absolute()
    for component in list(reversed(absolute.parents)) + [absolute]:
        try:
            if stat.S_ISLNK(component.lstat().st_mode):
                raise FixtureRefusal('dependency path cannot contain symlinks')
        except FileNotFoundError:
            break
    resolved = raw.resolve(strict=True)
    if not resolved.is_dir() or resolved.stat().st_uid != os.getuid():
        raise FixtureRefusal('dependency path must be an existing owned directory')
    return resolved


def _owned_fixture_evidence(path):
    raw = Path(path)
    if '..' in raw.parts:
        raise FixtureRefusal('fallback evidence path cannot use traversal')
    absolute = raw.absolute()
    for component in list(reversed(absolute.parents)) + [absolute]:
        try:
            if stat.S_ISLNK(component.lstat().st_mode):
                raise FixtureRefusal('fallback evidence path cannot contain symlinks')
        except FileNotFoundError:
            break
    resolved = raw.resolve(strict=True)
    evidence_root = (PROJECT / 'work/queue-coordinator').resolve(strict=True)
    if (not resolved.is_relative_to(evidence_root) or not resolved.is_file()
            or resolved.stat().st_uid != os.getuid()):
        raise FixtureRefusal('fallback evidence must be an owned file in the fixture work area')
    return resolved


def _load_fallback_evidence(path, packages):
    """Validate executed fixture reports and bind all four checks to exact O/C/F bytes."""
    evidence_path = _owned_fixture_evidence(path)
    try:
        evidence = json.loads(evidence_path.read_text())
    except (OSError, UnicodeError, ValueError) as exc:
        raise FixtureRefusal('fallback evidence is not valid JSON') from exc
    if not isinstance(evidence, dict) or evidence.get('schema') != 1 or evidence.get('execution_scope') != 'fixture-only':
        raise FixtureRefusal('fallback evidence schema or scope is invalid')
    expected = {name: _artifact_binding(package) for name, package in zip(('O', 'C', 'F'), packages)}
    source_bindings = evidence.get('package_bindings')
    expected_evidence = {name: {'manifest_sha256': value['bundle_manifest_sha256'],
                                'native_sha256': value['native_sha256'],
                                'fallback_policy_sha256': value['fallback_policy_sha256']}
                         for name, value in expected.items()}
    return_to_candidate = (expected['O']['bundle_manifest_sha256'] ==
                           expected['F']['bundle_manifest_sha256'])
    if return_to_candidate:
        source_matches = (isinstance(source_bindings, dict)
                          and source_bindings.get('C') == expected_evidence['C']
                          and source_bindings.get('F') == expected_evidence['F'])
    else:
        source_matches = source_bindings == expected_evidence
    if not source_matches:
        raise FixtureRefusal('fallback evidence does not bind the exact O/C/F manifests, native bytes and policy')
    if not isinstance(source_bindings, dict) or set(source_bindings) != {'O', 'C', 'F'}:
        raise FixtureRefusal('fallback evidence package bindings must name O, C and F exactly')
    checks = evidence.get('checks')
    from release_bundle import FALLBACK_CHECKS
    if not isinstance(checks, dict) or set(checks) != set(FALLBACK_CHECKS) or any(
            checks.get(name) != 'passed' for name in FALLBACK_CHECKS):
        raise FixtureRefusal('external artifact-bound fallback evidence has missing or unpassed named checks')
    sources = evidence.get('assertion_sources')
    if not isinstance(sources, dict) or set(sources) != {'rooms', 'native_process'}:
        raise FixtureRefusal('fallback evidence does not identify both executed assertion reports')
    root = (PROJECT / 'work/queue-coordinator').resolve(strict=True)
    loaded = {}
    for label, source in sources.items():
        if not isinstance(source, dict):
            raise FixtureRefusal(f'{label} assertion source schema is invalid')
        relative = source.get('path')
        if not isinstance(relative, str) or Path(relative).is_absolute() or '..' in Path(relative).parts:
            raise FixtureRefusal(f'{label} assertion source path is invalid')
        report_path = _owned_fixture_evidence(root / relative)
        raw = report_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != source.get('sha256'):
            raise FixtureRefusal(f'{label} assertion report bytes changed after evidence binding')
        try:
            loaded[label] = json.loads(raw)
        except (UnicodeError, ValueError) as exc:
            raise FixtureRefusal(f'{label} assertion report is invalid JSON') from exc
    rooms, native = loaded['rooms'], loaded['native_process']
    if not isinstance(rooms, dict) or not isinstance(native, dict):
        raise FixtureRefusal('Rooms and native assertion reports must be JSON objects')
    if rooms.get('execution_scope') != 'fixture-only' or rooms.get('package_bindings') != source_bindings:
        raise FixtureRefusal('Rooms assertions do not bind the exact fixture packages')
    room_names = {'fallback_candidate_compatible_handlers',
                  'fallback_reads_rooms_v1_v2_writes_v2_or_disables_mutation',
                  'same_runtime_stores_no_restore_or_physical_replay'}
    room_checks = rooms.get('checks')
    if not isinstance(room_checks, dict) or set(room_checks) != room_names or any(
            room_checks.get(name) != 'passed' for name in room_names):
        raise FixtureRefusal('Rooms assertion report is missing an executed named check')
    assertions = rooms.get('assertions')
    if not isinstance(assertions, dict):
        raise FixtureRefusal('Rooms assertion report has no assertion object')
    if (assertions.get('O_read_v1') is not True or assertions.get('O_read_v2') is not True
            or assertions.get('O_write_rejected') is not True
            or assertions.get('C_write_v2_and_receipt') is not True
            or assertions.get('F_reopened_and_write_v2') is not True
            or assertions.get('C_reopened_F_write_and_receipt') is not True
            or assertions.get('same_rooms_database_inode_across_O_C_F_C') is not True):
        raise FixtureRefusal('Rooms assertion report lacks same-store v1/v2 read/write evidence')
    room_audit = rooms.get('audit')
    if not isinstance(room_audit, dict):
        raise FixtureRefusal('Rooms assertion report has no audit object')
    if any(type(room_audit.get(name)) is not int or room_audit.get(name) != 0 for name in
           ('replay_calls', 'database_copy_calls', 'physical_import_attempts')):
        raise FixtureRefusal('Rooms assertion report observed replay, store copy or physical import')
    def valid_identity(value):
        return (isinstance(value, (list, tuple)) and len(value) == 2
                and all(type(item) is int and item > 0 for item in value))

    room_identity = rooms.get('rooms_store_identity_trace')
    if (not isinstance(room_identity, list) or len(room_identity) != 4
            or any(not isinstance(row, dict)
                   or type(row.get('device')) is not int or row['device'] <= 0
                   or type(row.get('inode')) is not int or row['inode'] <= 0
                   for row in room_identity)
            or len({(row['device'], row['inode']) for row in room_identity}) != 1):
        raise FixtureRefusal('Rooms assertion report did not provide four positive, identical device/inode identities')
    rooms_identity_summary = rooms.get('rooms_store_identity')
    if (not isinstance(rooms_identity_summary, dict)
            or type(rooms_identity_summary.get('device')) is not int
            or type(rooms_identity_summary.get('inode')) is not int
            or rooms_identity_summary.get('device') != room_identity[0]['device']
            or rooms_identity_summary.get('inode') != room_identity[0]['inode']):
        raise FixtureRefusal('Rooms identity summary does not match the four observed store identities')
    native_expected = {name: {'bundle_manifest_sha256': value['manifest_sha256'],
                              'native_sha256': value['native_sha256'],
                              'fallback_policy_sha256': value['fallback_policy_sha256']}
                       for name, value in source_bindings.items()}
    if native.get('scope') != 'fixture-only' or native.get('artifact_bindings') != native_expected:
        raise FixtureRefusal('native process assertions do not bind the exact fixture packages')
    workflow_assertion_names = {
        'shelf_observation_history_private_note_quantity',
        'shelf_draft_cancel_response_loss_request_key_recovery',
        'reviewed_label_raster_intent_recovery_zero_print_calls',
        'uncertain_item_note_after_native_commit_exactly_once_recovery',
        'matched_previous_release_preserves_new_fixture_profiles_and_loans',
        'legacy_missing_member_api_is_not_a_rollback_target',
    }
    workflow_assertions = native.get('workflow_assertions')
    if (not isinstance(workflow_assertions, dict)
            or set(workflow_assertions) != workflow_assertion_names
            or any(workflow_assertions.get(name) is not True for name in workflow_assertion_names)):
        raise FixtureRefusal('native workflow report lacks all six required passed assertions')
    trace = native.get('trace')
    expected_transitions = ['O', 'C', 'F', 'C']
    if (not isinstance(trace, list) or len(trace) != len(expected_transitions)
            or [row.get('selected_fixture_package') if isinstance(row, dict) else None
                for row in trace] != expected_transitions):
        raise FixtureRefusal('native process assertions lack packaged O/C/F/C transitions')
    if any(row.get('bundle_binding') != native_expected[row['selected_fixture_package']] for row in trace):
        raise FixtureRefusal('native process transition binding differs from final package hashes')
    if (native.get('same_native_and_ledger_store_identity') is not True
            or native.get('member_avatar_private_note_badge_and_loan_dates_history_preserved') is not True
            or type(native.get('restore_replay_calls')) is not int or native.get('restore_replay_calls') != 0
            or type(native.get('physical_output_count')) is not int or native.get('physical_output_count') != 0
            or native.get('runtime_store_removed') is not True):
        raise FixtureRefusal('native member/loan/store/no-replay assertion failed')

    def valid_timestamp(value):
        if not isinstance(value, str) or not value:
            return False
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return False
        return parsed.tzinfo is not None and parsed.utcoffset() is not None

    native_ids = [row.get('native_store_identity') for row in trace]
    ledger_ids = [row.get('ledger_store_identity') for row in trace]
    profiles = [row.get('member_profile_sha256') for row in trace]
    loan_ids = [row.get('loan_operation_id') for row in trace]
    created = [row.get('loan_created_at') for row in trace]
    confirmed = [row.get('loan_confirmed_at') for row in trace]
    if (not all(valid_identity(value) for value in native_ids + ledger_ids)
   5ÛNô¶‰žËkºwµç}•Ù¥‘•¹”¡•Ù¥‘•¹•}Á…Ñ °€¡ÁÉ•Ù¥½ÕÌ°…¹‘¥‘…Ñ”°™…±±‰…¬¤¤(€€€•±Í”è(€€€€€€€É…Ý}¡•­Ì€ô™…±±‰…­}µ…¹¥™•ÍÑlÁÉ½Ù•¹…¹”t¹•Ð Ñ•ÍÑ}É••¥ÁÐœ°íô¤¹•Ð ™…±±‰…­}¡•­Ìœ¤(€€€€€€€¥˜¹½Ð¥Í¥¹ÍÑ…¹”¡É…Ý}¡•­Ì°‘¥Ð¤½ÈÍ•Ð¡É…Ý}¡•­Ì¤€„ôÍ•Ð¡11	-}!-L¤½È…¹ä (€€€€€€€€€€€€€€€É…Ý}¡•­Ì¹•Ð¡¹…µ”¤€„ô€Á…ÍÍ•œ™½È¹…µ”¥¸11	-}!-L¤è(€€€€€€€€€€€µ¥ÍÍ¥¹œ€ôÍ½ÉÑ•¡¹…µ”™½È¹…µ”¥¸11	-}!-L(€€€€€€€€€€€€€€€€€€€€€€€€€€€€¥˜¹½Ð¥Í¥¹ÍÑ…¹”¡É…Ý}¡•­Ì°‘¥Ð¤½ÈÉ…Ý}¡•­Ì¹•Ð¡¹…µ”¤€„ô€Á…ÍÍ•œ¤(€€€€€€€€€€€É…¥Í”¥áÑÕÉ•I•™ÕÍ…° …ÉÑ¥™…Ðµ‰½Õ¹¹…µ•™…±±‰…¬¡•­Ì…É”µ¥ÍÍ¥¹œ½ÈÕ¹Á…ÍÍ•è€œ€¬€œ°€œ¹©½¥¸¡µ¥ÍÍ¥¹œ¤¤(€€€¥˜€¡Á½±¥ä¹•Ð •Ù¥‘•¹•}Í½Á”œ¤€„ô€™¥áÑÕÉ”µ½¹±äœ(€€€€€€€€€€€½ÈÁ½±¥ä¹•Ð ÉÕ¹Ñ¥µ•}ÍÑ…Ñ•}Á½±¥äœ¤€„ô€Í…µ”µÍÑ½É•Ìµ¹¼µÉ•ÍÑ½É”œ(€€€€€€€€€€€½ÈÁ½±¥ä¹•Ð Á¡åÍ¥…±}•™™•Ñ}Á½±¥äœ¤€„ô€¹•Ù•ÈµÉ•Á±…äœ(€€€€€€€€€€€½ÈÁ½±¥ä¹•Ð É½½µÍØÉ}É•…‘}Ù•ÉÍ¥½¹Ìœ¤€„ô…Á…‰¥±¥Ñä¹•Ð É•…‘}Ù•ÉÍ¥½¹Ìœ¤(€€€€€€€€€€€½ÈÁ½±¥ä¹•Ð Ý½É­Í¡½Á}µÕÑ…Ñ¥½¹}µ½‘”œ¤€„ô…Á…‰¥±¥Ñä¹•Ð ÝÉ¥Ñ•}µ½‘”œ¤(€€€€€€€€€€€½ÈÁ½±¥ä¹•Ð …¹‘¥‘…Ñ•}µ…¹¥™•ÍÑ}Í¡„ÈÔØœ¤€„ô}µ…¹¥™•ÍÑ}¡…Í ¡…¹‘¥‘…Ñ”¤(€€€€€€€€€€€½ÈÁ½±¥ä¹•Ð µ•µ‰•É}ÁÉ½™¥±•}±½…¹}½µÁ…Ñ¥‰¥±¥Ñäœ¤€„ô€Ù•É¥™¥•œ¤è(€€€€€€€É…¥Í”¥áÑÕÉ•I•™ÕÍ…° ™¥áÑÕÉ”™…±±‰…¬Á½±¥ä‘½•Ì¹½Ðµ…Ñ ¥ÑÌ…ÉÑ¥™…Ðµ‰½Õ¹…Á…‰¥±¥Ñäœ¤(€€€¥˜…¹‘¥‘…Ñ•}µ…¹¥™•ÍÑlÁÉ½Ù•¹…¹”ulÝ½É­Í¡½Á}…Á…‰¥±¥ÑäulÝÉ¥Ñ•}µ½‘”t€„ô€ØÈœè(€€€€€€€É…¥Í”¥áÑÕÉ•I•™ÕÍ…° …¹‘¥‘…Ñ”Á…­…”µÕÍÐ¡…Ù”„Ù•ÉÍ¥½¸´È]½É­Í¡½ÀÝÉ¥Ñ•Èœ¤(€€€€ŒÍÑ…•}‰Õ¹‘±”¡•­•É…ÜÉ••¥ÁÐ‰åÑ•Ì‰•™½É”Á…­…¥¹œìÙ…±¥‘…Ñ•}‰Õ¹‘±”(€€€€ŒÉ•¡•­ÌÑ¡”•µ‰•‘‘•…¹½¹¥…°½‰©•Ð¡…Í ¸=¹±äÑ¡•Í”‰½Õ¹Á…ÍÍ•‘€(€€€€ŒÉ•ÍÕ±ÑÌµ…ä¹½Ü‰”ÑÉ…¹Í±…Ñ•™½ÈÍ•±•Ñ}‰Õ¹‘±”Ì‰½½±•…¸Í¡•µ„¸(€€€É••¥ÁÐ€ôì(€€€€€€€€•á•ÕÑ¥½¹}Í½Á”œè€™¥áÑÕÉ”µ½¹±äœ°(€€€€€€€€ÁÉ•Ù¥½ÕÍ}‰Õ¹‘±•}µ…¹¥™•ÍÑ}Í¡„ÈÔØœè}µ…¹¥™•ÍÑ}¡…Í ¡ÁÉ•Ù¥½ÕÌ¤°(€€€€€€€€ÁÉ•Ù¥½ÕÍ}¹…Ñ¥Ù•}Í¡„ÈÔØœèÁÉ•Ù¥½ÕÍ}µ…¹¥™•ÍÑlÁÉ½Ù•¹…¹”ul¹…Ñ¥Ù•}Í¡„ÈÔØt°(€€€€€€€€…¹‘¥‘…Ñ•}‰Õ¹‘±•}µ…¹¥™•ÍÑ}Í¡„ÈÔØœè}µ…¹¥™•ÍÑ}¡…Í ¡…¹‘¥‘…Ñ”¤°(€€€€€€€€…¹‘¥‘…Ñ•}¹…Ñ¥Ù•}Í¡„ÈÔØœè…¹‘¥‘…Ñ•}µ…¹¥™•ÍÑlÁÉ½Ù•¹…¹”ul¹…Ñ¥Ù•}Í¡„ÈÔØt°(€€€€€€€€™…±±‰…­}‰Õ¹‘±•}µ…¹¥™•ÍÑ}Í¡„ÈÔØœè}µ…¹¥™•ÍÑ}¡…Í ¡™…±±‰…¬¤°(€€€€€€€€™…±±‰…­}¹…Ñ¥Ù•}Í¡„ÈÔØœè™…±±‰…­}µ…¹¥™•ÍÑlÁÉ½Ù•¹…¹”ul¹…Ñ¥Ù•}Í¡„ÈÔØt°(€€€€€€€€™…±±‰…­}Á½±¥å}Í¡„ÈÔØœè¡…Í¡±¥ˆ¹Í¡„ÈÔØ¡©Í½¸¹‘ÕµÁÌ¡Á½±¥ä°Í½ÉÑ}­•åÌõQÉÕ”°(€€€€€€€€€€€Í•Á…É…Ñ½ÉÌô œ°œ°€œèœ¤¤¹•¹½‘” ¤¤¹¡•á‘¥•ÍÐ ¤°(€€€€€€€€¡•­Ìœèí¹…µ”èÉ…Ý}¡•­Ím¹…µ•t€ôô€Á…ÍÍ•œ™½È¹…µ”¥¸11	-}!-Mô°(€€€ô(€€€ÑÉäè(€€€€€€€Ù…±¥‘…Ñ•}É••¥ÁÐ¡É••¥ÁÐ°ÁÉ•Ù¥½ÕÌ°…¹‘¥‘…Ñ”°™…±±‰…¬¤(€€€•á•ÁÐ	Õ¹‘±•ÉÉ½È…Ì•áŒè(€€€€€€€É…¥Í”¥áÑÕÉ•I•™ÕÍ…°¡˜™¥áÑÕÉ”™…±±‰…¬É••¥ÁÐÁÉ•™±¥¡Ð™…¥±•èí•áôœ¤™É½´•áŒ(€€€É•ÑÕÉ¸É••¥ÁÐ(()‘•˜}ÁÉ•™±¥¡Ñ}™¥áÑÕÉ•}Á…­…•Ì¡Á…Ñ¡Ì°…Á¤°•Ù¥‘•¹•}Á…Ñ õ9½¹”¤è(€€€|°	Õ¹‘±•ÉÉ½È°|°|°Ù…±¥‘…Ñ•}‰Õ¹‘±”°É•ÅÕ¥É•}…Á…‰¥±¥Ñä°|°|€ô…Á¤(€€€¥˜±•¸¡Á…Ñ¡Ì¤€„ô€Ì½È±•¸¡Í•Ð¡µ…À¡A…Ñ °Á…Ñ¡Ì¤¤¤€„ô€Ìè(€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È ™¥áÑÕÉ”µÁÉ½•ÍÌÉ•ÅÕ¥É•Ì‘¥ÍÑ¥¹Ð<½½Á…­…•Ìœ¤(€€€µ…¹¥™•ÍÑÌ€ômt(€€€™½ÈÁ…Ñ ¥¸Á…Ñ¡Ìè(€€€€€€€µ…¹¥™•ÍÐ€ôÙ…±¥‘…Ñ•}‰Õ¹‘±”¡Á…Ñ ¤(€€€€€€€}É•ÅÕ¥É•}É••¥ÁÑ}‰¥¹‘¥¹Ì¡µ…¹¥™•ÍÐ¤(€€€€€€€ÁÉ½Ù•¹…¹”€ôµ…¹¥™•ÍÐ¹•Ð ÁÉ½Ù•¹…¹”œ°íô¤(€€€€€€€¥˜€¡µ…¹¥™•ÍÐ¹•Ð ™½Éµ…Ðœ¤€„ô€È(€€€€€€€€€€€€€€€½ÈÁÉ½Ù•¹…¹”¹•Ð ‰Õ¥±‘}É••¥ÁÐœ°íô¤¹•Ð •á•ÕÑ¥½¹}Í½Á”œ¤€„ô€™¥áÑÕÉ”µ½¹±äœ(€€€€€€€€€€€€€€€½ÈÁÉ½Ù•¹…¹”¹•Ð Ñ•ÍÑ}É••¥ÁÐœ°íô¤¹•Ð •á•ÕÑ¥½¹}Í½Á”œ¤€„ô€™¥áÑÕÉ”µ½¹±äœ¤è(€€€€€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È ™¥áÑÕÉ”µÁÉ½•ÍÌÉ•ÅÕ¥É•Ì½µÁ±•Ñ”™¥áÑÕÉ”µ½¹±ä™½Éµ…Ð´È<½½Á…­…•Ìœ¤(€€€€€€€µ…¹¥™•ÍÑÌ¹…ÁÁ•¹¡µ…¹¥™•ÍÐ¤(€€€½}…Á…‰¥±¥Ñä€ôÉ•ÅÕ¥É•}…Á…‰¥±¥Ñä¡µ…¹¥™•ÍÑÍlÁt°É½±”ôÁÉ•Ù¥½ÕÌœ¤(€€€}…Á…‰¥±¥Ñä€ôÉ•ÅÕ¥É•}…Á…‰¥±¥Ñä¡µ…¹¥™•ÍÑÍlÅt°É½±”ô…¹‘¥‘…Ñ”œ°É•ÅÕ¥É•}ÝÉ¥Ñ•ÈõQÉÕ”¤(€€€™}…Á…‰¥±¥Ñä€ôÉ•ÅÕ¥É•}…Á…‰¥±¥Ñä¡µ…¹¥™•ÍÑÍlÉt°É½±”ô™…±±‰…¬œ¤(€€€¥˜€¡½}…Á…‰¥±¥ÑålÝÉ¥Ñ•}µ½‘”t€„ô€‘¥Í…‰±•œ(€€€€€€€€€€€½È}…Á…‰¥±¥ÑålÝÉ¥Ñ•}µ½‘”t€„ô€ØÈœ(€€€€€€€€€€€½È™}…Á…‰¥±¥ÑålÝÉ¥Ñ•}µ½‘”t¹½Ð¥¸€ ØÈœ°€‘¥Í…‰±•œ¤¤è(€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È ™¥áÑÕÉ”<½½]½É­Í¡½À…Á…‰¥±¥Ñ¥•Ì‘¼¹½ÐÍ…Ñ¥Í™ä‘¥Í…‰±•µ<°ØÈµ°½µÁ…Ñ¥‰±”µÁ½±¥äœ¤(€€€™¥ÉÍÑ}É••¥ÁÐ€ô}™¥áÑÕÉ•}É••¥ÁÐ¡Á…Ñ¡ÍlÁt°Á…Ñ¡ÍlÅt°Á…Ñ¡ÍlÉt°…Á¤°•Ù¥‘•¹•}Á…Ñ ¤(€€€€ŒµÑ¼µÉ•ÑÕÉ¸ÕÍ•ÌÑ¡”Í…µ”‰åÑ”µ¥‘•¹Ñ¥…°…ÉÑ¥™…Ð…¹Ñ¡”Í…µ”(€€€€Œ…¹‘¥‘…Ñ”µ‰½Õ¹Á½±¥ä°Ý¥Ñ …ÌÑ¡”Í•±•Ñ•ÁÉ•Ù¥½ÕÌÁ…­…”¸(€€€É•ÑÕÉ¹}É••¥ÁÐ€ô}™¥áÑÕÉ•}É••¥ÁÐ¡Á…Ñ¡ÍlÉt°Á…Ñ¡ÍlÅt°Á…Ñ¡ÍlÉt°…Á¤°•Ù¥‘•¹•}Á…Ñ ¤(€€€É•ÑÕÉ¸µ…¹¥™•ÍÑÌ°™¥ÉÍÑ}É••¥ÁÐ°É•ÑÕÉ¹}É••¥ÁÐ(()‘•˜}ÉÕ¹}™¥áÑÕÉ•}ÁÉ½•ÍÌ¡…ÉÌ°Á…Ñ¡Ì°‘•Á•¹‘•¹ä°…Á¤¤è(€€€|°	Õ¹‘±•ÉÉ½È°|°|°Ù…±¥‘…Ñ•}‰Õ¹‘±”€ô…Á¥lèÕt(€€€¥˜…ÉÌ¹¥¹©•Ñ}…¹‘¥‘…Ñ•}¥¹Ñ•ÉÉÕÁÑ¥½¸½È…ÉÌ¹¥¹©•Ñ}…¹‘¥‘…Ñ•}Ù•É¥™¥…Ñ¥½¹}™…¥±ÕÉ”è(€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È ™¥áÑÕÉ”µÁÉ½•ÍÌµ½‘”ÕÍ•Ì¥ÑÌ½Ý¸Í…µ”µÍÑ½É”…¹‘¥‘…Ñ”™…¥±ÕÉ”Í•¹…É¥¼œ¤(€€€µ…¹¥™•ÍÑÌ°™…±±‰…­}É••¥ÁÐ°É•ÑÕÉ¹}™…±±‰…­}É••¥ÁÐ€ô}ÁÉ•™±¥¡Ñ}™¥áÑÕÉ•}Á…­…•Ì (€€€€€€€Á…Ñ¡Ì°…Á¤°•Ñ…ÑÑÈ¡…ÉÌ°€™…±±‰…­}•Ù¥‘•¹”œ°9½¹”¤¤(€€€¥˜¹½Ð‘•Á•¹‘•¹ä¹¥Í}‘¥È ¤½È‘•Á•¹‘•¹ä¹¥Í}Íåµ±¥¹¬ ¤è(€€€€€€€É…¥Í”¥áÑÕÉ•I•™ÕÍ…° ‘•Á•¹‘•¹äÁ…Ñ µÕÍÐ‰”…¸•á¥ÍÑ¥¹œÉ•½É‘•¹½¸µÍåµ±¥¹¬‘¥É•Ñ½Éäœ¤((€€€€Œ%µÁ½ÉÐÑ¡”ÁÉ½•ÍÌÉÕ¹¹•È½¹±ä…™Ñ•È•Ù•ÉäÁ…­…”°…Á…‰¥±¥Ñä°Á½±¥ä…¹(€€€€ŒÉ…ÜÉ••¥ÁÐ‰¥¹‘¥¹œ¡…ÌÁ…ÍÍ•¸9¼ÉÕ¸½ÍÑ½É”É½½Ð•á¥ÍÑÌ…ÐÑ¡¥ÌÁ½¥¹Ð¸(€€€¥µÁ½ÉÐÉÕ¹Áä(€€€É½½µ}Ù•É¥™¥•È€ôÉÕ¹Áä¹ÉÕ¹}Á…Ñ ¡ÍÑÈ¡AI=)P€¼€‘•Á±½ä½Ù•É¥™äµÝ½É­Í¡½ÀµÉ½½µÌ¹Áäœ¤°(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€ÉÕ¹}¹…µ”ô™¥áÑÕÉ•}ÁÉ½•ÍÍ}É½½µÌœ¤((€€€ÉÕ¹}¥€ôÕÕ¥¹ÕÕ¥Ð ¤¹¡•à(€€€É•Ñ…¥¹•€ôAI=)P€¼€Ý½É¬½ÅÕ•Õ”µ½½É‘¥¹…Ñ½Èœ€¼˜Ý¡½±”µµ…ÀµÁÉ½•ÍÌµÉÕ¸µíÉÕ¹}¥‘ôœ(€€€É•Ñ…¥¹•¹µ­‘¥È¡µ½‘”ôÁ¼ÜÀÀ°Á…É•¹ÑÌõQÉÕ”¤(€€€±½Ì€ôÉ•Ñ…¥¹•€¼€±½Ìœ(€€€±½Ì¹µ­‘¥È¡µ½‘”ôÁ¼ÜÀÀ¤(€€€Ñ½­•¸€ôÕÕ¥¹ÕÕ¥Ð ¤¹¡•à€¬ÕÕ¥¹ÕÕ¥Ð ¤¹¡•à(€€€É•Á½ÉÑ}Á…Ñ €ôÉ•Ñ…¥¹•€¼€É••¥ÁÐ¹©Í½¸œ(€€€ÁÉ½•ÍÍ}µ…¹…•È€ô9½¹”(€€€É•ÍÕ±Ð€ô9½¹”(€€€™…¥±ÕÉ”€ô9½¹”(€€€Ñ•µÁ}É½½Ð€ô9½¹”(€€€±•…¹ÕÁ}•ÉÉ½ÉÌ€ômt(€€€ÑÉäè(€€€€€€€Ñ•µÁ}É½½Ð€ôA…Ñ ¡Ñ•µÁ™¥±”¹µ­‘Ñ•µÀ¡ÁÉ•™¥àôÝ¡½±”µµ…Àµ™¥áÑÕÉ”µÁÉ½•ÍÌ´œ¤¤(€€€€€€€½Ì¹¡µ½¡Ñ•µÁ}É½½Ð°€Á¼ÜÀÀ¤(€€€€€€€É•±•…Í•Ì€ôÑ•µÁ}É½½Ð€¼€É•±•…Í•Ìœ(€€€€€€€É•±•…Í•Ì¹µ­‘¥È¡µ½‘”ôÁ¼ÜÀÀ¤(€€€€€€€½Á¥•€ômt(€€€€€€€™½È¹…µ”°Á…Ñ ¥¸é¥À  <œ°€œ°€œ¤°Á…Ñ¡Ì¤è(€€€€€€€€€€€‘•ÍÑ¥¹…Ñ¥½¸€ôÉ•±•…Í•Ì€¼¹…µ”(€€€€€€€€€€€Í¡ÕÑ¥°¹½ÁåÑÉ•”¡Á…Ñ °‘•ÍÑ¥¹…Ñ¥½¸°Íåµ±¥¹­Ìõ…±Í”¤(€€€€€€€€€€€½Á¥•¹…ÁÁ•¹¡‘•ÍÑ¥¹…Ñ¥½¸¹É•Í½±Ù”¡ÍÑÉ¥ÐõQÉÕ”¤¤(€€€€€€€ÁÉ•Ù¥½ÕÌ°…¹‘¥‘…Ñ”°™…±±‰…¬€ô½Á¥•(€€€€€€€É•ÑÕÉ¹}™…±±‰…¬€ôÉ•±•…Í•Ì€¼€µÉ•ÑÕÉ¸œ(€€€€€€€Í¡ÕÑ¥°¹½ÁåÑÉ•”¡™…±±‰…¬°É•ÑÕÉ¹}™…±±‰…¬°Íåµ±¥¹­Ìõ…±Í”¤(€€€€€€€É•ÑÕÉ¹}™…±±‰…¬€ôÉ•ÑÕÉ¹}™…±±‰…¬¹É•Í½±Ù”¡ÍÑÉ¥ÐõQÉÕ”¤(€€€€€€€™½ÈÁ…­…”¥¸€ ©½Á¥•°É•ÑÕÉ¹}™…±±‰…¬¤è(€€€€€€€€€€€¥˜Ù…±¥‘…Ñ•}‰Õ¹‘±”¡Á…­…”¤¹•Ð ™½Éµ…Ðœ¤€„ô€Èè(€€€€€€€€€€€€€€€É…¥Í”¥áÑÕÉ•I•™ÕÍ…° ½Á¥•™¥áÑÕÉ”Á…­…”¡…¹•‘ÕÉ¥¹œÍÑ…¥¹œœ¤((€€€€€€€ÉÕ¹Ñ¥µ”€ôÑ•µÁ}É½½Ð€¼€ÉÕ¹Ñ¥µ”œ(€€€€€€€ÉÕ¹Ñ¥µ”¹µ­‘¥È¡µ½‘”ôÁ¼ÜÀÀ¤(€€€€€€€€¡ÉÕ¹Ñ¥µ”€¼€œ¹™¥áÑÕÉ”µÁÉ½•ÍÌµÑ½­•¸œ¤¹ÝÉ¥Ñ•}Ñ•áÐ¡Ñ½­•¸¤(€€€€€€€€¡ÉÕ¹Ñ¥µ”€¼€œ¹™¥áÑÕÉ”µÁÉ½•ÍÌµÑ½­•¸œ¤¹¡µ½ Á¼ØÀÀ¤(€€€€€€€Ý½É¬€ôÉÕ¹Ñ¥µ”€¼€Ý½É¬œ(€€€€€€€Ý½É¬¹µ­‘¥È¡µ½‘”ôÁ¼ÜÀÀ¤(€€€€€€€€¡Ý½É¬€¼€…ÁÁ±¥…Ñ¥½¸µÕÉÉ•¹Ðœ¤¹Íåµ±¥¹­}Ñ¼¡ÁÉ•Ù¥½ÕÌ°Ñ…É•Ñ}¥Í}‘¥É•Ñ½ÉäõQÉÕ”¤(€€€€€€€½Ý¹•É}ÍÑ…Ð€ôÑ•µÁ}É½½Ð¹ÍÑ…Ð ¤(€€€€€€€™¥áÑÕÉ”€ôì(€€€€€€€€€€€€½Ý¹•‘}É½½ÐœèÍÑÈ¡Ñ•µÁ}É½½Ð¤°€½Ý¹•É}¥‘•¹Ñ¥Ñäœè€¡½Ý¹•É}ÍÑ…Ð¹ÍÑ}‘•Ø°½Ý¹•É}ÍÑ…Ð¹ÍÑ}¥¹¼°½Ý¹•É}ÍÑ…Ð¹ÍÑ}Õ¥¤°(€€€€€€€€€€€€ÉÕ¹Ñ¥µ”œèÍÑÈ¡ÉÕ¹Ñ¥µ”¤°€™…±±‰…¬œèÍÑÈ¡™…±±‰…¬¤°€É•ÑÕÉ¹}™…±±‰…¬œèÍÑÈ¡É•ÑÕÉ¹}™…±±‰…¬¤°(€€€€€€€€€€€€ÁÉ½•ÍÍ}™¥áÑÕÉ”œèQÉÕ”°(€€€€€€€€€€€€Ý½É­Í¡½Á}‘ˆœèÍÑÈ¡Ý½É¬€¼€½ÁÌ½Ý½É­Í¡½À¹‘ˆœ¤°(€€€€€€€€€€€€¹…Ñ¥Ù•}‘ˆœèÍÑÈ¡Ý½É¬€¼€‰…Í•±¥¹”½‘…Ñ„½¡½µ•‰½à¹‘ˆœ¤°(€€€€€€€€€€€€™…±±‰…­}É••¥ÁÐœè™…±±‰…­}É••¥ÁÐ°(€€€€€€€€€€€€É•ÑÕÉ¹}™…±±‰…­}É••¥ÁÐœèÉ•ÑÕÉ¹}™…±±‰…­}É••¥ÁÐ°(€€€€€€€ô(€€€€€€€ÁÉ½•ÍÍ}µ…¹…•È€ô}A…­…•‘AÉ½•ÍÍ•Ì¡ÉÕ¹Ñ¥µ”°Ñ½­•¸°‘•Á•¹‘•¹ä°±½Ì¤(€€€€€€€É½½µ}Ù•É¥™¥•ÉlÑ•ÍÑ}É½½µ}‰Õ¹‘±•}É½±±‰…¬t¡™¥áÑÕÉ”°ÁÉ•Ù¥½ÕÌ°…¹‘¥‘…Ñ”°(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€ÁÉ½•ÍÍ}ÉÕ¹¹•ÈõÁÉ½•ÍÍ}µ…¹…•È¹ÉÕ¹}Í•ÉÙ¥•Ì¤(€€€€€€€É•ÍÕ±Ð€ôì(€€€€€€€€€€€€µ½‘”œè€™¥áÑÕÉ”µÁÉ½•ÍÌœ°€™¥áÑÕÉ•}½¹±äœèQÉÕ”°(€€€€€€€€€€€€½µÁ…Ñ¥‰¥±¥Ñå}±…¥´œè€Íå¹Ñ¡•Ñ¥Œµ…Ñ¡•µÁ…­…”ÁÉ½•ÍÌ•Ù¥‘•¹”½¹±äìÁÉ½‘ÕÑ¥½¸½µÁ…Ñ¥‰¥±¥ÑäÕ¹±…¥µ•œ°(€€€€€€€€€€€€ÁÉ½•ÍÍ•Í}ÍÑ…ÉÑ•œèÁÉ½•ÍÍ}µ…¹…•È¹ÁÉ½•ÍÍ•Í}ÍÑ…ÉÑ•°(€€€€€€€€€€€€¹…µ•‘}…ÍÍ•ÉÑ¥½¹}½Õ¹Ðœè±•¸¡ÁÉ½•ÍÍ}µ…¹…•È¹É½ÝÌ¤°(€€€€€€€€€€€€¹…µ•‘}…ÍÍ•ÉÑ¥½¹ÌœèÁÉ½•ÍÍ}µ…¹…•È¹É½ÝÌ°(€€€€€€€€€€€€¹…Ñ¥Ù•}Á½ÉÑ}É•ÑÉ¥•ÌœèÁÉ½•ÍÍ}µ…¹…•È¹¹…Ñ¥Ù•}Á½ÉÑ}É•ÑÉ¥•Ì°(€€€€€€€€€€€€Í…µ•}ÍÑ½É•}É½½µÌœè™¥áÑÕÉ”¹•Ð É½½µ}É½±±‰…­}¡•­Ìœ¤°(€€€€€€€€€€€€Í…µ•}ÍÑ½É•}É½½µÍ}•Ù¥‘•¹•}Í½Á”œè€Íå¹Ñ¡•Ñ¥ŒI½½µÌ½¹…Ñ¥Ù”™¥áÑÕÉ”Ñ…‰±•Ìì¹½Ð¹…Ñ¥Ù”µ•µ‰•È½±½…¸½µÁ…Ñ¥‰¥±¥Ñä•Ù¥‘•¹”œ°(€€€€€€€€€€€€‰Õ¹‘±•}µ…¹¥™•ÍÑÌœèí¹…µ”è}µ…¹¥™•ÍÑ}¡…Í ¡Á…Ñ ¤™½È¹…µ”°Á…Ñ ¥¸(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€é¥À  <œ°€œ°€œ¤°½Á¥•¥ô°(€€€€€€€€€€€€‰Õ¹‘±•}…ÉÑ¥™…Ñ}‰¥¹‘¥¹Ìœèí¹…µ”è}…ÉÑ¥™…Ñ}‰¥¹‘¥¹œ¡Á…Ñ ¤™½È¹…µ”°Á…Ñ ¥¸(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€é¥À  <œ°€œ°€œ¤°½Á¥•¥ô°(€€€€€€€€€€€€™…±±‰…­}•Ù¥‘•¹•}Á…Ñ œè€¡ÍÑÈ¡…ÉÌ¹™…±±‰…­}•Ù¥‘•¹”¤(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€¥˜•Ñ…ÑÑÈ¡…ÉÌ°€™…±±‰…­}•Ù¥‘•¹”œ°9½¹”¤•±Í”9½¹”¤°(€€€€€€€€€€€€™…±±‰…­}¡•­Ìœè™…±±‰…­}É••¥ÁÑl¡•­Ìt°(€€€€€€€€€€€€‘•Á•¹‘•¹å}Á…Ñ œèÍÑÈ¡‘•Á•¹‘•¹ä¤°(€€€€€€€€€€€€Í•ÉÙ¥•}±¥™•å±•}ÑÉ…”œèÁÉ½•ÍÍ}µ…¹…•È¹É½ÝÌ°(€€€€€€€€€€€€±½ÌœèmÍÑÈ¡Á…Ñ ¤™½ÈÁ…Ñ ¥¸Í½ÉÑ•¡±½Ì¹±½ˆ œ¨¹±½œœ¤¥t°(€€€€€€€ô(€€€€€€€¥˜¹½ÐÉ•ÍÕ±ÑlÍ…µ•}ÍÑ½É•}É½½µÌtè(€€€€€€€€€€€É…¥Í”¥áÑÕÉ•I•™ÕÍ…° Í…µ”µÍÑ½É”I½½µÌ…ÍÍ•ÉÑ¥½¹ÌÝ•É”¹½Ð•µ¥ÑÑ•œ¤(€€€•á•ÁÐ	…Í•á•ÁÑ¥½¸…Ì•áŒè(€€€€€€€™…¥±ÕÉ”€ô˜íÑåÁ”¡•áŒ¤¹}}¹…µ•}}ôèí•áôœ(€€€€€€€É…¥Í”(€€€™¥¹…±±äè(€€€€€€€¥˜ÁÉ½•ÍÍ}µ…¹…•Èè(€€€€€€€€€€€ÑÉäè(€€€€€€€€€€€€€€€ÁÉ½•ÍÍ}µ…¹…•È¹ÍÑ½Á}…±° ¤(€€€€€€€€€€€•á•ÁÐá•ÁÑ¥½¸…Ì•áŒè(€€€€€€€€€€€€€€€±•…¹ÕÁ}•ÉÉ½ÉÌ¹…ÁÁ•¹¡ÍÑÈ¡•áŒ¤¤(€€€€€€€ÉÕ¹Ñ¥µ•}ÍÑ½É•}É•µ½Ù•€ô€¡}É•µ½Ù•}ÉÕ¹Ñ¥µ•}É½½Ð¡Ñ•µÁ}É½½Ð°±•…¹ÕÁ}•ÉÉ½ÉÌ¤(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€¥˜Ñ•µÁ}É½½Ð¥Ì¹½Ð9½¹”•±Í”QÉÕ”¤(€€€€€€€É••¥ÁÐ€ôÉ•ÍÕ±Ð½Èìµ½‘”œè€™¥áÑÕÉ”µÁÉ½•ÍÌœ°€™¥áÑÕÉ•}½¹±äœèQÉÕ•ô(€€€€€€€É••¥ÁÑlÍÑ…ÑÕÌt€ô€Á…ÍÍ•œ¥˜™…¥±ÕÉ”¥Ì9½¹”…¹¹½Ð±•…¹ÕÁ}•ÉÉ½ÉÌ•±Í”€™…¥±•œ(€€€€€€€¥˜™…¥±ÕÉ”è(€€€€€€€€€€€É••¥ÁÑl™…¥±ÕÉ”t€ô™…¥±ÕÉ”(€€€€€€€¥˜±•…¹ÕÁ}•ÉÉ½ÉÌè(€€€€€€€€€€€É••¥ÁÑl±•…¹ÕÁ}•ÉÉ½ÉÌt€ô±•…¹ÕÁ}•ÉÉ½ÉÌ(€€€€€€€É••¥ÁÑlÉÕ¹Ñ¥µ•}ÍÑ½É•}É•µ½Ù•t€ôÉÕ¹Ñ¥µ•}ÍÑ½É•}É•µ½Ù•(€€€€€€€É•Á½ÉÑ}Á…Ñ ¹ÝÉ¥Ñ•}Ñ•áÐ¡©Í½¸¹‘ÕµÁÌ¡É••¥ÁÐ°Í½ÉÑ}­•åÌõQÉÕ”°¥¹‘•¹ÐôÈ¤€¬€q¸œ¤(€€€€€€€¥˜±•…¹ÕÁ}•ÉÉ½ÉÌ…¹™…¥±ÕÉ”¥Ì9½¹”è(€€€€€€€€€€€É…¥Í”¥áÑÕÉ•I•™ÕÍ…° ™¥áÑÕÉ”±•…¹ÕÀ™…¥±•ìÉ••¥ÁÐÉ•½É‘•…Ð€œ(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€˜íÉ•Á½ÉÑ}Á…Ñ¡ôè€œ€¬€œì€œ¹©½¥¸¡±•…¹ÕÁ}•ÉÉ½ÉÌ¤¤(€€€É•ÍÕ±ÑlÉ••¥ÁÑ}Á…Ñ t€ôÍÑÈ¡É•Á½ÉÑ}Á…Ñ ¤(€€€É•ÑÕÉ¸É•ÍÕ±Ð(()‘•˜}É•µ½Ù•}ÉÕ¹Ñ¥µ•}É½½Ð¡É½½Ð°•ÉÉ½ÉÌ¤è(€€€É½½Ð€ôA…Ñ ¡É½½Ð¤(€€€ÑÉäè(€€€€€€€€ŒI•ÍÑÉ¥Ð±•…¹ÕÀÑ¼„É•…°°½Ý¹•Ñ•µÁ½É…ÉäÉ½½Ð¸Q¡¥ÌÉ•©•ÑÌ(€€€€€€€€ŒÍåµ±¥¹­•Á…Ñ ½µÁ½¹•¹ÑÌ‰•™½É”É•Í½±Ù¥¹œÑ¡•´…¹•á±Õ‘•ÌÑ¡”(€€€€€€€€Œ½Á•É…Ñ¥½¹…°ÑÉ•”¸(€€€€€€€É½½Ð€ô}É•©•Ñ}½Á•É…Ñ¥½¹…°¡É½½Ð¤(€€€€€€€½Ì¹¡µ½¡É½½Ð°€Á¼ÜÀÀ¤(€€€€€€€™½ÈÕÉÉ•¹Ð°‘¥É•Ñ½É¥•Ì°}™¥±•Ì¥¸½Ì¹Ý…±¬¡É½½Ð°Ñ½Á‘½Ý¸õQÉÕ”°™½±±½Ý±¥¹­Ìõ…±Í”¤è(€€€€€€€€€€€Á…É•¹Ð€ôA…Ñ ¡ÕÉÉ•¹Ð¤(€€€€€€€€€€€™½È¹…µ”¥¸±¥ÍÐ¡‘¥É•Ñ½É¥•Ì¤è(€€€€€€€€€€€€€€€¡¥±€ôÁ…É•¹Ð€¼¹…µ”(€€€€€€€€€€€€€€€ÑÉäè(€€€€€€€€€€€€€€€€€€€µ½‘”€ô¡¥±¹±ÍÑ…Ð ¤¹ÍÑ}µ½‘”(€€€€€€€€€€€€€€€•á•ÁÐ¥±•9½Ñ½Õ¹‘ÉÉ½Èè(€€€€€€€€€€€€€€€€€€€‘¥É•Ñ½É¥•Ì¹É•µ½Ù”¡¹…µ”¤(€€€€€€€€€€€€€€€€€€€½¹Ñ¥¹Õ”(€€€€€€€€€€€€€€€¥˜ÍÑ…Ð¹M}%M19,¡µ½‘”¤è(€€€€€€€€€€€€€€€€€€€€Œ9•Ù•ÈÑÉ…Ù•ÉÍ”½È¡µ½„Íåµ±¥¹¬°•Ù•¸¥˜¥ÐÁ½¥¹ÑÌ(€€€€€€€€€€€€€€€€€€€€Œ‰…¬¥¹Ñ¼Ñ¡”™¥áÑÕÉ”É½½Ð¸(€€€€€€€€€€€€€€€€€€€‘¥É•Ñ½É¥•Ì¹É•µ½Ù”¡¹…µ”¤(€€€€€€€€€€€€€€€€€€€½¹Ñ¥¹Õ”(€€€€€€€€€€€€€€€¥˜¹½ÐÍÑ…Ð¹M}%M%H¡µ½‘”¤è(€€€€€€€€€€€€€€€€€€€‘¥É•Ñ½É¥•Ì¹É•µ½Ù”¡¹…µ”¤(€€€€€€€€€€€€€€€€€€€½¹Ñ¥¹Õ”(€€€€€€€€€€€€€€€¥˜¹½Ðµ½‘”€˜ÍÑ…Ð¹M}%]UMH½È¹½Ðµ½‘”€˜ÍÑ…Ð¹M}%aUMHè(€€€€€€€€€€€€€€€€€€€½Ì¹¡µ½¡¡¥±°€Á¼ÜÀÀ°™½±±½Ý}Íåµ±¥¹­Ìõ…±Í”¤(€€€€€€€Í¡ÕÑ¥°¹ÉµÑÉ•”¡É½½Ð¤(€€€•á•ÁÐá•ÁÑ¥½¸…Ì•áŒè(€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹¡˜ÉÕ¹Ñ¥µ”±•…¹ÕÀ™…¥±•èíÑåÁ”¡•áŒ¤¹}}¹…µ•}}ôèí•áôœ¤(€€€É•µ½Ù•€ô¹½ÐÉ½½Ð¹•á¥ÍÑÌ ¤…¹¹½ÐÉ½½Ð¹¥Í}Íåµ±¥¹¬ ¤(€€€¥˜¹½ÐÉ•µ½Ù•…¹¹½Ð…¹ä¡µ•ÍÍ…”¹ÍÑ…ÉÑÍÝ¥Ñ  ÉÕ¹Ñ¥µ”±•…¹ÕÀ™…¥±•èœ¤™½Èµ•ÍÍ…”¥¸•ÉÉ½ÉÌ¤è(€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ÉÕ¹Ñ¥µ”±•…¹ÕÀ™…¥±•è™¥áÑÕÉ”É½½ÐÍÑ¥±°•á¥ÍÑÌœ¤(€€€É•ÑÕÉ¸É•µ½Ù•(()‘•˜µ…¥¸¡…ÉØõ9½¹”¤è(€€€Á…ÉÍ•È€ô…ÉÁ…ÉÍ”¹ÉÕµ•¹ÑA…ÉÍ•È¡‘•ÍÉ¥ÁÑ¥½¸õ}}‘½}|¤(€€€Á…ÉÍ•È¹…‘‘}…ÉÕµ•¹Ð œ´µµ½‘”œ°¡½¥•Ìô ¥¹•ÉÐµÙ…±¥‘…Ñ¥½¸œ°€™¥áÑÕÉ”µÁÉ½•ÍÌœ¤°‘•™…Õ±Ðô¥¹•ÉÐµÙ…±¥‘…Ñ¥½¸œ¤(€€€Á…ÉÍ•È¹…‘‘}…ÉÕµ•¹Ð œ´µÁÉ•Ù¥½ÕÌœ°É•ÅÕ¥É•õQÉÕ”°ÑåÁ”õA…Ñ ¤(€€€Á…ÉÍ•È¹…‘‘}…ÉÕµ•¹Ð œ´µ…¹‘¥‘…Ñ”œ°É•ÅÕ¥É•õQÉÕ”°ÑåÁ”õA…Ñ ¤(€€€Á…ÉÍ•È¹…‘‘}…ÉÕµ•¹Ð œ´µ™…±±‰…¬œ°É•ÅÕ¥É•õQÉÕ”°ÑåÁ”õA…Ñ ¤(€€€Á…ÉÍ•È¹…‘‘}…ÉÕµ•¹Ð œ´µ™…±±‰…¬µ•Ù¥‘•¹”œ°ÑåÁ”õA…Ñ °(€€€€€€€€€€€€€€€€€€€€€€€¡•±Àô½Ý¹•™¥áÑÕÉ”µ½¹±ä•áÑ•É¹…°É••¥ÁÐ™É½´•á•ÕÑ•…ÉÑ¥™…Ðµ‰½Õ¹™…±±‰…¬…ÍÍ•ÉÑ¥½¹Ìœ¤(€€€Á…ÉÍ•È¹…‘‘}…ÉÕµ•¹Ð œ´µ‘•Á•¹‘•¹äµÁ…Ñ œ°ÑåÁ”õA…Ñ ¤(€€€Á…ÉÍ•È¹…‘‘}…ÉÕµ•¹Ð œ´µ¥¹©•Ðµ…¹‘¥‘…Ñ”µÙ•É¥™¥…Ñ¥½¸µ™…¥±ÕÉ”œ°…Ñ¥½¸ôÍÑ½É•}ÑÉÕ”œ¤(€€€Á…ÉÍ•È¹…‘‘}…ÉÕµ•¹Ð œ´µ¥¹©•Ðµ…¹‘¥‘…Ñ”µ¥¹Ñ•ÉÉÕÁÑ¥½¸œ°…Ñ¥½¸ôÍÑ½É•}ÑÉÕ”œ¤(€€€…ÉÌ€ôÁ…ÉÍ•È¹Á…ÉÍ•}…ÉÌ¡…ÉØ¤((€€€¥˜…ÉÌ¹µ½‘”€ôô€™¥áÑÕÉ”µÁÉ½•ÍÌœè(€€€€€€€¥¹¡•É¥Ñ•€ôm­•ä™½È­•ä¥¸½Ì¹•¹Ù¥É½¸¥˜­•ä¹ÍÑ…ÉÑÍÝ¥Ñ   !	=a|œ°€]=I-M!=A|œ°€!=5	=a}]	|œ¤¥t(€€€€€€€¥˜¥¹¡•É¥Ñ•è(€€€€€€€€€€€Á…ÉÍ•È¹•ÉÉ½È ¥¹¡•É¥Ñ•!	=`•¹‘Á½¥¹Ð½¹™¥ÕÉ…Ñ¥½¸¥ÌÉ•™ÕÍ•¥¸™¥áÑÕÉ”µÁÉ½•ÍÌµ½‘”œ¤(€€€ÑÉäè(€€€€€€€Á…Ñ¡Ì€ôÑÕÁ±”¡}É•©•Ñ}½Á•É…Ñ¥½¹…°¡Á…Ñ ¤™½ÈÁ…Ñ ¥¸(€€€€€€€€€€€€€€€€€€€€€€¡…ÉÌ¹ÁÉ•Ù¥½ÕÌ°…ÉÌ¹…¹‘¥‘…Ñ”°…ÉÌ¹™…±±‰…¬¤¤(€€€•á•ÁÐ€¡¥áÑÕÉ•I•™ÕÍ…°°=MÉÉ½È¤…Ì•áŒè(€€€€€€€Á…ÉÍ•È¹•ÉÉ½È¡ÍÑÈ¡•áŒ¤¤(€€€¥˜±•¸¡Í•Ð¡Á…Ñ¡Ì¤¤€„ô€Ìè(€€€€€€€Á…ÉÍ•È¹•ÉÉ½È ÁÉ•Ù¥½ÕÌ°…¹‘¥‘…Ñ”…¹™…±±‰…¬‰Õ¹‘±•ÌµÕÍÐ‘¥™™•Èœ¤(€€€¥˜…ÉÌ¹µ½‘”€ôô€™¥áÑÕÉ”µÁÉ½•ÍÌœ…¹…ÉÌ¹‘•Á•¹‘•¹å}Á…Ñ ¥Ì9½¹”è(€€€€€€€Á…ÉÍ•È¹•ÉÉ½È ™¥áÑÕÉ”µÁÉ½•ÍÌÉ•ÅÕ¥É•Ì…¸•áÁ±¥¥Ð¥¹ÍÑ…±±•€´µ‘•Á•¹‘•¹äµÁ…Ñ œ¤(€€€¥˜…ÉÌ¹™…±±‰…­}•Ù¥‘•¹”¥Ì¹½Ð9½¹”è(€€€€€€€¥˜…ÉÌ¹µ½‘”€„ô€™¥áÑÕÉ”µÁÉ½•ÍÌœè(€€€€€€€€€€€Á…ÉÍ•È¹•ÉÉ½È œ´µ™…±±‰…¬µ•Ù¥‘•¹”É•ÅÕ¥É•Ì™¥áÑÕÉ”µÁÉ½•ÍÌµ½‘”œ¤(€€€€€€€ÑÉäè(€€€€€€€€€€€…ÉÌ¹™…±±‰…­}•Ù¥‘•¹”€ô}½Ý¹•‘}™¥áÑÕÉ•}•Ù¥‘•¹”¡…ÉÌ¹™…±±‰…­}•Ù¥‘•¹”¤(€€€€€€€•á•ÁÐ€¡¥áÑÕÉ•I•™ÕÍ…°°=MÉÉ½È¤…Ì•áŒè(€€€€€€€€€€€Á…ÉÍ•È¹•ÉÉ½È¡ÍÑÈ¡•áŒ¤¤(€€€‘•Á•¹‘•¹ä€ô9½¹”(€€€¥˜…ÉÌ¹µ½‘”€ôô€™¥áÑÕÉ”µÁÉ½•ÍÌœè(€€€€€€€ÑÉäè(€€€€€€€€€€€‘•Á•¹‘•¹ä€ô}½Ý¹•‘}‘•Á•¹‘•¹ä¡…ÉÌ¹‘•Á•¹‘•¹å}Á…Ñ ¤(€€€€€€€•á•ÁÐ€¡¥áÑÕÉ•I•™ÕÍ…°°=MÉÉ½È¤…Ì•áŒè(€€€€€€€€€€€Á…ÉÍ•È¹•ÉÉ½È¡ÍÑÈ¡•áŒ¤¤(€€€¥˜…ÉÌ¹µ½‘”€ôô€¥¹•ÉÐµÙ…±¥‘…Ñ¥½¸œ…¹€¡…ÉÌ¹¥¹©•Ñ}…¹‘¥‘…Ñ•}¥¹Ñ•ÉÉÕÁÑ¥½¸(€€€€€€€€€€€½È…ÉÌ¹¥¹©•Ñ}…¹‘¥‘…Ñ•}Ù•É¥™¥…Ñ¥½¹}™…¥±ÕÉ”¤è(€€€€€€€Á…ÉÍ•È¹•ÉÉ½È ™…¥±ÕÉ”¥¹©•Ñ¥½¸É•ÅÕ¥É•Ì™¥áÑÕÉ”µÁÉ½•ÍÌµ½‘”…¹…ÉÑ¥™…Ðµ‰½Õ¹™…±±‰…¬¡•­Ìœ¤((€€€€Œ9¼ÁÉ½©•ÐÁ…­…”¥Ì¥µÁ½ÉÑ•Õ¹Ñ¥°•¹‘Á½¥¹Ð…¹Á…Ñ Õ…É‘Ì¡…Ù”Á…ÍÍ•¸(€€€…Á¤€ô}±½…‘}‰Õ¹‘±•}…Á¤ ¤(€€€¥˜…ÉÌ¹¥¹©•Ñ}…¹‘¥‘…Ñ•}Ù•É¥™¥…Ñ¥½¹}™…¥±ÕÉ”…¹…ÉÌ¹¥¹©•Ñ}…¹‘¥‘…Ñ•}¥¹Ñ•ÉÉÕÁÑ¥½¸è(€€€€€€€É…¥Í”…Á¥lÅt Í•±•Ð½¹”™…¥±ÕÉ”¥¹©•Ñ¥½¸…Ð„Ñ¥µ”œ¤(€€€ÑÉäè(€€€€€€€¥˜…ÉÌ¹µ½‘”€ôô€™¥áÑÕÉ”µÁÉ½•ÍÌœè(€€€€€€€€€€€É•Á½ÉÐ€ô}ÉÕ¹}™¥áÑÕÉ•}ÁÉ½•ÍÌ¡…ÉÌ°Á…Ñ¡Ì°‘•Á•¹‘•¹ä°…Á¤¤(€€€€€€€•±Í”è(€€€€€€€€€€€É•Á½ÉÐ€ô}¥¹•ÉÑ}Ù…±¥‘…Ñ¥½¸¡…ÉÌ°Á…Ñ¡Ì°…Á¤¤(€€€•á•ÁÐ¥áÑÕÉ•I•™ÕÍ…°…Ì•áŒè(€€€€€€€Á…ÉÍ•È¹•ÉÉ½È¡ÍÑÈ¡•áŒ¤¤(€€€ÁÉ¥¹Ð¡©Í½¸¹‘ÕµÁÌ¡É•Á½ÉÐ°Í½ÉÑ}­•åÌõQÉÕ”¤¤(()¥˜}}¹…µ•}|€ôô€}}µ…¥¹}|œè(€€€µ…¥¸ ¤