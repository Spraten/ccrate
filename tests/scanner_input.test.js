const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { bindScannerInput, mountScannerCapture } = require('../kiosk/scanner_input.js');

function scannerSetupFromPage(mount) {
  const page = fs.readFileSync(path.join(__dirname, '../kiosk/index.html'), 'utf8');
  const start = page.indexOf('function setupScannerInput(overlay,onScan){');
  const end = page.indexOf('\nfunction focusScannerInput', start);
  assert.notEqual(start, -1);
  assert.notEqual(end, -1);
  const source = page.slice(start, end);
  const node = (tag, text = '') => ({
    tag, textContent: text, attributes: {}, isConnected: false,
    setAttribute(name, value) { this.attributes[name] = value; },
  });
  return new Function('node', 'mountScannerCapture', `return (${source})`)(node, mount);
}

function captureInput() {
  const listeners = {};
  return {
    value: '',
    addEventListener(type, listener) { listeners[type] = listener; },
    key(key) {
      let prevented = false;
      listeners.keydown({ key, preventDefault() { prevented = true; } });
      return prevented;
    },
  };
}

function fakeDocument() {
  return {
    createElement(tag) {
      const listeners = {};
      return {
        tag,
        children: [],
        attributes: {},
        isConnected: false,
        append(...children) { this.children.push(...children); },
        addEventListener(type, listener) { listeners[type] = listener; },
        setAttribute(name, value) { this.attributes[name] = value; },
        focus() { listeners.focus?.(); },
        blur() { listeners.blur?.(); },
        key(key) {
          let prevented = false;
          listeners.keydown({ key, preventDefault() { prevented = true; } });
          return prevented;
        },
      };
    },
  };
}

function routeScanFromPage(sandbox) {
  const page = fs.readFileSync(path.join(__dirname, '../kiosk/index.html'), 'utf8');
  const start = page.indexOf('async function routeScan(code,expectedOverlay=null){');
  const end = page.indexOf("\ndocument.querySelector('#scan').onclick=async()=>", start);
  assert.notEqual(start, -1);
  assert.notEqual(end, -1);
  const source = page.slice(start, end);
  return new Function('sandbox', `with(sandbox){ ${source}; return routeScan; }`)(sandbox);
}

test('submits a focused scanner value only when Enter frames it', () => {
  const input = captureInput();
  const scans = [];
  bindScannerInput(input, code => scans.push(code));
  input.value = '  NETUM-42  ';

  assert.equal(input.key('2'), false);
  assert.deepEqual(scans, []);
  assert.equal(input.key('Enter'), true);
  assert.deepEqual(scans, ['NETUM-42']);
  assert.equal(input.value, '');
});

test('ignores empty Enter frames', () => {
  const input = captureInput();
  const scans = [];
  bindScannerInput(input, code => scans.push(code));

  assert.equal(input.key('Enter'), true);
  assert.deepEqual(scans, []);
});

test('mounts a focused HID capture field with pairing help and last-scan status', async () => {
  const priorDocument = global.document;
  global.document = fakeDocument();
  const overlay = { append(panel) { panel.isConnected = true; this.panel = panel; } };
  const scans = [];
  try {
    const captureInput = mountScannerCapture(overlay, async code => { scans.push(code); return 'No item matched'; });
    const [title, help, input, focusButton, status] = overlay.panel.children;
    assert.match(title.textContent, /NETUM 2D-C750-Yellow/);
    assert.match(help.textContent, /Bluetooth settings/);
    assert.match(help.textContent, /HID\/keyboard/);
    captureInput.focus();
    assert.equal(input, captureInput);
    assert.match(status.textContent, /Ready to receive/);
    input.value = 'NETUM-42';
    assert.equal(input.key('Enter'), true);
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(scans, ['NETUM-42']);
    assert.match(status.textContent, /No item matched/);
    assert.match(status.textContent, /Last scan: NETUM-42/);
    input.blur();
    assert.match(status.textContent, /Scanner input unfocused/);
    assert.match(status.textContent, /Last scan: NETUM-42/);
    focusButton.onclick();
    assert.match(status.textContent, /Ready to receive/);
    assert.match(status.textContent, /Last scan: NETUM-42/);
  } finally {
    global.document = priorDocument;
  }
});

