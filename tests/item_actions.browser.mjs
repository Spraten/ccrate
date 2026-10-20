import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { chromium } from '../work/homebox-ui-dev/node_modules/.pnpm/@playwright+test@1.60.0/node_modules/@playwright/test/index.mjs';

const source = await readFile(new URL('../homebox-ui/overlay/lib/item-actions.js', import.meta.url), 'utf8');
const browser = await chromium.launch({ headless: true, executablePath: '/usr/bin/chromium', args: ['--no-sandbox'] });
try {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await page.setContent(`<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><style>
    body{font:16px sans-serif;margin:12px} [role=dialog]{box-sizing:border-box;position:fixed;inset:5vh 4vw auto;background:white;border:1px solid #555;padding:16px;max-height:90vh;overflow:auto}
    input,textarea,button{box-sizing:border-box;font:inherit;padding:10px;margin:4px 0;max-width:100%} [hidden]{display:none}
  </style><button id="open">Check out</button><div id="dialog" role="dialog" aria-modal="true" aria-label="Check out equipment" hidden>
  <h1>Check out equipment</h1><p id="status"></p><label>Badge <input id="badge" autocomplete="off"></label><button id="badge-submit">Verify badge</button>
  <label>Item code <input id="code" autocomplete="off"></label><button id="scan-submit">Verify item</button>
  <label>Checkout note <textarea id="note"></textarea></label><p id="message" role="status"></p>
  <button id="confirm">Confirm checkout</button><button id="cancel">Cancel</button><button id="recover" hidden>Check saved result</button></div>`);
  const result = await page.evaluate(async sourceText => {
    const moduleUrl = `data:text/javascript;base64,${btoa(unescape(encodeURIComponent(sourceText)))}`;
    const { createItemActionController } = await import(moduleUrl);
    const itemId = '11111111-1111-4111-8111-111111111111';
    const calls = []; window.__actionCalls = calls;
    const storage = new Map();
    const mockStorage = { getItem: key => storage.get(key) || null, setItem: (key,value) => storage.set(key,value) };
    let number = 0;
    const controller = createItemActionController({
      getContext: () => ({ identity:'web-session', group:{id:'collection'}, user:{id:'member'}, manager:false }),
      uuid: () => `browser-key-${++number}`, storage: mockStorage,
      request: async (path, body, identity) => {
        calls.push({path,body,identity});
        if (path.startsWith('item-actions/status')) return [{id:itemId,availability:'available'}];
        if (path === 'item-actions/verify-badge') return {verification_id:'proof',required_items:[itemId],kit_versions:{}};
        if (path === 'item-actions/verify-item') return {verified_items:[itemId],required_items:[itemId]};
        if (path === 'item-actions/checkout') return {status:'completed',id:'receipt-1'};
        return {};
      },
    });
    const dialog = document.querySelector('#dialog'), opener = document.querySelector('#open');
    document.querySelector('#open').addEventListener('click', async () => {
      await controller.open({kind:'checkout',itemId,source:'row'}, opener);
      dialog.hidden = false; document.querySelector('#badge').focus();
      document.querySelector('#status').textContent = controller.state.status[0].availability;
    });
    document.querySelector('#badge-submit').addEventListener('click', () => controller.verifyBadge(document.querySelector('#badge').value));
    document.querySelector('#scan-submit').addEventListener('click', () => controller.verifyItem(document.querySelector('#code').value));
    document.querySelector('#note').addEventListener('input', event => controller.setNote(itemId,event.target.value));
    document.querySelector('#confirm').addEventListener('click', async () => {
      try { await controller.confirm(); dialog.hidden = true; }
      catch (error) { document.querySelector('#message').textContent = error.message; if(controller.state.phase==='uncertain') document.querySelector('#recover').hidden=false; }
    });
    document.querySelector('#cancel').addEventListener('click', () => { if(controller.close()) dialog.hidden=true; });
    document.querySelector('#recover').addEventListener('click', () => controller.reconcile());
    document.addEventListener('keydown', event => { if(event.key==='Escape' && !dialog.hidden) { if(controller.close()) dialog.hidden=true; event.preventDefault(); } });
    return { itemId };
  }, source);
  await page.getByRole('button', { name: 'Check out' }).click();
  assert.equal(await page.locator('#dialog').isVisible(), true);
  assert.equal(await page.evaluate(() => document.activeElement?.id), 'badge');
  await page.locator('#badge').fill('member-badge');
  await page.locator('#badge-submit').click();
  await page.locator('#code').fill('native-asset-code');
  await page.locator('#scan-submit').click();
  await page.locator('#note').fill('Ready 🎥');
  await page.locator('#confirm').click();
  assert.equal(await page.locator('#dialog').isVisible(), false);
  assert.equal(await page.evaluate(() => document.activeElement?.id), 'open');
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  const checkout = await page.evaluate(() => window.__actionCalls.find(row => row.path === 'item-actions/checkout'));
  assert.deepEqual(checkout.body.assets, [result.itemId]);
  assert.deepEqual(checkout.body.notes, { [result.itemId]: 'Ready 🎥' });
  assert.equal(checkout.body.verification_id, 'proof');
  console.log('PASS checkout badge/scan/confirm at 390×844; focus returns to the exact trigger.');

  for (const viewport of [{width:390,height:844},{width:800,height:480},{width:1280,height:800},{width:1920,height:1080}]) {
    await page.setViewportSize(viewport);
    for (const colorScheme of ['light','dark']) {
      await page.emulateMedia({ colorScheme });
      await page.locator('#open').focus();
      await page.keyboard.press('Enter');
      await page.locator('#dialog').waitFor({state:'visible'});
      const bounds = await page.locator('#dialog').boundingBox();
      assert.ok(bounds && bounds.x >= 0 && bounds.y >= 0 && bounds.x + bounds.width <= viewport.width && bounds.y + bounds.height <= viewport.height);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      assert.equal(await page.evaluate(() => document.activeElement?.id), 'badge');
      await page.keyboard.press('Escape');
      await page.locator('#dialog').waitFor({state:'hidden'});
      assert.equal(await page.evaluate(() => document.activeElement?.id), 'open');
    }
  }
  console.log('PASS keyboard open/Escape/focus and contained dialog at all four viewport sizes in light and dark modes.');

  const flow = await page.evaluate(async sourceText => {
    const moduleUrl = `data:text/javascript;base64,${btoa(unescape(encodeURIComponent(sourceText)))}`;
    const { createItemActionController } = await import(moduleUrl);
    const itemId = '11111111-1111-4111-8111-111111111111', calls = [];
    const memory = new Map(); let index = 0;
    const controller = createItemActionController({
      getContext: () => ({identity:'web-session',group:{id:'collection'},user:{id:'member'}}),
      uuid: () => `intent-${++index}`,
      storage: {getItem:key=>memory.get(key)||null,setItem:(key,value)=>memory.set(key,value)},
      request: async (path,body) => { calls.push({path,body}); if(path.startsWith('item-actions/status')) return [{id:itemId,availability:'available'}]; if(path==='item-actions/verify-badge') return {verification_id:'proof',required_items:[itemId],kit_versions:{}}; if(path==='item-actions/verify-item') return {verified_items:[itemId],required_items:[itemId]}; if(path==='item-actions/checkout') throw new Error('connection lost'); if(path==='operation/status') return {status:'pending'}; return {}; },
    });
    await controller.open({kind:'checkout',itemId,source:'row'}); await controller.verifyBadge('badge'); await controller.verifyItem('native-code');
    try { await controller.confirm(); } catch {}
    await controller.reconcile();
    return {phase:controller.state.phase, writes:calls.filter(row=>row.path==='item-actions/checkout').length, last:calls.at(-1).path};
  }, source);
  assert.deepEqual(flow, { phase: 'uncertain', writes: 1, last: 'operation/status' });
  console.log('PASS ambiguous result performs status-only recovery with one checkout POST.');

  const scenarios = await page.evaluate(async sourceText => {
    const moduleUrl = `data:text/javascript;base64,${btoa(unescape(encodeURIComponent(sourceText)))}`;
    const { createItemActionController } = await import(moduleUrl);
    const one = '11111111-1111-4111-8111-111111111111', two = '22222222-2222-4222-8222-222222222222';
    const context = {identity:'session',group:{id:'collection'},user:{id:'member',name:'Member'},manager:false};
    function make(routes) {
      const calls=[], values=new Map(); let key=0;
      const controller=createItemActionController({getContext:()=>context,uuid:()=>`scenario-${++key}`,storage:{getItem:id=>values.get(id)||null,setItem:(id,value)=>values.set(id,value)},request:async(path,body)=>{calls.push({path,body});const fn=routes[path];return fn?fn(body):{};}});
      return {controller,calls};
    }
    const checkin=make({[`item-actions/status?ids=${one}`]:async()=>[{id:one,availability:'checked_out',can_checkin:true,loan:{borrower_id:'member'}}],
      [`entity?id=${one}`]:async()=>({entity:{id:one,parent:{id:'assigned'}}}),[`kit?id=${one}`]:async()=>({kit:false,versions:{}}),
      'item-actions/checkin':async body=>({status:'completed',id:body.request_key})});
    await checkin.controller.open({kind:'checkin',itemId:one,source:'detail'});
    checkin.controller.setDraft({destination_id:'other',return_note:'Back from stage'}); await checkin.controller.confirm();
    const cart=make({'checkout-cart':async body=>body?({status:'saved'}):({revision:3,items:[one,two],notes:{}}),
      [`item-actions/status?ids=${encodeURIComponent(one+','+two)}`]:async()=>[{id:one,availability:'available'},{id:two,availability:'available'}],
      'item-actions/verify-badge':async body=>({verification_id:'cart-proof',required_items:body.item_ids,kit_versions:{}}),
      'item-actions/verify-item':async()=>({verified_items:[one,two],required_items:[one,two]}),
      'item-actions/checkout':async body=>({status:'completed',id:body.request_key})});
    await cart.controller.open({kind:'checkout',itemIds:[one,two],cartRevision:3,source:'cart'}); await cart.controller.verifyBadge('badge');
    await cart.controller.verifyItem('first'); cart.controller.setNote(one,'packed separately'); await cart.controller.confirm();
    const note=make({[`item-actions/status?ids=${one}`]:async()=>[{id:one,can_add_note:true}],
      'item-actions/note':async body=>({status:'completed',id:body.request_key})});
    await note.controller.open({kind:'note',itemId:one,source:'row'}); note.controller.setDraft({note:'Equipment checked'}); await note.controller.confirm();
    const kit=make({[`item-actions/status?ids=${one}`]:async()=>[{id:one,availability:'available'}],
      'item-actions/verify-badge':async()=>({verification_id:'kit-proof',required_items:[one,two],kit_versions:{[one]:'v1'}}),
      'item-actions/verify-item':async()=>{throw new Error('Kit manifest changed. Review the kit.');}});
    await kit.controller.open({kind:'checkout',itemId:one,source:'row'}); await kit.controller.verifyBadge('badge');
    try{await kit.controller.verifyItem('root')}catch{}
    const cancel=make({[`item-actions/status?ids=${one}`]:async()=>[{id:one,availability:'available'}]});
    await cancel.controller.open({kind:'cart',itemId:one,source:'row'}); const empty=cancel.controller.close();
    await cancel.controller.open({kind:'cart',itemId:one,source:'row'}); cancel.controller.setDraft({notes:{[one]:'private'}});
    const prompt=!cancel.controller.close(); cancel.controller.discard();
    const unknown=make({[`item-actions/status?ids=${one}`]:async()=>[{id:one,availability:'unknown'}]});
    let unknownRejected=false; try{await unknown.controller.open({kind:'checkout',itemId:one,source:'row'})}catch{unknownRejected=true}
    return {
      checkin:{badgeCalls:checkin.calls.filter(x=>x.path==='item-actions/verify-badge').length,payload:checkin.calls.find(x=>x.path==='item-actions/checkin').body.targets[0]},
      cart:{badgeCalls:cart.calls.filter(x=>x.path==='item-actions/verify-badge').length,payload:cart.calls.find(x=>x.path==='item-actions/checkout').body},
      note:note.calls.find(x=>x.path==='item-actions/note').body.note, kitPhase:kit.controller.state.phase,
      cancel:{empty,prompt,final:cancel.controller.state.phase},unknown:{rejected:unknownRejected,phase:unknown.controller.state.phase},
    };
  }, source);
  assert.equal(scenarios.checkin.badgeCalls, 0);
  assert.deepEqual(scenarios.checkin.payload, { entity_id: '11111111-1111-4111-8111-111111111111', destination_id: 'other', return_note: 'Back from stage' });
  assert.equal(scenarios.cart.badgeCalls, 1);
  assert.deepEqual(scenarios.cart.payload.cart, { revision: 3, items: ['11111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222'], notes: { '11111111-1111-4111-8111-111111111111': 'packed separately' } });
  assert.equal(scenarios.note, 'Equipment checked');
  assert.equal(scenarios.kitPhase, 'error');
  assert.deepEqual(scenarios.cancel, { empty: true, prompt: true, final: 'closed' });
  assert.equal(scenarios.unknown.rejected, true);
  console.log('PASS check-in, atomic cart notes, append note, kit conflict, cancellation/discard and unknown-status browser fixtures.');
} finally {
  await browser.close();
}
