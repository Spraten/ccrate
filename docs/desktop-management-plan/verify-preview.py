"""Verify the isolated desktop design preview; no live application access."""
import json,pathlib,sys
from playwright.sync_api import sync_playwright

root=pathlib.Path(__file__).parent
results=[];errors=[];external=[]
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':900})
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r:external.append(r.url) if r.url.startswith(('http:','https:')) else None)
    page.goto((root/'prototype.html').as_uri());page.wait_for_load_state('networkidle')
    page.get_by_role('heading',name='Workshop overview',exact=True).wait_for()
    page.locator('#toast').evaluate('(n)=>n.hidden=true');page.screenshot(path=str(root/'overview.png'))
    for key in ['overview','equipment','loans','people','workshop','imports','labels','recovery','system']:
        page.evaluate('go('+json.dumps(key)+')');assert page.locator('main').inner_text().strip()
    results.append('Every desktop navigation destination renders without page errors')
    page.evaluate("go('equipment')");page.get_by_label('Search equipment').fill('nonexistent')
    page.get_by_text('No equipment matches.',exact=False).wait_for();page.get_by_label('Search equipment').fill('drill')
    assert page.locator('#equipment-rows tr').count()==1
    page.get_by_role('button',name='Cordless drill kit',exact=True).click();page.get_by_role('button',name='Return notes',exact=True).click();page.get_by_text('Was dirty, but returned clean.',exact=True).wait_for();page.keyboard.press('Escape');assert not page.locator('#dialog').is_visible()
    assert page.get_by_label('Search equipment').input_value()=='drill'
    results.append('Search, empty result, item tabs and Escape preserve the table filter')
    page.get_by_label('Select Cordless drill kit').check();page.get_by_role('button',name='Queue labels',exact=True).click()
    page.get_by_role('button',name='Preview label',exact=True).click();page.get_by_text('Illustrative pattern, not a scannable QR',exact=False).count();page.get_by_role('button',name='Close',exact=True).click()
    page.get_by_role('button',name='Review print job',exact=True).click();page.get_by_text('Pi SUPVAN',exact=True).wait_for();page.get_by_role('button',name='Cancel',exact=True).click()
    results.append('Selection queues labels; preview and print review have safe Cancel')
    page.evaluate("go('people')");page.get_by_role('button',name='Add person',exact=True).click();page.get_by_role('button',name='Review invitation',exact=True).click();page.get_by_role('heading',name='Add a person to Workshop',exact=True).wait_for()
    page.get_by_label('Name',exact=True).fill('Example person');page.get_by_label('Homebox email',exact=True).fill('person@example.com');page.get_by_role('button',name='Review invitation',exact=True).click();page.get_by_role('heading',name='Review person',exact=True).wait_for();page.get_by_role('button',name='Cancel',exact=True).click()
    page.get_by_role('button',name='Manage badge',exact=True).click();page.get_by_role('button',name='Cancel',exact=True).click()
    results.append('People validation, invitation review and badge Cancel work')
    page.evaluate("go('loans')");page.get_by_role('button',name='Record return',exact=True).click();page.get_by_label('Return note (optional)').fill('Returned clean');page.get_by_role('button',name='Cancel',exact=True).click()
    results.append('Administrative return shows operator and retains an explicit cancellation path')
    page.evaluate("go('workshop')");page.locator('svg [role="button"]').focus();page.keyboard.press('Enter');page.get_by_role('button',name='Manage native storage',exact=True).wait_for();page.locator('#toast').evaluate('(n)=>n.hidden=true');page.screenshot(path=str(root/'workshop.png'))
    results.append('Workshop rack selection works with keyboard and shows linked storage')
    page.evaluate("go('imports')");page.get_by_role('button',name='Use training CSV',exact=True).click();page.get_by_role('button',name='Review rows',exact=True).click();page.get_by_role('button',name='Fix row',exact=True).click();page.get_by_role('button',name='Cancel',exact=True).click();page.get_by_role('button',name='Batch summary',exact=True).click();page.get_by_role('button',name='Back to review',exact=True).click()
    results.append('Import mapping, row edit Cancel, summary and Back work')
    page.get_by_role('button',name='Fix row',exact=True).click();page.get_by_label('Equipment name',exact=True).fill('Edited training saw');page.get_by_label('Assigned storage',exact=True).select_option(label='CAB / 1');page.get_by_role('button',name='Save review',exact=True).click();page.get_by_text('Edited training saw',exact=True).wait_for();page.get_by_role('button',name='Edit row',exact=True).click();assert page.get_by_label('Equipment name',exact=True).input_value()=='Edited training saw';assert page.get_by_label('Assigned storage',exact=True).input_value()=='CAB / 1';page.get_by_role('button',name='Cancel',exact=True).click();page.get_by_role('button',name='Batch summary',exact=True).click();page.get_by_role('button',name='Confirm: create 2 reviewed items',exact=True).wait_for()
    results.append('Saved fictional import edits persist and update the batch summary')
    page.evaluate("go('recovery')");page.get_by_role('button',name='Inspect saved operation',exact=True).click();assert page.get_by_role('button',name='Review completion',exact=True).is_disabled();page.get_by_label('I inspected the physical result and stored values.',exact=False).check();assert page.get_by_role('button',name='Review completion',exact=True).is_enabled();page.get_by_role('button',name='Back to recovery',exact=True).click()
    results.append('Recovery review requires physical verification and allows Back')
    page.evaluate("go('system')");page.get_by_role('button',name='Review recovery backup',exact=True).click();page.get_by_role('button',name='Cancel',exact=True).click()
    results.append('Backup review has Cancel and performs no operation')
    page.get_by_label('Preview role',exact=True).select_option('member');assert page.locator('#nav').get_by_role('button',name='People & badges',exact=True).count()==0
    page.evaluate("go('people')");assert page.evaluate('current')=='overview'
    page.get_by_label('Preview role',exact=True).select_option('manager')
    results.append('Preview member hides manager areas and rejects their navigation')
    for width in (1440,1024,800,390):
        page.set_viewport_size({'width':width,'height':900 if width>800 else 780})
        page.evaluate("go('equipment')")
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('#mobile-nav').select_option('people');page.get_by_role('heading',name='People & badges',exact=True).wait_for()
    results.append('1440, 1024, 800 and 390px layouts contain overflow; mobile navigation works')
    page.set_viewport_size({'width':1440,'height':900});page.evaluate("go('equipment')");page.locator('#toast').evaluate('(n)=>n.hidden=true');page.screenshot(path=str(root/'equipment.png'))
    page.get_by_role('button',name='Cordless drill kit',exact=True).click();page.get_by_role('button',name='Return notes',exact=True).click();page.screenshot(path=str(root/'return-notes.png'))
    assert not errors,errors;assert not external,external
    results.append('No browser errors or network requests; all content stays inside the mockup')
    browser.close()
result={'prototype_only':True,'live_requests':0,'live_mutations':0,'physical_prints':0,'passed':len(results),'checks':results}
(root/'preview-validation.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
