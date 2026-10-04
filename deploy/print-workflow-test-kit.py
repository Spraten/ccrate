"""Print the user-requested badge and tool once, retaining request keys."""
import pathlib,sys,json,urllib.request,uuid
root=pathlib.Path('/home/user/Desktop/inventory-system')
sys.path.insert(0,str(root/'work/hardware/python'))
from PIL import Image
import zxingcpp
out=root/'work/workflow-test-kit';path=out/'print-state.json'
if path.exists():raise SystemExit('Print attempt already exists. Inspect its durable job outcomes before any reprint.')
state={'badge_key':str(uuid.uuid4()),'item_key':str(uuid.uuid4())}
def save():path.write_text(json.dumps(state));path.chmod(0o600)
save()
kit=json.loads((out/'state.json').read_text())
code=zxingcpp.read_barcodes(Image.open(out/'test-badge.png'))[0].text
def post(route,data):
    req=urllib.request.Request('http://127.0.0.1:17749'+route,data=json.dumps(data).encode(),headers={'Content-Type':'application/json','Origin':'http://127.0.0.1:17749'})
    with urllib.request.urlopen(req,timeout=90) as response:return json.load(response)
try:
    state['badge']=post('/badge/print',{'badge_id':kit['badge_id'],'code':code,'request_key':state['badge_key']});save()
    print('Badge: '+state['badge']['status'],flush=True)
    state['item']=post('/label/print',{'entity_id':kit['entity_id'],'request_key':state['item_key']});save()
    print('Equipment label: '+state['item']['status'],flush=True)
except Exception as error:
    state['stopped']=True;save()
    if isinstance(error,urllib.error.HTTPError):print('Printing stopped: '+error.read().decode(),flush=True)
    else:print('Printing stopped; check durable Admin recovery before reprinting.',flush=True)
    raise SystemExit(1)
