# Location contents layout change

## Changes

`deploy/build-homebox-ui.py` now mounts the overlay `ChildContents` view on every location detail page as a one-location root, keyed by the current location ID. This uses the existing grouped thumbnail rows, `×N` count, item detail links, filter, refresh/retry behavior, and collapsible child bins for direct contents at every depth, including leaf and empty bins. Existing item pages and the default `ChildContents` recursive child rendering are unchanged. Direct-only mode skips the child-location detail request and recursive child view, avoiding duplicate child bins.

Native `ItemViewSelectable` remains available in a collapsed **Manage items** disclosure when the location has direct items, preserving its bulk/select actions. The grouped contents view is the default. Its loader continues to use the existing all-pages direct-item fetch and metadata hydration; bulk actions increment a keyed contents revision and refresh the native selectable list. Location detail data now uses a reactive async-data key. Location IDs key the management disclosure, and both direct and child contents views use the same revision so native item moves refresh both sections.

## Sources

- Builder: `deploy/build-homebox-ui.py`, `location_child_contents_frontend()`.
- Shared contents implementation: `homebox-ui/overlay/components/Location/ChildContents.vue`.

## Limitations and verification

No tests or builds were run, per instruction. The native bulk controls are now one disclosure deeper, and the page displays the grouped contents loader alongside the existing native list data used for management actions.
