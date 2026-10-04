import pathlib,sys,json,io
root=pathlib.Path('/home/user/Desktop/inventory-system')
sys.path.insert(0,str(root/'work/hardware/python'))
from PIL import Image,ImageDraw,ImageFont
import zxingcpp
out=root/'work/workflow-test-kit'
state=json.loads((out/'state.json').read_text())
badge_image=Image.open(out/'test-badge.png').convert('RGB')
item_qr=Image.open(out/'test-item-qr.png').convert('RGB')
badge_code=zxingcpp.read_barcodes(badge_image)[0].text
item_code=zxingcpp.read_barcodes(item_qr)[0].text
assert item_code=='/item/'+state['entity_id']
(out/'test-import.csv').write_text('Name,Serial,ID,Description,Condition\nTEST - Imported Tool,WORKFLOW-IMPORT-001,WORKFLOW-IMPORT-001,Fictional item for the import wizard,Unreviewed\n')
(out/'manual-codes.txt').write_text('Badge (Workflow Test User):\n'+badge_code+'\n\nItem (TEST - QR Tool):\n'+item_code+'\n')
sheet=Image.new('RGB',(1100,780),'white');draw=ImageDraw.Draw(sheet)
font='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
draw.text((45,25),'Workflow test kit',fill='#203448',font=ImageFont.truetype(font,36))
for x,title,name,image in [(45,'1. Scan badge','Workflow Test User',badge_image),(600,'2. Scan equipment','TEST - QR Tool',item_qr)]:
    draw.text((x,85),title,fill='#203448',font=ImageFont.truetype(font,25))
    sheet.paste(image.resize((420,420),Image.Resampling.NEAREST),(x,130))
    draw.text((x,570),name,fill='#203448',font=ImageFont.truetype(font,24))
for y,line in enumerate(['Checkout: scan badge, scan tool, confirm.','Return: scan badge again, scan tool, confirm.','Import CSV separately: Admin > Import CSV > select TEST shelf.']):
    draw.text((45,635+y*37),line,fill='#203448',font=ImageFont.truetype(font,22))
sheet.save(out/'workflow-test-sheet.png');state['complete']=True
(out/'state.json').write_text(json.dumps(state))
print('Test kit complete. Both QR codes decode correctly; no native writes repeated.')
