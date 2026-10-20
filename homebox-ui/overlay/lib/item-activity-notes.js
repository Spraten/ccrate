export function recentItemNotes(rows = [], itemId, limit = 5) {
  return rows.flatMap(row => [
    ...(row.checkout_notes || []).filter(note => note.entity_id === itemId)
      .map(note => ({ ...note, kind: 'checkout' })),
    ...(row.return_notes || []).filter(note => !note.entity_id || note.entity_id === itemId)
      .map(note => ({ ...note, kind: 'return' })),
    ...(row.action === 'add_note' && row.note_text && row.note_state !== 'edited'
      && row.note_current_text_attribution !== 'unknown'
      ? [{ text: row.note_text, author: row.note_author || row.actor, created_at: row.confirmed_at || row.created_at, kind: 'item', note_state: row.note_state, note_current_text_attribution: row.note_current_text_attribution }]
      : []),
  ]).sort((a, b) => Date.parse(b.created_at || '') - Date.parse(a.created_at || '')).slice(0, Math.max(0, limit));
}
