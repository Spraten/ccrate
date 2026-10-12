#!/usr/bin/env python3
"""Stage immutable public desktop fixtures and verify room editing in Chromium.

This is a disposable-browser fixture harness. Its bundles are not deployable releases.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import re
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[1]
PURPOSE = 'disposable-browser-fixture-v1'
TASK5_RUNTIME_DELTAS = {
    'kiosk/index.html', 'kiosk/workshop-ui.js', 'kiosk/workflow-ui.js',
    'deploy/kiosk-server.py',
}
QUEUE = pathlib.Path('/home/user/Desktop/inventory-system/work/queue-coordinator')
CANONICAL_RECEIPT = 'shelf-checks-canonical-build-receipt.json'
CANONICAL_RECEIPT_SHA256 = '141a8040b2d0867cd98f319ae6ada1bf04b83b5112298461d3a7f9df8ec47bf2'
SEALED_NATIVE_SHA256 = 'e8502bd85b18ff14d67172dffb0006e06504eddbe38a7c3d643bdee2088dd15a'
HISTORICAL_RECEIPT = QUEUE / 'map-task6-frontend-build_attempt2-receipt.json'
HISTORICAL_INPUTS = QUEUE / 'map-task6-frontend-build_attempt2-input-manifest.json'
HISTORICAL_STATIC = QUEUE / 'map-task6-frontend-build_attempt2-static-manifest.json'


def digest(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def static_output_matches(path: pathlib.Path, row: dict, *, require_mode: bool) -> bool:
    """Bind static bytes/size; accept absent historical mode but never a conflicting mode."""
    if not isinstance(row, dict) or path.is_symlink() or not path.is_file():
        return False
    actual_mode = stat.S_IMODE(path.stat().st_mode)
    declared_mode = row.get('mode')
    return (digest(path) == row.get('sha256') and path.stat().st_size == row.get('size') and
            (declared_mode is not None or not require_mode) and
            (declared_mode is None or declared_mode == actual_mode))


def tracked_public(source: pathlib.Path) -> list[pathlib.Path]:
    source = source.resolve(strict=True)
    excluded = {'profiles', 'private', 'backups', 'cache'}
    allowed_kiosk = {'.py', '.js', '.css', '.html', '.svg'}
    paths = []
    def fail_walk(error):
        raise error
    for top in ('ops', 'kiosk'):
        root = source / top
        if not root.is_dir() or root.is_symlink():
            raise ValueError('Runtime source root is missing or a symlink: ' + top)
        for directory, dirs, files in os.walk(root, followlinks=False, onerror=fail_walk):
            base = pathlib.Path(directory)
            rel_dir = base.relative_to(source)
            if any(part in excluded for part in rel_dir.parts):
                dirs[:] = []
                continue
            for name in list(dirs):
                child = base / name
                if name in excluded:
                    dirs.remove(name)
                elif child.is_symlink():
                    raise ValueError('Runtime source closure contains a symlink: ' + child.relative_to(source).as_posix())
            for name in files:
                path = base / name
                rel = path.relative_to(source)
                if path.is_symlink():
                    raise ValueError('Runtime source closure contains a symlink: ' + rel.as_posix())
                if not path.is_file() or not path.resolve(strict=True).is_relative_to(source):
                    raise ValueError('Runtime source closure contains a non-file or escaping path: ' + rel.as_posix())
                if (top == 'ops' and path.suffix == '.py') or (top == 'kiosk' and path.suffix in allowed_kiosk):
                    paths.append(path)
    for name in ('deploy/kiosk-server.py', 'deploy/workshop-gateway.py'):
        path = source / name
        if path.is_symlink():
            raise ValueError('Runtime source closure contains a symlink: ' + name)
        if path.is_file():
            if not path.resolve(strict=True).is_relative_to(source):
                raise ValueError('Runtime source closure contains an escaping path: ' + name)
            paths.append(path)
    label_documents = source / 'label-ui/src/starter-documents.json'
    if (label_documents.is_symlink() or not label_documents.is_file() or
            label_documents.resolve(strict=True) != label_documents or
            not label_documents.resolve(strict=True).is_relative_to(source)):
        raise ValueError('Runtime source closure is missing or has an unsafe label starter document.')
    paths.append(label_documents)
    return sorted(set(paths))


def evidence_file(path: pathlib.Path, *, source: pathlib.Path | None = None) -> pathlib.Path:
    path = path.absolute()
    if path.is_symlink():
        raise ValueError('Build evidence must be a direct public coordinator file.')
    path = path.resolve(strict=True)
    if (source is not None and path == source.resolve(strict=True) / 'work/queue-coordinator' / CANONICAL_RECEIPT
            and path.is_file() and digest(path) == CANONICAL_RECEIPT_SHA256):
        return path
    if path.parent != QUEUE.resolve(strict=True) or not path.is_file():
        raise ValueError('Build evidence must be a direct file in the public coordinator scratch directory.')
    return path


def _safe_tree_files(root: pathlib.Path) -> dict[str, pathlib.Path]:
    """Return regular files while rejecting symlinks anywhere in the tree."""
    found = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        base = pathlib.Path(directory)
        if any((base / name).is_symlink() for name in dirs + files):
            raise ValueError('Build source/output contains a symlink.')
        dirs[:] = sorted(dirs)
        for name in files:
            path = base / name
            found[path.relative_to(root).as_posix()] = path
    return found


def canonical_build_provenance(source: pathlib.Path, public: pathlib.Path,
                               receipt_path: pathlib.Path) -> tuple[str, dict, dict, dict]:
    """Validate the accepted canonical receipt's embedded source and output manifests."""
    source = source.resolve(strict=True)
    receipt_path = evidence_file(receipt_path, source=source)
    if receipt_path.name != CANONICAL_RECEIPT or digest(receipt_path) != CANONICAL_RECEIPT_SHA256:
        raise ValueError('Canonical build receipt is not the accepted pinned receipt.')
    receipt = json.loads(receipt_path.read_text())
    if (not isinstance(receipt, dict) or receipt.get('exit_code') != 0 or receipt.get('deployed') is not False or
            receipt.get('upstream_pin') != 'e01dd737238a3fa7e1a6454b37de6c6fc88c86e4' or
            receipt.get('expected_upstream_pin') != receipt.get('upstream_pin') or
            receipt.get('overlay_identical_to_canonical') is not True or
            'typecheck added no diagnostics' not in receipt.get('result', '').lower()):
        raise ValueError('Canonical build receipt does not prove the accepted pinned build.')
    inputs = receipt.get('source_inputs')
    if not isinstance(inputs, dict) or len(inputs) != 5:
        raise ValueError('Canonical build receipt has a malformed source input manifest.')
    for name, row in inputs.items():
        relative = pathlib.PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or not isinstance(row, dict):
            raise ValueError('Canonical build receipt contains an unsafe source input path.')
        path = source.joinpath(*relative.parts)
        expected = row.get('canonical_sha256')
        if (row.get('matches') is not True or row.get('isolated_sha256') != expected or
                path.resolve(strict=True) != path or path.is_symlink() or not path.is_file() or digest(path) != expected):
            raise ValueError('Canonical build source input changed: ' + name)
    pin = json.loads((source / 'homebox-ui/upstream-typecheck.json').read_text())
    if pin.get('pin') != receipt['upstream_pin']:
        raise ValueError('Canonical build source has a different pinned upstream baseline.')
    overlay = receipt.get('overlay_manifest')
    if not isinstance(overlay, list) or len(overlay) != receipt.get('overlay_source_files'):
        raise ValueError('Canonical build receipt has a malformed overlay manifest.')
    overlay_paths = set()
    for row in overlay:
        if not isinstance(row, dict) or not isinstance(row.get('path'), str):
            raise ValueError('Canonical build receipt has a malformed overlay entry.')
        name = row['path']
        relative = pathlib.PurePosixPath(name)
        if (relative.is_absolute() or '..' in relative.parts or not name.startswith('homebox-ui/overlay/') or
                name in overlay_paths):
            raise ValueError('Canonical build receipt has an unsafe or duplicate overlay path.')
        overlay_paths.add(name)
        path = source.joinpath(*relative.parts)
        if path.is_symlink() or not path.is_file() or digest(path) != row.get('sha256'):
            raise ValueError('Canonical overlay source changed: ' + name)
    overlay_root = source / 'homebox-ui/overlay'
    if overlay_root.is_symlink():
        raise ValueError('Canonical overlay root is a symlink.')
    actual_overlay = _safe_tree_files(overlay_root)
    if {'homebox-ui/overlay/' + name for name in actual_overlay} != overlay_paths:
        raise ValueError('Canonical overlay membership changed.')

    rows = receipt.get('output_manifest')
    if not isinstance(rows, list) or len(rows) != receipt.get('output', {}).get('file_count'):
        raise ValueError('Canonical build receipt has a malformed output manifest.')
    outputs = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('path'), str):
            raise ValueError('Canonical build receipt has a malformed output entry.')
        name = row['path']
        relative = pathlib.PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or name in outputs:
            raise ValueError('Canonical build receipt has an unsafe or duplicate output path.')
        outputs[name] = {'sha256': row.get('sha256'), 'size': row.get('bytes')}
    if public.is_symlink():
        raise ValueError('Canonical build output root is a symlink.')
    public = public.resolve(strict=True)
    actual = _safe_tree_files(public)
    if set(actual) != set(outputs):
        raise ValueError('Canonical build output membership differs from its receipt.')
    for name, row in outputs.items():
        path = actual[name]
        if digest(path) != row['sha256'] or path.stat().st_size != row['size']:
            raise ValueError('Canonical build output changed: ' + name)
    if sum(row['size'] for row in outputs.values()) != receipt.get('output', {}).get('bytes'):
        raise ValueError('Canonical build output byte count differs from its receipt.')
    return 'accepted-canonical-build', receipt, inputs, outputs


def build_provenance(source: pathlib.Path, public: pathlib.Path, binary: pathlib.Path,
                     receipt_path: pathlib.Path, input_path: pathlib.Path | None,
                     static_path: pathlib.Path | None, *, allowed_source_deltas=()) -> tuple[str, dict, dict, dict]:
    source = source.resolve(strict=True)
    if source != ROOT.resolve(strict=True):
        raise ValueError('Build provenance source must be the approved isolated worktree.')
    receipt_path = evidence_file(receipt_path, source=source)
    if receipt_path.name == CANONICAL_RECEIPT and digest(receipt_path) == CANONICAL_RECEIPT_SHA256:
        if input_path is not None or static_path is not None:
            raise ValueError('Accepted canonical receipt embeds its own exact input and output manifests.')
        provenance, receipt, inputs, static = canonical_build_provenance(source, public, receipt_path)
        if (binary.is_symlink() or not binary.is_file() or stat.S_IMODE(binary.stat().st_mode) != 0o555 or
                digest(binary) != SEALED_NATIVE_SHA256):
            raise ValueError('Canonical build fixture is not paired with the accepted sealed native binary.')
        return provenance, receipt, inputs, static
    if input_path is None or static_path is None:
        raise ValueError('Historical and fresh builds require both separate exact manifests.')
    input_path = evidence_file(input_path)
    static_path = evidence_file(static_path)
    receipt = json.loads(receipt_path.read_text())
    inputs = json.loads(input_path.read_text())
    static = json.loads(static_path.read_text())
    if not isinstance(inputs, dict) or not inputs or not isinstance(static, dict) or not static:
        raise ValueError('Build provenance needs non-empty exact input and static manifests.')
    historical = receipt.get('head') == '661bea7222c6f9e1c419b30d8e63cbc0e4088f43'
    if (receipt.get('kind') != 'build' or receipt.get('exit_code') != 0 or
            receipt.get('source_before_after_exact') is not True or
            receipt.get('builder_before_after_exact') is not True or
            (not historical and receipt.get('static_manifest_after_build_exact') not in (None, True)) or
            receipt.get('head_before_after_exact') is not True or
            receipt.get('native_before_after_exact') is not True or
            receipt.get('dependencies_before_after_exact') is not True or
            receipt.get('timed_out') is not False):
        raise ValueError('Build receipt does not prove a complete exact successful build.')
    if receipt.get('builder_inputs') != len(inputs) or receipt.get('static_files') != len(static):
        raise ValueError('Build receipt input/static counts do not match the exact manifests.')
    if (receipt.get('-input-manifest.json') != {'path': str(input_path), 'sha256': digest(input_path)} or
            receipt.get('-static-manifest.json') != {'path': str(static_path), 'sha256': digest(static_path)}):
        raise ValueError('Build receipt does not bind the supplied input and static manifests.')
    source_entries = {name.removeprefix('source/'): {'sha256': row.get('sha256'), 'mode': row.get('mode')}
                      for name, row in inputs.items() if name.startswith('source/')}
    receipt_entries = {name: {'sha256': row.get('sha256'), 'mode': row.get('mode')}
                       for name, row in receipt.get('source_entries', {}).items()}
    if source_entries != receipt_entries:
        raise ValueError('Build receipt source entries differ from the complete input manifest.')
    if not historical:
        for name, row in inputs.items():
            relative = pathlib.PurePosixPath(name)
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('Build input manifest contains an escaping path: ' + name)
            if name.startswith('source/'):
                path = source / name.removeprefix('source/')
            elif name.startswith('upstream/frontend/'):
                path = source / 'upstream/homebox/frontend' / name.removeprefix('upstream/frontend/')
            else:
                raise ValueError('Build input path is outside the reviewed source/frontend roots: ' + name)
            if (not path.is_file() or path.is_symlink() or row.get('symlink') is not False):
                raise ValueError('Build input bytes, mode or size changed: ' + name)
            if name.startswith('source/') and name.removeprefix('source/') in allowed_source_deltas:
                continue
            if (digest(path) != row.get('sha256') or stat.S_IMODE(path.stat().st_mode) != row.get('mode') or
                    path.stat().st_size != row.get('size')):
                raise ValueError('Build input bytes, mode or size changed: ' + name)
    actual = {path.relative_to(public).as_posix(): path for path in public.rglob('*') if path.is_file()}
    if set(actual) != set(static):
        raise ValueError('Built public membership differs from its exact static manifest.')
    for name, row in static.items():
        path = actual[name]
        if not static_output_matches(path, row, require_mode=not historical):
            raise ValueError('Built public output differs from its exact static manifest: ' + name)
    if (not binary.is_file() or stat.S_IMODE(binary.stat().st_mode) != receipt.get('native', {}).get('mode') or
            binary.stat().st_size != receipt.get('native', {}).get('size') or
            digest(binary) != receipt.get('native', {}).get('sha256')):
        raise ValueError('Built frontend receipt is not bound to the selected sealed native binary.')
    summary = receipt.get('typecheck_summary')
    if not isinstance(summary, list) or not any('43' in str(row) and 'no added diagnostics' in str(row).lower()
                                                 for row in summary):
        raise ValueError('Build receipt does not pin the accepted 43-old/0-new typecheck baseline.')
    if historical:
        bindings = ((receipt_path, 'd8bd1204902bd9ebf86d239b7a6368cf465324cb53dea3308ea20e63eb640001'),
                    (input_path, 'd0055093cc44dbf166a2c5bd1845632145d25bf9d8bb8b79b8814ddbf69c870e'),
                    (static_path, '6d905ed4f0336ae5ce8947c4c96054384ab3a117989d7d85b4885f15a2c00cc2'))
        if any(digest(path) != expected for path, expected in bindings) or len(static) != 179 or len(inputs) != 472:
            raise ValueError('Historical Stage1 predecessor no longer matches its accepted evidence.')
        provenance = 'historical-stage1-predecessor'
    else:
        if not receipt.get('head'):
            raise ValueError('Fresh Rooms build must declare the source HEAD captured by its receipt.')
        provenance = 'fresh-rooms-build'
    return provenance, receipt, inputs, static


