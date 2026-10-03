#!/usr/bin/env python3
"""Loopback read-only prototype using the isolated Homebox demonstration account."""
import json, os, pathlib, signal, threading, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
ROOT=pathlib.Path('/home/user/Desktop/inventory-system')
BASE='http://127.0.0.1:17745'
lock=threading.Lock()
def inventory():
    # Temporary demo account only. Tokens never reach the browser or logs.
    account=json.loads((ROOT/'work/baseline/test-account.json').read_text())
    req=urllib.request.Request(BASE+'/api/v1/users/login',data=json.dumps({'username':account['email'],'password':account['password']}).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=8) as response:token=json.load(response)['token'].removeprefix('Bearer ')
    items=[]
    page=1
    while True:
        req=urllib.request.Request(BASE+f'/api/v1/entities?page={page}&pageSize=100&isLocation=false',headers={'Authorization':'Bearer '+token})
        with urllib.request.urlopen(req,timeout=8) as response:data=json.load(response)
        items.extend(data['items'])
        if len(items)>=data['total'] or not data['items']:break
        page+=1
    return items
class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
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
