#!/usr/bin/env python3
"""Exercise member lifecycle mutations in a disposable native DB; never use live data."""
import pathlib,tempfile,subprocess,os,time,json,sys,hashlib,urllib.request,urllib.error,sqlite3,base64,io
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ops'))
from homebox import Homebox
from native_fields import update_payload
BASE='http://127.0.0.1:17777'
BINARY=pathlib.Path(os.environ.get('HOMEBOX_VERIFY_NATIVE_BINARY',str(ROOT/'work/homebox-backend-build/homebox')))
results=[]
def passed(name):results.append(name);print('PASS '+name,flush=True)
with tempfile.TemporaryDirectory(prefix='native-member-isolated-') as folder:
 root=pathlib.Path(folder);(root/'data').mkdir();(root/'work/baseline').mkdir(parents=True)
 env=dict(os.environ,HBOX_WEB_HOST='127.0.0.1',HBOX_WEB_PORT='17777',HBOX_STORAGE_PREFIX_PATH=str(root/'data'),HBOX_DATABASE_SQLITE_PATH=str(root/'data/homebox.db')+'?_pragma=busy_timeout=999&_pragma=journal_mode=WAL&_fk=1&_time_format=sqlite',HBOX_AUTH_API_KEY_PEPPER=str(uuid4()),HBOX_OPTIONS_ALLOW_REGISTRATION='true',HBOX_OPTIONS_GITHUB_RELEASE_CHECK='false',HBOX_OPTIONS_ALLOW_ANALYTICS='false')
 with (root/'native.log').open('w') as log:
  process=subprocess.Popen([str(BINARY)],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
  try:
   for _ in range(200):
    try:urllib.request.urlopen(BASE+'/api/v1/status',timeout=1).close();break
    except OSError:
     if process.poll() is not None:raise RuntimeError('Isolated native server exited')
     time.sleep(.1)
   def account(name):
    data={'name':name,'email':str(uuid4())+'@isolated.invalid','password':'isolated-test-password'}
    req=urllib.request.Request(BASE+'/api/v1/users/register',data=json.dumps(data).encode(),headers={'Content-Type':'application/json'});urllib.request.urlopen(req,timeout=30).close()
    (root/'work/baseline/test-account.json').write_text(json.dumps(data));return Homebox(root,base=BASE)
   client=account('Fixture admin');owner=client.call('/api/v1/users/self')['item'];gid=owner['defaultGroupId']
   def rejected(fn,codes=(400,403,404,409,422)):
    try:fn()
    except urllib.error.HTTPError as error:assert error.code in codes,error.code
    else:raise AssertionError('Unsafe member action was accepted')
   def expect_bad_request(fn):
    try:fn()
    except urllib.error.HTTPError as error:assert error.code==400,error.code
    else:raise AssertionError('Over-limit UTF-8 name was accepted')
   def create(name='Bob',email='',key=None,using=client):return using.call('/api/v1/groups/members','POST',{'name':name,'email':email,'requestKey':key or str(uuid4())})
   def profile(id,using=client):return using.call('/api/v1/groups/members/'+id+'/profile')
   def save(value,using=client):return using.call('/api/v1/groups/members/'+value['id']+'/profile','PUT',value)
   assert client.call('/api/v1/groups/members/administration')['canManage']
   key=str(uuid4());bob=create(key=key);assert bob['id']==key and bob['name']=='Bob' and bob['email']=='' and bob['mode']=='badge-only' and bob['editable']
   assert create(key=key)['id']==key
   rejected(lambda:create(name='Changed request',key=key))
   second=create();assert second['id']!=bob['id']
   rows=client.call('/api/v1/groups/members');assert len([r for r in rows if r['name']=='Bob'])==2 and all(not r['email'] for r in rows if r['name']=='Bob')
   with sqlite3.connect(root/'data/homebox.db') as db:
    records=db.execute("SELECT password,email,is_superuser FROM users WHERE name='Bob'").fetchall();assert len(records)==2 and all(r[0] is None and r[1].endswith('@caci-create.invalid') and not r[2] for r in records)
   for credential in ('password','pin'):
    rejected(lambda:client.call('/api/v1/groups/members','POST',{'requestKey':str(uuid4()),'name':'Unsupported credential fixture',credential:'123456'}),codes=(400,))
   passed('Name-only members are native, password-free, nonprivileged and idempotent; duplicate names stay distinct')
   boundary=create(name='界'*85)
   boundary=save(dict(boundary,name='😀'*63+'abc'))
   assert boundary['name']=='😀'*63+'abc'
   before_invalid=sorted((row['id'],row['name']) for row in client.call('/api/v1/groups/members'))
   for invalid_name in ('界'*86,'界'*90,'😀'*64):
    expect_bad_request(lambda invalid_name=invalid_name:create(name=invalid_name))
   before_profile=profile(boundary['id'])
   expect_bad_request(lambda:save(dict(before_profile,name='界'*90)))
   after_profile=profile(boundary['id'])
   assert after_profile['name']==before_profile['name'] and after_profile['updatedAt']==before_profile['updatedAt']
   after_invalid=sorted((row['id'],row['name']) for row in client.call('/api/v1/groups/members'))
   assert after_invalid==before_invalid
   passed('Native UTF-8 name boundaries return 400 without changing users')
   updated=dict(bob,name='Robert',email='optional@example.invalid',notes='Fixture details');updated=save(updated)
   assert updated['id']==bob['id'] and updated['email']=='optional@example.invalid' and updated['notes']=='Fixture details' and updated['updatedAt']!=bob['updatedAt']
   rejected(lambda:save(dict(bob,name='Stale edit')),codes=(409,))
   updated=save(dict(updated,email=''));assert not updated['email']
   for credential in ('password','pin'):
    rejected(lambda:save(dict(updated,**{credential:'123456'})),codes=(400,))
   passed('Rename, optional email and details preserve native identity; stale concurrent editing is rejected')
   from PIL import Image
   picture=io.BytesIO();Image.new('RGB',(64,64),'#3479bc').save(picture,'JPEG');avatar='data:image/jpeg;base64,'+base64.b64encode(picture.getvalue()).decode()
   updated=save(dict(updated,avatar=avatar));assert profile(bob['id'])['avatar']==avatar
   summary=next(r for r in client.call('/api/v1/groups/members') if r['id']==bob['id']);assert summary['avatar']==avatar
   rejected(lambda:save(dict(updated,avatar='data:image/svg+xml,<svg onload=alert(1)>')))
   updated=save(dict(updated,avatar=''));assert not profile(bob['id'])['avatar']
   passed('Valid local pictures appear in native members; unsafe formats are rejected and generated-avatar reset is supported')
   invitation=client.call('/api/v1/groups/invitations','POST',{'uses':1})
   ordinary={'name':'Ordinary member','email':'ordinary@isolated.invalid','password':'isolated-test-password','token':invitation['token']}
   client.call('/api/v1/users/register','POST',ordinary);(root/'work/baseline/test-account.json').write_text(json.dumps(ordinary));member=Homebox(root,base=BASE)
   assert not member.call('/api/v1/groups/members/administration')['canManage']
   rejected(lambda:create(using=member),codes=(403,));rejected(lambda:profile(bob['id'],member),codes=(403,));rejected(lambda:save(updated,member),codes=(403,))
   rejected(lambda:member.call('/api/v1/groups/members/'+owner['id'],'DELETE'),codes=(403,))
   rejected(lambda:client.call('/api/v1/groups/members/'+owner['id'],'DELETE'),codes=(400,))
   passed('Ordinary members cannot administer accounts or remove owners; native collection-owner access is protected')
   owner_profile=profile(owner['id']);assert owner_profile['protected'];rejected(lambda:save(dict(owner_profile,email='replacement@isolated.invalid')),codes=(400,))
   ordinary_id=member.call('/api/v1/users/self')['item']['id'];personal=profile(ordinary_id)
   save(dict(personal,avatar=avatar,notes='Preserve separate preferences'))
   member.call('/api/v1/users/self/settings','PUT',{'language':'en','caciProfile':{'avatar':'bad','managed':True,'notes':'tampered'}})
   after=profile(ordinary_id);assert after['mode']=='web-account' and after['avatar']==avatar and after['notes']=='Preserve separate preferences'
   assert member.call('/api/v1/users/self/settings')['item']['language']=='en'
   passed('Normal preference saves preserve admin profiles and cannot change account mode; owner sign-in email stays intact')
   outsider=account('Foreign owner');foreign=outsider.call('/api/v1/users/self')['item']
   rejected(lambda:profile(foreign['id']),codes=(404,));rejected(lambda:profile(bob['id'],outsider),codes=(404,));rejected(lambda:create(key=key,using=outsider),codes=(409,))
   join=client.call('/api/v1/groups/invitations','POST',{'uses':1});outsider.call('/api/v1/groups/invitations/'+join['token'],'POST')
   shared=profile(foreign['id']);assert not shared['editable'] and not shared['notes'];rejected(lambda:save(dict(shared,name='Unauthorized rename')),codes=(403,))
   passed('Foreign profiles stay private; a shared member is edited only by their primary collection')
   with sqlite3.connect(root/'data/homebox.db') as db:internal=db.execute("SELECT email FROM users WHERE name='Robert'").fetchone()[0]
   rejected(lambda:client.call('/api/v1/users/login','POST',{'username':internal,'password':''}),codes=(401,))
   rejected(lambda:client.call('/api/v1/users/login','POST',{'username':'optional@example.invalid','password':'1234'}),codes=(401,))
   for temporary_member in (second,boundary):
    client.call('/api/v1/groups/members/'+temporary_member['id'],'DELETE')
    assert not any(r['id']==temporary_member['id'] for r in client.call('/api/v1/groups/members'))
   with sqlite3.connect(root/'data/homebox.db') as db:
    assert db.execute('SELECT COUNT(*) FROM users WHERE id=?',(second['id'],)).fetchone()[0]==1
    assert db.execute('SELECT COUNT(*) FROM users WHERE id=?',(boundary['id'],)).fetchone()[0]==1
   passed('Badge-only records cannot sign in with empty/password-like PINs; collection removal preserves the native account identity')
   receipt={'checks':results,'count':len(results),'live_mutations':0,'physical_prints':0,'native_binary':str(BINARY),'binary_sha256':hashlib.sha256(BINARY.read_bytes()).hexdigest()}
   target=ROOT/'work/member-api-results.json';target.write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'count':len(results),'live_mutations':0,'physical_prints':0}))
  finally:
   with sqlite3.connect(root/'data/homebox.db') as db:
    with sqlite3.connect(ROOT/'work/member-api-fixture.db') as target:db.backup(target)
   (ROOT/'work/member-api-fixture.db').chmod(0o600)
   (ROOT/'work/member-api-native-fixture.log').write_text((root/'native.log').read_text())
   (ROOT/'work/member-api-native-fixture.log').chmod(0o600)
   process.terminate();process.wait(timeout=15)
