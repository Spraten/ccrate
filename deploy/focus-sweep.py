import pathlib,sys,subprocess,base64,json,io
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path.insert(0,str(root/'work/hardware/python'))
from playwright.sync_api import sync_playwright
from PIL import Image
import zxingcpp
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--use-fake-ui-for-media-stream']);page=browser.new_page(permissions=['camera']);page.goto('http://127.0.0.1:17749')
    page.evaluate('''async()=>{window.s=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:1280},height:{ideal:720}},audio:false});window.v=document.createElement('video');v.muted=true;v.srcObject=s;await v.play()}''')
    results=[];chosen=180
    for focus in [120,150,180,210]:
        subprocess.run(['v4l2-ctl','-d','/dev/video0','--set-ctrl=focus_absolute='+str(focus)],check=True,capture_output=True)
        page.wait_for_timeout(1000)
        encoded=page.evaluate("()=>{const c=document.createElement('canvas');c.width=v.videoWidth;c.height=v.videoHeight;c.getContext('2d').drawImage(v,0,0);return c.toDataURL('image/png').split(',')[1]}")
        raw=base64.b64decode(encoded);decoded=zxingcpp.read_barcodes(Image.open(io.BytesIO(raw)))
        (root/f'work/qr-focus-{focus}.png').write_bytes(raw);results.append({'focus':focus,'decoded_codes':len(decoded)})
        if decoded:chosen=focus;break
    subprocess.run(['v4l2-ctl','-d','/dev/video0','--set-ctrl=focus_absolute='+str(chosen)],check=True,capture_output=True)
    page.evaluate('s.getTracks().forEach(t=>t.stop())');browser.close();print(json.dumps({'results':results,'selected_focus':chosen}))
