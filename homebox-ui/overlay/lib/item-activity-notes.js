export function recentItemNotes(rows = [], itemId, limit = 5) {
  const notes = [];

  for (const row of rows) {
    const belongsToItem = !Array.isArray(row.assets) || row.assets.includes(itemId);

    for (const [source, kind] of [['checkout_notes', 'checkout'], ['return_notes', 'return']]) {
      for (const note of row[source] || []) {
        if (note.entity_id ? note.entity_id !== itemId : !belongsToItem) continue;
        notes.push({
          text: note.text,
          author: note.author || null,
          created_at: note.created_at || null,
          kind,
        });
      }
    }

    if (row.action === 'add_note' && row.note_text && belongsToItem) {
      const edited = row.note_state === 'edited' || row.note_current_text_attribution === 'unknown';
      notes.push({
        text: row.note_text,
        author: edited ? null : row.note_author || row.actor || null,
        created_at: row.confirmed_at || row.created_at || null,
        kind: 'item',
        note_state: row.note_state,
        note_current_text_attribution: row.note_current_text_attribution,
      });
    }
  }

  return notes.sort((a, b) => {
    const aTime = Date.parse(a.created_at || '');
    const bTime = Date.parse(b.created_at || '');
    if (Number.isNaN(aTime)) return Number.isNaN(bTime) ? 0 : 1;
    if (Number.isNaN(bTime)) return -1;
    return bTime - aTime;
  }).slice(0, Math.max(0, limit));
}
