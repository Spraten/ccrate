"""Optional deliberate photos become native attachments, with safe recovery."""
import base64,hashlib,io,urllib.request
from PIL import Image
from ledger import Conflict
def photo_bytes(value):
    if not isinstance(value,str) or not value.startswith('data:image/jpeg;base64,') or len(value)>650000:raise ValueError('Use a JPEG equipment photo smaller than 480 KB')
    raw=base64.b64decode(value.split(',',1)[1],validate=True)
    with Image.open(io.BytesIO(raw)) as image:
        if image.width>1280 or image.height>960:raise ValueError('Equipment photo is too large')
        image.load();output=io.BytesIO();image.convert('RGB').save(output,format='JPEG',quality=85)
    return output.getvalue()
def upload(client,entity_id,title,content):
    boundary='homebox-companion-photo';parts=[]
    for name,value in [('name',title),('type','photo'),('primary','false')]:parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{title}"\r\nContent-Type: image/jpeg\r\n\r\n'.encode()+content+b'\r\n')
    body=b''.join(parts)+f'--{boundary}--\r\n'.encode()
    request=urllib.request.Request(client.base+'/api/v1/entities/'+entity_id+'/attachments',data=body,headers={'Authorization':'Bearer '+client.token,'Content-Type':'multipart/form-data; boundary='+boundary})
    with urllib.request.urlopen(request,timeout=20) as response:response.read()
def photo_values(data):
    values=data.get('photos')
    if values is None:values=[data['photo']] if data.get('photo') else []
    if not isinstance(values,list) or len(values)>6:raise ValueError('Add up to six equipment photos')
    return values

def validate_photos(data):
    for value in photo_values(data):photo_bytes(value)

def ensure_photo(client,jobs,group,key,entity_id):
    job=jobs.detail(group,key);payload=job['payload'] or {}
    values=photo_values(payload)
    legacy=payload.get('photos') is None
    for index,value in enumerate(values):
        content=photo_bytes(value);digest=hashlib.sha256(content).hexdigest()
        suffix='' if legacy else '-'+str(index+1)
        title='Equipment photo '+job['id']+suffix+'.jpg'
        flag='photo_post_started' if legacy else 'photo_post_started_'+str(index+1)
        def matches():return [a for a in client.entity(entity_id).get('attachments',[]) if a['title']==title]
        found=matches()
        if len(found)>1:raise Conflict('Multiple native photos match this request; review C-Crate')
        if not found:
            if jobs.detail(group,key)['context'].get(flag):raise Conflict('Photo upload outcome is unknown; review native attachments before retrying')
            jobs.context(group,key,**{flag:True});upload(client,entity_id,title,content);found=matches()
        if len(found)!=1:raise Conflict('Native photo could not be verified')
        request=urllib.request.Request(client.base+'/api/v1/entities/'+entity_id+'/attachments/'+found[0]['id'],headers={'Authorization':'Bearer '+client.token})
        with urllib.request.urlopen(request,timeout=15) as response:actual=response.read()
        if hashlib.sha256(actual).hexdigest()!=digest:raise Conflict('Native photo bytes differ; inspect C-Crate before finishing')
        jobs.record(group,key,'native_photo_verified',{'entity_id':entity_id,'attachment_id':found[0]['id'],'sha256':digest})
