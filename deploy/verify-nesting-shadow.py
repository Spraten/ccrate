#!/usr/bin/env python3
"""Prove the staged native build preserves a private SQLite clone of real data."""
import contextlib,hashlib,json,os,pathlib,shutil,sqlite3,subprocess,sys,tempfile,time,urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ops'))
from homebox import Homebox
os.umask(0o077)
def fingerprint(client):
 records={'equipment':[client.entity(e['id']) for e in client.entities()], 'locations':[client.entity(e['id']) for e in client.entities(True)],'members':client.call('/api/v1/groups/members')}
 return {name:{'count':len(rows),'sha256':hashlib.sha256(json.dumps(sorted(rows,key=lambda e:e['id']),sort_keys=True,separators=(',',':')).encode()).hexdigest()} for name,rows in records.items()}
before=fingerprint(Homebox(ROOT,base='http://127.0.0.1:17747',timeout=60))
with tempfile.TemporaryDirectory(prefix='private-native-shadow-',dir=ROOT/'work') as temporary:
 root=pathlib.Path(temporary);(root/'data').mkdir();(root/'work/baseline').mkdir(parents=True)
 shutil.copy2(ROOT/'work/baseline/test-account.json',root/'work/baseline/test-account.json')
 source=ROOT/'work/baseline/data'
 for child in source.iterdir():
  if child.name.startswith('homebox.db'):continue
  if child.is_dir():shutil.copytree(child,root/'data'/child.name)
  else:shutil.copy2(child,root/'data'/child.name)
 with contextlib.closing(sqlite3.connect('file:'+str(source/'homebox.db')+'?mode=ro',uri=True)) as connection, contextlib.closing(sqlite3.connect(root/'data/homebox.db')) as destination:connection.backup(destination)
 env=dict(os.environ,HBOX_WEB_HOST='127.0.0.1',HBOX_WEB_PORT='17777',HBOX_STORAGE_PREFIX_PATH=str(root/'data'),HBOX_DATABASE_SQLITE_PATH=str(root/'data/homebox.db')+'?_pragma=busy_timeout=999&_pragma=journal_mode=WAL&_fk=1&_time_format=sqlite',HBOX_AUTH_API_KEY_PEPPER=(ROOT/'work/baseline/pepper').read_text().strip(),HBOX_OPTIONS_ALLOW_REGISTRATION='false',HBOX_OPTIONS_GITHUB_RELEASE_CHECK='false',HBOX_OPTIONS_ALLOW_ANALYTICS='false')
 with (root/'native.log').open('w') as log:
  process=subprocess.Popen([str(ROOT/'work/homebox-backend-build/homebox')],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
  try:
   for _ in range(200):
    try:urllib.request.urlopen('http://127.0.0.1:17777/api/v1/status',timeout=1).close();break
    except OSError:
     if process.poll() is not None:raise RuntimeError('Private clone native startup failed')
     time.sleep(.1)
   after=fingerprint(Homebox(root,base='http://127.0.0.1:17777',timeout=60))
   assert before==after,'Staged native responses differ from real inventory/membership; inspect privately before deployment'
   with contextlib.closing(sqlite3.connect(root/'data/homebox.db')) as connection:assert connection.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
   assert fingerprint(Homebox(ROOT,base='http://127.0.0.1:17747',timeout=60))==before,'Live data changed during shadow check; refresh baseline before deployment'
   result={'inventory_preserved':True,**{name:value['count'] for name,value in after.items()},'live_mutations':0,'clone_integrity':'ok','binary_sha256':hashlib.sha256((ROOT/'work/homebox-backend-build/homebox').read_bytes()).hexdigest()}
   (ROOT/'work/nesting-shadow-results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
  finally:process.terminate();process.wait(timeout=15)
