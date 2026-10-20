# Task 1 report: collection-scoped item metadata

## Delivered

- Added `ops/item_metadata.py` with additive SQLite tables for per-item field notes, normalized unordered relations, and request-key replay protection. Each write is transactional and collection-scoped.
- Added authenticated metadata GET and POST routes in `ops/desktop_api.py`. Native item identities are resolved through the authenticated collection Homebox client before writes; locations are rejected. The read model omits inaccessible targets' identifiers and details while retaining their relation.
- Added local SQLite and authenticated API fixture coverage in `tests/test_item_metadata.py` and `tests/test_desktop_api_item_metadata.py`.

## Verification

Commands run:

- `PYTHONPATH=ops:kiosk python -m unittest discover -s tests -p 'test_item_metadata.py' -v` — 3 tests passed.
- `PYTHONPATH=ops:kiosk python -m unittest discover -s tests -p 'test_desktop_api_item_metadata.py' -v` — 22 tests passed (2 metadata API tests plus 20 existing equipment catalog tests discovered through the reused fixture module).
- `git diff --check` — passed.

The requested pre-implementation red run was not performed: implementation was already underway before the test file was added. The post-implementation focused suites pass.

## Review notes

No known functional concern remains in the task scope. API tests reuse the equipment catalog fixture, so discovery also picks up that fixture module's test class; all of those tests passed in the final focused command. No operational Homebox instance was used.
