#!/usr/bin/env python3
"""Restore a complete backup to a private sandbox; never replace live files."""
import contextlib,hashlib,json,os,pathlib,sqlite3,subprocess,sys,tarfile,time,urllib.request
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path.insert(0,str(root/'ops'))
from homebox import Homebox
from uuid import uuid4
backup=sorted((root/'work/backups').glob('deployment-*.tar.gz'))[-1];target=root/'work/restore-check'/(backup.name.removesuffix('.tar.gz')+'-'+str(uuid4())[:8]);target.mkdir(mode=0o700,parents=True,exist_ok=False)
os.umask(0o077)
with tarfile.open(backup) as archive:archive.extractall(target,filter='data')
# SQLite regenerates shared-memory indexes; they are not portable recovery data.
for db in [target/'work/ops/ledger.db',target/'work/baseline/data/homebox.db']:
    pathlib.Path(str(db)+'-shm').unlink(missing_ok=True)
manifest=json.loads((target/'deployment-manifest.json').read_text())
for name,digest in manifest['sha256'].items():assert hashlib.sha256((target/name).read_bytes()).hexdigest()==digest,name
with contextlib.closing(sqlite3.connect(target/'work/ops/ledger.db')) as restored,contextlib.closing(sqlite3.connect(root/'work/ops/ledger.db')) as live:
    assert restored.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    for table in ['operations','custody','events','badges','native_jobs','native_job_events']:
        assert restored.execute('SELECT COUNT(*) FROM '+table).fetchone()==live.execute('SELECT COUNT(*) FROM '+table).fetchone(),table
run=target/'work/baseline';env=dict(os.environ,HBOX_WEB_HOST='127.0.0.1',HBOX_WEB_PORT='17748',HBOX_STORAGE_PREFIX_PATH='data',HBOX_DATABASE_SQLITE_PATH=str(run/'data/homebox.db')+'?_pragma=journal_mode=WAL&_fk=1&_time_format=sqlite',HBOX_AUTH_API_KEY_PEPPER=(run/'pepper').read_text(),HBOX_OPTIONS_GITHUB_RELEASE_CHECK='false',HBOX_OPTIONS_ALLOW_ANALYTICS='false')
proc=subprocess.Popen([str(target/'work/homebox-bin/homebox')],cwd=run,env=env,stdout=(target/'restore.log').open('ab'),stderr=subprocess.STDOUT)
try:
    for attempt in range(80):
        try:urllib.request.urlopen('http://127.0.0.1:17748/api/v1/status',timeout=1).close();break
        except OSError:time.sleep(.25)
    restored=Homebox(target,'http://127.0.0.1:17748',timeout=30);live=Homebox(root,timeout=30)
    assert {e['id'] for e in restored.entities()}=={e['id'] for e in live.entities()}
    assert {e['id'] for e in restored.entities(True)}=={e['id'] for e in live.entities(True)}
    assert restored.call('/api/v1/groups/members')==live.call('/api/v1/groups/members')
    asset=restored.entity('efb41b6f-0386-452b-af21-75da992e9677')
    attachments=asset.get('attachments',[]);verified=0
    for item in attachments:
        path='/api/v1/entities/'+asset['id']+'/attachments/'+item['id']
        def download(client):return urllib.request.urlopen(urllib.request.Request(client.base+path,headers={'Authorization':'Bearer '+client.token}),timeout=10).read()
        assert download(restored)==download(live);verified+=1
    result={'complete_backup_restored':True,'runtime_hashes_verified':True,'operational_custody_badges_events_jobs_preserved':True,'native_inventory_locations_members_preserved':True,'attachment_bytes_verified':verified,'isolated_restore_port':17748,'live_deployment_replaced':False,'external_media_copy':'Still required for SD-card failure protection'}
    (root/'docs/deployment-restore-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
finally:proc.terminate();proc.wait(timeout=15)
