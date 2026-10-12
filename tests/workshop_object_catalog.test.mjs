import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { workshopObjectPresets, workshopPresetForDrawing } from '../homebox-ui/overlay/lib/workshop-object-catalog.js';

const assetDirectory = fileURLToPath(new URL('../homebox-ui/overlay/public/workshop/objects/', import.meta.url));
const schemaSource = await readFile(new URL('../ops/workshop.py', import.meta.url), 'utf8');
const schemaKinds = new Set([...schemaSource.match(/KINDS\s*=\s*\(([^)]*)\)/)?.[1].matchAll(/'([^']+)'/g) || []].map((match) => match[1]));

test('catalog presets have unique ids, supported kinds, positive dimensions, and same-origin assets', async () => {
  assert.ok(workshopObjectPresets.length >= 20);
  assert.equal(new Set(workshopObjectPresets.map(({ id }) => id)).size, workshopObjectPresets.length);
  const normalizedArtwork = new Set();
  for (const preset of workshopObjectPresets) {
    assert.ok(schemaKinds.has(preset.kind), preset.kind);
    assert.ok(preset.width > 0 && preset.depth > 0, preset.id);
    assert.match(preset.asset, /^\/workshop\/objects\/[a-z0-9-]+\.svg$/);
    const svg = await readFile(`${assetDirectory}/${preset.id}.svg`, 'utf8');
    assert.match(svg, /<svg\b[^>]*viewBox=/);
    assert.doesNotMatch(svg, /<script\b|<text\b|<foreignObject\b|(?:href|src)=['"](?:https?:|data:|\/\/)/i);
    assert.ok(!normalizedArtwork.has(svg.replace(/#[\da-f]{3,8}\b/gi, '#COLOR')), `${preset.id} must depict distinct geometry, not just a recolor`);
    normalizedArtwork.add(svg.replace(/#[\da-f]{3,8}\b/gi, '#COLOR'));
  }
  assert.deepEqual([...new Set(workshopObjectPresets.map(({ category }) => category))], [
    'Shelves', 'Cabinets', 'Drawers', 'Bins', 'Work surfaces', 'Structure', 'Machines',
  ]);
});

test('known drawings match by existing kind and name while custom names safely fall back', () => {
  const preset = workshopObjectPresets.find(({ name }) => name === 'Wall cabinet');
  assert.equal(preset.kind, 'Cabinet');
  assert.equal(workshopPresetForDrawing({ kind: preset.kind, name: '  WALL CABINET ' }), preset);
  assert.equal(workshopPresetForDrawing({ kind: 'Misc', name: 'Wall cabinet' }), null);
  assert.equal(workshopPresetForDrawing({ kind: 'Custom', name: 'https://example.invalid/unsafe.svg' }), null);
  assert.equal(workshopPresetForDrawing({ kind: preset.kind, name: 'Renamed cabinet' }), null);
  assert.equal(workshopPresetForDrawing(null), null);

  const drawing = { id: 'native-link-preserved', kind: preset.kind, name: 'Wall cabinet', x: 2, y: 3, width: 3, height: 1, location_id: 'native-location' };
  const before = structuredClone(drawing);
  assert.equal(workshopPresetForDrawing(drawing), preset);
  assert.deepEqual(drawing, before);
});
