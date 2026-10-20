export const PACKAGING_OPTIONS = Object.freeze(['Original Packaging', 'No Packaging', 'HardCase', 'Softcase', 'Bag', 'Misc']);
const fold = value => String(value ?? '').trim().replace(/\s+/g, ' ').toLocaleLowerCase();

export function createSuggestionLookup(fetchSuggestions) {
  let generation = 0;
  return {
    invalidate() { generation++; },
    async search(typeId, query) {
      const current = ++generation;
      if (!typeId || !String(query || '').trim()) return [];
      const rows = await fetchSuggestions(typeId, query);
      return current === generation ? (Array.isArray(rows) ? rows.slice(0, 8) : []) : [];
    },
  };
}

export function selectSuggestion(form, item) {
  form.name = String(item.name || '');
  form.manufacturer = String(item.manufacturer || '');
  form.modelNumber = String(item.modelNumber || '');
  form.modelCode = String(item.modelCode || '');
  form.tags = Array.isArray(item.tagIds) ? [...item.tagIds] : [];
  form.serialNumber = '';
}

export function validateCustomRows(rows) {
  const seen = new Set(['device packaging']);
  return (rows || []).map(row => ({ name: String(row.name || '').trim().replace(/\s+/g, ' '), value: String(row.value || ''), note: String(row.note || '') })).filter(row => row.name || row.value || row.note).map(row => {
    if (!row.name) throw new Error('Enter a name for every custom field.');
    const key = fold(row.name);
    if (seen.has(key)) throw new Error(`Duplicate custom field: ${row.name}`);
    seen.add(key);
    if (row.name.length > 255 || row.value.length > 8000 || row.note.length > 2000) throw new Error('A custom field is too long.');
    return row;
  });
}

function fieldMap(fields) {
  const map = new Map();
  for (const field of fields || []) {
    const key = fold(field.name);
    if (map.has(key)) throw new Error(`Duplicate native field ${field.name} needs review.`);
    map.set(key, field);
  }
  return map;
}

export function buildNativeMetadataUpdate(current, draft) {
  const rows = validateCustomRows(draft.rows);
  if (draft.packaging && !PACKAGING_OPTIONS.includes(draft.packaging)) throw new Error('Choose a listed packaging value.');
  const fields = (current.fields || []).map(field => ({ ...field }));
  const existing = fieldMap(fields);
  const changes = [...rows.map(row => ({ name: row.name, value: row.value }))];
  if (draft.packaging) changes.push({ name: 'Device Packaging', value: draft.packaging });
  for (const change of changes) {
    const prior = existing.get(fold(change.name));
    if (prior && prior.type !== 'text') throw new Error(`${change.name} is not a text field and needs review.`);
    if (prior) prior.textValue = change.value;
    else fields.push({ name: change.name, type: 'text', textValue: change.value, numberValue: 0, booleanValue: false });
  }
  const { displayId, shortCode, parent, entityType, tags, attachments, children, ...native } = current;
  return { ...native, serialNumber: String(draft.serialNumber || ''), fields, parentId: parent?.id || null, entityTypeId: entityType?.id || '', tagIds: (tags || []).map(tag => tag.id) };
}

export function nativeMetadataMatches(item, draft) {
  try {
    if (String(item.serialNumber || '') !== String(draft.serialNumber || '')) return false;
    const fields = fieldMap(item.fields || []);
    if (draft.packaging && String(fields.get('device packaging')?.textValue || '') !== draft.packaging) return false;
    return validateCustomRows(draft.rows).every(row => String(fields.get(fold(row.name))?.textValue || '') === row.value);
  } catch { return false; }
}
