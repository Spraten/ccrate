import json,pathlib,sqlite3,subprocess,sys,urllib.request
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path.insert(0,str(root/'ops'))
from homebox import Homebox
before=json.loads((root/'work/reboot-before.json').read_text());after=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip();assert before['boot_id']!=after,'Pi did not reboot'
for unit in ['homebox-native.service','homebox-companion.service']:assert subprocess.check_output(['systemctl','--user','is-active',unit],text=True).strip()=='active'
client=Homebox(root);assert before['inventory_ids']==sorted(e['id'] for e in client.entities());assert before['location_ids']==sorted(e['id'] for e in client.entities(True))
with sqlite3.connect(root/'work/ops/ledger.db') as db:
    for table,count in before['operational_counts'].items():assert count==db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],table
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
assert json.load(urllib.request.urlopen('http://127.0.0.1:17749/api/session'))['user'] is None
profile=str(root/'work/kiosk-browser');main=[]
for process in pathlib.Path('/proc').glob('[0-9]*'):
    try:
        args=(process/'cmdline').read_bytes().split(b'\0')
        if ('--user-data-dir='+profile).encode() in args and not any(a.startswith(b'--type=') for a in args):main.append(args)
    except OSError:pass
result={'boot_id_changed':True,'native_and_companion_started_at_boot':True,'native_inventory_locations_preserved':True,'operational_counts_preserved':True,'badge_session_cleared':True,'operational_integrity':'ok','dedicated_kiosk_browser_autostarted':bool(main),'fullscreen_launch_flag':bool(main and b'--start-fullscreen' in main[0]),'power_loss_test':'Orderly reboot exercised; no physical power cut performed'}
(root/'docs/reboot-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
