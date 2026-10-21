#!/usr/bin/env python3
"""Headless synthetic acceptance check for the shared touchscreen page.

Uses only Python's standard library and the system Chromium executable. The
fixture intercepts every fetch in page JavaScript and never contacts Homebox.
Screenshots and browser profiles are written under /tmp.
"""
import json
import html
import pathlib
import sys
import signal
import shutil
import subprocess
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
CHROMIUM = shutil.which('chromium') or shutil.which('chromium-browser') or shutil.which('google-chrome')
LONG_NAME = 'TEST DJI Mavic 3 Classic Enterprise Thermal Survey Kit with extended descriptive title'
ITEM = {'id': '10000000-0000-4000-8000-000000000001', 'name': LONG_NAME,
        'assetId': 'DRONE-3C-1', 'quantity': 1, 'archived': False,
        'condition': 'Ready', 'parent': {'name': 'Lab / D Wing / G38'},
        'entityType': {'isLocation': False}}
MEMBER = {'id': '20000000-0000-4000-8000-000000000001', 'name': 'Synthetic Test Member'}


BOOTSTRAP = r"""<script>
(() => {
 const item=__ITEM__, member=__MEMBER__; let active=false;
 window.setInterval=()=>0;
 const json=(data,status=200)=>Promise.resolve(new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}}));
 window.fetch=async (input,options={})=>{
   const url=new URL(typeof input==='string'?input:input.url,location.href), path=url.pathname;
   const body=options.body?JSON.parse(options.body):{};
   if(path==='/api/session')return json({user:active?member:null,generation:active?1:null,instance:active?'synthetic-session':null});
   if(path==='/scan') { if(body.code==='SYNTHETIC-BADGE'){active=true;return json({kind:'user',user:member,generation:1,instance:'synthetic-session'});} if(body.code==='SYNTHETIC-ITEM')return json({kind:'entity',entity:item}); return json({kind:'unknown',reason:'Unknown synthetic code'},404); }
   if(path==='/session/activity')return json({active});
   if(path==='/session/end'){active=false;return json({status:'completed'});}
   if(path==='/api/inventory')return json([item]);
   if(path==='/api/kit')return json({kit:false});
   if(path==='/checkout/cart')return json({revision:0,items:[],notes:{}});
   if(path==='/checkout/availability')return json([{id:item.id,reason:null}]);
   if(path==='/return/availability')return json({items:[{id:item.id,eligible:true,reason:null,condition:'Ready',location:{id:'loc-1',name:'Lab / D Wing / G38'}}]});
   if(path==='/checkout/confirm')return json({id:'SYNTHETIC-CHECKOUT-RECEIPT',count:1,status:'completed'});
   if(path==='/return/confirm')return json({id:'SYNTHETIC-RETURN-RECEIPT',count:1,status:'completed'});
   if(path==='/operation/status')return json({status:'completed',id:'SYNTHETIC-RECOVERED-RECEIPT',count:1});
   return json({error:'Unexpected synthetic route '+path},404);
 };
 window.__fixtureRequests=[];
 const original=window.fetch;
 window.fetch=async (...args)=>{const url=new URL(typeof args[0]==='string'?args[0]:args[0].url,location.href);window.__fixtureRequests.push({path:url.pathname,method:args[1]?.method||'GET'});return original(...args)};
 const wait=async fn=>{for(let i=0;i<100;i++){if(fn())return;await new Promise(r=>setTimeout(r,20));}throw Error('Timed out waiting for '+fn.toString())};
 const click=async selector=>{await wait(()=>document.querySelector(selector));document.querySelector(selector).click();await new Promise(r=>setTimeout(r,40));};
 const fill=async (selector,value)=>{await wait(()=>document.querySelector(selector));const el=document.querySelector(selector);el.value=value;el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));};
 const run=async()=>{try{
   const flow=new URLSearchParams(location.search).get('flow'),stage=new URLSearchParams(location.search).get('stage')||'receipt';
   await click(`[data-flow="${flow}"]`); document.body.dataset.step='flow-selected';
   if(getComputedStyle(document.querySelector('#home')).display!=='none'||document.querySelector('#flow').hidden)throw Error('Flow navigation did not hide the home menu');
   await fill('#badge-code','SYNTHETIC-BADGE');document.querySelector('#badge-form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await wait(()=>window.checkoutSession?.generation===1);document.body.dataset.step='badge-accepted';
   const search=flow==='checkout'?'#checkout-ui input[aria-label="Search inventory"]':'#return-ui input[placeholder="Search by name or ID"]';
   await fill(search,'Mavic');await wait(()=>[...document.querySelectorAll('#checkout-ui button,#return-ui button')].some(b=>b.textContent.includes('Mavic')));document.body.dataset.step='search-result';
   const candidate=[...document.querySelectorAll('#checkout-ui button,#return-ui button')].find(b=>b.textContent.includes('Mavic'));
   if(!candidate)throw Error('Search suggestion was not rendered');candidate.click();await new Promise(r=>setTimeout(r,40));
   const scan=flow==='checkout'?'#checkout-ui input[aria-label="Scan item barcode"]':'#return-ui input[placeholder="Scan item barcode"]';await fill(scan,'SYNTHETIC-ITEM');
   if(flow==='checkout')document.querySelector('#checkout-ui form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));else {const add=[...document.querySelectorAll('#return-ui button')].find(b=>b.textContent==='Verify scan and add');if(!add)throw Error('Scan button missing');add.click();}
   await wait(()=>document.querySelector('#'+flow+'-ui article'));
   const note=document.querySelector(flow==='checkout'?'#checkout-ui article input':'#return-ui article input[placeholder="Optional return note"]');
   if(note){note.value='Synthetic per-item handling note';note.dispatchEvent(new Event('input',{bubbles:true}));}
   const review=[...document.querySelectorAll('#'+flow+'-ui button')].find(b=>b.textContent==='Review '+(flow==='checkout'?'checkout':'return'));
   if(!review)throw Error('Review action missing');review.click();await new Promise(r=>setTimeout(r,180));
   await wait(()=>[...document.querySelectorAll('#'+flow+'-ui button')].some(b=>b.textContent==='Confirm '+(flow==='checkout'?'checkout':'return')&&!b.disabled));
   const overflow=document.documentElement.scrollWidth>document.documentElement.clientWidth;
   const shortButtons=[...document.querySelectorAll('button')].filter(b=>{const r=b.getBoundingClientRect();return r.width>0&&r.height<44;}).map(b=>b.textContent.trim());
   const manager=/(manager|settings|workshop|badge administration|inventory edit)/i.test(document.body.innerText);
   const reviewData={stage:'review',flow,overflow,shortButtons,manager,scrollWidth:document.documentElement.scrollWidth,clientWidth:document.documentElement.clientWidth,
     longNameVisible:document.body.innerText.includes(item.name),noteVisible:[...document.querySelectorAll('#'+flow+'-ui input')].some(i=>i.value==='Synthetic per-item handling note'),locationVisible:document.body.innerText.includes('Lab / D Wing / G38'),
     conditionVisible:flow==='return'?document.body.innerText.includes('Recorded condition: Ready'):true,
     blockerVisible:document.body.innerText.includes('Blocked:')};
   if(stage==='review'){document.body.dataset.result=JSON.stringify(reviewData);return;}
   const confirm=[...document.querySelectorAll('#'+flow+'-ui button')].find(b=>b.textContent==='Confirm '+(flow==='checkout'?'checkout':'return'));
   if(confirm.disabled)throw Error('Confirm remains disabled after complete review');confirm.click();await wait(()=>document.body.innerText.includes(flow==='checkout'?'Checkout complete':'Return complete'));
   const receipt={...reviewData,stage:'receipt',receiptVisible:true,confirmRequests:window.__fixtureRequests.filter(x=>x.path==='/'+flow+'/confirm').length};
   document.body.dataset.result=JSON.stringify(receipt);
 }catch(e){document.body.dataset.error=String(e.stack||e);}};
 window.addEventListener('load',()=>setTimeout(run,40));
})();
</script>"""