test('immediately marks the HID input unfocused when it loses keyboard focus', () => {
  const priorDocument = global.document;
  global.document = fakeDocument();
  const overlay = { append(panel) { panel.isConnected = true; this.panel = panel; } };
  try {
    const input = mountScannerCapture(overlay, async () => true);
    const [, , , , status] = overlay.panel.children;
    input.focus();
    assert.match(status.textContent, /Ready to receive/);

    input.blur();

    assert.match(status.textContent, /Scanner input unfocused/);
    assert.doesNotMatch(status.textContent, /Ready to receive/);
  } finally {
    global.document = priorDocument;
  }
});

test('routes a HID-framed equipment scan into the existing checkout cart flow', async () => {
  const priorDocument = global.document;
  global.document = fakeDocument();
  const overlay = { append(panel) { panel.isConnected = true; this.panel = panel; } };
  const entity = { id: 'asset-42', name: 'Bench supply', entityType: { isLocation: false } };
  const checkoutCart = [];
  const requests = [];
  const sandbox = {
    clearItemActionOffer() {},
    scanPurpose: null,
    manufacturerCodeDraft: null,
    enrollment: null,
    cancelScanRequest() {},
    routeRevision: 4,
    activeScanRequest: null,
    scanOverlay: overlay,
    crypto,
    fetch: async (url, options) => {
      requests.push({ url, options });
      return { ok: true, json: async () => ({ entity }) };
    },
    checkoutMode: true,
    kitDraft: null,
    problemMode: false,
    returnDestinationFor: null,
    itemNoteMode: false,
    returnMode: false,
    stopScan() {},
    addCheckout: async scanned => checkoutCart.push(scanned),
    status: { textContent: '' },
  };
  try {
    const routeScan = routeScanFromPage(sandbox);
    const input = mountScannerCapture(overlay, code => routeScan(code, overlay));
    input.focus();
    input.value = 'BIN-D-GC-C-1';
    input.key('Enter');
    await new Promise(resolve => setImmediate(resolve));

    assert.equal(requests.length, 1);
    assert.equal(requests[0].url, '/scan');
    assert.equal(JSON.parse(requests[0].options.body).code, 'BIN-D-GC-C-1');
    assert.deepEqual(checkoutCart, [entity]);
  } finally {
    global.document = priorDocument;
  }
});

test('keeps unfocused status when a delayed scan result arrives', async () => {
  const priorDocument = global.document;
  global.document = fakeDocument();
  const overlay = { append(panel) { panel.isConnected = true; this.panel = panel; } };
  let finishScan;
  try {
    const input = mountScannerCapture(overlay, () => new Promise(resolve => { finishScan = resolve; }));
    const [, , captureInput, , status] = overlay.panel.children;
    input.focus();
    captureInput.value = 'NETUM-42';
    captureInput.key('Enter');
    captureInput.blur();
    finishScan('No item matched');
    await new Promise(resolve => setImmediate(resolve));

    assert.match(status.textContent, /No item matched/);
    assert.match(status.textContent, /Scanner input unfocused/);
    assert.match(status.textContent, /Last scan: NETUM-42/);
  } finally {
    global.document = priorDocument;
  }
});

test('scanner helper load or initialization failure leaves a clear fallback status', () => {
  for (const mount of [undefined, () => { throw new Error('init failed'); }]) {
    const overlay = { children: [], append(status) { status.isConnected = true; this.children.push(status); } };
    const capture = scannerSetupFromPage(mount)(overlay, () => {});
    assert.equal(capture.input, null);
    assert.match(capture.status.textContent, /Bluetooth scanner input unavailable/);
    assert.match(capture.status.textContent, /webcam/i);
    assert.equal(overlay.children[0], capture.status);
  }
});

