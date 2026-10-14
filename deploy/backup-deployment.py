#!/usr/bin/env python3
"""Cold, private offline deployment backup. Importing this module is safe."""
import contextlib
import fcntl
import hashlib
import json
import os
import pathlib
import shutil
import sqlite3
import subprocess
import tarfile
import time

BASE_MEMBERS = [
    'AGENTS.md', '.git', 'ops', 'kiosk', 'deploy', 'docs', 'upstream/homebox',
    'work/baseline/data', 'work/baseline/pepper', 'work/baseline/test-account.json',
    'work/ops', 'work/homebox-bin/homebox', 'work/hardware/python',
    'work/supvan-cups/target/release/examples/kiosk-label',
    'label-ui/src', 'label-ui/vendor', 'label-ui/public', 'label-ui/patches',
    'label-ui/package.json', 'label-ui/pnpm-lock.yaml', 'label-ui/vite.config.ts',
    'label-ui/editor.html', 'label-ui/render.html', 'label-ui/vendor-manifest.json',
    'work/label-ui-build',
]
OPTIONAL_DATABASES = ('work/ops/imports.db', 'work/ops/workshop.db', 'work/ops/label-layouts.db',
                      'work/ops/feedback-reports.db')
HASHED_BINARIES = ('work/homebox-bin/homebox', 'work/supvan-cups/target/release/examples/kiosk-label')


def database_inventory(root):
    root = pathlib.Path(root)
    names = ['work/ops/ledger.db', 'work/baseline/data/homebox.db']
    names.extend(name for name in OPTIONAL_DATABASES if (root / name).is_file())
    return names


def checkpoint_databases(root, databases):
    """Checkpoint and integrity-check only explicitly supplied disposable/live paths."""
    root = pathlib.Path(root)
    for name in databases:
        with contextlib.closing(sqlite3.connect(root / name)) as connection:
            checkpoint = connection.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
            if checkpoint[0] != 0:
                raise RuntimeError('Database checkpoint was busy: ' + name)
            if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Database integrity check failed: ' + name)


def build_backup_manifest(root, *, created_at, commit, homebox_pin, members, databases):
    root = pathlib.Path(root)
    hashed = list(databases) + [name for name in HASHED_BINARIES if (root / name).is_file()]
    return {
        'format': 2, 'created_at': created_at, 'commit': commit, 'homebox_pin': homebox_pin,
        'members': list(members), 'sha256': {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in hashed},
    }


def create_archive(root, target, members, manifest):
    """Create a fixture-safe archive at the caller's explicit destination."""
    root, target = pathlib.Path(root), pathlib.Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix('.partial')
    if partial.exists():
        partial.unlink()
    excluded = {name + '-shm' for name in manifest.get('sha256', {})}
    with tarfile.open(partial, 'w:gz', compresslevel=1) as archive:
        for name in members:
            path = root / name
            if not path.exists():
                raise FileNotFoundError(name)
            archive.add(path.resolve() if name in ('work/homebox-ui-current', 'work/kiosk-ui-current') else path,
                        arcname=name, filter=lambda entry: None if entry.name in excluded else entry)
        body = json.dumps(manifest, indent=2).encode()
        info = tarfile.TarInfo('deployment-manifest.json'); info.size = len(body); info.mode = 0o600
        import io
        archive.addfile(info, io.BytesIO(body))
    partial.replace(target)
    target.chmod(0o600)
    return target


BACKUP_SERVICES = ('homebox-native.service', 'homebox-companion.service',
                   'homebox-workshop-gateway.service')


def stop_backup_services(runner):
    """Stop the request gateway before its SQLite data is checkpointed or hashed."""
    active = {service for service in BACKUP_SERVICES
              if runner.run(['systemctl', '--user', 'is-active', '--quiet', service],
                            check=False).returncode == 0}
    try:
        runner.run(['systemctl', '--user', 'stop', 'homebox-workshop-gateway.service'], check=True)
        runner.run(['systemctl', '--user', 'stop', 'homebox-companion.service',
                    'homebox-native.service'], check=True)
    except Exception:
        resume_backup_services(runner, active)
        raise
    return active


def resume_backup_services(runner, active):
    """Restore only services that were active before the backup began."""
    for service in BACKUP_SERVICES:
        if service in active:
            runner.run(['systemctl', '--user', 'start', service], check=True)


def main():
    root = pathlib.Path('/home/user/Desktop/inventory-system')
    folder = root / 'work/backups'; folder.mkdir(mode=0o700, exist_ok=True)
    os.umask(0o077)
    with (folder / 'deployment.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
        target = folder / ('deployment-' + stamp + '.tar.gz')
        members = list(BASE_MEMBERS)
        for name, directory in (('homebox-backend', root/'homebox-backend'), ('desktop', root/'desktop'),
                                ('homebox-ui', root/'homebox-ui'), ('work/homebox-ui-current', root/'work/homebox-ui-current'),
                                ('work/kiosk-ui-current', root/'work/kiosk-ui-current')):
            if directory.is_dir(): members.append(name)
        databases = database_inventory(root)
        active_services = set()
        try:
            active_services = stop_backup_services(subprocess)
            checkpoint_databases(root, databases)
            manifest = build_backup_manifest(root, created_at=stamp,
                commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
                homebox_pin=subprocess.check_output(['git', '-C', 'upstream/homebox', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
                members=members, databases=databases)
            create_archive(root, target, members, manifest)
            (target.with_suffix('.sha256')).write_text(hashlib.sha256(target.read_bytes()).hexdigest() + '  ' + target.name + '\n')
            result = {'status': 'completed', 'backup': target.name, 'bytes': target.stat().st_size, 'database_integrity': 'ok'}
            state_path = root / 'work/backup-status.json'
            try: state = json.loads(state_path.read_text())
            except (FileNotFoundError, ValueError): state = {}
            state.update(result)
            state_path.write_text(json.dumps(state)); state_path.chmod(0o600)
            print(json.dumps(result))
        except Exception:
            (root/'work/backup-status.json').write_text(json.dumps({'status':'failed','reason':'Backup failed; inspect the local service log'}))
            raise
        finally:
            resume_backup_services(subprocess, active_services)


if __name__ == '__main__':
    main()
