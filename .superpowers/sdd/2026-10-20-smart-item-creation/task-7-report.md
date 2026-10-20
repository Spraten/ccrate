# Task 7 report: cross-feature builder and recovery review

## Changes

- Added a builder regression using disposable local CreateModal and layout source fixtures. It checks one global OCR popover, routing to the create launcher, absence of generated template controls and navigation, and retained generated-ID assignment.
- Added a temporary SQLite API regression. After saving active and archived templates, it opens a fresh catalog on the same fixture database and confirms both records, fields, archived state, and history remain readable through the backend API.
- No feature code, existing item IDs, or QR routes changed.

## Regression sensitivity

- With `ocr_popover_frontend` temporarily replaced by a no-op, the new builder test failed at `AssertionError: 0 != 1` for the single global popover. The normal test passed after restoring the builder.
- With `EquipmentCatalog.list_templates` temporarily returning an empty list, the new backend test failed because the active saved template disappeared from the API listing. The normal test passed after restoring the catalog.

## Focused fixture verification

Command: `PYTHONPATH=ops:kiosk:tests PYTHONWARNINGS=ignore::ResourceWarning python3 -m unittest tests.test_equipment_catalog tests.test_desktop_api_equipment_catalog tests.test_item_metadata tests.test_desktop_api_item_metadata tests.test_equipment_search_builder tests.test_equipment_inventory_builder -q`

Exit: 0. Exact output:

```text
----------------------------------------------------------------------
Ran 71 tests in 1.585s

OK
```

The first combined Python invocation used `PYTHONPATH=ops:kiosk` and produced `ModuleNotFoundError: No module named 'test_desktop_api_equipment_catalog'` while importing `test_desktop_api_item_metadata`. The corrected invocation above adds `tests` to `PYTHONPATH` and supersedes that invocation. Resource warnings from fixture SQLite connections were suppressed for the concise corrected output.

Command: `node --test tests/equipment_catalog.test.mjs tests/equipment_groups.test.mjs tests/equipment_inventory.test.mjs tests/equipment_search.test.mjs tests/item_suggestions.test.mjs tests/item_metadata.test.mjs tests/item_metadata.browser.mjs` (captured with `set -o pipefail` and `tail -n 9`)

Exit: 0. Exact summary output:

```text
1..103
# tests 103
# suites 0
# pass 103
# fail 0
# cancelled 0
# skipped 0
# todo 0
# duration_ms 13036.921687
```

The Node suite includes mounted generated create and detail browser fixtures. Its builder preparation and browser data were confined to disposable local fixtures; no operational Homebox was contacted.

Command: `PYTHONPATH=ops:kiosk python3 -m unittest tests.test_homebox_ui_builder -v`

Exit: 1. Exact summary:

```text
Ran 13 tests in 0.475s

FAILED (errors=2)
```

The two existing errors are `test_generated_location_selector_preserves_hierarchy_and_parent_filtering` and `test_prepare_accepts_barcode_aware_create_entity_dialog_type`; both stop before transformation at `ValueError: Homebox source snapshot has no verified commit marker`. This is the source-marker environment limit already recorded in the Task 3 and Task 5 ledger.

## Static review

`git diff --check` passed. The original commit contained only the two test files and this report. No credentials, databases, build artifacts, QR destinations, existing ID data, or unrelated source changes were added. Preexisting untracked review files were left untouched.

## Review fix round 1: self-contained builder fixture and SQLite cleanup

The reviewer found that the first builder regression skipped when the shared patched Homebox cache was absent. The test now writes a small source fixture for the existing `smart_create_form_text` and `ocr_popover_frontend` transforms into `TemporaryDirectory`; it has no cache probe or skip. The related-item transform is isolated because its behavior is covered by the focused Node fixture suite. The OCR mutation check still fails the new regression with `AssertionError: 0 != 1`, and the unmodified test passes.

The warning investigation showed that `Ledger.connection()` closes its SQLite connections, while two legacy catalog fixture migrations used `with sqlite3.connect(path)`, which commits but does not close. Those fixtures now use `closing(...)` around the transaction context. No warning suppression is needed.

Command: `PYTHONPATH=ops:kiosk python3 -m unittest tests.test_homebox_ui_builder.HomeboxUiBuilderTests.test_generated_create_keeps_one_global_ocr_launcher_and_id_assignment_without_template_controls -v`

Exit: 0. Exact output:

