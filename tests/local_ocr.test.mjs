import assert from 'node:assert/strict';
import test from 'node:test';
import { recognizeNameFromImage, suggestNameWithoutOverwritingEdits } from '../homebox-ui/overlay/lib/local-ocr.js';

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
