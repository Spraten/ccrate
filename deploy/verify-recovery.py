#!/usr/bin/env python3
"""Verify native membership, attachment bytes and API-key continuity on restore."""
import hashlib,json,os,pathlib,shutil,time,urllib.request
ROOT=pathlib.Path('/home/user/Desktop/inventory-system')
# Reuse the baseline's exact launch configuration without executing its seeding.
helpers=(ROOT/'deploy/complete-baseline.py').read_text().split('token = login(BASE)')[0]
exec(compile(helpers,'baseline_helpers','exec'))
token=login(BASE)
members=request(BASE,'GET','/api/v1/groups/members',token=token)
assert isinstance(members,list) and all('id' in m and 'name' in m for m in members)
asset=next(e for e in entities(BASE,token,False) if e['name']=='Demo Drone 001')
path='/api/v1/entities/'+asset['id']
detail=request(BASE,'GET',path,token=token)
content=b'Synthetic Homebox attachment recovery proof. No real equipment data.\n'
attachment=next((a for a in detail.get('attachments',[]) if a.get('title')=='recovery-proof.txt'),None)
if not attachment:
    boundary='homebox-recovery-proof'
    parts=[]
    for name,value in [('name','recovery-proof.txt'),('type','attachment'),('primary','false')]:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="recovery-proof.txt"\r\nContent-Type: text/plain\r\n\r\n'.encode()+content+b'\r\n')
    body=b''.join(parts)+f'--{boundary}--\r\n'.encode()
    req=urllib.request.Request(BASE+path+'/attachments',data=body,headers={'Authorization':'Bearer '+token.removeprefix('Bearer '),'Content-Type':'multipart/form-data; boundary='+boundary})
    with urllib.request.urlopen(req,timeout=15) as response:detail=json.load(response)
    attachment=next(a for a in detail['attachments'] if a.get('title')=='recovery-proof.txt')
def download(base,auth):
    req=urllib.request.Request(base+path+'/attachments/'+attachment['id'],headers={'Authorization':'Bearer '+auth.removeprefix('Bearer ')})
    with urllib.request.urlopen(req,timeout=15) as response:return response.read()
assert download(BASE,token)==content
key=request(BASE,'POST','/api/v1/users/self/api-keys',{'name':'temporary-restore-verification'},token)
restored=None;backup=None
try:
    stamp=time.strftime('%Y%m%d-%H%M%S')+'-attachments'
    backup=ROOT/'work/backups'/stamp;backup.mkdir(mode=0o700)
    stopped=False
    try:
        stop_baseline();stopped=True
        shutil.copytree(RUN/'data',backup/'data');shutil.copy2(RUN/'pepper',backup/'pepper');os.chmod(backup/'pepper',0o600)
    finally:
        if stopped:
            proc=launch(RUN,17745);(RUN/'homebox.pid').write_text(str(proc.pid))
    restore=ROOT/'work/restore-check'/stamp;restore.mkdir(mode=0o700)
    shutil.copytree(backup/'data',restore/'data')
    restored=launch(restore,17748);base='http://127.0.0.1:17748'
    assert download(base,key['token'])==content
    assert request(base,'GET',path,token=key['token'])['id']==asset['id']
    request(base,'DELETE','/api/v1/users/self/api-keys/'+key['id'],token=login(base))
finally:
    if restored:restored.terminate();restored.wait(timeout=15)
    request(BASE,'DELETE','/api/v1/users/self/api-keys/'+key['id'],token=login(BASE))
report={'native_members_lookup':True,'member_count':len(members),'attachment_upload_download':True,'restored_attachment_sha256':hashlib.sha256(content).hexdigest(),'api_key_works_after_restore':True,'temporary_key_revoked':True,'baseline_restarted':True,'backup_folder':str(backup)}
(ROOT/'docs/recovery-verification-results.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))

