from pathlib import Path
source=Path('/home/user/Desktop/inventory-system/deploy/verify-workflow-navigation.py').read_text()
base=source.split(' def check(')[0]
base=base.replace("OUTPUT=ROOT/'work/workflow-verification';OUTPUT.mkdir(exist_ok=True)","OUTPUT=ROOT/'docs/user-guide/images';OUTPUT.mkdir(parents=True,exist_ok=True)")
tail='''
 page,state,pending,requests,page_errors,reply=setup()
 def shot(name):
  page.wait_for_load_state('networkidle');page.screenshot(path=str(OUTPUT/(name+'.png')))
 shot('home')
 page.locator('[data-action="Check Out"]').tap();shot('identify')
 page.evaluate("routeScan('BADGE')");page.evaluate("routeScan('TOOL')");page.get_by_role('button',name='Review checkout',exact=True).tap();shot('checkout')
 page.evaluate('checkoutCart=[];checkoutMode=false;home()')
 state['held']=True;page.locator('[data-action="Return"]').tap();page.evaluate("routeScan('TOOL')");page.get_by_role('button',name='Add note',exact=True).tap();shot('return-note')
 page.evaluate("returnCart[0].return_note='Was dirty, but returned clean';renderReturn()");page.get_by_role('button',name='Review return',exact=True).tap();shot('return')
 page.evaluate('returnCart=[];returnMode=false;home()');page.locator('#manual').tap();shot('manual');page.get_by_role('dialog').get_by_role('button',name='Back',exact=True).tap()
 page.locator('#admin').tap();shot('admin')
 page.get_by_role('button',name='Import CSV',exact=True).tap();shot('import-start')
 page.evaluate('importBatch='+json.dumps(batch())+';void importReview(0)');shot('import-review')
 page.evaluate('formDirty=false;home()');page.locator('#storage-nav').tap();shot('storage')
 page.evaluate('detail('+json.dumps(TOOL)+')');state['delay']='/api/history';page.get_by_role('button',name='Activity history',exact=True).tap();page.wait_for_timeout(100)
 reply(pending['/api/history'],[{'action':'return','status':'completed','actor':'Borrower A','created_at':'2026-10-04T22:43:00Z','assets':[TOOL['id']],'asset_names':[TOOL['name']],'return_notes':[{'text':'Was dirty, but returned clean','author':'Borrower A','created_at':'2026-10-04T22:43:00Z'}]}]);page.get_by_text('Was dirty, but returned clean',exact=True).wait_for();shot('history');state['delay']=None
 page.evaluate('formDirty=false;home()');page.locator('[data-action="Workshop"]').tap();page.wait_for_load_state('networkidle');page.evaluate('workshopStart(true);workshopEditing=false;workshopRender()');shot('workshop')
 page.evaluate('workshopDirty=false;formDirty=false;home()');page.locator('#admin').tap();page.get_by_role('button',name='System status & backup',exact=True).tap();shot('system')
 assert not page_errors,page_errors
 browser.close()
print('Guide screenshots captured using intercepted training fixtures; no live mutations.')
'''
exec(compile(base+tail,__file__,'exec'))
