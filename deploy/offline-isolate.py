"""Run under sudo unshare --net --mount; isolate restored data, not the live Pi."""
import os,pathlib,pwd,subprocess,sys,tempfile
root=pathlib.Path('/home/user/Desktop/inventory-system');clone=pathlib.Path(sys.argv[1]).resolve()
if not clone.is_relative_to(root/'work/restore-check') or not (clone/'deployment-manifest.json').is_file():raise ValueError('Choose a verified private restore sandbox')
script=(root/'deploy/offline-proof.py').read_bytes();account=pwd.getpwnam('user')
with tempfile.NamedTemporaryFile(prefix='homebox-offline-',suffix='.py',delete=False) as stream:stream.write(script);path=pathlib.Path(stream.name)
path.chmod(0o600);os.chown(path,account.pw_uid,account.pw_gid)
try:
    subprocess.run(['mount','--make-rprivate','/'],check=True)
    subprocess.run(['mount','--bind',str(clone),str(root)],check=True)
    subprocess.run(['ip','link','set','lo','up'],check=True)
    subprocess.run(['setpriv','--reuid=user','--regid=user','--init-groups','/usr/bin/python3',str(path)],check=True)
finally:path.unlink(missing_ok=True)
