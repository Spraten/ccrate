function normalize(value) {
  return String(value ?? '').trim().replace(/\s+/g, ' ').toLocaleLowerCase();
}

/** Rank active-item suggestions by normalized prefix, then substring, preserving ties. */
export function rankItemSuggestions(query, items) {
  if (!Array.isArray(items)) return [];
  const needle = normalize(query);
  if (!needle) return [];
  return items
    .map((item, index) => {
      const haystack = normalize([item?.name, item?.manufacturer, item?.model_number].filter(Boolean).join(' '));
      const position = haystack.indexOf(needle);
      return { item, index, rank: position === 0 ? 0 : position > 0 ? 1 : 2 };
    })
    .filter(row => row.rank < 2)
    .sort((a, b) => a.rank - b.rank || a.index - b.index)
    .map(row => row.item);
}
