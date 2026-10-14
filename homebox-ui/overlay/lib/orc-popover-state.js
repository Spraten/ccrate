/** @typedef {{ enabled: boolean, open: boolean }} OcrPopoverState */

/** @param {OcrPopoverState} state @param {'toggle-enabled' | 'open' | 'close'} action @returns {OcrPopoverState} */
export function nextOcrPopoverState(state, action) {
  if (action === 'toggle-enabled') return { enabled: !state.enabled, open: false };
  if (action === 'open') return state.enabled ? { enabled: true, open: true } : { ...state };
  if (action === 'close') return { enabled: state.enabled, open: false };
  return { ...state };
}
