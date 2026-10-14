"""Native QR label previews and one-shot USB printing with durable outcomes."""
import io,base64,json,pathlib,subprocess,hashlib,os,re
import qrcode
from PIL import Image,ImageDraw,ImageFont
from ledger import Conflict,uuid
ROOT=pathlib.Path(os.environ.get('WORKSHOP_ROOT','/home/user/Desktop/inventory-system'))
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
def _fit_name_lines(content,draw,name_font,available,max_lines):
    measure=lambda text:draw.textbbox((0,0),text,font=name_font)[2]
    lines=[]
    for paragraph in re.split(r'\r\n?|\n',content):
        if paragraph=='':
            lines.append('');continue
        current=''
        for word in paragraph.split(' '):
            candidate=word if current=='' else current+' '+word
            if measure(candidate)<=available:
                current=candidate;continue
            if current:lines.append(current)
            if measure(word)<=available:
                current=word;continue
            chunk=''
            for character in word:
                if chunk and measure(chunk+character)>available:
                    lines.append(chunk);chunk=character
                else:chunk+=character
            current=chunk
        lines.append(current)
    if len(lines)>max_lines:
        lines=lines[:max_lines];characters=list(lines[-1])
        while characters and measure(''.join(characters)+'…')>available:characters.pop()
        if measure('…')>available:return []
        lines[-1]=''.join(characters)+'…'
    return lines
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
    max_lines=max(1,(height-74-top)//22)
    name_font=font(18);lines=_fit_name_lines(entity['name'],draw,name_font,available,max_lines)
    for line in lines[:max_lines]:
        if line:draw.text((left,top),line,font=name_font,fill=0)
        top+=22
    identifier=entity.get('assetId','');identifier_font=font(17)
    while identifier and draw.textbbox((0,0),identifier,font=identifier_font)[2]>available:identifier=identifier[:-1]
    draw.text((left,height-56),identifier,font=identifier_font,fill=0)
    draw.text((left,height-32),'C-Crate',font=font(13),fill=0)
    return image,code
def preview(client,entity_id,*,layouts=None,group=None,actor=None,template_id=None,template_revision=None):
    if layouts is not None:
        return layouts.preview(client,group,actor,{'mode':'item','entity_id':entity_id,'template_id':template_id,'template_revision':template_revision})
    entity=client.entity(uuid(entity_id));image,code=render(entity);stream=io.BytesIO();image.save(stream,format='PNG')
    return {'entity_id':entity['id'],'name':entity['name'],'code':code,'width':image.width,'height':image.height,'image':'data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode()}
def print_label(client,jobs,group,actor,key,entity_id,*,layouts=None,review_id=None,valid_context=None):
    entity_id=uuid(entity_id)
    if layouts is None:
        entity=client.entity(entity_id)
        if not (entity.get('isLocation') or (entity.get('entityType') or {}).get('isLocation')):raise ValueError('Select and review a saved label template before printing')
        job=jobs.prepare(group,actor,'print_label',key,{'entity_id':entity_id})
        if job['status']=='completed':return {'id':job['id'],'status':'completed','entity_id':entity_id}
        if job['status']!='prepared':raise Conflict('Printer outcome needs Admin review. Do not retry automatically')
        try:
            material=probe();image,_=render(entity,material['width_mm'],material['height_mm']);jobs.sent(group,job['id']);jobs.bind(group,job['id'],entity_id)
            result=subprocess.run([adapter(),'print',printer_path(),str(image.width),str(image.height)],input=image.tobytes(),capture_output=True,timeout=60,check=True)
            if json.loads(result.stdout).get('status')!='printed':raise OSError('Printer did not confirm completion')
            jobs.record(group,job['id'],'printer_completion',{'entity_id':entity_id});jobs.complete(group,job['id'])
            return {'id':job['id'],'status':'completed','entity_id':entity_id}
        except Exception:
            if jobs.detail(group,job['id'])['status']=='prepared':jobs.cancel(group,job['id']);raise ValueError('Printer not ready. Check connection and loaded stock')
            jobs.review(group,job['id'],'Printer outcome uncertain. Inspect the label; never auto-reprint');raise Conflict('Printing outcome is uncertain. Inspect the label and review in Admin')
    if review_id is None:raise ValueError('Select and review a saved label template before printing')
    review_id=uuid(review_id)
    with jobs.ledger.connection() as db:
        prior=db.execute('SELECT id,status FROM native_jobs WHERE group_id=? AND request_key=?',(uuid(group),uuid(key))).fetchone()
    job=jobs.prepare(group,actor,'print_label',key,{'entity_id':entity_id,'review_id':review_id})
    if job['status']=='completed':
        try:layouts.resolve_review(group,review_id)
        except Exception:pass
        return {'id':job['id'],'status':'completed','entity_id':job['result_id']}
    if job['status']!='prepared':raise Conflict('Printer outcome needs inspection. Do not retry automatically')
    if prior:raise Conflict('This print was prepared earlier and may have stopped before confirmation. Cancel it in Recovery and review the item again before printing')
    ticket=None;attached=False
    try:
        if hasattr(layouts,'reconcile_reviews'):layouts.reconcile_reviews(group,jobs)
        if job['payload']!={'entity_id':entity_id,'review_id':review_id}:raise Conflict('Prepared print has no matching saved review; cancel it in Recovery before starting a new print')
        for pending in jobs.unresolved(group):
            if pending['id']==job['id']:continue
            payload=pending['payload'] or {}
            if pending['kind']=='print_label' and (payload.get('entity_id')==entity_id or pending.get('result_id')==entity_id):raise Conflict('This item has an unconfirmed print. Inspect its output and finish Recovery before printing another copy')
        ticket=layouts.review(group,actor,review_id)
        if not ticket or ticket['item_id']!=entity_id:raise ValueError('Reviewed label is missing, expired, or belongs to another item')
        if ticket.get('attached_job') not in (None,job['id']):raise Conflict('Reviewed label is already attached to another print')
        template=layouts.get(group,ticket['template_id'])
        if template['revision']!=ticket['template_revision'] or hashlib.sha256(json.dumps(template['document'],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()!=ticket['template_hash']:raise Conflict('Saved template changed; review the label again')
        entity=client.entity(entity_id)
        if entity.get('updatedAt')!=ticket['item_updated_at'] or entity.get('displayId')!=ticket.get('item_display_id') or entity.get('archived'):raise Conflict('Item or storage path changed since review; preview it again')
        material=probe()
        if (material.get('width_mm'),material.get('height_mm'))!=(40,30):raise ValueError('Load the required 40 x 30 mm SUPVAN stock')
        with Image.open(io.BytesIO(ticket['png'])) as image_file:
            image_file.load()
            if image_file.mode!='L' or image_file.size!=(ticket['width'],ticket['height']):raise ValueError('Reviewed label raster is invalid')
            frozen=image_file.copy()
        if hashlib.sha256(ticket['png']).hexdigest()!=ticket['sha256']:raise ValueError('Reviewed label raster failed its integrity check')
        if valid_context and not valid_context():raise Conflict('Label manager or session changed; review the item again')
        layouts.attach_review(group,actor,review_id,job['id']);attached=True
        metadata={key:ticket[key] for key in ('review_id','template_id','template_revision','template_hash','sha256','profile','label_mm','dpi','width','height')}
        if valid_context and not valid_context():raise Conflict('Label manager or session changed; review the item again')
        jobs.sent_print(group,job['id'],entity_id,metadata)
        result=subprocess.run([adapter(),'print',printer_path(),str(frozen.width),str(frozen.height)],input=frozen.tobytes(),capture_output=True,timeout=60,check=True)
        if json.loads(result.stdout).get('status')!='printed':raise OSError('Printer did not confirm completion')
        jobs.record(group,job['id'],'printer_completion',{'entity_id':entity_id});jobs.complete(group,job['id']);layouts.resolve_review(group,review_id)
        return {'id':job['id'],'status':'completed','entity_id':entity_id}
    except Exception:
        state=jobs.detail(group,job['id'])['status']
        if state=='completed':return {'id':job['id'],'status':'completed','entity_id':entity_id}
        if state=='prepared':
            jobs.cancel(group,job['id'])
            if attached and ticket and ticket.get('actor_id')==uuid(actor) and ticket.get('attached_job') in (None,job['id']):
                try:layouts.resolve_review(group,review_id)
                except Exception:pass
            raise
        jobs.review(group,job['id'],'Printer outcome uncertain. Inspect the label; never auto-reprint')
        raise Conflict('Printing outcome is uncertain. Inspect the label and review in Admin')

def recover_print(client,jobs,group,job_id,outcome,*,layouts=None):
    job=jobs.detail(group,job_id)
    job_id=job['id']
    if job['kind'] not in ('print_label','print_badge'):raise ValueError('Not a printer job')
    if outcome=='cancel':
        with jobs.ledger.connection() as db:started=db.execute("SELECT 1 FROM native_job_events WHERE job_id=? AND kind='native_write_started'",(job_id,)).fetchone()
        if job['status']!='prepared' or started:raise Conflict('A started or already linked print requires inspection; it cannot be cancelled as unsent')
        payload=job['payload'] or {};review_id=payload.get('review_id')
        ticket=layouts.review(group,job['actor_id'],review_id) if layouts and job['kind']=='print_label' and review_id else None
        owned_attachment=ticket and ticket.get('attached_job')==job_id and ticket.get('actor_id')==job['actor_id']
        jobs.cancel(group,job_id)
        if owned_attachment:
            try:layouts.resolve_review(group,review_id)
            except Exception:pass
        return {'id':job_id,'status':'cancelled'}
    if outcome!='complete':raise Conflict('Inspect the printer output. Finishing acknowledges it; reprint is a separate explicit action')
    if job['kind']=='print_label' and job['status'] in ('sent','review') and not job['result_id']:
        entity_id=(job['payload'] or {}).get('entity_id')
        if not entity_id:raise Conflict('Legacy print has no strict saved item ID to bind; keep it for inspection')
        jobs.bind(group,job_id,entity_id);job=jobs.detail(group,job_id)
    if job['status']!='completed':jobs.record(group,job_id,'physical_output_acknowledged',{});jobs.complete(group,job_id)
    if layouts and job['kind']=='print_label':
        review=(job['payload'] or {}).get('review_id')
        if not review:
            with jobs.ledger.connection() as db:
                row=db.execute("SELECT detail FROM native_job_events WHERE job_id=? AND kind='print_reviewed' ORDER BY rowid DESC LIMIT 1",(job_id,)).fetchone()
                review=json.loads(row['detail']).get('review_id') if row else None
        if review:
            try:layouts.resolve_review(group,review)
            except Exception:pass
    return {'id':job_id,'status':'completed','entity_id':job['result_id']}

def paper(client,layouts,group,actor,data,*,deadline=None):
    import time,label_render
    deadline=deadline or time.monotonic()+20;ids=data.get('review_ids');geometry=data.get('geometry')
    if not isinstance(ids,list) or not 1<=len(ids)<=36 or not isinstance(geometry,dict):raise ValueError('Select 1 to 36 reviewed labels and provide sheet geometry')
    frozen=[]
    for review_id in ids:
        if time.monotonic()>=deadline:raise TimeoutError('Paper preview exceeded the request budget; select fewer items')
        ticket=layouts.review(group,actor,review_id)
        if not ticket:raise Conflict('A reviewed label is missing or expired; review the items again')
        if time.time()-ticket.get('created',0)>86400:raise Conflict('A reviewed label has expired; review the items again')
        old_timeout=getattr(client,'timeout',None)
        if old_timeout is not None:client.timeout=min(old_timeout,max(.001,deadline-time.monotonic()))
        try:entity=client.entity(ticket['item_id'])
        finally:
            if old_timeout is not None:client.timeout=old_timeout
        if entity.get('updatedAt')!=ticket['item_updated_at'] or entity.get('displayId')!=ticket.get('item_display_id') or entity.get('archived'):raise Conflict('An item or storage path changed since review; preview the items again')
        template=layouts.get(group,ticket['template_id'])
        if template['revision']!=ticket['template_revision'] or hashlib.sha256(json.dumps(template['document'],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()!=ticket['template_hash']:raise Conflict('A saved template changed since review')
        if geometry.get('label_mm')!=ticket['label_mm'] or ticket['profile']!='letter' or ticket['dpi']!=300:raise ValueError('Paper geometry must match Letter reviewed labels')
        frozen.append(ticket)
    if time.monotonic()>=deadline:raise TimeoutError('Paper preview exceeded the request budget; select fewer items')
    result=label_render.render_paper_sheet(frozen,geometry,asset_root=layouts.asset_root,timeout=max(.001,deadline-time.monotonic()))
    if time.monotonic()>=deadline:raise TimeoutError('Paper preview exceeded the request budget; select fewer items')
    return result

def reprint_badge(client,badges,jobs,group,actor,key,badge_id):
    members=client.call('/api/v1/groups/members')
    code=badges.print_code(group,badge_id,[member['id'] for member in members])
    return print_badge(client,badges,jobs,group,actor,key,badge_id,code)

def print_badge(client,badges,jobs,group,actor,key,badge_id,code):
    members=client.call('/api/v1/groups/members');user_id=badges.resolve(group,code,[m['id'] for m in members])
    badge=next((b for b in badges.list(group) if b['id']==uuid(badge_id) and not b['revoked']),None)
    if not user_id or not badge or badge['user_id']!=user_id:raise ValueError('Badge is revoked or does not match this native member')
    for pending in jobs.unresolved(group):
        if pending['kind']=='print_badge' and (pending['payload'] or {}).get('badge_id')==badge['id']:
            raise Conflict('This badge has an unconfirmed print. Inspect its output and finish Recovery before printing another copy')
    name=next(m['name'] for m in members if m['id']==user_id)
    # The print journal stores only a hash; the QR raster stays in memory.
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
