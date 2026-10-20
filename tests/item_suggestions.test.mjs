import test from 'node:test';
import assert from 'node:assert/strict';
import { rankItemSuggestions } from '../homebox-ui/overlay/lib/item-suggestions.js';

test('normalizes case and whitespace and ranks prefixes before substrings stably', () => {
  const a = { name: 'Drone Pro' }, b = { name: 'Pro Drone' }, c = { name: 'drone case' };
  assert.deepEqual(rankItemSuggestions('  DRONE   ', [a, b, c]), [a, c, b]);
});

test('matches partial words in shared model text and preserves ties', () => {
  const a = { name: 'Camera', manufacturer: 'Acme Imaging' }, b = { name: 'Camera', manufacturer: 'Acme' };
  assert.deepEqual(rankItemSuggestions(' imag ', [a, b]), [a]);
});

test('empty query and empty list return no suggestions', () => {
  assert.deepEqual(rankItemSuggestions('', [{ name: 'Drone' }]), []);
  assert.deepEqual(rankItemSuggestions('drone', []), []);
});