```text
test_generated_create_keeps_one_global_ocr_launcher_and_id_assignment_without_template_controls (tests.test_homebox_ui_builder.HomeboxUiBuilderTests.test_generated_create_keeps_one_global_ocr_launcher_and_id_assignment_without_template_controls)
Exercise the create and layout transforms using local source fixtures. ... ok

----------------------------------------------------------------------
Ran 1 test in 0.091s

OK
```

Command: `PYTHONPATH=ops:kiosk:tests python3 -W error::ResourceWarning -m unittest tests.test_equipment_catalog tests.test_desktop_api_equipment_catalog tests.test_item_metadata tests.test_desktop_api_item_metadata tests.test_equipment_search_builder tests.test_equipment_inventory_builder -q`

Exit: 0. Exact output:

```text
----------------------------------------------------------------------
Ran 71 tests in 0.749s

OK
```

Command: `node --test tests/equipment_catalog.test.mjs tests/equipment_groups.test.mjs tests/equipment_inventory.test.mjs tests/equipment_search.test.mjs tests/item_suggestions.test.mjs tests/item_metadata.test.mjs tests/item_metadata.browser.mjs` (captured with `set -o pipefail` and `tail -n 9`)

Exit: 0. Exact summary output:

```text
1..103
# tests 103
# suites 0
# pass 103
# fail 0
# cancelled 0
# skipped 0
# todo 0
# duration_ms 9681.799755
```

The full builder suite rerun reported `Ran 13 tests in 0.174s` and `FAILED (errors=2)`, at the same two source-marker tests identified above. The new self-contained regression passed in that run.

## Final whole-branch review fix round

Resolved all seven findings from the final branch review:

1. Detail edits now retain the native item and Notes snapshots captured when the panel loaded. Save merges by native field UUID: untouched values keep concurrent server changes, server additions survive, and conflicting simultaneous changes/deletions stop with a field-specific reload message before any native or Notes write. The final Notes update includes concurrent fields and notes.
2. Custom-field name identity now uses one cross-language contract: normalize whitespace and apply Unicode case folding. The client uses a generated table of Unicode casefold expansions after lowercase; the API uses Python `casefold()`. Validation, native matching, detail display, and Notes matching share the client canonicalizer. This covers sharp-s, Greek final sigma, and other casefold expansions while retaining the 120-character visible-name limit and existing Notes keys.
3. Related native creates that were uncertain can now be reconciled as confirmed absent. That explicit action marks the step retryable; uncertain creates still cannot retry. The step retry only reissues its unresolved create and dependent link.
4. Explicitly confirming that the main item was not created clears both the main intent and its dependent durable related intent. Staged related-item form values remain in the open modal for the next create attempt.
5. Idempotency keys use a shared `workshopUUID()` helper with a `getRandomValues` fallback when `crypto.randomUUID` is missing. Both the detail panel and generated create/relation flows use it.
6. A definitive relation API rejection (4xx other than timeout/conflict/rate-limit) clears the locked pending relation. Ambiguous outcomes retain the stable request for reconciliation/retry.
7. The navigation regression now supplies a real `/templates` entry to the extracted production removal transform. A no-op mutation check confirmed `/templates` remains and the fixture assertion would fail.

### Focused verification

Command: `PYTHONPATH=ops:kiosk:tests python3 -W error::ResourceWarning -m unittest tests.test_item_metadata tests.test_desktop_api_item_metadata tests.test_homebox_ui_builder.HomeboxUiBuilderTests.test_equipment_template_navigation_removal_uses_a_real_entry_fixture tests.test_homebox_ui_builder.HomeboxUiBuilderTests.test_generated_create_keeps_one_global_ocr_launcher_and_id_assignment_without_template_controls -q`

Exit: 0. Exact summary:

```text
Ran 33 tests in 0.330s
OK
```

Command: `set -o pipefail; node --test tests/item_metadata.test.mjs tests/item_metadata.browser.mjs tests/equipment_catalog.test.mjs | tail -n 9`

Exit: 0. Exact output:

```text
1..64
# tests 64
# suites 0
# pass 64
# fail 0
# cancelled 0
# skipped 0
# todo 0
# duration_ms 9712.526692
```

The browser fixture mounted the generated create UI and detail panel. It verified conflict-safe native/Notes behavior, safe confirmed-absence retries, the HTTP-compatible UUID fallback, and definitive relation failure recovery. No operational Homebox was contacted.

Navigation mutation sensitivity command used a temporary fixture and a no-op `replace` function; exact output:

```text
no-op mutation retained /templates; fixture assertion would fail as intended
```

`git diff --check` passed before commit. The normal focused builder tests use disposable source fixtures; the two previously documented source-marker failures in the broader Homebox builder suite remain an environment limitation and were not changed in this fix round.
