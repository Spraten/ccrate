/** @typedef {{ enabled: boolean, open: boolean }} OcrPopoverState */

/** @param {OcrPopoverState} state @param {'toggle-enabled' | 'open' | 'close'} action @returns {OcrPopoverState} */
export function nextOcrPopoverState(state, action) {
  if (action === 'toggle-enabled') return { enabled: !state.enabled, open: false };
  if (action === 'open') return state.enabled ? { enabled: true, open: true } : { ...state };
  if (action === 'close') return { enabled: state.enabled, open: false };
  return { ...state };
}

/** @param {number} captureGeneration @param {number} currentGeneration @param {{ enabled: boolean, open: boolean, minimized: boolean, cameraActive: boolean, disposed: boolean }} state */
export function isOcrCaptureCurrent(captureGeneration, currentGeneration, state) {
  return captureGeneration === currentGeneration
    && state.enabled && state.open && !state.minimized && state.cameraActive && !state.disposed;
}

/** @param {number} scanGeneration @param {number} currentGeneration @param {{ enabled: boolean, open: boolean, minimized: boolean, disposed: boolean }} state */
export function isOcrScanCurrent(scanGeneration, currentGeneration, state) {
  return scanGeneration === currentGeneration
    && state.enabled && state.open && !state.minimized && !state.disposed;
}