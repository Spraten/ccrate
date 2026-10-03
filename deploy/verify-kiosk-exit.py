import pathlib,sys,time,urllib.request,json
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path.insert(0,str(root/'ops'))
from kiosk_processes import kiosk_pids
profile=root/'work/kiosk-browser';before=kiosk_pids(profile);assert before,'Open the kiosk before running this physical close check'
request=urllib.request.Request('http://127.0.0.1:17749/exit',data=b'',headers={'Origin':'http://127.0.0.1:17749'})
with urllib.request.urlopen(request,timeout=5) as response:assert response.status==200
for _ in range(30):
    if not kiosk_pids(profile):break
    time.sleep(.2)
assert not kiosk_pids(profile),'Kiosk browser did not close'
with urllib.request.urlopen('http://127.0.0.1:17749/',timeout=5) as response:assert response.status==200
print(json.dumps({'exit_response':200,'kiosk_browser_closed':True,'companion_still_running':True}))
