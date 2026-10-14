import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const returns = readFileSync(new URL('../kiosk/return-ui.js', import.meta.url), 'utf8');
const checkout = readFileSync(new URL('../kiosk/checkout-ui.js', import.meta.url), 'utf8');
const section = (source, start, end) => source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start)));
const returnGate = [
  section(returns, 'function returnReady(){', '\nfunction returnActionControls'),
  section(returns, 'async function startAnonymousReturn(){', '\nrenderReturn=function'),
  section(returns, "renderReturn=function(message=''){", '\n    if(returnPicker)') + '\n};',
].join('\n');
const checkoutGate = section(checkout, "renderCheckout=function(message=''){", '    if(checkoutPickerOpen') + '\n};';
const button = section(checkout, "function checkoutButton(label,fn,kind=''){", '\nfunction checkoutFrame');

function fixture(initial = {}) {
  const node = (tag, text = '', cls = '') => ({
    tag, textContent: text || '', className: cls, children: [], style: {},
    append(...items) { this.children.push(...items); },
    setAttribute() {},
    classList: { add() {} },
  });
  const identity = node('span');
  const context = {
    ...initial,
    node,
    identity,
    document: { querySelector: selector => selector === '#identity' ? identity : node('button') },
    checkoutNotice() {},
    returnActionControls() {},
    manualCodeEntry() {},
    api: async () => ({ generation: 4, instance: 'terminal-1', return_only: true }),
  };
  context.checkoutFrame = () => (context.lastShell = node('section'));
  context.acceptSession = data => {
    context.identityGeneration = data.generation;
    context.identityInstance = data.instance;
    return true;
  };
  vm.createContext(context);
  vm.runInContext(button, context);
  return context;
}

test('return identity gate offers the audited anonymous return, while checkout remains badge-gated', async () => {
  const returning = fixture({
    returnMode: true, returnReview: false, returnPicker: false, returnCart: [], returnAvailable: [],
    returnKey: null, returnBusy: false, returnAdding: false, identified: false, anonymousReturn: false,
    identityGeneration: 3, identityInstance: 'old', checkoutBusy: false, checkoutMode: false,
    checkoutKey: null, returnKitVersions: {}, checkoutKitVersions: {}, checkoutReview: false,
    itemActionOffer: null, itemActionOrigin: null, pendingItemAction: null, kitDraft: null,
  });
  let startRequest;
  returning.api = async (path, body) => {
    startRequest = { path, body };
    return { generation: 4, instance: 'terminal-1', return_only: true };
  };
  vm.runInContext(returnGate, returning);
  returning.renderReturn();
  const body = returning.lastShell.children[0];
  const skip = body.children.find(item => item.textContent === 'Skip badge scan');
  assert.ok(skip, 'return gate should visibly offer skipping the badge scan');
  assert.match(skip.className, /main/, 'skip action should have the same visual prominence as scanning');

  await skip.onclick();
  assert.equal(startRequest.path, '/return/session/start');
  assert.equal(Object.keys(startRequest.body).length, 0);
  assert.equal(returning.anonymousReturn, true);
  assert.equal(returning.identified, false);
  assert.equal(returning.identity.textContent, 'Unidentified returner');

  const checkingOut = fixture({
    checkoutMode: true, checkoutBusy: false, checkoutKey: null, returnKey: null,
    returnBusy: false, identified: false, checkoutReview: false, checkoutPickerOpen: false,
    checkoutCart: [], returnCart: [], checkoutKitVersions: {}, itemActionOffer: null, itemActionOrigin: null,
  });
  vm.runInContext(checkoutGate, checkingOut);
  checkingOut.renderCheckout();
  const checkoutButtons = checkingOut.lastShell.children[0].children.filter(item => item.tag === 'button');
  assert.ok(checkoutButtons.some(item => item.textContent === 'Scan my badge'));
  assert.ok(!checkoutButtons.some(item => item.textContent === 'Skip badge scan'));
});
