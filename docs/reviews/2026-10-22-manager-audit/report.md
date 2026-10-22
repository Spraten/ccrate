# Authenticated C-Crate manager UI review

Captured 2026-10-22 at 1440 × 1000 from the current generated frontend against a disposable Homebox database. The fixture had one manager, one tool, one location, and one item. The Create Item photo and success states used a synthetic image and wrote only to this disposable database. The manager's selected touchscreen theme was saved only to the fixture. No checkout or return was submitted; physical devices were not connected.

## Captures

| Screen | Evidence |
|---|---|
| Home dashboard | [dashboard.png](dashboard.png) |
| Inventory and create item | [items.png](items.png), [create-item.png](create-item.png), [create-item-expanded.png](create-item-expanded.png), [create-item-photo-preview.png](create-item-photo-preview.png), [create-item-success.png](create-item-success.png) |
| Item details | [item-detail.png](item-detail.png) — capture blocker: route rendered a blank page in the isolated fixture. |
| Locations and location details | [locations.png](locations.png), [location-detail.png](location-detail.png) |
| Members and label maker | [members.png](members.png), [labels.png](labels.png) |
| Appearance and theme picker | [appearance.png](appearance.png) |
| Workshop map, loans, and equipment | [workshop-map.png](workshop-map.png), [workshop-loans.png](workshop-loans.png) — loan history route rendered blank content in the fixture; [workshop-equipment.png](workshop-equipment.png) |
| Checkout cart, imports, recovery, system, equipment IDs | [checkout-cart.png](checkout-cart.png), [imports.png](imports.png), [recovery.png](recovery.png), [system.png](system.png), [equipment-ids.png](equipment-ids.png) |

The appearance capture confirms the manager can save the selected Homebox theme for the touchscreen. Updated dashboard and member captures show the compact zero-count disclosure and quieter empty-loan state. The photo-preview capture shows the synthetic photo selected in Create Item; the success capture confirms the item was created and the photo upload reported success in the temporary fixture. The kiosk transaction screens and scanner flow are in [the kiosk audit folder](../2026-10-22-kiosk-audit/).

## Changes reflected in the captures

- The dashboard keeps populated categories in the main legend and moves zero-count categories into a keyboard-operable disclosure. The current dashboard capture shows the updated layout; counts and chart calculations are unchanged.
- Inventory now selects a useful preview by default, shows the selected group, and uses clearer language for unloaded notes. The missing custom component imports that hid inventory content were fixed.
- Item details hide empty metadata by default and place packaging, custom fields, and related items behind a disclosure.
- Location tree controls now name their actions (“Expand all”, “Collapse all”, and “Show/Hide items”).
- The label maker distinguishes an empty collection from a search with no matches, offers Clear search, and explains the 100-item preview cap.
- Checkout and return review include an item preview with a neutral no-photo fallback.
- A collection-scoped, manager-controlled touchscreen theme setting uses the generated Homebox theme CSS.
- Netum scanner Enter submission was added to the return item scan flow.

## Limits visible in this pass

The disposable fixture has no hardware, so printer and camera indicators are unavailable. The item-detail route and workshop-loans route rendered blank content and are explicitly not considered visual evidence; the checkout-cart capture also lacks its live history data. The fixture does not cover physical scanner hardware or a real transaction. Kiosk failure, receipt, and uncertain-recovery states are called out as blockers in the kiosk report.
