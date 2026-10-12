#!/usr/bin/env python3
"""Build the pinned standalone PrintDesignPro host without touching native builds."""
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess

NODE = pathlib.Path('/home/user/Desktop/inventory-system/work/toolchains/node-v24.21.0-linux-arm64/bin')
PNPM = pathlib.Path('/home/user/Desktop/inventory-system/work/toolchains/pnpm/node_modules/.bin/pnpm')
PIN = 'eb118cc05b169c554066d823c44dc179aa3b96bb'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    root = pathlib.Path(args.source_root).resolve()
    package = root / 'label-ui'
    out = (root / args.output).resolve() if not pathlib.Path(args.output).is_absolute() else pathlib.Path(args.output).resolve()
    work_root = (root / 'work').resolve()
    try:
        out.relative_to(work_root)
    except ValueError:
        raise SystemExit('Refusing output outside the isolated source-root work/ directory')
    if out == work_root:
        raise SystemExit('Refusing to replace the isolated work/ directory itself')
    if not (package / 'vendor/print-design-pro/src/index.ts').is_file():
        raise SystemExit('Pinned PrintDesignPro source is missing')
    if json.loads((package / 'vendor-manifest.json').read_text())['upstream_commit'] != PIN:
        raise SystemExit('Vendor manifest does not name the required full upstream pin')
    if (package / 'public/licenses/PRINTDESIGNPRO-MIT.txt').read_bytes() != (package / 'vendor/print-design-pro/LICENSE').read_bytes():
        raise SystemExit('Distributed PrintDesignPro MIT notice differs from the pinned upstream license')
    env = dict(os.environ, PATH=str(NODE) + os.pathsep + os.environ.get('PATH', ''))
    subprocess.run([str(PNPM), 'install', '--frozen-lockfile', '--ignore-scripts'], cwd=package, env=env, check=True)
    subprocess.run([str(PNPM), 'build'], cwd=package, env=env, check=True)
    if out.exists():
        old_manifest = out / 'manifest.json'
        if not old_manifest.is_file() or json.loads(old_manifest.read_text()).get('builder') != 'deploy/build-label-ui.py':
            raise SystemExit(f'Refusing to remove unowned output directory: {out}')
        shutil.rmtree(out)
    shutil.copytree(package / 'dist', out)
    build_manifest = {
        **json.loads((package / 'vendor-manifest.json').read_text()),
        'builder': 'deploy/build-label-ui.py',
        'upstream_commit': PIN,
        'node': subprocess.check_output([str(NODE / 'node'), '--version'], text=True).strip(),
        'pnpm': subprocess.check_output([str(PNPM), '--version'], env=env, text=True).strip(),
        'dependencies_lock_sha256': sha(package / 'pnpm-lock.yaml'),
        'font_sha256': sha(package / 'public/fonts/DejaVuSans.ttf'),
        'font_license_sha256': sha(package / 'public/fonts/DejaVu-Fonts-Copyright.txt'),
        'upstream_license_sha256': sha(package / 'vendor/print-design-pro/LICENSE'),
        'vendor_source_sha256': hashlib.sha256(b''.join(
            path.relative_to(package / 'vendor/print-design-pro').as_posix().encode() + b'\0' + path.read_bytes()
            for path in sorted((package / 'vendor/print-design-pro').rglob('*')) if path.is_file()
        )).hexdigest(),
        'patch_sha256': sha(package / 'patches/0001-offline-fonts.patch'),
        'build_inputs': {},
        'runtime_assets': {},
    }
    input_roots = ['package.json', 'pnpm-lock.yaml', 'vite.config.ts', 'editor.html', 'render.html', 'vendor-manifest.json', 'src', 'public', 'patches']
    for item in input_roots:
        path = package / item
        inputs = [path] if path.is_file() else sorted(entry for entry in path.rglob('*') if entry.is_file())
        for entry in inputs:
            build_manifest['build_inputs'][entry.relative_to(package).as_posix()] = sha(entry)
    for path in sorted(p for p in out.rglob('*') if p.is_file()):
        build_manifest['runtime_assets'][path.relative_to(out).as_posix()] = sha(path)
    (out / 'manifest.json').write_text(json.dumps(build_manifest, indent=2) + '\n')
    print(f'Built standalone label UI at {out}')


if __name__ == '__main__':
    main()
