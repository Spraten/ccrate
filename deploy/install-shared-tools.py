#!/usr/bin/env python3
"""Install shared tools. Importing this module never touches services or accounts."""
import json
import os
import pathlib
import subprocess
import time
import urllib.request

ROOT = pathlib.Path('/home/user/Desktop/inventory-system')
SERVICE_NAMES = ('homebox-native.service', 'homebox-companion.service', 'homebox-workshop-gateway.service')


def snapshot_services(service_source, directory, snapshot):
    source, directory, snapshot = pathlib.Path(service_source), pathlib.Path(directory), pathlib.Path(snapshot)
    snapshot.mkdir(parents=True, mode=0o700, exist_ok=True)
    previous = {}
    for name in SERVICE_NAMES:
        path = directory / name
        previous[name] = path.read_bytes() if path.exists() else None
        if previous[name] is not None: (snapshot/name).write_bytes(previous[name])
    return previous


def install_service_files(service_source, directory):
    """Write the three service definitions; caller owns rollback on failure."""
    source, directory = pathlib.Path(service_source), pathlib.Path(directory)
    for name in SERVICE_NAMES:
        (directory/name).write_bytes((source/name).read_bytes())


def restore_services(directory, previous):
    directory = pathlib.Path(directory)
    for name, body in previous.items():
        path = directory / name
        if body is not None: path.write_bytes(body)
        else: path.unlink(missing_ok=True)


def healthy(url, *, open_url=urllib.request.urlopen, sleep=time.sleep):
    for _ in range(40):
        try:
            with open_url(url, timeout=2) as response:
                if response.status == 200: return
        except OSError: sleep(.25)
    raise RuntimeError('Service did not become ready: '+url)


def install(root=ROOT, *, directory=None, run=subprocess.run, open_url=urllib.request.urlopen):
    root = pathlib.Path(root)
    os.umask(0o077)
    import sys
    sys.path.insert(0, str(root/'ops'))
    from homebox import Homebox
    native = Homebox(root, base='http://127.0.0.1:17745')
    account = native.call('/api/v1/users/self')['item']
    managers = root/'work/ops/desktop-managers.json'
    config = json.loads(managers.read_text()) if managers.exists() else {'managers': []}
    config['owner_id'] = account['id']
    reference = {'user_id': account['id'], 'group_id': account['defaultGroupId']}
    if reference not in config['managers']: config['managers'].append(reference)
    managers.write_text(json.dumps(config, indent=2)+'\n'); managers.chmod(0o600)
    directory = pathlib.Path(directory or pathlib.Path.home()/'.config/systemd/user')
    directory.mkdir(parents=True, exist_ok=True)
    snapshot = root/'work/shared-tools-rollback'/time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    previous = snapshot_services(root/'deploy', directory, snapshot)
    try:
        install_service_files(root/'deploy', directory)
        run(['systemctl','--user','daemon-reload'], check=True)
        run(['systemctl','--user','restart','homebox-native.service'], check=True)
        healthy('http://127.0.0.1:17747/api/v1/status', open_url=open_url)
        run(['systemctl','--user','restart','homebox-companion.service'], check=True)
        healthy('http://127.0.0.1:17749/', open_url=open_url)
        run(['systemctl','--user','enable','--now','homebox-workshop-gateway.service'], check=True)
        healthy('http://127.0.0.1:17745/workshop/', open_url=open_url)
        healthy('http://127.0.0.1:17745/', open_url=open_url)
    except Exception:
        run(['systemctl','--user','stop','homebox-workshop-gateway.service'], check=False)
        restore_services(directory, previous)
        for name, body in previous.items():
            if body is None: run(['systemctl','--user','disable',name], check=False, capture_output=True)
        run(['systemctl','--user','daemon-reload'], check=True)
        run(['systemctl','--user','restart','homebox-native.service','homebox-companion.service'], check=True)
        raise
    print('Shared Homebox tools are ready at port 17745; Equipment Terminal remains at port 17749.')


if __name__ == '__main__': install()
