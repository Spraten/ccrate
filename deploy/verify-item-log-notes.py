#!/usr/bin/env python3
"""Run the notes GUI against an isolated native database and captured assets."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def validate_tree(root: Path, manifest_path: Path) -> Path:
    manifest = json.loads(manifest_path.read_text())
    source_path = Path(manifest['source'])
    if source_path.is_symlink():
        raise SystemExit('captured Terminal static root is a symlink')
    selected = source_path.resolve(strict=True)
    if not (selected / 'index.html').is_file():
        raise SystemExit('captured Terminal static root is not a regular selected tree')
    entries = manifest.get('entries')
    if not isinstance(entries, dict) or not entries:
        raise SystemExit('captured Terminal manifest is incomplete')
    actual = set()
    for path in selected.rglob('*'):
        relative = path.relative_to(selected).as_posix()
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise SystemExit('captured Terminal static contains a symlink')
        if stat.S_ISDIR(info.st_mode):
            actual.add(relative)
            continue
        if not stat.S_ISREG(info.st_mode):
            raise SystemExit('captured Terminal static contains a special file')
        actual.add(relative)
        expected = entries.get(relative)
        if (not expected or expected.get('type') != 'file' or expected.get('sha256') != sha256(path)
                or expected.get('size') != info.st_size or expected.get('mode') != stat.S_IMODE(info.st_mode)):
            raise SystemExit('captured Terminal static differs from its reviewed manifest')
    if actual != set(entries):
        raise SystemExit('captured Terminal static membership differs from its reviewed manifest')
    return selected


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--live-root', required=True, type=Path)
    parser.add_argument('--native-binary', required=True, type=Path)
    parser.add_argument('--static-root', required=True, type=Path)
    return parser.parse_args()


def main():
    args = parse_args()
    if args.source_root.is_symlink():
        raise SystemExit('--source-root must be a direct isolated candidate directory')
    source = args.source_root.resolve(strict=True)
    live = args.live_root.resolve(strict=True)
    binary = args.native_binary.resolve(strict=True)
    static = args.static_root.resolve(strict=True)
    if not (source / 'ops/item_notes.py').is_file() or not (source / 'deploy/kiosk-server.py').is_file():
        raise SystemExit('--source-root is not the frozen notes candidate')
    if source != Path(__file__).resolve().parents[1]:
        raise SystemExit('--source-root must match this verifier\'s candidate source directory')
    if not (live / 'work/hardware/python').is_dir():
        raise SystemExit('--live-root has no installed read-only Python runtime')
    if not stat.S_ISREG(binary.lstat().st_mode) or not os.access(binary, os.X_OK):
        raise SystemExit('--native-binary must be an executable regular file')
    if sha256(binary) != 'e8502bd85b18ff14d67172dffb0006e06504eddbe38a7c3d643bdee2088dd15a':
        raise SystemExit('--native-binary differs from the reviewed unchanged native pin')
    if not (static / 'index.html').is_file():
        raise SystemExit('--static-root is not a built native frontend')

    prep = source.parents[1]
    terminal_manifest = prep / 'baseline/terminal-static-manifest.json'
    if not terminal_manifest.is_file():
        raise SystemExit('reviewed captured Terminal manifest is missing')
    if sha256(terminal_manifest) != '11142902f59c61fb13e796d7899f1173cf02ef6058b8c54142b3b39be7be17b6':
        raise SystemExit('captured Terminal manifest differs from the reviewed O static binding')
    terminal_static = validate_tree(source, terminal_manifest)
    runner = prep / 'runners/verify-desktop-integration.py'
    if not runner.is_file():
        raise SystemExit('guarded disposable runner is missing')

    env = dict(os.environ)
    env.update({
        'TERMINAL_LABEL_SOURCE_ROOT': str(source),
        'TERMINAL_LABEL_LIVE_ROOT': str(live),
        'HOMEBOX_VERIFY_NATIVE_BINARY': str(binary),
        'ITEM_NOTES_STATIC_ROOT': str(static),
        'ITEM_NOTES_TERMINAL_STATIC_ROOT': str(terminal_static),
        'ITEM_NOTES_GUI_FOCUS': '1',
    })
    completed = subprocess.run([sys.executable, str(runner)], cwd=source, env=env, check=False)
    return completed.returncode


if __name__ == '__main__':
    raise SystemExit(main())
