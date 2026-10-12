#!/usr/bin/env python3
"""Exercise hierarchy mutations in a disposable native DB; never use live data."""
import pathlib,tempfile,subprocess,os,time,json,sys,hashlib,urllib.request,urllib.error
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ops'))
from homebox import Homebox
from native_fields import update_payload
BASE='http://127.0.0.1:17777'
BINARY=pathlib.Path(os.environ.get('HOMEBOX_VERIFY_NATIVE_BINARY',str(ROOT/'work/homebox-backend-build/homebox')))
results=[]
def passed(name):results.append(name);print('PASS '+name,flush=True)
with tempfile.TemporaryDirectory(prefix='native-hierarchy-isolated-') as folder:
 root=pathlib.Path(folder);(root/'data').mkdir();(root/'work/baseline').mkdir(parents=True)
 env=dict(os.environ,HBOX_WEB_HOST='127.0.0.1',HBOX_WEB_PORT='17777',HBOX_STORAGE_PREFIX_PATH=str(root/'data'),HBOX_DATABASE_SQLITE_PATH=str(root/'data/homebox.db')+'?_pragma=busy_timeout=999&_pragma=journal_mode=WAL&_fk=1&_time_format=sqlite',HBOX_AUTH_API_KEY_PEPPER=str(uuid4()),HBOX_OPTIONS_ALLOW_REGISTRATION='true',HBOX_OPTIONS_GITHUB_RELEASE_CHECK='false',HBOX_OPTIONS_ALLOW_ANALYTICS='false')
 with (root/'native.log').open('w') as log:
  process=subprocess.Popen([str(BINARY)],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
  try:
   for _ in range(200):
    try:urllib.request.urlopen(BASE+'/api/v1/status',timeout=1).close();break
    except OSError:
     if process.poll() is not None:raise RuntimeError('Isolated native server exited')
     time.sleep(.1)
   with urllib.request.urlopen(BASE+'/swagger/doc.json',timeout=10) as response:contract=json.load(response)['definitions']
   assert 'parentId' not in contract['v1.EntityTemplateCreateItemRequest'].get('required',[])
   assert contract['v1.EntityTemplateCreateItemRequest']['properties']['parentId']['x-nullable']
   assert contract['repo.EntityPatch']['properties']['clearParent']['type']=='boolean'
   passed('Published native JSON contract exposes optional template parents and explicit parent clearing')
   def account(name):
    data={'name':name,'email':str(uuid4())+'@isolated.invalid','password':'isolated-test-password'}
    req=urllib.request.Request(BASE+'/api/v1/users/register',data=json.dumps(data).encode(),headers={'Content-Type':'application/json'});urllib.request.urlopen(req,timeout=30).close()
    (root/'work/baseline/test-account.json').write_text(json.dumps(data));return Homebox(root,base=BASE)
   client=account('Fixture admin');client.call('/api/v1/entity-types','POST',{'name':'Equipment','isLocation':False});types=client.call('/api/v1/entity-types');loc=next(t['id'] for t in types if t['isLocation']);item=next(t['id'] for t in types if not t['isLocation'])
   def create(name,kind,parent=None,using=client):return using.call('/api/v1/entities','POST',{'name':name,'entityTypeId':kind,'parentId':parent,'quantity':1})
   def move(entity,parent,method='PUT'):
    payload=update_payload(client.entity(entity['id'])) if method=='PUT' else {}
    if method=='PATCH' and parent is None:payload['clearParent']=True
    else:payload['parentId']=parent
    return client.call('/api/v1/entities/'+entity['id'],method,payload)
   def rejected(fn):
    try:fn()
    except urllib.error.HTTPError as error:assert error.code in (400,403,404,422),error.code
    else:raise AssertionError('Unsafe hierarchy write was accepted')
   office=create('Office',loc);box=create('Box',item);shelf=create('Shelf',loc,box['id']);vacuum=create('Vacuum',item,office['id']);child=create('Child',item,box['id'])
   assert client.entity(box['id']).get('parent') is None
   passed('Optional roots, locations inside items and direct item placement')
   payload=update_payload(client.entity(box['id']));payload.update(syncChildEntityLocations=True,serialNumber='preserve-serial',description='preserve-description',fields=[{'name':'Fixture metadata','type':'text','textValue':'preserve-value'}]);client.call('/api/v1/entities/'+box['id'],'PUT',payload)
   move(box,office['id']);move(box,None,'PATCH');move(box,office['id'],'PATCH')
   for entity in (shelf,child):assert client.entity(entity['id'])['parent']['id']==box['id']
   fresh=client.entity(box['id']);assert fresh['serialNumber']=='preserve-serial' and fresh['description']=='preserve-description' and fresh['fields'][0]['textValue']=='preserve-value' and fresh['syncChildEntityLocations']
   passed('PUT/PATCH moves and clear-parent retain container contents and native metadata')
   for method in ('PUT','PATCH'):
    rejected(lambda:move(box,box['id'],method));rejected(lambda:move(box,shelf['id'],method));rejected(lambda:move(office,child['id'],method))
   passed('Self and mixed descendant cycles rejected by every native update path')
   archived=create('Archived destination',item);payload=update_payload(archived);payload['archived']=True;client.call('/api/v1/entities/'+archived['id'],'PUT',payload)
   rejected(lambda:create('Rejected fixture',loc,archived['id']));rejected(lambda:move(vacuum,archived['id']))
   passed('Archived destinations rejected before any parent mutation')
   template=client.call('/api/v1/templates','POST',{'name':'Fixture template','defaultQuantity':1,'defaultManufacturer':'Fixture maker'})
   def from_template(parent):return client.call('/api/v1/templates/'+template['id']+'/create-item','POST',{'name':'Fixture template item','parentId':parent,'entityTypeId':item,'quantity':1,'tagIds':[]})
   assert from_template(None).get('parent') is None
   assert from_template(box['id'])['parent']['id']==box['id']
   rejected(lambda:from_template(archived['id']))
   passed('Template creation uses the same optional active mixed-parent checks')

   second=account('Foreign group');foreign=second.call('/api/v1/entities','POST',{'name':'Private foreign parent','entityTypeId':next(t['id'] for t in second.call('/api/v1/entity-types') if t['isLocation']),'parentId':None,'quantity':1})
   rejected(lambda:move(box,foreign['id']));rejected(lambda:create('Foreign fixture',loc,foreign['id']))
   passed('Cross-collection parents remain inaccessible')
   chain=[create('Deep root',loc)]
   for index in range(70):chain.append(create('Depth '+str(index+1),loc if index%2 else item,chain[-1]['id']))
   def flatten(tree):
    nodes=[];todo=list(tree)
    while todo:
     node=todo.pop();nodes.append(node);todo.extend(node.get('children') or [])
    return nodes
   for with_items in ('true','false'):
    tree=flatten(client.call('/api/v1/entities/tree?withItems='+with_items));assert set(e['id'] for e in chain)<=set(e['id'] for e in tree)
   path=client.call('/api/v1/entities/'+chain[-1]['id']+'/path');assert len(path)==71 and [p['type'] for p in path]==['location']+['item' if i%2==0 else 'location' for i in range(70)]
   mixed=client.call('/api/v1/entities/'+shelf['id']+'/path');assert [p['type'] for p in mixed]==['location','item','location']
   rejected(lambda:move(chain[0],chain[-1]['id']))
   passed('71-level mixed trees and typed breadcrumbs keep all levels without arbitrary caps')
   a=create('Concurrent A',item);b=create('Concurrent B',loc)
   def competing(pair):
    try:move(pair[0],pair[1]['id'],'PATCH');return True
    except urllib.error.HTTPError as error:assert error.code==400;return False
   with ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(competing,[(a,b),(b,a)]))
   assert sorted(outcomes)==[False,True]
   assert not ((client.entity(a['id']).get('parent') or {}).get('id')==b['id'] and (client.entity(b['id']).get('parent') or {}).get('id')==a['id'])
   passed('Concurrent opposing parent changes cannot create a cycle')
   receipt={'checks':results,'count':len(results),'live_mutations':0,'physical_prints':0,'native_binary':str(BINARY),'binary_sha256':hashlib.sha256(BINARY.read_bytes()).hexdigest()}
   target=ROOT/'work/nesting-api-results.json';target.write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'count':len(results),'live_mutations':0,'physical_prints':0}))
  finally:process.terminate();process.wait(timeout=15)
