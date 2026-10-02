#!/usr/bin/env python3
import json, pathlib, subprocess, sys, time
root=pathlib.Path('/home/user/Desktop/inventory-system')
sys.path.insert(0,str(root/'work/hardware/python'))
from PIL import Image
import qrcode,zxingcpp
work=root/'work/hardware'
work.mkdir(exist_ok=True)
result={}
qr=qrcode.make('HARDWARE-PROOF:QR:001').get_image()
qr.save(work/'test-qr.png')
result['synthetic_qr_decode']=any(c.text=='HARDWARE-PROOF:QR:001' for c in zxingcpp.read_barcodes(qr))
def run(name,args):
    start=time.monotonic()
    try:
        proc=subprocess.run(args,capture_output=True,text=True,timeout=20)
        result[name]={'exit_code':proc.returncode,'seconds':round(time.monotonic()-start,2),'output':(proc.stdout+proc.stderr)[-4000:]}
    except subprocess.TimeoutExpired:
        result[name]={'timeout':True,'seconds':20}
run('capture',['ffmpeg','-y','-hide_banner','-loglevel','warning','-f','v4l2','-input_format','mjpeg','-video_size','640x480','-framerate','10','-i','/dev/video0','-frames:v','1','-update','1',str(work/'camera.jpg')])
if (work/'camera.jpg').exists():
    try:
        with Image.open(work/'camera.jpg') as frame:
            frame.load();result['frame']={'dimensions':list(frame.size),'bytes':(work/'camera.jpg').stat().st_size}
    except Exception as error:result['frame_error']=str(error)
run('stream',['ffmpeg','-hide_banner','-benchmark','-f','v4l2','-input_format','mjpeg','-video_size','640x480','-framerate','10','-i','/dev/video0','-t','5','-f','null','-'])
(root/'docs/camera-proof-results.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
