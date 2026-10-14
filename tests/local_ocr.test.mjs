import assert from 'node:assert/strict';
import test from 'node:test';
import { applyRecognizedTextWithoutOverwritingEdits, recognizeNameFromImage, recognizeTextFromImage, suggestNameWithoutOverwritingEdits } from '../homebox-ui/overlay/lib/local-ocr.js';

test('full-text OCR receives the image locally, normalizes whitespace, and terminates its worker', async () => {
  const image = new Blob(['private photo']);
  let receivedImage;
  let terminated = false;
  const result = await recognizeTextFromImage(image, async () => ({
    createWorker: async language => {
      assert.equal(language, 'eng');
      return {
        recognize: async source => {
          receivedImage = source;
          return { data: { text: '  First line\n\n Second\tline  ' } };
        },
        terminate: async () => { terminated = true; },
      };
    },
  }));

  assert.equal(result, 'First line Second line');
  assert.equal(receivedImage, image);
  assert.equal(terminated, true);
});

test('late OCR results never replace a name the user typed while recognition was running', async () => {
  let currentName = '';
  let resolveRecognition;
  const pending = new Promise(resolve => { resolveRecognition = resolve; });
  const result = suggestNameWithoutOverwritingEdits({
    getName: () => currentName,
    setName: value => { currentName = value; },
    recognize: () => pending,
    image: { local: true },
  });

  currentName = 'User-entered part name';
  resolveRecognition('OCR package heading');
  assert.equal(await result, 'edited-during-recognition');
  assert.equal(currentName, 'User-entered part name');
});
test('OCR respects an edit even if the user changes the name back to its original value', async () => {
  let currentName = 'Original';
  let editRevision = 0;
  let resolveRecognition;
  const pending = new Promise(resolve => { resolveRecognition = resolve; });
  const result = suggestNameWithoutOverwritingEdits({
    getName: () => currentName,
    getRevision: () => editRevision,
    setName: value => { currentName = value; },
    recognize: () => pending,
    image: { local: true },
  });

  currentName = 'User typed this';
  editRevision++;
  currentName = 'Original';
  editRevision++;
  resolveRecognition('OCR package heading');
  assert.equal(await result, 'edited-during-recognition');
  assert.equal(currentName, 'Original');
});

test('OCR receives the image in the browser and terminates its worker after recognition', async () => {
  const image = new Blob(['private photo']);
  let receivedImage;
  let terminated = false;
  const result = await recognizeNameFromImage(image, async () => ({
    createWorker: async language => {
      assert.equal(language, 'eng');
      return {
        recognize: async source => {
          receivedImage = source;
          return { data: { text: '  Eventronic ET1001  ' } };
        },
        terminate: async () => { terminated = true; },
      };
    },
  }));

  assert.equal(result, 'Eventronic ET1001');
  assert.equal(receivedImage, image);
  assert.equal(terminated, true);
});

test('OCR prefers a prominent, spatially aligned title and leaves small serial/footer text out', async () => {
  const data = {
    text: 'EVENTRONIC ET1001 560-Piece Heat Shrink Tube Assortment 125°C 60pcs web example.com',
    blocks: [{ paragraphs: [{ lines: [
      { text: 'EVENTRONIC', bbox: { x0: 60, y0: 40, x1: 270, y1: 81 } },
      { text: 'ET1001 560-Piece', bbox: { x0: 280, y0: 40, x1: 610, y1: 81 } },
      { text: 'Heat Shrink Tube Assortment', bbox: { x0: 60, y0: 86, x1: 600, y1: 126 } },
      { text: '125°C 60pcs', bbox: { x0: 62, y0: 160, x1: 190, y1: 176 } },
      { text: 'web example.com', bbox: { x0: 60, y0: 420, x1: 220, y1: 432 } },
    ] }] }],
  };
  let outputOptions;
  const suggestion = await recognizeNameFromImage(new Blob(['label']), async () => ({
    createWorker: async () => ({ recognize: async (_image, _options, output) => { outputOptions = output; return { data }; }, terminate: async () => undefined }),
  }));

  assert.deepEqual(outputOptions, { text: true, blocks: true });
  assert.equal(suggestion, 'EVENTRONIC ET1001 560-Piece Heat Shrink Tube Assortment');
});

test('OCR keeps a short product title separate from a lower same-size instruction line', async () => {
  const data = {
    text: 'AEROGARD Read all instructions before use and record serial number 845193',
    blocks: [{ paragraphs: [{ lines: [
      { text: 'AEROGARD', bbox: { x0: 70, y0: 42, x1: 220, y1: 74 } },
      { text: 'Read all instructions before use and record serial number 845193', bbox: { x0: 70, y0: 101, x1: 590, y1: 133 } },
    ] }] }],
  };
  const suggestion = await recognizeNameFromImage(new Blob(['label']), async () => ({
    createWorker: async () => ({ recognize: async () => ({ data }), terminate: async () => undefined }),
  }));

  assert.equal(suggestion, 'AEROGARD');
});

