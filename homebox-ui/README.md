# Native Homebox workshop integration

`overlay/` adds native Vue pages and components to the pinned Homebox frontend. `deploy/build-homebox-ui.py` copies the upstream source into `work/homebox-ui-build`, applies checked overlay patches, and stages static output without modifying the submodule.

The Members page shows native users, shared badge actions and checked-out items. Manage users edits the existing native profile. The native Home page and item details also expose workshop checkout information. Workshop routes reuse the native layout, collection, theme and authenticated request helper; the Equipment Terminal remains available from the sidebar.

The Workshop map has a searchable illustrated object library with 22 presets across shelves, cabinets, drawers, bins, work surfaces, structure and machines. Choose **Edit**, select a preset and click the room to place it; **Escape** cancels pending placement. Preset dimensions are in feet. Adding or removing a drawing does not create or delete a native inventory/location record. Native linking remains an explicit action in the inspector.

Object artwork uses separate SVG assets with preserved proportions. Captions stay horizontal when objects rotate. Drag and resize preview geometry; a completed change is one undo action, and returning to the starting point creates none. Save changes explicitly; an unconfirmed save must be checked before making another write.

Build with the configured toolchain:

```sh
python3 deploy/build-homebox-ui.py --toolchain-root "$PWD/work/toolchains" --upstream-root "$PWD"
```

The private toolchain lives under `work/toolchains`; the build uses its pinned Node.js and pnpm packages. Output is staged under `work/homebox-ui-build`. Build and fixture verification must use isolated local data, never the operational Homebox database.

The gateway serves the selected static tree from `work/homebox-ui-current`. Release selection and rollback are separate operations; a build does not deploy or restart services.

The native label generator adapts the layout and generate/preview interaction from HomeSortStuff commit `85b96e5060a48dd11db24addfbc63407eed4e74c`.
Its source is distributed under AGPL-3.0; see `HOMESORTSTUFF-LICENSE.txt`.

Member names and identities come from native Homebox users. Badge-only accounts have no native password. Badge writes use durable request identities and uncertain results require Recovery. Private credentials, badge keys and operational databases remain on the Pi and outside generated frontend bundles.
