import assert from 'node:assert/strict';
import test from 'node:test';
import { applyCameraControl, describeCameraControls, digitalZoomDrawArgs, CameraControlError } from '../homebox-ui/overlay/lib/ocr-camera-controls.js';

test('digital zoom keeps the full source at 1× and a centered quarter at 4×', () => {
  assert.deepEqual(digitalZoomDrawArgs(1920, 1080, 1), [0, 0, 1920, 1080, 0, 0, 1920, 1080]);
  assert.deepEqual(digitalZoomDrawArgs(1920, 1080, 4), [720, 405, 480, 270, 0, 0, 1920, 1080]);
  assert.deepEqual(digitalZoomDrawArgs(1920, 1080, 0), [0, 0, 1920, 1080, 0, 0, 1920, 1080]);
  assert.deepEqual(digitalZoomDrawArgs(1920, 1080, 8), [720, 405, 480, 270, 0, 0, 1920, 1080]);
});

test('digital zoom gives integer source rectangles inside odd frame dimensions', () => {
  for (const [width, height, zoom] of [[1919, 1079, 2.3], [1079, 1919, 3.7], [1, 1, 4]]) {
    const [x, y, cropWidth, cropHeight] = digitalZoomDrawArgs(width, height, zoom);
    assert.ok([x, y, cropWidth, cropHeight].every(Number.isInteger));
    assert.ok(x >= 0 && y >= 0 && cropWidth >= 1 && cropHeight >= 1);
    assert.ok(x + cropWidth <= width && y + cropHeight <= height);
  }
});

test('preview and capture use the same crop mapping for wide and tall frames', () => {
  for (const [width, height, expected] of [
    [1600, 900, [400, 225, 800, 450, 0, 0, 1600, 900]],
    [900, 1600, [225, 400, 450, 800, 0, 0, 900, 1600]],
  ]) {
    assert.deepEqual(digitalZoomDrawArgs(width, height, 2), expected);
  }
});

function track(capabilities, settings = {}, constraints = {}) {
  const calls = [];
  let currentSettings = settings;
  return {
    calls,
    getCapabilities: () => capabilities,
    getSettings: () => currentSettings,
    getConstraints: () => constraints,
    applyConstraints: async value => { calls.push(value); const key = ['zoom', 'focusMode', 'focusDistance'].find(name => name in value && value[name] !== constraints[name]); if (key) currentSettings = { ...currentSettings, [key]: value[key] }; },
  };
}

test('describes reported zoom and focus ranges and modes only', () => {
  const camera = track({ zoom: { min: 1, max: 5, step: 0.5 }, focusMode: ['none', 'manual', 'single-shot', 'continuous'], focusDistance: { min: 0, max: 10, step: 1 } }, { zoom: 2.5, focusDistance: 3 });
  assert.deepEqual(describeCameraControls(camera), {
    zoom: { min: 1, max: 5, step: 0.5, value: 2.5 },
    focusModes: ['none', 'manual', 'single-shot', 'continuous'],
    focusDistance: { min: 0, max: 10, step: 1, value: 3 },
  });
  assert.deepEqual(describeCameraControls(track({})), { focusModes: [] });
  assert.deepEqual(describeCameraControls({}), { focusModes: [] });
});

test('applies supported controls clamped and rounded while preserving constraints', async () => {
  const camera = track({ zoom: { min: 1, max: 5, step: 0.5 }, focusMode: ['manual', 'continuous'] }, { zoom: 2 }, { width: { ideal: 1280 }, facingMode: 'environment' });
  assert.deepEqual(await applyCameraControl(camera, 'zoom', 9), { zoom: 5 });
  assert.deepEqual(camera.calls[0], { width: { ideal: 1280 }, facingMode: 'environment', zoom: 5 });
  await applyCameraControl(camera, 'focusMode', 'manual');
  assert.deepEqual(camera.calls[1], { width: { ideal: 1280 }, facingMode: 'environment', focusMode: 'manual' });
  assert.deepEqual(await applyCameraControl(track({ zoom: { min: 0, max: 2, step: 0.5 } }), 'zoom', 1.26), { zoom: 1.5 });
});

test('unsupported or invalid values reject with a typed error without applying', async () => {
  const camera = track({ focusMode: ['manual'] });
  await assert.rejects(applyCameraControl(camera, 'zoom', 2), error => error instanceof CameraControlError && error.code === 'unsupported');
  await assert.rejects(applyCameraControl(camera, 'focusMode', 'continuous'), error => error instanceof CameraControlError && error.code === 'invalid-value');
  assert.equal(camera.calls.length, 0);
});

test('rejects stale and failed tracks without stopping the camera', async () => {
  const stale = track({ zoom: { min: 1, max: 2 } });
  stale.readyState = 'ended';
  await assert.rejects(applyCameraControl(stale, 'zoom', 1.5), error => error instanceof CameraControlError && error.code === 'stale-track');
  const failed = track({ zoom: { min: 1, max: 2 } });
  failed.applyConstraints = async () => { throw new Error('driver rejected'); };
  await assert.rejects(applyCameraControl(failed, 'zoom', 1.5), /driver rejected/);
  assert.notEqual(failed.readyState, 'ended');
});

test('does not apply a control if existing constraints cannot be read', async () => {
  const camera = track({ zoom: { min: 1, max: 2 } });
  camera.getConstraints = () => { throw new Error('constraints unavailable'); };
  await assert.rejects(applyCameraControl(camera, 'zoom', 1.5), error => error instanceof CameraControlError && error.code === 'constraints-unavailable');
  assert.equal(camera.calls.length, 0);
});

test('rejects tracks without applyConstraints using a typed failure', async () => {
  const camera = track({ zoom: { min: 1, max: 2 } });
  delete camera.applyConstraints;
  await assert.rejects(applyCameraControl(camera, 'zoom', 1.5), error => error instanceof CameraControlError && error.code === 'apply-unavailable');
  assert.notEqual(camera.readyState, 'ended');
});
