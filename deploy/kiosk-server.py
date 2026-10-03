#!/usr/bin/env python3
"""Loopback read-only prototype using the isolated Homebox demonstration account."""
import io, json, os, pathlib, signal, sys, threading, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
ROOT=pathlib.Path('/home/user/Desktop/inventory-system')
sys.path.insert(0,str(ROOT/'kiosk'))
sys.path.insert(0,str(ROOT/'work/hardware/python'))
from scan_codes import normalize
from PIL import Image
import zxingcpp
BASE='http://127.0.0.1:17745'
lock=threading.Lock()
def inventory(locations=False):
    # Temporary demo account only. Tokens never reach the browser or logs.
    account=json.loads((ROOT/'work/baseline/test-account.json').read_text())
    req=urllib.request.Request(BASE+'/api/v1/users/login',data=json.dumps({'username':account['email'],'password':account['password']}).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=8) as response:token=json.load(response)['token'].removeprefix('Bearer ')
    items=[]
    page=1
    while True:
        req=urllib.request.Request(BASE+f'/api/v1/entities?page={page}&pageSize=100&isLocation={str(locations).lower()}',headers={'Authorization':'Bearer '+token})
        with urllib.request.urlopen(req,timeout=8) as response:data=json.load(response)
        items.extend(data['items'])
        if len(items)>=data['total'] or not data['items']:break
        page+=1
    return items
class Handler(BaseHTTPRequestHandler):
    def reply_json(self,code,data):
        body=json.dumps(data).encode()
        self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_POST(self):
        if self.path in ('/decode','/scan'):
            if self.headers.get('Origin') != 'http://127.0.0.1:17749':self.send_error(403);return
            try:size=int(self.headers.get('Content-Length','0'))
            except ValueError:self.send_error(400);return
            if not 0<size<=1000000:self.send_error(413);return
            raw=self.rfile.read(size)
            try:
                if self.path=='/decode':
                    with Image.open(io.BytesIO(raw)) as frame:
                        if frame.width>1280 or frame.height>960:self.send_error(413);return
                        codes=[c.text for c in zxingcpp.read_barcodes(frame)]
                    self.reply_json(200,{'codes':codes});return
                data=json.loads(raw);code=normalize(data.get('code'))
                if code['kind'] in ('asset','entity'):
                    with lock:items=inventory()+inventory(True)
                    match=next((e for e in items if ('asset_id' in code and e.get('assetId')==code['asset_id']) or ('entity_id' in code and e['id']==code['entity_id'])),None)
                    if match:code['entity']=match
                    else:code={'kind':'unknown','reason':'This code is not in this Homebox inventory'}
                self.reply_json(200,code)
            except (ValueError,TypeError,AttributeError,OSError,KeyError):self.reply_json(400,{'kind':'invalid','reason':'Could not read the scan'})
            return

        if self.path != '/exit' or self.headers.get('Origin') != 'http://127.0.0.1:17749':
            self.send_error(403);return
        profile=str(ROOT/'work/kiosk-browser')
        targets=[]
        for entry in pathlib.Path('/proc').iterdir():
            if not entry.name.isdigit():continue
            try:
                args=(entry/'cmdline').read_bytes().split(b'\0')
                if ('--user-data-dir='+profile).encode() in args and not any(a.startswith(b'--type=') for a in args) and b'chromium' in args[0]:
                    targets.append(int(entry.name))
            except (OSError,IndexError):continue
        if not targets:
            self.send_error(409);return
        self.send_response(200);self.send_header('Content-Length','0');self.end_headers()
        for pid in targets:
            try:os.kill(pid,signal.SIGTERM)
            except ProcessLookupError:pass
    def do_GET(self):
        if self.path=='/':
            body=(ROOT/'kiosk/index.html').read_bytes();mime='text/html; charset=utf-8';code=200
        elif self.path=='/api/inventory':
            try:
                with lock:body=json.dumps(inventory()).encode()
                code=200
            except (OSError,ValueError,KeyError):body=b'{"error":"Homebox unavailable"}';code=503
            mime='application/json'
        else:body=b'Not found';mime='text/plain';code=404
        self.send_response(code);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
    def log_message(self,*args):pass
print('Kiosk prototype: http://127.0.0.1:17749',flush=True)
ThreadingHTTPServer(('127.0.0.1',17749),Handler).serve_forever()
