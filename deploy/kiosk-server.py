#!/usr/bin/env python3
"""Loopback read-only prototype using the isolated Homebox demonstration account."""
import base64, io, json, os, pathlib, signal, sys, threading, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
ROOT=pathlib.Path('/home/user/Desktop/inventory-system')
sys.path.insert(0,str(ROOT/'kiosk'))
sys.path.insert(0,str(ROOT/'work/hardware/python'))
sys.path.insert(0,str(ROOT/'ops'))
from ledger import Ledger
from badges import Badges
from sessions import Session
from scan_codes import normalize
from PIL import Image
import zxingcpp, qrcode
from urllib.parse import urlsplit, parse_qs
from homebox import Homebox
from checkout import confirm_checkout
from returns import confirm_return, recover, RETURN_STATES
from maps import list_map,save_room,save_object,remove_object
from ledger import Conflict
from conditions import STATES, condition, checkout_blocker, set_condition
BASE='http://127.0.0.1:17745'
lock=threading.Lock()
ops_path=ROOT/'work/ops'
ops_path.mkdir(exist_ok=True,mode=0o700)
os.chmod(ops_path,0o700)
ledger=Ledger(ops_path/'ledger.db')
badges=Badges(ledger)
session=Session(timeout=120)
# Explicitly approved temporary setup mode; loopback only.
OPEN_ADMIN=True
def inventory(locations=False):
    # Temporary demo account only. Tokens never reach the browser or logs.
    account=json.loads((ROOT/'work/baseline/test-account.json').read_text())
    req=urllib.request.Request(BASE+'/api/v1/users/login',data=json.dumps({'username':account['email'],'password':account['password']}).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=8) as response:token=json.load(response)['token'].removeprefix('Bearer ')
    items=[]
    page=1
    while True:
        req=urllib.request.Request(BASE+f'/api/v1/entities?page={page}&pageSize=100&includeArchived=true&isLocation={str(locations).lower()}',headers={'Authorization':'Bearer '+token})
        with urllib.request.urlopen(req,timeout=8) as response:data=json.load(response)
        items.extend(data['items'])
        if len(items)>=data['total'] or not data['items']:break
        page+=1
    return items
def native_context():
    account=json.loads((ROOT/'work/baseline/test-account.json').read_text())
    req=urllib.request.Request(BASE+'/api/v1/users/login',data=json.dumps({'username':account['email'],'password':account['password']}).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=8) as response:token=json.load(response)['token'].removeprefix('Bearer ')
    def get(path):
        req=urllib.request.Request(BASE+path,headers={'Authorization':'Bearer '+token})
        with urllib.request.urlopen(req,timeout=8) as response:return json.load(response)
    actor=get('/api/v1/users/self')['item']
    members=get('/api/v1/groups/members')
    return actor['defaultGroupId'],members

