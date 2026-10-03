# Admin CSV import wizard

Open Equipment Terminal, tap Admin, then Import CSV. If the terminal was already open during installation, tap Desktop and reopen Equipment Terminal.

1. Choose a CSV UTF-8 file (up to 700 KB, 500 individually tracked items and 40 columns). Give the source system a stable name, such as Asset Manager.
2. Map its columns to equipment name, serial, manufacturer, model, description, location, category, source ID and original condition. Name is required. Mapping the original ID is recommended for reliable repeat-import detection. Comma, semicolon and tab separators, quoted commas and UTF-8 BOM exports are accepted.
3. Pick default existing locations/categories for blank CSV values. Named locations/categories match an existing Homebox name exactly, ignoring case. Unknown or ambiguous names require a selection during item review; the wizard does not invent storage locations.
4. Step through items. Edit with the touchscreen keyboard, choose location/category/condition, and Save review & next or Skip item & next. Previous, Next and Jump to item navigate saved rows. Unsaved edits are discarded when navigating without saving.
5. Batch summary shows reviewed valid items, skipped items and items still needing review. Confirm creation creates only selected, saved, valid rows. Stop after current item pauses the queue.
6. Select created items in the label queue, preview labels, then confirm printing. Prints run sequentially. The queue stops on the first error. Completed labels stay marked printed and are not automatically repeated.

## Native Homebox records

Each CSV row creates one native Homebox equipment record with quantity 1. Names, descriptions, serials, manufacturers, models, equipment categories and parent locations remain native data. Import source, source ID, original condition and a source identity hash are native custom fields. Existing equipment is never overwritten by this importer. Created records can be edited through their Homebox link.

Imports start Unreviewed even if a CSV says Ready. Admin may choose a condition; Ready additionally requires explicit inspection confirmation. Archived, Retired, Broken and Trashed remain preserved records, blocked from checkout. Archived sets Homebox's native archived flag. The original CSV condition is preserved separately.

Existing serial numbers or source identities block duplicates. A source identity uses the stable source-system name plus original ID. Without an ID, it uses the original mapped row contents: identical reimports are detected, but changed rows without serials/IDs cannot be reliably matched. Keep the system name and map source IDs consistently.

## Saved progress and recovery

Private drafts and per-row progress live in work/ops/imports.db on the Pi, scoped to the native Homebox group. Inventory authority remains Homebox. The database is included in the cold deployment backup with integrity/checkpoint/hash checks.

Reopen Import CSV and choose Resume. Refresh saved progress reconciles completed native jobs, including completion after a lost browser response. Uncertain creates/prints require the existing Admin recovery workflow. Native jobs are durable before an external action and are never automatically resubmitted after an uncertain outcome. Resolve the job, then refresh the batch. Safely cancelled rows can be edited and saved for an explicit new attempt. A safely cancelled print may be explicitly tried again; uncertain printing must be physically checked first.

This prototype uses the previously approved temporary open Admin mode and the existing loopback/same-origin protections. CSV data stays on the Pi. No Asset Manager account or API connection is needed.

## Verification

107 unit checks pass, including CSV parsing, preview without native writes, group isolation, duplicate checks, condition inspection, persisted edits and completed/uncertain job handling. deploy/verify-imports.py exercises touchscreen editing, two native demo creations, native provenance/condition readback, saved-batch reopening, duplicate reimport blocking and label previews at 800 x 480.
