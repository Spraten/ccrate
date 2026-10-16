import { readFileSync } from 'node:fs';
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

const html = readFileSync(new URL('../kiosk/terminal.js', import.meta.url), 'utf8');
const from = html.indexOf('function labelPrintStatus(');
const to = html.indexOf('\nfunction dashboardIcon(', from);
assert.notEqual(from, -1, 'label recovery state helpers must be present');
const source = html.slice(from, to);
function harness(statusByKey) {
  const calls = [], saved = [], keys = [];
  const states = { ...statusByKey };
  const api = async (path, data) => {
    calls.push([path, data]);
    if (path === '/operation/status') return { status: states[data.request_key] || 'not_started', id: 'job-1' };
    if (path === '/label/preview') return { reviews: [{ review_id: 'fresh-review', image: 'fresh.png' }] };
    if (path === '/label/print') { if (states.__throwPrint) { states[data.request_key]='completed'; throw new Error('reply lost'); } states[data.request_key]='completed'; return { status: 'completed' }; }
    throw new Error('unexpected request '+path);
  };
  const owner = (row,ownerId)=>ownerId!==undefined?ownerId:Object.prototype.hasOwnProperty.call(row,'owner_user_id')?row.owner_user_id:'owner';
  const state = new Function('api','saveLabelPrint','crypto','labelPrintRows','labelPrintOwner','identityUserId', source+'; return {labelNeedsRecovery,labelRetrySafe,labelPrintActions,labelPrintCardState,reconcileLabelPrint,reconcileLabelRecovery,prepareLabelRetry,confirmSafeLabelRetry};')(
    api, row => { const i=saved.findIndex(item=>item.request_key===row.request_key); if(i<0)saved.push(structuredClone(row));else saved[i]=structuredClone(row) }, { randomUUID: () => { keys.push('new-key'); return 'new-key'; } }, () => saved, owner, 'owner');
  return { ...state, calls, saved, keys, states };
}

test('uncertain restored request stays locked and never creates or posts a new request', async () => {
  const h = harness({ 'old-key': 'sent' });
  const row = { entity_id:'item', request_key:'old-key', status:'uncertain', template_id:'t', template_revision:2 };
  await h.reconcileLabelPrint(row);
  assert.equal(h.labelNeedsRecovery(row), true);
  assert.deepEqual(h.labelPrintActions(row), {confirmDisabled:true,quickDisabled:true});
  await assert.rejects(h.confirmSafeLabelRetry(row, 'item', {review_id:'fresh'}, 1, 'session'), /not confirmed unsent/);
  assert.deepEqual(h.keys, []);
  assert.equal(h.calls.some(([path])=>path==='/label/print'), false);
});

test('Recovery to not_started requires a fresh preview, then a separate confirmation before POST', async () => {
  const h = harness({ 'old-key': 'review' });
  const row = { entity_id:'item', request_key:'old-key', status:'uncertain', operation_id:'job-1', template_id:'t', template_revision:2 };
  h.saved.push(structuredClone(row));
  h.states['old-key']='not_started';
  await h.reconcileLabelRecovery('job-1','cancelled');
  row.status=h.saved.find(item=>item.request_key==='old-key').status;
  assert.equal(row.status, 'not_started');
  assert.deepEqual(h.labelPrintActions(row), {confirmDisabled:true,quickDisabled:false});
  assert.ok(h.calls.some(([path,data])=>path==='/operation/status'&&data.request_key==='old-key'), 'Recovery is followed by authoritative status reconciliation');
  const review = await h.prepareLabelRetry(row, 'item', 1, 'session');
  assert.equal(review.review_id, 'fresh-review');
  assert.equal(h.calls.some(([path])=>path==='/label/print'), false, 'preview alone cannot print');
  assert.deepEqual(h.keys, [], 'preview does not allocate a request identity');
  await h.confirmSafeLabelRetry(row, 'item', review, 1, 'session');
  assert.deepEqual(h.keys, ['new-key']);
  assert.equal(h.calls.filter(([path])=>path==='/label/print').length, 1);
  assert.equal(row.request_key, 'new-key');
  assert.equal(row.status, 'completed');
});

test('successful print and recovered lost reply repaint as completed and lock both print actions', async () => {
  const direct=harness({ 'old-key':'not_started' });
  const directRow={entity_id:'item',request_key:'old-key',status:'not_started',template_id:'t',template_revision:2};
  const review=await direct.prepareLabelRetry(directRow,'item',1,'session');
  await direct.confirmSafeLabelRetry(directRow,'item',review,1,'session');
  const completeState={message:'Pi printer confirmed this request. Inspect the physical label before printing another copy.',confirmLabel:'Printed',actions:{confirmDisabled:true,quickDisabled:true}};
  assert.deepEqual(direct.labelPrintCardState(directRow),completeState);

  const recovered=harness({ 'old-key':'not_started',__throwPrint:true });
  const uncertain={entity_id:'item',request_key:'old-key',status:'not_started',template_id:'t',template_revision:2};
  const recoveredReview=await recovered.prepareLabelRetry(uncertain,'item',1,'session');
  await assert.rejects(recovered.confirmSafeLabelRetry(uncertain,'item',recoveredReview,1,'session'),/reply lost/);
  assert.equal(uncertain.status,'completed');
  assert.deepEqual(recovered.labelPrintCardState(uncertain),completeState);
});

