import hashlib,json,pathlib,sqlite3,sys
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path.insert(0,str(root/'ops'))
from homebox import Homebox
client=Homebox(root)
def ids(locations=False):return sorted(e['id'] for e in client.entities(locations))
with sqlite3.connect(root/'work/ops/ledger.db') as db:
    counts={table:db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ['operations','events','custody','badges','native_jobs','native_job_events']}
    assert counts['custody']==0,'Return test custody before reboot'
    assert db.execute("SELECT COUNT(*) FROM operations WHERE status IN ('pending','review')").fetchone()[0]==0
    assert db.execute("SELECT COUNT(*) FROM native_jobs WHERE status IN ('prepared','sent','review')").fetchone()[0]==0
state={'boot_id':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'inventory_ids':ids(),'location_ids':ids(True),'operational_counts':counts}
(root/'work/reboot-before.json').write_text(json.dumps(state));print('Reboot baseline saved; no unresolved work or test custody')
