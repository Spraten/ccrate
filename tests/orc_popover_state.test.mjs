import test from 'node:test';
import assert from 'node:assert/strict';
import { isOcrCaptureCurrent, isOcrScanCurrent, nextOcrPopoverState } from '../homebox-ui/overlay/lib/orc-popover-state.js';

test('enabling OCR exposes its launcher without opening the popout', () => {
  assert.deepEqual(
    nextOcrPopoverState({ enabled: false, open: false }, 'toggle-enabled'),
    { enabled: true, open: false },
  );
});

test('the bubble cannot open while OCR is disabled', () => {
  assert.deepEqual(
    nextOcrPopoverState({ enabled: false, open: false }, 'open'),
    { enabled: false, open: false },
  );
  assert.deepEqual(
    nextOcrPopoverState({ enabled: true, open: false }, 'open'),
    { enabled: true, open: true },
  );
});

test('disabling OCR closes an open popout', () => {
  assert.deepEqual(
    nextOcrPopoverState({ enabled: true, open: true }, 'toggle-enabled'),
    { enabled: false, open: false },
  );
});

test('closing the popout keeps the header toggle enabled for reopening', () => {
  assert.deepEqual(
    nextOcrPopoverState({ enabled: true, open: true }, 'close'),
    { enabled: true, open: false },
  );
});

test('camera captures are discarded when the camera or popout is stopped before encoding finishes', () => {
  const active = { enabled: true, open: true, minimized: false, cameraActive: true, disposed: false };
  assert.equal(isOcrCaptureCurrent(4, 4, active), true);
  assert.equal(isOcrCaptureCurrent(4, 5, active), false);
  for (const changed of [
    { cameraActive: false },
    { open: false },
    { enabled: false },
    { minimized: true },
    { disposed: true },
  ]) {
    assert.equal(isOcrCaptureCurrent(4, 4, { ...active, ...changed }), false);
  }
});

test('OCR scan results are invalidated when the popout is closed, minimized, disabled, or unmounted', () => {
  const active = { enabled: true, open: true, minimized: false, disposed: false };
  assert.equal(isOcrScanCurrent(7, 7, active), true);
  assert.equal(isOcrScanCurrent(7, 8, active), false);
  for (const changed of [
    { open: false },
    { enabled: false },
    { minimized: true },
    { disposed: true },
  ]) {
    assert.equal(isOcrScanCurrent(7, 7, { ...active, ...changed }), false);
  }
});