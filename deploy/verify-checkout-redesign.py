#!/usr/bin/env python3
"""Headless synthetic acceptance check for the shared touchscreen page.

Uses only Python's standard library and the system Chromium executable. The
fixture intercepts every fetch in page JavaScript and never contacts Homebox.
Screenshots and browser profiles are written under /tmp.
"""
import json
import html
import os
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
        'entityType': {'isLocation': False},
        'customFields': [{'name': 'Equipment kit manifest', 'value': '{"version":1,"members":["10000000-0000-4000-8000-000000000002"]}'}]}
PART = {'id': '10000000-0000-4000-8000-000000000002',
        'name': 'TEST DJI Mavic kit component', 'quantity': 1, 'archived': False,
        'entityType': {'isLocation': False}}
MEMBER = {'id': '20000000-0000-4000-8000-000000000001', 'name': 'Synthetic Test Member'}


BOOTSTRAP = r"""<script>
(() => {
 const item=__ITEM__, part=__PART__, member=__MEMBER__; let active=false, generation=0, scanned=new Set();
 window.__fixtureRequests=[];
 const json=(data,status=200)=>Promise.resolve(new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}}));
 window.fetch=async (input,options={})=>{
   const url=new URL(typeof input==='string'?input:input.url,location.href), path=url.pathname;
   const body=options.body?JSON.parse(options.body):{};
   window.__fixtureRequests.push({path:path,method:options.method||'GET',client:options.headers&&options.headers['X-Homebox-Client']||null,body:body});
   if(path==='/api/session')return json({user:active?member:null,generation:active?generation:2,instance:'synthetic-session',return_only:false});
   if(path==='/scan') { if(body.code==='SYNTHETIC-BADGE'){active=true;generation=1;return json({kind:'user',user:member,generation:generation,instance:'synthetic-session'});} if(body.code==='SYNTHETIC-ITEM'){scanned.add(item.id);return json({kind:'entity',entity:item});} if(body.code==='SYNTHETIC-COMPONENT'){scanned.add(part.id);return json({kind:'entity',entity:part});} return json({kind:'unknown',reason:'Unknown synthetic code'},404); }
   if(path==='/session/activity')return json({active});
   if(path==='/session/end'){active=false;generation++;return json({status:'completed'});}
   if(path==='/api/inventory')return json([item]);
   if(path==='/api/kit'){const id=url.searchParams.get('id');return id===item.id?json({kit:true,root:item,entities:[item,part],versions:{[item.id]:'synthetic-kit-version'},verified:[...scanned]}):json({kit:false,root:part,entities:[part],versions:{},verified:[...scanned]});}
   if(path==='/checkout/cart')return json({revision:0,items:[],notes:{}});
   if(path==='/checkout/availability'){const ids=(url.searchParams.get('ids')||'').split(',');return json(ids.map(id=>({id:id,reason:null})));}
   if(path==='/return/availability'){const ids=(url.searchParams.get('ids')||'').split(',');return json({items:ids.map(id=>({id:id,eligible:true,reason:null,condition:'Ready',location:{id:'loc-1',name:'Lab / D Wing / G38'}}))});}
   if(path==='/checkout/confirm'){window.__checkoutPayload=body;throw new TypeError('Synthetic lost response');}
   if(path==='/return/confirm'){window.__returnPayload=body;active=false;generation++;throw new TypeError('Synthetic lost response after server session end');}
   if(path==='/operation/status')return json({status:'completed',id:'SYNTHETIC-RECOVERED-RECEIPT',count:2});
   return json({error:'Unexpected synthetic route '+path},404);
 };
 const wait=async fn=>{for(let i=0;i<100;i++){if(fn())return;await new Promise(r=>setTimeout(r,20));}throw Error('Timed out waiting for '+fn.toString())};
 const click=async selector=>{await wait(()=>document.querySelector(selector));document.querySelector(selector).click();await new Promise(r=>setTimeout(r,40));};
 const fill=async (selector,value)=>{await wait(()=>document.querySelector(selector));const el=document.querySelector(selector);el.value=value;el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));};
 const run=async()=>{try{
   const flow=new URLSearchParams(location.search).get('flow'),stage=new URLSearchParams(location.search).get('stage')||'receipt';
   await click(`[data-flow="${flow}"]`); document.body.dataset.step='flow-selected';
   if(getComputedStyle(document.querySelector('#home')).display!=='none'||document.querySelector('#flow').hidden)throw Error('Flow navigation did not hide the home menu');
   const inactiveHost=document.querySelector(flow==='checkout'?'#return-ui':'#checkout-ui');if(getComputedStyle(inactiveHost).display!=='none')throw Error('Inactive transaction UI is visible');
   await fill('#badge-code','SYNTHETIC-BADGE');document.querySelector('#badge-form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await wait(()=>window.checkoutSession?.generation===1);if(!document.querySelector('#badge-form').hidden)throw Error('Badge form remained visible after member verification');document.body.dataset.step='badge-accepted';
   const search=flow==='checkout'?'#checkout-ui input[aria-label="Search inventory"]':'#return-ui input[placeholder="Search by name or ID"]';
   await fill(search,'Mavic');await wait(()=>[...document.querySelectorAll('#checkout-ui button,#return-ui button')].some(b=>b.textContent.includes('Mavic')));document.body.dataset.step='search-result';
   const candidate=[...document.querySelectorAll('#checkout-ui button,#return-ui button')].find(b=>b.textContent.includes('Mavic'));
   if(!candidate)throw Error('Search suggestion was not rendered');candidate.click();await new Promise(r=>setTimeout(r,40));
   const scan=flow==='checkout'?'#checkout-ui input[aria-label="Scan item barcode"]':'#return-ui input[placeholder="Scan item barcode"]';
   const submitScan=async code=>{await fill(scan,code);if(flow==='checkout')document.querySelector('#checkout-ui form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));else [...document.querySelectorAll('#return-ui button')].find(b=>b.textContent==='Verify scan and add').click();};
   await submitScan('SYNTHETIC-ITEM');await wait(()=>document.querySelector('#'+flow+'-ui p')?.textContent.includes('Scan kit component'));
   await submitScan('SYNTHETIC-COMPONENT');await wait(()=>document.querySelectorAll('#'+flow+'-ui article').length===1);
   await submitScan('SYNTHETIC-ITEM');await wait(()=>document.querySelectorAll('#'+flow+'-ui article').length===1&&document.querySelector('#'+flow+'-ui article strong')?.textContent===item.name);
   const note=document.querySelector(flow==='checkout'?'#checkout-ui article input':'#return-ui article input[placeholder="Optional return note"]');
   if(flow==='checkout'){note.value='Synthetic per-item handling note';note.dispatchEvent(new Event('input',{bubbles:true}));}
   else {const condition=document.querySelector('#return-ui select');condition.value='Broken';condition.dispatchEvent(new Event('change',{bubbles:true}));const issue=document.querySelector('#return-ui input[placeholder="Required note if condition changed"]');issue.value='Synthetic condition issue note';issue.dispatchEvent(new Event('input',{bubbles:true}));note.value='Synthetic per-item handling note';note.dispatchEvent(new Event('input',{bubbles:true}));}
   const review=[...document.querySelectorAll('#'+flow+'-ui button')].find(b=>b.textContent==='Review '+(flow==='checkout'?'checkout':'return'));
   if(!review)throw Error('Review action missing');review.click();await new Promise(r=>setTimeout(r,180));
   await wait(()=>[...document.querySelectorAll('#'+flow+'-ui button')].some(b=>b.textContent==='Confirm '+(flow==='checkout'?'checkout':'return')&&!b.disabled));
   const tray=document.querySelector('#'+flow+'-ui .flow-actions');
   const fieldSelectors=flow==='checkout'?['#checkout-ui input[placeholder="Optional note for this item"]']:['#return-ui input[placeholder="Required note if condition changed"]','#return-ui input[placeholder="Optional return note"]'];
   const fieldVisibility=[];
   for(const selector of fieldSelectors){const field=document.querySelector(selector);if(!field)throw Error('Expected review field missing: '+selector);field.scrollIntoView({block:'center'});await new Promise(r=>setTimeout(r,30));const r=field.getBoundingClientRect(),t=tray.getBoundingClientRect();fieldVisibility.push({placeholder:field.placeholder,top:r.top,bottom:r.bottom,height:r.height,trayTop:t.top,visible:r.height>=44&&r.top>=0&&r.bottom<=t.top});}
   window.scrollTo(0,0);
   if(fieldVisibility.some(field=>!field.visible))throw Error('A note field is covered by the fixed action tray: '+JSON.stringify(fieldVisibility));
   const overflow=document.documentElement.scrollWidth>document.documentElement.clientWidth;
   const shortButtons=[...document.querySelectorAll('button')].filter(b=>{const r=b.getBoundingClientRect();return r.width>0&&r.height<44;}).map(b=>b.textContent.trim());
   const manager=/(manager|settings|workshop|badge administration|inventory edit)/i.test(document.body.innerText);
   const primaryNames=['Review '+(flow==='checkout'?'checkout':'return'),'Confirm '+(flow==='checkout'?'checkout':'return')];
   const primaryButtons=primaryNames.map(name=>{const b=[...document.querySelectorAll('#'+flow+'-ui button')].find(x=>x.textContent===name),r=b?.getBoundingClientRect();return {name,visible:!!r&&r.top>=0&&r.bottom<=innerHeight,top:r?.top??null,bottom:r?.bottom??null};});
   if(primaryButtons.some(b=>!b.visible))throw Error('Primary review/confirm controls are outside the 800x480 viewport: '+JSON.stringify(primaryButtons));
   const reviewData={stage:'review',flow,overflow,shortButtons,primaryButtons,fieldVisibility,kitGrouped:document.querySelectorAll('#'+flow+'-ui article').length===1,inactiveFlowHidden:getComputedStyle(inactiveHost).display==='none',manager,scrollWidth:document.documentElement.scrollWidth,clientWidth:document.documentElement.clientWidth,
     longNameVisible:document.body.innerText.includes(item.name),noteVisible:[...document.querySelectorAll('#'+flow+'-ui input')].some(i=>i.value==='Synthetic per-item handling note'),locationVisible:document.body.innerText.includes('Lab / D Wing / G38'),
     conditionVisible:flow==='return'?document.body.innerText.includes('Recorded condition: Ready'):true,
     blockerVisible:document.body.innerText.includes('Blocked:')};
   if(stage==='review'){document.body.dataset.result=JSON.stringify(reviewData);return;}
   const confirm=[...document.querySelectorAll('#'+flow+'-ui button')].find(b=>b.textContent==='Confirm '+(flow==='checkout'?'checkout':'return'));
   if(confirm.disabled)throw Error('Confirm remains disabled after complete review');confirm.click();await wait(()=>[...document.querySelectorAll('#'+flow+'-ui button')].some(b=>b.textContent==='Check saved result'));[...document.querySelectorAll('#'+flow+'-ui button')].find(b=>b.textContent==='Check saved result').click();await wait(()=>document.body.innerText.includes(flow==='checkout'?'Checkout complete':'Return complete'));
   if(flow==='return'){document.dispatchEvent(new Event('visibilitychange'));await wait(()=>window.checkoutSession?.authenticated===false);if(!document.body.innerText.includes('Return complete'))throw Error('Inactive member poll cleared the completed return receipt');if(window.checkoutSession.generation!==1)throw Error('Inactive numeric generation replaced captured receipt identity');const done=[...document.querySelectorAll('#return-ui button')].find(b=>b.textContent==='Done');done.click();await wait(()=>document.querySelector('#flow').hidden&&!document.querySelector('#home').hidden);if(window.returnReceiptPreserved)throw Error('Done did not clear the preserved return context');}
   const required=['/scan','/api/kit','/operation/status','/'+flow+'/confirm',flow==='checkout'?'/checkout/availability':'/return/availability'];
   for(const path of required)if(!window.__fixtureRequests.some(req=>req.path===path))throw Error('Missing synthetic request '+path);
   if(window.__fixtureRequests.some(req=>req.client!=='synthetic-client'))throw Error('A flow request omitted or changed X-Homebox-Client');
   const payload=flow==='checkout'?window.__checkoutPayload:window.__returnPayload;
   if(flow==='checkout'&&payload.notes[item.id]!=='Synthetic per-item handling note')throw Error('Edited checkout note was not submitted');
   if(flow==='return'&&(payload.targets.length!==2||payload.targets[0].note!=='Synthetic condition issue note'||payload.targets[0].return_note!=='Synthetic per-item handling note'))throw Error('Return notes or unique kit targets were not submitted');
   const receipt={...reviewData,stage:'receipt',receiptVisible:true,confirmRequests:window.__fixtureRequests.filter(x=>x.path==='/'+flow+'/confirm').length,statusRequests:window.__fixtureRequests.filter(x=>x.path==='/operation/status').length,pollPreserved:flow==='return'};
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
    injection = (BOOTSTRAP.replace('__ITEM__', json.dumps(ITEM))
                 .replace('__PART__', json.dumps(PART))
                 .replace('__MEMBER__', json.dumps(MEMBER)))
    for asset in ('checkout-ui.js', 'return-ui.js', 'touchscreen.js'):
        source = (ROOT / 'kiosk' / asset).read_text(encoding='utf-8')
        body = body.replace(f'<script src="/{asset}" defer></script>',
                            f'<script data-fixture-asset="{asset}">' + source + '</script>')
    # Install mocks before application scripts while keeping all real asset
    # tags present for the inline bundle replacement above.
    body = body.replace('<script data-fixture-asset="checkout-ui.js">',
                        injection + '<script data-fixture-asset="checkout-ui.js">', 1)
    # file:// has inconsistent localStorage implementations across Chromium builds.
    shim = "<script>Object.defineProperty(window,'localStorage',{value:{getItem:()=> 'synthetic-client',setItem:()=>{}},configurable:true});</script>"
    return body.replace('<head>', '<head>' + shim)


def run_case(browser, flow, stage, screenshot):
    command = [browser, '--headless', '--no-sandbox', '--disable-gpu', '--hide-scrollbars',
               '--disable-dev-shm-usage', '--disable-background-networking', '--disable-extensions',
               '--no-proxy-server', '--window-size=800,480', '--force-device-scale-factor=1',
               '--virtual-time-budget=12000', '--dump-dom']
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
            stdout, stderr = process.communicate(timeout=30)
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
    if any(not field['visible'] for field in data['fieldVisibility']):
        raise AssertionError('A note or issue field is hidden by the fixed action tray: ' + repr(data['fieldVisibility']))
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
