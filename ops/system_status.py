"""Non-secret local diagnostics and an isolated user-service backup request."""
import json,pathlib,shutil,subprocess,time,os
from ledger import uuid,Conflict
from hardware import reconnect,camera_status
ROOT=pathlib.Path(os.environ.get('WORKSHOP_ROOT','/home/user/Desktop/inventory-system'));STATE=ROOT/'work/backup-status.json'
def unit(name):
    result=subprocess.run(['systemctl','--user','is-active',name],capture_output=True,text=True,timeout=5)
    return result.stdout.strip() or 'unknown'
def read_state():
    try:return json.loads(STATE.read_text())
    except (FileNotFoundError,ValueError):return None
def storage_health(disk):
    """Warn before local inventory, photo and journal writes run out of space."""
    if disk.free < 512 * 1024**2:
        return {'level':'critical','message':'Storage critically low. Ask an administrator to free space before adding photos or creating backups. Preserve inventory and recovery files.'}
    if disk.free < 2 * 1024**3 or (disk.total and disk.free / disk.total < 0.10):
        return {'level':'warning','message':'Storage is running low. Plan an approved external backup and have an administrator review old backup files.'}
    return {'level':'ok','message':None}

def status():
    disk=shutil.disk_usage(ROOT)
    printer=reconnect('printer');camera=camera_status()
    return {'homebox':unit('homebox-native.service'),'companion':unit('homebox-companion.service'),'printer':printer,'camera':camera,'camera_devices':len(list(pathlib.Path('/dev').glob('video*'))),'free_gb':round(disk.free/1024**3,1),'storage':storage_health(disk),'homebox_version':'0.26.2','backup':read_state(),'private_backups':len(list((ROOT/'work/backups').glob('deployment-*.tar.gz')))}
def start_backup(key):
    key=uuid(key);previous=read_state()
    if previous and previous.get('request_key')==key:return previous
    if previous and previous.get('status')=='running' and unit(previous['unit']) in ('active','activating'):raise Conflict('A backup is already running')
    name='homebox-backup-'+key
    state={'request_key':key,'unit':name,'status':'running','started_at':time.time()};STATE.write_text(json.dumps(state));STATE.chmod(0o600)
    try:subprocess.run(['systemd-run','--user','--unit='+name,'--collect','/usr/bin/python3',str(ROOT/'deploy/backup-deployment.py')],capture_output=True,check=True,timeout=5)
    except subprocess.SubprocessError:
        state['status']='failed';STATE.write_text(json.dumps(state));raise ValueError('Backup could not start; retry from System status')
    return state
