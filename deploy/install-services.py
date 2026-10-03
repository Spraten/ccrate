"""Install user services and replace only this project's existing processes."""
import pathlib,subprocess,time,os,signal
root=pathlib.Path('/home/user/Desktop/inventory-system');folder=pathlib.Path.home()/'.config/systemd/user';folder.mkdir(parents=True,exist_ok=True)
for name in ['homebox-native.service','homebox-companion.service']:(folder/name).write_bytes((root/'deploy'/name).read_bytes())
for proc in pathlib.Path('/proc').glob('[0-9]*'):
    try:
        cmd=(proc/'cmdline').read_bytes().split(b'\0')
        if str(root/'work/homebox-bin/homebox').encode() in cmd or str(root/'deploy/kiosk-server.py').encode() in cmd:
            os.kill(int(proc.name),signal.SIGTERM)
    except (PermissionError,ProcessLookupError,FileNotFoundError):pass
time.sleep(1)
subprocess.run(['systemctl','--user','daemon-reload'],check=True)
subprocess.run(['systemctl','--user','enable','--now','homebox-native.service','homebox-companion.service'],check=True)
print('Project user services installed and enabled')
