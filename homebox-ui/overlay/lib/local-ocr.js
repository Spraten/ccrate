const TESSERACT_SCRIPT = 'https://cdn.jsdelivr.net/npm/tesseract.js@6.0.1/dist/tesseract.min.js';

let tesseractPromise;

/** @typedef {{ x0: number, y0: number, x1: number, y1: number }} OCRBox */
/** @typedef {{ text?: string, bbox?: OCRBox }} OCRLine */
/** @typedef {{ data?: { text?: string, blocks?: Array<{ paragraphs?: Array<{ lines?: OCRLine[] }> }>, lines?: OCRLine[] }, recognize: (source: Blob, options?: object, output?: { text?: boolean, blocks?: boolean }) => Promise<{ data?: { text?: string, blocks?: Array<{ paragraphs?: Array<{ lines?: OCRLine[] }> }>, lines?: OCRLine[] } }>, terminate: () => Promise<void> }} OCRWorker */
/** @typedef {{ createWorker: (language: string) => Promise<OCRWorker> }} TesseractEngine */
/** @type {typeof globalThis & { Tesseract?: TesseractEngine }} */
const runtime = globalThis;

function normalizeText(value) {
  return String(value || '').replace(/\s+/g, ' ').trim();
}

function isInstructionOrWarning(text) {
  const value = normalizeText(text).replace(/^[•*-]\s*/, '');
  const warningHeading = /^(?:caution|warning|danger|notice)\s*[:.!-]?$/i;
  const imperative = /^(?:read\s+(?:(?:all|the|these)\s+)?(?:instructions?|directions?|manual|guide|label)\b|record\s+(?:the\s+)?(?:serial|model|asset|lot)\s+(?:number|no\.?\b)|use\s+(?:only|as directed|according to)\b|keep\s+(?:away from|out of reach|closed|dry)\b|avoid\s+(?:contact|exposure)\b|do not\s+(?:use|open|ingest|operate|remove|expose)\b|don't\s+(?:use|open|ingest|operate|remove|expose)\b|for\s+(?:indoor|outdoor)\s+use only\b)/i;
  const warningPrefix = /^(?:caution|warning|danger|notice)\s*(?::|!|\.|-\s+)\s*/i;
  return warningHeading.test(value) || warningPrefix.test(value)
    || imperative.test(value.replace(warningPrefix, ''));
}

/** @param {OCRLine[] | undefined} lines @returns {string | null} */
function prominentTitle(lines) {
  const candidates = (lines || []).map((line, index) => {
    const box = line.bbox;
    const height = box ? box.y1 - box.y0 : 0;
    const width = box ? box.x1 - box.x0 : 0;
    return { index, text: normalizeText(line.text), box, height, width };
  }).filter(row => row.text && row.box
    && Number.isFinite(row.box.x0) && Number.isFinite(row.box.y0)
    && Number.isFinite(row.box.x1) && Number.isFinite(row.box.y1) && row.height > 0 && row.width > 0);

  if (!candidates.length) return '';
  const suitable = candidates.filter(row => !isInstructionOrWarning(row.text));
  if (!suitable.length) return null;
  const maxHeight = Math.max(...suitable.map(row => row.height));
  const ordered = suitable.filter(row => row.height >= maxHeight * 0.72)
    .sort((a, b) => a.box.y0 - b.box.y0 || a.box.x0 - b.box.x0 || a.index - b.index);
  if (!ordered.length) return null;

  const anchor = ordered.reduce((best, row) => row.height > best.height
    || (row.height === best.height && (row.box.y0 < best.box.y0
      || (row.box.y0 === best.box.y0 && row.box.x0 < best.box.x0))) ? row : best);
  const cluster = new Set([anchor]);
  const queue = [anchor];
  for (let cursor = 0; cursor < queue.length; cursor++) {
    const current = queue[cursor];
    for (const candidate of ordered) {
      if (cluster.has(candidate)) continue;
      const verticalGap = Math.max(0, Math.max(candidate.box.y0, current.box.y0)
        - Math.min(candidate.box.y1, current.box.y1));
      const horizontalGap = Math.max(0, Math.max(candidate.box.x0, current.box.x0)
        - Math.min(candidate.box.x1, current.box.x1));
      if (verticalGap <= Math.max(candidate.height, current.height) * 0.75
        && horizontalGap <= Math.max(candidate.height, current.height) * 1.5) {
        cluster.add(candidate);
        queue.push(candidate);
      }
    }
  }
  return ordered.filter(row => cluster.has(row)).map(row => row.text).join(' ');
}

/** Load the OCR runtime only after a user asks for a name suggestion. */
export function loadTesseract() {
  if (runtime.Tesseract) return Promise.resolve(runtime.Tesseract);
  if (tesseractPromise) return tesseractPromise;
  if (typeof document === 'undefined') return Promise.reject(new Error('Browser OCR is unavailable.'));

  /** @type {Promise<TesseractEngine>} */
  const pending = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = TESSERACT_SCRIPT;
    script.async = true;
    script.onload = () => runtime.Tesseract
      ? resolve(runtime.Tesseract)
      : reject(new Error('The browser OCR runtime did not initialize.'));
    script.onerror = () => reject(new Error('The browser OCR runtime could not be downloaded.'));
    document.head.append(script);
  });
  tesseractPromise = pending.catch(error => {
    tesseractPromise = undefined;
    throw error;
  });
  return tesseractPromise;
}

/**
 * Recognize text in a user-selected image entirely in this browser.
 * Tesseract.js fetches its code and English model on first use; the image is
 * passed to the local worker and is never sent to the OCR asset host.
 * @param {Blob} image
 * @param {() => Promise<TesseractEngine>} [loadEngine]
 * @returns {Promise<string | null>}
 */
