#!/usr/bin/env python3
"""Validate bundles inertly or run the packaged O→C→F→C fixture process proof."""
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
            or len({tuple(value) for value in native_ids}) != 1
            or len({tuple(value) for value in ledger_ids}) != 1):
        raise FixtureRefusal('native and Ledger store identities must be positive device/inode pairs preserved through O/C/F/C')
    import runpy
    gap_verifier = runpy.run_path(str(PROJECT / 'deploy/verify-packaged-workflow-gaps.py'),
                                  run_name='validate_packaged_workflow_gap_evidence')
    expected_manifests = [native_expected[name]['bundle_manifest_sha256'] for name in expected_transitions]
    try:
        shelf_workflow = native.get('shelf_workflow')
        label_workflow = native.get('label_workflow')
        note_workflow = native.get('uncertain_note_workflow')
        gap_verifier['validate_shelf_workflow'](shelf_workflow, expected_manifests, bundles=packages)
        gap_verifier['validate_label_workflow'](label_workflow, expected_manifests, bundles=packages)
        gap_verifier['validate_note_workflow'](note_workflow, expected_manifests, bundles=packages)
    except (TypeError, ValueError, KeyError) as exc:
        raise FixtureRefusal(f'packaged workflow assertion details are invalid: {exc}') from exc
    for workflow in (shelf_workflow, label_workflow, note_workflow):
        for row in workflow['trace']:
            if row.get('ledger_store_identity') != ledger_ids[0]:
                raise FixtureRefusal('Shelf, label or note workflow escaped the native process Ledger store')
    publisher = native.get('publisher_checks')
    publisher_checks = publisher.get('checks') if isinstance(publisher, dict) else None
    required_publisher_checks = {
        'matched_previous_release_preserves_new_fixture_profiles_and_loans',
        'legacy_missing_member_api_is_not_a_rollback_target',
        *FALLBACK_CHECKS,
    }
    if (not isinstance(publisher, dict) or publisher.get('scope') != 'fixture-only'
            or publisher.get('receipt_validation') != 'passed'
            or publisher.get('legacy_bundle_rejected') is not True
            or not isinstance(publisher_checks, dict)
            or set(publisher_checks) != required_publisher_checks
            or any(publisher_checks.get(name) is not True for name in required_publisher_checks)):
        raise FixtureRefusal('pure publisher receipt validation lacks both named fixture checks')
    if (any(not isinstance(value, str) or re.fullmatch(r'[0-9a-fA-F]{64}', value) is None
            for value in profiles) or len(set(profiles)) != 1):
        raise FixtureRefusal('native member profile hash must be a preserved 64-character SHA-256')
    try:
        parsed_loan_ids = [uuid.UUID(value) if isinstance(value, str) else None for value in loan_ids]
    except (ValueError, AttributeError, TypeError) as exc:
        raise FixtureRefusal('native loan operation IDs must be valid UUIDs') from exc
    if (any(value is None or value.int == 0 for value in parsed_loan_ids)
            or len(set(parsed_loan_ids)) != 1
            or not all(valid_timestamp(value) for value in created + confirmed)
            or len(set(created)) != 1 or len(set(confirmed)) != 1):
        raise FixtureRefusal('native loan ID and creation/confirmation timestamps must be valid and preserved through O/C/F/C')
    if any(datetime.fromisoformat(start) > datetime.fromisoformat(end)
           for start, end in zip(created, confirmed)):
        raise FixtureRefusal('native loan confirmation timestamp precedes loan creation')

    process_assertions = native.get('process_assertions')
    expected_names = ['packaged_native_listener',
                      'packaged_companion_code_static_and_physical_boundary',
                      'packaged_gateway_code_and_static_root',
                      'native_member_profile_avatar_private_note_badge_loan_history']
    if not isinstance(process_assertions, list) or len(process_assertions) != 16:
        raise FixtureRefusal('native process report must contain all 16 named process assertions')
    for index, row in enumerate(process_assertions):
        package_name = expected_transitions[index // len(expected_names)]
        expected_binding = native_expected[package_name]
        expected_name = expected_names[index % len(expected_names)]
        if (not isinstance(row, dict) or row.get('result') != 'passed'
                or row.get('name') != expected_name
                or {key: row.get(key) for key in expected_binding} != expected_binding):
            raise FixtureRefusal('native packaged process assertion is missing, unpassed or bound to another artifact')
        if expected_name == 'native_member_profile_avatar_private_note_badge_loan_history':
            if (not valid_identity(row.get('native_store_identity'))
                    or row.get('native_store_identity') != native_ids[index // 4]
                    or not valid_identity(row.get('ledger_store_identity'))
                    or row.get('ledger_store_identity') != ledger_ids[index // 4]
                    or row.get('profile_sha256') != profiles[index // 4]
                    or row.get('loan_operation_id') != loan_ids[index // 4]
                    or row.get('loan_created_at') != created[index // 4]
                    or row.get('loan_confirmed_at') != confirmed[index // 4]
                    or type(row.get('physical_effects')) is not int or row.get('physical_effects') != 0):
                raise FixtureRefusal('native process assertion lacks valid member, loan, identity or physical-boundary evidence')
        else:
            if (type(row.get('pid')) is not int or row['pid'] <= 0
                    or row.get('host') != '127.0.0.1'
                    or type(row.get('port')) is not int or row['port'] <= 0):
                raise FixtureRefusal('native packaged listener assertion lacks a positive PID and loopback port')
    return checks


def _load_bundle_api():
    sys.path.insert(0, str(PROJECT / 'deploy'))
    from release_bundle import (FALLBACK_CHECKS, BundleError, recover_interrupted,
                                select_bundle, validate_bundle, _require_workshop_compatibility,
                                _validate_fallback_policy, _validate_fallback_receipt)
    return (FALLBACK_CHECKS, BundleError, recover_interrupted, select_bundle, validate_bundle,
            _require_workshop_compatibility, _validate_fallback_policy,
            _validate_fallback_receipt)


def _inert_validation(args, paths, api):
    _, BundleError, _, _, validate_bundle = api[:5]
    previous_path, candidate_path, fallback_path = paths
    previous, candidate, fallback = (validate_bundle(path) for path in paths)
    if any(item.get('format') != 2 for item in (previous, candidate, fallback)):
        raise BundleError('inert validation requires complete format-2 O/C/F bundles')
    if len(set(paths)) != 3:
        raise BundleError('previous, candidate and fallback bundles must differ')
    return {
        'mode': 'inert-validation', 'fixture_only': True,
        'compatibility_claim': 'unclaimed', 'processes_started': 0,
        'selector_exercised': False,
        'validated_bundles': {name: _manifest_hash(path) for name, path in
                              zip(('previous', 'candidate', 'fallback'), paths)},
        'process_scope': 'format-and-artifact-integrity-only',
    }


def _free_ports(count):
    sockets, ports = [], []
    try:
        for _ in range(count):
            sock = socket.socket()
            sock.bind(('127.0.0.1', 0))
            sockets.append(sock)
            ports.append(sock.getsockname()[1])
        if len(set(ports)) != count or any(not 32768 <= port <= 60999 for port in ports):
            raise FixtureRefusal('OS did not provide distinct unprivileged loopback ports')
        return ports
    finally:
        for sock in sockets:
            sock.close()


def _pid_owns_listener(pid, port):
    inodes = set()
    for table in ('/proc/net/tcp', '/proc/net/tcp6'):
        try:
            rows = Path(table).read_text().splitlines()[1:]
        except OSError:
            continue
        for row in rows:
            fields = row.split()
            if len(fields) > 9 and fields[1].rsplit(':', 1)[-1] == f'{port:04X}' and fields[3] == '0A':
                inodes.add(fields[9])
    if not inodes:
        return False
    try:
        for name in os.listdir(f'/proc/{pid}/fd'):
            target = os.readlink(f'/proc/{pid}/fd/{name}')
            if target.startswith('socket:[') and target.endswith(']') and target[8:-1] in inodes:
                return True
        return False
    except OSError:
        return False


def _listener_owner_pids(port):
    inodes = set()
    for table in ('/proc/net/tcp', '/proc/net/tcp6'):
        try:
            rows = Path(table).read_text().splitlines()[1:]
        except OSError:
            continue
        for row in rows:
            fields = row.split()
            if len(fields) > 9 and fields[1].rsplit(':', 1)[-1] == f'{port:04X}' and fields[3] == '0A':
                inodes.add(fields[9])
    if not inodes:
        return ()
    owners = []
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            descriptors = process / 'fd'
            for name in os.listdir(descriptors):
                target = os.readlink(descriptors / name)
                if target.startswith('socket:[') and target.endswith(']') and target[8:-1] in inodes:
                    owners.append(int(process.name))
                    break
        except OSError:
            continue
    return tuple(sorted(set(owners)))


def _http(url, pid, port, expected=None):
    if not _pid_owns_listener(pid, port):
        owners = _listener_owner_pids(port)
        foreign = [owner for owner in owners if owner != pid]
        if foreign:
            raise ListenerOwnershipMismatch(pid, port, foreign)
        raise ConnectionError(f'fixture listener at {port} is not ready or not yet observable for pid {pid}')
    with urllib.request.urlopen(url, timeout=0.8) as response:
        body = response.read()
    if not _pid_owns_listener(pid, port):
        raise FixtureRefusal(f'listener ownership changed during probe at {port} for fixture process {pid}')
    if callable(expected):
        expected(body)
    elif expected is not None and body != expected:
        raise FixtureRefusal(f'packaged static response differs at {url}')
    return body


def _validate_native_status(body):
    try:
        payload = json.loads(body)
    except (TypeError, ValueError) as exc:
        raise FixtureRefusal('native readiness endpoint did not return JSON') from exc
    if not isinstance(payload, dict):
        raise FixtureRefusal('native readiness endpoint returned an unexpected response')


def _assert_native_state_snapshot(expected, observed):
    if expected != observed:
        raise FixtureRefusal('native member/loan state changed across packaged process transition')


class _PackagedProcesses:
    def __init__(self, runtime, token, dependency, log_root):
        self.runtime, self.token, self.dependency = runtime, token, dependency
        self.log_root = log_root
        self.children = {}
        self.rows = []
        self.processes_started = 0
        self.serial = 0
        self.native_state = None
        self.current_release = None
        self.native_port_retries = []
        self.native_port, self.companion_port, self.gateway_port = _free_ports(3)

    def _base_env(self, release, component, ready=None):
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(('HBOX_', 'WORKSHOP_', 'HOMEBOX_WEB_'))}
        dep_link = self.runtime / 'program-files/runtime/hardware/python'
        dep_link.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not dep_link.exists():
            dep_link.symlink_to(self.dependency, target_is_directory=True)
        env.update({'WORKSHOP_ROOT': str(self.runtime), 'WORKSHOP_FIXTURE_PROCESS': '1',
                    'WORKSHOP_FIXTURE_TOKEN': self.token, 'WORKSHOP_BIND_HOST': '127.0.0.1',
                    'PYTHONDONTWRITEBYTECODE': '1'})
        if component == 'native':
            env.update({'HOMEBOX_WEB_HOST': '127.0.0.1', 'HOMEBOX_WEB_PORT': str(self.native_port),
                        'HBOX_OPTIONS_ALLOW_REGISTRATION': 'true'})
        elif component == 'companion':
            env.update({'WORKSHOP_NATIVE_BASE': f'http://127.0.0.1:{self.native_port}',
                        'WORKSHOP_COMPANION_PORT': '0', 'WORKSHOP_PORT': '0',
                        'WORKSHOP_FIXTURE_READY_FILE': str(ready)})
        else:
            env.update({'WORKSHOP_NATIVE_PORT': str(self.native_port),
                        'WORKSHOP_COMPANION_PORT': str(self.companion_port), 'WORKSHOP_PORT': '0',
                        'WORKSHOP_FIXTURE_READY_FILE': str(ready)})
        return env

    def _launch(self, release, component, ready=None):
        self.serial += 1
        log_path = self.log_root / f'{self.serial:02d}-{component}.log'
        log = log_path.open('wb')
        command = [sys.executable, str(release / 'deploy/run-release.py'), component]
        child = subprocess.Popen(command, cwd=self.runtime, env=self._base_env(release, component, ready),
                                 stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                 start_new_session=True)
        self.processes_started += 1
        self.children[component] = (child, log, log_path)
        return child

    def _wait_listener(self, child, port, url, ready=None, expected=None, origin_checks=None, timeout=30):
        deadline = time.monotonic() + timeout
        last_error = None
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise FixtureRefusal(f'packaged process exited before readiness: pid {child.pid}')
            try:
                if ready:
                    obj = json.loads(ready.read_text())
                    if (obj.get('pid') != child.pid or obj.get('host') != '127.0.0.1'
                            or not 32768 <= obj.get('port', 0) <= 60999):
                        raise FixtureRefusal('packaged process ready record did not bind its owned loopback listener')
                    if origin_checks:
                        origin_checks(obj)
                    port = obj['port']
                    url = url.rsplit(':', 1)[0] + ':' + str(port) + '/'
                _http(url, child.pid, port, expected)
                return port
            except ListenerOwnershipMismatch:
                raise
            except (OSError, ValueError, urllib.error.URLError) as exc:
                last_error = exc
                time.sleep(0.1)
        raise FixtureRefusal(f'packaged process did not become ready: {last_error}')

    def _start_native_listener(self, release):
        for attempt in range(3):
            native = self._launch(release, 'native')
            try:
                self._wait_listener(native, self.native_port,
                    f'http://127.0.0.1:{self.native_port}/api/v1/status', expected=_validate_native_status,
                    timeout=90)
                return native
            except ListenerOwnershipMismatch as exc:
                foreign_owners = [owner for owner in exc.owners if owner != native.pid]
                if (not foreign_owners or native.poll() is not None or attempt == 2):
                    raise
                old_port = self.native_port
                self.stop_all()
                self.native_port = _free_ports(1)[0]
                self.native_port_retries.append({'old_port': old_port, 'foreign_listener_pids': foreign_owners,
                                                 'terminated_fixture_pid': native.pid,
                                                 'new_port': self.native_port})
        raise FixtureRefusal('native listener retry budget exhausted')

    def start(self, release):
        release = Path(release).resolve(strict=True)
        self.current_release = release
        binding = _artifact_binding(release)
        manifest_hash = binding['bundle_manifest_sha256']
        self.runtime.joinpath('work/baseline/data').mkdir(mode=0o700, parents=True, exist_ok=True)
        baseline = self.runtime / 'work/baseline'
        pepper = baseline / 'pepper'
        if not pepper.exists():
            pepper.write_text(uuid.uuid4().hex + uuid.uuid4().hex)
        database = baseline / 'data/homebox.db'
        database.touch(mode=0o600, exist_ok=True)
        account_file = baseline / 'test-account.json'
        if not account_file.exists():
            account_file.write_text('{}')
        pepper.chmod(0o600)
        (baseline / 'pepper').chmod(0o600)
        account_file.chmod(0o600)

        native = self._start_native_listener(release)
        self.rows.append({'name': 'packaged_native_listener', 'result': 'passed',
                          **binding, 'pid': native.pid,
                          'host': '127.0.0.1', 'port': self.native_port,
                          'readiness_endpoint': '/api/v1/status'})

        comp_ready = self.runtime / 'work/fixture-companion-ready.json'
        companion = self._launch(release, 'companion', comp_ready)
        def check_companion(obj):
            if (Path(obj.get('code_root', '')).resolve() != release
                    or Path(obj.get('terminal_root', '')).resolve() != (release / 'kiosk').resolve()
                    or obj.get('physical_boundary') != 'pre-import stubs'
                    or any(not Path(path).resolve().is_relative_to(release)
                           for path in obj.get('module_origins', {}).values())):
                raise FixtureRefusal('companion code, static root, module origin or physical boundary escaped the selected bundle')
        self.companion_port = self._wait_listener(companion, 0,
            'http://127.0.0.1:0/', ready=comp_ready,
            expected=(release / 'kiosk/index.html').read_bytes(), origin_checks=check_companion)
        comp_row = json.loads(comp_ready.read_text())
        self.rows.append({'name': 'packaged_companion_code_static_and_physical_boundary', 'result': 'passed',
                          **binding, 'pid': companion.pid,
                          'host': comp_row['host'], 'port': self.companion_port,
                          'module_origins': comp_row['module_origins'],
                          'terminal_root': comp_row['terminal_root'],
                          'physical_boundary': comp_row['physical_boundary']})

        gateway_ready = self.runtime / 'work/fixture-gateway-ready.json'
        gateway = self._launch(release, 'gateway', gateway_ready)
        def check_gateway(obj):
            if (Path(obj.get('code_root', '')).resolve() != release
                    or Path(obj.get('static_root', '')).resolve() != (release / 'public').resolve()):
                raise FixtureRefusal('gateway code or static root escaped the selected bundle')
        self.gateway_port = self._wait_listener(gateway, 0, 'http://127.0.0.1:0/',
            ready=gateway_ready, expected=(release / 'public/index.html').read_bytes(),
            origin_checks=check_gateway)
        gate_row = json.loads(gateway_ready.read_text())
        self.rows.append({'name': 'packaged_gateway_code_and_static_root', 'result': 'passed',
                          **binding, 'pid': gateway.pid,
                          'host': gate_row['host'], 'port': self.gateway_port,
                          'static_root': gate_row['static_root']})
        if self.native_state is None:
            self.native_state = self._create_native_state(manifest_hash)
        else:
            observed = self._native_state_snapshot(self.native_state)
            _assert_native_state_snapshot(self.native_state['snapshot'], observed)
            self.rows.append({'name': 'native_member_profile_avatar_private_note_badge_loan_history',
                              'result': 'passed', **binding,
                              'profile_sha256': observed['member_profile_sha256'],
                              'loan_operation_id': observed['loan_history'][0]['operation_id'],
                              'loan_created_at': observed['loan_history'][0]['created_at'],
                              'loan_confirmed_at': observed['loan_history'][0]['confirmed_at'],
                              'native_store_identity': observed['native_store_identity'],
                              'ledger_store_identity': observed['ledger_store_identity'],
                              'physical_effects': 0})

    def _api_json(self, base, path, method='GET', payload=None, *, token=None, child=None, port=None):
        if child is not None and not _pid_owns_listener(child.pid, port):
            raise FixtureRefusal(f'fixture listener ownership failed before API request: {path}')
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        if base == f'http://127.0.0.1:{self.companion_port}':
            headers['Origin'] = base
        request = urllib.request.Request(base + path, method=method, headers=headers,
            data=None if payload is None else json.dumps(payload).encode())
        # Fixture native registration and migration-adjacent writes can take
        # longer on the isolated storage used by the whole-map proof. Keep the
        # bounded request timeout generous enough for those owned processes.
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read()
        if child is not None and not _pid_owns_listener(child.pid, port):
            raise FixtureRefusal(f'fixture listener ownership changed during API request: {path}')
        return json.loads(body) if body else None

    def _native_auth(self):
        account = json.loads((self.runtime / 'work/baseline/test-account.json').read_text())
        login = self._api_json(f'http://127.0.0.1:{self.native_port}', '/api/v1/users/login',
                               'POST', {'username': account['email'], 'password': account['password']},
                               child=self.children['native'][0], port=self.native_port)
        return login['token'].removeprefix('Bearer ')

    def _native_state_snapshot(self, state):
        base = f'http://127.0.0.1:{self.native_port}'
        child = self.children['native'][0]
        token = self._native_auth()
        profile = self._api_json(base, f"/api/v1/groups/members/{state['member_id']}/profile",
                                 token=token, child=child, port=self.native_port)
        if (profile.get('id') != state['member_id'] or profile.get('name') != state['member_name']
                or profile.get('avatar') != state['avatar'] or profile.get('notes') != state['notes']):
            raise FixtureRefusal('native member profile, avatar or private note did not reopen')
        entity = self._api_json(base, f"/api/v1/entities/{state['entity_id']}", token=token,
                                child=child, port=self.native_port)
        if entity.get('id') != state['entity_id'] or entity.get('name') != state['entity_name']:
            raise FixtureRefusal('native loan entity identity did not reopen')
        native_db = self.runtime / 'work/baseline/data/homebox.db'
        ledger_db = self.runtime / 'work/ops/ledger.db'
        native_stat, ledger_stat = native_db.stat(), ledger_db.stat()
        with sqlite3.connect(ledger_db) as db:
            db.row_factory = sqlite3.Row
            operation = db.execute('SELECT id,group_id,actor_id,action,status,created_at FROM operations WHERE id=?',
                                   (state['loan_id'],)).fetchone()
            if not operation:
                raise FixtureRefusal('fixture loan operation disappeared from ledger history')
            events = [dict(row) for row in db.execute(
                'SELECT kind,created_at FROM events WHERE operation_id=? ORDER BY sequence', (state['loan_id'],))]
            assets = [row[0] for row in db.execute(
                'SELECT entity_id FROM operation_assets WHERE operation_id=? ORDER BY entity_id',
                (state['loan_id'],))]
            badges = [dict(row) for row in db.execute(
                'SELECT id,user_id,revoked,created_at FROM badges WHERE user_id=? ORDER BY created_at',
                (state['member_id'],))]
            custody = [dict(row) for row in db.execute(
                'SELECT group_id,entity_id,actor_id,operation_id FROM custody WHERE operation_id=?',
                (state['loan_id'],))]
        if (operation['action'] != 'check_out' or operation['status'] != 'completed'
                or assets != [state['entity_id']] or not any(row['kind'] == 'completed' for row in events)
                or len(badges) != 1 or badges[0]['id'] != state['badge_id']
                or badges[0]['revoked'] != 0 or not custody
                or custody[0]['actor_id'] != state['member_id']):
            raise FixtureRefusal('native badge or loan/date/history state did not reopen')
        completed = next(row['created_at'] for row in events if row['kind'] == 'completed')
        return {'member_profile_sha256': hashlib.sha256(json.dumps(profile, sort_keys=True,
                    separators=(',', ':')).encode()).hexdigest(),
                'loan_history': [{'operation_id': operation['id'], 'group_id': operation['group_id'],
                    'actor_id': operation['actor_id'], 'action': operation['action'],
                    'status': operation['status'], 'created_at': operation['created_at'],
                    'confirmed_at': completed, 'events': events, 'assets': assets}],
                'badge_state': badges, 'custody': custody,
                'native_store_identity': [native_stat.st_dev, native_stat.st_ino],
                'ledger_store_identity': [ledger_stat.st_dev, ledger_stat.st_ino]}

    def _create_native_state(self, manifest_hash):
        base = f'http://127.0.0.1:{self.native_port}'
        native_child = self.children['native'][0]
        email = uuid.uuid4().hex + '@fixture.invalid'
        password = uuid.uuid4().hex + uuid.uuid4().hex
        self._api_json(base, '/api/v1/users/register', 'POST',
                       {'name': 'Whole Map Fixture Owner', 'email': email, 'password': password},
                       child=native_child, port=self.native_port)
        account = {'email': email, 'password': password}
        account_file = self.runtime / 'work/baseline/test-account.json'
        account_file.write_text(json.dumps(account))
        account_file.chmod(0o600)
        token = self._native_auth()
        owner = self._api_json(base, '/api/v1/users/self', token=token,
                               child=native_child, port=self.native_port)['item']
        request_key = str(uuid.uuid4())
        member = self._api_json(base, '/api/v1/groups/members', 'POST',
                    {'name': 'Fixture Member', 'email': '', 'requestKey': request_key},
                    token=token, child=native_child, port=self.native_port)
        member_id = member['id']
        profile = self._api_json(base, f'/api/v1/groups/members/{member_id}/profile', token=token,
                                 child=native_child, port=self.native_port)
        avatar = 'data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCABAAEADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDLooor6g+bCiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKAP//Z'
        notes = 'Fixture private member note ' + uuid.uuid4().hex
        profile.update({'name': 'Fixture Member Updated', 'email': '', 'avatar': avatar, 'notes': notes})
        profile = self._api_json(base, f'/api/v1/groups/members/{member_id}/profile', 'PUT', profile,
                                 token=token, child=native_child, port=self.native_port)
        types = self._api_json(base, '/api/v1/entity-types', token=token,
                               child=native_child, port=self.native_port)
        item_type = next((row for row in types if not row.get('isLocation')), None)
        if item_type is None:
            item_type = self._api_json(base, '/api/v1/entity-types', 'POST',
                {'name': 'Whole Map Fixture Equipment', 'isLocation': False, 'icon': ''},
                token=token, child=native_child, port=self.native_port)
        entity = self._api_json(base, '/api/v1/entities', 'POST',
                    {'name': 'Whole Map Fixture Loan Item', 'entityTypeId': item_type['id'],
                     'parentId': None, 'quantity': 1}, token=token,
                    child=native_child, port=self.native_port)
        entity['parentId'] = (entity.get('parent') or {}).get('id')
        entity['entityTypeId'] = entity.get('entityType', {}).get('id', item_type['id'])
        entity['tagIds'] = [tag['id'] for tag in entity.get('tags', [])]
        fields = list(entity.get('fields', []))
        fields.append({'name': 'Equipment condition', 'type': 'text', 'textValue': 'Ready'})
        entity['fields'] = fields
        entity = self._api_json(base, f"/api/v1/entities/{entity['id']}", 'PUT', entity, token=token,
                                child=native_child, port=self.native_port)
        companion_base = f'http://127.0.0.1:{self.companion_port}'
        companion_child = self.children['companion'][0]
        badge = self._api_json(companion_base, '/badge/issue', 'POST', {'user_id': member_id},
                               child=companion_child, port=self.companion_port)
        scan = self._api_json(companion_base, '/scan', 'POST', {'code': badge['code']},
                              child=companion_child, port=self.companion_port)
        if scan.get('kind') != 'user' or scan.get('user', {}).get('id') != member_id:
            raise FixtureRefusal('fixture badge did not create the expected member session')
        loan = self._api_json(companion_base, '/checkout/confirm', 'POST',
                    {'assets': [entity['id']], 'request_key': str(uuid.uuid4()),
                     'session_generation': scan['generation'], 'session_instance': scan['instance']},
                    child=companion_child, port=self.companion_port)
        if loan.get('status') != 'completed':
            raise FixtureRefusal('fixture native loan did not complete')
        state = {'member_id': member_id, 'member_name': profile['name'], 'avatar': avatar,
                 'notes': notes, 'entity_id': entity['id'], 'entity_name': entity['name'],
                 'badge_id': badge['id'], 'loan_id': loan['id'], 'group_id': owner['defaultGroupId']}
        snapshot = self._native_state_snapshot(state)
        state['snapshot'] = snapshot
        self.rows.append({'name': 'native_member_profile_avatar_private_note_badge_loan_history',
                          'result': 'passed', **_artifact_binding(self.current_release),
                          'profile_sha256': snapshot['member_profile_sha256'],
                          'loan_operation_id': snapshot['loan_history'][0]['operation_id'],
                          'loan_created_at': snapshot['loan_history'][0]['created_at'],
                          'loan_confirmed_at': snapshot['loan_history'][0]['confirmed_at'],
                          'native_store_identity': snapshot['native_store_identity'],
                          'ledger_store_identity': snapshot['ledger_store_identity'],
                          'physical_effects': 0})
        return state

    def stop_all(self):
        errors = []
        for component in ('gateway', 'companion', 'native'):
            entry = self.children.get(component)
            if not entry:
                continue
            child, log, _ = entry
            try:
                if child.poll() is None:
                    try:
                        child.terminate()
                    except Exception as exc:
                        errors.append(f'{component} terminate failed: {type(exc).__name__}: {exc}')
                    try:
                        child.wait(timeout=15 if component == 'native' else 5)
                    except Exception as exc:
                        errors.append(f'{component} wait after terminate failed: {type(exc).__name__}: {exc}')
                        try:
                            child.kill()
                            child.wait(timeout=5)
                        except Exception as kill_exc:
                            errors.append(f'{component} kill/wait failed: {type(kill_exc).__name__}: {kill_exc}')
            except Exception as exc:
                errors.append(f'{component} cleanup failed: {type(exc).__name__}: {exc}')
                try:
                    if child.poll() is None:
                        child.kill()
                        child.wait(timeout=5)
                except Exception as kill_exc:
                    errors.append(f'{component} final kill/wait failed: {type(kill_exc).__name__}: {kill_exc}')
            try:
                if child.poll() is not None:
                    self.children.pop(component, None)
                else:
                    # Keep unresolved children available for another cleanup
                    # attempt and for diagnosis by the caller.
                    errors.append(f'{component} pid {getattr(child, "pid", "unknown")} remained alive')
            except Exception as exc:
                errors.append(f'{component} final poll failed: {type(exc).__name__}: {exc}')
            finally:
                try:
                    log.close()
                except Exception as exc:
                    errors.append(f'{component} log close failed: {type(exc).__name__}: {exc}')
        if errors:
            raise FixtureRefusal('; '.join(errors))

    def run_services(self, arguments):
        if arguments[0] == 'stop':
            self.stop_all()
            return
        self.stop_all()
        selected = (self.runtime / 'work/application-current').resolve(strict=True)
        self.start(selected)


def _fixture_receipt(previous, candidate, fallback, api, evidence_path=None):
    FALLBACK_CHECKS, BundleError, _, _, validate_bundle = api[:5]
    _, _, _, _, _, require_capability, validate_policy, validate_receipt = api
    previous_manifest, candidate_manifest, fallback_manifest = (
        validate_bundle(path) for path in (previous, candidate, fallback))
    for manifest in (previous_manifest, candidate_manifest, fallback_manifest):
        _require_receipt_bindings(manifest)
    require_capability(previous_manifest, role='previous')
    require_capability(candidate_manifest, role='candidate', require_writer=True)
    capability = require_capability(fallback_manifest, role='fallback')
    try:
        policy = validate_policy(fallback_manifest.get('fallback_policy'))
    except BundleError as exc:
        raise FixtureRefusal(f'fixture fallback policy preflight failed: {exc}') from exc
    if evidence_path is not None:
        raw_checks = _load_fallback_evidence(evidence_path, (previous, candidate, fallback))
    else:
        raw_checks = fallback_manifest['provenance'].get('test_receipt', {}).get('fallback_checks')
        if not isinstance(raw_checks, dict) or set(raw_checks) != set(FALLBACK_CHECKS) or any(
                raw_checks.get(name) != 'passed' for name in FALLBACK_CHECKS):
            missing = sorted(name for name in FALLBACK_CHECKS
                             if not isinstance(raw_checks, dict) or raw_checks.get(name) != 'passed')
            raise FixtureRefusal('artifact-bound named fallback checks are missing or unpassed: ' + ', '.join(missing))
    if (policy.get('evidence_scope') != 'fixture-only'
            or policy.get('runtime_state_policy') != 'same-stores-no-restore'
            or policy.get('physical_effect_policy') != 'never-replay'
            or policy.get('roomsv2_read_versions') != capability.get('read_versions')
            or policy.get('workshop_mutation_mode') != capability.get('write_mode')
            or policy.get('candidate_manifest_sha256') != _manifest_hash(candidate)
            or policy.get('member_profile_loan_compatibility') != 'verified'):
        raise FixtureRefusal('fixture fallback policy does not match its artifact-bound capability')
    if candidate_manifest['provenance']['workshop_capability']['write_mode'] != 'v2':
        raise FixtureRefusal('candidate package must have a version-2 Workshop writer')
    # stage_bundle checked raw receipt bytes before packaging; validate_bundle
    # rechecks the embedded canonical object hash. Only these bound `passed`
    # results may now be translated for select_bundle's boolean schema.
    receipt = {
        'execution_scope': 'fixture-only',
        'previous_bundle_manifest_sha256': _manifest_hash(previous),
        'previous_native_sha256': previous_manifest['provenance']['native_sha256'],
        'candidate_bundle_manifest_sha256': _manifest_hash(candidate),
        'candidate_native_sha256': candidate_manifest['provenance']['native_sha256'],
        'fallback_bundle_manifest_sha256': _manifest_hash(fallback),
        'fallback_native_sha256': fallback_manifest['provenance']['native_sha256'],
        'fallback_policy_sha256': hashlib.sha256(json.dumps(policy, sort_keys=True,
            separators=(',', ':')).encode()).hexdigest(),
        'checks': {name: raw_checks[name] == 'passed' for name in FALLBACK_CHECKS},
    }
    try:
        validate_receipt(receipt, previous, candidate, fallback)
    except BundleError as exc:
        raise FixtureRefusal(f'fixture fallback receipt preflight failed: {exc}') from exc
    return receipt


def _preflight_fixture_packages(paths, api, evidence_path=None):
    _, BundleError, _, _, validate_bundle, require_capability, _, _ = api
    if len(paths) != 3 or len(set(map(Path, paths))) != 3:
        raise BundleError('fixture-process requires distinct O/C/F packages')
    manifests = []
    for path in paths:
        manifest = validate_bundle(path)
        _require_receipt_bindings(manifest)
        provenance = manifest.get('provenance', {})
        if (manifest.get('format') != 2
                or provenance.get('build_receipt', {}).get('execution_scope') != 'fixture-only'
                or provenance.get('test_receipt', {}).get('execution_scope') != 'fixture-only'):
            raise BundleError('fixture-process requires complete fixture-only format-2 O/C/F packages')
        manifests.append(manifest)
    o_capability = require_capability(manifests[0], role='previous')
    c_capability = require_capability(manifests[1], role='candidate', require_writer=True)
    f_capability = require_capability(manifests[2], role='fallback')
    if (o_capability['write_mode'] != 'disabled'
            or c_capability['write_mode'] != 'v2'
            or f_capability['write_mode'] not in ('v2', 'disabled')):
        raise BundleError('fixture O/C/F Workshop capabilities do not satisfy disabled-O, v2-C, compatible-F policy')
    first_receipt = _fixture_receipt(paths[0], paths[1], paths[2], api, evidence_path)
    # F-to-C return uses the same byte-identical F artifact and the same
    # candidate-bound policy, with F as the selected previous package.
    return_receipt = _fixture_receipt(paths[2], paths[1], paths[2], api, evidence_path)
    return manifests, first_receipt, return_receipt


def _run_fixture_process(args, paths, dependency, api):
    _, BundleError, _, _, validate_bundle = api[:5]
    if args.inject_candidate_interruption or args.inject_candidate_verification_failure:
        raise BundleError('fixture-process mode uses its own same-store candidate failure scenario')
    manifests, fallback_receipt, return_fallback_receipt = _preflight_fixture_packages(
        paths, api, getattr(args, 'fallback_evidence', None))
    if not dependency.is_dir() or dependency.is_symlink():
        raise FixtureRefusal('dependency path must be an existing recorded non-symlink directory')

    # Import the process runner only after every package, capability, policy and
    # raw receipt binding has passed. No run/store root exists at this point.
    import runpy
    room_verifier = runpy.run_path(str(PROJECT / 'deploy/verify-workshop-rooms.py'),
                                   run_name='fixture_process_rooms')

    run_id = uuid.uuid4().hex
    retained = PROJECT / 'work/queue-coordinator' / f'whole-map-process-run-{run_id}'
    retained.mkdir(mode=0o700, parents=True)
    logs = retained / 'logs'
    logs.mkdir(mode=0o700)
    token = uuid.uuid4().hex + uuid.uuid4().hex
    report_path = retained / 'receipt.json'
    process_manager = None
    result = None
    failure = None
    temp_root = None
    cleanup_errors = []
    try:
        temp_root = Path(tempfile.mkdtemp(prefix='whole-map-fixture-process-'))
        os.chmod(temp_root, 0o700)
        releases = temp_root / 'releases'
        releases.mkdir(mode=0o700)
        copied = []
        for name, path in zip(('O', 'C', 'F'), paths):
            destination = releases / name
            shutil.copytree(path, destination, symlinks=False)
            copied.append(destination.resolve(strict=True))
        previous, candidate, fallback = copied
        return_fallback = releases / 'F-return'
        shutil.copytree(fallback, return_fallback, symlinks=False)
        return_fallback = return_fallback.resolve(strict=True)
        for package in (*copied, return_fallback):
            if validate_bundle(package).get('format') != 2:
                raise FixtureRefusal('copied fixture package changed during staging')

        runtime = temp_root / 'runtime'
        runtime.mkdir(mode=0o700)
        (runtime / '.fixture-process-token').write_text(token)
        (runtime / '.fixture-process-token').chmod(0o600)
        work = runtime / 'work'
        work.mkdir(mode=0o700)
        (work / 'application-current').symlink_to(previous, target_is_directory=True)
        owner_stat = temp_root.stat()
        fixture = {
            'owned_root': str(temp_root), 'owner_identity': (owner_stat.st_dev, owner_stat.st_ino, owner_stat.st_uid),
            'runtime': str(runtime), 'fallback': str(fallback), 'return_fallback': str(return_fallback),
            'process_fixture': True,
            'workshop_db': str(work / 'ops/workshop.db'),
            'native_db': str(work / 'baseline/data/homebox.db'),
            'fallback_receipt': fallback_receipt,
            'return_fallback_receipt': return_fallback_receipt,
        }
        process_manager = _PackagedProcesses(runtime, token, dependency, logs)
        room_verifier['test_room_bundle_rollback'](fixture, previous, candidate,
                                                    process_runner=process_manager.run_services)
        result = {
            'mode': 'fixture-process', 'fixture_only': True,
            'compatibility_claim': 'synthetic matched-package process evidence only; production compatibility unclaimed',
            'processes_started': process_manager.processes_started,
            'named_assertion_count': len(process_manager.rows),
            'named_assertions': process_manager.rows,
            'native_port_retries': process_manager.native_port_retries,
            'same_store_rooms': fixture.get('room_rollback_checks'),
            'same_store_rooms_evidence_scope': 'synthetic Rooms/native fixture tables; not native member/loan compatibility evidence',
            'bundle_manifests': {name: _manifest_hash(path) for name, path in
                                 zip(('O', 'C', 'F'), copied)},
            'bundle_artifact_bindings': {name: _artifact_binding(path) for name, path in
                                         zip(('O', 'C', 'F'), copied)},
            'fallback_evidence_path': (str(args.fallback_evidence)
                                       if getattr(args, 'fallback_evidence', None) else None),
            'fallback_checks': fallback_receipt['checks'],
            'dependency_path': str(dependency),
            'service_lifecycle_trace': process_manager.rows,
            'logs': [str(path) for path in sorted(logs.glob('*.log'))],
        }
        if not result['same_store_rooms']:
            raise FixtureRefusal('same-store Rooms assertions were not emitted')
    except BaseException as exc:
        failure = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        if process_manager:
            try:
                process_manager.stop_all()
            except Exception as exc:
                cleanup_errors.append(str(exc))
        runtime_store_removed = (_remove_runtime_root(temp_root, cleanup_errors)
                                 if temp_root is not None else True)
        receipt = result or {'mode': 'fixture-process', 'fixture_only': True}
        receipt['status'] = 'passed' if failure is None and not cleanup_errors else 'failed'
        if failure:
            receipt['failure'] = failure
        if cleanup_errors:
            receipt['cleanup_errors'] = cleanup_errors
        receipt['runtime_store_removed'] = runtime_store_removed
        report_path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + '\n')
        if cleanup_errors and failure is None:
            raise FixtureRefusal('fixture cleanup failed; receipt recorded at '
                                 f'{report_path}: ' + '; '.join(cleanup_errors))
    result['receipt_path'] = str(report_path)
    return result


def _remove_runtime_root(root, errors):
    root = Path(root)
    try:
        # Restrict cleanup to a real, owned temporary root. This rejects
        # symlinked path components before resolving them and excludes the
        # operational tree.
        root = _reject_operational(root)
        os.chmod(root, 0o700)
        for current, directories, _files in os.walk(root, topdown=True, followlinks=False):
            parent = Path(current)
            for name in list(directories):
                child = parent / name
                try:
                    mode = child.lstat().st_mode
                except FileNotFoundError:
                    directories.remove(name)
                    continue
                if stat.S_ISLNK(mode):
                    # Never traverse or chmod a symlink, even if it points
                    # back into the fixture root.
                    directories.remove(name)
                    continue
                if not stat.S_ISDIR(mode):
                    directories.remove(name)
                    continue
                if not mode & stat.S_IWUSR or not mode & stat.S_IXUSR:
                    os.chmod(child, 0o700, follow_symlinks=False)
        shutil.rmtree(root)
    except Exception as exc:
        errors.append(f'runtime cleanup failed: {type(exc).__name__}: {exc}')
    removed = not root.exists() and not root.is_symlink()
    if not removed and not any(message.startswith('runtime cleanup failed:') for message in errors):
        errors.append('runtime cleanup failed: fixture root still exists')
    return removed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('inert-validation', 'fixture-process'), default='inert-validation')
    parser.add_argument('--previous', required=True, type=Path)
    parser.add_argument('--candidate', required=True, type=Path)
    parser.add_argument('--fallback', required=True, type=Path)
    parser.add_argument('--fallback-evidence', type=Path,
                        help='owned fixture-only external receipt from executed artifact-bound fallback assertions')
    parser.add_argument('--dependency-path', type=Path)
    parser.add_argument('--inject-candidate-verification-failure', action='store_true')
    parser.add_argument('--inject-candidate-interruption', action='store_true')
    args = parser.parse_args(argv)

    if args.mode == 'fixture-process':
        inherited = [key for key in os.environ if key.startswith(('HBOX_', 'WORKSHOP_', 'HOMEBOX_WEB_'))]
        if inherited:
            parser.error('inherited HBOX endpoint configuration is refused in fixture-process mode')
    try:
        paths = tuple(_reject_operational(path) for path in
                      (args.previous, args.candidate, args.fallback))
    except (FixtureRefusal, OSError) as exc:
        parser.error(str(exc))
    if len(set(paths)) != 3:
        parser.error('previous, candidate and fallback bundles must differ')
    if args.mode == 'fixture-process' and args.dependency_path is None:
        parser.error('fixture-process requires an explicit installed --dependency-path')
    if args.fallback_evidence is not None:
        if args.mode != 'fixture-process':
            parser.error('--fallback-evidence requires fixture-process mode')
        try:
            args.fallback_evidence = _owned_fixture_evidence(args.fallback_evidence)
        except (FixtureRefusal, OSError) as exc:
            parser.error(str(exc))
    dependency = None
    if args.mode == 'fixture-process':
        try:
            dependency = _owned_dependency(args.dependency_path)
        except (FixtureRefusal, OSError) as exc:
            parser.error(str(exc))
    if args.mode == 'inert-validation' and (args.inject_candidate_interruption
            or args.inject_candidate_verification_failure):
        parser.error('failure injection requires fixture-process mode and artifact-bound fallback checks')

    # No project package is imported until endpoint and path guards have passed.
    api = _load_bundle_api()
    if args.inject_candidate_verification_failure and args.inject_candidate_interruption:
        raise api[1]('select one failure injection at a time')
    try:
        if args.mode == 'fixture-process':
            report = _run_fixture_process(args, paths, dependency, api)
        else:
            report = _inert_validation(args, paths, api)
    except FixtureRefusal as exc:
        parser.error(str(exc))
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
