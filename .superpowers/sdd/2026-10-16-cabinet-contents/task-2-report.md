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

## Review Fix Round 1

Updated filtering so an empty query shows every bin, while a nonempty query keeps bins whose names or loaded items match and displays a `Bin name match` marker for name matches. A no-results status appears when no loaded locations match. Added contract coverage for these states.

Immediate bins now load their location details on root mount, alongside the existing batched item request. Root detail requests still skip per-bin item-list calls; nested child details and their items remain lazy until those children are expanded. `Expand bins` requests details for any expanded row whose details have not loaded, including after a previous failure. The loaded-only disclosure remains.

Verification: new contracts failed before implementation (missing bin filtering and root detail loading); `python3 -m unittest tests.test_location_child_preview -v` passes (5 tests); `git diff --check` passes.

Self-review confirmed the changes are limited to component rendering/loading, focused contract assertions, and this report. Existing batching and partial-load error/retry behavior are unchanged.
