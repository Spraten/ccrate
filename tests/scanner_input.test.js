const test = require('node:test');
const assert = require('node:assert/strict');
const { bindScannerInput, mountScannerCapture } = require('../kiosk/scanner_input.js');

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
        key(key) {
          let prevented = false;
          listeners.keydown({ key, preventDefault() { prevented = true; } });
          return prevented;
        },
      };
    },
  };
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
    focusButton.onclick();
  } finally {
    global.document = priorDocument;
  }
});
