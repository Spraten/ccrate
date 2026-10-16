export class CameraControlError extends Error {
  constructor(code, message) {
    super(message);
    this.name = 'CameraControlError';
    this.code = code;
  }
}

function ranges(track) {
  try { return track?.getCapabilities?.() || {}; } catch { return {}; }
}

function settings(track) {
  try { return track?.getSettings?.() || {}; } catch { return {}; }
}

function rangeDescription(capability, value) {
  if (!capability || !Number.isFinite(capability.min) || !Number.isFinite(capability.max)) return undefined;
  const result = { min: capability.min, max: capability.max };
  if (Number.isFinite(capability.step)) result.step = capability.step;
  if (Number.isFinite(value)) result.value = value;
  return result;
}

export function describeCameraControls(track) {
  const capabilities = ranges(track);
  const current = settings(track);
  const result = { focusModes: Array.isArray(capabilities.focusMode) ? [...capabilities.focusMode] : [] };
  const zoom = rangeDescription(capabilities.zoom, current.zoom);
  const focusDistance = rangeDescription(capabilities.focusDistance, current.focusDistance);
  if (zoom) result.zoom = zoom;
  if (focusDistance) result.focusDistance = focusDistance;
  return result;
}

function fail(code, message) { throw new CameraControlError(code, message); }

export async function applyCameraControl(track, name, value) {
  if (!track || track.readyState === 'ended') fail('stale-track', 'Camera track is no longer active');
  const capabilities = ranges(track);
  let requested;
  if (name === 'focusMode') {
    if (!Array.isArray(capabilities.focusMode) || !capabilities.focusMode.length) fail('unsupported', 'Focus mode is not supported');
    if (typeof value !== 'string' || !capabilities.focusMode.includes(value)) fail('invalid-value', 'Focus mode is not supported by this camera');
    requested = value;
  } else if (name === 'zoom' || name === 'focusDistance') {
    const capability = capabilities[name];
    if (!capability || !Number.isFinite(capability.min) || !Number.isFinite(capability.max)) fail('unsupported', `${name} is not supported`);
    if (typeof value !== 'number' || !Number.isFinite(value)) fail('invalid-value', `${name} must be a finite number`);
    const clamped = Math.min(capability.max, Math.max(capability.min, value));
    const step = Number.isFinite(capability.step) && capability.step > 0 ? capability.step : 0;
    requested = step ? Math.min(capability.max, Math.max(capability.min, capability.min + Math.round((clamped - capability.min) / step) * step)) : clamped;
  } else {
    fail('unsupported', `Unknown camera control: ${String(name)}`);
  }

  if (typeof track.applyConstraints !== 'function') fail('apply-unavailable', 'Camera track cannot apply constraints');
  let existing;
  try {
    existing = track.getConstraints?.() || {};
  } catch {
    fail('constraints-unavailable', 'Existing camera constraints could not be read');
  }
  await track.applyConstraints({ ...existing, [name]: requested });
  return settings(track);
}
