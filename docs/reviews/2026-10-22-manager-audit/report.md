# Authenticated C-Crate manager UI review

Captured 2026-10-22 at 1440 × 1000 from the current generated frontend against a disposable Homebox database. The fixture had one manager, one tool, one location, and one item. Browser writes were restricted to login, the fixture's theme preference, and user appearance settings. Checkout and return confirmations were not submitted; physical devices were not connected.

## Captures

| Screen | Evidence |
|---|---|
| Home dashboard | [dashboard.png](dashboard.png) |
| Inventory and create item | [items.png](items.png), [create-item.png](create-item.png), [create-item-expanded.png](create-item-expanded.png) |
| Item details | [item-detail.png](item-detail.png) |
| Locations and location details | [locations.png](locations.png), [location-detail.png](location-detail.png) |
| Members and label maker | [members.png](members.png), [labels.png](labels.png) |
| Appearance and theme picker | [appearance.png](appearance.png) |
| Workshop map, loans, and equipment | [workshop-map.png](workshop-map.png), [workshop-loans.png](workshop-loans.png), [workshop-equipment.png](workshop-equipment.png) |
| Checkout cart, imports, recovery, system, equipment IDs | [checkout-cart.png](checkout-cart.png), [imports.png](imports.png), [recovery.png](recovery.png), [system.png](system.png), [equipment-ids.png](equipment-ids.png) |

The appearance capture confirms the manager can save the selected Homebox theme for the touchscreen. The kiosk transaction screens and scanner flow are in [the kiosk audit folder](../2026-10-22-kiosk-audit/).

## Changes reflected in the captures

- The dashboard screenshot showed the condition and availability panels dominated by zero-count rows. The dashboard now keeps populated categories in the main legend and moves zero-count categories into a keyboard-operable disclosure. Counts and chart calculations are unchanged; this is a source change after the screenshot below, so that capture does not yet show the updated layout.
- Inventory now selects a useful preview by default, shows the selected group, and uses clearer language for unloaded notes. The missing custom component imports that hid inventory content were fixed.
- Item details hide empty metadata by default and place packaging, custom fields, and related items behind a disclosure.
- Location tree controls now name their actions (“Expand all”, “Collapse all”, and “Show/Hide items”).
- The label maker distinguishes an empty collection from a search with no matches, offers Clear search, and explains the 100-item preview cap.
- Checkout and return review include an item preview with a neutral no-photo fallback.
- A collection-scoped, manager-controlled touchscreen theme setting uses the generated Homebox theme CSS.
- Netum scanner Enter submission was added to the return item scan flow.

## Limits visible in this pass

The disposable fixture has no hardware, so printer and camera indicators are unavailable. Dashboard statistics and member loan details may still be loading when captured. The checkout cart route is blank in this fixture because its backing history/group write was intentionally blocked by the browser route policy; this capture is not evidence of production behavior. The fixture does not cover physical scanner hardware or transaction confirmation.

The dashboard capture predates the compact zero-count category disclosure. It remains evidence for the original clutter finding, not for the updated rendering; regenerate `dashboard.png` from a current authenticated fixture before treating the new dashboard layout as visually verified.