test('scanner setup is caught before the overlay starts its webcam and manual paths', () => {
  const page = fs.readFileSync(path.join(__dirname, '../kiosk/index.html'), 'utf8');
  const start = page.indexOf("document.querySelector('#scan').onclick=async()=>");
  const end = page.indexOf("window.addEventListener('pagehide',stopScan)", start);
  const scanner = page.slice(start, end);
  const setup = scanner.indexOf('setupScannerInput(');
  assert.ok(setup >= 0);
  assert.ok(setup < scanner.indexOf('document.body.append(overlay)'));
  assert.ok(scanner.indexOf('document.body.append(overlay)') < scanner.indexOf('openBrowserCamera('));
  assert.match(scanner, /Enter code/);
  assert.match(scanner, /Reconnect webcam/);
});

test('scan handler keeps camera and manual controls usable when scanner setup or focus fails', async () => {
  const page = fs.readFileSync(path.join(__dirname, '../kiosk/index.html'), 'utf8');
  const start = page.indexOf("document.querySelector('#scan').onclick=async()=>{");
  const end = page.indexOf("\nwindow.addEventListener('pagehide',stopScan)", start);
  assert.notEqual(start, -1);
  assert.notEqual(end, -1);
  const source = page.slice(start, end).replace("document.querySelector('#scan').onclick=async()=>{", 'async function scanClick(){');
  const setupStart = page.indexOf('function setupScannerInput(overlay,onScan){');
  const setupEnd = page.indexOf('\nlet manufacturerCodeDraft', setupStart);
  const setupSource = page.slice(setupStart, setupEnd);

  for (const failure of ['missing', 'initialization', 'focus']) {
    const mounted = [];
    let cameraStarts = 0;
    const ui = {
      createElement(tag) {
        return {
          tag, children: [], style: {}, disabled: false, readyState: 0,
          append(...children) { this.children.push(...children); },
          setAttribute() {}, getContext() { return { clearRect() {}, strokeRect() {}, beginPath() {}, lineTo() {}, moveTo() {}, closePath() {}, stroke() {}, setLineDash() {} }; },
          focus() { if (failure === 'focus') throw Error('focus failed'); },
          remove() {},
        };
      },
      body: { append(element) { mounted.push(element); } },
      querySelector() { return { disabled: false, click() {} }; },
    };
    const overlay = { children: [], style: {}, append(...children) { this.children.push(...children); }, remove() {} };
    const makeNode = (tag, text) => ({ tag, textContent: text, style: {}, children: [], disabled: false, append(...children) { this.children.push(...children); }, setAttribute() {}, remove() {} });
    const mount = failure === 'missing' ? undefined : failure === 'initialization' ? () => { throw Error('init failed'); } : () => ({ focus() { throw Error('focus failed'); } });
    const startCamera = async () => {
      cameraStarts++;
      throw Error('Camera needs a secure browser connection');
    };
    const sandbox = {
      document: ui, node: makeNode, mountScannerCapture: mount,
      closeKeyboard() {}, stopScan() {}, manualCodeEntry() {},
      openBrowserCamera: startCamera, cameraHelp: error => error.message,
      scanOverlay: null, scanStream: null, scanTimer: null, scanBusy: false,
      navigator: { userAgent: '', platform: '', mediaDevices: {} },
      editorMode: false, setTimeout() { return 1; }, clearTimeout() {},
      console,
    };
    const run = new Function('sandbox', `with(sandbox){ ${setupSource}; ${source}; return scanClick; }`)(sandbox);
    await run();

    assert.equal(cameraStarts, 1, `${failure}: camera startup should still run`);
    assert.equal(mounted.length, 1, `${failure}: overlay should mount`);
    const scanOverlay = mounted[0];
    const descendants = [];
    const visit = item => { if (!item || typeof item !== 'object') return; descendants.push(item); for (const child of item.children || []) visit(child); };
    visit(scanOverlay);
    assert.ok(descendants.some(item => item.textContent === 'Enter code'), `${failure}: manual entry should remain available`);
    assert.ok(descendants.some(item => item.textContent === 'Reconnect webcam'), `${failure}: reconnect should remain available`);
    assert.ok(descendants.some(item => /Bluetooth scanner input unavailable/.test(item.textContent || '')), `${failure}: clear scanner status should be visible`);
  }
});