test('OCR keeps a close-spaced subtitle with the product title', async () => {
  const data = {
    text: 'AEROGARD Portable Water Filter',
    blocks: [{ paragraphs: [{ lines: [
      { text: 'AEROGARD', bbox: { x0: 70, y0: 42, x1: 220, y1: 74 } },
      { text: 'Portable Water Filter', bbox: { x0: 70, y0: 94, x1: 360, y1: 126 } },
    ] }] }],
  };
  const suggestion = await recognizeNameFromImage(new Blob(['label']), async () => ({
    createWorker: async () => ({ recognize: async () => ({ data }), terminate: async () => undefined }),
  }));

  assert.equal(suggestion, 'AEROGARD Portable Water Filter');
});

test('OCR does not let a close-spaced subtitle pull in lower instructions', async () => {
  const data = {
    text: 'AEROGARD Portable Water Filter Read instructions before use',
    blocks: [{ paragraphs: [{ lines: [
      { text: 'AEROGARD', bbox: { x0: 70, y0: 42, x1: 220, y1: 74 } },
      { text: 'Portable Water Filter', bbox: { x0: 70, y0: 94, x1: 360, y1: 126 } },
      { text: 'Read instructions before use', bbox: { x0: 70, y0: 150, x1: 440, y1: 182 } },
    ] }] }],
  };
  const suggestion = await recognizeNameFromImage(new Blob(['label']), async () => ({
    createWorker: async () => ({ recognize: async () => ({ data }), terminate: async () => undefined }),
  }));

  assert.equal(suggestion, 'AEROGARD Portable Water Filter');
});

test('OCR includes a subtitle 24px below its title', async () => {
  const data = {
    text: 'AEROGARD Portable Water Filter',
    blocks: [{ paragraphs: [{ lines: [
      { text: 'AEROGARD', bbox: { x0: 70, y0: 42, x1: 220, y1: 74 } },
      { text: 'Portable Water Filter', bbox: { x0: 70, y0: 98, x1: 360, y1: 130 } },
    ] }] }],
  };
  const suggestion = await recognizeNameFromImage(new Blob(['label']), async () => ({
    createWorker: async () => ({ recognize: async () => ({ data }), terminate: async () => undefined }),
  }));

  assert.equal(suggestion, 'AEROGARD Portable Water Filter');
});

test('OCR does not let lower instructions bridge a title and subtitle cluster', async () => {
  const data = {
    text: 'AEROGARD Portable Water Filter Read instructions before use',
    blocks: [{ paragraphs: [{ lines: [
      { text: 'AEROGARD', bbox: { x0: 70, y0: 42, x1: 320, y1: 82 } },
      { text: 'Portable Water Filter', bbox: { x0: 70, y0: 106, x1: 520, y1: 146 } },
      { text: 'Read instructions before use', bbox: { x0: 70, y0: 170, x1: 430, y1: 202 } },
    ] }] }],
  };
  const suggestion = await recognizeNameFromImage(new Blob(['label']), async () => ({
    createWorker: async () => ({ recognize: async () => ({ data }), terminate: async () => undefined }),
  }));

  assert.equal(suggestion, 'AEROGARD Portable Water Filter');
});

test('OCR skips a standalone caution heading when selecting a wider product title', async () => {
  const data = {
    text: 'CAUTION AEROGARD Portable Water Filter',
    blocks: [{ paragraphs: [{ lines: [
      { text: 'CAUTION', bbox: { x0: 70, y0: 42, x1: 220, y1: 74 } },
      { text: 'AEROGARD Portable Water Filter', bbox: { x0: 70, y0: 140, x1: 570, y1: 172 } },
    ] }] }],
  };
  const suggestion = await recognizeNameFromImage(new Blob(['label']), async () => ({
    createWorker: async () => ({ recognize: async () => ({ data }), terminate: async () => undefined }),
  }));

  assert.equal(suggestion, 'AEROGARD Portable Water Filter');
});

test('OCR keeps a Record Player title with its model line', async () => {
  const data = {
    text: 'Record Player Model 1234',
    blocks: [{ paragraphs: [{ lines: [
      { text: 'Record Player', bbox: { x0: 70, y0: 42, x1: 290, y1: 74 } },
      { text: 'Model 1234', bbox: { x0: 70, y0: 82, x1: 250, y1: 114 } },
    ] }] }],
  };
  const suggestion = await recognizeNameFromImage(new Blob(['label']), async () => ({
    createWorker: async () => ({ recognize: async () => ({ data }), terminate: async () => undefined }),
  }));

  assert.equal(suggestion, 'Record Player Model 1234');
});