def stage_fixture_bundle(destination: pathlib.Path, *, source: pathlib.Path,
                         public: pathlib.Path, binary: pathlib.Path,
                         receipt_path: pathlib.Path, input_manifest_path: pathlib.Path | None,
                        static_manifest_path: pathlib.Path | None, terminal_runtime: bool = False) -> None:
    """Copy only tracked public runtime code and a matched public build."""
    if destination.exists() or destination.is_symlink():
        raise ValueError('Fixture destination must be absent and owned by this staging run.')
    if source.is_symlink() or public.is_symlink():
        raise ValueError('Fixture source and public output must not be symlinks.')
    source = source.resolve(strict=True)
    public = public.resolve(strict=True)
    binary = binary.resolve(strict=True)
    receipt_path = evidence_file(receipt_path, source=source)
    if receipt_path.name != CANONICAL_RECEIPT or digest(receipt_path) != CANONICAL_RECEIPT_SHA256:
        input_manifest_path = evidence_file(input_manifest_path) if input_manifest_path is not None else None
        static_manifest_path = evidence_file(static_manifest_path) if static_manifest_path is not None else None
    allowed_deltas = TASK5_RUNTIME_DELTAS if terminal_runtime else set()
    if not public.is_dir() or not (public / 'index.html').is_file():
        raise ValueError('Explicit public build must contain index.html.')
    if not public.is_relative_to(source):
        raise ValueError('Public build must be inside the approved isolated worktree.')
    provenance, receipt, input_manifest, static_manifest = build_provenance(
        source, public, binary, receipt_path, input_manifest_path, static_manifest_path,
        allowed_source_deltas=allowed_deltas)
    if not (binary.is_file() and binary.stat().st_mode & 0o777 == 0o555):
        raise ValueError('Preserved native fixture must be an immutable 0555 file.')
    sources = tracked_public(source)
    if any(path.is_symlink() or not path.is_file() for path in sources):
        raise ValueError('Runtime source closure contains a symlink or non-file.')
    public_bytes = sum(path.stat().st_size for path in public.rglob('*') if path.is_file())
    source_bytes = sum(path.stat().st_size for path in sources)
    if source_bytes + public_bytes > 12 * 1024 * 1024:
        raise ValueError('Public fixture copy exceeds the reviewed 12 MiB staging ceiling.')
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if shutil.disk_usage(destination.parent).free - source_bytes - public_bytes < 749 * 1024 * 1024:
        raise ValueError('Fixture staging would consume the reviewed 749 MiB free-space reserve.')
    entries: dict[str, dict[str, object]] = {}
    destination.mkdir(mode=0o700, parents=True)
    try:
        for src in sources:
            rel = src.relative_to(source)
            target = destination / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target, follow_symlinks=False)
            entries[rel.as_posix()] = {'sha256': digest(target), 'mode': stat.S_IMODE(target.stat().st_mode)}
        public_target = destination / 'public'
        shutil.copytree(public, public_target, symlinks=False)
        for path in sorted(p for p in public_target.rglob('*') if p.is_file()):
            rel = path.relative_to(destination).as_posix()
            entries[rel] = {'sha256': digest(path), 'mode': stat.S_IMODE(path.stat().st_mode)}
        native_target = destination / 'native' / 'homebox'
        native_target.parent.mkdir(parents=True)
        native_target.symlink_to(binary)
        manifest = {
            'purpose': PURPOSE,
            'not_rollout_evidence': True,
            'verifier_path': str(pathlib.Path(__file__).resolve(strict=True)),
            'verifier_sha256': digest(pathlib.Path(__file__).resolve(strict=True)),
            'ui_provenance': provenance,
            'terminal_runtime_deltas': sorted(allowed_deltas) if terminal_runtime else [],
            'source_root': str(source),
            'runtime_source_head': subprocess.run(['git', '-C', str(source), 'rev-parse', 'HEAD'],
                                                   check=True, capture_output=True, text=True).stdout.strip(),
            'ui_source_head': receipt.get('head', receipt.get('isolated_head')),
            'build_receipt_sha256': digest(receipt_path),
            'build_receipt_path': str(receipt_path),
            'known_browser_diagnostics': [],
            'diagnostics': receipt.get('typecheck_summary'),
            'native': {'path': 'native/homebox', 'target': str(binary), 'sha256': digest(binary), 'mode': 0o555},
            'members': entries,
        }
        if input_manifest_path is not None and static_manifest_path is not None:
            manifest.update(input_manifest_sha256=digest(input_manifest_path),
                            static_manifest_sha256=digest(static_manifest_path),
                            input_manifest_path=str(input_manifest_path),
                            static_manifest_path=str(static_manifest_path))
        (destination / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')
        validate_candidate(destination)
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def tree_hash(root: pathlib.Path) -> str:
    rows = []
    for path in sorted(p for p in root.rglob('*') if p.is_file() and not p.is_symlink()):
        rows.append((path.relative_to(root).as_posix(), stat.S_IMODE(path.stat().st_mode), digest(path)))
    return hashlib.sha256(json.dumps(rows, separators=(',', ':')).encode()).hexdigest()


def validate_candidate(candidate: pathlib.Path) -> dict:
    candidate = candidate.resolve(strict=True)
    manifest_path = candidate / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    if manifest.get('purpose') != PURPOSE or manifest.get('not_rollout_evidence') is not True:
        raise ValueError('Candidate is not a declared disposable browser fixture.')
    verifier_path = pathlib.Path(manifest.get('verifier_path', '')).resolve(strict=True)
    if (verifier_path != (ROOT / 'deploy/verify-workshop-rooms.py').resolve(strict=True) or
            manifest.get('verifier_sha256') != digest(verifier_path)):
        raise ValueError('Candidate is not bound to the current exact Rooms verifier.')
    expected = manifest.get('members')
    if not isinstance(expected, dict) or not expected:
        raise ValueError('Candidate manifest has no exact public membership.')
    native = manifest.get('native', {})
    if set(p.relative_to(candidate).as_posix() for p in candidate.rglob('*') if p.is_symlink()) != {native.get('path')}:
        raise ValueError('Candidate contains an undeclared or missing symlink.')
    forbidden = {'profiles', 'private', 'backups', 'credentials', 'database', 'cache', 'node_modules'}
    if any(forbidden & set(pathlib.PurePosixPath(rel).parts) for rel in expected):
        raise ValueError('Candidate manifest includes private or mutable runtime data.')
    actual = {p.relative_to(candidate).as_posix() for p in candidate.rglob('*')
              if p.is_file() and not p.is_symlink() and p != manifest_path}
    if actual != set(expected):
        raise ValueError('Candidate membership differs from its manifest.')
    for rel, binding in expected.items():
        path = candidate / rel
        if path.is_symlink() or not path.is_file() or digest(path) != binding.get('sha256') or stat.S_IMODE(path.stat().st_mode) != binding.get('mode'):
            raise ValueError('Candidate file failed its hash or mode binding: ' + rel)
    link = candidate / native.get('path', '')
    target = pathlib.Path(native.get('target', '')).resolve(strict=True)
    sealed = ROOT / 'work/homebox-bin/homebox'
    if (not link.is_symlink() or link.resolve(strict=True) != target or target != sealed.resolve(strict=True) or
            digest(target) != 'e8502bd85b18ff14d67172dffb0006e06504eddbe38a7c3d643bdee2088dd15a' or
            manifest.get('native', {}).get('sha256') != digest(target) or stat.S_IMODE(target.stat().st_mode) != 0o555):
        raise ValueError('Candidate native binding does not match the sealed fixture binary.')
    if not (candidate / 'public/index.html').is_file():
        raise ValueError('Candidate public application is missing.')
    if (manifest.get('ui_provenance') not in {'historical-stage1-predecessor', 'fresh-rooms-build',
                                              'accepted-canonical-build'} or
            not isinstance(manifest.get('known_browser_diagnostics'), list)):
        raise ValueError('Candidate UI/build provenance or diagnostic allowlist is missing.')
    source_root = pathlib.Path(manifest.get('source_root', '')).resolve(strict=True)
    receipt_path = pathlib.Path(manifest.get('build_receipt_path', ''))
    input_path = pathlib.Path(manifest['input_manifest_path']) if manifest.get('input_manifest_path') else None
    static_path = pathlib.Path(manifest['static_manifest_path']) if manifest.get('static_manifest_path') else None
    runtime_deltas = manifest.get('terminal_runtime_deltas', [])
    if not isinstance(runtime_deltas, list) or set(runtime_deltas) - TASK5_RUNTIME_DELTAS:
        raise ValueError('Candidate declares an unapproved runtime input delta.')
    provenance, _, _, static = build_provenance(
        source_root, candidate / 'public', target, receipt_path, input_path, static_path,
        allowed_source_deltas=runtime_deltas)
    receipt = json.loads(receipt_path.read_text())
    if (provenance != manifest['ui_provenance'] or
            manifest.get('ui_source_head') != receipt.get('head', receipt.get('isolated_head')) or
            manifest.get('build_receipt_sha256') != digest(receipt_path) or
            (input_path is not None and manifest.get('input_manifest_sha256') != digest(input_path)) or
            (static_path is not None and manifest.get('static_manifest_sha256') != digest(static_path))):
        raise ValueError('Candidate UI artifact is not bound to its exact build evidence.')
    ui_actual = {name.removeprefix('public/'): binding for name, binding in expected.items()
                 if name.startswith('public/')}
    if set(ui_actual) != set(static) or any(
            ui_actual[name].get('sha256') != row.get('sha256') or
            ('mode' in row and ui_actual[name].get('mode') != row['mode']) or
            ui_actual[name].get('size', (candidate / 'public' / name).stat().st_size) != row.get('size')
            for name, row in static.items()):
        raise ValueError('Candidate public bytes or modes differ from the exact build manifest.')
    return manifest


def test_desktop_room_drafts(page, fixture) -> None:
    """Exercise the planner, per-room drafts and recovery through visible controls."""
    def accept_one_dialog(target_page, action) -> list[str]:
        observed_messages: list[str] = []
        def accept(dialog):
            observed_messages.append(dialog.message)
            dialog.accept()
        try:
            with target_page.expect_event('dialog') as dialog_event:
                target_page.once('dialog', accept)
                action()
        except Exception as error:
            if type(error).__name__ != 'TimeoutError':
                raise
            raise AssertionError(f'Expected one confirm dialog; observed messages: {observed_messages!r}') from error
        assert observed_messages == [dialog_event.value.message]
        return observed_messages

    workshop_view_requests = []
    workshop_view_responses = []
    workshop_view_events = []
    page.on('request', lambda request: (workshop_view_requests.append(request.url),
            workshop_view_events.append({'event': 'request', 'at_ns': time.monotonic_ns(),
                                         'url': request.url})
            ) if '/workshop-api/workshop/view?' in request.url else None)
    page.on('response', lambda response: (workshop_view_responses.append(response),
            workshop_view_events.append({'event': 'response', 'at_ns': time.monotonic_ns(),
                                         'status': response.status, 'url': response.url})
            ) if '/workshop-api/workshop/view?' in response.url else None)
    page.get_by_role('heading', name='Workshop & storage').wait_for()
    picker = page.get_by_role('combobox', name='Workshop room', exact=True)
    second = fixture['second_page']
    picker.wait_for()
    page.get_by_role('region', name='Object palette', exact=True).wait_for()
    canvas = page.get_by_role('region', name='Room plan canvas', exact=True)
    canvas.wait_for()
    plan = page.locator('[data-planner-canvas="true"]')
    inspector = page.get_by_role('region', name='Workshop inspector', exact=True)
    inspector.wait_for()
    assert canvas.bounding_box()['width'] > inspector.bounding_box()['width']
    assert page.get_by_role('region', name='Object palette', exact=True).bounding_box()['x'] < canvas.bounding_box()['x']
    # Global native search is reachable from the fresh Browse view without
    # opening the longer coverage disclosure. Keyboard selection must not edit
    # the room document or its revision.
    quick_before = fixture['document'](page)
    quick_search = page.get_by_role('searchbox', name='Search native records', exact=True)
    quick_search.fill('Fixture photo shelf')
    quick_result = page.locator('.planner-quick-search .workshop-search-results').get_by_role(
        'button', name=re.compile('Fixture photo shelf'))
    quick_result.wait_for()
    quick_result.focus()
    page.keyboard.press('Enter')
    inspector.get_by_role('heading', name='Fixture photo shelf', exact=True).wait_for()
    assert inspector.get_by_role('link', name='Open in C-Crate', exact=True).get_attribute('href') == (
        '/location/' + fixture['shelf_id'])
    assert not page.locator('details.planner-coverage').evaluate('(element) => element.open')
    assert fixture['document'](page) == quick_before
    page.goto(fixture['gateway_url'] + '/workshop/map', wait_until='domcontentloaded')
    picker.wait_for()
    plan = page.locator('[data-planner-canvas="true"]')
    inspector = page.get_by_role('region', name='Workshop inspector', exact=True)
    page.get_by_role('button', name='Edit', exact=True).click()

    # Opening a legacy single-room record must preserve its exact coordinates;
    # simply displaying and changing the snap preference must not quantize it.
    legacy_width = page.get_by_label('Room width in feet', exact=True)
    legacy_depth = page.get_by_label('Room depth in feet', exact=True)
    assert legacy_width.input_value() == '17.13'
    assert legacy_depth.input_value() == '15.27'
    page.get_by_label('Snap to quarter-foot grid', exact=True).uncheck()
    page.get_by_label('Snap to quarter-foot grid', exact=True).check()
    assert legacy_width.input_value() == '17.13'
    assert legacy_depth.input_value() == '15.27'
    legacy_room_id = picker.input_value()
    page.get_by_role('button', name='Rack', exact=True).click()
    legacy_plan = page.locator('[data-planner-canvas="true"]')
    legacy_box = legacy_plan.bounding_box()
    page.mouse.click(legacy_box['x'] + legacy_box['width'] * .94,
                     legacy_box['y'] + legacy_box['height'] * .92)
    legacy_drawing = page.locator('[data-workshop-drawing].is-selected')
    legacy_drawing.wait_for()
    legacy_geometry = {key: float(legacy_drawing.get_attribute('data-' + key))
                       for key in ('x', 'y', 'width', 'height')}
    assert legacy_geometry['x'] + legacy_geometry['width'] <= 17.13
    assert legacy_geometry['y'] + legacy_geometry['height'] <= 15.27
    page.get_by_role('button', name='Room settings', exact=True).click()
    assert page.get_by_label('Room width in feet', exact=True).input_value() == '17.13'
    assert page.get_by_label('Room depth in feet', exact=True).input_value() == '15.27'
    page.get_by_role('button', name='Drawing settings', exact=True).click()
    remove_drawing_messages = accept_one_dialog(
        page, lambda: page.get_by_role('button', name='Remove drawing only', exact=True).click())
    assert remove_drawing_messages == ['Remove this drawing? Its native location and inventory will remain.']
    page.get_by_role('button', name='Remove room', exact=True).click()
    page.get_by_role('dialog', name='Remove room', exact=True).get_by_role(
        'button', name='Remove room', exact=True).click()
    assert legacy_room_id not in page.locator('select[aria-label="Workshop room"] option').evaluate_all(
        'rows => rows.map(row => row.value)')
    untouched_legacy = fixture['document'](page)
    assert untouched_legacy['revision'] == fixture['legacy_revision']
    legacy_row = untouched_legacy['document']['rooms'][0]
    assert (legacy_row['width'], legacy_row['height']) == (17.13, 15.27)
    # Removing the last empty room must not hide the native Browse result.
    empty_plan_server_before = fixture['document'](page)
    empty_plan_draft_before = fixture['draft_state'](page)
    assert empty_plan_draft_before['document']['rooms'] == []
    page.get_by_role('button', name='Browse', exact=True).click()
    empty_search = page.get_by_role('searchbox', name='Search native records', exact=True)
    empty_search.fill('Fixture photo shelf')
    empty_result = page.locator('.planner-quick-search .workshop-search-results').get_by_role(
        'button', name=re.compile('Fixture photo shelf'))
    empty_result.wait_for()
    empty_result.focus()
    page.keyboard.press('Enter')
    inspector = page.get_by_role('region', name='Workshop inspector', exact=True)
    inspector.get_by_role('heading', name='Fixture photo shelf', exact=True).wait_for()
    assert inspector.get_by_role('navigation', name='Native storage path', exact=True).count() == 1
    assert inspector.get_by_role('link', name='Open in C-Crate', exact=True).get_attribute('href') == (
        '/location/' + fixture['shelf_id'])
    assert fixture['document'](page) == empty_plan_server_before
    assert fixture['draft_state'](page) == empty_plan_draft_before
    page.get_by_role('button', name='Edit', exact=True).click()

    def create_room(title: str, root_id: str) -> str:
        page.get_by_role('button', name='New room', exact=True).click()
        page.get_by_label('Room title', exact=True).fill(title)
        page.get_by_label('Room width in feet', exact=True).fill('20')
        page.get_by_label('Room depth in feet', exact=True).fill('16')
        page.get_by_label('Native storage root', exact=True).select_option(root_id)
        page.get_by_role('button', name='Apply room changes', exact=True).click()
        picker.wait_for()
        options = page.locator('select[aria-label="Workshop room"] option').evaluate_all(
            "rows => rows.map(row => [row.value, row.textContent])")
        return next(value for value, label in options if title in label)

    fixture['room_one'] = create_room('Fixture room one', fixture['native_location_id'])
    fixture['room_two'] = create_room('Fixture room two', fixture['other_native_location_id'])
    fixture['room_three'] = create_room('Fixture transfer room', fixture['native_location_id'])
    with page.expect_response(lambda response: response.url.endswith('/workshop-api/workshop/save')) as initial_save:
        page.get_by_role('button', name='Save all room changes', exact=True).click()
    assert initial_save.value.status == 200
    fixture['revision'] = initial_save.value.json()['revision']
    picker.select_option(fixture['room_one'])
    fixture['second_page'].reload()
    fixture['second_page'].get_by_role('combobox', name='Workshop room', exact=True).wait_for()
    picker.select_option(fixture['room_one'])
    page.get_by_label('Room title', exact=True).fill('Fixture renamed room')
    page.get_by_role('button', name='Apply room changes', exact=True).click()
    page.get_by_role('button', name='Undo', exact=True).click()
    assert page.get_by_label('Room title', exact=True).input_value() == 'Fixture room one'
    page.get_by_role('button', name='Redo', exact=True).click()
    assert page.get_by_label('Room title', exact=True).input_value() == 'Fixture renamed room'
    assert fixture['native_location']('after') == fixture['native_name_before']

    fixture['room_one_pair'] = (fixture['room_one'], fixture['native_location_id'])
    page.get_by_role('button', name='Rack', exact=True).click()
    plan.click(position={'x': 160, 'y': 120})
    drawing_id = page.locator('[data-workshop-drawing].is-selected').get_attribute('data-workshop-drawing')
    assert drawing_id and drawing_id.count('-') == 4
    fixture['drawing_id'] = drawing_id
    page.get_by_label('Drawing caption', exact=True).fill('Fixture rack drawing')
    page.keyboard.press('Tab')
    page.get_by_role('button', name='Apply geometry', exact=True).click()
    drawing_control = page.get_by_role('button', name='Fixture rack drawing', exact=False)
    drawing_control.focus()
    page.keyboard.press('Enter')
    assert page.locator('[data-workshop-drawing].is-selected').get_attribute('data-workshop-drawing') == drawing_id
    assert page.get_by_label('Drawing caption', exact=True).input_value() == 'Fixture rack drawing'
    page.get_by_role('button', name='Room settings', exact=True).click()
    assert page.get_by_label('Room title', exact=True).input_value() == 'Fixture renamed room'
    page.get_by_label('Room title', exact=True).fill('Fixture settings reachable')
    page.keyboard.press('Tab')
    page.get_by_role('button', name='Apply room changes', exact=True).click()
    page.get_by_role('button', name='Undo', exact=True).click()
    assert page.get_by_label('Room title', exact=True).input_value() == 'Fixture renamed room'
    page.get_by_role('button', name='Redo', exact=True).click()
    assert page.get_by_label('Room title', exact=True).input_value() == 'Fixture settings reachable'
    page.get_by_label('Room title', exact=True).fill('Fixture renamed room')
    page.keyboard.press('Tab')
    page.get_by_role('button', name='Apply room changes', exact=True).click()
    page.get_by_role('button', name='Drawing settings', exact=True).click()
    assert page.get_by_label('Drawing caption', exact=True).input_value() == 'Fixture rack drawing'
    page.get_by_label('Native storage location', exact=True).select_option(fixture['native_location_id'])
    page.get_by_label('Drawing caption', exact=True).fill('Fixture rack drawing')
    numeric_x = page.get_by_label('Position X in feet', exact=True)
    numeric_x.focus(); page.keyboard.press('Control+a'); page.keyboard.type('3'); page.keyboard.press('Tab')
    assert numeric_x.input_value() == '3'
    page.get_by_label('Position Y in feet', exact=True).fill('4')
    page.get_by_label('Drawing width in feet', exact=True).fill('5')
    page.get_by_label('Drawing depth in feet', exact=True).fill('2')
    def wait_for_rotation(turns: int) -> None:
        page.wait_for_function('''args => {
          const input = document.querySelector('[aria-label="Rotation in quarter turns"]');
          const drawing = document.querySelector(`[data-workshop-drawing="${args.id}"]`);
          return input?.value === String(args.turns) && drawing?.dataset.rotation === String(args.turns * 90);
        }''', arg={'id': drawing_id, 'turns': turns})
    def wait_for_drawing_field(label: str, attribute: str, value: str) -> None:
        page.wait_for_function('''args => {
          const input = document.querySelector(`[aria-label="${args.label}"]`);
          const drawing = document.querySelector(`[data-workshop-drawing="${args.id}"]`);
          return input?.value === args.value && drawing?.dataset[args.attribute] === args.value;
        }''', arg={'id': drawing_id, 'label': label, 'attribute': attribute, 'value': value})
    page.get_by_role('button', name='Rotate clockwise 90 degrees', exact=True).click()
    wait_for_rotation(1)
    assert page.get_by_label('Rotation in quarter turns', exact=True).input_value() == '1'
    assert page.locator(f'[data-workshop-drawing="{drawing_id}"]').get_attribute('data-rotation') == '90'
    page.get_by_label('Drawing caption', exact=True).fill('Keyboard editing stays local')
    page.get_by_label('Drawing caption', exact=True).focus()
    page.keyboard.press('Control+z')
    assert page.get_by_label('Rotation in quarter turns', exact=True).input_value() == '1'
    page.get_by_label('Snap to quarter-foot grid', exact=True).check()
    page.get_by_role('button', name='Rotate clockwise 90 degrees', exact=True).click()
    wait_for_rotation(2)
    assert page.get_by_label('Rotation in quarter turns', exact=True).input_value() == '2'
    page.get_by_role('button', name='Undo', exact=True).click()
    wait_for_rotation(1)
    assert page.get_by_label('Rotation in quarter turns', exact=True).input_value() == '1'
    page.get_by_role('button', name='Redo', exact=True).click()
    wait_for_rotation(2)
    assert page.get_by_label('Rotation in quarter turns', exact=True).input_value() == '2'
    page.get_by_role('button', name='Workbench', exact=True).click()
    plan.click(position={'x': 300, 'y': 180})
    second_drawing_id = page.locator('[data-workshop-drawing].is-selected').get_attribute('data-workshop-drawing')
    assert second_drawing_id and second_drawing_id != drawing_id
    page.get_by_label('Native storage location', exact=True).select_option(fixture['native_location_id'])
    page.get_by_label('Drawing caption', exact=True).fill('Second representation')
    page.get_by_role('button', name='Workbench', exact=True).click()
    plan.click(position={'x': 340, 'y': 240})
    unlinked_drawing_id = page.locator('[data-workshop-drawing].is-selected').get_attribute('data-workshop-drawing')
    assert unlinked_drawing_id and unlinked_drawing_id not in {drawing_id, second_drawing_id}
    fixture['unlinked_drawing_id'] = unlinked_drawing_id
    assert page.get_by_label('Native storage location', exact=True).input_value() == ''
    with page.expect_response(lambda response: response.url.endswith('/workshop-api/workshop/save')) as planner_save:
        page.get_by_role('button', name='Save all room changes', exact=True).click()
    assert planner_save.value.status == 200
    planner_payload = planner_save.value.request.post_data_json
    assert {room['id'] for room in planner_payload['document']['rooms']} == {
        fixture['room_one'], fixture['room_two'], fixture['room_three']}
    assert next(obj for room in planner_payload['document']['rooms'] for obj in room['objects']
                if obj['id'] == drawing_id)['rotation'] == 180
    picker.select_option(fixture['room_three'])
    page.get_by_role('button', name='Rack', exact=True).click()
    plan.click(position={'x': 160, 'y': 120})
    third_drawing_id = page.locator('[data-workshop-drawing].is-selected').get_attribute('data-workshop-drawing')
    assert third_drawing_id and third_drawing_id not in {drawing_id, second_drawing_id}
    fixture['third_drawing_id'] = third_drawing_id
    page.get_by_label('Native storage location', exact=True).select_option(fixture['native_location_id'])
    page.get_by_label('Drawing caption', exact=True).fill('Cross-room search representation')
    page.keyboard.press('Tab')
    with page.expect_response(lambda response: response.url.endswith('/workshop-api/workshop/save')) as cross_room_representation_save:
        page.get_by_role('button', name='Save all room changes', exact=True).click()
    assert cross_room_representation_save.value.status == 200
    fixture['revision'] = cross_room_representation_save.value.json()['revision']
    # A room with no selected drawing still shows one native representation
    # chooser when a global search finds matches across the plan.
    page.get_by_role('button', name='Browse', exact=True).click()
    picker.select_option(fixture['room_two'])
    seeded_document = fixture['document'](page)['document']
    seeded_rooms = {room['id']: room for room in seeded_document['rooms']}
    expected_linked_drawings = {drawing_id, second_drawing_id, third_drawing_id}
    assert {obj['id'] for obj in seeded_rooms[fixture['room_one']]['objects']} >= {
        drawing_id, second_drawing_id}
    assert third_drawing_id in {obj['id'] for obj in seeded_rooms[fixture['room_three']]['objects']}
    assert all(obj['location_id'] == fixture['native_location_id']
               for room in seeded_rooms.values() for obj in room['objects']
               if obj['id'] in expected_linked_drawings)
    quick_search = page.get_by_role('searchbox', name='Search native records', exact=True)
    quick_search.fill('Fixture photo shelf')
    quick_result = page.locator('.planner-quick-search .workshop-search-results').get_by_role(
        'button', name=re.compile('Fixture photo shelf'))
    quick_result.wait_for()
    chooser_start = {
        'url': page.url,
        'room_picker': picker.input_value(),
        'selected_drawing': page.locator('[data-workshop-drawing].is-selected').get_attribute(
            'data-workshop-drawing') if page.locator('[data-workshop-drawing].is-selected').count() else None,
        'request_index': len(workshop_view_requests),
        'response_index': len(workshop_view_responses),
    }
    quick_result.click()
    room_chooser = inspector.get_by_role('group', name='Choose a room', exact=True)
    try:
        room_chooser.wait_for()
    except Exception as error:
        if type(error).__name__ != 'TimeoutError':
            raise
        relevant_responses = []
        for response in workshop_view_responses[chooser_start['response_index']:]:
            details = {'url': response.url, 'status': response.status, 'matches': []}
            try:
                payload = response.json()
                details['matches'] = [
                    {'room_id': match.get('room_id'), 'drawing_id': match.get('drawing_id')}
                    for match in payload.get('selection', {}).get('matches', [])]
            except Exception as response_error:
                details['body_error'] = type(response_error).__name__
            relevant_responses.append(details)
        diagnostic = {
            **chooser_start,
            'room_picker_after': picker.input_value(),
            'selected_drawing_after': page.locator('[data-workshop-drawing].is-selected').get_attribute(
                'data-workshop-drawing') if page.locator('[data-workshop-drawing].is-selected').count() else None,
            'inspector_text': inspector.inner_text(),
            'view_request_urls': workshop_view_requests[chooser_start['request_index']:],
            'view_responses': relevant_responses,
        }
        print('ROOM-REPRESENTATION-CHOOSER-DIAGNOSTIC ' + json.dumps(diagnostic, sort_keys=True),
              flush=True)
        raise
    assert room_chooser.count() == 1
    selection_view_requests = workshop_view_requests[chooser_start['request_index']:]
    selected_entity_requests = [
        request for request in selection_view_requests
        if parse_qs(urlsplit(request).query, keep_blank_values=True).get('id') == [fixture['shelf_id']]
    ]
    assert selected_entity_requests, 'Selecting a global search result must refresh its room representations.'
    assert all('room_id' not in parse_qs(urlsplit(request).query, keep_blank_values=True)
               for request in selected_entity_requests), (
        'A route update must preserve the global search scope; the selected-entity request must not be room-filtered: '
        + repr(selected_entity_requests))
    refresh_request_start = len(workshop_view_requests)
    with page.expect_response(lambda response: '/workshop-api/workshop/view' in response.url
                              and 'id=' + fixture['shelf_id'] in response.url) as global_refresh:
        page.evaluate("window.dispatchEvent(new Event('focus'))")
    assert global_refresh.value.status == 200
    refresh_requests = workshop_view_requests[refresh_request_start:]
    assert refresh_requests and all('room_id=' not in request for request in refresh_requests), (
        'Focus refresh must retain global search scope until a room or drawing is selected: '
        + repr(refresh_requests))
    room_choice = room_chooser.get_by_role('button').first
    room_choice.wait_for()
    with page.expect_response(lambda response: '/workshop-api/workshop/view' in response.url
                              and 'id=' + fixture['shelf_id'] in response.url
                              and 'room_id=' in response.url) as scoped_refresh:
        room_choice.click()
    assert scoped_refresh.value.status == 200
    assert 'room_id=' in scoped_refresh.value.url, (
        'Explicitly choosing a room representation should return to room-scoped refreshes.')
    page.goto(fixture['drawing_bookmark_url'](fixture['room_one'], unlinked_drawing_id), wait_until='domcontentloaded')
    picker.wait_for()
    page.locator(f'[data-workshop-drawing="{unlinked_drawing_id}"].is-selected').wait_for()
    assert page.locator(f'[data-workshop-drawing="{unlinked_drawing_id}"].is-selected').count() == 1
    page.get_by_text('This drawing is not linked to native storage', exact=False).wait_for()
    page.goto(fixture['drawing_bookmark_url'](fixture['room_one'], drawing_id), wait_until='domcontentloaded')
    picker.wait_for()
    page.locator(f'[data-workshop-drawing="{drawing_id}"].is-selected').wait_for()
    inspector = page.get_by_role('region', name='Workshop inspector', exact=True)
    inspector.get_by_role('navigation', name='Native storage path', exact=True).wait_for()
    assert inspector.get_by_role('link', name='Open in C-Crate', exact=True).get_attribute('href') == (
        '/location/' + fixture['native_location_id'])
    inspector.get_by_text(fixture['native_name_before'], exact=True).wait_for()
    # Exercise the same compatibility rules through the router's query-update
    # path, without re-mounting the planner component.
    view_requests_before_invalid_bookmark = len(workshop_view_requests)
    page.evaluate('''url => { history.pushState({}, '', url); window.dispatchEvent(new PopStateEvent('popstate')); }''',
                  '/workshop/map?id=' + fixture['native_location_id'] + '&room_id=' + fixture['room_two'] + '&drawing_id=' + drawing_id)
    page.get_by_text('This drawing is not available in the requested room', exact=False).wait_for()
    assert len(workshop_view_requests) == view_requests_before_invalid_bookmark
    assert inspector.get_by_role('link', name='Open in C-Crate', exact=True).count() == 0
    view_requests_before_invalid_room = len(workshop_view_requests)
    page.evaluate('''url => { history.pushState({}, '', url); window.dispatchEvent(new PopStateEvent('popstate')); }''',
                  '/workshop/map?id=' + fixture['native_location_id'] + '&room_id=' + str(uuid.uuid4()))
    inspector.get_by_text('This room bookmark is no longer available', exact=False).wait_for()
    assert len(workshop_view_requests) == view_requests_before_invalid_room
    assert page.get_by_role('link', name='Open in C-Crate', exact=True).count() == 0
    page.evaluate('''url => { history.pushState({}, '', url); window.dispatchEvent(new PopStateEvent('popstate')); }''',
                  '/workshop/map?id=' + fixture['native_location_id'] + '&room_id=' + fixture['room_one'] + '&drawing_id=' + str(uuid.uuid4()))
    page.get_by_text('This drawing bookmark is no longer available', exact=False).wait_for()
    assert len(workshop_view_requests) == view_requests_before_invalid_room
    assert page.get_by_role('link', name='Open in C-Crate', exact=True).count() == 0
    page.evaluate('''url => { history.pushState({}, '', url); window.dispatchEvent(new PopStateEvent('popstate')); }''',
                  '/workshop/map?room_id=' + fixture['room_one'] + '&drawing_id=' + drawing_id)
    page.locator(f'[data-workshop-drawing="{drawing_id}"].is-selected').wait_for()
    assert inspector.get_by_role('link', name='Open in C-Crate', exact=True).get_attribute('href') == (
        '/location/' + fixture['native_location_id'])
    assert page.locator(f'[data-workshop-drawing="{drawing_id}"].is-selected').count() == 1
    page.goto(fixture['drawing_bookmark_url'](fixture['room_two'], drawing_id), wait_until='domcontentloaded')
    bookmark_query = parse_qs(urlsplit(page.url).query)
    assert bookmark_query.get('room_id') == [fixture['room_two']]
    assert bookmark_query.get('drawing_id') == [drawing_id]
    picker.wait_for()
    assert picker.input_value() == fixture['room_two']
    try:
        page.get_by_text('This drawing is not available in the requested room', exact=False).wait_for()
    except Exception as error:
        if type(error).__name__ == 'TimeoutError':
            try:
                print(json.dumps({'bookmark_mismatch_diagnostic': {
                    'url': page.url, 'title': page.title(), 'body_text': page.locator('body').inner_text(),
                    'expected_room_id': fixture['room_two'], 'expected_drawing_id': drawing_id}},
                    ensure_ascii=False))
            except Exception as diagnostic_error:
                print(json.dumps({'bookmark_mismatch_diagnostic_error': str(diagnostic_error)}))
        raise
    page.goto(fixture['drawing_bookmark_url'](fixture['room_one'], str(uuid.uuid4())), wait_until='domcontentloaded')
    page.get_by_text('This drawing bookmark is no longer available', exact=False).wait_for()
    views_before_invalid_mount = len(workshop_view_requests)
    page.goto(fixture['gateway_url'] + '/workshop/map?id=' + fixture['native_location_id'] +
              '&room_id=' + str(uuid.uuid4()), wait_until='domcontentloaded')
    inspector.get_by_text('This room bookmark is no longer available', exact=False).wait_for()
    assert len(workshop_view_requests) == views_before_invalid_mount
    assert page.get_by_role('link', name='Open in C-Crate', exact=True).count() == 0
    page.goto(fixture['gateway_url'] + '/workshop/map?id=' + fixture['native_location_id'] +
              '&room_id=' + fixture['room_one'] + '&drawing_id=' + str(uuid.uuid4()),
              wait_until='domcontentloaded')
    page.get_by_text('This drawing bookmark is no longer available', exact=False).wait_for()
    assert len(workshop_view_requests) == views_before_invalid_mount
    page.goto(fixture['drawing_bookmark_url'](fixture['room_one'], drawing_id), wait_until='domcontentloaded')
    page.locator(f'[data-workshop-drawing="{drawing_id}"].is-selected').wait_for()
    page.get_by_role('button', name='Browse', exact=True).click()
    page.locator(f'[data-workshop-drawing="{drawing_id}"]').click()
    inspector.get_by_text(fixture['native_name_before'], exact=True).wait_for()
    page.evaluate('''targetId => {
      const originalFetch = window.fetch.bind(window);
      window.__holdNextWorkshopView = true;
      window.__workshopViewHeld = false;
      window.__workshopViewProcessed = false;
      window.__releaseWorkshopView = null;
      window.fetch = (input, init) => {
        const url = typeof input === 'string' ? input : input.url;
        const response = originalFetch(input, init);
        if (!window.__holdNextWorkshopView || !url.includes('/workshop-api/workshop/view?') ||
            !url.includes('id=' + targetId)) return response;
        window.__holdNextWorkshopView = false;
        return response.then(value => new Promise(resolve => {
          window.__workshopViewHeld = true;
          window.__releaseWorkshopView = () => {
            resolve(value);
            setTimeout(() => { window.__workshopViewProcessed = true; }, 0);
          };
        }));
      };
    }''', fixture['native_location_id'])
    views_before_held_refresh = len(workshop_view_requests)
    page.evaluate("window.dispatchEvent(new Event('focus'))")
    page.wait_for_function('window.__workshopViewHeld === true')
    assert any('id=' + fixture['native_location_id'] in url
               for url in workshop_view_requests[views_before_held_refresh:])
    page.screenshot(path=fixture['desktop_screenshot'], full_page=False)
    def ensure_panel_open(name: str) -> None:
        panel_toggle = page.get_by_role('button', name=name, exact=True)
        if panel_toggle.get_attribute('aria-expanded') != 'true':
            panel_toggle.click()
    page.set_viewport_size({'width': 800, 'height': 480})
    ensure_panel_open('Tools')
    ensure_panel_open('Inspector')
    page.screenshot(path=fixture['narrow_browse_screenshot'], full_page=False)
    page.set_viewport_size({'width': 1440, 'height': 1000})
    page.get_by_role('button', name='Edit', exact=True).click()
    page.screenshot(path=fixture['desktop_edit_screenshot'], full_page=False)
    page.set_viewport_size({'width': 800, 'height': 480})
    ensure_panel_open('Tools')
    ensure_panel_open('Inspector')
    page.get_by_role('button', name='Fit room', exact=True).click()
    assert page.get_by_role('button', name='Tools', exact=True).get_attribute('aria-expanded') == 'true'
    assert page.get_by_role('button', name='Inspector', exact=True).get_attribute('aria-expanded') == 'true'
    assert page.get_by_role('region', name='Object palette', exact=True).is_visible()
    assert page.get_by_role('region', name='Workshop inspector', exact=True).is_visible()
    page.screenshot(path=fixture['narrow_edit_screenshot'], full_page=False)
    page.set_viewport_size({'width': 1440, 'height': 1000})
    fixture['revision'] = cross_room_representation_save.value.json()['revision']
    position_x = page.get_by_label('Position X in feet', exact=True)
    position_edit_event_start = len(workshop_view_events)
    position_edit_started = time.monotonic_ns()
    position_x.fill('7')
    page.evaluate('''() => {
      window.__workshopPaintMutations = 0;
      const root = document.querySelector('.room-planner')?.parentElement;
      window.__workshopPaintObserver = new MutationObserver(() => window.__workshopPaintMutations++);
      window.__workshopPaintObserver.observe(root, {childList: true, subtree: true});
    }''')
    page.evaluate('window.__releaseWorkshopView()')
    page.wait_for_function('window.__workshopViewProcessed === true')
    assert page.evaluate('window.__workshopPaintMutations') == 0
    assert position_x.input_value() == '7'
    assert page.evaluate("document.activeElement?.getAttribute('aria-label')") == 'Position X in feet'
    page.keyboard.press('Tab')
    page.get_by_role('button', name='Apply geometry', exact=True).click()
    try:
        wait_for_drawing_field('Position X in feet', 'x', '7')
    except Exception as error:
        if type(error).__name__ != 'TimeoutError':
            raise
        drawing = page.locator(f'[data-workshop-drawing="{drawing_id}"]')
        print('ROOM-GEOMETRY-REFRESH-DIAGNOSTIC ' + json.dumps({
            'elapsed_ms': (time.monotonic_ns() - position_edit_started) // 1_000_000,
            'url': page.url,
            'selected_room': picker.input_value(),
            'selected_drawing': page.locator('[data-workshop-drawing].is-selected').get_attribute(
                'data-workshop-drawing') if page.locator('[data-workshop-drawing].is-selected').count() else None,
            'input_value': page.get_by_label('Position X in feet', exact=True).input_value(),
            'canvas_x': drawing.get_attribute('data-x'),
            'view_events_since_edit': workshop_view_events[position_edit_event_start:],
        }, sort_keys=True), flush=True)
        raise
    assert position_x.input_value() == '7'
    assert page.locator(f'[data-workshop-drawing="{drawing_id}"]').get_attribute('data-x') == '7'
    first_room_x = '7'

    before_browse = fixture['document'](page)
    geometry_labels = ('Position X in feet', 'Position Y in feet',
                       'Drawing width in feet', 'Drawing depth in feet',
                       'Rotation in quarter turns', 'Native storage location')
    visible_geometry_before_browse = tuple(
        page.get_by_label(label, exact=True).input_value() for label in geometry_labels)
    visible_canvas_geometry_before_browse = {
        key: page.locator(f'[data-workshop-drawing="{drawing_id}"]').get_attribute('data-' + key)
        for key in ('x', 'y', 'width', 'height', 'rotation')}
    selected_drawing_before_browse = page.locator(f'[data-workshop-drawing="{drawing_id}"]').get_attribute('data-workshop-drawing')
    page.get_by_role('button', name='Browse', exact=True).click()
    page.locator(f'[data-workshop-drawing="{drawing_id}"]').click()
    inspector.get_by_text(fixture['native_name_before'], exact=True).wait_for()
    inspector.get_by_role('region', name='Equipment contents', exact=True).get_by_role(
        'button', name=fixture['native_item_name'] + ' · ' + fixture['native_item_id'], exact=True).wait_for()
    native_search = page.get_by_role('searchbox', name='Search native equipment and storage', exact=True)
    coverage_disclosure = page.locator('details.planner-coverage')
    coverage_disclosure.locator('summary').click()
    assert coverage_disclosure.evaluate('(element) => element.open')
    native_search.wait_for(state='visible')
    native_search.fill('Fixture photo shelf')
    search_result = page.locator('details.planner-coverage .workshop-search-results').get_by_role(
        'button', name=re.compile('Fixture photo shelf'))
    search_result.wait_for()
    shelf_search_start = {
        'url': page.url,
        'room_picker': picker.input_value(),
        'selected_drawing': page.locator('[data-workshop-drawing].is-selected').get_attribute(
            'data-workshop-drawing') if page.locator('[data-workshop-drawing].is-selected').count() else None,
        'request_index': len(workshop_view_requests),
        'response_index': len(workshop_view_responses),
    }
    room_chooser = inspector.get_by_role('group', name='Choose a room', exact=True)
    try:
        with page.expect_response(lambda response: '/workshop-api/workshop/view?' in response.url and
                                  'id=' + fixture['shelf_id'] in response.url,
                                  timeout=20_000) as global_shelf_view:
            search_result.click()
    except Exception as error:
        if type(error).__name__ != 'TimeoutError':
            raise
        diagnostic = {
            **shelf_search_start,
            'url_at_assertion': page.url,
            'room_picker_at_assertion': picker.input_value(),
            'selected_drawing_at_assertion': page.locator(
                '[data-workshop-drawing].is-selected').get_attribute('data-workshop-drawing')
                if page.locator('[data-workshop-drawing].is-selected').count() else None,
            'search_result_visible': search_result.is_visible(),
            'search_result_enabled': search_result.is_enabled(),
            'search_result_disabled_attribute': search_result.get_attribute('disabled'),
            'search_result_aria_disabled': search_result.get_attribute('aria-disabled'),
            'search_value': native_search.input_value(),
            'view_requests_since_search': workshop_view_requests[shelf_search_start['request_index']:],
            'view_responses_since_search': [],
            'chooser_text_before_search_result': room_chooser.inner_text()
                if room_chooser.count() else None,
        }
        print('ROOM-REPRESENTATION-SCOPE-DIAGNOSTIC ' + json.dumps(diagnostic, sort_keys=True),
              flush=True)
        raise
    assert global_shelf_view.value.status == 200
    global_shelf_payload = global_shelf_view.value.json()
    assert global_shelf_payload.get('selection', {}).get('target_id') == fixture['shelf_id']
    assert len(global_shelf_payload.get('selection', {}).get('matches', [])) > 1
    room_chooser.wait_for()
    assert room_chooser.count() == 1
    shelf_views = [url for url in workshop_view_requests if 'id=' + fixture['shelf_id'] in url]
    new_shelf_views = workshop_view_requests[shelf_search_start['request_index']:]
    if not new_shelf_views or any('room_id=' in url for url in new_shelf_views):
        recent_responses = []
        for response in workshop_view_responses[shelf_search_start['response_index']:]:
            details = {'url': response.url, 'status': response.status, 'matches': []}
            try:
                payload = response.json()
                details['matches'] = [
                    {'room_id': match.get('room_id'), 'drawing_id': match.get('drawing_id')}
                    for match in payload.get('selection', {}).get('matches', [])]
            except Exception as response_error:
                details['body_error'] = type(response_error).__name__
            recent_responses.append(details)
        print('ROOM-REPRESENTATION-SCOPE-DIAGNOSTIC ' + json.dumps({
            **shelf_search_start,
            'url_at_assertion': page.url,
            'room_picker_at_assertion': picker.input_value(),
            'selected_drawing_at_assertion': page.locator(
                '[data-workshop-drawing].is-selected').get_attribute('data-workshop-drawing')
                if page.locator('[data-workshop-drawing].is-selected').count() else None,
            'shelf_views': shelf_views,
            'view_requests_since_search': workshop_view_requests[shelf_search_start['request_index']:],
            'view_responses_since_search': recent_responses,
            'chooser_text': room_chooser.inner_text(),
        }, sort_keys=True), flush=True)
    assert new_shelf_views and all('room_id=' not in url for url in new_shelf_views)
    room_three_representation = room_chooser.get_by_role('button', name=re.compile(
        'Fixture transfer room.*Cross-room search representation'))
    representation_start = time.monotonic_ns()
    representation_event_start = len(workshop_view_events)
    with page.expect_response(lambda response: '/workshop-api/workshop/view?' in response.url and
                              'id=' + fixture['shelf_id'] in response.url and
                              'room_id=' + fixture['room_three'] in response.url,
                              timeout=20_000) as representation_view:
        room_three_representation.click()
    assert representation_view.value.status == 200
    assert representation_view.value.json().get('selection', {}).get('target_id') == fixture['shelf_id']
    assert picker.input_value() == fixture['room_three']
    assert page.locator(f'[data-workshop-drawing="{fixture["third_drawing_id"]}"].is-selected').count() == 1
    inspector.get_by_text('Containing placement:', exact=False).wait_for()
    open_target = inspector.get_by_role('link', name='Open in C-Crate', exact=True)
    assert open_target.get_attribute('href') == '/location/' + fixture['shelf_id']
    assert fixture['unauthenticated_photo_status'] in (401, 403)
    photo = inspector.locator(f'img[data-attachment-id="{fixture["shelf_photo_id"]}"]')
    assert photo.get_attribute('data-attachment-owner') == fixture['shelf_id']
    assert photo.get_attribute('src').endswith('/' + fixture['shelf_id'] +
        '/attachments/' + fixture['shelf_photo_id'])
    assert inspector.locator(f'img[data-attachment-id="{fixture["parent_photo_id"]}"]').count() == 0
    photo.wait_for(state='attached')
    try:
        photo.scroll_into_view_if_needed()
    except Exception:
        print('ROOM-REPRESENTATION-PHOTO-DIAGNOSTIC ' + json.dumps({
            'selection_request_url': representation_view.value.url,
            'selection_response_status': representation_view.value.status,
            'elapsed_ms': (time.monotonic_ns() - representation_start) // 1_000_000,
            'view_events_since_selection': workshop_view_events[representation_event_start:],
            'photo_count_at_failure': inspector.locator(
                f'img[data-attachment-id="{fixture["shelf_photo_id"]}"]').count(),
            'url': page.url,
        }, sort_keys=True), flush=True)
        raise
    page.wait_for_function('(id) => { const image = document.querySelector(`img[data-attachment-id="${id}"]`); return !!image && image.complete && image.naturalWidth === 2 && image.naturalHeight === 2; }',
                           arg=fixture['shelf_photo_id'])
    photo_url = photo.evaluate('(image) => image.src')
    assert urlsplit(photo_url).scheme == urlsplit(fixture['gateway_url']).scheme
    assert urlsplit(photo_url).netloc == urlsplit(fixture['gateway_url']).netloc
    photo_response = page.context.request.get(photo_url, timeout=20_000)
    assert photo_response.status == 200
    assert photo_response.headers.get('content-type', '').startswith('image/jpeg')
    from io import BytesIO
    from PIL import Image
    photo_bytes = photo_response.body()
    assert hashlib.sha256(photo_bytes).hexdigest() == fixture['shelf_photo_sha256']
    with Image.open(BytesIO(photo_bytes)) as decoded_photo:
        assert decoded_photo.format == 'JPEG' and decoded_photo.size == (2, 2)
    page.screenshot(path=fixture['desktop_screenshot'], full_page=False)
    with page.expect_response(lambda response: '/workshop-api/workshop/view?' in response.url and
                              'id=' + fixture['shelf_id'] in response.url) as refresh_target:
        inspector.get_by_role('button', name='Refresh native status', exact=True).click()
    assert refresh_target.value.status == 200
    picker.select_option(fixture['room_one'])
    page.locator(f'[data-workshop-drawing="{drawing_id}"]').click()
    inspector.get_by_role('region', name='Equipment contents', exact=True).get_by_role(
        'button', name=fixture['native_item_name'] + ' · ' + fixture['native_item_id'], exact=True).wait_for()
    page.get_by_role('navigation', name='Native storage path', exact=True).wait_for()
    page.get_by_role('group', name='Record status', exact=True).wait_for()
    page.get_by_role('region', name='Authorized photos', exact=True).wait_for()
    for name in ('Zoom in', 'Zoom out', 'Fit room', 'Pan left', 'Pan right'):
        page.get_by_role('button', name=name, exact=True).click()
    assert fixture['document'](page) == before_browse
    page.get_by_role('button', name='Edit', exact=True).click()
    visible_geometry_after_browse = tuple(
        page.get_by_label(label, exact=True).input_value() for label in geometry_labels)
    assert visible_geometry_after_browse == visible_geometry_before_browse
    assert page.locator(f'[data-workshop-drawing="{drawing_id}"]').get_attribute('data-workshop-drawing') == selected_drawing_before_browse
    assert {key: page.locator(f'[data-workshop-drawing="{drawing_id}"]').get_attribute('data-' + key)
            for key in visible_canvas_geometry_before_browse} == visible_canvas_geometry_before_browse

    # A native refresh during active typing must retain both the uncommitted value and focus.
    caption_input = page.get_by_label('Drawing caption', exact=True)
    caption_input.fill('Uncommitted caption survives refresh')
    with page.expect_response(lambda response: '/workshop-api/workshop/view?' in response.url) as focused_refresh:
        page.evaluate("window.dispatchEvent(new Event('focus'))")
    assert focused_refresh.value.status == 200
    assert page.get_by_label('Drawing caption', exact=True).input_value() == 'Uncommitted caption survives refresh'
    assert page.evaluate("document.activeElement?.getAttribute('aria-label')") == 'Drawing caption'
    page.keyboard.press('Tab')
    page.get_by_label('Drawing caption', exact=True).fill('Fixture rack drawing')
    page.keyboard.press('Tab')

    width_input = page.get_by_label('Drawing width in feet', exact=True)
    valid_width = width_input.input_value()
    saved_before_invalid = fixture['document'](page)
    undo_before_invalid = page.get_by_role('button', name='Undo', exact=True).is_enabled()
    redo_before_invalid = page.get_by_role('button', name='Redo', exact=True).is_enabled()
    width_input.fill('100')
    page.keyboard.press('Tab')
    page.get_by_role('alert').get_by_text('positive geometry that fits inside the room', exact=False).wait_for()
    assert page.get_by_label('Drawing width in feet', exact=True).input_value() == valid_width
    assert page.evaluate("document.activeElement?.getAttribute('aria-label')") == 'Drawing width in feet'
    assert fixture['document'](page) == saved_before_invalid
    assert page.get_by_role('button', name='Undo', exact=True).is_enabled() == undo_before_invalid
    assert page.get_by_role('button', name='Redo', exact=True).is_enabled() == redo_before_invalid
    page.get_by_label('Drawing width in feet', exact=True).fill(valid_width)
    page.keyboard.press('Tab')
    assert page.get_by_role('button', name='Undo', exact=True).is_enabled() == undo_before_invalid

    # Put a genuine geometry operation at the history head. Browse Ctrl+Z must
    # leave the whole persisted document and both history stacks untouched.
    x_field = page.get_by_label('Position X in feet', exact=True)
    browse_undo_x_text = x_field.input_value()
    browse_undo_x = float(browse_undo_x_text)
    browse_undo_changed_x = round(browse_undo_x + .25, 2)
    x_field.fill(str(browse_undo_changed_x))
    page.get_by_role('button', name='Apply geometry', exact=True).click()
    assert page.get_by_role('button', name='Undo', exact=True).is_enabled()
    draft_before_browse_undo = fixture['draft_state'](page)
    drawing_before_browse_undo = {key: page.locator(f'[data-workshop-drawing="{drawing_id}"]').get_attribute('data-' + key)
                                  for key in ('x', 'y', 'width', 'height', 'rotation', 'name', 'location-id')}
    # Browse never routes keyboard undo to the geometry history.
    page.get_by_role('button', name='Browse', exact=True).click()
    page.locator(f'[data-workshop-drawing="{drawing_id}"]').focus()
    page.keyboard.press('Control+z')
    assert {key: page.locator(f'[data-workshop-drawing="{drawing_id}"]').get_attribute('data-' + key)
            for key in drawing_before_browse_undo} == drawing_before_browse_undo
    assert fixture['draft_state'](page) == draft_before_browse_undo
    page.get_by_role('button', name='Edit', exact=True).click()
    page.get_by_role('button', name='Undo', exact=True).click()
    assert page.get_by_label('Position X in feet', exact=True).input_value() == browse_undo_x_text
    page.get_by_role('button', name='Redo', exact=True).click()
    assert page.get_by_label('Position X in feet', exact=True).input_value() == str(browse_undo_changed_x)

    # Explicit numeric precision is retained when snapping is off and merely
    # toggling snap on; geometry changes only when a direct edit/gesture occurs.
    snap = page.get_by_label('Snap to quarter-foot grid', exact=True)
    snap.uncheck()
    page.get_by_label('Position X in feet', exact=True).fill('3.13')
    page.get_by_role('button', name='Apply geometry', exact=True).click()
    wait_for_drawing_field('Position X in feet', 'x', '3.13')
    assert page.get_by_label('Position X in feet', exact=True).input_value() == '3.13'
    snap = page.get_by_label('Snap to quarter-foot grid', exact=True)
    snap.check()
    assert page.get_by_label('Position X in feet', exact=True).input_value() == '3.13'

    # Drag and resize use the visible canvas handles; geometry changes are then
    # checked against the actual schema2 document and preserved drawing UUID.
    drawing = page.locator(f'[data-workshop-drawing="{drawing_id}"]')
    drag_x_before = page.get_by_label('Position X in feet', exact=True).input_value()
    box = drawing.bounding_box()
    page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
    page.mouse.down(); page.mouse.move(box['x'] + box['width'] / 2 + 40, box['y'] + box['height'] / 2 + 24)
    page.mouse.up()
    drag_x_after = page.get_by_label('Position X in feet', exact=True).input_value()
    assert drag_x_after != drag_x_before
    resize_width_before = page.get_by_label('Drawing width in feet', exact=True).input_value()
    resize_handle = page.get_by_role('button', name='Resize drawing handle', exact=True)
    resize_box = resize_handle.bounding_box()
    resize_view_event_start = len(workshop_view_events)
    resize_started = time.monotonic_ns()
    resize_start_diagnostic = page.evaluate('''drawingId => {
      const group = document.querySelector(`[data-workshop-drawing="${drawingId}"]`);
      const handle = group?.querySelector('[data-resize-handle]');
      const svg = group?.closest('svg');
      window.__plannerResizeGroup = group;
      const box = handle?.getBoundingClientRect();
      const target = box && document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2);
      const describe = node => node && ({tag: node.tagName, role: node.getAttribute('role'),
        resize: node.dataset?.resizeHandle || null, drawing: node.closest('[data-workshop-drawing]')?.dataset.workshopDrawing || null});
      window.__plannerResizeEvents = [];
      for (const type of ['pointerdown', 'gotpointercapture', 'pointermove', 'pointerup', 'pointercancel', 'lostpointercapture']) {
        group?.addEventListener(type, event => {
          if (type === 'pointerdown') window.__lastPlannerPointerId = event.pointerId;
          window.__plannerResizeEvents.push({type,
            target: describe(event.target), x: event.clientX, y: event.clientY, buttons: event.buttons,
            pointerId: event.pointerId, isPrimary: event.isPrimary,
            width: group.dataset.width, height: group.dataset.height,
            handleX: handle?.getAttribute('x'), handleY: handle?.getAttribute('y')});
        }, true);
      }
      return {drawing: group && Object.fromEntries(['x','y','width','height','rotation'].map(k => [k, group.dataset[k]])),
        setPointerCaptureType: typeof group?.setPointerCapture,
        handle: handle && {x: handle.getAttribute('x'), y: handle.getAttribute('y'), width: handle.getAttribute('width'), height: handle.getAttribute('height'), box: box && {x:box.x,y:box.y,width:box.width,height:box.height}},
        roomFrame: svg?.closest('[data-room-width]') && {width:svg.closest('[data-room-width]').dataset.roomWidth,height:svg.closest('[data-room-width]').dataset.roomHeight},
        viewBox: svg?.getAttribute('viewBox'), target: describe(target), targetBounds: target?.getBoundingClientRect().toJSON(),
        editMode: [...document.querySelectorAll('.planner-modes button')].map(button => [button.textContent, button.getAttribute('aria-pressed')])};
    }''', drawing_id)
    page.mouse.move(resize_box['x'] + resize_box['width'] / 2,
                    resize_box['y'] + resize_box['height'] / 2)
    page.mouse.down(); page.mouse.move(resize_box['x'] + resize_box['width'] / 2 + 24,
                                       resize_box['y'] + resize_box['height'] / 2)
    page.mouse.up()
    resized_width = page.get_by_label('Drawing width in feet', exact=True).input_value()
    if resized_width == resize_width_before:
        resize_failure_diagnostic = page.evaluate('''drawingId => {
          const group = document.querySelector(`[data-workshop-drawing="${drawingId}"]`);
          const initialGroup = window.__plannerResizeGroup;
          const handle = group?.querySelector('[data-resize-handle]');
          return {drawing: group && Object.fromEntries(['x','y','width','height','rotation'].map(k => [k, group.dataset[k]])),
            originalGroupStillCurrent: initialGroup === group,
            originalGroupConnected: !!initialGroup?.isConnected,
            hasPointerCapture: initialGroup && window.__lastPlannerPointerId !== undefined
              ? initialGroup.hasPointerCapture(window.__lastPlannerPointerId) : null,
            inspectorWidth: document.querySelector('[aria-label="Drawing width in feet"]')?.value,
            events: window.__plannerResizeEvents || [],
            handle: handle && {x:handle.getAttribute('x'),y:handle.getAttribute('y'),width:handle.getAttribute('width'),height:handle.getAttribute('height'),box:handle.getBoundingClientRect().toJSON()},
            roomFrame: group?.closest('[data-planner-canvas]')?.closest('[data-room-width]') && {width:group.closest('[data-planner-canvas]').closest('[data-room-width]').dataset.roomWidth,height:group.closest('[data-planner-canvas]').closest('[data-room-width]').dataset.roomHeight},
            viewBox: group?.closest('svg')?.getAttribute('viewBox'), mode: [...document.querySelectorAll('.planner-modes button')].map(button => [button.textContent,button.getAttribute('aria-pressed')])};
        }''', drawing_id)
        print('RESIZE-HANDLE-DIAGNOSTIC ' + json.dumps({'before': resize_start_diagnostic,
              'after': resize_failure_diagnostic, 'width_before': resize_width_before,
              'width_after': resized_width,
              'elapsed_ms': (time.monotonic_ns() - resize_started) // 1_000_000,
              'view_events_since_resize': workshop_view_events[resize_view_event_start:],
              'browser_errors': fixture['browser_errors']}, sort_keys=True), flush=True)
        try:
            page.screenshot(path=str(QUEUE / 'rooms4-desktop_candidate_attempt30-resize-failure.png'), full_page=True)
        except Exception as screenshot_error:
            print('RESIZE-FAILURE-SCREENSHOT-ERROR ' + type(screenshot_error).__name__, flush=True)
    assert resized_width != resize_width_before
    page.get_by_label('Drawing width in feet', exact=True).fill('6')
    page.get_by_role('button', name='Apply geometry', exact=True).click()
    with page.expect_response(lambda response: response.url.endswith('/workshop-api/workshop/save')) as geometry_save:
        page.get_by_role('button', name='Save all room changes', exact=True).click()
    assert geometry_save.value.status == 200
    edited = fixture['document'](page)
    second.reload()
    second.get_by_role('combobox', name='Workshop room', exact=True).wait_for()
    page.get_by_label('Position X in feet', exact=True).fill('9')
    edited_row = next(obj for room in edited['document']['rooms'] for obj in room['objects']
                      if obj['id'] == drawing_id)
    assert edited_row['width'] == 6 and edited_row['rotation'] == 180
    assert edited_row['id'] == drawing_id and edited_row['location_id'] == fixture['native_location_id']
    assert str(edited_row['x']) != drag_x_before
    assert edited_row['x'] == float(drag_x_after)
    assert edited_row['width'] == float(page.get_by_label('Drawing width in feet', exact=True).input_value())
    assert (edited_row['x'] * 4).is_integer() and (edited_row['y'] * 4).is_integer()

    # Rotated 6×2 objects use the stored room-space envelope for their visible
    # footprint, bounds and resize handle; opening the plan never rewrites size.
    page.get_by_label('Position X in feet', exact=True).fill('14')
    page.keyboard.press('Tab')
    page.get_by_label('Position Y in feet', exact=True).fill('0')
    page.keyboard.press('Tab')
    rotation_input = page.get_by_label('Rotation in quarter turns', exact=True)
    rotation_input.fill('1')
    page.keyboard.press('Tab')
    page.get_by_role('button', name='Apply geometry', exact=True).click()
    wait_for_rotation(1)
    turned = page.locator(f'[data-workshop-drawing="{drawing_id}"]')
    assert rotation_input.input_value() == '1'
    assert turned.get_attribute('data-rotation') == '90'
    assert turned.get_attribute('data-x') == '14'
    assert turned.get_attribute('data-y') == '0'
    visible_bounds = page.evaluate('''id => {
      const drawing = document.querySelector(`[data-workshop-drawing="${id}"]`);
      const shape = drawing.querySelector('g').getBoundingClientRect();
      const surface = document.querySelector('[data-room-surface]').getBoundingClientRect();
      const handle = drawing.querySelector('[data-resize-handle]').getBoundingClientRect();
      return {shape:{left:shape.left,right:shape.right,top:shape.top,bottom:shape.bottom},
              surface:{left:surface.left,right:surface.right,top:surface.top,bottom:surface.bottom},
              handle:{right:handle.right,bottom:handle.bottom},
              data:{x:Number(drawing.dataset.x),y:Number(drawing.dataset.y),width:Number(drawing.dataset.width),height:Number(drawing.dataset.height)}};
    }''', drawing_id)
    assert visible_bounds['shape']['left'] >= visible_bounds['surface']['left'] - 2
    assert visible_bounds['shape']['right'] <= visible_bounds['surface']['right'] + 2
    assert visible_bounds['shape']['top'] >= visible_bounds['surface']['top'] - 2
    assert visible_bounds['shape']['bottom'] <= visible_bounds['surface']['bottom'] + 2
    assert visible_bounds['data']['width'] == 6 and visible_bounds['data']['height'] == 2
    assert abs(visible_bounds['handle']['right'] - (visible_bounds['surface']['left'] +
        (visible_bounds['data']['x'] + visible_bounds['data']['width']) /
        float(page.locator('[data-room-surface]').get_attribute('width')) *
        (visible_bounds['surface']['right'] - visible_bounds['surface']['left']))) < 3
    assert abs(visible_bounds['handle']['bottom'] - (visible_bounds['surface']['top'] +
        (visible_bounds['data']['y'] + visible_bounds['data']['height']) /
        float(page.locator('[data-room-surface]').get_attribute('height')) *
        (visible_bounds['surface']['bottom'] - visible_bounds['surface']['top']))) < 3
    page.get_by_label('Position X in feet', exact=True).fill('7')
    page.keyboard.press('Tab')
    page.get_by_label('Position Y in feet', exact=True).fill('4')
    page.keyboard.press('Tab')
    page.get_by_label('Rotation in quarter turns', exact=True).fill('2')
    page.keyboard.press('Tab')
    first_room_history = page.get_by_role('button', name='Undo', exact=True).is_enabled()
    picker.select_option(fixture['room_two'])
    page.get_by_label('Room width in feet', exact=True).fill('21')
    page.get_by_role('button', name='Apply room changes', exact=True).click()
    second_room_width = page.get_by_label('Room width in feet', exact=True).input_value()
    second_room_undo = page.get_by_role('button', name='Undo', exact=True).is_enabled()
    assert second_room_width == '21' and second_room_undo
    picker.select_option(fixture['room_one'])
    assert page.get_by_role('button', name='Undo', exact=True).is_enabled() == first_room_history
    page.get_by_role('button', name='Undo', exact=True).click()
    picker.select_option(fixture['room_two'])
    assert page.get_by_label('Room width in feet', exact=True).input_value() == second_room_width
    assert page.get_by_role('button', name='Undo', exact=True).is_enabled() == second_room_undo
    page.get_by_role('button', name='Undo', exact=True).click()
    assert page.get_by_label('Room width in feet', exact=True).input_value() == '20'
    page.get_by_role('button', name='Redo', exact=True).click()
    assert page.get_by_label('Room width in feet', exact=True).input_value() == '21'
    page.get_by_role('button', name='Undo', exact=True).click()
    assert page.get_by_label('Room width in feet', exact=True).input_value() == '20'
    picker.select_option(fixture['room_one'])
    page.get_by_role('button', name='Redo', exact=True).click()
    first_room_x = page.get_by_label('Position X in feet', exact=True).input_value()
    assert first_room_x == '7'

    # Native collection switching must suspend the original draft under its UUID.
    original_group = fixture['original_group_name']
    original_draft_before_switch = fixture['draft_state'](page)
    assert original_draft_before_switch['group_id'] == fixture['original_group_id']
    assert original_draft_before_switch['room_id'] == fixture['room_one']
    assert original_draft_before_switch['drawing_id'] == drawing_id
    original_drawing_before_switch = next(
        obj for room in original_draft_before_switch['document']['rooms']
        for obj in room['objects'] if obj['id'] == drawing_id)
    assert original_drawing_before_switch['x'] == float(first_room_x)
    collection_selector = page.get_by_role('combobox', name='Select collection')
    collection_selector.click()
    collection_search = page.get_by_placeholder('Search Collections…', exact=True)
    collection_search.wait_for()
    collection_search.fill(fixture['alternate_group_name'])
    alternate_option = page.get_by_role('option', name=fixture['alternate_group_name'], exact=True)
    alternate_option.wait_for()
    alternate_option.focus()
    with page.expect_navigation(wait_until='domcontentloaded'):
        alternate_option.press('Space')
    page.get_by_text(fixture['alternate_group_name'], exact=True).wait_for()
    assert fixture['displayed_group'](page) != original_group
    assert fixture['draft_state'](page) == original_draft_before_switch
    page.get_by_role('combobox', name='Workshop room', exact=True).wait_for()
    collection_selector.click()
    collection_search = page.get_by_placeholder('Search Collections…', exact=True)
    collection_search.wait_for()
    collection_search.fill(original_group)
    original_option = page.get_by_role('option', name=original_group, exact=True)
    original_option.wait_for()
    original_option.focus()
    with page.expect_navigation(wait_until='domcontentloaded'):
        original_option.press('Space')
    collection_selector.get_by_text(original_group, exact=True).wait_for()
    assert fixture['displayed_group'](page) == original_group
    picker = page.get_by_role('combobox', name='Workshop room', exact=True)
    picker.wait_for()
    picker.select_option(fixture['room_one'])
    page.get_by_role('button', name='Edit', exact=True).click()
    position_x = page.get_by_label('Position X in feet', exact=True)
    position_x.wait_for()
    assert position_x.input_value() == first_room_x
    restored_original_draft = fixture['draft_state'](page)
    assert restored_original_draft == original_draft_before_switch
    assert restored_original_draft['group_id'] == fixture['original_group_id']
    assert restored_original_draft['room_id'] == fixture['room_one']
    assert restored_original_draft['drawing_id'] == drawing_id
    restored_original_drawing = next(
        obj for room in restored_original_draft['document']['rooms']
        for obj in room['objects'] if obj['id'] == drawing_id)
    assert restored_original_drawing == original_drawing_before_switch
    assert restored_original_drawing['x'] == float(first_room_x)

    # A second manager session saves from the same revision; the stale draft is kept.
    second.get_by_role('combobox', name='Workshop room', exact=True).select_option(fixture['room_one'])
    second.get_by_role('button', name='Edit', exact=True).click()
    second.get_by_label('Room width in feet', exact=True).fill('19')
    second.get_by_role('button', name='Apply room changes', exact=True).click()
    second.get_by_role('combobox', name='Workshop room', exact=True).select_option(fixture['room_two'])
    second.get_by_label('Room width in feet', exact=True).fill('22')
    second.get_by_role('button', name='Apply room changes', exact=True).click()
    second.get_by_role('combobox', name='Workshop room', exact=True).select_option(fixture['room_one'])
    with second.expect_response(lambda response: response.url.endswith('/workshop-api/workshop/save')) as second_save:
        second.get_by_role('button', name='Save all room changes', exact=True).click()
    assert second_save.value.status == 200
    second_payload = second_save.value.request.post_data_json
    assert {room['id'] for room in second_payload['document']['rooms']} == {
        fixture['room_one'], fixture['room_two'], fixture['room_three']}
    assert next(room for room in second_payload['document']['rooms']
                if room['id'] == fixture['room_two'])['width'] == 22
    second_save_body = second_save.value.json()
    response_width = next(room['width'] for room in second_save_body['document']['rooms']
                          if room['id'] == fixture['room_two'])
    server_width = next(room['width'] for room in fixture['document'](second)['document']['rooms']
                        if room['id'] == fixture['room_two'])
    print('ROOM-SAVE-DIAGNOSTIC ' + json.dumps({
        'request_width': 22, 'response_width': response_width,
        'server_width_after_save': server_width,
        'revision': second_save_body['revision'],
    }, sort_keys=True), flush=True)
    fixture['server_revision'] = second_save_body['revision']
    with page.expect_response(lambda response: response.url.endswith('/workshop-api/workshop/save')) as conflict_save:
        page.get_by_role('button', name='Save all room changes', exact=True).click()
    assert conflict_save.value.status == 409
    page.get_by_text('changed elsewhere', exact=False).wait_for()
    assert page.get_by_label('Position X in feet', exact=True).input_value() == first_room_x
    assert page.get_by_role('button', name='Reload saved plan', exact=True).is_visible()
    schema_before = fixture['document'](page)
    schema_route = fixture['reject_schema_save'](page)
    with page.expect_response(lambda response: response.url.endswith('/workshop-api/workshop/save')) as schema_reject:
        page.get_by_role('button', name='Save all room changes', exact=True).click()
    assert schema_reject.value.status == 400
    assert schema_route['wire']['schema_version'] == 1 and schema_route['original']['schema_version'] == 2
    assert schema_reject.value.json()['error'] == 'This Workshop save is outdated. Reload before saving.'
    assert fixture['document'](page) == schema_before
    page.get_by_role('alert').get_by_text('The server rejected this room plan', exact=False).wait_for()
    assert page.get_by_label('Position X in feet', exact=True).input_value() == first_room_x
    assert page.get_by_role('button', name='Reload saved plan', exact=True).is_visible()
    page.unroute('**/workshop-api/workshop/save')

    # Wrong-root transfer and non-empty removal must preserve UUIDs and native links.
    before_pair = (edited_row['id'], edited_row['location_id'])
    page.locator(f'[data-workshop-drawing="{drawing_id}"]').click()
    page.get_by_role('button', name='Move drawing to another room', exact=True).click()
    page.get_by_label('Target room', exact=True).select_option(fixture['room_two'])
    page.get_by_label('Target X in feet', exact=True).fill('2')
    page.get_by_label('Target Y in feet', exact=True).fill('2')
    page.get_by_role('button', name='Move drawing', exact=True).click()
    move_dialog = page.get_by_role('dialog', name='Move drawing to another room', exact=True)
    move_dialog.get_by_role('alert').get_by_text('native storage root', exact=False).wait_for()
    assert move_dialog.is_visible()
    assert page.get_by_label('Native storage location', exact=True).input_value() == fixture['native_location_id']
    assert page.get_by_label('Position X in feet', exact=True).input_value() == first_room_x
    after_doc = fixture['document'](page)
    after_row = next(obj for room in after_doc['document']['rooms'] for obj in room['objects']
                     if obj['id'] == drawing_id)
    assert (after_row['id'], after_row['location_id']) == before_pair
    cancel_messages = accept_one_dialog(
        page, lambda: move_dialog.get_by_role('button', name='Cancel', exact=True).click())
    assert cancel_messages == ['Discard these unsaved edits?']
    assert fixture['document'](page) == after_doc
    room_width = page.get_by_label('Room width in feet', exact=True)
    if room_width.count() == 0:
        page.get_by_role('button', name='Room settings', exact=True).click()
    room_width.wait_for()
    assert not page.get_by_role('button', name='Remove room', exact=True).is_enabled()
    assert fixture['room_one'] in {room['id'] for room in after_doc['document']['rooms']}
    picker.select_option(fixture['room_two'])
    page.get_by_role('button', name='Remove room', exact=True).click()
    remove_dialog = page.get_by_role('dialog', name='Remove room', exact=True)
    remove_dialog.get_by_role('button', name='Cancel', exact=True).click()
    picker_options = page.locator('select[aria-label="Workshop room"] option').evaluate_all(
        'rows => rows.map(row => row.value)')
    assert fixture['room_two'] in picker_options
    picker.select_option(fixture['room_two'])
    assert page.get_by_label('Room width in feet', exact=True).input_value() == '20'
    assert fixture['room_two'] in {room['id'] for room in fixture['document'](page)['document']['rooms']}

    # A compatible transfer uses the chosen room and coordinates without changing IDs or size.
    second.reload()
    second_picker = second.get_by_role('combobox', name='Workshop room', exact=True)
    second_picker.wait_for()
    second.get_by_role('button', name='Edit', exact=True).click()
    second_picker.select_option(fixture['room_two'])
    second_room_width = second.get_by_label('Room width in feet', exact=True)
    assert second_room_width.input_value() == '22', (
        'Reloading the second tab restored another tab\'s stale room draft instead of its saved room width.')
    second_picker.select_option(fixture['room_three'])
    second.locator(f'[data-workshop-drawing="{fixture["third_drawing_id"]}"]').click()
    remove_search_messages = accept_one_dialog(
        second, lambda: second.get_by_role('button', name='Remove drawing only', exact=True).click())
    assert remove_search_messages == ['Remove this drawing? Its native location and inventory will remain.']
    with second.expect_response(lambda response: response.url.endswith('/workshop-api/workshop/save')) as remove_search_representation_save:
        second.get_by_role('button', name='Save all room changes', exact=True).click()
    assert remove_search_representation_save.value.status == 200
    before_room_edit = fixture['document'](second)
    width_before_room_edit = next(room['width'] for room in before_room_edit['document']['rooms']
                                  if room['id'] == fixture['room_two'])
    print('ROOM-SAVE-SEQUENCE-DIAGNOSTIC ' + json.dumps({
        'width_before_room_edit': width_before_room_edit,
        'save_count': len(fixture['save_posts']()),
        'recent_save_widths': [next((room['width'] for room in post.get('document', {}).get('rooms', [])
                                     if room['id'] == fixture['room_two']), None)
                               for post in fixture['save_posts']()[-6:]],
    }, sort_keys=True), flush=True)
    second_picker.select_option(fixture['room_two'])
    room_settings_toggle = second.get_by_role('button', name='Room settings', exact=True)
    if room_settings_toggle.count():
        room_settings_toggle.click()
    second.get_by_label('Room width in feet', exact=True).fill('23')
    second.get_by_role('button', name='Apply room changes', exact=True).click()
    second.get_by_role('button', name='Undo', exact=True).click()
    width_after_room_undo = second.get_by_label('Room width in feet', exact=True).input_value()
    if width_after_room_undo != '22':
        print('ROOM-UNDO-DIAGNOSTIC ' + json.dumps({
            'room_id': fixture['room_two'],
            'width_after_undo': width_after_room_undo,
            'undo_enabled': second.get_by_role('button', name='Undo', exact=True).is_enabled(),
            'redo_enabled': second.get_by_role('button', name='Redo', exact=True).is_enabled(),
            'saved_width': next(room['width'] for room in fixture['document'](second)['document']['rooms']
                                if room['id'] == fixture['room_two']),
        }, sort_keys=True), flush=True)
    assert width_after_room_undo == '22'
    second.get_by_role('button', name='Redo', exact=True).click()
    assert second.get_by_label('Room width in feet', exact=True).input_value() == '23'
    second.get_by_role('button', name='Undo', exact=True).click()
    assert second.get_by_label('Room width in feet', exact=True).input_value() == '22'
    sibling_room_history_before_transfer = (
        second.get_by_role('button', name='Undo', exact=True).is_enabled(),
        second.get_by_role('button', name='Redo', exact=True).is_enabled())
    assert sibling_room_history_before_transfer == (False, True)
    second_picker.select_option(fixture['room_one'])
    second.locator(f'[data-workshop-drawing="{drawing_id}"]').click()
    x_before_transfer = float(second.get_by_label('Position X in feet', exact=True).input_value())
    x_before_transfer = '5' if x_before_transfer != 5 else '5.25'
    second.get_by_label('Position X in feet', exact=True).fill(x_before_transfer)
    second.get_by_role('button', name='Apply geometry', exact=True).click()
    assert second.get_by_role('button', name='Undo', exact=True).is_enabled()
    second.get_by_role('combobox', name='Workshop room', exact=True).select_option(fixture['room_three'])
    second.get_by_label('Room width in feet', exact=True).fill('19.9')
    second.get_by_role('button', name='Apply room changes', exact=True).click()
    assert second.get_by_role('button', name='Undo', exact=True).is_enabled()
    assert second.locator('[data-workshop-drawing]').count() == 0
    second.get_by_role('combobox', name='Workshop room', exact=True).select_option(fixture['room_one'])
    second.locator(f'[data-workshop-drawing="{drawing_id}"]').click()
    before_edge_reject = fixture['document'](second)
    source_edge_draft = {
        'x': second.get_by_label('Position X in feet', exact=True).input_value(),
        'y': second.get_by_label('Position Y in feet', exact=True).input_value(),
        'width': second.get_by_label('Drawing width in feet', exact=True).input_value(),
        'height': second.get_by_label('Drawing depth in feet', exact=True).input_value(),
        'rotation': second.get_by_label('Rotation in quarter turns', exact=True).input_value(),
        'location': second.get_by_label('Native storage location', exact=True).input_value(),
    }
    second.get_by_role('button', name='Move drawing to another room', exact=True).click()
    second.get_by_label('Target room', exact=True).select_option(fixture['room_three'])
    target_max_x = round(19.9 - float(source_edge_draft['width']), 3)
    target_x_before_snap = round(target_max_x - .01, 3)
    snapped_target_x = round(target_x_before_snap * 4) / 4
    assert target_x_before_snap >= 0 and target_x_before_snap < target_max_x \
            and snapped_target_x > target_max_x, (
        f'The fixture edge coordinate must be valid before snapping and invalid after snapping: '
        f'max_x={target_max_x}, target_x={target_x_before_snap}, snapped_x={snapped_target_x}')
    assert second.get_by_label('Snap to quarter-foot grid', exact=True).is_checked()
    second.get_by_label('Target X in feet', exact=True).fill(str(target_x_before_snap))
    second.get_by_label('Target Y in feet', exact=True).fill('2')
    second.get_by_role('button', name='Move drawing', exact=True).click()
    try:
        second.get_by_text('Snapped coordinates do not fit', exact=False).wait_for()
    except Exception as error:
        if type(error).__name__ != 'TimeoutError':
            raise
        current_draft = fixture['draft_state'](second)['document']
        current_source = next(obj for room in current_draft['rooms'] for obj in room['objects']
                              if obj['id'] == drawing_id)
        current_target = next(room for room in current_draft['rooms'] if room['id'] == fixture['room_three'])
        move_dialog = second.get_by_role('dialog', name='Move drawing to another room', exact=True)
        print('EDGE-MOVE-DIAGNOSTIC ' + json.dumps({
            'source_edge_draft': source_edge_draft,
            'source_width_after': current_source['width'],
            'target_width_after': current_target['width'],
            'target_max_x': target_max_x,
            'target_x_field': move_dialog.get_by_label('Target X in feet', exact=True).input_value()
                if move_dialog.count() else None,
            'target_y_field': move_dialog.get_by_label('Target Y in feet', exact=True).input_value()
                if move_dialog.count() else None,
            'snap_checked': second.get_by_label('Snap to quarter-foot grid', exact=True).is_checked(),
            'dialog_visible': move_dialog.is_visible() if move_dialog.count() else False,
            'dialog_alerts': move_dialog.get_by_role('alert').all_inner_texts() if move_dialog.count() else [],
            'all_alerts': second.get_by_role('alert').all_inner_texts(),
        }, sort_keys=True), flush=True)
        raise
    assert fixture['document'](second) == before_edge_reject
    assert second.locator(f'[data-workshop-drawing="{drawing_id}"]').count() == 1
    assert second.get_by_label('Native storage location', exact=True).input_value() == fixture['native_location_id']
    assert second.get_by_role('button', name='Undo', exact=True).is_enabled()
    assert {
        'x': second.get_by_label('Position X in feet', exact=True).input_value(),
        'y': second.get_by_label('Position Y in feet', exact=True).input_value(),
        'width': second.get_by_label('Drawing width in feet', exact=True).input_value(),
        'height': second.get_by_label('Drawing depth in feet', exact=True).input_value(),
        'rotation': second.get_by_label('Rotation in quarter turns', exact=True).input_value(),
        'location': second.get_by_label('Native storage location', exact=True).input_value(),
    } == source_edge_draft
    near_edge = second.get_by_role('dialog', name='Move drawing to another room', exact=True)
    edge_cancel_messages = accept_one_dialog(
        second, lambda: near_edge.get_by_role('button', name='Cancel', exact=True).click())
    assert edge_cancel_messages == ['Discard these unsaved edits?']
    assert second.get_by_label('Position X in feet', exact=True).input_value() == source_edge_draft['x']
    assert second.get_by_label('Position Y in feet', exact=True).input_value() == source_edge_draft['y']
    assert second.get_by_role('button', name='Undo', exact=True).is_enabled()
    second.get_by_role('combobox', name='Workshop room', exact=True).select_option(fixture['room_three'])
    assert second.get_by_label('Room width in feet', exact=True).input_value() == '19.9'
    assert second.locator('[data-workshop-drawing]').count() == 0
    assert second.get_by_role('button', name='Undo', exact=True).is_enabled()
    second.get_by_role('combobox', name='Workshop room', exact=True).select_option(fixture['room_one'])
    second.locator(f'[data-workshop-drawing="{drawing_id}"]').click()
    second.get_by_role('button', name='Move drawing to another room', exact=True).click()
    second.get_by_label('Target room', exact=True).select_option(fixture['room_three'])
    second.get_by_label('Target X in feet', exact=True).fill('2')
    second.get_by_label('Target Y in feet', exact=True).fill('2')
    second.get_by_text('Confirming this move adds one coordinated Undo step', exact=False).wait_for()
    source_room_ids_before_transfer = second.locator('[data-workshop-drawing]').evaluate_all(
        'nodes => nodes.map(node => node.getAttribute("data-workshop-drawing"))')
    assert drawing_id in source_room_ids_before_transfer and len(source_room_ids_before_transfer) >= 2
    second.get_by_role('button', name='Move drawing', exact=True).click()
    assert second.get_by_role('button', name='Undo', exact=True).is_enabled()
    second.get_by_role('button', name='Room settings', exact=True).click()
    second.get_by_label('Room width in feet', exact=True).fill('19.8')
    second.get_by_role('button', name='Apply room changes', exact=True).click()
    second.get_by_role('combobox', name='Workshop room', exact=True).select_option(fixture['room_one'])
    second.get_by_role('button', name='Undo', exact=True).click()
    second.get_by_text('Cross-room Undo is unavailable until both rooms return to the transfer boundary',
                        exact=False).wait_for()
    assert second.locator(f'[data-workshop-drawing="{drawing_id}"]').count() == 0
    second.get_by_role('combobox', name='Workshop room', exact=True).select_option(fixture['room_three'])
    second.get_by_role('button', name='Room settings', exact=True).click()
    assert second.locator(f'[data-workshop-drawing="{drawing_id}"]').count() == 1
    assert second.get_by_label('Room width in feet', exact=True).input_value() == '19.8'
    second.get_by_role('button', name='Undo', exact=True).click()
    assert second.get_by_label('Room width in feet', exact=True).input_value() == '19.9'
    second.get_by_role('button', name='Undo', exact=True).click()
    assert second.get_by_label('Room width in feet', exact=True).input_value() == '19.9'
    assert second.locator('[data-workshop-drawing]').count() == 0
    assert second.get_by_role('button', name='Redo', exact=True).is_enabled()
    second.get_by_role('combobox', name='Workshop room', exact=True).select_option(fixture['room_one'])
    assert second.locator(f'[data-workshop-drawing="{drawing_id}"]').count() == 1
    source_x_at_transfer = second.locator(f'[data-workshop-drawing="{drawing_id}"]').get_attribute('data-x')
    second.get_by_role('button', name='Undo', exact=True).click()
    assert second.locator(f'[data-workshop-drawing="{drawing_id}"]').get_attribute('data-x') != source_x_at_transfer
    second.get_by_role('button', name='Redo', exact=True).click()
    assert second.locator(f'[data-workshop-drawing="{drawing_id}"]').get_attribute('data-x') == source_x_at_transfer
    second.get_by_role('combobox', name='Workshop room', exact=True).select_option(fixture['room_three'])
    second.get_by_role('button', name='Undo', exact=True).click()
    assert second.get_by_label('Room width in feet', exact=True).input_value() == '20'
    second.get_by_role('button', name='Redo', exact=True).click()
    assert second.get_by_label('Room width in feet', exact=True).input_value() == '19.9'
    second.get_by_role('button', name='Redo', exact=True).click()
    second.get_by_role('combobox', name='Workshop room', exact=True).select_option(fixture['room_one'])
    assert second.locator(f'[data-workshop-drawing="{drawing_id}"]').count() == 0
    remaining_source_ids = second.locator('[data-workshop-drawing]').evaluate_all(
        'nodes => nodes.map(node => node.getAttribute("data-workshop-drawing"))')
    assert set(remaining_source_ids) == set(source_room_ids_before_transfer) - {drawing_id}
    second.get_by_role('combobox', name='Workshop room', exact=True).select_option(fixture['room_three'])
    assert second.locator(f'[data-workshop-drawing="{drawing_id}"]').count() == 1
    second.get_by_role('combobox', name='Workshop room', exact=True).select_option(fixture['room_two'])
    assert second.get_by_label('Room width in feet', exact=True).input_value() == '22'
    assert (second.get_by_role('button', name='Undo', exact=True).is_enabled(),
            second.get_by_role('button', name='Redo', exact=True).is_enabled()) == sibling_room_history_before_transfer
    second.get_by_role('button', name='Redo', exact=True).click()
    assert second.get_by_label('Room width in feet', exact=True).input_value() == '23'
    second.get_by_role('button', name='Undo', exact=True).click()
    assert second.get_by_label('Room width in feet', exact=True).input_value() == '22'
    second.get_by_role('combobox', name='Workshop room', exact=True).select_option(fixture['room_three'])
    with second.expect_response(lambda response: response.url.endswith('/workshop-api/workshop/save')) as transfer_save:
        second.get_by_role('button', name='Save all room changes', exact=True).click()
    assert transfer_save.value.status == 200
    moved_doc = fixture['document'](second)
    global_drawing_ids = [obj['id'] for room in moved_doc['document']['rooms'] for obj in room['objects']]
    assert global_drawing_ids.count(drawing_id) == 1
    moved_room = next(room for room in moved_doc['document']['rooms'] if room['id'] == fixture['room_three'])
    moved_row = next(obj for obj in moved_room['objects'] if obj['id'] == drawing_id)
    assert (moved_row['id'], moved_row['location_id'], moved_row['x'], moved_row['y'],
            moved_row['width'], moved_row['height']) == (
                drawing_id, fixture['native_location_id'], 2, 2, edited_row['width'], edited_row['height'])

    # Save the full draft, force a lost response after commit, then recover only by status.
    second.get_by_role('combobox', name='Workshop room', exact=True).select_option(fixture['room_one'])
    room_one_before_apply = next(
        room for room in fixture['draft_state'](second)['document']['rooms']
        if room['id'] == fixture['room_one'])
    max_drawing_right = max(
        (drawing['x'] + drawing['width'] for drawing in room_one_before_apply['objects']),
        default=0)
    requested_room_width = 18
    if max_drawing_right > requested_room_width:
        requested_room_width = math.ceil((max_drawing_right + .25) * 4) / 4
    expected_room_width = str(requested_room_width)
    second.get_by_label('Room width in feet', exact=True).fill(expected_room_width)
    room_one_width_after_fill = second.get_by_label('Room width in feet', exact=True).input_value()
    room_one_draft_width_after_fill = next(
        room for room in fixture['draft_state'](second)['document']['rooms']
        if room['id'] == fixture['room_one'])['width']
    second.get_by_role('button', name='Apply room changes', exact=True).click()
    room_one_width_after_apply = second.get_by_label('Room width in feet', exact=True).input_value()
    room_one_draft_width_after_apply = next(
        room for room in fixture['draft_state'](second)['document']['rooms']
        if room['id'] == fixture['room_one'])['width']
    room_one_apply_alert = second.get_by_role('alert').all_inner_texts()
    print('ROOM-WIDTH-APPLY-DIAGNOSTIC ' + json.dumps({
        'existing_width': room_one_before_apply['width'],
        'drawing_right_edges': [drawing['x'] + drawing['width']
                                for drawing in room_one_before_apply['objects']],
        'requested_width': requested_room_width,
        'width_after_fill': room_one_width_after_fill,
        'draft_width_after_fill': room_one_draft_width_after_fill,
        'width_after_apply': room_one_width_after_apply,
        'draft_width_after_apply': room_one_draft_width_after_apply,
        'alerts_after_apply': room_one_apply_alert,
    }, sort_keys=True), flush=True)
    assert room_one_width_after_apply == expected_room_width, (
        f'Applying the room width did not commit the valid edited value: {room_one_width_after_apply!r}; '
        f'expected {expected_room_width!r}, alerts={room_one_apply_alert!r}')
    assert room_one_draft_width_after_apply == requested_room_width, (
        'Applying the room width updated the field but not the saved-device draft: '
        f'{room_one_draft_width_after_apply!r}')
    second.get_by_role('combobox', name='Workshop room', exact=True).select_option(fixture['room_three'])
    second.locator(f'[data-workshop-drawing="{drawing_id}"]').click()
    uncertain_x = float(second.get_by_label('Position X in feet', exact=True).input_value())
    second.get_by_label('Position X in feet', exact=True).fill(str(round(uncertain_x + .25, 2)))
    second.get_by_role('button', name='Apply geometry', exact=True).click()
    assert second.get_by_role('button', name='Undo', exact=True).is_enabled()
    uncertain_key_geometry = {key: second.locator(f'[data-workshop-drawing="{drawing_id}"]').get_attribute('data-' + key)
                              for key in ('x', 'y', 'width', 'height', 'rotation')}
    save_count = len(fixture['save_posts']())
    revision_before_timeout = fixture['document'](second)['revision']
    fixture['drop_next_save_response'](second)
    second.get_by_role('button', name='Save all room changes', exact=True).click()
    second.get_by_role('button', name='Check save status', exact=True).wait_for()
    draft_before_uncertain_undo = fixture['draft_state'](second)
    assert draft_before_uncertain_undo['undo'].get(fixture['room_three'])
    second.locator(f'[data-workshop-drawing="{drawing_id}"]').focus()
    second.keyboard.press('Control+z')
    assert fixture['draft_state'](second) == draft_before_uncertain_undo
    assert {key: second.locator(f'[data-workshop-drawing="{drawing_id}"]').get_attribute('data-' + key)
            for key in uncertain_key_geometry} == uncertain_key_geometry
    assert len(fixture['save_posts']()) == save_count + 1
    saved_intent = fixture['save_posts']()[-1]
    assert saved_intent['schema_version'] == 2
    room_one_width_in_save = next(room for room in saved_intent['document']['rooms']
                                  if room['id'] == fixture['room_one'])['width']
    if room_one_width_in_save != requested_room_width:
        draft_room_one_width = next(room for room in fixture['draft_state'](second)['document']['rooms']
                                    if room['id'] == fixture['room_one'])['width']
        print('ROOM-UNCERTAIN-SAVE-DIAGNOSTIC ' + json.dumps({
            'room_one_width_after_fill': room_one_width_after_fill,
            'room_one_draft_width_after_fill': room_one_draft_width_after_fill,
            'room_one_width_after_apply': room_one_width_after_apply,
            'room_one_width_in_save': room_one_width_in_save,
            'room_one_width_in_draft': draft_room_one_width,
            'saved_width_room_two': next(room for room in saved_intent['document']['rooms']
                                         if room['id'] == fixture['room_two'])['width'],
            'draft_is_dirty': fixture['draft_state'](second)['dirty'],
            'revision_before_timeout': revision_before_timeout,
            'alerts': second.get_by_role('alert').all_inner_texts(),
        }, sort_keys=True), flush=True)
    assert room_one_width_in_save == requested_room_width
    status_key = saved_intent['request_key']
    pending_rows = second.evaluate('(key) => JSON.parse(localStorage.getItem(key) || "[]")',
                                   fixture['pending_save_key'])
    pending_save = next(row for row in pending_rows if row.get('key') == status_key)
    assert pending_save['intent'] == saved_intent
    assert pending_save['group_id'] == fixture['original_group_id']
    assert pending_save['user_id'] == fixture['user_id']
    assert pending_save['identity'] == fixture['identity']
    with second.expect_response(lambda response: response.url.endswith('/workshop-api/operation/status')) as status_response:
        second.get_by_role('button', name='Check save status', exact=True).click()
    status_body = status_response.value.request.post_data_json
    status_result = status_response.value.json()
    assert status_response.value.status == 200
    assert status_body['request_key'] == status_key
    assert status_result['status'] == 'completed' and status_result['action'] == 'workshop/save'
    assert status_result['result']['revision'] == revision_before_timeout + 1
    assert fixture['document'](second)['document'] == saved_intent['document']
    second.get_by_role('button', name='Check save status', exact=True).wait_for(state='detached')
    assert 'uncertain' not in second.locator('body').inner_text().lower()
    pending_rows = second.evaluate('(key) => JSON.parse(localStorage.getItem(key) || "[]")',
                                   fixture['pending_save_key'])
    assert not any(row.get('key') == status_key for row in pending_rows)
    assert fixture['document'](second)['revision'] == revision_before_timeout + 1
    assert len(fixture['save_posts']()) == save_count + 1

    # A stale room bookmark and an ambiguous native placement both lead to a chooser.
    page.goto(fixture['invalid_room_url'])
    page.get_by_role('combobox', name='Workshop room', exact=True).wait_for()
    page.get_by_role('region', name='Workshop inspector', exact=True).get_by_text(
        'This room bookmark is no longer available. Choose a room to continue.', exact=True).wait_for()
    page.goto(fixture['ambiguous_bookmark_url'])
    page.get_by_role('group', name='Choose a room', exact=True).wait_for()
    assert fixture['native_location']('after') == fixture['native_name_before']

    # Keyboard focus and narrow layout remain usable without changing the saved plan.
    populated_document = fixture['document'](page)['document']
    bookmarked_room = next(room for room in populated_document['rooms']
                           if room['id'] == fixture['room_three'])
    bookmarked_drawing = next(drawing for drawing in bookmarked_room['objects']
                              if drawing['id'] == fixture['drawing_id'])
    assert bookmarked_drawing['location_id'] == fixture['native_location_id']
    original_page = page
    stale_draft_before_bookmark = fixture['draft_state'](original_page)
    assert stale_draft_before_bookmark and stale_draft_before_bookmark['dirty']
    stale_room = next(room for room in stale_draft_before_bookmark['document']['rooms']
                      if room['id'] == fixture['room_three'])
    assert all(drawing['id'] != fixture['drawing_id'] for drawing in stale_room['objects'])

    def assert_stale_draft_preserved() -> None:
        current_draft = fixture['draft_state'](original_page)
        assert current_draft is not None
        for key in ('identity', 'group_id', 'user_id', 'revision', 'dirty', 'document', 'undo', 'redo', 'uncertain'):
            assert current_draft[key] == stale_draft_before_bookmark[key], (
                f'The stale tab lost or changed its {key} while opening a conflicting bookmark.')

    original_page.goto(fixture['populated_bookmark_url']())
    original_page.get_by_text(
        'This drawing is not available in the requested room. Choose a drawing or room to continue.',
        exact=True).wait_for()
    assert_stale_draft_preserved()

    # A clean tab opens the current saved bookmark while the conflicted tab keeps
    # its own unsaved draft intact.
    page = original_page.context.new_page()
    page.on('request', lambda request: (workshop_view_requests.append(request.url),
            workshop_view_events.append({'event': 'request', 'at_ns': time.monotonic_ns(),
                                         'url': request.url})
            ) if '/workshop-api/workshop/view?' in request.url else None)
    page.on('response', lambda response: (workshop_view_responses.append(response),
            workshop_view_events.append({'event': 'response', 'at_ns': time.monotonic_ns(),
                                         'status': response.status, 'url': response.url})
            ) if '/workshop-api/workshop/view?' in response.url else None)
    bookmark_event_start = len(workshop_view_events)
    page.goto(fixture['populated_bookmark_url']())
    try:
        assert page.get_by_role('combobox', name='Workshop room', exact=True).input_value() == fixture['room_three']
        clean_tab_state = fixture['draft_state'](page)
        assert clean_tab_state is None or not clean_tab_state['dirty']
        if clean_tab_state:
            assert clean_tab_state['document'] == populated_document
        page.locator(f'[data-workshop-drawing="{fixture["drawing_id"]}"].is-selected').wait_for(timeout=5000)
        page.get_by_role('region', name='Workshop inspector', exact=True).get_by_role(
            'heading', name='Fixture rack drawing', exact=True).wait_for(timeout=5000)
    except Exception:
        stored_draft = fixture['draft_state'](page)
        saved_document = fixture['document'](page)['document']
        saved_bookmark_room = next(room for room in saved_document['rooms']
                                   if room['id'] == fixture['room_three'])
        print('POPULATED-BOOKMARK-SELECTION-DIAGNOSTIC ' + json.dumps({
            'url': page.url,
            'room_picker': page.get_by_role('combobox', name='Workshop room', exact=True).input_value(),
            'expected_room': fixture['room_three'],
            'expected_drawing': fixture['drawing_id'],
            'stored_draft': None if stored_draft is None else {
                key: stored_draft.get(key) for key in
                ('identity', 'group_id', 'user_id', 'revision', 'dirty', 'room_id', 'drawing_id')},
            'stored_room_drawing_ids': [] if stored_draft is None else [
                {'room_id': room['id'], 'drawing_ids': [drawing['id'] for drawing in room['objects']]}
                for room in stored_draft['document']['rooms']],
            'saved_room_drawing_ids': [drawing['id'] for drawing in saved_bookmark_room['objects']],
            'rendered_drawings': page.locator('[data-workshop-drawing]').evaluate_all(
                'nodes => nodes.map(node => ({id:node.getAttribute("data-workshop-drawing"), '
                'className:node.getAttribute("class"), location:node.getAttribute("data-location-id")}))'),
            'inspector_text': page.get_by_role('region', name='Workshop inspector', exact=True).inner_text(),
            'workshop_view_events': workshop_view_events[bookmark_event_start:],
        }, sort_keys=True), flush=True)
        raise
    assert_stale_draft_preserved()
    page.get_by_role('button', name='Browse', exact=True).click()
    inspector = page.get_by_role('region', name='Workshop inspector', exact=True)
    open_native = inspector.get_by_role('link', name='Open in C-Crate', exact=True)
    try:
        open_native.wait_for()
        assert open_native.get_attribute('href') == '/location/' + fixture['native_location_id']
        inspector.get_by_role('region', name='Authorized photos', exact=True).wait_for()
    except Exception:
        print('POPULATED-BOOKMARK-NATIVE-DIAGNOSTIC ' + json.dumps({
            'url': page.url,
            'room_picker': page.get_by_role('combobox', name='Workshop room', exact=True).input_value(),
            'selected_drawing': page.locator('[data-workshop-drawing].is-selected').get_attribute(
                'data-workshop-drawing') if page.locator('[data-workshop-drawing].is-selected').count() else None,
            'drawing_id': fixture['drawing_id'],
            'expected_location_id': fixture['native_location_id'],
            'inspector_text': inspector.inner_text(),
            'workshop_view_events': workshop_view_events[bookmark_event_start:],
        }, sort_keys=True), flush=True)
        raise
    page.set_viewport_size({'width': 800, 'height': 480})
    ensure_panel_open('Tools')
    ensure_panel_open('Inspector')
    page.screenshot(path=fixture['narrow_screenshot'], full_page=True)
    page.get_by_role('button', name='Browse', exact=True).focus()
    page.keyboard.press('Tab')
    edit_button = page.get_by_role('button', name='Edit', exact=True)
    assert edit_button.evaluate('el => document.activeElement === el && el.matches(":focus-visible")')
    focus_style = edit_button.evaluate(
        "el => ({style:getComputedStyle(el).outlineStyle,width:getComputedStyle(el).outlineWidth})")
    assert focus_style['style'] != 'none' and focus_style['width'] != '0px'
    dimensions = page.evaluate('''() => ({root: document.querySelector('.workshop-native').clientWidth,
      scroll: document.querySelector('.workshop-native').scrollWidth,
      canvas: document.querySelector('[aria-label="Room plan canvas"]').getBoundingClientRect().width})''')
    print('NARROW-WORKSHOP-DIMENSIONS ' + json.dumps(dimensions, sort_keys=True), flush=True)
    assert dimensions['scroll'] <= dimensions['root'] and dimensions['canvas'] >= 300, (
        f'Workshop layout overflowed or made its canvas too narrow: {dimensions!r}')
    page.set_viewport_size({'width': 1440, 'height': 1000})
    page.get_by_role('button', name='Edit', exact=True).click()
    saved_before_empty_room = fixture['document'](page)
    page.get_by_role('button', name='New room', exact=True).click()
    empty_room_id = page.locator('select[aria-label="Workshop room"] option').last.get_attribute('value')
    page.get_by_role('button', name='Remove room', exact=True).click()
    page.get_by_role('dialog', name='Remove room', exact=True).get_by_role(
        'button', name='Remove room', exact=True).click()
    assert empty_room_id not in page.locator('select[aria-label="Workshop room"] option').evaluate_all(
        'rows => rows.map(row => row.value)')
    assert fixture['document'](page) == saved_before_empty_room
    assert fixture['native_location']('after') == fixture['native_name_before']


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


def require_ports_free(ports: tuple[int, ...]) -> None:
    for port in ports:
        with socket.socket() as sock:
            try:
                sock.bind(('127.0.0.1', port))
            except OSError as error:
                raise RuntimeError(f'Selected fixture port {port} is already occupied.') from error


def native_pid_owns_listener(pid: int, port: int) -> bool:
    """Fail closed unless Linux procfs ties the requested loopback listener to pid."""
    proc = pathlib.Path('/proc')
    try:
        rows = (proc / 'net/tcp').read_text().splitlines()[1:]
        inodes = {row.split()[9] for row in rows
                  if len(row.split()) > 9 and row.split()[1].endswith(f':{port:04X}') and
                  row.split()[3] == '0A'}
        if not inodes:
            return False
        for descriptor in (proc / str(pid) / 'fd').iterdir():
            try:
                target = os.readlink(descriptor)
            except OSError:
                continue
            if target.startswith('socket:[') and target[8:-1] in inodes:
                return True
    except OSError:
        return False
    return False


def install_lost_save_response(page) -> None:
    state = {'armed': True}
    def lose_after_commit(route):
        if not state['armed']:
            route.continue_()
            return
        state['armed'] = False
        route.fetch(timeout=30000)  # The isolated server commits once; the browser loses only its response.
        route.abort('timedout')
    page.route('**/workshop-api/workshop/save', lose_after_commit)


def install_schema_rejection(page) -> dict:
    state = {'armed': True}
    def reject_once(route):
        if state['armed']:
            state['armed'] = False
            original = route.request.post_data_json
            wire = dict(original, schema_version=1)
            state.update(original=original, wire=wire)
            response = route.fetch(post_data=json.dumps(wire))
            state['status'] = response.status
            route.fulfill(response=response)
        else:
            route.continue_()
    page.route('**/workshop-api/workshop/save', reject_once)
    return state


def test_terminal_room_drafts(page, fixture) -> None:
    """Exercise the real touch terminal controls against the disposable candidate."""
    page.set_viewport_size({'width': 800, 'height': 480})
    page.goto(fixture['companion_url'], wait_until='domcontentloaded')
    page.get_by_role('button', name='Edit layout', exact=True).click()
    try:
        page.get_by_role('heading', name='Workshop planner', exact=True).wait_for(timeout=5000)
    except Exception:
        page.screenshot(path=fixture['narrow_screenshot'], full_page=True)
        state = page.evaluate('''() => {
          const read = source => { try { return (0, eval)(source); } catch (error) { return String(error); } };
          return {route:read('routeRevision'), openGeneration:read('task5OpenGeneration'),
            taskContext:read('task5Context'), taskDocument:read('task5Document'),
            stale:read('task5StaleMessage'), routeTitle:read('routeTitle')};
        }''')
        raise AssertionError('Terminal planner did not open; body=' + repr(page.locator('body').inner_text()) +
                             '; page_errors=' + repr(fixture['browser_errors']) +
                             '; requests=' + repr(fixture['browser_requests'][-12:]) +
                             '; responses=' + repr(fixture['browser_responses'][-12:]) +
                             '; state=' + repr(state))
    print('TERMINAL_CHECKPOINT planner-open', flush=True)
    assert page.evaluate('''() => {
      const original=routeTitle; routeTitle='Workshop'; const legacy=workshopIsMapPage();
      routeTitle='Workshop planner'; const planner=workshopIsMapPage(); routeTitle='Storage';
      const outside=workshopIsMapPage(); routeTitle=original;
      return {legacy,planner,outside};
    }''') == {'legacy': True, 'planner': True, 'outside': False}
    room_picker = page.get_by_role('combobox', name='Workshop room', exact=True)
    room_picker.wait_for()
    controls = page.locator('[data-room-control]')
    heights = controls.evaluate_all('rows => rows.map(row => row.getBoundingClientRect().height)')
    assert heights and all(height >= 44 for height in heights), heights

    def server_document():
        return page.evaluate('''async () => {
          const response = await fetch('/workshop/get', {method:'POST',
            headers:{'Content-Type':'application/json'}, body:'{}'});
          if (!response.ok) throw new Error('Workshop document unavailable');
          return response.json();
        }''')

    initial = server_document()
    before_browse = json.dumps(initial['document'], sort_keys=True)
    before_revision = initial['revision']
    page.get_by_role('button', name='Browse', exact=True).click()
    page.get_by_role('button', name='Pan right', exact=True).click()
    page.get_by_role('button', name='Zoom in', exact=True).click()
    after_browse = server_document()
    assert json.dumps(after_browse['document'], sort_keys=True) == before_browse
    assert after_browse['revision'] == before_revision

    page.get_by_role('button', name='Edit', exact=True).click()
    if not initial['document']['rooms']:
        page.get_by_role('button', name='New room', exact=True).click()
        page.get_by_label('Room title', exact=True).fill('Terminal room one')
        page.get_by_role('button', name='Apply room changes', exact=True).click()
    first_room = room_picker.input_value()
    page.get_by_role('button', name='Rack', exact=True).click()
    canvas = page.get_by_role('img', name='Overhead workshop floor plan', exact=True)
    box = canvas.bounding_box()
    page.mouse.click(box['x'] + box['width'] * .35, box['y'] + box['height'] * .35)
    drawing = page.locator('[data-workshop-drawing].is-selected')
    drawing_id = drawing.get_attribute('data-workshop-drawing')
    assert drawing_id and drawing_id.count('-') == 4
    page.get_by_label('Native storage location', exact=True).select_option(fixture['native_location_id'])
    page.get_by_label('Position X in feet', exact=True).fill('2.25')
    page.get_by_label('Position Y in feet', exact=True).fill('2.5')
    page.get_by_role('button', name='Apply geometry', exact=True).click()
    first_identity = {'id': drawing_id, 'location_id': fixture['native_location_id']}
    assert drawing.get_attribute('data-location-id') == first_identity['location_id']
    first_room_document = fixture['terminal_draft_state'](page, initial['workshop_context'])['document']['rooms']
    assert next(room for room in first_room_document if room['id'] == first_room)['objects'][0]['id'] == drawing_id

    page.get_by_role('button', name='New room', exact=True).click()
    page.get_by_label('Room title', exact=True).fill('Terminal room two')
    page.get_by_role('button', name='Apply room changes', exact=True).click()
    second_room = room_picker.input_value()
    page.get_by_role('button', name='Table', exact=True).click()
    box = canvas.bounding_box()
    page.mouse.click(box['x'] + box['width'] * .55, box['y'] + box['height'] * .45)
    second_drawing = page.locator('[data-workshop-drawing].is-selected').get_attribute('data-workshop-drawing')
    page.get_by_role('button', name='Undo', exact=True).click()
    rooms_after_undo = fixture['terminal_draft_state'](page, initial['workshop_context'])['document']['rooms']
    assert next(room for room in rooms_after_undo if room['id'] == second_room)['objects'] == []
    assert next(room for room in rooms_after_undo if room['id'] == first_room)['objects'][0]['id'] == drawing_id
    page.get_by_role('button', name='Redo', exact=True).click()
    assert second_drawing and page.locator(f'[data-workshop-drawing="{second_drawing}"]').count() == 1
    rooms_after_redo = fixture['terminal_draft_state'](page, initial['workshop_context'])['document']['rooms']
    assert next(room for room in rooms_after_redo if room['id'] == second_room)['objects'][0]['id'] == second_drawing
    room_picker.select_option(second_room)
    page.locator(f'[data-workshop-drawing="{second_drawing}"]').click()
    page.get_by_label('Native storage location', exact=True).select_option(fixture['native_location_id'])
    assert page.evaluate('id => task5Document.rooms.find(room=>room.id===task5ActiveRoom).objects.find(row=>row.id===id).location_id', second_drawing) == fixture['native_location_id']
    # Persist the fixture placements before exercising native-to-map matching;
    # the native view API intentionally reads the saved document, not local drafts.
    page.evaluate('''async () => {
      const document=task5Clone(task5Document),revision=workshopState.revision;
      const result=await api('/workshop/save',{schema_version:2,revision,document,
        request_key:crypto.randomUUID()},task5Header());
      workshopState.revision=result.revision;workshopState.document=task5Clone(result.document);
      task5Document=task5Clone(result.document);task5BaseRevision=result.revision;
      task5UndoByRoom.clear();task5RedoByRoom.clear();task5Touch();workshopRender();
    }''')
    initial = server_document()
    fixture['clear_save_posts']()
    unique_placement = page.evaluate('''async locationId => {
      const room={id:crypto.randomUUID(),location_id:null,name:'Terminal unique match room',
        width:20,height:16,unit:'ft',approximate:false,objects:[]};
      const drawing={id:crypto.randomUUID(),kind:'Kiosk',name:'Unique match drawing',x:3,y:3,
        width:2,height:2,rotation:0,location_id:locationId};
      room.objects.push(drawing);task5Document.rooms.push(room);task5EnsureHistory(room);
      const result=await api('/workshop/save',{schema_version:2,revision:workshopState.revision,
        document:task5Clone(task5Document),request_key:crypto.randomUUID()},task5Header());
      workshopState.revision=result.revision;workshopState.document=task5Clone(result.document);
      task5Document=task5Clone(result.document);task5BaseRevision=result.revision;
      task5ActiveRoom=room.id;task5Selected=drawing.id;task5Touch();workshopRender();
      return {room:room.id,drawing:drawing.id};
    }''', fixture['other_native_location_id'])
    initial = server_document()
    before_revision = initial['revision']
    fixture['clear_save_posts']()
    room_picker.select_option(first_room)
    page.locator(f'[data-workshop-drawing="{drawing_id}"]').click()

    # Linked drawings in the Terminal planner must hydrate native hierarchy and
    # status details through the same route guards as the legacy Workshop map.
    room_picker.select_option(first_room)
    page.locator(f'[data-workshop-drawing="{drawing_id}"]').click()
    native_panel = page.get_by_label('Native storage and equipment', exact=True)
    native_panel.get_by_text('Full path:', exact=False).wait_for(timeout=5000)
    native_panel.get_by_text('assigned ·', exact=False).wait_for(timeout=5000)
    assert fixture['native_location_id'] in native_panel.inner_text()
    try:
        page.wait_for_function("""() => {
          const images=[...document.querySelectorAll('.workshop-native-details img')];
          for(const image of images) image.loading='eager';
          return images.some(image => image.complete && image.naturalWidth>0);
        }""", timeout=10000)
    except Exception as error:
        photo_state = page.evaluate("""() => [...document.querySelectorAll('.workshop-native-details img')]
          .map(image=>({src:image.src,complete:image.complete,width:image.naturalWidth,height:image.naturalHeight}))""")
        raise AssertionError('Authorized native photo did not load; panel=' + repr(native_panel.inner_text()) +
            '; images=' + repr(photo_state) +
            '; responses=' + repr(fixture['browser_responses'][-12:])) from error
    print('TERMINAL_CHECKPOINT native-photo', flush=True)
    # A fresh hierarchy response from another collection/actor must freeze an
    # Edit draft until an explicit planner reopen reviews the active context.
    page.get_by_role('button', name='Edit', exact=True).click()
    assert page.evaluate("() => { const object=task5Object(),room=task5Room(); const nextX=object.x+object.width+.25<=room.width?object.x+.25:object.x-.25; return task5ApplyGeometry(object,{name:{field:{value:object.name}},x:{field:{value:String(nextX)}},y:{field:{value:String(object.y)}},width:{field:{value:String(object.width)}},height:{field:{value:String(object.height)}},rotation:{field:{value:String(object.rotation/90)}}}) }") is True
    edit_gate = page.evaluate("() => ({mode:task5Mode,dirty:task5IsDirty(),canMutate:task5CanMutate()})")
    assert edit_gate['mode']=='Edit' and edit_gate['dirty'] and edit_gate['canMutate'], edit_gate
    assert page.get_by_role('button', name='Save all room changes', exact=True).is_enabled()
    page_snapshot = page.evaluate("() => ({context:task5Clone(task5Context),document:task5Clone(task5Document),undo:Object.fromEntries(task5UndoByRoom),redo:Object.fromEntries(task5RedoByRoom),stored:localStorage.getItem(task5DraftKey),revision:workshopState.revision,baseRevision:task5BaseRevision,mode:task5Mode,dirty:task5IsDirty(),locations:task5Clone(workshopState.locations),parents:task5Clone(workshopState.parents),pending:task5Clone(task5PendingIntent),pendingKey:task5PendingKey})")
    mismatch_save_count = len(fixture['save_posts']())
    def return_other_workshop_context(route):
        response = route.fetch()
        payload = response.json()
        payload['workshop_context'] = {'group_id':str(uuid.uuid4()),'actor_id':str(uuid.uuid4())}
        payload['locations'] = [*payload.get('locations', []), {'id':'other-context-location','name':'Other context location','parent_id':None,'isLocation':True}]
        payload['parents'] = [*payload.get('parents', []), {'id':'other-context-location','name':'Other context location','parent_id':None,'kind':'Location','isLocation':True}]
        route.fulfill(response=response, json=payload)
    page.route('**/workshop/get', return_other_workshop_context)
    with page.expect_response(lambda response: response.url.endswith('/workshop/get') and response.request.method == 'POST'):
        native_panel.get_by_role('button', name='Refresh native hierarchy', exact=True).click()
    mismatch_after = page.evaluate("() => ({context:task5Clone(task5Context),document:task5Clone(task5Document),undo:Object.fromEntries(task5UndoByRoom),redo:Object.fromEntries(task5RedoByRoom),stored:localStorage.getItem(task5DraftKey),revision:workshopState.revision,baseRevision:task5BaseRevision,mode:task5Mode,dirty:task5IsDirty(),canMutate:task5CanMutate(),locked:task5ContextMismatch,locations:task5Clone(workshopState.locations),parents:task5Clone(workshopState.parents),pending:task5Clone(task5PendingIntent),pendingKey:task5PendingKey,message:task5StaleMessage})")
    assert mismatch_after['message'] and 'collection or service actor changed' in mismatch_after['message'].lower(), mismatch_after
    assert {key:mismatch_after[key] for key in page_snapshot} == page_snapshot, mismatch_after
    assert mismatch_after['locked'] and not mismatch_after['canMutate'], mismatch_after
    assert page.get_by_role('button', name='Save all room changes', exact=True).is_disabled()
    geometry_attempt = page.evaluate("() => { const object=task5Object(),room=task5Room(); const nextX=object.x+object.width+.25<=room.width?object.x+.25:object.x-.25; return task5ApplyGeometry(object,{name:{field:{value:object.name}},x:{field:{value:String(nextX)}},y:{field:{value:String(object.y)}},width:{field:{value:String(object.width)}},height:{field:{value:String(object.height)}},rotation:{field:{value:String(object.rotation/90)}}}) }")
    assert geometry_attempt is False
    assert page.evaluate("() => ({document:task5Clone(task5Document),undo:Object.fromEntries(task5UndoByRoom),redo:Object.fromEntries(task5RedoByRoom),stored:localStorage.getItem(task5DraftKey),revision:workshopState.revision,baseRevision:task5BaseRevision})") == {key:page_snapshot[key] for key in ('document','undo','redo','stored','revision','baseRevision')}
    page.get_by_role('button', name='Save all room changes', exact=True).click(force=True)
    page.wait_for_timeout(100)
    assert page.get_by_role('dialog', name='Confirm room plan save', exact=True).count()==0
    assert len(fixture['save_posts']()) == mismatch_save_count
    page.unroute('**/workshop/get', return_other_workshop_context)
    with page.expect_response(lambda response: response.url.endswith('/workshop/get') and response.request.method == 'POST'):
        native_panel.get_by_role('button', name='Refresh native hierarchy', exact=True).click()
    assert page.evaluate("() => task5ContextMismatch&&!task5CanMutate()")
    assert page.get_by_role('button', name='Save all room changes', exact=True).is_disabled()
    page.evaluate('() => workshopOpen()')
    page.get_by_role('heading', name='Workshop planner', exact=True).wait_for()
    reopened_gate = page.evaluate("() => ({locked:task5ContextMismatch,canMutate:task5CanMutate(),dirty:task5IsDirty()})")
    assert not reopened_gate['locked'] and reopened_gate['canMutate'] and reopened_gate['dirty'], reopened_gate
    assert server_document()['revision'] == page_snapshot['revision']
    print('TERMINAL_CHECKPOINT context-lock', flush=True)
    room_picker.select_option(first_room)
    page.get_by_label('Native room storage root', exact=True).select_option(fixture['native_location_id'])
    page.get_by_role('button', name='Apply room changes', exact=True).click()
    page.locator(f'[data-workshop-drawing="{drawing_id}"]').click()
    link_before_reject = page.evaluate('''() => ({document:task5Clone(task5Document),
      undo:Object.fromEntries(task5UndoByRoom),redo:Object.fromEntries(task5RedoByRoom)})''')
    assert page.evaluate('''id=>!task5WithinRoot(id,task5Room().location_id)''', fixture['other_native_location_id'])
    page.get_by_label('Native storage location', exact=True).select_option(fixture['other_native_location_id'])
    page.wait_for_timeout(100)
    rejected_link_state = page.evaluate('''() => ({mode:task5Mode,canMutate:task5CanMutate(),message:task5StaleMessage,
      selected:task5Selected,root:task5Room()?.location_id,parents:workshopParents().map(row=>({id:row.id,parent_id:row.parent_id})),
      current:task5Object()?.location_id,control:document.querySelector('[aria-label="Native storage location"]')?.value})''')
    assert 'within this room’s storage root' in rejected_link_state['message'], rejected_link_state
    assert page.get_by_label('Native storage location', exact=True).input_value() == fixture['native_location_id']
    assert page.evaluate('''() => ({document:task5Clone(task5Document),
      undo:Object.fromEntries(task5UndoByRoom),redo:Object.fromEntries(task5RedoByRoom)})''') == link_before_reject

    # The touch-only field path opens the shared on-screen keyboard and writes
    # back into the same input used by the room inspector.
    touch_info = page.evaluate('''() => {
      window.__task5TouchRestore={matchMedia:window.matchMedia};
      window.matchMedia=query=>({matches:query==='(pointer:fine)'?false:window.__task5TouchRestore.matchMedia(query).matches});
      const probe=task5Input('Touch keyboard probe','', 'text');
      document.querySelector('.task5-inspector').append(probe.wrap);
      return {readOnly:probe.field.readOnly, inputMode:probe.field.inputMode};
    }''')
    assert touch_info == {'readOnly': True, 'inputMode': 'none'}
    page.get_by_label('Touch keyboard probe', exact=True).click()
    page.get_by_role('dialog', name='Touchscreen search keyboard', exact=True).wait_for()
    page.get_by_role('button', name='Key A', exact=True).click()
    page.get_by_role('button', name='Done', exact=True).click()
    assert page.get_by_label('Touch keyboard probe', exact=True).input_value() == 'a'
    print('TERMINAL_CHECKPOINT touch-keyboard', flush=True)
    page.evaluate('''() => { window.matchMedia=window.__task5TouchRestore.matchMedia;
      delete window.__task5TouchRestore;
      document.querySelector('[aria-label="Touch keyboard probe"]')?.closest('label')?.remove(); }''')

    page.get_by_role('button', name='New room', exact=True).click()
    page.get_by_label('Room title', exact=True).fill('Terminal incompatible root')
    page.get_by_label('Native room storage root', exact=True).select_option(fixture['other_native_location_id'])
    page.get_by_role('button', name='Apply room changes', exact=True).click()
    invalid_root_room = room_picker.input_value()
    room_picker.select_option(first_room)
    page.locator(f'[data-workshop-drawing="{drawing_id}"]').click()

    # Browse is read-only even when history is already seeded. Exercise both
    # rendered controls and mutation entry points, then compare draft/history.
    page.get_by_role('button', name='Browse', exact=True).click()
    browse_snapshot = page.evaluate('''() => ({document:task5Clone(task5Document),
      undo:Object.fromEntries(task5UndoByRoom),redo:Object.fromEntries(task5RedoByRoom),
      stored:localStorage.getItem(task5DraftKey),revision:workshopState.revision})''')
    browse_server_snapshot = server_document()
    assert page.get_by_role('button', name='New room', exact=True).count() == 0
    assert page.get_by_role('button', name='Undo', exact=True).is_disabled()
    assert page.get_by_role('button', name='Redo', exact=True).is_disabled()
    native_panel = page.get_by_label('Native storage and equipment', exact=True)
    for action in ('Resolve code or scan result','Scan native code','Refresh native hierarchy','Refresh native status'):
        assert native_panel.get_by_role('button', name=action, exact=True).is_enabled(), action
    browse_search = native_panel.get_by_label('Search native equipment and storage', exact=True)
    browse_search.fill(fixture['native_location_id'])
    native_result = native_panel.locator(f'[data-native-id="{fixture["native_location_id"]}"]')
    assert native_result.is_enabled()
    native_result.click()
    native_panel.get_by_text('Choose a map representation', exact=True).wait_for()
    duplicate_choices = page.evaluate('''() => ({matches:workshopViewData?.selection?.matches,
      room:task5ActiveRoom, buttons:[...document.querySelectorAll('.workshop-native-details button')]
        .map(button=>({text:button.textContent,disabled:button.disabled}))})''')
    print('TERMINAL_CHECKPOINT duplicate-choices ' + repr(duplicate_choices), flush=True)
    assert len(duplicate_choices['matches'] or []) == 2, duplicate_choices
    assert any(row['text'].startswith('Table ·') and not row['disabled']
        for row in duplicate_choices['buttons']), duplicate_choices
    native_panel.get_by_role('button', name=re.compile('^Table ·'), exact=False).click()
    assert room_picker.input_value() == second_room
    assert page.locator(f'[data-workshop-drawing="{second_drawing}"]').get_attribute('class') == 'is-selected'
    # A unique native placement in another room must flow through the effective
    # resolve/search selection override without the Task5 renderer replacing it.
    room_picker.select_option(first_room)
    browse_search.fill(fixture['other_native_location_id'])
    unique_result = native_panel.locator(f'[data-native-id="{fixture["other_native_location_id"]}"]')
    with page.expect_response(lambda response: response.url.endswith('/workshop/view') and
        response.request.method == 'POST' and
        (response.request.post_data_json or {}).get('entity_id') == fixture['other_native_location_id']):
        unique_result.click()
    try:
        page.wait_for_function('id => workshopEntityId === id && workshopViewAvailable',
                               arg=fixture['other_native_location_id'])
    except Exception:
        try:
            view_state = page.evaluate('''() => ({entity:typeof workshopEntityId==='undefined'?null:workshopEntityId,
              available:typeof workshopViewAvailable==='undefined'?null:workshopViewAvailable,
              error:typeof workshopViewError==='undefined'?null:workshopViewError,
              data:typeof workshopViewData==='undefined'?null:workshopViewData})''')
        except Exception as diagnostic_error:
            view_state = {'diagnostic_error': str(diagnostic_error)}
        view_responses = []
        for response in fixture['workshop_view_responses'][-12:]:
            try:
                body = response.body()
                body_text = body.decode('utf-8', errors='replace')
                content_type = response.headers.get('content-type')
                try:
                    body_data = json.loads(body_text)
                except (json.JSONDecodeError, TypeError):
                    body_data = None
                view_responses.append({'status': response.status, 'url': response.url,
                    'content_type': content_type, 'body_bytes': len(body),
                    'body_text': body_text[:4000], 'body_json': body_data})
            except Exception as diagnostic_error:
                view_responses.append({'url': response.url,
                    'diagnostic_error': str(diagnostic_error)})
        print('TERMINAL_WORKSHOP_VIEW_WAIT_FAILURE ' + repr({
            'state': view_state,
            'page_errors': fixture['browser_errors'],
            'requests': fixture['workshop_view_requests'][-12:],
            'responses': view_responses,
        }), flush=True)
        try:
            page.screenshot(path=fixture['terminal_view_failure_screenshot'], full_page=True)
        except Exception as diagnostic_error:
            print('TERMINAL_WORKSHOP_VIEW_SCREENSHOT_FAILURE ' + repr(str(diagnostic_error)), flush=True)
        raise
    unique_state = page.evaluate('''() => ({routeTitle,entity:workshopEntityId,available:workshopViewAvailable,
      selection:workshopViewData?.selection,active:task5ActiveRoom,selected:task5Selected,
      expectedRooms:task5Document.rooms.filter(room=>room.objects.some(row=>
        row.id===task5Selected)).map(room=>room.id)})''')
    unique_matches = unique_state['selection'] and unique_state['selection'].get('matches') or []
    assert len(unique_matches) == 1 and unique_matches[0]['drawing_id'] == unique_placement['drawing'], unique_state
    page.wait_for_function('room => task5ActiveRoom === room', arg=unique_placement['room'])
    assert room_picker.input_value() == unique_placement['room']
    assert page.locator(f'[data-workshop-drawing="{unique_placement["drawing"]}"]').get_attribute('class') == 'is-selected'
    assert page.evaluate('''id=>workshopEntityId===id&&task5ActiveRoom===task5Document.rooms.find(
      room=>room.objects.some(row=>row.id===task5Selected)).id''', fixture['other_native_location_id'])
    # Resolve is a native read and scan wiring is exercised with only the kiosk
    # scan button intercepted; no camera, serial reader or physical device starts.
    browse_search = page.get_by_label('Search native equipment and storage', exact=True)
    browse_search.fill('/item/' + fixture['native_item_id'])
    with page.expect_response(lambda response: response.url.endswith('/workshop/resolve') and
                              response.request.method == 'POST'):
        native_panel.get_by_role('button', name='Resolve code or scan result', exact=True).click()
    native_panel.get_by_text('Full path:', exact=False).wait_for()
    scan_probe = page.evaluate('''() => {
      const button=document.querySelector('#scan'), original=button.onclick;
      window.__task5ScanProbe={button,original,calls:0};
      button.onclick=()=>{window.__task5ScanProbe.calls++};
      return true;
    }''')
    assert scan_probe
    native_panel.get_by_role('button', name='Scan native code', exact=True).click()
    assert page.evaluate('''() => ({purpose:scanPurpose,calls:window.__task5ScanProbe.calls})''') == {
        'purpose':'workshop_map','calls':1}
    page.evaluate('''() => {window.__task5ScanProbe.button.onclick=window.__task5ScanProbe.original;
      delete window.__task5ScanProbe;scanPurpose=null}''')
    with page.expect_response(lambda response: response.url.endswith('/workshop/get') and
                              response.request.method == 'POST'):
        native_panel.get_by_role('button', name='Refresh native hierarchy', exact=True).click()
    with page.expect_response(lambda response: response.url.endswith('/workshop/view') and
                              response.request.method == 'POST'):
        native_panel.get_by_role('button', name='Refresh native status', exact=True).click()
    browse_search.fill(fixture['browse_rack_id'])
    native_panel.locator(f'[data-native-id="{fixture["browse_rack_id"]}"]').click()
    native_panel.get_by_text('Rack front view', exact=False).wait_for()
    shelf_order = native_panel.get_by_role('button', name='Review shelf order', exact=True)
    assert shelf_order.is_disabled(), 'Browse must keep shelf-order mutation locked'
    native_panel.get_by_role('button', name=re.compile('Fixture browse shelf'), exact=False).click()
    native_panel.get_by_role('heading', name=re.compile('Fixture browse shelf')).wait_for()
    page.wait_for_function('''() => [...document.querySelectorAll('.workshop-native-details img')]
      .some(image=>{image.loading='eager';return image.complete&&image.naturalWidth>0})''', timeout=10000)
    assert native_panel.get_by_role('link', name='Edit native photos', exact=True).is_enabled()
    room_picker.select_option(first_room)
    browse_after_native = page.evaluate('''() => ({document:task5Clone(task5Document),
      undo:Object.fromEntries(task5UndoByRoom),redo:Object.fromEntries(task5RedoByRoom),revision:workshopState.revision})''')
    assert browse_after_native == {key:browse_snapshot[key] for key in ('document','undo','redo','revision')}
    fixture['mutate_native'](fixture['refresh_root_id'], name='Fixture refreshed hierarchy root')
    fixture['mutate_native'](fixture['refresh_child_id'], parentId=fixture['other_native_location_id'])
    page.evaluate('''ids => {task5RefreshRootId=ids.root;task5RefreshChildId=ids.child}''',
                  {'root':fixture['refresh_root_id'],'child':fixture['refresh_child_id']})
    refresh_plan_snapshot = page.evaluate('''() => ({document:task5Clone(task5Document),
      undo:Object.fromEntries(task5UndoByRoom),redo:Object.fromEntries(task5RedoByRoom),
      stored:localStorage.getItem(task5DraftKey),revision:workshopState.revision})''')
    refresh_server_snapshot = server_document()
    refresh_save_count = len(fixture['save_posts']())
    with page.expect_response(lambda response: response.url.endswith('/workshop/get') and
                              response.request.method == 'POST'):
        native_panel.get_by_role('button', name='Refresh native hierarchy', exact=True).click()
    refreshed_native_snapshot = page.evaluate('''() => ({document:task5Clone(task5Document),
      undo:Object.fromEntries(task5UndoByRoom),redo:Object.fromEntries(task5RedoByRoom),
      stored:localStorage.getItem(task5DraftKey),revision:workshopState.revision,
      root:workshopParents().find(row=>row.id===task5RefreshRootId),
      child:workshopParents().find(row=>row.id===task5RefreshChildId),
      path:workshopNativePath(workshopParents().find(row=>row.id===task5RefreshChildId))})''')
    assert refreshed_native_snapshot['root']['name'] == 'Fixture refreshed hierarchy root', refreshed_native_snapshot
    assert refreshed_native_snapshot['child']['parent_id'] == fixture['other_native_location_id'], refreshed_native_snapshot
    assert refreshed_native_snapshot['path'].endswith(
      'Fixture Other Native Root / Fixture refreshed hierarchy child'), refreshed_native_snapshot
    browse_search.fill('Fixture refreshed hierarchy child')
    refreshed_path_button = native_panel.locator(f'[data-native-id="{fixture["refresh_child_id"]}"]')
    refreshed_path_button.wait_for()
    assert 'Fixture Other Native Root / Fixture refreshed hierarchy child' in refreshed_path_button.inner_text()
    assert {key:refreshed_native_snapshot[key] for key in ('document','undo','redo','stored','revision')} == {
      key:refresh_plan_snapshot[key] for key in ('document','undo','redo','stored','revision')}
    assert server_document() == refresh_server_snapshot
    assert len(fixture['save_posts']()) == refresh_save_count
    browse_mutation_snapshot = page.evaluate('''() => ({document:task5Clone(task5Document),
      undo:Object.fromEntries(task5UndoByRoom),redo:Object.fromEntries(task5RedoByRoom),
      stored:localStorage.getItem(task5DraftKey),revision:workshopState.revision})''')
    page.evaluate('''() => { task5Undo(); task5Redo(); task5AddRoom(); task5AddDrawing('Cabinet',3,3);
      workshopMoveDrawing(task5Selected, task5Document.rooms.find(r=>r.id!==task5ActiveRoom).id, 1, 1);
      workshopRemoveEmptyRoom(task5Document.rooms.find(r=>r.id!==task5ActiveRoom).id); }''')
    browse_after = page.evaluate('''() => ({document:task5Clone(task5Document),
      undo:Object.fromEntries(task5UndoByRoom),redo:Object.fromEntries(task5RedoByRoom),
      stored:localStorage.getItem(task5DraftKey),revision:workshopState.revision})''')
    assert browse_after == browse_mutation_snapshot
    browse_server_after = server_document()
    assert {key:browse_server_after[key] for key in ('document','revision')} == {
      key:refresh_server_snapshot[key] for key in ('document','revision')}

    # A transfer either updates both rooms and records paired history, or does
    # nothing. Undo/redo must move the stable drawing UUID between both rooms.
    page.get_by_role('button', name='Edit', exact=True).click()
    page.locator(f'[data-workshop-drawing="{drawing_id}"]').click()
    transfer_result = page.evaluate('''({id,source,target}) => {
      try { return {error:null,result:workshopMoveDrawing(id,target,2,2)} }
      catch(error) { return {error:error.message,result:null} }
    }''', {'id': drawing_id, 'source': first_room, 'target': second_room})
    assert transfer_result == {'error': None, 'result': True}, transfer_result
    transfer_doc = page.evaluate('''() => task5Clone(task5Document)''')
    source_after_transfer = next(room for room in transfer_doc['rooms'] if room['id'] == first_room)
    target_after_transfer = next(room for room in transfer_doc['rooms'] if room['id'] == second_room)
    assert drawing_id not in [row['id'] for row in source_after_transfer['objects']]
    assert drawing_id in [row['id'] for row in target_after_transfer['objects']]
    page.get_by_role('button', name='Undo', exact=True).click()
    undo_doc = page.evaluate('''() => task5Clone(task5Document)''')
    assert drawing_id in [row['id'] for row in next(r for r in undo_doc['rooms'] if r['id'] == first_room)['objects']]
    assert drawing_id not in [row['id'] for row in next(r for r in undo_doc['rooms'] if r['id'] == second_room)['objects']]
    page.get_by_role('button', name='Redo', exact=True).click()
    redo_doc = page.evaluate('''() => task5Clone(task5Document)''')
    assert drawing_id not in [row['id'] for row in next(r for r in redo_doc['rooms'] if r['id'] == first_room)['objects']]
    assert drawing_id in [row['id'] for row in next(r for r in redo_doc['rooms'] if r['id'] == second_room)['objects']]
    before_rejected_transfer = page.evaluate('''() => ({document:task5Clone(task5Document),
      undo:Object.fromEntries(task5UndoByRoom),redo:Object.fromEntries(task5RedoByRoom)})''')
    rejected_transfer = page.evaluate('''({id,target}) => {
      try { return {error:null,result:workshopMoveDrawing(id,target,999,999)} }
      catch(error) { return {error:error.message,result:null} }
    }''', {'id': drawing_id, 'target': first_room})
    after_rejected_transfer = page.evaluate('''() => ({document:task5Clone(task5Document),
      undo:Object.fromEntries(task5UndoByRoom),redo:Object.fromEntries(task5RedoByRoom)})''')
    assert rejected_transfer['result'] is False
    assert after_rejected_transfer == before_rejected_transfer
    invalid_root_before = page.evaluate('''() => ({document:task5Clone(task5Document),
      undo:Object.fromEntries(task5UndoByRoom),redo:Object.fromEntries(task5RedoByRoom)})''')
    native_before_invalid_transfer = fixture['native_location']('after')
    invalid_root_move = page.evaluate('''({id,target}) => ({result:workshopMoveDrawing(id,target,2,2),
      message:task5StaleMessage})''', {'id': drawing_id, 'target': invalid_root_room})
    invalid_root_after = page.evaluate('''() => ({document:task5Clone(task5Document),
      undo:Object.fromEntries(task5UndoByRoom),redo:Object.fromEntries(task5RedoByRoom)})''')
    assert invalid_root_move['result'] is False
    assert 'native storage root' in invalid_root_move['message']
    assert invalid_root_after == invalid_root_before
    assert fixture['native_location']('after') == native_before_invalid_transfer
    # Restore the stable drawing to its original room before the fractional
    # boundary interaction assertions below.
    assert page.evaluate('''({id,target}) => workshopMoveDrawing(id,target,2,2)''',
        {'id': drawing_id, 'target': first_room}) is True
    print('TERMINAL_CHECKPOINT root-validation', flush=True)

    # Edge drag, resize, and rotation preserve the authoritative unrotated
    # footprint inside a fractional legacy room boundary.
    page.get_by_role('combobox', name='Workshop room', exact=True).select_option(first_room)
    page.get_by_label('Room width in feet', exact=True).fill('17.13')
    page.get_by_role('button', name='Apply room changes', exact=True).click()
    page.locator(f'[data-workshop-drawing="{drawing_id}"]').click()
    page.get_by_label('Position X in feet', exact=True).fill('14')
    page.get_by_role('button', name='Apply geometry', exact=True).click()
    canvas_box = page.get_by_role('img', name='Overhead workshop floor plan', exact=True).bounding_box()
    drawing_box = page.locator(f'[data-workshop-drawing="{drawing_id}"]').bounding_box()
    page.mouse.move(drawing_box['x'] + drawing_box['width'] / 2,
                    drawing_box['y'] + drawing_box['height'] / 2)
    page.mouse.down()
    page.mouse.move(canvas_box['x'] + canvas_box['width'] - 1,
                    drawing_box['y'] + drawing_box['height'] / 2)
    page.mouse.up()
    edge_drawing = page.locator(f'[data-workshop-drawing="{drawing_id}"]')
    edge_x = float(edge_drawing.get_attribute('data-x'))
    edge_width = float(edge_drawing.get_attribute('data-width'))
    assert edge_x + edge_width <= 17.13, (edge_x, edge_width)
    resize = edge_drawing.locator('[data-resize-handle="true"]')
    resize_box = resize.bounding_box()
    page.mouse.move(resize_box['x'] + resize_box['width'] / 2,
                    resize_box['y'] + resize_box['height'] / 2)
    page.mouse.down()
    page.mouse.move(canvas_box['x'] + canvas_box['width'] - 1,
                    canvas_box['y'] + canvas_box['height'] - 1)
    page.mouse.up()
    bounded = page.locator(f'[data-workshop-drawing="{drawing_id}"]')
    assert float(bounded.get_attribute('data-x')) + float(bounded.get_attribute('data-width')) <= 17.13
    room_height = page.evaluate('''() => task5Room().height''')
    assert float(bounded.get_attribute('data-y')) + float(bounded.get_attribute('data-height')) <= room_height
    page.get_by_role('button', name='Rotate clockwise 90 degrees', exact=True).click()
    rotated = page.locator(f'[data-workshop-drawing="{drawing_id}"]')
    assert rotated.locator('rect:not([data-resize-handle])').get_attribute('transform') is None
    assert 'rotate(90' in rotated.locator('text').get_attribute('transform')
    assert float(rotated.get_attribute('data-x')) + float(rotated.get_attribute('data-width')) <= 17.13
    print('TERMINAL_CHECKPOINT geometry', flush=True)

    # Room selection through keyboard must select the requested stable UUID.
    room_picker.select_option(second_room)
    room_picker.focus()
    room_picker.press('ArrowUp')
    room_picker.press('Enter')
    assert room_picker.input_value() == first_room
    assert page.locator(f'[data-workshop-drawing="{drawing_id}"]').count() == 1

    # Revoking management while the save confirmation is open must leave the
    # server revision unchanged and must not create a pending save intent.
    save_gate = page.evaluate('''() => ({mode:task5Mode,canMutate:task5CanMutate(),dirty:task5IsDirty(),
      busy:task5SaveBusy,conflict:task5Conflict,canManage:workshopState.can_manage,
      pending:!!task5PendingIntent,active:task5ActiveRoom,routeTitle,routeRevision,
      button:document.querySelector('.task5-toolbar button')?.outerHTML})''')
    assert save_gate['canMutate'] and save_gate['dirty'], save_gate
    page.get_by_role('button', name='Save all room changes', exact=True).click()
    print('TERMINAL_CHECKPOINT save-click ' + repr(page.evaluate('''() => ({dialog:!!document.querySelector('.workshop-dialog'),
      body:document.body.innerText.slice(-500),mode:task5Mode,canMutate:task5CanMutate(),dirty:task5IsDirty(),
      pending:!!task5PendingIntent,message:task5StaleMessage,routeTitle,routeRevision,
      plannerButtons:[...document.querySelectorAll('.task5-toolbar button')].map(b=>({text:b.textContent,type:b.type,disabled:b.disabled,html:b.outerHTML,form:!!b.closest('form')}))})''')), flush=True)
    page.get_by_role('dialog', name='Confirm room plan save', exact=True).wait_for()
    fixture['set_open_admin'](False)
    page.get_by_role('button', name='Confirm save', exact=True).click()
    try:
        page.get_by_text('Management permission was revoked', exact=False).wait_for()
    except Exception:
        try:
            revocation_state = page.evaluate('''() => ({owner:typeof task5Scope==='function'?task5Scope():null,
              context:typeof task5Context==='undefined'?null:task5Context,
              routeTitle:typeof routeTitle==='undefined'?null:routeTitle,
              routeRevision:typeof routeRevision==='undefined'?null:routeRevision,
              mode:typeof task5Mode==='undefined'?null:task5Mode,
              dirty:typeof task5IsDirty==='function'?task5IsDirty():null,
              saveBusy:typeof task5SaveBusy==='undefined'?null:task5SaveBusy,
              pending:typeof task5PendingIntent==='undefined'?null:task5PendingIntent,
              message:typeof task5StaleMessage==='undefined'?null:task5StaleMessage})''')
        except Exception as diagnostic_error:
            revocation_state = {'diagnostic_error': str(diagnostic_error)}
        save_responses = []
        for response in fixture['workshop_save_responses'][-12:]:
            try:
                body = response.body()
                body_text = body.decode('utf-8', errors='replace')
                try:
                    body_data = json.loads(body_text)
                except (json.JSONDecodeError, TypeError):
                    body_data = None
                save_responses.append({'status': response.status, 'url': response.url,
                    'content_type': response.headers.get('content-type'), 'body_bytes': len(body),
                    'body_text': body_text[:4000], 'body_json': body_data})
            except Exception as diagnostic_error:
                save_responses.append({'url': response.url,
                    'diagnostic_error': str(diagnostic_error)})
        print('TERMINAL_MANAGEMENT_REVOCATION_WAIT_FAILURE ' + repr({
            'state': revocation_state,
            'save_requests': fixture['save_posts']()[-12:],
            'save_responses': save_responses,
            'browser_errors': fixture['browser_errors'],
        }), flush=True)
        try:
            page.screenshot(path=fixture['terminal_management_revocation_screenshot'], full_page=True)
        except Exception as diagnostic_error:
            print('TERMINAL_MANAGEMENT_REVOCATION_SCREENSHOT_FAILURE ' + repr(str(diagnostic_error)),
                  flush=True)
        raise
    fixture['set_open_admin'](True)
    assert server_document()['revision'] == before_revision
    assert len(fixture['save_posts']()) == 1
    page.get_by_role('button', name='Check saved result', exact=True).click()
    page.get_by_role('button', name='Acknowledge no save started', exact=True).wait_for()
    page.get_by_role('button', name='Acknowledge no save started', exact=True).click()
    page.get_by_role('dialog', name='Acknowledge no save started', exact=True).get_by_role(
        'button', name='Keep draft and clear request', exact=True).click()
    assert page.evaluate('''() => task5PendingIntent===null && task5IsDirty()''')
    fixture['clear_save_posts']()

    # The first uncertain request is committed by the isolated server and its
    # response is dropped. Reload can only inspect status; it cannot resend.
    page.route('**/workshop/save', fixture['drop_next_save_response'])
    page.get_by_role('button', name='Save all room changes', exact=True).click()
    page.get_by_role('dialog', name='Confirm room plan save', exact=True).wait_for()
    page.get_by_role('button', name='Confirm save', exact=True).click()
    page.get_by_text('Check the saved result', exact=False).wait_for()
    assert len(fixture['save_posts']()) == 1
    pending_snapshot = page.evaluate('''() => ({document:task5Clone(task5Document),
      undo:Object.fromEntries(task5UndoByRoom),redo:Object.fromEntries(task5RedoByRoom),
      draft_key:task5DraftKey,stored:localStorage.getItem(task5DraftKey),revision:workshopState.revision})''')
    submitted_room = next(room for room in pending_snapshot['document']['rooms'] if room['id'] == first_room)
    submitted_geometry = next(row for row in submitted_room['objects'] if row['id'] == drawing_id)
    uncertain_server_snapshot = server_document()
    pending_controls = page.evaluate('''() => ({mode:task5Mode,pending:task5PendingIntent,
      canMutate:task5CanMutate(),busy:workflowBusy(),saveBusy:task5SaveBusy,
      buttons:[...document.querySelectorAll('.task5-toolbar button')].map(button=>({
        text:button.textContent,disabled:button.disabled,html:button.outerHTML})),
      message:task5StaleMessage})''')
    assert page.get_by_role('button', name='New room', exact=True).is_disabled(), pending_controls
    page.get_by_role('button', name='Undo', exact=True).is_disabled()
    page.get_by_role('button', name='Redo', exact=True).is_disabled()
    page.evaluate('''() => { task5Undo(); task5Redo(); task5AddRoom(); task5AddDrawing('Cabinet',4,4);
      workshopMoveDrawing(task5Selected, task5Document.rooms.find(r=>r.id!==task5ActiveRoom).id, 1, 1);
      workshopRemoveEmptyRoom(task5Document.rooms.find(r=>r.id!==task5ActiveRoom).id); }''')
    pending_after = page.evaluate('''() => ({document:task5Clone(task5Document),
      undo:Object.fromEntries(task5UndoByRoom),redo:Object.fromEntries(task5RedoByRoom),
      draft_key:task5DraftKey,stored:localStorage.getItem(task5DraftKey),revision:workshopState.revision})''')
    if pending_after != pending_snapshot:
        print('TERMINAL_PENDING_NO_MUTATION_DIFF ' + repr({
          key: {'before': pending_snapshot.get(key), 'after': pending_after.get(key)}
          for key in sorted(set(pending_snapshot) | set(pending_after))
          if pending_snapshot.get(key) != pending_after.get(key)}), flush=True)
    assert pending_after == pending_snapshot
    assert server_document() == uncertain_server_snapshot
    page.unroute('**/workshop/save')
    page.reload()
    try:
        assert len(fixture['save_posts']()) == 1
        page.get_by_role('button', name='Edit layout', exact=True).click()
        page.get_by_role('heading', name='Workshop planner', exact=True).wait_for()
        page.get_by_role('button', name='Check saved result', exact=True).wait_for(timeout=5000)
    except Exception:
        recovery_state = page.evaluate('''() => ({localStorage:Object.keys(localStorage).map(key => [key,localStorage.getItem(key)]),
          sessionStorage:Object.keys(sessionStorage).map(key => [key,sessionStorage.getItem(key)]),
          route:routeRevision, title:routeTitle, taskContext:task5Context, taskPending:task5PendingIntent,
          taskPendingKey:task5PendingKey, taskDocument:task5Document, stale:task5StaleMessage})''')
        page.screenshot(path=fixture['narrow_screenshot'], full_page=True)
        raise AssertionError('Pending save recovery control missing after reload; body=' +
            repr(page.locator('body').inner_text()) + '; state=' + repr(recovery_state) +
            '; requests=' + repr(fixture['browser_requests'][-16:]) +
            '; responses=' + repr(fixture['browser_responses'][-16:]))
    pending_storage = page.evaluate('''() => ({key:task5PendingKey,marker:localStorage.getItem(task5PendingKey),
      request:task5PendingIntent?.request_key,draftKey:task5DraftKey})''')
    first_owner_row = page.evaluate('key => localStorage.getItem(key)', pending_snapshot['draft_key'])
    assert first_owner_row == pending_snapshot['stored'], {
        'key':pending_snapshot['draft_key'],'before':pending_snapshot['stored'],'after':first_owner_row}
    page.reload()
    page.get_by_role('button', name='Edit layout', exact=True).click()
    page.get_by_role('combobox', name='Workshop room', exact=True).wait_for()
    page.get_by_role('button', name='Check saved result', exact=True).wait_for(timeout=5000)
    first_reopen_pointer = page.evaluate('''() => JSON.parse(localStorage.getItem(task5ContextMarkerKey())||'null')''')
    assert first_reopen_pointer['pending_key'] == pending_storage['key'], first_reopen_pointer
    first_reopen_owner_row = page.evaluate('key => localStorage.getItem(key)', pending_snapshot['draft_key'])
    assert first_reopen_owner_row == pending_snapshot['stored'], {
        'key':pending_snapshot['draft_key'],'before':pending_snapshot['stored'],'after':first_reopen_owner_row}
    repeated_recovery = page.evaluate('''({key,marker,draftKey,originalDraftKey}) => ({key:task5PendingKey,
      marker:localStorage.getItem(key),pendingKeyValue:task5PendingIntent?.request_key,
      markerRequest:JSON.parse(localStorage.getItem(key)||'null')?.request_key,
      oldDraft:localStorage.getItem(originalDraftKey),activeDraftKey:task5DraftKey})''', {
          **pending_storage,'originalDraftKey':pending_snapshot['draft_key']})
    assert repeated_recovery['key'] == pending_storage['key']
    assert repeated_recovery['marker'] == pending_storage['marker']
    assert repeated_recovery['pendingKeyValue'] == pending_storage['request']
    assert repeated_recovery['markerRequest'] == pending_storage['request']
    assert repeated_recovery['oldDraft'] == pending_snapshot['stored']
    assert repeated_recovery['activeDraftKey'] != pending_snapshot['draft_key']
    assert len(fixture['save_posts']()) == 1
    page.get_by_role('button', name='Check saved result', exact=True).click()
    try:
        page.get_by_text('Saved result confirmed', exact=False).wait_for(timeout=5000)
    except Exception:
        check_state = page.evaluate('''() => ({body:document.querySelector('#view').innerText,
          route:routeRevision, title:routeTitle, taskContext:task5Context, taskPending:task5PendingIntent,
          taskPendingKey:task5PendingKey, taskOpenGeneration:task5OpenGeneration, stale:task5StaleMessage,
          owner:task5Scope()})''')
        raise AssertionError('Explicit status check did not confirm; state=' + repr(check_state) +
            '; responses=' + repr(fixture['browser_responses'][-12:]) +
            '; requests=' + repr(fixture['browser_requests'][-12:]))
    recovered = server_document()
    page.wait_for_function('() => !workflowBusy() && !task5SaveBusy && task5PendingIntent===null', timeout=5000)
    recovered_gate = page.evaluate('''() => ({conflict:task5Conflict, dirty:task5IsDirty(),
      canMutate:task5CanMutate(), pending:!!task5PendingIntent})''')
    assert recovered_gate['conflict'] is False and recovered_gate['dirty'] is False and \
        recovered_gate['pending'] is False, recovered_gate
    assert len(fixture['save_posts']()) == 1
    assert recovered['revision'] == before_revision + 1
    saved = next(room for room in recovered['document']['rooms'] if room['id'] == first_room)
    moved = next(row for row in saved['objects'] if row['id'] == drawing_id)
    assert moved['id'] == first_identity['id'] and moved['location_id'] == first_identity['location_id']
    assert {key: moved[key] for key in ('x','y','width','height','rotation')} == {
        key: submitted_geometry[key] for key in ('x','y','width','height','rotation')}

    # Status confirmation renders its result before its finally block releases
    # the shared write lock. Wait for that real cleanup state before starting a
    # separate mutation scenario, rather than racing the disabled Edit control.
    page.wait_for_function('''() => !workflowBusy() && !task5SaveBusy &&
      task5PendingIntent===null && task5Mode==='Browse' ''', timeout=5000)
    # A 409 is not retried. Recovery returns to read-only Browse; explicitly
    # enter Edit only after checking that no pending request or conflict remains.
    browse_gate = page.evaluate('''() => ({mode:task5Mode, canMutate:task5CanMutate(),
      dirty:task5IsDirty(), pending:!!task5PendingIntent, conflict:task5Conflict})''')
    assert browse_gate == {'mode':'Browse','canMutate':False,'dirty':False,
      'pending':False,'conflict':False}, browse_gate
    page.get_by_role('button', name='Edit', exact=True).click()
    edit_gate = page.evaluate('''() => ({mode:task5Mode, canMutate:task5CanMutate(),
      dirty:task5IsDirty(), pending:!!task5PendingIntent, conflict:task5Conflict})''')
    assert edit_gate == {'mode':'Edit','canMutate':True,'dirty':False,
      'pending':False,'conflict':False}, edit_gate
    page.get_by_role('combobox', name='Workshop room', exact=True).select_option(first_room)
    page.locator(f'[data-workshop-drawing="{drawing_id}"]').click()
    move_gate = page.evaluate('''() => ({mode:task5Mode, canMutate:task5CanMutate(), dirty:task5IsDirty(),
      busy:workflowBusy(), saveBusy:task5SaveBusy, pending:!!task5PendingIntent, conflict:task5Conflict,
      room:task5ActiveRoom, selected:task5Selected, object:task5Object(), button:document.querySelector('[aria-label="Move left"]')?.outerHTML})''')
    print('TERMINAL_CHECKPOINT 409-move-gate ' + repr(move_gate), flush=True)
    assert move_gate['mode'] == 'Edit' and move_gate['canMutate'] and move_gate['selected'] == drawing_id, move_gate
    page.get_by_role('button', name='Move left', exact=True).click()
    assert page.evaluate('() => task5IsDirty()')
    fixture['clear_save_posts']()
    rejected_posts = []
    def reject_save(route):
        rejected_posts.append(route.request.post_data_json)
        route.fulfill(status=409, content_type='application/json',
                      body=json.dumps({'error': 'The room plan changed elsewhere.'}))
    page.route('**/workshop/save', reject_save)
    page.get_by_role('button', name='Save all room changes', exact=True).click()
    page.get_by_role('button', name='Confirm save', exact=True).click()
    page.get_by_role('button', name='Check saved result', exact=True).wait_for()
    pending_draft = page.evaluate('''() => ({document:task5Clone(task5Document),
      undo:Object.fromEntries(task5UndoByRoom),redo:Object.fromEntries(task5RedoByRoom),
      base:task5BaseRevision,pending:task5PendingIntent&&task5Clone(task5PendingIntent)})''')
    page.get_by_role('button', name='Check saved result', exact=True).click()
    page.get_by_role('button', name='Acknowledge no save started', exact=True).wait_for()
    page.get_by_role('button', name='Acknowledge no save started', exact=True).click()
    resolution = page.get_by_role('dialog', name='Acknowledge no save started', exact=True)
    resolution.get_by_role('button', name='Keep draft and clear request', exact=True).click()
    page.get_by_text('draft remains unsaved', exact=False).wait_for()
    after_ack = page.evaluate('''() => ({document:task5Clone(task5Document),
      undo:Object.fromEntries(task5UndoByRoom),redo:Object.fromEntries(task5RedoByRoom),
      base:task5BaseRevision,pending:task5PendingIntent,stored:localStorage.getItem(task5DraftKey)})''')
    assert len(rejected_posts) == 1 and len(fixture['save_posts']()) == 1
    assert after_ack['document'] == pending_draft['document']
    assert after_ack['undo'] == pending_draft['undo'] and after_ack['redo'] == pending_draft['redo']
    assert after_ack['base'] == pending_draft['base'] and after_ack['pending'] is None
    page.unroute('**/workshop/save')

    # A second tab commits a newer server revision while the original tab has a
    # dirty draft. Re-entry must preserve that draft/history and block overwrite.
    conflict_draft = page.evaluate('''() => ({document:task5Clone(task5Document),
      undo:Object.fromEntries(task5UndoByRoom),redo:Object.fromEntries(task5RedoByRoom),
      base:task5BaseRevision,stored:JSON.parse(localStorage.getItem(task5DraftKey))})''')
    other_tab = page.context.new_page()
    other_tab.goto(fixture['companion_url'], wait_until='domcontentloaded')
    external_save = other_tab.evaluate('''async () => {
      const state=await(await fetch('/workshop/get',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})).json();
      const document=JSON.parse(JSON.stringify(state.document));document.rooms[0].name+=' · concurrent update';
      const response=await fetch('/workshop/save',{method:'POST',headers:{'Content-Type':'application/json',
        'X-Workshop-Group':state.workshop_context.group_id,'X-Workshop-Actor':state.workshop_context.actor_id},
        body:JSON.stringify({schema_version:2,revision:state.revision,document,request_key:crypto.randomUUID()})});
      return {status:response.status,body:await response.json()};
    }''')
    assert external_save['status'] == 200, external_save
    # Re-enter in the same page/client session so the dirty draft remains
    # owned by this exact identity scope. A separate new-page test above changes
    # instance/generation and verifies that the old row is not adopted.
    page.evaluate('() => workshopOpen()')
    try:
        page.get_by_text('newer room plan was saved elsewhere', exact=False).wait_for(timeout=8000)
    except Exception as error:
        conflict_debug = page.evaluate('''() => ({body:document.querySelector('#view').innerText,
          title:routeTitle,route:routeRevision,identityUserId,identityInstance,identityGeneration,
          context:task5Context,scope:task5Scope(),base:task5BaseRevision,conflict:task5Conflict,
          activeDraftKey:task5DraftKey,storedOwner:JSON.parse(localStorage.getItem(task5DraftKey)||'null')?.owner,
          tab:sessionStorage.getItem('workshop-room-draft-tab'),stale:task5StaleMessage,
          document:task5Document,openGeneration:task5OpenGeneration,
          drafts:Object.keys(localStorage).filter(key=>key.includes('workshop')).map(key=>[key,localStorage.getItem(key)])})''')
        raise AssertionError('Revision conflict was not presented after re-entry: ' + repr(conflict_debug)) from error
    page.get_by_role('button', name='Edit', exact=True).click()
    conflict_after = page.evaluate('''() => ({document:task5Clone(task5Document),
      undo:Object.fromEntries(task5UndoByRoom),redo:Object.fromEntries(task5RedoByRoom),
      base:task5BaseRevision,conflict:task5Conflict,save:document.querySelector('.task5-toolbar button[aria-label="Save all room changes"]')?.disabled,
      stored:JSON.parse(localStorage.getItem(task5DraftKey))})''')
    assert conflict_after['document'] == conflict_draft['document']
    assert conflict_after['undo'] == conflict_draft['undo'] and conflict_after['redo'] == conflict_draft['redo']
    assert conflict_after['base'] == conflict_draft['base'] and conflict_after['conflict'] is True
    assert conflict_after['stored']['revision'] == conflict_draft['base']
    assert page.get_by_role('button', name='Save all room changes', exact=True).is_disabled()
    page.get_by_role('button', name='Discard conflicting draft and load saved plan', exact=True).click()
    assert page.evaluate('''() => !task5Conflict && !task5IsDirty()''')
    other_tab.close()
    recovered = server_document()

    # A same-revision service collection switch suspends the prior draft under
    # its original owner. The old draft never becomes a save candidate in B.
    page.get_by_role('button', name='Edit', exact=True).click()
    page.locator(f'[data-workshop-drawing="{drawing_id}"]').click()
    page.get_by_role('button', name='Move right', exact=True).click()
    original_context = recovered['workshop_context']
    original_draft = fixture['terminal_draft_state'](page, original_context)
    alternate_group = str(uuid.uuid4())
    def switched_context(route):
        response = route.fetch()
        payload = response.json()
        payload['workshop_context']['group_id'] = alternate_group
        body = json.dumps(payload).encode()
        route.fulfill(status=response.status,
                      headers={'Content-Type': 'application/json', 'Content-Length': str(len(body))}, body=body)
    page.route('**/workshop/get', switched_context)
    page.reload()
    page.get_by_role('button', name='Edit layout', exact=True).click()
    page.get_by_role('heading', name='Workshop planner', exact=True).wait_for()
    page.get_by_text('collection changed', exact=False).wait_for()
    page.unroute('**/workshop/get')
    assert fixture['terminal_draft_state'](page, original_context) == original_draft
    assert fixture['save_posts']() and len(fixture['save_posts']()) == 1

    # A same-user badge instance/generation change must not adopt or relabel the
    # prior session's draft row, even when the browser tab itself is reused.
    page.get_by_role('button', name='Edit', exact=True).click()
    page.get_by_role('button', name='New room', exact=True).click()
    page.get_by_label('Room title', exact=True).fill('Old badge owner draft')
    page.get_by_role('button', name='Apply room changes', exact=True).click()
    old_owner_row = page.evaluate('''() => ({key:task5DraftKey,raw:localStorage.getItem(task5DraftKey),
      owner:task5Scope(),document:task5Clone(task5Document)})''')
    next_identity = page.evaluate('''() => ({instance:crypto.randomUUID(),generation:identityGeneration+1,
      user:identityUserId})''')
    def changed_same_user_identity(route):
        response=route.fetch()
        payload=response.json()
        payload['instance']=next_identity['instance']
        payload['generation']=next_identity['generation']
        route.fulfill(response=response,body=json.dumps(payload))
    page.route('**/api/session', changed_same_user_identity)
    page.reload()
    page.get_by_role('button', name='Edit layout', exact=True).click()
    page.get_by_role('heading', name='Workshop planner', exact=True).wait_for()
    page.get_by_role('combobox', name='Workshop room', exact=True).wait_for()
    owner_reload = page.evaluate('''oldKey => ({identity:task5Scope(),activeKey:task5DraftKey,
      oldRow:localStorage.getItem(oldKey),document:task5Clone(task5Document),
      server:task5Clone(workshopState.document),stale:task5StaleMessage})''', old_owner_row['key'])
    assert owner_reload['identity'] != old_owner_row['owner']
    assert owner_reload['activeKey'] != old_owner_row['key']
    assert owner_reload['oldRow'] == old_owner_row['raw']
    assert owner_reload['document'] == owner_reload['server']
    page.get_by_role('button', name='Edit', exact=True).click()
    page.get_by_role('button', name='New room', exact=True).click()
    page.get_by_label('Room title', exact=True).fill('New badge owner draft')
    page.get_by_role('button', name='Apply room changes', exact=True).click()
    assert page.evaluate('key => localStorage.getItem(key)', old_owner_row['key']) == old_owner_row['raw']
    assert page.evaluate('key => task5DraftKey !== key', old_owner_row['key'])


def _require_fresh_room_fixture(fixture, previous, candidate) -> None:
    """Reject caller paths unless all writes are confined to a fresh owned root."""
    required = {'owned_root', 'owner_identity', 'runtime', 'fallback', 'return_fallback',
                'workshop_db', 'native_db', 'fallback_receipt', 'return_fallback_receipt'}
    missing = required - set(fixture)
    if missing:
        raise ValueError(f'Fixture is missing required ownership or package bindings: {sorted(missing)}')
    root_raw = pathlib.Path(fixture['owned_root'])
    if '..' in root_raw.parts:
        raise ValueError('Owned fixture root cannot contain parent traversal components.')
    root = pathlib.Path(os.path.abspath(root_raw))
    try:
        root_stat = root.lstat()
    except OSError as exc:
        raise ValueError('Owned fixture root is unavailable; refusing before opening stores.') from exc
    expected = tuple(fixture.get('owner_identity', ()))
    actual = (root_stat.st_dev, root_stat.st_ino, root_stat.st_uid)
    if (not stat.S_ISDIR(root_stat.st_mode) or stat.S_ISLNK(root_stat.st_mode)
            or stat.S_IMODE(root_stat.st_mode) != 0o700 or root_stat.st_uid != os.getuid()
            or actual != expected or root.resolve(strict=True) != root):
        raise ValueError('Fixture root is not a fresh owned 0700 directory; refusing before opening stores.')

    def contained(value, label):
        raw_path = pathlib.Path(value)
        if '..' in raw_path.parts:
            raise ValueError(f'{label} contains a parent traversal component.')
        path = pathlib.Path(os.path.abspath(raw_path))
        try:
            relative = path.relative_to(root)
        except ValueError as exc:
            raise ValueError(f'{label} must remain inside the owned fixture root.') from exc
        if '..' in relative.parts:
            raise ValueError(f'{label} contains a parent traversal component.')
        current = root
        for part in relative.parts:
            current = current / part
            try:
                info = current.lstat()
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise ValueError(f'Cannot safely inspect {label}.') from exc
            if stat.S_ISLNK(info.st_mode):
                # The selector is the sole intentional symlink and is checked separately.
                if current == pathlib.Path(fixture['runtime']).absolute() / 'work/application-current':
                    continue
                raise ValueError(f'{label} contains a symlink; refusing before opening stores.')
            if info.st_uid != os.getuid():
                raise ValueError(f'{label} contains a path not owned by this user.')
        physical = path.resolve(strict=False)
        if physical != path or not physical.is_relative_to(root):
            raise ValueError(f'{label} is not canonically contained in the owned fixture root.')
        return path

    runtime = contained(fixture['runtime'], 'runtime')
    previous = contained(previous, 'previous package')
    candidate = contained(candidate, 'candidate package')
    fallback = contained(fixture['fallback'], 'fallback package')
    return_fallback = contained(fixture.get('return_fallback', fixture['fallback']), 'return fallback package')
    database = contained(fixture['workshop_db'], 'Workshop database')
    native_database = contained(fixture['native_db'], 'native fixture database')
    if not runtime.is_dir() or not (runtime / 'work').is_dir():
        raise ValueError('Runtime and work directories must already exist in the fresh fixture.')
    expected_runtime_entries = {'work', '.fixture-process-token'} if fixture.get('process_fixture') else {'work'}
    if ({path.name for path in runtime.iterdir()} != expected_runtime_entries
            or {path.name for path in (runtime / 'work').iterdir()} != {'application-current'}):
        raise ValueError('Runtime contains pre-existing state beyond the fixture selector; refusing before opening stores.')
    for label, package in (('previous', previous), ('candidate', candidate), ('fallback', fallback),
                           ('return fallback', return_fallback)):
        if not package.is_dir():
            raise ValueError(f'{label} package must already exist in the owned fixture.')
    selector = runtime / 'work/application-current'
    try:
        selector_info = selector.lstat()
        selector_target = pathlib.Path(os.readlink(selector))
    except OSError as exc:
        raise ValueError('Fixture selector must point to the previous package before testing.') from exc
    if (not stat.S_ISLNK(selector_info.st_mode)
            or not (selector.parent / selector_target).resolve(strict=True) == previous.resolve(strict=True)):
        raise ValueError('Fixture selector does not identify the previous package.')
    forbidden = [database, native_database]
    forbidden.extend(contained(item, 'private store') for item in fixture.get('private_paths', ()))
    forbidden.extend((runtime / 'work/baseline/data/homebox.db',
                      runtime / 'work/baseline/pepper', runtime / 'work/ops/ledger.db'))
    for path in forbidden:
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        raise ValueError(f'Private fixture store already exists at {path}; refusing before opening stores.')
    return {'root': root, 'runtime': runtime, 'previous': previous, 'candidate': candidate,
            'fallback': fallback, 'return_fallback': return_fallback,
            'workshop_db': database, 'native_db': native_database}


class _FixturePhysicalImportGuard:
    """Fail before a physical-output package initializer can execute."""
    blocked_names = frozenset({'printer', 'printing', 'label_output', 'hardware', 'gpio'})

    def __init__(self):
        self.blocked_imports = 0

    @classmethod
    def _is_physical_module(cls, fullname):
        return bool(cls.blocked_names.intersection(part.lower() for part in fullname.split('.')))

    def reject_cached_modules(self):
        cached = sorted(name for name in sys.modules if self._is_physical_module(name))
        if cached:
            raise RuntimeError(f'cached physical modules are blocked in the fixture boundary: {cached}')

    def find_spec(self, fullname, path=None, target=None):
        if self._is_physical_module(fullname):
            self.blocked_imports += 1
            raise RuntimeError('physical output imports are blocked in the fixture boundary')
        return None


def test_room_bundle_rollback(fixture, previous, candidate, *, process_runner=None) -> None:
    """Exercise same-store save, F reopen, and F-to-C return inside an owned fixture."""
    validated = _require_fresh_room_fixture(fixture, previous, candidate)
    physical_import_audit = _FixturePhysicalImportGuard()
    physical_import_audit.reject_cached_modules()
    import importlib.util
    import sys

    try:
        from release_bundle import BundleError, _read_transaction_events, select_bundle, validate_bundle
        from contextlib import closing
    except ImportError as exc:
        raise RuntimeError('Run the matched rollback fixture with deploy/ on PYTHONPATH.') from exc

    runtime = validated['runtime']
    previous = validated['previous']
    candidate = validated['candidate']
    fallback = validated['fallback']
    return_fallback = validated['return_fallback']
    database = validated['workshop_db']
    native_database = validated['native_db']
    ledger_database = runtime / 'work/ops/ledger.db'
    receipt = fixture['fallback_receipt']
    manifests = {name: validate_bundle(path) for name, path in
                 (('previous', previous), ('candidate', candidate), ('fallback', fallback))}
    for name, manifest in manifests.items():
        if manifest.get('format') != 2 or not manifest.get('provenance', {}).get('workshop_capability'):
            raise RuntimeError(f'{name} package lacks the artifact-matched Workshop capability gate.')
    if (manifests['previous']['provenance']['workshop_capability']['write_mode'] != 'disabled'
            or manifests['candidate']['provenance']['workshop_capability']['write_mode'] != 'v2'):
        raise RuntimeError('Fixture requires a disabled-write O and a version-2-writing C.')

    # These UUID rows are API fixtures, not a Homebox database or production data.
    room_location, item_location = str(uuid.uuid4()), str(uuid.uuid4())
    native_database.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with closing(sqlite3.connect(native_database)) as db, db:
        db.execute('''CREATE TABLE native_identity_fixture(
            id TEXT PRIMARY KEY, name TEXT NOT NULL, parent_id TEXT, is_location INTEGER NOT NULL,
            caption TEXT NOT NULL, precision REAL NOT NULL, privacy_marker TEXT NOT NULL)''')
        db.executemany('INSERT INTO native_identity_fixture VALUES(?,?,?,?,?,?,?)', (
            (room_location, 'The Cage', None, 1, 'fixture room', 0.125, 'private-fixture-A'),
            (item_location, 'The Cage', room_location, 1, 'fixture child', 0.125, 'private-fixture-B')))
        native_before = db.execute('SELECT * FROM native_identity_fixture ORDER BY id').fetchall()
        db.execute('''CREATE TABLE native_effect_fixture(
            entity_id TEXT NOT NULL, kind TEXT NOT NULL, identity TEXT NOT NULL,
            payload TEXT NOT NULL, PRIMARY KEY(entity_id,kind,identity))''')
        db.executemany('INSERT INTO native_effect_fixture VALUES(?,?,?,?)', (
            (item_location, 'photo', 'photo-uuid', 'fixture-photo-sha256'),
            (item_location, 'loan', 'loan-uuid', 'pending fixture loan'),
            (item_location, 'history', 'event-uuid', 'fixture native event'),
            (item_location, 'privacy', 'tenant-scope', 'private-fixture-B')))
        native_effect_before = db.execute('SELECT * FROM native_effect_fixture ORDER BY 1,2,3').fetchall()
    native_inode = native_database.stat().st_ino

    group_ids, actor_id = [str(uuid.uuid4()), str(uuid.uuid4())], str(uuid.uuid4())
    legacy_object = {'id': str(uuid.uuid4()), 'kind': 'Rack', 'name': 'Linked legacy rack',
                     'x': 1.0, 'y': 2.0, 'width': 2.0, 'height': 3.0,
                     'rotation': 0, 'location_id': item_location}
    legacy_documents = [
        {'name': 'Populated legacy room', 'width': 13.5, 'height': 21.0, 'unit': 'ft',
         'approximate': True, 'objects': [legacy_object]},
        {'name': 'Empty legacy room', 'width': 12.0, 'height': 18.0, 'unit': 'ft',
         'approximate': True, 'objects': []},
    ]
    audit = {'candidate_saves': 0, 'previous_write_attempts': 0, 'replay_calls': 0,
             'monitored_shutil_store_copy_calls': 0, 'physical_import_attempts': 0}

    sys.meta_path.insert(0, physical_import_audit)
    original_copy_functions = {name: getattr(shutil, name) for name in ('copyfile', 'copy', 'copy2', 'copytree')}
    def watched_copy(name):
        original = original_copy_functions[name]
        def copy(source, destination, *args, **kwargs):
            source_path, destination_path = pathlib.Path(source), pathlib.Path(destination)
            if (source_path == database or destination_path == database or
                    source_path == native_database or destination_path == native_database or
                    source_path == ledger_database or destination_path == ledger_database):
                audit['monitored_shutil_store_copy_calls'] += 1
            return original(source, destination, *args, **kwargs)
        return copy
    for copy_name in original_copy_functions:
        setattr(shutil, copy_name, watched_copy(copy_name))

    def load_workshop(bundle, suffix):
        for module_name in ('ledger', 'native_fields'):
            sys.modules.pop(module_name, None)
        operations = str(pathlib.Path(bundle) / 'ops')
        sys.path.insert(0, operations)
        try:
            path = pathlib.Path(bundle) / 'ops/workshop.py'
            spec = importlib.util.spec_from_file_location(f'_rooms_workshop_{suffix}', path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.Ledger = sys.modules['ledger'].Ledger
            original_replay = module.Workshop.replay_save
            def counted_replay(self, *args, **kwargs):
                audit['replay_calls'] += 1
                return original_replay(self, *args, **kwargs)
            module.Workshop.replay_save = counted_replay
            if pathlib.Path(module.__file__).resolve(strict=True) != path.resolve(strict=True):
                raise RuntimeError('Workshop module did not load from its immutable bundle.')
            dependencies = [sys.modules[name].__file__ for name in ('ledger', 'native_fields')]
            if any(not pathlib.Path(dependency).resolve().is_relative_to(pathlib.Path(bundle).resolve())
                   for dependency in dependencies):
                raise RuntimeError('Workshop dependency import escaped its immutable bundle.')
            return module
        finally:
            sys.path.remove(operations)
            for module_name in ('ledger', 'native_fields'):
                sys.modules.pop(module_name, None)

    try:
        old_workshop = load_workshop(previous, 'previous')
        candidate_workshop = load_workshop(candidate, 'candidate-seed')
        old_store = old_workshop.Workshop(database)
        candidate_store = candidate_workshop.Workshop(database)
        workshop_inode = database.stat().st_ino
        with closing(sqlite3.connect(database)) as db, db:
            for group, legacy in zip(group_ids, legacy_documents):
                db.execute('INSERT INTO plans VALUES(?,?,?)',
                           (group, 0, json.dumps(legacy, sort_keys=True)))
        for group in group_ids:
            old_read = old_store.get(group)
            if old_read['stored_schema_version'] != 1:
                raise RuntimeError('Previous package did not read a legacy document.')

        class FixtureNativeClient:
            rows = {room_location: {'id': room_location, 'name': 'The Cage', 'parent': None,
                                    'entityType': {'isLocation': True}, 'archived': False},
                    item_location: {'id': item_location, 'name': 'The Cage',
                                    'parent': {'id': room_location},
                                    'entityType': {'isLocation': True}, 'archived': False}}
            def entities(self, locations_only=False):
                return [dict(self.rows[room_location]), dict(self.rows[item_location])]
            def entity(self, key):
                return dict(self.rows[key])

        native_client = FixtureNativeClient()
        documents, requests = {}, {}
        for index, (group, legacy) in enumerate(zip(group_ids, legacy_documents)):
            old_read = old_store.get(group)
            rooms = old_read['document']['rooms']
            if index == 0:
                # Retain the legacy drawing link and add a second room linked to
                # the same-named native root/child UUID pair.
                rooms[0]['objects'][0]['location_id'] = item_location
                rooms.append({'id': str(uuid.uuid4()), 'location_id': room_location,
                              'name': 'Linked second room', 'width': 8.0, 'height': 10.0,
                              'unit': 'ft', 'approximate': True,
                              'objects': [{'id': str(uuid.uuid4()), 'kind': 'Rack',
                                           'name': 'Linked rack', 'x': 0.0, 'y': 0.0,
                                           'width': 2.0, 'height': 2.0, 'rotation': 0,
                                           'location_id': item_location}]})
            else:
                room = {'id': str(uuid.uuid4()), 'location_id': room_location,
                        'name': 'Linked second room', 'width': 8.0, 'height': 10.0,
                        'unit': 'ft', 'approximate': True,
                        'objects': [{'id': str(uuid.uuid4()), 'kind': 'Rack', 'name': 'Linked rack',
                                     'x': 0.0, 'y': 0.0, 'width': 2.0, 'height': 2.0,
                                     'rotation': 0, 'location_id': item_location}]}
                rooms.append(room)
            documents[group] = {'version': 2, 'rooms': rooms}
            requests[group] = {'schema_version': 2, 'revision': 0, 'document': documents[group],
                               'request_key': str(uuid.uuid4())}

        calls = []
        save_hashes = {}
        unresolved_operation = None
        ledger_before = None
        def service_runner(action):
            names = list(action)
            if len(names) != 4 or names[0] not in ('start', 'stop'):
                raise RuntimeError('Unexpected service transition in the fixture.')
            calls.append(names)
            if process_runner is not None:
                process_runner(names)

        def open_store(bundle, suffix):
            module = load_workshop(bundle, suffix)
            return module, module.Workshop(database)

        def check_all(store, label):
            results = {}
            for group in group_ids:
                current = store.get(group)
                if current['revision'] != 1 or current['stored_schema_version'] != 2:
                    raise RuntimeError(f'{label} reopened a non-v2 document or wrong revision.')
                if current['document'] != documents[group]:
                    raise RuntimeError(f'{label} changed drawing identity, geometry, or storage links.')
                status = store.save_status(group, requests[group]['request_key'], actor_id=actor_id)
                if status.get('status') != 'completed' or status.get('result', {}).get('document') != documents[group]:
                    raise RuntimeError(f'{label} lost a completed save receipt.')
                results[group] = current
            return results

        def check_ledger(ledger_type, label):
            current = ledger_type(ledger_database).detail(group_ids[0], unresolved_operation['id'])
            if current != ledger_before:
                raise RuntimeError(f'{label} changed pending operation fields, intent/context, or events.')
            return current

        def first_verify(selected):
            nonlocal unresolved_operation, ledger_before
            selected = pathlib.Path(selected).resolve(strict=True)
            if selected == pathlib.Path(candidate).resolve(strict=True):
                for group in group_ids:
                    saved = candidate_store.save(native_client, group, requests[group], actor_id=actor_id)
                    audit['candidate_saves'] += 1
                    if saved['revision'] != 1 or saved['document'] != documents[group]:
                        raise RuntimeError('Candidate did not migrate and save the full v2 document.')
                    save_hashes[group] = hashlib.sha256(json.dumps(saved['document'], sort_keys=True,
                        separators=(',', ':')).encode()).hexdigest()
                # Create a durable unresolved receipt in the actual bundled ledger schema.
                ledger = candidate_workshop.Ledger(ledger_database)
                unresolved_operation = ledger.begin(group_ids[0], actor_id, 'check_out', [item_location],
                                                    str(uuid.uuid4()), context={'fixture': 'unresolved'},
                                                    intent={'fixture': True})
                ledger_before = ledger.detail(group_ids[0], unresolved_operation['id'])
                if ledger_before['status'] != 'pending' or len(ledger_before['events']) != 1:
                    raise RuntimeError('Fixture could not create a pending operation receipt.')
                raise RuntimeError('injected candidate selection failure after same-store saves')
            if selected != fallback:
                raise RuntimeError('First transition selected an unexpected fallback.')
            f_module, f_store = open_store(fallback, 'selected-fresh-f')
            if pathlib.Path(f_module.__file__).resolve() != fallback / 'ops/workshop.py':
                raise RuntimeError('Selected F module origin did not match its package.')
            check_all(f_store, 'Fresh selected F')
            check_ledger(old_workshop.Ledger, 'O')
            check_ledger(f_module.Ledger, 'F')
            changed = json.loads(json.dumps(documents[group_ids[0]]))
            changed['rooms'][0]['name'] = 'must remain rejected'
            rejected = dict(requests[group_ids[0]], revision=1, document=changed,
                            request_key=str(uuid.uuid4()))
            audit['previous_write_attempts'] += 1
            try:
                old_store.save(native_client, group_ids[0], rejected, actor_id=actor_id)
            except Exception as exc:
                if 'Workshop writes disabled' not in str(exc):
                    raise RuntimeError('Disabled O did not reject the write for the expected reason.') from exc
            else:
                raise RuntimeError('Disabled O unexpectedly accepted a write.')
            if old_store.get(group_ids[0])['document'] != documents[group_ids[0]]:
                raise RuntimeError('Rejected O write changed a document.')
            with closing(sqlite3.connect(native_database)) as db, db:
                if db.execute('SELECT * FROM native_identity_fixture ORDER BY id').fetchall() != native_before:
                    raise RuntimeError('Synthetic native identity fixture changed during fallback.')
            if database.stat().st_ino != workshop_inode or native_database.stat().st_ino != native_inode:
                raise RuntimeError('A same-store database inode changed during fallback.')

        try:
            if process_runner is not None:
                process_runner(['start', 'homebox-native', 'homebox-companion', 'homebox-workshop-gateway'])
            select_bundle(runtime, candidate, fallback=fallback, fallback_receipt=receipt,
                          run_services=service_runner, verify=first_verify)
        except BundleError as exc:
            if ('injected candidate selection failure after same-store saves' not in str(exc)
                    or 'compatible F selected and verified' not in str(exc)):
                raise
        else:
            raise AssertionError('Injected candidate failure did not select compatible F.')

        # Re-select C from a process-shaped fresh reopen, using the same release
        # selector engine and a second F package with the identical candidate closure.
        second_receipt = fixture['return_fallback_receipt']
        def verify_return(selected):
            selected = pathlib.Path(selected).resolve(strict=True)
            if selected != pathlib.Path(candidate).resolve(strict=True):
                raise RuntimeError('F-to-C verification received an unexpected selected package.')
            module, reopened = open_store(candidate, 'returned-fresh-c')
            if pathlib.Path(module.__file__).resolve() != candidate / 'ops/workshop.py':
                raise RuntimeError('Returned C module origin did not match its package.')
            check_all(reopened, 'Fresh returned C')
            check_ledger(module.Ledger, 'Returned C')

        select_bundle(runtime, candidate, fallback=return_fallback,
                      fallback_receipt=second_receipt, run_services=service_runner,
                      verify=verify_return)
        events = _read_transaction_events(runtime / 'work/application-release-journal.jsonl', runtime)
        with closing(sqlite3.connect(native_database)) as db, db:
            native_after = db.execute('SELECT * FROM native_identity_fixture ORDER BY id').fetchall()
            native_effect_after = db.execute('SELECT * FROM native_effect_fixture ORDER BY 1,2,3').fetchall()
        if (runtime / 'work/application-current').resolve(strict=True) != pathlib.Path(candidate).resolve(strict=True):
            raise AssertionError('F-to-C did not leave C selected.')
        if events[-1]['phase'] != 'candidate_verified' or len(calls) != 6:
            raise AssertionError('Selection journal or service transitions did not record both trips.')
        if native_after != native_before or native_effect_after != native_effect_before:
            raise AssertionError('Synthetic native identities or unresolved receipt changed.')
        if database.stat().st_ino != workshop_inode or native_database.stat().st_ino != native_inode:
            raise AssertionError('Same-store database inode changed during either transition.')
        # Counts are observed by wrappers/firewalls around the called code paths.
        audit['physical_import_attempts'] = physical_import_audit.blocked_imports
        if (audit['replay_calls'] or audit['monitored_shutil_store_copy_calls']
                or audit['physical_import_attempts']):
            raise AssertionError(f'Unexpected replay, monitored store-copy, or physical import attempt: {audit}')
        fixture['room_rollback_checks'] = {
            'legacy_populated_and_empty_read': True, 'selected_f_reopened': True,
            'f_to_c_reopened': True, 'drawing_identity_and_native_links_preserved': True,
            'completed_receipts_preserved': True, 'unresolved_operation_preserved': True,
            'native_fixture_state_preserved': True, 'full_unresolved_operation_preserved': True,
            'native_evidence_scope': 'synthetic Rooms identity/effect tables; not native member/loan compatibility evidence',
            'replay_calls': audit['replay_calls'],
            'monitored_shutil_store_copy_calls': audit['monitored_shutil_store_copy_calls'],
            'physical_import_attempts': audit['physical_import_attempts'],
            'candidate_saves': audit['candidate_saves'],
            'selector': str(candidate), 'compatibility_claim': 'fixture-only',
        }
    finally:
        if physical_import_audit in sys.meta_path:
            sys.meta_path.remove(physical_import_audit)
        for copy_name, original in original_copy_functions.items():
            setattr(shutil, copy_name, original)

def rewrite_companion_for_fixture(source: str, candidate: pathlib.Path, data_root: pathlib.Path,
                                  native_url: str, companion_url: str,
                                  hardware_compat: pathlib.Path) -> str:
    """Pin current companion source anchors to the disposable candidate and loopback fixture."""
    candidate_literal = repr(str(candidate))
    data_literal = repr(str(data_root))
    anchors = {
        "CODE_ROOT=pathlib.Path(CODE_ROOT_ENV or pathlib.Path(__file__).resolve().parents[1]).resolve()":
            f'CODE_ROOT=pathlib.Path({candidate_literal}).resolve(strict=True)',
        "ROOT=pathlib.Path(os.environ.get('WORKSHOP_ROOT','/home/user/Desktop/inventory-system')).resolve()":
            f'ROOT=pathlib.Path({data_literal}).resolve(strict=True)',
        "BASE=os.environ.get('WORKSHOP_NATIVE_BASE','http://127.0.0.1:17745')": f'BASE={native_url!r}',
        "sys.path.insert(0,str(CODE_ROOT/'kiosk'))":
            f'sys.path.insert(0,{str(candidate / "kiosk")!r})',
        "sys.path.insert(0,str(ROOT/'program-files/runtime/hardware/python'))":
            f'sys.path.insert(0,{str(hardware_compat)!r})',
        "sys.path.insert(0,str(CODE_ROOT/'ops'))":
            f'sys.path.insert(0,{str(candidate / "ops")!r})',
        "self.headers.get('Origin') != 'http://127.0.0.1:17749'":
            f"self.headers.get('Origin') != {companion_url!r}",
        "_fixture_server=ThreadingHTTPServer((_fixture_host,_fixture_port),Handler)": '_fixture_server=None',
        "print('Homebox companion listening on 0.0.0.0:17749',flush=True)": 'pass',
        '_fixture_server.serve_forever()': 'pass',
    }
    for before, after in anchors.items():
        if source.count(before) != 1:
            raise RuntimeError('Candidate companion fixture anchor changed: ' + before[:48])
        source = source.replace(before, after, 1)

    boundary = f'''_fixture_expected=pathlib.Path({str(candidate)!r}).resolve(strict=True)
for _n in ('homebox','ledger','native_jobs','imports','workshop','desktop_api','badges','attachments',
           'sessions','scan_codes','decode_codes','checkout','returns','maps','categories',
           'code_registration','stock','reviews','kits','system_status','hardware','accounts',
           'labels','problems','setup_native','kiosk_processes','network_access','products','conditions'):
 _m=sys.modules.get(_n)
 if _m is None or not pathlib.Path(_m.__file__).resolve(strict=True).is_relative_to(_fixture_expected): raise RuntimeError('Project import escaped candidate: '+_n)
import hardware as _fixture_hardware, labels as _fixture_labels
def _fixture_refuse(*_a,**_k): raise RuntimeError('Physical printer/camera operations are disabled in this fixture.')
for _m,_names in ((_fixture_hardware,('probe','camera_status','reconnect')),(_fixture_labels,('probe','print_label','print_badge','reprint_badge'))):
 for _name in _names: setattr(_m,_name,_fixture_refuse)
reconnect_hardware=camera_status=printer_probe=_fixture_refuse
label_preview=print_label=print_badge=recover_print=_fixture_refuse
'''
    store_anchor = "ops_path=ROOT/'work/ops'"
    if source.count(store_anchor) != 1:
        raise RuntimeError('Candidate companion store boundary changed.')
    return source.replace(store_anchor, boundary + '\n' + store_anchor, 1)


def run_desktop(candidate: pathlib.Path, ports: tuple[int, int, int], *, terminal_only: bool = False) -> None:
    from playwright.sync_api import sync_playwright
    candidate = candidate.resolve(strict=True)
    manifest = validate_candidate(candidate)
    native_port, companion_port, gateway_port = ports
    if len(set(ports)) != 3 or any(port < 32768 or port > 60999 for port in ports):
        raise ValueError('Use distinct unprivileged ephemeral loopback ports.')
    system_tmp = pathlib.Path(tempfile.gettempdir()).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='workshop-rooms-') as temporary:
        data_root = pathlib.Path(temporary).resolve(strict=True)
        if data_root == system_tmp or not data_root.is_relative_to(system_tmp):
            raise RuntimeError('Runtime data must be a fresh directory beneath the system temporary root.')
        (data_root / 'data').mkdir()
        (data_root / 'work/ops').mkdir(parents=True)
        (data_root / 'work/baseline').mkdir(parents=True)
        shutil.copytree(candidate / 'kiosk', data_root / 'work/kiosk-ui-current')
        native_url = f'http://127.0.0.1:{native_port}'
        gateway_url = f'http://127.0.0.1:{gateway_port}'
        companion_url = f'http://127.0.0.1:{companion_port}'
        fixture_env = dict(HBOX_WEB_HOST='127.0.0.1', HBOX_WEB_PORT=str(native_port),
                   HBOX_DATABASE_DRIVER='sqlite3',
                   HBOX_STORAGE_PREFIX_PATH=str(data_root / 'data'),
                   HBOX_STORAGE_CONN_STRING='file://' + str(data_root / 'data'),
                   HBOX_DATABASE_PUBSUB_CONN_STRING='mem://{{ .Topic }}',
                   HBOX_DATABASE_SQLITE_PATH=str(data_root / 'data/homebox.db') + '?_pragma=busy_timeout=999&_pragma=journal_mode=WAL&_fk=1&_time_format=sqlite',
                   HBOX_AUTH_API_KEY_PEPPER=str(uuid.uuid4()), HBOX_OPTIONS_ALLOW_REGISTRATION='true',
                   HBOX_OPTIONS_GITHUB_RELEASE_CHECK='false', HBOX_OPTIONS_ALLOW_ANALYTICS='false',
                   WORKSHOP_ROOT=str(data_root), WORKSHOP_CODE_ROOT=str(candidate),
                   WORKSHOP_NATIVE_BASE=native_url,
                   WORKSHOP_NATIVE_PORT=str(native_port), WORKSHOP_COMPANION_PORT=str(companion_port),
                   WORKSHOP_PORT=str(gateway_port), HOMEBOX_UI_ROOT=str(candidate / 'public'))
        inherited_hbox = {key: value for key, value in os.environ.items() if key.startswith('HBOX_')}
        env = {key: value for key, value in os.environ.items() if not key.startswith('HBOX_')}
        env.update(fixture_env)
        prior_env = {key: os.environ.get(key) for key in set(inherited_hbox) | set(fixture_env)}
        prior_bytecode = sys.dont_write_bytecode
        before_bundle = tree_hash(candidate)
        binary = candidate / manifest['native']['path']
        log = (data_root / 'native.log').open('w')
        native = None
        companion = gateway = None
        try:
            for key in inherited_hbox:
                os.environ.pop(key, None)
            os.environ.update(fixture_env)
            sys.dont_write_bytecode = True
            native = subprocess.Popen([str(binary)], cwd=data_root, env=env, stdout=log, stderr=subprocess.STDOUT)
            for _ in range(150):
                if native.poll() is not None:
                    raise RuntimeError('Disposable native Homebox exited before readiness.')
                try:
                    with urllib.request.urlopen(native_url + '/api/v1/status', timeout=1):
                        pass
                    if native.poll() is not None or not native_pid_owns_listener(native.pid, native_port):
                        raise RuntimeError('Ready native endpoint is not owned by the launched fixture process.')
                    break
                except OSError:
                    time.sleep(.1)
            else:
                raise RuntimeError('Disposable Homebox did not become ready.')
            account = {'email': 'rooms-manager@fixture.invalid', 'name': 'Rooms Fixture Manager',
                       'password': 'isolated-fixture-password'}
            request = urllib.request.Request(native_url + '/api/v1/users/register',
                data=json.dumps(account).encode(), headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(request, timeout=15):
                pass
            (data_root / 'work/baseline/test-account.json').write_text(json.dumps(account))
            native_login = urllib.request.Request(native_url + '/api/v1/users/login',
                data=json.dumps({'username': account['email'], 'password': account['password']}).encode(),
                headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(native_login, timeout=15) as response:
                native_token = json.loads(response.read())['token']
            native_self = urllib.request.Request(native_url + '/api/v1/users/self',
                headers={'Authorization': native_token})
            with urllib.request.urlopen(native_self, timeout=15) as response:
                manager_user = json.loads(response.read())['item']
            manager_path = data_root / 'work/ops/desktop-managers.json'
            manager_path.write_text(json.dumps({'managers': [{'user_id': manager_user['id'],
                'group_id': manager_user['defaultGroupId']}]}))
            manager_path.chmod(0o600)

            # Compile only after validation; pin source imports and state to this disposable fixture.
            companion_path = candidate / 'deploy/kiosk-server.py'
            hardware_compat = ROOT / 'work/hardware/python'
            source = rewrite_companion_for_fixture(companion_path.read_text(), candidate, data_root,
                                                   native_url, companion_url, hardware_compat)
            scope = {'__file__': str(companion_path), '__name__': 'rooms_candidate_companion'}
            exec(compile(source, str(companion_path), 'exec'), scope)
            # The production same-origin policy pins 17749. This isolated server
            # binds an ephemeral port, so accept only this fixture's exact origin.
            fixture_origin = f'http://127.0.0.1:{companion_port}'
            scope['same_origin'] = lambda origin, host: origin == fixture_origin and host == fixture_origin.removeprefix('http://')
            companion = ThreadingHTTPServer(('127.0.0.1', companion_port), scope['Handler'])
            threading.Thread(target=companion.serve_forever, daemon=True).start()

            gateway_path = candidate / 'deploy/workshop-gateway.py'
            gateway_spec = __import__('importlib.util', fromlist=['spec_from_file_location']).spec_from_file_location(
                'rooms_candidate_gateway', gateway_path)
            gateway_module = __import__('importlib.util', fromlist=['module_from_spec']).module_from_spec(gateway_spec)
            gateway_spec.loader.exec_module(gateway_module)
            if not pathlib.Path(gateway_module.__file__).resolve(strict=True).is_relative_to(candidate):
                raise RuntimeError('Candidate gateway import escaped the pinned bundle.')
            expected_roots = ((candidate / 'ops').resolve(strict=True),
                              (candidate / 'kiosk').resolve(strict=True))
            project_names = {
                                   'homebox', 'ledger', 'native_jobs', 'imports', 'workshop',
                                   'desktop_api', 'badges', 'attachments', 'sessions', 'scan_codes',
                                   'decode_codes', 'checkout', 'returns', 'maps', 'categories',
                                   'code_registration', 'stock', 'reviews', 'kits', 'system_status',
                                   'hardware', 'accounts', 'labels', 'problems', 'setup_native',
                                   'kiosk_processes', 'network_access', 'products', 'conditions',
                                   'workshop_views'}
            project_modules = {name: sys.modules.get(name) for name in project_names}
            project_modules.update({name: module for name, module in sys.modules.items()
                                    if getattr(module, '__file__', None) and
                                    any(pathlib.Path(module.__file__).resolve().is_relative_to(root)
                                        for root in expected_roots)})
            if any(module is None or not getattr(module, '__file__', None) or
                    not any(pathlib.Path(module.__file__).resolve(strict=True).is_relative_to(root)
                            for root in expected_roots)
                    for module in project_modules.values()):
                raise RuntimeError('A project module was not imported solely from candidate ops/kiosk.')
            gateway_module.ROOT = data_root
            gateway_module.NATIVE_PORT = native_port
            gateway_module.COMPANION_PORT = companion_port
            gateway_module.PORT = gateway_port
            gateway = ThreadingHTTPServer(('127.0.0.1', gateway_port), gateway_module.Handler)
            threading.Thread(target=gateway.serve_forever, daemon=True).start()

            import http.cookiejar
            jar = http.cookiejar.CookieJar()
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
            login = urllib.request.Request(gateway_url + '/api/v1/users/login',
                data=json.dumps({'username': account['email'], 'password': account['password']}).encode(),
                headers={'Content-Type': 'application/json', 'Origin': gateway_url})
            with opener.open(login, timeout=15) as response:
                login_result = json.loads(response.read())
            context_req = urllib.request.Request(gateway_url + '/workshop-api/context')
            with opener.open(context_req, timeout=15) as response:
                context = json.loads(response.read())
            legacy_revision = 1
            legacy_plan = {'name': 'Legacy precision room', 'width': 17.13, 'height': 15.27,
                           'unit': 'ft', 'approximate': False, 'objects': []}
            with sqlite3.connect(data_root / 'work/ops/workshop.db') as db:
                db.execute('INSERT INTO plans(group_id,revision,document) VALUES(?,?,?)',
                           (context['group']['id'], legacy_revision,
                            json.dumps(legacy_plan, separators=(',', ':'))))

            def native_call(path: str, method: str = 'GET', body: dict | None = None):
                headers = {'Authorization': login_result['token'], 'Origin': gateway_url}
                data = None if body is None else json.dumps(body).encode()
                if data is not None:
                    headers['Content-Type'] = 'application/json'
                request = urllib.request.Request(native_url + path, data=data, headers=headers, method=method)
                with urllib.request.urlopen(request, timeout=15) as response:
                    raw = response.read()
                    return json.loads(raw) if raw else None

            entity_types = native_call('/api/v1/entity-types')
            location_type = next(row for row in entity_types if row.get('isLocation'))
            native_call('/api/v1/entity-types', 'POST',
                        {'name': 'Fixture tool', 'isLocation': False, 'icon': ''})
            fixture_types = [row for row in native_call('/api/v1/entity-types')
                             if row.get('name') == 'Fixture tool' and row.get('isLocation') is False]
            if len(fixture_types) != 1 or not fixture_types[0].get('id'):
                raise RuntimeError('Disposable native fixture tool type was not created exactly once.')
            item_type = fixture_types[0]
            location = native_call('/api/v1/entities', 'POST', {
                'name': 'Fixture Native Room Label', 'entityTypeId': location_type['id'], 'quantity': 1})
            native_item = native_call('/api/v1/entities', 'POST', {
                'name': 'Fixture item contents', 'entityTypeId': item_type['id'],
                'parentId': location['id'], 'quantity': 1})
            fixture_modules = {name: sys.modules.get(name) for name in
                               ('homebox', 'ledger', 'native_jobs', 'setup_native', 'attachments')}
            if any(module is None or not pathlib.Path(module.__file__).resolve(strict=True).is_relative_to(candidate)
                   for module in fixture_modules.values()):
                raise RuntimeError('Synthetic photo helpers must come from the exact disposable candidate source.')
            from io import BytesIO
            from PIL import Image
            photo_client = fixture_modules['homebox'].Homebox(data_root, base=native_url)
            photo_jobs = fixture_modules['native_jobs'].NativeJobs(
                fixture_modules['ledger'].Ledger(data_root / 'work/ops/ledger.db'))
            shelf_result = fixture_modules['setup_native'].submit(
                photo_client, photo_jobs, context['group']['id'], context['user']['id'],
                'create_location', str(uuid.uuid4()),
                {'name': 'Fixture photo shelf', 'storage_kind': 'Shelf',
                 'storage_code': 'ROOMS-PHOTO-1', 'parent_id': location['id']})
            shelf_id = shelf_result['entity_id']
            browse_rack = fixture_modules['setup_native'].submit(
                photo_client, photo_jobs, context['group']['id'], context['user']['id'],
                'create_location', str(uuid.uuid4()),
                {'name': 'Fixture browse rack', 'storage_kind': 'Rack',
                 'storage_code': 'ROOMS-BROWSE-RACK', 'parent_id': location['id']})
            browse_rack_id = browse_rack['entity_id']
            browse_shelf = fixture_modules['setup_native'].submit(
                photo_client, photo_jobs, context['group']['id'], context['user']['id'],
                'create_location', str(uuid.uuid4()),
                {'name': 'Fixture browse shelf', 'storage_kind': 'Shelf',
                 'storage_code': 'ROOMS-BROWSE-SHELF', 'parent_id': browse_rack_id})
            browse_shelf_id = browse_shelf['entity_id']
            def synthetic_jpeg(color: tuple[int, int, int]) -> bytes:
                stream = BytesIO()
                Image.new('RGB', (2, 2), color).save(stream, format='JPEG')
                return stream.getvalue()
            shelf_photo_bytes = synthetic_jpeg((24, 86, 120))
            fixture_modules['attachments'].upload(
                photo_client, shelf_id, 'Fixture authorized shelf photo.jpg', shelf_photo_bytes)
            fixture_modules['attachments'].upload(
                photo_client, browse_shelf_id, 'Fixture Browse rack shelf photo.jpg', shelf_photo_bytes)
            fixture_modules['attachments'].upload(
                photo_client, location['id'], 'Fixture parent-only photo.jpg', synthetic_jpeg((180, 42, 72)))
            shelf_photo = next(row for row in photo_client.entity(shelf_id)['attachments']
                               if row.get('title') == 'Fixture authorized shelf photo.jpg')
            parent_photo = next(row for row in photo_client.entity(location['id'])['attachments']
                                if row.get('title') == 'Fixture parent-only photo.jpg')
            if not shelf_photo.get('id') or not parent_photo.get('id'):
                raise RuntimeError('Synthetic native photo attachments were not created on their expected owners.')
            unauthenticated_photo_status = None
            try:
                with urllib.request.urlopen(gateway_url + '/api/v1/entities/' + shelf_id +
                        '/attachments/' + shelf_photo['id'], timeout=10) as response:
                    unauthenticated_photo_status = response.status
            except urllib.error.HTTPError as error:
                unauthenticated_photo_status = error.code
            if unauthenticated_photo_status not in (401, 403):
                raise RuntimeError('Native attachment bytes were readable without the fixture attachment authorization.')
            other_location = native_call('/api/v1/entities', 'POST', {
                'name': 'Fixture Other Native Root', 'entityTypeId': location_type['id'], 'quantity': 1})
            refresh_root = native_call('/api/v1/entities', 'POST', {
                'name': 'Fixture stale hierarchy root', 'entityTypeId': location_type['id'], 'quantity': 1})
            refresh_child = native_call('/api/v1/entities', 'POST', {
                'name': 'Fixture refreshed hierarchy child', 'entityTypeId': location_type['id'],
                'parentId': refresh_root['id'], 'quantity': 1})
            alternate_group = native_call('/api/v1/groups', 'POST', {'name': 'Fixture alternate collection'})
            manager_path = data_root / 'work/ops/desktop-managers.json'
            manager_path.write_text(json.dumps({'managers': [
                {'user_id': manager_user['id'], 'group_id': manager_user['defaultGroupId']},
                {'user_id': manager_user['id'], 'group_id': alternate_group['id']}]}))
            manager_path.chmod(0o600)
            def native_location(phase: str):
                current = native_call('/api/v1/entities/' + location['id'])
                if phase not in ('before', 'after') or current.get('id') != location['id']:
                    raise AssertionError('Native location proof did not reread the expected entity UUID.')
                return current['name']
            def mutate_native(entity_id: str, **changes):
                current = native_call('/api/v1/entities/' + entity_id)
                payload = dict(current)
                payload['parentId'] = (current.get('parent') or {}).get('id')
                payload['entityTypeId'] = current['entityType']['id']
                payload['tagIds'] = [tag['id'] for tag in current.get('tags', [])]
                payload['fields'] = current.get('fields') or []
                payload.update(changes)
                return native_call('/api/v1/entities/' + entity_id, 'PUT', payload)
            second_page = None
            save_posts = []
            with sync_playwright() as pw:
                browser = pw.chromium.launch(executable_path='/usr/bin/chromium', headless=True,
                                             args=['--no-sandbox'])
                try:
                    context_browser = browser.new_context(viewport={'width': 1280, 'height': 900})
                    context_browser.set_default_timeout(20000)
                    context_browser.set_default_navigation_timeout(20000)
                    context_browser.route('**/*', lambda route: route.continue_() if
                        (urlsplit(route.request.url).scheme, urlsplit(route.request.url).hostname,
                         urlsplit(route.request.url).port) in {('http', '127.0.0.1', gateway_port),
                             ('http', '127.0.0.1', companion_port), ('http', '127.0.0.1', native_port)}
                        else route.abort())
                    context_browser.add_cookies([{'name': c.name, 'value': c.value, 'url': gateway_url,
                        'httpOnly': c.has_nonstandard_attr('HttpOnly')} for c in jar])
                    context_browser.add_cookies([{'name':'hb.auth.session','value':'true','url':gateway_url},
                        {'name':'hb.auth.attachment_token','value':login_result['attachmentToken'],'url':gateway_url}])
                    first = context_browser.new_page()
                    second_page = context_browser.new_page()
                    browser_errors = []
                    browser_requests = []
                    browser_responses = []
                    workshop_view_requests = []
                    workshop_view_responses = []
                    workshop_save_responses = []
                    first.on('pageerror', lambda error: browser_errors.append(str(error)))
                    second_page.on('pageerror', lambda error: browser_errors.append(str(error)))
                    first.on('request', lambda request: browser_requests.append(request.method + ' ' + request.url))
                    first.on('response', lambda response: browser_responses.append(
                        str(response.status) + ' ' + response.url))
                    first.on('request', lambda request: workshop_view_requests.append({
                        'method': request.method, 'url': request.url,
                        'body': request.post_data}) if request.url.endswith('/workshop/view') else None)
                    first.on('response', lambda response: workshop_view_responses.append(response)
                        if response.url.endswith('/workshop/view') else None)
                    first.on('response', lambda response: workshop_save_responses.append(response)
                        if response.url.endswith('/workshop/save') else None)
                    def record_save(request):
                        if request.method == 'POST' and request.url.endswith('/workshop/save'):
                            save_posts.append(request.post_data_json)
                    first.on('request', record_save)
                    second_page.on('request', record_save)
                    if not terminal_only:
                        first.goto(gateway_url + '/workshop/map', wait_until='domcontentloaded')
                        first.get_by_role('heading', name='Workshop & storage').wait_for(timeout=20000)
                        second_page.goto(gateway_url + '/workshop/map', wait_until='domcontentloaded')
                    artifacts = ROOT / 'work/rooms-browser-artifacts' / (candidate.name + '-' + uuid.uuid4().hex[:8])
                    artifacts.mkdir(mode=0o700, parents=True)
                    fixture = {'second_page': second_page, 'save_posts': lambda: list(save_posts),
                        'browser_requests': browser_requests,
                        'browser_responses': browser_responses,
                        'workshop_view_requests': workshop_view_requests,
                        'workshop_view_responses': workshop_view_responses,
                        'workshop_save_responses': workshop_save_responses,
                        'clear_save_posts': lambda: save_posts.clear(),
                        'browser_errors': browser_errors,
                        'desktop_screenshot': str(artifacts / 'desktop.png'),
                        'narrow_screenshot': str(artifacts / 'narrow.png'),
                        'desktop_edit_screenshot': str(artifacts / 'desktop-edit.png'),
                        'narrow_browse_screenshot': str(artifacts / 'narrow-browse.png'),
                        'narrow_edit_screenshot': str(artifacts / 'narrow-edit.png'),
                        'terminal_view_failure_screenshot': str(artifacts / 'terminal-workshop-view-failure.png'),
                        'terminal_management_revocation_screenshot': str(
                            artifacts / 'terminal-management-revocation-failure.png'),
                        'native_name_before': native_location('before'), 'native_location': native_location,
                        'native_location_id': location['id'], 'other_native_location_id': other_location['id'],
                        'refresh_root_id': refresh_root['id'], 'refresh_child_id': refresh_child['id'],
                        'mutate_native': mutate_native,
                        'native_item_name': native_item['name'], 'native_item_id': native_item['id'],
                        'shelf_id': shelf_id, 'shelf_photo_id': shelf_photo['id'],
                        'browse_rack_id': browse_rack_id, 'browse_shelf_id': browse_shelf_id,
                        'shelf_photo_sha256': hashlib.sha256(shelf_photo_bytes).hexdigest(),
                        'parent_photo_id': parent_photo['id'],
                        'unauthenticated_photo_status': unauthenticated_photo_status,
                        'legacy_revision': legacy_revision,
                        'original_group_id': context['group']['id'],
                        'user_id': context['user']['id'], 'identity': context['identity'],
                        'pending_save_key': 'workshop-pending:' + context['group']['id'] + ':' + context['user']['id'],
                        'planner_draft_key': 'workshop-room-draft:' + context['group']['id'] + ':' + context['user']['id'],
                        'gateway_url': gateway_url,
                        'companion_url': companion_url,
                        'set_open_admin': lambda value: scope.__setitem__('OPEN_ADMIN', value),
                        'terminal_draft_state': lambda p, context: p.evaluate('''context => {
                          const rows = Object.keys(localStorage).filter(key => key.startsWith('workshop-room-draft:'));
                          for (const key of rows) { try { const value = JSON.parse(localStorage.getItem(key));
                            if (value?.workshop_context?.group_id === context.group_id) return value; } catch {} }
                          return null;
                        }''', context),
                        'drop_next_save_response': lambda route: None,
                        'draft_state': lambda p: p.evaluate(
                            '(key) => JSON.parse(localStorage.getItem(key + ":" + sessionStorage.getItem("workshop-room-draft-tab")) || "null")',
                            'workshop-room-draft:' + context['group']['id'] + ':' + context['user']['id']),
                        'original_group_name': context['group']['name'],
                        'alternate_group_name': alternate_group['name'],
                        'displayed_group': lambda p: p.get_by_role('combobox', name='Select collection').inner_text(),
                        'document': lambda p: p.evaluate('''async (group) => {
                          const response = await fetch('/workshop-api/workshop', {headers: {'X-Workshop-Group': group}});
                          if (!response.ok) throw new Error('Could not read the disposable Workshop document.');
                          return response.json();
                        }''', context['group']['id']),
                        'drop_next_save_response': lambda p: install_lost_save_response(p),
                        'reject_schema_save': lambda p: install_schema_rejection(p),
                        'invalid_room_url': gateway_url + '/workshop/map?room_id=' + str(uuid.uuid4()),
                    'ambiguous_bookmark_url': gateway_url + '/workshop/map?id=' + location['id'],
                        'populated_bookmark_url': lambda: gateway_url + '/workshop/map?room_id=' + fixture['room_three'] + '&drawing_id=' + fixture['drawing_id'],
                        'drawing_bookmark_url': lambda room_id, drawing_id: gateway_url +
                            '/workshop/map?room_id=' + room_id + '&drawing_id=' + drawing_id,
                        'server_revision': None}
                    if terminal_only:
                        def drop_committed_response(route):
                            route.fetch()
                            route.abort()
                        fixture['drop_next_save_response'] = drop_committed_response
                        first.set_default_timeout(20000)
                        first.goto(companion_url, wait_until='domcontentloaded')
                        test_terminal_room_drafts(first, fixture)
                        first.screenshot(path=fixture['narrow_edit_screenshot'], full_page=True)
                        allowed_errors = manifest.get('known_browser_diagnostics', [])
                        unexpected_errors = [error for error in browser_errors
                                             if not any(known in error for known in allowed_errors)]
                        if unexpected_errors:
                            raise AssertionError('Unexpected browser JavaScript errors: ' + repr(unexpected_errors))
                        print(json.dumps({'case':'terminal_rooms','browser_screenshots':[
                            fixture['narrow_edit_screenshot']], 'browser_errors':browser_errors,
                            'save_posts':len(save_posts),'candidate':str(candidate)}))
                        return
                    test_desktop_room_drafts(first, fixture)
                    allowed_errors = manifest.get('known_browser_diagnostics', [])
                    unexpected_errors = [error for error in browser_errors
                                         if not any(known in error for known in allowed_errors)]
                    if unexpected_errors:
                        raise AssertionError('Unexpected browser JavaScript errors: ' + repr(unexpected_errors))
                    print(json.dumps({'browser_screenshots': [fixture['desktop_screenshot'],
                        fixture['desktop_edit_screenshot'], fixture['narrow_screenshot'],
                        fixture['narrow_browse_screenshot'], fixture['narrow_edit_screenshot']],
                        'browser_errors': browser_errors}))
                    print(json.dumps({'case':'desktop_rooms','save_posts':len(save_posts),
                                      'candidate':str(candidate),'ui_provenance':manifest['ui_provenance']}))
                finally:
                    browser.close()
        except Exception:
            try:
                log.flush()
                print('NATIVE LOG TAIL\n' + (data_root / 'native.log').read_text(errors='replace')[-5000:])
            except OSError:
                pass
            raise
        finally:
            active_error = sys.exc_info()[1]
            teardown_errors = []
            try:
                after_manifest = validate_candidate(candidate)
                if after_manifest != manifest or tree_hash(candidate) != before_bundle:
                    raise RuntimeError('Candidate bundle changed during browser verification.')
            except BaseException as error:
                teardown_errors.append(error)
            for server in (gateway, companion):
                if server:
                    try:
                        server.shutdown()
                        server.server_close()
                    except BaseException as error:
                        teardown_errors.append(error)
            if native is not None:
                try:
                    native.terminate()
                    native.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    try:
                        native.kill()
                        native.wait(timeout=5)
                    except BaseException as error:
                        teardown_errors.append(error)
                except BaseException as error:
                    teardown_errors.append(error)
            try:
                log.close()
            except BaseException as error:
                teardown_errors.append(error)
            try:
                for key in tuple(os.environ):
                    if key.startswith('HBOX_'):
                        os.environ.pop(key, None)
                for key, value in prior_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
            except BaseException as error:
                teardown_errors.append(error)
            try:
                sys.dont_write_bytecode = prior_bytecode
            except BaseException as error:
                teardown_errors.append(error)
            if teardown_errors:
                if active_error is not None:
                    raise BaseExceptionGroup('Runtime and post-run validation/cleanup failures.',
                                             [active_error, *teardown_errors])
                raise BaseExceptionGroup('Post-run validation/cleanup failures.', teardown_errors)


def run_terminal(candidate: pathlib.Path, ports: tuple[int, int, int]) -> None:
    run_desktop(candidate, ports, terminal_only=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=('desktop_rooms', 'terminal_rooms', 'all'))
    parser.add_argument('--native-port', type=int, default=0)
    parser.add_argument('--companion-port', type=int, default=0)
    parser.add_argument('--gateway-port', type=int, default=0)
    parser.add_argument('--candidate', type=pathlib.Path,
                        default=pathlib.Path(os.environ['WORKSHOP_CANDIDATE_FIXTURE_BUNDLE'])
                        if os.environ.get('WORKSHOP_CANDIDATE_FIXTURE_BUNDLE') else None)
    parser.add_argument('--previous', type=pathlib.Path)
    parser.add_argument('--stage-fixture', type=pathlib.Path)
    parser.add_argument('--terminal-runtime', action='store_true',
                        help='Allow the approved Task5 terminal/server delta over unchanged Task4 public output.')
    parser.add_argument('--source', type=pathlib.Path)
    parser.add_argument('--public', type=pathlib.Path)
    parser.add_argument('--native', type=pathlib.Path)
    parser.add_argument('--build-receipt', type=pathlib.Path)
    parser.add_argument('--input-manifest', type=pathlib.Path)
    parser.add_argument('--static-manifest', type=pathlib.Path)
    args = parser.parse_args()
    if args.stage_fixture:
        if (args.case or args.candidate or not all((args.source, args.public, args.native, args.build_receipt)) or
                bool(args.input_manifest) != bool(args.static_manifest)):
            parser.error('staging requires source, public, native, receipt, and either both or neither separate manifests')
        stage_fixture_bundle(args.stage_fixture, source=args.source, public=args.public,
                             binary=args.native, receipt_path=args.build_receipt,
                             input_manifest_path=args.input_manifest, static_manifest_path=args.static_manifest,
                             terminal_runtime=args.terminal_runtime)
        print('STAGED ' + str(args.stage_fixture.resolve()))
        return 0
    if not args.candidate or not args.case:
        parser.error('verification requires --case and an explicit --candidate')
    manifest = validate_candidate(args.candidate)
    if args.previous:
        validate_candidate(args.previous)
    print('VALIDATED ' + manifest['purpose'] + ' ' + str(args.candidate.resolve()))
    selected = []
    for requested in (args.native_port, args.companion_port, args.gateway_port):
        port = requested or free_port()
        if not 32768 <= port <= 60999 or port in selected:
            parser.error('Choose distinct unprivileged ephemeral loopback ports, or use zero.')
        selected.append(port)
    require_ports_free(tuple(selected))
    if args.case in ('desktop_rooms', 'all'):
        run_desktop(args.candidate, tuple(selected))
    if args.case in ('terminal_rooms', 'all'):
        run_terminal(args.candidate, tuple(selected))
    if args.case == 'all':
        print(json.dumps({
            'fixture_only': True,
            'compatibility_claim': 'unclaimed',
            'same_store_bundle_rollback': 'not_run: browser fixture inputs are not matched format-2 O/C/F packages',
            'live_mutations': 0,
            'physical_prints': 0,
        }, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
