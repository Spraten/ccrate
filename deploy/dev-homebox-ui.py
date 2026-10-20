#!/usr/bin/env python3
"""Keep a patched Homebox UI workspace current and run its Nuxt dev server."""

import argparse
import filecmp
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / 'work/homebox-ui-dev'
TOOLCHAIN = ROOT / 'work/toolchains'
SOURCE_MARKER = '.ccrate-ui-dev-source.json'
INSTALL_MARKER = '.ccrate-ui-dev-lock.sha256'
PRESERVE = {'node_modules', '.nuxt', '.output'}


def ui_builder():
    script = ROOT / 'deploy/build-homebox-ui.py'
    spec = importlib.util.spec_from_file_location('ccrate_ui_builder', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_inputs():
    roots = (
        ROOT / 'upstream/homebox/frontend',
        ROOT / 'homebox-ui/overlay',
        ROOT / 'kiosk/branding',
        ROOT / 'deploy/homebox-patches',
    )
    singles = (
        ROOT / 'homebox-ui/pnpm-lock.yaml',
        ROOT / 'deploy/homebox-patchset.json',
        ROOT / 'deploy/homebox_patchset.py',
        ROOT / 'deploy/build-homebox-ui.py',
        ROOT / 'kiosk/member-avatar.js',
        ROOT / 'kiosk/label-editor.js',
    )
    return sorted((*singles, *(path for root in roots for path in root.rglob('*') if path.is_file())))


def source_signature():
    return tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in source_inputs())


def lock_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def needs_install():
    marker = WORKSPACE / INSTALL_MARKER
    return (
        not (WORKSPACE / 'node_modules/.modules.yaml').is_file()
        or not marker.is_file()
        or marker.read_text().strip() != lock_digest(ROOT / 'homebox-ui/pnpm-lock.yaml')
    )


def sync_source(staged):
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    marker = WORKSPACE / SOURCE_MARKER
    if not marker.exists() and any(WORKSPACE.iterdir()):
        raise RuntimeError(f'Refusing to overwrite an unowned dev workspace: {WORKSPACE}')
    previous = set(json.loads(marker.read_text())) if marker.exists() else set()
    current = set()
    for source in staged.rglob('*'):
        relative = source.relative_to(staged)
        if PRESERVE.intersection(relative.parts) or not source.is_file():
            continue
        name = relative.as_posix()
        current.add(name)
        target = WORKSPACE / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink() or not target.is_file() or not filecmp.cmp(source, target, shallow=False):
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as temp:
                temporary = pathlib.Path(temp.name)
            try:
                shutil.copy2(source, temporary)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
    for name in previous - current:
        if PRESERVE.intersection(pathlib.PurePosixPath(name).parts):
            continue
        target = WORKSPACE / name
        target.unlink(missing_ok=True)
        parent = target.parent
        while parent != WORKSPACE:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
    marker.write_text(json.dumps(sorted(current)) + '\n')


def toolchain():
    node_root = pathlib.Path((TOOLCHAIN / 'node-path.txt').read_text().strip())
    environment = dict(os.environ, PATH=str(node_root / 'bin') + os.pathsep + os.environ.get('PATH', ''))
    pnpm = ui_builder().resolve_pnpm_launcher(TOOLCHAIN)
    return str(pnpm), environment


def prepare_workspace():
    builder = ui_builder()
    WORKSPACE.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='homebox-ui-dev-source-', dir=WORKSPACE.parent) as temp:
        staged = pathlib.Path(temp)
        builder.prepare_source_workspace(staged)
        sync_source(staged)
    if needs_install():
        pnpm, environment = toolchain()
        print('Installing pinned frontend dependencies in', WORKSPACE, flush=True)
        builder.run_frontend_command([pnpm, 'install', '--frozen-lockfile', '--ignore-scripts'], cwd=WORKSPACE, env=environment)
        (WORKSPACE / INSTALL_MARKER).write_text(lock_digest(WORKSPACE / 'pnpm-lock.yaml') + '\n')
    builder.configure_oxc_wasi_binding(WORKSPACE, TOOLCHAIN)
    print('Dev UI source ready in', WORKSPACE, flush=True)


def stop_server(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def serve():
    host = os.environ.get('WORKSHOP_UI_DEV_HOST', '127.0.0.1')
    port = int(os.environ.get('WORKSHOP_UI_DEV_PORT', '17751'))
    if not 1 <= port <= 65535:
        raise ValueError('WORKSHOP_UI_DEV_PORT must be between 1 and 65535')
    signature = source_signature()
    prepare_workspace()
    _, environment = toolchain()
    node = pathlib.Path((TOOLCHAIN / 'node-path.txt').read_text().strip()) / 'bin/node'
    command = [str(node), str(WORKSPACE / 'node_modules/nuxt/bin/nuxt.mjs'), 'dev', '--host', host, '--port', str(port)]
    print(f'Starting Nuxt dev at http://{host}:{port}', flush=True)
    process = subprocess.Popen(command, cwd=WORKSPACE, env=environment)
    try:
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        while process.poll() is None:
            time.sleep(1)
            updated = source_signature()
            if updated != signature:
                if needs_install():
                    stop_server(process)
                prepare_workspace()
                signature = updated
                if process.poll() is not None:
                    print('Restarting Nuxt after dependency update', flush=True)
                    process = subprocess.Popen(command, cwd=WORKSPACE, env=environment)
        return process.returncode
    finally:
        stop_server(process)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'serve'))
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare_workspace()
        return 0
    return serve()


if __name__ == '__main__':
    sys.exit(main())
