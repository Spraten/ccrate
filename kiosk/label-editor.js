const LABEL_ACTIONS = new Set(['labels/templates', 'labels/templates/save', 'labels/templates/result', 'labels/preview', 'labels/paper', 'labels/print', 'touch-field']);
export function createLabelDesignerSaveHandlers({ workspace, setDirty, clearReviews, refresh, onTemplates, onError }) {
  return {
    designerDirty(value) { setDirty(value); },
    designerSaved() {
      workspace.templateId = '';
      clearReviews();
      Promise.resolve().then(refresh).then(onTemplates).catch(onError);
    },
  };
}

function secureNonce() {
  if (typeof globalThis.crypto?.randomUUID === 'function') return globalThis.crypto.randomUUID();
  const bytes = new Uint8Array(16); globalThis.crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
  return [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join('-');
}
export function mountLabelDesigner(container, options) {
  const nonce = secureNonce(), iframe = document.createElement('iframe');
  let disposed = false, dirty = false, busy = false, epoch = 0;
  const postContext = context => {
    const plainContext = context == null ? context : JSON.parse(JSON.stringify(context));
    iframe.contentWindow?.postMessage({ channel: 'label-designer', nonce, type: 'initialize', data: { context: plainContext, epoch } }, location.origin);
  };
  iframe.title = 'Label maker'; iframe.src = `${options.src}?nonce=${encodeURIComponent(nonce)}`;
  const fitFrame = () => {
    const available = window.innerHeight - container.getBoundingClientRect().top - 72;
    iframe.style.height = `${Math.max(390, Math.min(900, available))}px`;
  };
  iframe.className = 'label-designer-frame';
  fitFrame();
  window.addEventListener('resize', fitFrame);
  iframe.setAttribute('allow', 'clipboard-read; clipboard-write'); container.replaceChildren(iframe);
  const onMessage = async event => {
    if (disposed || event.origin !== location.origin || event.source !== iframe.contentWindow || event.data?.channel !== 'label-designer' || event.data.nonce !== nonce) return;
    const msg = event.data; options.activity?.();
    if (msg.type === 'session-activity') { options.activity?.(); return; }
    if (msg.type === 'dirty') { dirty = !!msg.data?.dirty; options.dirty?.(dirty); return; }
    if (msg.type === 'busy') { busy = !!msg.data?.busy; options.busy?.(busy); return; }
    if (msg.type === 'template-saved') { options.saved?.(msg.data); return; }
    if (msg.type === 'ready') { postContext(options.context?.()); return; }
    if (msg.type !== 'request' || !msg.id || !LABEL_ACTIONS.has(msg.action)) return;
    const requestEpoch = epoch;
    try {
      const context = options.context?.();
      const payload = msg.action === 'touch-field' || !msg.data || context?.generation == null ? msg.data : { ...msg.data, session_generation: context.generation, session_instance: context.instance };
      let result;
      if (msg.action === 'touch-field' && options.touchField) result = await options.touchField(payload);
      else if (msg.action === 'labels/print') {
        if (typeof options.write !== 'function') throw new Error('Physical printing requires a separate reviewed-item confirmation.');
        result = await options.write(msg.action, payload, 'Print reviewed item label', payload?.entity_id || 'label');
      } else if (msg.action === 'labels/templates/save') {
        if (typeof options.write !== 'function') throw new Error('Template saving requires a confirmed write handler.');
        result = await options.write(msg.action, payload, 'Save label template', payload?.id || 'labels');
      } else result = await options.request(msg.action, payload);
      if (disposed || epoch !== requestEpoch) return;
      iframe.contentWindow?.postMessage({ channel: 'label-designer', nonce, type: 'response', id: msg.id, ok: true, result }, location.origin);
    } catch (error) {
      if (disposed || epoch !== requestEpoch) return;
      iframe.contentWindow?.postMessage({ channel: 'label-designer', nonce, type: 'response', id: msg.id, ok: false, error: error.message || String(error), status: Number.isInteger(error?.status) ? error.status : undefined }, location.origin);
    }
  };
  window.addEventListener('message', onMessage); container.addEventListener('pointerdown', options.activity || (()=>{}), true); container.append(iframe);
  return { iframe, canLeave() { return !busy && (!dirty || window.confirm('Discard unsaved label design changes?')); }, updateContext(context) { if (!disposed) postContext(context); }, invalidate() { epoch++; dirty = false; options.dirty?.(false); }, dispose() { if (disposed) return; disposed = true; epoch++; window.removeEventListener('resize', fitFrame); window.removeEventListener('message', onMessage); container.replaceChildren(); } };
}

export const createLabelEditorFrame = mountLabelDesigner;

export async function exportReviewedPaper(renderUrl, result, format, isCurrent = () => true) {
  if (!['print', 'pdf'].includes(format) || !Array.isArray(result?.pages) || !result.pages.length || result.pages.length > 2 || result.geometry?.dpi !== 300 || result.geometry.page_mm?.join(',') !== '215.9,279.4') throw new Error('Review a valid Letter sheet before exporting.');
  const frame = document.createElement('iframe'); frame.title = 'Reviewed paper exporter'; frame.className = 'reviewed-paper-export-frame'; frame.src = renderUrl;
  document.body.append(frame);
  try {
    await new Promise((resolve, reject) => { const timer = setTimeout(() => reject(new Error('Offline label exporter did not load.')), 10000); frame.onload = () => { clearTimeout(timer); resolve(); }; frame.onerror = () => { clearTimeout(timer); reject(new Error('Offline label exporter did not load.')); }; });
    if (!isCurrent()) throw new Error('Your account, collection or label review changed. Review again before exporting.');
    const exporter = frame.contentWindow?.exportReviewedPaper;
    if (typeof exporter !== 'function') throw new Error('Offline label export asset is missing. Rebuild the matched label bundle.');
    const output = await exporter(result.pages, result.geometry, format, isCurrent);
    if (!isCurrent()) throw new Error('Your account, collection or label review changed. Review again before exporting.');
    if (format === 'pdf') {
      if (!output || output.type !== 'application/pdf' || output.size < 8) throw new Error('PDF export did not return a valid document.');
      const url = URL.createObjectURL(output), link = document.createElement('a'); link.href = url; link.download = 'reviewed-labels-letter.pdf'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      return 'PDF download requested. The reviewed pages remain available.';
    }
    return 'Print dialog closed. Physical output is unconfirmed; the reviewed pages remain available.';
  } finally { frame.remove(); }
}
