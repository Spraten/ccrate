#!/usr/bin/env python3
"""Loopback read-only prototype using the isolated Homebox demonstration account."""
import json, pathlib, threading, urllib.request, urllib.error
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