export async function recognizeNameFromImage(image, loadEngine = loadTesseract) {
  const engine = await loadEngine();
  const worker = await engine.createWorker('eng');
  try {
    // Tesseract.js 6 returns only plain text by default. Request blocks so the
    // title selection can use the real line bounding boxes in its block tree.
    const result = await worker.recognize(image, {}, { text: true, blocks: true });
    const data = result.data;
    const blockLines = data?.blocks?.flatMap(block =>
      block.paragraphs?.flatMap(paragraph => paragraph.lines || []) || []);
    const title = prominentTitle(blockLines?.length ? blockLines : data?.lines);
    const suggestion = normalizeText(title === null ? '' : title || data?.text).slice(0, 255).trim();
    return suggestion || null;
  } finally {
    await worker.terminate();
  }
}

/** @returns {Promise<'applied' | 'empty' | 'edited-during-recognition' | 'stale'>} */
export async function suggestNameWithoutOverwritingEdits({ getName, getRevision = () => 0, setName, recognize, isCurrent = () => true, image }) {
  const initialName = getName();
  const initialRevision = getRevision();
  const suggestion = await recognize(image);
  if (!isCurrent()) return 'stale';
  if (!suggestion) return 'empty';
  if (getName() !== initialName || getRevision() !== initialRevision) return 'edited-during-recognition';
  setName(suggestion);
  return 'applied';
}

/** @returns {Promise<'applied' | 'empty' | 'edited-during-recognition' | 'stale'>} */
export async function applyRecognizedTextWithoutOverwritingEdits({ getText, getRevision = () => 0, setText, recognize, isCurrent = () => true, image }) {
  const initialText = getText();
  const initialRevision = getRevision();
  const recognized = await recognize(image);
  if (!isCurrent()) return 'stale';
  const text = typeof recognized === 'string' ? recognized : recognized?.text;
  if (!text?.trim()) return 'empty';
  if (getText() !== initialText || getRevision() !== initialRevision) return 'edited-during-recognition';
  setText(text);
  return 'applied';
}
/**
 * Recognize all text in a user-selected image entirely in this browser.
 * @param {Blob} image
 * @param {() => Promise<TesseractEngine>} [loadEngine]
 * @returns {Promise<{ text: string, lines: Array<{ text: string, bbox: OCRBox, confidence: number }>, imageWidth: number, imageHeight: number, confidence: number }>}
 */
export async function recognizeStructuredTextFromImage(image, loadEngine = loadTesseract) {
  const bitmap = await createImageBitmap(image);
  let worker;
  try {
    const canvas = document.createElement('canvas');
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    const context = canvas.getContext('2d');
    if (!context) throw new Error('Browser OCR image processing is unavailable.');
    context.drawImage(bitmap, 0, 0);
    const source = context.getImageData(0, 0, bitmap.width, bitmap.height);
    for (let i = 0; i < source.data.length; i += 4) {
      for (let channel = 0; channel < 3; channel++) {
        source.data[i + channel] = Math.max(0, Math.min(255, (source.data[i + channel] - 128) * 1.25 + 128));
      }
    }
    context.putImageData(source, 0, 0);
    const enhanced = await new Promise((resolve, reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('Could not prepare the image for browser OCR.'))));
    const engine = await loadEngine();
    worker = await engine.createWorker('eng');
    const passes = [
      { image, psm: 6 },
      { image, psm: 11 },
      { image: enhanced, psm: 6 },
      { image: enhanced, psm: 11 },
    ];
    let best;
    for (const pass of passes) {
      const result = await worker.recognize(pass.image, { tessedit_pageseg_mode: pass.psm }, { text: true, blocks: true });
      const data = result.data || {};
      const confidence = Number.isFinite(data.confidence) ? data.confidence : -Infinity;
      if (!best || confidence > best.confidence) best = { data, confidence };
    }
    const data = best?.data || {};
    const lines = (data.blocks || []).flatMap(block =>
      (block.paragraphs || []).flatMap(paragraph => paragraph.lines || []))
      .filter(line => {
        const box = line.bbox;
        return normalizeText(line.text) && box
          && [box.x0, box.y0, box.x1, box.y1].every(Number.isFinite)
          && box.x0 >= 0 && box.y0 >= 0
          && box.x1 <= bitmap.width && box.y1 <= bitmap.height
          && box.x1 > box.x0 && box.y1 > box.y0;
      })
      .map(line => ({ text: normalizeText(line.text), bbox: line.bbox, confidence: Number.isFinite(line.confidence) ? line.confidence : 0 }));
    return {
      text: normalizeText(data.text),
      lines,
      imageWidth: bitmap.width,
      imageHeight: bitmap.height,
      confidence: Number.isFinite(best?.confidence) ? best.confidence : 0,
    };
  } finally {
    try {
      if (worker) await worker.terminate();
    } finally {
      bitmap.close();
    }
  }
}

/**
 * Recognize text in an image. Browser callers use the richer local OCR flow;
 * non-browser callers retain the original plain-text worker path.
 * @param {Blob} image
 * @param {() => Promise<TesseractEngine>} [loadEngine]
 * @returns {Promise<string>}
 */
export async function recognizeTextFromImage(image, loadEngine = loadTesseract) {
  if (typeof document !== 'undefined' && typeof createImageBitmap === 'function') {
    const result = await recognizeStructuredTextFromImage(image, loadEngine);
    return result.text;
  }
  const engine = await loadEngine();
  const worker = await engine.createWorker('eng');
  try {
    const result = await worker.recognize(image);
    return normalizeText(result.data?.text);
  } finally {
    await worker.terminate();
  }
}
