import pathlib,sys,json,sqlite3,time
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path.insert(0,str(root/'ops'));sys.path.insert(0,str(root/'work/hardware/python'))
from homebox import Homebox
from playwright.sync_api import sync_playwright
c=Homebox(root);account=c.call('/api/v1/users/self')['item'];members=c.call('/api/v1/groups/members');assert len(members)==1 and members[0]['id']==account['id']
c.call('/api/v1/users/self','PUT',{'name':'Workshop Admin','email':account['email']});assert c.call('/api/v1/users/self')['item']['name']=='Workshop Admin'
assert not c.entities() and not c.entities(True) and not c.call('/api/v1/templates') and not c.call('/api/v1/tags')
assert len(c.call('/api/v1/entity-types'))==2
with sqlite3.connect(root/'work/ops/ledger.db') as db:
    for table in ('operations','native_jobs','badges','custody'):assert db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
with sqlite3.connect(root/'work/ops/imports.db') as db:assert db.execute('SELECT COUNT(*) FROM batches').fetchone()[0]==0
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);page=browser.new_page(viewport={'width':800,'height':480},has_touch=True);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:17749');page.get_by_text('Homebox connected · 0 assets',exact=True).wait_for();page.screenshot(path=str(root/'work/clean-home-screen.png'));page.get_by_role('button',name='Workshop Explore locations and equipment',exact=True).tap();page.get_by_role('button',name='Add workshop locations',exact=True).wait_for();page.get_by_role('button',name='Add workshop locations',exact=True).tap();page.get_by_role('button',name='Create location',exact=True).wait_for();assert not errors;browser.close()
audit=root/'work/demo-cleanup.json';state=json.loads(audit.read_text());archive=sorted((root/'work/demo-archive').iterdir())[-1]
with sqlite3.connect(archive/'ledger.db') as db:counts={t:db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('operations','native_jobs','badges')}
state.update(status='completed',finished_at=time.time(),archived_test_history=counts,private_archive=str(archive.relative_to(root)),remaining_equipment=0,remaining_locations=0);audit.write_text(json.dumps(state));audit.chmod(0o600)
print(json.dumps({'removed_native_records':len(state['plan']['entities']),'remaining_equipment':0,'remaining_locations':0,'catalog_and_tags_empty':True,'only_workshop_admin':True,'clean_ledger_and_imports':True,'empty_workshop_setup_works':True,'browser_errors':errors}))
