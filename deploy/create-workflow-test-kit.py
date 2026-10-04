"""User-requested test fixtures only; never retry uncertain native writes."""
import pathlib,sys,json,secrets,base64,urllib.request,uuid,io
root=pathlib.Path('/home/user/Desktop/inventory-system')
sys.path[:0]=[str(root/'ops'),str(root/'work/hardware/python'),str(root/'kiosk')]
from homebox import Homebox
from native_jobs import NativeJobs
from ledger import Ledger
from setup_native import submit
from PIL import Image,ImageDraw,ImageFont
import qrcode,zxingcpp
out=root/'work/workflow-test-kit';out.mkdir(exist_ok=True);out.chmod(0o700)
state_path=out/'state.json'
if state_path.exists():raise SystemExit('Test kit already started. Inspect state; do not automatically recreate it.')
state={'location_key':str(uuid.uuid4()),'asset_key':str(uuid.uuid4())}
def save():state_path.write_text(json.dumps(state));state_path.chmod(0o600)
save()
base='http://127.0.0.1:17749'
def post(path,data):
    request=urllib.request.Request(base+path,data=json.dumps(data).encode(),headers={'Content-Type':'application/json','Origin':base})
    with urllib.request.urlopen(request,timeout=60) as response:return json.load(response)
client=Homebox(root)
member=post('/accounts/create',{'name':'Workflow Test User','email':'workflow-test@example.invalid','password':secrets.token_urlsafe(32)})['user']
state['user_id']=member['id'];save()
badge=post('/badge/issue',{'user_id':member['id']});state['badge_id']=badge['id'];save()
badge_image=Image.open(io.BytesIO(base64.b64decode(badge['qr'].split(',')[1]))).convert('RGB')
badge_image.save(out/'test-badge.png')
assert zxingcpp.read_barcodes(badge_image)[0].text==badge['code']
native=client.call('/api/v1/users/self')['item']
jobs=NativeJobs(Ledger(root/'work/ops/ledger.db'))
location=submit(client,jobs,native['defaultGroupId'],member['id'],'create_location',state['location_key'],{'name':'TEST – Workflow shelf','description':'Temporary user-requested workflow test location.','storage_kind':'Shelf','storage_code':'TEST'})
state['location_id']=location['entity_id'];save()
asset=submit(client,jobs,native['defaultGroupId'],member['id'],'create_asset',state['asset_key'],{'name':'TEST – QR Tool','description':'Fictional fixture for checkout and return testing; not real equipment.','serial':'WORKFLOW-QR-001','location_id':state['location_id'],'reviewed':True})
state['entity_id']=asset['entity_id'];save()
label=post('/label/preview',{'entity_id':state['entity_id']})
Image.open(io.BytesIO(base64.b64decode(label['image'].split(',')[1]))).save(out/'test-item-label.png')
item_qr=qrcode.make(label['code']);item_qr.save(out/'test-item-qr.png')
assert zxingcpp.read_barcodes(item_qr.convert('RGB'))[0].text==label['code']
(out/'test-import.csv').write_text('Name,Serial,ID,Description,Condition\nTEST - Imported Tool,WORKFLOW-IMPORT-001,WORKFLOW-IMPORT-001,Fictional item for the import wizard,Unreviewed\n')
(out/'manual-codes.txt').write_text('Badge (Workflow Test User):\n'+badge['code']+'\n\nItem (TEST - QR Tool):\n'+label['code']+'\n')
width=1100;sheet=Image.new('RGB',(width,780),'white');draw=ImageDraw.Draw(sheet)
font='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
draw.text((45,25),'Workflow test kit',fill='#203448',font=ImageFont.truetype(font,36))
draw.text((45,85),'1. Scan badge',fill='#203448',font=ImageFont.truetype(font,25))
draw.text((600,85),'2. Scan equipment',fill='#203448',font=ImageFont.truetype(font,25))
sheet.paste(badge_image.resize((420,420),Image.Resampling.NEAREST),(45,130))
sheet.paste(item_qr.convert('RGB').resize((420,420),Image.Resampling.NEAREST),(600,130))
draw.text((45,570),'Workflow Test User',fill='#203448',font=ImageFont.truetype(font,24))
draw.text((600,570),'TEST - QR Tool',fill='#203448',font=ImageFont.truetype(font,24))
for y,line in enumerate(['Checkout: scan badge, scan tool, confirm.','Return: scan badge again, scan tool, confirm.','Import CSV separately: Admin > Import CSV > select TEST shelf.']):
    draw.text((45,635+y*37),line,fill='#203448',font=ImageFont.truetype(font,22))
sheet.save(out/'workflow-test-sheet.png')
state['complete']=True;save()
print(json.dumps({'created_test_member':True,'created_test_shelf':True,'created_ready_test_item':True,'badge_and_item_qr_decode_verified':True,'download_files':['test-badge.png','test-item-qr.png','test-item-label.png','test-import.csv','manual-codes.txt','workflow-test-sheet.png']}))
