"""Native QR label previews and one-shot USB printing with durable outcomes."""
import io,base64,json,pathlib,subprocess,textwrap,hashlib
import qrcode
from PIL import Image,ImageDraw,ImageFont
from ledger import Conflict,uuid
ROOT=pathlib.Path('/home/user/Desktop/inventory-system')
def printer_path():
    matches=[]
    for device in pathlib.Path('/sys/class/hidraw').glob('hidraw*'):
        if 'HID_ID=0003:00001820:0000207F' in (device/'device/uevent').read_text():matches.append('/dev/'+device.name)
    if len(matches)!=1:raise ValueError('Connect exactly one SUPVAN printer')
    return matches[0]
def adapter():return str(ROOT/'work/supvan-cups/target/release/examples/kiosk-label')
def probe():
    result=subprocess.run([adapter(),'probe',printer_path()],capture_output=True,timeout=15,check=True)
    return json.loads(result.stdout)
def font(size):return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf',size)
def render(entity,width_mm=40,height_mm=30,code_override=None,title_override=None):
    width=min(384,int(width_mm)*8);height=int(height_mm)*8-16
    if width<256 or height<208:raise ValueError('Loaded labels are too small for this QR layout (minimum 32 x 28 mm)')
    location=bool(entity.get('entityType',{}).get('isLocation'));code=code_override or ('/location/' if location else '/item/')+uuid(entity['id'])
    qr=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,box_size=1,border=4);qr.add_data(code);qr.make(fit=True)
    matrix=qr.get_matrix();scale=min((height-28)//len(matrix),(width-112)//len(matrix))
    if scale<4:raise ValueError('Loaded label does not leave enough room for a readable QR code')
    image=Image.new('L',(width,height),255);draw=ImageDraw.Draw(image);draw.fontmode='1'
    draw.text((8,15),title_override or ('LOCATION' if location else 'EQUIPMENT'),font=font(18),fill=0)
    for y,row in enumerate(matrix):
        for x,black in enumerate(row):
            if black:draw.rectangle((x*scale,26+y*scale,(x+1)*scale-1,26+(y+1)*scale-1),fill=0)
    left=len(matrix)*scale+4;available=width-left-4;top=30
    # Bold, binary text avoids weak gray edge dots from thermal dithering.
    name_font=font(18);lines=[];line=''
    for character in ' '.join(entity['name'].split()):
        candidate=line+character
        if line and draw.textbbox((0,0),candidate,font=name_font)[2]>available:
            lines.append(line.rstrip());line=character.lstrip()
        else:line=candidate
    if line:lines.append(line)
    max_lines=max(1,(height-74-top)//22)
    for line in lines[:max_lines]:
        draw.text((left,top),line,font=name_font,fill=0);top+=22
    identifier=entity.get('assetId','');identifier_font=font(17)
    while identifier and draw.textbbox((0,0),identifier,font=identifier_font)[2]>available:identifier=identifier[:-1]
    draw.text((left,height-56),identifier,font=identifier_font,fill=0)
    draw.text((left,height-32),'Homebox',font=font(13),fill=0)
    return image,code
def preview(client,entity_id):
    entity=client.entity(uuid(entity_id));image,code=render(entity);stream=io.BytesIO();image.save(stream,format='PNG')
    return {'entity_id':entity['id'],'name':entity['name'],'code':code,'width':image.width,'height':image.height,'image':'data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode()}
def print_label(client,jobs,group,actor,key,entity_id):
    entity_id=uuid(entity_id);job=jobs.prepare(group,actor,'print_label',key,{'entity_id':entity_id})
    if job['status']=='completed':return {'id':job['id'],'status':'completed','entity_id':entity_id}
    if job['status']!='prepared':raise Conflict('Printer outcome needs Admin review. Do not retry automatically')
    try:
        material=probe();entity=client.entity(entity_id);image,code=render(entity,material['width_mm'],material['height_mm'])
        jobs.sent(group,job['id']);jobs.bind(group,job['id'],entity_id)
        result=subprocess.run([adapter(),'print',printer_path(),str(image.width),str(image.height)],input=image.tobytes(),capture_output=True,timeout=60,check=True)
        if json.loads(result.stdout).get('status')!='printed':raise OSError('Printer did not confirm completion')
        jobs.record(group,job['id'],'printer_completion',{'entity_id':entity_id});jobs.complete(group,job['id'])
        return {'id':job['id'],'status':'completed','entity_id':entity_id}
    except Exception:
        if jobs.detail(group,job['id'])['status']=='prepared':jobs.cancel(group,job['id']);raise ValueError('Printer not ready. Check connection and loaded stock')
        jobs.review(group,job['id'],'Printer outcome uncertain. Inspect the label; never auto-reprint')
        raise Conflict('Printing outcome is uncertain. Inspect the label and review in Admin')
def recover_print(client,jobs,group,job_id,outcome):
    job=jobs.detail(group,job_id)
    if job['kind'] not in ('print_label','print_badge'):raise ValueError('Not a printer job')
    if outcome!='complete':raise Conflict('Inspect the printer output. Finishing acknowledges it; reprint is a separate explicit action')
    if job['status']!='completed':jobs.record(group,job_id,'physical_output_acknowledged',{});jobs.complete(group,job_id)
    return {'id':job_id,'status':'completed','entity_id':job['result_id']}

def print_badge(client,badges,jobs,group,actor,key,badge_id,code):
    members=client.call('/api/v1/groups/members');user_id=badges.resolve(group,code,[m['id'] for m in members])
    badge=next((b for b in badges.list(group) if b['id']==uuid(badge_id) and not b['revoked']),None)
    if not user_id or not badge or badge['user_id']!=user_id:raise ValueError('Badge is revoked or does not match this native member')
    name=next(m['name'] for m in members if m['id']==user_id)
    # Neither the bearer code nor its QR raster enters the database or filesystem.
    job=jobs.prepare(group,actor,'print_badge',key,{'badge_id':badge['id'],'code_hash':hashlib.sha256(code.encode()).hexdigest()})
    if job['status']=='completed':return {'id':job['id'],'status':'completed'}
    if job['status']!='prepared':raise Conflict('Badge printing needs Admin review; do not retry automatically')
    try:
        material=probe();image,_=render({'id':user_id,'name':name,'assetId':'Scan to identify'},material['width_mm'],material['height_mm'],code_override=code,title_override='PERSON BADGE')
        jobs.sent(group,job['id']);jobs.bind(group,job['id'],user_id)
        result=subprocess.run([adapter(),'print',printer_path(),str(image.width),str(image.height)],input=image.tobytes(),capture_output=True,timeout=60,check=True)
        if json.loads(result.stdout).get('status')!='printed':raise OSError('Printer did not confirm completion')
        jobs.record(group,job['id'],'badge_printer_completion',{'badge_id':badge['id']});jobs.complete(group,job['id'])
        return {'id':job['id'],'status':'completed'}
    except Exception:
        if jobs.detail(group,job['id'])['status']=='prepared':jobs.cancel(group,job['id']);raise ValueError('Printer not ready. Check the stock and connection')
        jobs.review(group,job['id'],'Badge output uncertain. Inspect it; never auto-reprint');raise Conflict('Inspect the badge output and review it in Admin')