class BrowserUnavailable(RuntimeError):
    pass


def fixture_html():
    body = (ROOT / 'kiosk/touchscreen.html').read_text(encoding='utf-8')
    css = (ROOT / 'kiosk/touchscreen.css').read_text(encoding='utf-8')
    body = body.replace('<link rel="stylesheet" href="/touchscreen.css">', '<style>' + css + '</style>')
    injection = BOOTSTRAP.replace('__ITEM__', json.dumps(ITEM)).replace('__MEMBER__', json.dumps(MEMBER))
    body = body.replace('<script src="/checkout-ui.js" defer></script>', injection)
    for asset in ('checkout-ui.js', 'return-ui.js', 'touchscreen.js'):
        source = (ROOT / 'kiosk' / asset).read_text(encoding='utf-8')
        body = body.replace(f'<script src="/{asset}" defer></script>', '<script>' + source + '</script>')
    # file:// has inconsistent localStorage implementations across Chromium builds.
    shim = "<script>Object.defineProperty(window,'localStorage',{value:{getItem:()=>null,setItem:()=>{}},configurable:true});</script>"
    return body.replace('<head>', '<head>' + shim)


def run_case(browser, flow, stage, screenshot):
    command = [browser, '--headless', '--no-sandbox', '--disable-gpu', '--hide-scrollbars',
               '--disable-dev-shm-usage', '--disable-background-networking', '--disable-extensions', '--no-proxy-server',
               '--window-size=800,480', '--force-device-scale-factor=1', '--virtual-time-budget=5000', '--dump-dom']
    command = [browser, '--headless', '--no-sandbox', '--disable-gpu', '--hide-scrollbars',
               '--disable-dev-shm-usage', '--disable-background-networking', '--disable-extensions',
               '--window-size=800,480', '--force-device-scale-factor=1', '--timeout=4000', '--dump-dom']
    if screenshot:
        command += [f'--screenshot={screenshot}']
    with tempfile.TemporaryDirectory(prefix='ccrate-touchscreen-fixture-') as temp:
        fixture = pathlib.Path(temp) / 'touchscreen.html'
        fixture.write_text(fixture_html(), encoding='utf-8')
        url = fixture.as_uri() + f'?flow={flow}&stage={stage}'
        profile = pathlib.Path(temp) / 'profile'
        command += [f'--user-data-dir={profile}', url]
        process = subprocess.Popen(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        try:
            stdout, stderr = process.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate(timeout=5)
            raise BrowserUnavailable(f'Chromium did not finish its file:// capture: {stderr[-1200:]}')
        result = subprocess.CompletedProcess(command, process.returncode or 0, stdout, stderr)
    if result.returncode and not result.stdout:
        raise BrowserUnavailable(f'Chromium failed before producing a DOM: {result.stderr[-2000:]}')
    import re
    match = re.search(r'<body[^>]*data-result="([^"]+)"', result.stdout)
    error = re.search(r'<body[^>]*data-error="([^"]+)"', result.stdout)
    if error:
        raise AssertionError('Browser flow failed: ' + error.group(1))
    if not match:
        if not result.stdout or '<html' not in result.stdout:
            raise BrowserUnavailable('Chromium produced no page DOM: ' + result.stderr[-1200:])
        raise AssertionError('Synthetic browser flow did not complete and emit results. DOM tail: ' + result.stdout[-1200:])
    data = json.loads(html.unescape(match.group(1)))
    if data['overflow']:
        raise AssertionError(f"Horizontal overflow at 800x480: {data['scrollWidth']} > {data['clientWidth']}")
    if data['shortButtons']:
        raise AssertionError('Touch targets below 44px: ' + repr(data['shortButtons']))
    if data['manager']:
        raise AssertionError('Manager UI text is exposed on the touchscreen')
    if not data['longNameVisible']:
        raise AssertionError('Long item name missing from review')
    if not data['noteVisible']:
        raise AssertionError('Per-item note missing from review')
    if flow == 'return' and (not data['locationVisible'] or not data['conditionVisible']):
        raise AssertionError('Return review omitted condition or location')
    if stage == 'receipt' and (not data['receiptVisible'] or data['confirmRequests'] != 1):
        raise AssertionError('Receipt missing or confirmation was not exactly once')
    return data


def main():
    if not CHROMIUM:
        raise SystemExit('No system Chromium executable is available; install no dependencies for this verifier.')
    screenshots = pathlib.Path('/tmp')
    results = []
    try:
        for flow in ('checkout', 'return'):
            review = run_case(CHROMIUM, flow, 'review', screenshots / f'ccrate-{flow}-review-800x480.png')
            receipt = run_case(CHROMIUM, flow, 'receipt', None)
            results.extend((review, receipt))
    except BrowserUnavailable as error:
        print(json.dumps({'status': 'browser_unavailable', 'reason': str(error), 'live_homebox_requests': 0}, indent=2))
        return 2
    print(json.dumps({'status': 'passed', 'results': results, 'screenshots': [str(screenshots / 'ccrate-checkout-review-800x480.png'), str(screenshots / 'ccrate-return-review-800x480.png')],
                      'api_mode': 'synthetic fetch shim, no network access', 'live_homebox_requests': 0}, indent=2))


if __name__ == '__main__':
    sys.exit(main())
