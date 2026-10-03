#!/usr/bin/env python3
import json, pathlib, subprocess, sys, time
root=pathlib.Path('/home/user/Desktop/inventory-system')
sys.path.insert(0,str(root/'work/hardware/python'))
from PIL import Image
import qrcode,zxingcpp
work=root/'work/hardware'
work.mkdir(exist_ok=True)
devices=sorted(pathlib.Path('/dev/v4l/by-id').glob('*USB_2.0_Camera*video-index0'))
device=str(devices[0]) if devices else '/dev/video0'
result={'camera_present':pathlib.Path(device).exists(),'device':device}
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
run('capture',['ffmpeg','-y','-hide_banner','-loglevel','warning','-f','v4l2','-input_format','mjpeg','-video_size','640x480','-framerate','10','-i',device,'-frames:v','1','-update','1',str(work/'camera.jpg')])
if result['capture'].get('exit_code') == 0 and (work/'camera.jpg').exists():
    try:
        with Image.open(work/'camera.jpg') as frame:
            frame.load();result['frame']={'dimensions':list(frame.size),'bytes':(work/'camera.jpg').stat().st_size}
    except Exception as error:result['frame_error']=str(error)
run('stream',['ffmpeg','-hide_banner','-benchmark','-f','v4l2','-input_format','mjpeg','-video_size','640x480','-framerate','10','-i',device,'-t','5','-f','null','-'])
(root/'docs/camera-proof-results.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))


