import pathlib,sys,base64,json
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path.insert(0,str(root/'work/hardware/python'))
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--use-fake-ui-for-media-stream'])
    page=browser.new_page(permissions=['camera']);page.goto('http://127.0.0.1:17749')
    result=page.evaluate('''async()=>{const s=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:1280},height:{ideal:720},frameRate:{ideal:15}},audio:false});try{const v=document.createElement('video');v.muted=true;v.srcObject=s;await v.play();await new Promise(r=>setTimeout(r,2500));const c=document.createElement('canvas');c.width=v.videoWidth;c.height=v.videoHeight;c.getContext('2d').drawImage(v,0,0);return {image:c.toDataURL('image/png'),settings:s.getVideoTracks()[0].getSettings()}}finally{s.getTracks().forEach(t=>t.stop())}}''')
    (root/'work/qr-camera-only.png').write_bytes(base64.b64decode(result['image'].split(',')[1]))
    print(json.dumps({'width':result['settings']['width'],'height':result['settings']['height'],'camera_only_capture':True}));browser.close()
