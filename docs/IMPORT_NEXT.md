# Import planning — awaiting source identification

User explicitly requested Admin import on 3 October 2026; this supersedes the original future-scope exclusion for CSV imports.

Target: native Homebox records via its supported API. Preserve source IDs as provenance, not replacement native UUIDs. Keep the existing kiosk ledger and custody separate.

Before implementing source-specific import, obtain the program name and a representative export with column headings. Prefer a CSV or Excel export where the source offers one; do not assume an Access database or Power Apps backend can be read directly on the Pi.

Recommended flow: choose file, map columns, preview rows and native destinations, highlight missing/invalid values and duplicate source IDs or serials, confirm the reviewed batch, then show created/skipped/review outcomes. Re-import should detect prior source IDs and avoid duplicates. Use durable per-row native jobs and lost-response reconciliation rather than blind retries.

Preserve names, manufacturer/model, serial, notes, source asset number and location hierarchy where actually present. Do not infer a Ready inspection or active custody from undocumented source values. Imported conditions require an explicit reviewed mapping; unknown equipment stays Unreviewed. Attachments and historical loans need separate source capabilities and mappings.

Pending: source identification; available export format; actual columns; condition and location mapping; initial import preview. No production rows imported yet.
