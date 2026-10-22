# C-Crate front end audit — initial screenshot pass

**Captured:** 2026-10-21
**Viewport:** manager 1280 × 900; kiosk 1280 × 657
**Kiosk data:** isolated fixture only (Jamie Rivera, one fake Makita driver). All checkout and return confirmation endpoints are blocked. No Homebox transaction was recorded.

## Screens captured

| Step | Screenshot | What it shows |
|---|---|---|
| 0 | [Manager sign in](00-manager-login.png) | C-Crate/Homebox login screen, signed out |
| 1 | [Kiosk home](01-kiosk-home.png) | Member badge entry and the two top-level actions |
| 2 | [Checkout badge gate](02-checkout-badge-gate.png) | Checkout selected, asking for a member badge |
| 3 | [Checkout scan](03-checkout-scan-ready.png) | Authenticated fixture member, inventory search and barcode scan |
| 4 | [Checkout item review](04-checkout-review.png) | Scanned item, optional note, list save, review and confirm actions |
| 5 | [Return scan](05-return-scan-ready.png) | Return inventory search and barcode scan |
| 6 | [Return item review](06-return-review.png) | Item condition, required issue note, optional return note, review and confirm actions |
| 7 | [Interactive prototype, current](07-prototype-current.png) | Inventory split view and preview-only theme selector |

## Step-by-step notes

1. **Manager sign in — enter the manager UI.** The email/password fields and Login action are easy to locate, and the branding is clear. The screen cannot establish whether manager screens are usable because no authenticated session was available. The password visibility icon and keyboard/focus behavior were not tested. Evidence: [manager sign in](00-manager-login.png).
2. **Kiosk home — choose checkout or return.** The two large actions are easy to distinguish and have generous touch targets. Member status is separated in the top bar, while most of the screen is empty. Keyboard focus and actual scanner input were not tested. Evidence: [kiosk home](01-kiosk-home.png).
3. **Checkout badge gate — identify the member.** The screen explains that a badge is needed and offers a manual badge field and Scan badge button. There is no visible way back to home from this step. The badge scan was simulated; physical scanner behavior remains unverified. Evidence: [checkout badge gate](02-checkout-badge-gate.png).
4. **Checkout scan — locate and scan an item.** Both text search and a dedicated barcode field are available, with explicit “Verify scan and add” feedback. Their relationship is not explained, and the scan control sits beside rather than within a clearly grouped step. No image or item status is shown before scanning. Evidence: [checkout scan](03-checkout-scan-ready.png).
5. **Checkout review — verify the draft.** The scanned item name and note field are visible, and Remove offers a way to correct that item. There is no clear transaction-level cancel action, and the disabled confirm control does not look disabled. Evidence uses one synthetic item; no real item photo was available. [Checkout item review](04-checkout-review.png).
6. **Return scan — find the item being returned.** Search and barcode scan mirror checkout, giving users two ways to locate an item. The screen does not provide an obvious cancel route, and the item does not appear as a preview before scan. Physical scanner input was not tested. Evidence: [return scan](05-return-scan-ready.png).
7. **Return review — confirm condition and notes.** Current condition and return location are shown, and condition options are spelled out. Inputs, Remove, and fixed bottom actions compete for space; the required issue-note field is visible even when condition remains unchanged. No image is shown. Evidence uses a synthetic item and no transaction confirmation was sent. [Return item review](06-return-review.png).
8. **Prototype review — compare proposed inventory layout.** The split view exposes the result list and selected item together, and the theme control is clearly labeled preview-only. In this capture, emoji item markers render as missing-glyph boxes, and the prototype uses a custom font/focus treatment that differs from the Homebox source styles. Replace those prototype-only values with source components/tokens and use photo or intentional neutral fallback treatment. Evidence is only the local concept page, not a production manager view. [Interactive prototype](07-prototype-current.png).

## Findings

### High priority

1. **There is no visible way to cancel or leave an in-progress checkout or return.** On both item screens, there is no Back, Cancel, or discard action. The only visible controls concern the current item and the fixed Review/Confirm bar. This matches the reported difficulty cancelling a check-in or check-out. See [checkout review](04-checkout-review.png) and [return review](06-return-review.png).

2. **Checkout confirmation looks enabled before review.** In the checkout screenshot, “Confirm checkout” has the same green fill and contrast as the available “Review checkout” action even though it is disabled until review succeeds. The control’s state is communicated mainly by its behavior, not its appearance. Give disabled buttons a clear visual state and preserve a visible reason until review is complete. See [checkout item review](04-checkout-review.png).

### Medium priority

3. **Scanned items are shown as loose text and fields rather than a clear item preview.** The checkout has a name, note input, and Remove button spread across the available width. Return adds condition and note controls, but still lacks a contained item card or image. This makes it hard to quickly verify the scanned object and its context. See [checkout item review](04-checkout-review.png) and [return item review](06-return-review.png).

4. **The transaction screens have uneven alignment and large unused areas.** Search and scan controls occupy the left side, some secondary actions float to the right, and the review/confirm bar is fixed at the bottom. The result leaves substantial whitespace between the item details and the bottom actions while fields and buttons crowd together in a few rows. Review on a touch display should keep the active item and its actions visually grouped. See [checkout item review](04-checkout-review.png) and [return item review](06-return-review.png).

5. **The kiosk and manager entry screen do not read as one product.** The manager uses the Homebox logo, wave-shaped green header, and centered login card. The kiosk uses a plain C-Crate text header, pale flat canvas, and large solid green action tiles. The palette overlaps, but typography, header treatment, spacing, and surfaces differ. See [manager sign in](00-manager-login.png) and [kiosk home](01-kiosk-home.png).

6. **The kiosk home has a lot of unstructured empty space.** The two large choices are clear, but they sit alone in the upper portion of a nearly empty screen. Member status is small and separated in the header. A more deliberate idle/ready layout could keep the primary choice prominent while making member state and scan guidance feel connected. See [kiosk home](01-kiosk-home.png).

## Capture limits

The manager app was only available at its signed-out login screen in this session. The saved login attempt did not provide access to authenticated manager screens, so item, location, create-item, and settings pages have not yet been visually audited. The kiosk screenshots use the real kiosk frontend against synthetic fixture APIs. They show representative interaction states but do not validate production service responses or actual Homebox item photography.

## Suggested audit order

1. Capture manager Items list, item detail, Locations list, location detail, and Create item at the same desktop viewport.
2. Capture kiosk at its installed touch display resolution and verify the badge and barcode scan presentation with the Netum scanner.
3. Use these findings to refine the already drafted redesign plan, including shared Homebox theme tokens, item previews, clear cancel/discard handling, and compact item/location layouts.
