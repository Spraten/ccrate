# Task 2 Report: Preserve navigation, filtering, and deeper hierarchy

## Result

Updated `ChildContents.vue` with a cabinet-local filter that searches the loaded bin and item data by bin name, item name, display ID, asset ID, manufacturer, model, and serial number. The root filter is passed through recursive child components, and the UI says that deeper locations must be expanded before their contents are loaded and searched. A clear-filter action resets the query.

Item rows retain native item links, generated ID/asset ID, quantity, and now show a linked full bin path as context. Root bins continue to use the Task 1 paged batch request and retain the existing partial-load error/retry behavior. Descendant locations remain collapsed and fetch their detail and direct items only when expanded; empty-bin and per-location retry states remain available.

## Verification

- RED: Added the filtering and navigation contracts, then ran `python3 -m unittest tests.test_location_child_preview -v`. The new filter contract failed because the input and search fields were absent; pre-existing lazy-loading, empty-state, and retry contracts passed.
- GREEN: `python3 -m unittest tests.test_location_child_preview -v` passed (4 tests).
- `git diff --check` passed.

## Scope

Changed only `homebox-ui/overlay/components/Location/ChildContents.vue`, `tests/test_location_child_preview.py`, and this report. Other pre-existing modified and untracked files were left untouched. No separate pure helper or JavaScript test exists.

## Commit

`Filter loaded cabinet contents`.