test('a new reviewed label after completion is printable while uncertain output remains globally locked', () => {
  const h = harness({});
  const statusSource = html.slice(html.indexOf('function labelPrintStatus('), html.indexOf('\nfunction labelRetrySafe('));
  const status = new Function('labelPrintRows','identityUserId', 'function labelNeedsRecovery(row){return !!row&&["pending","uncertain","prepared","sent","review"].includes(row.status)};'+statusSource+'; return labelPrintStatus;')(() => [
    { entity_id:'item', review_id:'old-review', request_key:'done', status:'completed' },
  ], 'owner');
  assert.equal(status('item','old-review','owner').status, 'completed');
  assert.equal(status('item','new-review','owner'), null, 'a completed prior label must not block a fresh review');

  const withUncertain = new Function('labelPrintRows','identityUserId', 'function labelNeedsRecovery(row){return !!row&&["pending","uncertain","prepared","sent","review"].includes(row.status)};'+statusSource+'; return labelPrintStatus;')(() => [
    { entity_id:'item', review_id:'old-review', request_key:'done', status:'completed' },
    { entity_id:'item', review_id:'new-review', request_key:'uncertain', status:'uncertain' },
  ], 'owner');
  assert.equal(withUncertain('item','new-review','owner').status, 'uncertain');
  assert.deepEqual(h.labelPrintActions(withUncertain('item','new-review','owner')), {confirmDisabled:true,quickDisabled:true});
});

test('late status reconciliation persists under the original badge owner', async () => {
  let identityUserId = 'badge-A';
  const storage = new Map();
  const localStorage = { getItem:key=>storage.get(key)||null, setItem:(key,value)=>storage.set(key,value) };
  const source = html.slice(html.indexOf('function labelPrintKey('), html.indexOf('\nfunction labelPrintStatus('));
  const save = new Function('localStorage', `let identityUserId='badge-A'; ${source}; return { saveLabelPrint, setIdentity(value){identityUserId=value} };`)(localStorage);
  save.setIdentity('badge-B');
  save.saveLabelPrint({ owner_user_id:'badge-A', request_key:'old-request', status:'completed' });
  assert.equal(JSON.parse(storage.get('label-print:badge-A'))[0].request_key, 'old-request');
  assert.equal(storage.has('label-print:badge-B'), false);
});

test('anonymous label reconciliation stays anonymous if another badge is scanned while it waits', async () => {
  let identityUserId = 'badge-A';
  const storage = new Map();
  const localStorage = { getItem:key=>storage.get(key)||null, setItem:(key,value)=>storage.set(key,value) };
  const helperSource = html.slice(html.indexOf('function labelPrintKey('), html.indexOf('\nfunction labelPrintStatus('));
  const reconcileSource = html.slice(html.indexOf('async function reconcileLabelPrint('), html.indexOf('\nasync function reconcileLabelRecovery('));
  let finishStatus;
  const api = () => new Promise(resolve => { finishStatus=resolve; });
  const helper = new Function('localStorage','identityUserId','api',`${helperSource}; ${reconcileSource}; return {reconcileLabelPrint,setIdentity(value){identityUserId=value}};`)(localStorage,identityUserId,api);
  const row = { owner_user_id:null, entity_id:'item', request_key:'anonymous-request', status:'pending' };
  const pending = helper.reconcileLabelPrint(row);
  helper.setIdentity('badge-B');
  finishStatus({status:'completed'});
  await pending;
  assert.equal(JSON.parse(storage.get('label-print:anonymous'))[0].request_key,'anonymous-request');
  assert.equal(storage.has('label-print:badge-B'),false);
});

test('label maker restores and reconciles saved requests and recovery resolution', () => {
  const maker=html.slice(html.indexOf('async function showLabelMaker'),html.indexOf('async function showLabel(entity)'));
  const recovery=html.slice(html.indexOf('function confirmRecovery'),html.indexOf('function renderCheckout'));
  assert.match(maker,/labelPrintRows\(ownerId\)\.filter\(row=>row\.status!=='completed'\)/);
  assert.match(maker,/reconcileLabelPrint\(row,ownerId\)/);
  assert.match(recovery,/await reconcileLabelRecovery\(row\.id,data\.status\)/);
  assert.match(maker,/const cardState=labelPrintCardState\(saved\)/);
});
