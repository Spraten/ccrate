# Task 6 report: Custom-field Inventory search

## Changes

- Added `matchInventoryCustomFields`, matching case-insensitive custom field names and values on the already-projected native item records.
- Added the custom-field matches to the existing matched UUID set in the Inventory projection. The projection remains scoped to `projected` records sourced from `equipmentRows` and the current native collection result; there is no secondary fetch.
- Added Node coverage for tracking/barcode name and value matching, with a hidden record excluded, plus a builder-source assertion that the custom-field matcher receives the projected records.

## TDD evidence

- RED: `node --test tests/equipment_search.test.mjs` failed at module instantiation because `matchInventoryCustomFields` was not exported yet (`SyntaxError: ... does not provide an export named 'matchInventoryCustomFields'`).
- GREEN: The same command passed after implementation: 6 tests, 6 passed, 0 failed.

## Verification

- `node --test tests/equipment_search.test.mjs` — passed, 6 tests.
- `python3 -m unittest tests.test_equipment_search_builder` — passed, 2 tests.
- `git diff --check` — passed.

## Self-review

Custom-field matching only examines native fields on the existing `projected` set and adds matching item IDs to the existing native match set. Existing native filters, pagination, group expansion, and precedence are not changed. No dependencies or unrelated source files were changed. No live Homebox was used.

## Commit

`8dcd53b` (`Add custom field inventory search`).
