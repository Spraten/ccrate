import test from 'node:test';
import assert from 'node:assert/strict';
import { nextOcrPopoverState } from '../homebox-ui/overlay/lib/orc-popover-state.js';

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