test('OCR keeps a Caution Tape title', async () => {
  const data = {
    text: 'Caution Tape',
    blocks: [{ paragraphs: [{ lines: [
      { text: 'Caution Tape', bbox: { x0: 70, y0: 42, x1: 300, y1: 74 } },
    ] }] }],
  };
  const suggestion = await recognizeNameFromImage(new Blob(['label']), async () => ({
    createWorker: async () => ({ recognize: async () => ({ data }), terminate: async () => undefined }),
  }));

  assert.equal(suggestion, 'Caution Tape');
});

test('OCR keeps a hyphenated Caution-Tape title', async () => {
  const data = {
    text: 'Caution-Tape',
    blocks: [{ paragraphs: [{ lines: [
      { text: 'Caution-Tape', bbox: { x0: 70, y0: 42, x1: 300, y1: 74 } },
    ] }] }],
  };
  const suggestion = await recognizeNameFromImage(new Blob(['label']), async () => ({
    createWorker: async () => ({ recognize: async () => ({ data }), terminate: async () => undefined }),
  }));

  assert.equal(suggestion, 'Caution-Tape');
});

test('OCR keeps a Warning-Label Roll title', async () => {
  const data = {
    text: 'Warning-Label Roll',
    blocks: [{ paragraphs: [{ lines: [
      { text: 'Warning-Label Roll', bbox: { x0: 70, y0: 42, x1: 360, y1: 74 } },
    ] }] }],
  };
  const suggestion = await recognizeNameFromImage(new Blob(['label']), async () => ({
    createWorker: async () => ({ recognize: async () => ({ data }), terminate: async () => undefined }),
  }));

  assert.equal(suggestion, 'Warning-Label Roll');
});

test('OCR keeps a three-line product title together', async () => {
  const data = {
    text: 'AEROGARD Portable Water Filter System',
    blocks: [{ paragraphs: [{ lines: [
      { text: 'AEROGARD', bbox: { x0: 70, y0: 42, x1: 270, y1: 74 } },
      { text: 'Portable Water', bbox: { x0: 70, y0: 82, x1: 360, y1: 114 } },
      { text: 'Filter System', bbox: { x0: 70, y0: 122, x1: 320, y1: 154 } },
    ] }] }],
  };
  const suggestion = await recognizeNameFromImage(new Blob(['label']), async () => ({
    createWorker: async () => ({ recognize: async () => ({ data }), terminate: async () => undefined }),
  }));

  assert.equal(suggestion, 'AEROGARD Portable Water Filter System');
});

test('OCR returns no name when every prominent line is an instruction', async () => {
  const data = {
    text: 'Read all instructions before use Record serial number 845193',
    blocks: [{ paragraphs: [{ lines: [
      { text: 'Read all instructions before use', bbox: { x0: 70, y0: 42, x1: 470, y1: 74 } },
      { text: 'Record serial number 845193', bbox: { x0: 70, y0: 82, x1: 440, y1: 114 } },
    ] }] }],
  };
  const suggestion = await recognizeNameFromImage(new Blob(['label']), async () => ({
    createWorker: async () => ({ recognize: async () => ({ data }), terminate: async () => undefined }),
  }));

  assert.equal(suggestion, null);
});

test('OCR ignores a warning-prefixed instruction above the product title', async () => {
  const data = {
    text: 'WARNING: Read all instructions before use AEROGARD Portable Water Filter',
    blocks: [{ paragraphs: [{ lines: [
      { text: 'WARNING: Read all instructions before use', bbox: { x0: 70, y0: 42, x1: 520, y1: 74 } },
      { text: 'AEROGARD Portable Water Filter', bbox: { x0: 70, y0: 96, x1: 570, y1: 128 } },
    ] }] }],
  };
  const suggestion = await recognizeNameFromImage(new Blob(['label']), async () => ({
    createWorker: async () => ({ recognize: async () => ({ data }), terminate: async () => undefined }),
  }));

  assert.equal(suggestion, 'AEROGARD Portable Water Filter');
});

test('OCR skips a punctuated warning heading above the product title', async () => {
  const data = {
    text: 'WARNING: Choking hazard AEROGARD Portable Water Filter',
    blocks: [{ paragraphs: [{ lines: [
      { text: 'WARNING: Choking hazard', bbox: { x0: 70, y0: 42, x1: 390, y1: 74 } },
      { text: 'AEROGARD Portable Water Filter', bbox: { x0: 70, y0: 96, x1: 570, y1: 128 } },
    ] }] }],
  };
  const suggestion = await recognizeNameFromImage(new Blob(['label']), async () => ({
    createWorker: async () => ({ recognize: async () => ({ data }), terminate: async () => undefined }),
  }));

  assert.equal(suggestion, 'AEROGARD Portable Water Filter');
});

