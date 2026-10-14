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

/** @param {OCRLine[] | undefined} lines */
function prominentTitle(lines) {
  const candidates = (lines || []).map((line, index) => {
    const box = line.bbox;
    const height = box ? box.y1 - box.y0 : 0;
    const width = box ? box.x1 - box.x0 : 0;
    return { index, text: normalizeText(line.text), box, height, width };
  }).filter(row => row.text && row.box && Number.isFinite(row.box.x0) && Number.isFinite(row.box.y0)
    && Number.isFinite(row.box.x1) && Number.isFinite(row.box.y1) && row.height > 0 && row.width > 0);

  if (!candidates.length) return '';
  const maxHeight = Math.max(...candidates.map(row => row.height));
  const ordered = candidates.filter(row => row.height >= maxHeight * 0.72)
    .sort((a, b) => a.box.y0 - b.box.y0 || a.box.x0 - b.box.x0 || a.index - b.index);
  if (!ordered.length) return '';

  const anchor = ordered.reduce((best, row) => row.height > best.height
    || (row.height === best.height && row.width * row.height > best.width * best.height) ? row : best);
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
      if (verticalGap <= Math.max(candidate.height, current.height) * 1.5
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
    const lines = prominentTitle(blockLines?.length ? blockLines : data?.lines);
    const suggestion = normalizeText(lines || data?.text).slice(0, 255).trim();
    return suggestion || null;
  } finally {
    await worker.terminate();
  }
}

/** @returns {Promise<'applied' | 'empty' | 'edited-during-recognition'>} */
export async function suggestNameWithoutOverwritingEdits({ getName, getRevision = () => 0, setName, recognize, image }) {
  const initialName = getName();
  const initialRevision = getRevision();
  const suggestion = await recognize(image);
  if (!suggestion) return 'empty';
  if (getName() !== initialName || getRevision() !== initialRevision) return 'edited-during-recognition';
  setName(suggestion);
  return 'applied';
}
