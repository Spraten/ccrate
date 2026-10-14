#!/usr/bin/env python3
"""Build the runtime compatibility manifest. Importing this module is safe."""
import hashlib
import importlib.metadata
import json
import pathlib
import platform
import sqlite3
import subprocess
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from homebox_patchset import source_commit


def build_runtime_manifest(root, *, run=subprocess.check_output, python_version=None, sqlite_version=None, platform_name=None):
    root = pathlib.Path(root)
    def command(args): return run(args, cwd=root, text=True).strip()
    distributions = importlib.metadata.distributions(path=[str(root/'work/hardware/python')]) if (root/'work/hardware/python').is_dir() else []
    binaries = [name for name in ('work/homebox-bin/homebox','work/supvan-cups/target/release/examples/kiosk-label') if (root/name).is_file()]
    return {
        'format': 1, 'platform': platform_name or platform.platform(),
        'os_release': pathlib.Path('/etc/os-release').read_text() if pathlib.Path('/etc/os-release').is_file() else '',
        'python': python_version or sys.version, 'sqlite': sqlite_version or sqlite3.sqlite_version,
        'chromium': command(['chromium','--version']), 'homebox_version': '0.26.2',
        'homebox_pin': source_commit(root/'upstream/homebox') if (root/'upstream/homebox').exists() else command(['git','-C','upstream/homebox','rev-parse','HEAD']),
        'printer_source_pin': command(['git','-C','work/supvan-cups','rev-parse','HEAD']),
        'project_commit': command(['git','rev-parse','HEAD']), 'operational_schema': 2,
        'native_field_formats': {'map': 1, 'kit': 1},
        'python_dependencies': sorted([{'name': d.metadata['Name'], 'version': d.version} for d in distributions], key=lambda d:d['name']),
        'binary_sha256': {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in binaries},
        'system_packages': command(['dpkg-query','-W','python3','chromium','liblzma5','libc6','libstdc++6','libnss3']),
        'offline_runtime_in_backup': True,
    }


def main():
    root = pathlib.Path('/home/user/Desktop/inventory-system')
    result = build_runtime_manifest(root)
    (root/'docs/runtime-manifest.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({k:result[k] for k in ['python','chromium','sqlite','homebox_version','python_dependencies']}, indent=2))


if __name__ == '__main__': main()