test('OCR selects a 28px product title below a taller warning heading', async () => {
  const data = {
    text: 'WARNING AEROGARD Portable Water Filter',
    blocks: [{ paragraphs: [{ lines: [
      { text: 'WARNING', bbox: { x0: 70, y0: 42, x1: 220, y1: 82 } },
      { text: 'AEROGARD Portable Water Filter', bbox: { x0: 70, y0: 100, x1: 570, y1: 128 } },
    ] }] }],
  };
  const suggestion = await recognizeNameFromImage(new Blob(['label']), async () => ({
    createWorker: async () => ({ recognize: async () => ({ data }), terminate: async () => undefined }),
  }));

  assert.equal(suggestion, 'AEROGARD Portable Water Filter');
});

test('OCR keeps indoor-use copy out of a wrapped three-line product title', async () => {
  const data = {
    text: 'AEROGARD Portable Water Filter System For indoor use only',
    blocks: [{ paragraphs: [{ lines: [
      { text: 'AEROGARD', bbox: { x0: 70, y0: 42, x1: 270, y1: 74 } },
      { text: 'Portable Water', bbox: { x0: 70, y0: 82, x1: 360, y1: 114 } },
      { text: 'Filter System', bbox: { x0: 70, y0: 122, x1: 320, y1: 154 } },
      { text: 'For indoor use only', bbox: { x0: 70, y0: 162, x1: 350, y1: 194 } },
    ] }] }],
  };
  const suggestion = await recognizeNameFromImage(new Blob(['label']), async () => ({
    createWorker: async () => ({ recognize: async () => ({ data }), terminate: async () => undefined }),
  }));

  assert.equal(suggestion, 'AEROGARD Portable Water Filter System');
});

test('full-text OCR preserves footer text and text beyond the name suggestion limit', async () => {
  const longBody = '0123456789 '.repeat(30);
  const recognizedText = `PROMINENT TITLE\n${longBody}\nSmall footer text`;
  const result = await recognizeTextFromImage(new Blob(['label']), async () => ({
    createWorker: async () => ({
      recognize: async () => ({ data: { text: recognizedText } }),
      terminate: async () => undefined,
    }),
  }));

  assert.equal(result, `PROMINENT TITLE ${longBody.trimEnd()} Small footer text`);
});

test('full-text OCR does not replace edits made while recognition is running', async () => {
  let currentText = 'Earlier scan';
  let revision = 0;
  let resolveRecognition;
  const pending = new Promise(resolve => { resolveRecognition = resolve; });
  const result = applyRecognizedTextWithoutOverwritingEdits({
    getText: () => currentText,
    getRevision: () => revision,
    setText: value => { currentText = value; },
    recognize: () => pending,
    image: { local: true },
  });

  currentText = 'My corrected notes';
  revision++;
  resolveRecognition('OCR result');
  assert.equal(await result, 'edited-during-recognition');
  assert.equal(currentText, 'My corrected notes');
});

test('full-text OCR respects edits even when the user restores the previous text', async () => {
  let currentText = 'Earlier scan';
  let revision = 0;
  let resolveRecognition;
  const pending = new Promise(resolve => { resolveRecognition = resolve; });
  const result = applyRecognizedTextWithoutOverwritingEdits({
    getText: () => currentText,
    getRevision: () => revision,
    setText: value => { currentText = value; },
    recognize: () => pending,
    image: { local: true },
  });

  currentText = 'My corrected notes';
  revision++;
  currentText = 'Earlier scan';
  revision++;
  resolveRecognition('OCR result');
  assert.equal(await result, 'edited-during-recognition');
  assert.equal(currentText, 'Earlier scan');
});

test('full-text OCR discards recognition for a photo that was retaken while scanning', async () => {
  let currentText = '';
  let currentImage = { id: 'first' };
  const scannedImage = currentImage;
  let resolveRecognition;
  const pending = new Promise(resolve => { resolveRecognition = resolve; });
  const result = applyRecognizedTextWithoutOverwritingEdits({
    getText: () => currentText,
    setText: value => { currentText = value; },
    recognize: () => pending,
    isCurrent: () => currentImage === scannedImage,
    image: scannedImage,
  });

  currentImage = { id: 'retake' };
  resolveRecognition('Text from the first photo');
  assert.equal(await result, 'stale');
  assert.equal(currentText, '');
});
