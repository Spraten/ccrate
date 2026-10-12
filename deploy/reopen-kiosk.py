import urllib.request,time,subprocess,os,pathlib
root=pathlib.Path('/home/user/Desktop/inventory-system')
req=urllib.request.Request('http://127.0.0.1:17749/exit',data=b'{}',headers={'Origin':'http://127.0.0.1:17749','Content-Type':'application/json'})
with urllib.request.urlopen(req) as response:assert response.status==200
time.sleep(1)
env=dict(os.environ,DISPLAY=':0')
with open(root/'work/kiosk-launch.log','ab') as log:
    subprocess.Popen(['sh',str(root/'deploy/open-kiosk.sh')],env=env,stdout=log,stderr=log,start_new_session=True)
print('Kiosk reopened with updated scan UI.')
