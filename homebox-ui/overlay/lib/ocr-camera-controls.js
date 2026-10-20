export class CameraControlError extends Error {
  constructor(code, message) {
    super(message);
    this.name = 'CameraControlError';
    this.code = code;
  }
}

/** Centered, integer-safe source crop and full-frame destination for drawImage. */
export function digitalZoomDrawArgs(width, height, zoom) {
  const scale = Number.isFinite(zoom) ? Math.min(4, Math.max(1, zoom)) : 1;
  const cropWidth = Math.max(1, Math.floor(width / scale));
  const cropHeight = Math.max(1, Math.floor(height / scale));
  return [Math.floor((width - cropWidth) / 2), Math.floor((height - cropHeight) / 2),
    cropWidth, cropHeight, 0, 0, width, height];
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

/** Fresh values for a new camera session, or neutral values after stopping it. */
export function cameraControlSessionState(track) {
  if (!track) return { controls: null, hardwareZoom: 1, focusMode: '', focusDistance: 0,
    defaultZoom: undefined, defaultFocusMode: undefined, defaultFocusDistance: undefined };
  const controls = describeCameraControls(track);
  const reported = settings(track);
  return {
    controls,
    hardwareZoom: Number.isFinite(reported.zoom) ? reported.zoom : controls.zoom?.min ?? 1,
    focusMode: typeof reported.focusMode === 'string' ? reported.focusMode : '',
    focusDistance: Number.isFinite(reported.focusDistance) ? reported.focusDistance : controls.focusDistance?.min ?? 0,
    defaultZoom: reported.zoom,
    defaultFocusMode: reported.focusMode,
    defaultFocusDistance: reported.focusDistance,
  };
}

export function isCameraControlRequestCurrent(requestTrack, requestGeneration, activeTrack, activeGeneration) {
  return requestTrack === activeTrack && requestGeneration === activeGeneration && requestTrack?.readyState !== 'ended';
}

/** Capture the same centered digital crop used by the live preview. */
export async function captureCameraFrame(source, zoom, createCanvas = () => document.createElement('canvas')) {
  const canvas = createCanvas();
  canvas.width = source.videoWidth;
  canvas.height = source.videoHeight;
  const context = canvas.getContext('2d');
  if (!context) return null;
  context.drawImage(source, ...digitalZoomDrawArgs(canvas.width, canvas.height, zoom));
  return new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.9));
}

function fail(code, message) { throw new CameraControlError(code, message); }

function requestedCameraControlValue(capabilities, name, value) {
  if (name === 'focusMode') {
    if (!Array.isArray(capabilities.focusMode) || !capabilities.focusMode.length) fail('unsupported', 'Focus mode is not supported');
    if (typeof value !== 'string' || !capabilities.focusMode.includes(value)) fail('invalid-value', 'Focus mode is not supported by this camera');
    return value;
  } else if (name === 'zoom' || name === 'focusDistance') {
    const capability = capabilities[name];
    if (!capability || !Number.isFinite(capability.min) || !Number.isFinite(capability.max)) fail('unsupported', `${name} is not supported`);
    if (typeof value !== 'number' || !Number.isFinite(value)) fail('invalid-value', `${name} must be a finite number`);
    const clamped = Math.min(capability.max, Math.max(capability.min, value));
    const step = Number.isFinite(capability.step) && capability.step > 0 ? capability.step : 0;
    return step ? Math.min(capability.max, Math.max(capability.min, capability.min + Math.round((clamped - capability.min) / step) * step)) : clamped;
  } else {
    fail('unsupported', `Unknown camera control: ${String(name)}`);
  }
}

/** Classify the actual settings readback after a constraint is applied. */
export function cameraControlReadback(track, name, value, reported) {
  const requested = requestedCameraControlValue(ranges(track), name, value);
  const actual = reported?.[name];
  if (typeof requested === 'number') {
    if (typeof actual !== 'number' || !Number.isFinite(actual)) return { state: 'unreported' };
    const tolerance = 1e-6 * Math.max(1, Math.abs(requested));
    return { state: Math.abs(actual - requested) <= tolerance ? 'confirmed' : 'mismatch', actual };
  }
  if (typeof actual !== 'string') return { state: 'unreported' };
  return { state: actual === requested ? 'confirmed' : 'mismatch', actual };
}

/** Subscribe to a track ending; the caller supplies the accepted-track guard. */
export function watchCameraTrackEnd(track, isCurrent, onEnded) {
  const handleEnded = () => { if (isCurrent()) onEnded(); };
  track.addEventListener('ended', handleEnded);
  return () => track.removeEventListener('ended', handleEnded);
}

export async function applyCameraControl(track, name, value) {
  if (!track || track.readyState === 'ended') fail('stale-track', 'Camera track is no longer active');
  const requested = requestedCameraControlValue(ranges(track), name, value);

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