class Handler(BaseHTTPRequestHandler):
    def reply_json(self,code,data):
        body=json.dumps(data).encode()
        self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_POST(self):
        if self.path in ('/decode','/scan','/badge/issue','/badge/revoke','/session/end','/session/activity','/condition','/checkout/confirm','/return/confirm','/recovery/resolve','/map/room','/map/object','/map/remove'):
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
                data=json.loads(raw)
                if self.path in ('/map/room','/map/object','/map/remove'):
                    if not OPEN_ADMIN:self.send_error(403);return
                    with lock:
                        client=Homebox(ROOT)
                        if self.path=='/map/room':result=save_room(client,data.get('entity_id'),data)
                        elif self.path=='/map/object':result=save_object(client,data.get('entity_id'),data)
                        else:result=remove_object(client,data.get('entity_id'))
                    self.reply_json(200,result);return
                if self.path=='/recovery/resolve':
                    if not OPEN_ADMIN:self.send_error(403);return
                    with lock:
                        client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item']
                        result=recover(client,ledger,native['defaultGroupId'],data.get('id'),data.get('outcome'))
                    self.reply_json(200,result);return
                if self.path=='/return/confirm':
                    actor=session.current()
                    if not actor:self.reply_json(401,{'error':'Scan your badge first'});return
                    with lock:
                        client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item']
                        result=confirm_return(client,ledger,native['defaultGroupId'],actor,data.get('targets'),data.get('request_key'),lambda:session.current()==actor)
                        session.end()
                    self.reply_json(200,result);return
                if self.path=='/checkout/confirm':
                    actor=session.current()
                    if not actor:self.reply_json(401,{'error':'Scan your badge first'});return
                    with lock:
                        client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item']
                        result=confirm_checkout(client,ledger,native['defaultGroupId'],actor,data.get('assets',[]),data.get('request_key'),lambda:session.current()==actor)
                        session.end()
                    self.reply_json(200,result);return
                if self.path=='/condition':
                    if not OPEN_ADMIN:self.send_error(403);return
                    with lock:entity=set_condition(Homebox(ROOT),data.get('entity_id'),data.get('state'))
                    self.reply_json(200,{'entity':entity,'condition':condition(entity),'blocker':checkout_blocker(entity)});return
                if self.path=='/session/activity':
                    self.reply_json(200,{'active':session.current(activity=True) is not None});return
                if self.path=='/scan':session.current(activity=True)
                if self.path=='/session/end':
                    session.end()
                    self.reply_json(200,{'ended':True});return
                if self.path in ('/badge/issue','/badge/revoke'):
                    if not OPEN_ADMIN:self.send_error(403);return
                    group,members=native_context()
                    if self.path=='/badge/issue':
                        badge=badges.issue(group,data.get('user_id'),[m['id'] for m in members])
                        image=io.BytesIO();qrcode.make(badge['code']).save(image,format='PNG')
                        badge['qr']='data:image/png;base64,'+base64.b64encode(image.getvalue()).decode()
                        self.reply_json(200,badge)
                    else:
                        result=badges.revoke(group,data.get('id'))
                        session.end()
                        self.reply_json(200,{'revoked':result})
                    return
                if isinstance(data.get('code'),str) and data['code'].startswith(Badges.PREFIX):
                    group,members=native_context();user=badges.resolve(group,data['code'],[m['id'] for m in members])
                    if user:
                        name=next(m['name'] for m in members if m['id']==user)
                        session.start(user)
                        self.reply_json(200,{'kind':'user','user':{'id':user,'name':name}})
                    else:self.reply_json(200,{'kind':'invalid','reason':'Badge unknown, revoked, or no longer a group member'})
                    return
                code=normalize(data.get('code'))
                if code['kind'] in ('asset','entity'):
                    with lock:items=inventory()+inventory(True)
                    match=next((e for e in items if ('asset_id' in code and e.get('assetId')==code['asset_id']) or ('entity_id' in code and e['id']==code['entity_id'])),None)
                    if match:code['entity']=match
                    else:code={'kind':'unknown','reason':'This code is not in this Homebox inventory'}
                self.reply_json(200,code)
            except Conflict as error:self.reply_json(409,{'error':str(error),'reason':str(error)})
            except (ValueError,TypeError,AttributeError,KeyError) as error:self.reply_json(400,{'kind':'invalid','error':str(error),'reason':str(error)})
            except OSError:self.reply_json(503,{'error':'Homebox unavailable; no confirmation received','reason':'Homebox unavailable; try again'})
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
        if urlsplit(self.path).path=='/api/map':
            try:
                entity_id=parse_qs(urlsplit(self.path).query).get('entity',[None])[0]
                self.reply_json(200,list_map(Homebox(ROOT),entity_id))
            except (ValueError,TypeError,KeyError):self.reply_json(400,{'error':'Map or location needs review'})
            except OSError:self.reply_json(503,{'error':'Homebox map unavailable'})
            return
        if self.path=='/api/session' and session.current() is None:
            self.reply_json(200,{'user':None});return
        if urlsplit(self.path).path=='/api/history':
            try:
                group,members=native_context();names={m['id']:m['name'] for m in members}
                entity_id=parse_qs(urlsplit(self.path).query).get('entity',[None])[0]
                rows=ledger.history(group,entity_id)
                for row in rows:row['actor']=names.get(row['actor_id'],'Former Homebox member')
                self.reply_json(200,rows)
            except (ValueError,KeyError):self.reply_json(400,{'error':'Invalid history request'})
            except OSError:self.reply_json(503,{'error':'Homebox unavailable'})
            return
        if self.path=='/api/recovery':
            if not OPEN_ADMIN:self.send_error(403);return
            try:
                client=Homebox(ROOT);group=client.call('/api/v1/users/self')['item']['defaultGroupId'];rows=[]
                for record in ledger.unresolved():
                    if record['group_id']!=group:continue
                    detail=ledger.detail(group,record['id']);detail.pop('request_hash',None);detail.pop('request_key',None)
                    detail['native_assets']=[]
                    for entity_id in detail['assets']:
                        try:
                            entity=client.entity(entity_id)
                            detail['native_assets'].append({'id':entity_id,'name':entity['name'],'condition':condition(entity),'parent':(entity.get('parent') or {}).get('name','Unassigned')})
                        except OSError:detail['native_assets'].append({'id':entity_id,'name':entity_id,'error':'Native asset unavailable'})
                    rows.append(detail)
                self.reply_json(200,rows)
            except (OSError,ValueError,KeyError):self.reply_json(503,{'error':'Recovery data unavailable'})
            return
        if urlsplit(self.path).path=='/api/entity':
            try:
                entity_id=parse_qs(urlsplit(self.path).query).get('id',[''])[0]
                entity=Homebox(ROOT).entity(entity_id)
                self.reply_json(200,{'entity':entity,'condition':condition(entity),'states':STATES,'return_states':RETURN_STATES,'blocker':checkout_blocker(entity)} )
            except (ValueError,KeyError):self.reply_json(400,{'error':'Invalid asset'})
            except OSError:self.reply_json(503,{'error':'Homebox unavailable'})
            return
        if self.path=='/':
            body=(ROOT/'kiosk/index.html').read_bytes();mime='text/html; charset=utf-8';code=200
        elif self.path in ('/api/members','/api/badges','/api/session','/api/custody'):
            try:
                group,members=native_context()
                if self.path=='/api/members':data=[{'id':m['id'],'name':m['name']} for m in members]
                elif self.path=='/api/custody':
                    data=ledger.custody(group)
                    names={m['id']:m['name'] for m in members}
                    for row in data:row['borrower']=names.get(row['actor_id'],'Former Homebox member')
                elif self.path=='/api/badges':data=badges.list(group) if OPEN_ADMIN else []
                else:
                    with lock:
                        member=next((m for m in members if m['id']==session.current()),None)
                        if not member:session.end()
                    data={'user':{'id':member['id'],'name':member['name']} if member else None}
                self.reply_json(200,data)
            except (OSError,ValueError,KeyError):self.reply_json(503,{'error':'Homebox unavailable'})
            return
        elif self.path in ('/api/inventory','/api/locations'):
            try:
                with lock:body=json.dumps(inventory(self.path=='/api/locations')).encode()
                code=200
            except (OSError,ValueError,KeyError):body=b'{"error":"Homebox unavailable"}';code=503
            mime='application/json'
        else:body=b'Not found';mime='text/plain';code=404
        self.send_response(code);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
    def log_message(self,*args):pass
print('Kiosk prototype: http://127.0.0.1:17749',flush=True)
ThreadingHTTPServer(('127.0.0.1',17749),Handler).serve_forever()
