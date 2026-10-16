# Task 1 Report: Batch immediate bin contents

## Result

Updated `ChildContents.vue` so the root cabinet preview opens each immediate bin by default and loads direct items for the full set of immediate child IDs in paged requests of 100, including archived items. Returned items are assigned to bins using `item.parent.id`; each bin keeps its row and displays its own empty state when appropriate.

Nested locations use an explicit depth. Descendants remain collapsed and fetch their direct items and location details when expanded. Root batch status is shown once for the batch. If a later page fails, items collected from earlier pages remain visible and the batch error says results may be incomplete, with a retry action. Collapse and expand controls expose the current aggregate expanded state and expansion does not clear cached direct items.

Updated the source contract test to assert that the generated page mounts `ChildContents`, root bins default open, the batch query uses all immediate child IDs and native parent IDs, and the expand/collapse controls and existing details/item links remain present.

## Verification

- RED: `python3 -m unittest tests.test_location_child_preview -v` failed at the new batch-query assertion against the original one-bin-at-a-time component.
- GREEN: `python3 -m unittest tests.test_location_child_preview -v` passed (2 tests).
- `git diff --check` passed.

No broad test suite was run, per task instructions.

## Review notes

Only the component and its focused contract test are included in this task commit. The existing unrelated modified and untracked workspace files were left untouched. No separate pure helper or JavaScript test was needed.

## Commit

`c27c2f5` (`Batch cabinet immediate bin contents`).

## Review round 1 fixes

Addressed the three review findings:

- Only the root `ChildContents` instance starts the batch request on mount. Recursive instances wait until their bin is expanded, then fetch that bin's items and location details. Root bins no longer issue one `getLocation` request per bin on initial render; details are loaded only when a collapsed bin is expanded.
- Pagination tracks the number of returned items independently of mapped bins. An empty page while fewer than `total` items have arrived is treated as an error, so accumulated rows are retained as partial and cannot be marked fully loaded.
- Added focused source-contract assertions for root-only initial batching, nested on-demand fetching, and incomplete pagination failure.

Verification: `python3 -m unittest tests.test_location_child_preview -v` passed (2 tests); `git diff --check` passed. No broad suite was run.
