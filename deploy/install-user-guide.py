from pathlib import Path
import sys,json
root=Path('/home/user/Desktop/inventory-system');sys.path.insert(0,str(root/'work/hardware/python'))
from playwright.sync_api import sync_playwright
guide=root/'docs/user-guide/index.html'
desktop=Path('/home/user/Desktop')
target=desktop/'Equipment User Guide.html'
target.write_text(guide.read_text().replace('src="images/','src="inventory-system/docs/user-guide/images/'))
launcher=desktop/'Equipment User Guide.desktop'
launcher.write_text('[Desktop Entry]\nType=Application\nName=Equipment User Guide\nComment=Touchscreen and administrator handbook\nExec=xdg-open "/home/user/Desktop/Equipment User Guide.html"\nIcon=help-browser\nTerminal=false\n')
launcher.chmod(0o755)
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1280,'height':900});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(target.as_uri());page.wait_for_load_state('networkidle')
 assert page.locator('section').count()==23
 for img in page.locator('.picture img').all():
  img.scroll_into_view_if_needed();assert img.evaluate('(n)=>n.complete && n.naturalWidth>0')
 assert page.evaluate("[...document.querySelectorAll('nav a')].every(a=>document.querySelector(a.getAttribute('href')))")
 page.locator('#users').click();assert page.locator('section[data-admin="true"]:visible').count()==0
 page.locator('#all').click();assert page.locator('section[data-admin="true"]:visible').count()==11
 page.locator('.picture').first.click();assert page.locator('#viewer').is_visible();page.locator('#close').click();assert not page.locator('#viewer').is_visible()
 page.locator('.picture').first.click();page.keyboard.press('Escape');assert not page.locator('#viewer').is_visible()
 page.evaluate('scrollTo(0,0)');page.screenshot(path=str(root/'docs/user-guide/guide-desktop.png'))
 page.set_viewport_size({'width':800,'height':480});page.evaluate('scrollTo(0,0)');assert page.evaluate('document.documentElement.scrollWidth <= innerWidth');page.screenshot(path=str(root/'docs/user-guide/guide-touch.png'))
 page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
 page.emulate_media(media='print');assert not page.locator('nav').is_visible()
 assert not errors,errors
 browser.close()
result={'chapters':23,'screenshots':len(list((guide.parent/'images').glob('*.png'))),'image_loads':'passed','anchor_links':'passed','audience_filter':'passed','image_zoom_and_escape':'passed','widths_checked':[1280,800,390],'print_style':'passed','page_errors':errors}
(guide.parent/'validation.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
