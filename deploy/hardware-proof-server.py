#!/usr/bin/env python3
"""Local diagnostic UI. No inventory credentials or production workflows."""
import io, json, pathlib, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
root=pathlib.Path('/home/user/Desktop/inventory-system')
sys.path.insert(0,str(root/'work/hardware/python'))
from PIL import Image
import qrcode, zxingcpp
image=qrcode.make('HARDWARE-PROOF:QR:001').get_image()
image.save(root/'work/hardware/test-qr.png')
decoded=zxingcpp.read_barcodes(image)
assert any(code.text=='HARDWARE-PROOF:QR:001' for code in decoded)
state={'synthetic_qr_decode':'passed','touch_targets':[], 'touch_event_types':[], 'camera':None, 'scans':[]}
if (root/'docs/hardware-proof-results.json').exists():
    state.update(json.loads((root/'docs/hardware-proof-results.json').read_text()))
html=b'''<!doctype html><html><meta name="viewport" content="width=device-width,initial-scale=1"><style>
*{box-sizing:border-box}body{margin:12px;background:#17212b;color:#fff;font:18px sans-serif}h1{font-size:23px;margin:0 0 8px}.row{display:flex;gap:12px}.panel{flex:1}button{font:18px sans-serif;padding:14px;border:0;border-radius:8px;margin:3px;background:#dce8f2;color:#17212b}.zones{display:grid;grid-template-columns:1fr 1fr}.zones button{height:60px}video{width:320px;height:240px;background:#000}#msg{font-size:17px;overflow-wrap:anywhere}.ok{background:#80d9aa}img{width:128px;height:128px}p{margin:7px 0}</style>
<h1>Hardware proof <small>temporary test</small></h1><div class="row"><div class="panel"><p>Tap all five targets.</p><div class="zones">'''+b''.join(f'<button data-zone="{n}">Touch {n}</button>'.encode() for n in range(1,6))+b'''</div><p id="touch">0 of 5</p><img src="/qr.png"><small>Test QR only</small></div><div class="panel"><button id="start">Start camera</button><video autoplay playsinline muted></video><p id="msg">Camera not started</p></div></div><script>
const seen=new Set(),msg=document.querySelector('#msg'),video=document.querySelector('video');
async function event(data){await fetch('/event',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})}
document.querySelectorAll('[data-zone]').forEach(b=>b.addEventListener('pointerdown',e=>{seen.add(b.dataset.zone);b.classList.add('ok');document.querySelector('#touch').textContent=seen.size+' of 5 - '+e.pointerType;event({type:'touch',zone:b.dataset.zone,pointerType:e.pointerType})}));
document.querySelector('#start').onclick=async()=>{try{const status=await (await fetch('/camera-status')).json();if(!status.present){msg.textContent='Webcam disconnected. Reconnect USB, then tap Start camera.';return}if(!window.isSecureContext){msg.textContent='Open http://127.0.0.1:17746 on this Pi for camera access.';return}const stream=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:640},height:{ideal:480},frameRate:{ideal:10,max:15}},audio:false});video.srcObject=stream;const s=stream.getVideoTracks()[0].getSettings();msg.textContent='Camera: '+s.width+'x'+s.height;event({type:'camera',settings:s});const canvas=document.createElement('canvas');canvas.width=640;canvas.height=480;setInterval(async()=>{if(video.readyState<2)return;canvas.getContext('2d').drawImage(video,0,0,640,480);canvas.toBlob(async blob=>{const response=await fetch('/decode',{method:'POST',body:blob});const data=await response.json();if(data.codes.length)msg.textContent='Scanned: '+data.codes.join(', ')},'image/jpeg',0.7)},500)}catch(e){msg.textContent=e.name+': '+e.message;event({type:'camera_error',name:e.name,message:e.message})}};
</script></html>'''
def save():
    (root/'docs/hardware-proof-results.json').write_text(json.dumps(state,indent=2))
save()
class Handler(BaseHTTPRequestHandler):
    def respond(self,status,content,mime):
        self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(content)));self.end_headers();self.wfile.write(content)
    def do_GET(self):
        if self.path=='/':self.respond(200,html,'text/html')
        elif self.path=='/qr.png':self.respond(200,(root/'work/hardware/test-qr.png').read_bytes(),'image/png')
        elif self.path=='/camera-status':self.respond(200,json.dumps({'present':any(p.exists() for p in pathlib.Path('/dev/v4l/by-id').glob('*USB_2.0_Camera*video-index0'))}).encode(),'application/json')
        elif self.path=='/results':self.respond(200,json.dumps(state).encode(),'application/json')
        else:self.respond(404,b'Not found','text/plain')
    def do_POST(self):
        size=int(self.headers.get('Content-Length','0'))
        if size>1000000:self.respond(413,b'','text/plain');return
        body=self.rfile.read(size)
        if self.path=='/event':
            data=json.loads(body)
            if data['type']=='touch':
                if data['zone'] not in state['touch_targets']:state['touch_targets'].append(data['zone'])
                if data['pointerType'] not in state['touch_event_types']:state['touch_event_types'].append(data['pointerType'])
            elif data['type']=='camera':state['camera']=data['settings']
            elif data['type']=='camera_error':state['camera_error']=data
            save();self.respond(200,b'{}','application/json')
        elif self.path=='/decode':
            start=time.monotonic()
            try:
                codes=[result.text for result in zxingcpp.read_barcodes(Image.open(io.BytesIO(body)))]
            except Exception:codes=[]
            for code in codes:
                if code not in state['scans']:state['scans'].append(code);save()
            self.respond(200,json.dumps({'codes':codes,'decode_ms':round((time.monotonic()-start)*1000,1)}).encode(),'application/json')
        else:self.respond(404,b'','text/plain')
    def log_message(self,*args):pass
print('Hardware proof: http://127.0.0.1:17746; synthetic QR decoder passed',flush=True)
ThreadingHTTPServer(('127.0.0.1',17746),Handler).serve_forever()



