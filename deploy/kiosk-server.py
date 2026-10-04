#!/usr/bin/env python3
"""Loopback Homebox companion using the isolated native demonstration account."""
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
from native_jobs import NativeJobs
from categories import create_category,recover_category
from stock import browse as browse_stock,invalidate as invalidate_stock
from reviews import submit_review,recover_review
from kits import manifest as kit_manifest,save as save_kit
from system_status import status as system_status,start_backup
from accounts import create_account
from labels import preview as label_preview,print_label,print_badge,recover_print,probe as printer_probe
from problems import submit_problem,recover_problem
from setup_native import submit, recover_creation
from imports import Imports
from kiosk_processes import kiosk_pids
from workshop import Workshop,move_location
from products import catalog,lookup
from ledger import Conflict
from conditions import STATES, condition, checkout_blocker, set_condition
BASE='http://127.0.0.1:17745'
lock=threading.Lock()
ops_path=ROOT/'work/ops'
ops_path.mkdir(exist_ok=True,mode=0o700)
os.chmod(ops_path,0o700)
ledger=Ledger(ops_path/'ledger.db')
badges=Badges(ledger)
native_jobs=NativeJobs(ledger)
imports=Imports(ops_path/'imports.db')
workshop=Workshop(ops_path/'workshop.db')
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
        if self.path in ('/workshop/get','/workshop/save','/workshop/move') or self.path in ('/imports/upload', '/imports/map', '/imports/save', '/imports/create', '/imports/label', '/imports/get', '/imports/list') or self.path in ('/camera/focus','/decode','/scan','/badge/issue','/badge/revoke','/session/end','/session/activity','/condition','/checkout/confirm','/return/confirm','/recovery/resolve','/map/room','/map/object','/map/remove','/locations/create','/catalog/create','/enroll/confirm','/problem/confirm','/label/preview','/label/print','/accounts/create','/backup/start','/kit/save','/maintenance/complete','/categories/create','/badge/print'):
            if self.headers.get('Origin') != 'http://127.0.0.1:17749':self.send_error(403);return
            try:size=int(self.headers.get('Content-Length','0'))
            except ValueError:self.send_error(400);return
            if not 0<size<=1000000:self.send_error(413);return
            raw=self.rfile.read(size)
            try:
                if self.path=='/decode':
                    with Image.open(io.BytesIO(raw)) as frame:
                        if frame.width>1280 or frame.height>960:self.send_error(413);return
                        found=zxingcpp.read_barcodes(frame)
                        codes=[c.text for c in found]
                        detections=[{'code':c.text,'corners':[[p.x,p.y] for p in (c.position.top_left,c.position.top_right,c.position.bottom_right,c.position.bottom_left)]} for c in found]
                        width,height=frame.size
                    self.reply_json(200,{'codes':codes,'detections':detections,'width':width,'height':height});return
                data=json.loads(raw)
                if self.path=='/camera/focus':
                    import subprocess
                    device='/dev/video0'
                    if 'C920' not in pathlib.Path('/sys/class/video4linux/video0/name').read_text():raise ValueError('Pi C920 camera not found')
                    mode=data.get('mode')
                    if mode not in ('auto','manual'):raise ValueError('Unknown focus mode')
                    value=data.get('value',150)
                    if mode=='manual' and (type(value) is not int or value<0 or value>250 or value%5):raise ValueError('Focus must be 0 to 250 in steps of 5')
                    subprocess.run(['v4l2-ctl','-d',device,'--set-ctrl=focus_automatic_continuous='+('1' if mode=='auto' else '0')],check=True,capture_output=True,timeout=5)
                    if mode=='manual':subprocess.run(['v4l2-ctl','-d',device,'--set-ctrl=focus_absolute='+str(value)],check=True,capture_output=True,timeout=5)
                    self.reply_json(200,{'mode':mode,'value':value});return
                if self.path.startswith('/workshop/'):
                    if self.path!='/workshop/get' and not OPEN_ADMIN:self.send_error(403);return
                    with lock:
                        client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item'];group=native['defaultGroupId']
                        if self.path=='/workshop/save':result=workshop.save(client,group,data)
                        elif self.path=='/workshop/move':result=move_location(client,data);invalidate_stock()
                        else:result=workshop.snapshot(client,group)
                    self.reply_json(200,result);return
                if self.path.startswith('/imports/'):
                    if not OPEN_ADMIN:self.send_error(403);return
                    with lock:
                        client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item'];group=native['defaultGroupId'];action=self.path.rsplit('/',1)[1]
                        if action=='upload':result=imports.upload(group,session.current() or native['id'],data)
                        elif action=='list':result=imports.list(group)
                        elif action=='map':result=imports.map(client,group,data)
                        elif action=='get':result=imports.sync(client,native_jobs,group,data)
                        else:result=getattr(imports,action)(client,native_jobs,group,data)
                        if action=='create':invalidate_stock()
                    self.reply_json(200,result);return
                if self.path not in ('/scan','/session/end','/session/activity','/label/preview','/backup/start'):invalidate_stock()
                if self.path=='/badge/print':
                    if not OPEN_ADMIN:self.send_error(403);return
                    with lock:
                        client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item'];result=print_badge(client,badges,native_jobs,native['defaultGroupId'],session.current() or native['id'],data.get('request_key'),data.get('badge_id'),data.get('code'))
                    self.reply_json(200,result);return
                if self.path=='/categories/create':
                    if not OPEN_ADMIN:self.send_error(403);return
                    with lock:
                        client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item'];result=create_category(client,native_jobs,native['defaultGroupId'],session.current() or native['id'],data.get('request_key'),data.get('input',{}))
                    self.reply_json(200,result);return
                if self.path=='/maintenance/complete':
                    if not OPEN_ADMIN:self.send_error(403);return
                    with lock:
                        client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item'];result=submit_review(client,native_jobs,native['defaultGroupId'],session.current() or native['id'],data.get('request_key'),data,'complete_maintenance')
                    self.reply_json(200,result);return
                if self.path=='/kit/save':
                    if not OPEN_ADMIN:self.send_error(403);return
                    with lock:
                        client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item'];held={r['entity_id'] for r in ledger.custody(native['defaultGroupId'])}
                        if held & {data.get('entity_id'),*data.get('members',[])}:raise Conflict('Return the kit and components before changing its manifest')
                        result=save_kit(client,data.get('entity_id'),data.get('members',[]))
                    self.reply_json(200,result);return
                if self.path=='/backup/start':
                    if not OPEN_ADMIN:self.send_error(403);return
                    with lock:result=start_backup(data.get('request_key'))
                    self.reply_json(202,result);return
                if self.path=='/accounts/create':
                    if not OPEN_ADMIN:self.send_error(403);return
                    with lock:result=create_account(Homebox(ROOT),data)
                    self.reply_json(200,result);return
                if self.path in ('/label/preview','/label/print'):
                    if not OPEN_ADMIN:self.send_error(403);return
                    with lock:
                        client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item']
                        result=label_preview(client,data.get('entity_id')) if self.path=='/label/preview' else print_label(client,native_jobs,native['defaultGroupId'],session.current() or native['id'],data.get('request_key'),data.get('entity_id'))
                    self.reply_json(200,result);return
                if self.path in ('/locations/create','/catalog/create','/enroll/confirm','/problem/confirm'):
                    if self.path not in ('/enroll/confirm','/problem/confirm') and not OPEN_ADMIN:self.send_error(403);return
                    actor,generation=session.snapshot()
                    if self.path in ('/enroll/confirm','/problem/confirm'):
                        if not actor:self.reply_json(401,{'error':'Scan your badge first'});return
                        if data.get('session_generation')!=generation or data.get('session_instance')!=session.instance:raise Conflict('Badge session changed; review your selection again')
                    with lock:
                        client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item'];group=native['defaultGroupId']
                        if actor and actor not in {m['id'] for m in client.call('/api/v1/groups/members')}:raise Conflict('Badge holder is no longer a member')
                        kind={'/locations/create':'create_location','/catalog/create':'create_template','/enroll/confirm':'create_asset','/problem/confirm':'report_problem'}[self.path]
                        if self.path in ('/enroll/confirm','/problem/confirm') and session.snapshot()!=(actor,generation):raise Conflict('Session ended; scan your badge again')
                        result=submit_problem(client,native_jobs,group,actor,data.get('request_key'),data.get('input',{})) if kind=='report_problem' else submit(client,native_jobs,group,actor or native['id'],kind,data.get('request_key'),data.get('input',{}))
                        if self.path in ('/enroll/confirm','/problem/confirm'):session.end(generation)
                    self.reply_json(200,result);return
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
                        group=native['defaultGroupId']
                        if data.get('native_job'):
                            job=native_jobs.detail(group,data.get('id'))
                            handler=recover_category if job['kind']=='create_type' else recover_review if job['kind'] in ('review_condition','complete_maintenance') else recover_print if job['kind'] in ('print_label','print_badge') else recover_problem if job['kind']=='report_problem' else recover_creation
                            result=handler(client,native_jobs,group,data.get('id'),data.get('outcome'))
                        else:result=recover(client,ledger,group,data.get('id'),data.get('outcome'))
                    self.reply_json(200,result);return
                if self.path=='/return/confirm':
                    actor,generation=session.snapshot()
                    if not actor:self.reply_json(401,{'error':'Scan your badge first'});return
                    if data.get('session_generation')!=generation or data.get('session_instance')!=session.instance:raise Conflict('Badge session changed; review your selection again')
                    with lock:
                        client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item']
                        result=confirm_return(client,ledger,native['defaultGroupId'],actor,data.get('targets'),data.get('request_key'),lambda:session.snapshot()==(actor,generation),session.scans(generation),data.get('kit_versions'))
                        session.end(generation)
                    self.reply_json(200,result);return
                if self.path=='/checkout/confirm':
                    actor,generation=session.snapshot()
                    if not actor:self.reply_json(401,{'error':'Scan your badge first'});return
                    if data.get('session_generation')!=generation or data.get('session_instance')!=session.instance:raise Conflict('Badge session changed; review your selection again')
                    with lock:
                        client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item']
                        result=confirm_checkout(client,ledger,native['defaultGroupId'],actor,data.get('assets',[]),data.get('request_key'),lambda:session.snapshot()==(actor,generation),session.scans(generation),data.get('kit_versions'))
                        session.end(generation)
                    self.reply_json(200,result);return
                if self.path=='/condition':
                    if not OPEN_ADMIN:self.send_error(403);return
                    with lock:
                        client=Homebox(ROOT);native=client.call('/api/v1/users/self')['item'];result=submit_review(client,native_jobs,native['defaultGroupId'],session.current() or native['id'],data.get('request_key'),{'entity_id':data.get('entity_id'),'state':data.get('state')});entity=client.entity(result['entity_id'])
                    self.reply_json(200,{'entity':entity,'condition':condition(entity),'blocker':checkout_blocker(entity)});return
                if self.path=='/session/activity':
                    self.reply_json(200,{'active':session.current(activity=True) is not None});return
                if self.path=='/scan':session.current(activity=True)
                if self.path=='/session/end':
                    if not data.get('expected_instance') or data.get('expected_instance')==session.instance:session.end(data.get('expected_generation'))
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
                        generation=session.start(user)
                        self.reply_json(200,{'kind':'user','user':{'id':user,'name':name},'generation':generation,'instance':session.instance})
                    else:self.reply_json(200,{'kind':'invalid','reason':'Badge unknown, revoked, or no longer a group member'})
                    return
                code=normalize(data.get('code'))
                if code['kind'] in ('asset','entity'):
                    with lock:items=inventory()+inventory(True)
                    match=next((e for e in items if ('asset_id' in code and e.get('assetId')==code['asset_id']) or ('entity_id' in code and e['id']==code['entity_id'])),None)
                    if match:
                        code['entity']=match;session.record_scan(match['id'])
                    else:code={'kind':'unknown','reason':'This code is not in this Homebox inventory'}
                self.reply_json(200,code)
            except Conflict as error:self.reply_json(409,{'error':str(error),'reason':str(error)})
            except (ValueError,TypeError,AttributeError,KeyError) as error:self.reply_json(400,{'kind':'invalid','error':str(error),'reason':str(error)})
            except OSError:self.reply_json(503,{'error':'Homebox unavailable; no confirmation received','reason':'Homebox unavailable; try again'})
            return

        if self.path != '/exit' or self.headers.get('Origin') != 'http://127.0.0.1:17749':
            self.send_error(403);return
        profile=str(ROOT/'work/kiosk-browser')
        targets=kiosk_pids(profile)
        if not targets:
            self.send_error(409);return
        self.send_response(200);self.send_header('Content-Length','0');self.end_headers()
        self.wfile.flush()
        def close_window():
            for pid in targets:
                try:os.kill(pid,signal.SIGTERM)
                except ProcessLookupError:pass
        timer=threading.Timer(0.3,close_window);timer.daemon=True;timer.start()
    def do_GET(self):
        if urlsplit(self.path).path=='/api/file':
            try:
                from ledger import uuid
                query=parse_qs(urlsplit(self.path).query);entity_id=uuid(query.get('entity',[None])[0]);attachment_id=uuid(query.get('attachment',[None])[0]);client=Homebox(ROOT);entity=client.entity(entity_id)
                attachment=next(a for a in entity.get('attachments',[]) if a['id']==attachment_id)
                request=urllib.request.Request(client.base+'/api/v1/entities/'+entity_id+'/attachments/'+attachment_id,headers={'Authorization':'Bearer '+client.token})
                class LocalRedirect(urllib.request.HTTPRedirectHandler):
                    def redirect_request(self,request,fp,code,msg,headers,newurl):
                        destination=urlsplit(newurl)
                        if destination.hostname!='127.0.0.1' or destination.port!=17745:raise ValueError('External file unavailable offline')
                        return super().redirect_request(request,fp,code,msg,headers,newurl)
                with urllib.request.build_opener(LocalRedirect()).open(request,timeout=15) as response:
                    content=response.read(10000001);mime=response.headers.get_content_type()
                if len(content)>10000000:raise ValueError('File exceeds kiosk preview limit')
                self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(content)));self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store')
                if mime not in ('image/jpeg','image/png','image/webp','image/gif'):self.send_header('Content-Disposition','attachment')
                self.end_headers();self.wfile.write(content)
            except (OSError,ValueError,StopIteration):self.reply_json(404,{'error':'Native file unavailable'})
            return
        if urlsplit(self.path).path=='/api/stock':
            try:self.reply_json(200,browse_stock(Homebox(ROOT),'refresh' in parse_qs(urlsplit(self.path).query)))
            except (OSError,ValueError):self.reply_json(503,{'error':'Native stock unavailable'})
            return
        if urlsplit(self.path).path=='/api/maintenance':
            try:
                from ledger import uuid
                entity_id=uuid(parse_qs(urlsplit(self.path).query).get('entity',[None])[0]);self.reply_json(200,Homebox(ROOT).call('/api/v1/entities/'+entity_id+'/maintenance'))
            except (OSError,ValueError):self.reply_json(503,{'error':'Native maintenance unavailable'})
            return
        if urlsplit(self.path).path=='/api/kit':
            try:
                data=kit_manifest(Homebox(ROOT),parse_qs(urlsplit(self.path).query).get('id',[None])[0]);data['verified']=list(session.scans(session.snapshot()[1]));self.reply_json(200,data)
            except (ValueError,OSError):self.reply_json(400,{'error':'Kit manifest or native equipment needs review'})
            return
        if self.path=='/api/system':
            if not OPEN_ADMIN:self.send_error(403);return
            self.reply_json(200,system_status());return
        if urlsplit(self.path).path in ('/api/catalog','/api/product','/api/types'):
            try:
                client=Homebox(ROOT)
                if urlsplit(self.path).path=='/api/catalog':data=catalog(client)
                elif urlsplit(self.path).path=='/api/types':data=client.call('/api/v1/entity-types')
                else:data=lookup(client,parse_qs(urlsplit(self.path).query).get('gtin',[''])[0])
                self.reply_json(200,data)
            except (ValueError,KeyError):self.reply_json(400,{'error':'Barcode or catalog data needs review'})
            except OSError:self.reply_json(503,{'error':'Native catalog unavailable'})
            return
        if urlsplit(self.path).path=='/api/map':
            try:
                entity_id=parse_qs(urlsplit(self.path).query).get('entity',[None])[0]
                self.reply_json(200,list_map(Homebox(ROOT),entity_id))
            except (ValueError,TypeError,KeyError):self.reply_json(400,{'error':'Map or location needs review'})
            except OSError:self.reply_json(503,{'error':'Homebox map unavailable'})
            return
        if self.path=='/api/session' and session.current() is None:
            self.reply_json(200,{'user':None,'generation':session.snapshot()[1],'instance':session.instance});return
        if urlsplit(self.path).path=='/api/history':
            try:
                group,members=native_context();names={m['id']:m['name'] for m in members}
                entity_id=parse_qs(urlsplit(self.path).query).get('entity',[None])[0]
                rows=ledger.history(group,entity_id)+native_jobs.history(group,entity_id)
                rows=sorted(rows,key=lambda r:r['created_at'],reverse=True)[:100]
                client=Homebox(ROOT);labels={e['id']:e['name'] for e in client.entities()+client.entities(True)}
                labels.update(names);labels.update({t['id']:t['name'] for t in client.call('/api/v1/templates')});labels.update({t['id']:t['name'] for t in client.call('/api/v1/entity-types')})
                for row in rows:row['asset_names']=[labels.get(key,'Deleted native record') for key in row['assets']]
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
                for job in native_jobs.unresolved(group):
                    rows.append({'id':job['id'],'action':job['kind'],'status':job['status'],'native_job':True,
                        'native_assets':[{'id':job['result_id'],'name':(job['payload'] or {}).get('name','Native setup task'),'error':'Pending native setup'}],
                        'context':None})
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
        elif self.path=='/workshop-ui.js':
            body=(ROOT/'kiosk/workshop-ui.js').read_bytes();mime='text/javascript; charset=utf-8';code=200
        elif self.path=='/import-ui.js':
            body=(ROOT/'kiosk/import-ui.js').read_bytes();mime='text/javascript; charset=utf-8';code=200
        elif self.path in ('/api/members','/api/badges','/api/session','/api/custody'):
            try:
                snapshot=session.snapshot()
                group,members=native_context()
                if self.path=='/api/members':data=[{'id':m['id'],'name':m['name']} for m in members]
                elif self.path=='/api/custody':
                    data=ledger.custody(group)
                    names={m['id']:m['name'] for m in members}
                    for row in data:row['borrower']=names.get(row['actor_id'],'Former Homebox member')
                elif self.path=='/api/badges':data=badges.list(group) if OPEN_ADMIN else []
                else:
                    with lock:
                        member=next((m for m in members if m['id']==snapshot[0]),None)
                        if not member:session.end(snapshot[1])
                    data={'user':{'id':member['id'],'name':member['name']} if member else None,'generation':snapshot[1],'instance':session.instance}
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
