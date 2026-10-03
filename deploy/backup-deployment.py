#!/usr/bin/env python3
"""Cold, private, complete offline deployment backup with restart in finally."""
import fcntl,hashlib,json,os,pathlib,sqlite3,subprocess,tarfile,time
root=pathlib.Path('/home/user/Desktop/inventory-system');folder=root/'work/backups';folder.mkdir(mode=0o700,exist_ok=True)
os.umask(0o077)
with (folder/'deployment.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    stamp=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime());target=folder/('deployment-'+stamp+'.tar.gz');partial=target.with_suffix('.partial')
    members=['.git','ops','kiosk','deploy','docs','upstream/homebox','work/baseline/data','work/baseline/pepper','work/baseline/test-account.json','work/ops','work/homebox-bin/homebox','work/hardware/python','work/supvan-cups/target/release/examples/kiosk-label']
    manifest={'format':1,'created_at':stamp,'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'homebox_pin':subprocess.check_output(['git','-C','upstream/homebox','rev-parse','HEAD'],cwd=root,text=True).strip(),'members':members,'sha256':{}}
    stopped=False
    try:
        subprocess.run(['systemctl','--user','stop','homebox-companion.service','homebox-native.service'],check=True);stopped=True
        for db in ['work/ops/ledger.db','work/baseline/data/homebox.db']:
            with sqlite3.connect(root/db) as connection:
                connection.execute('PRAGMA wal_checkpoint(TRUNCATE)');assert connection.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        for name in ['work/ops/ledger.db','work/baseline/data/homebox.db','work/homebox-bin/homebox','work/supvan-cups/target/release/examples/kiosk-label']:
            manifest['sha256'][name]=hashlib.sha256((root/name).read_bytes()).hexdigest()
        with tarfile.open(partial,'w:gz',compresslevel=1) as archive:
            for name in members:archive.add(root/name,arcname=name)
            body=json.dumps(manifest,indent=2).encode();info=tarfile.TarInfo('deployment-manifest.json');info.size=len(body);info.mode=0o600
            import io
            archive.addfile(info,io.BytesIO(body))
        partial.rename(target);target.chmod(0o600)
        (target.with_suffix('.sha256')).write_text(hashlib.sha256(target.read_bytes()).hexdigest()+'  '+target.name+'\n')
        result={'status':'completed','backup':target.name,'bytes':target.stat().st_size,'database_integrity':'ok'}
        state_path=root/'work/backup-status.json'
        try:state=json.loads(state_path.read_text())
        except (FileNotFoundError,ValueError):state={}
        state.update(result);state_path.write_text(json.dumps(state));state_path.chmod(0o600)
        print(json.dumps(result))
    except Exception:
        (root/'work/backup-status.json').write_text(json.dumps({'status':'failed','reason':'Backup failed; inspect the local service log'}))
        raise
    finally:
        if stopped:subprocess.run(['systemctl','--user','start','homebox-native.service','homebox-companion.service'],check=True)
