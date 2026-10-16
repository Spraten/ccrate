
## Final branch review: cabinet filter and custom group whitespace

- Cabinet filtering now follows loaded descendant paths, opens matching paths for display, and shares nested load state across recursive views. Search makes no new descendant requests.
- The API collapses group-name whitespace, reuses a unique equivalent native tag, rejects ambiguous assignment, and removes the selected membership by native ID even when equivalent tags coexist. Other tags and equipment metadata remain untouched.
- Regression tests were run red before implementation: the cabinet path test and five API cases failed for the reported behavior.
- Focused verification: `node --test tests/location_child_contents.test.mjs tests/equipment_groups.test.mjs` (12 passed); `PYTHONPATH=ops:kiosk python3 -m unittest -k custom_group tests.test_desktop_api` (14 passed); `git diff --check` (passed).
- The existing committed corrupt blob in the API/test code range and unrelated worktree repairs were excluded from this fix commit. Python tests ran against the repaired working tree.

## Re-review: forced-open filter controls

- Matching paths now show disabled per-bin collapse controls with an accessible explanation. Collapse all is disabled while a matching filter is active, with a visible status message; clearing the filter restores normal controls.
- Added a regression for an unloaded matching bin: filter-forced expansion cannot toggle saved state or trigger a detail request. The test failed before the fix and passed afterward.
- Verification: `node --test tests/location_child_contents.test.mjs tests/equipment_groups.test.mjs` (13 passed); `git diff --check` (passed). No UI build or device action.

## Combined verification: preview source contracts

- Updated two stale Python source-contract assertions to reflect loaded-descendant filtering, the forced-open disabled control, and shared recursive state. Production behavior was unchanged.
- Verification: `python3 -m unittest tests.test_location_child_preview -v` (7 passed); `node --test tests/location_child_contents.test.mjs` (5 passed); `git diff --check` (passed).
