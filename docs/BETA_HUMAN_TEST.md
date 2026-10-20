# C-Crate beta: quick human feature check

Use the local test app and disposable test items. This is a short acceptance pass for the features you want to try; skip exhaustive error and edge-case scenarios for now. Record **Pass** or **Fail** for each flow and include the page and step when something fails.

1. **Inventory:** Create an item with a name and location, save it, find it in Inventory, open it, edit one field, and save. Confirm it remains visible with the updated value.
2. **Scan and text capture:** Scan a product barcode with the webcam and confirm the decoded value appears. Open the header text-capture pop-out, take a photo of packaging, and confirm the recognized text can be edited and copied without replacing edits.
3. **Labels:** Open Label, choose or create a template, move a text or code element, and save it. Preview it for the test item; confirm the item details and short code are present. Export a PDF or print one label if the printer is available.
4. **Workshop map:** Open a room, add an object, change its dimensions and save. Click the object and confirm there is no oversized selection border. Drag the empty map area to pan, then reload and confirm the saved layout remains.
5. **Storage browsing:** Open a parent location and expand a child location. Confirm its item is visible without leaving the parent page. Move the test item to another location and confirm its generated display ID follows the new location.
6. **Grouped equipment:** Find two or more items with the same manufacturer and model. Search for the model and confirm they appear together while each serial number, status, storage location, and item link stays distinct. Expand the group and confirm recent return notes identify and link to the item that received each note. For groups larger than 100, verify notes from later members are considered.
7. **Cabinet contents:** Open a cabinet with at least 20 bins. Confirm direct contents and empty bins are visible, search finds items among loaded contents, and expanding a nested bin makes its contents available. Record the time until direct contents appear and the number of location-detail requests in browser developer tools; use the result to decide whether loading needs optimization.
8. **Camera and small-screen review (target hardware):** On the supported Chromium device with the C920, record browser/device versions and which zoom/focus controls are available. Change and reset each exposed control, check its readback, capture a near and far label, compare the camera preview with the OCR crop, and verify text boxes align with recognized lines. Review the flow at 800×480 with keyboard and touch, confirming visible focus and usable controls.

These camera and small-screen checks require the target hardware and are not covered by automated tests. Record them as **Not run** when that hardware is unavailable; do not treat mock browser tests as camera acceptance. Kiosk checkout, physical printer recovery, scanner pairing variants, and failure-injection scenarios remain deferred from this quick pass.

## Result

| Flow | Pass / Fail | Notes |
|---|---|---|
| Inventory create/edit | | |
| Barcode and text capture | | |
| Label design and preview | | |
| Workshop map | | |
| Child-location browsing and move | | |
| Grouped equipment and recent notes | | |
| Cabinet contents and load timing | | |
| C920 controls, capture framing, and OCR alignment | | |
| 800×480 keyboard and touch usability | | |

## Item quick actions — 2026-10-19

- In the local development UI, open a child location, a grouped Inventory row, the native item table/card, a current loan, and a Workshop map selection. Confirm item actions appear only beside individual native equipment IDs. A collapsed group and a location or drawing without a native equipment record must not offer an implicit checkout target.
- Expand a group with several units and select a specific unit. Confirm the dialog names that unit, cancellation returns focus to its action trigger, and completing an action refreshes that item’s status/history without changing the current filter, group expansion, or scroll position.
- Test checkout with badge verification, check-in with an authorized destination, cart notes, and append note using disposable items. Confirm the browser does not report success before the server receipt is confirmed. Do not use this checklist against live custody unless the collection owner has supplied disposable test records.
- Automated fixture coverage: action controller and component browser suites, a 20-unit grouped Workshop fixture with a narrowed search, and generated layout/table/card integration. Map, child-location, current-loan, and physical custody flows still require human confirmation in the local development UI.

## Pi acceptance notes — 2026-10-18

- **Grouped equipment route:** Pass. After authentication, the Workshop & storage link opened Equipment in the running local development UI. Searching `Mavic 3` returned 18 native records, including seven Mavic 3 Classic records. Those seven remain separate because the sample records have no manufacturer/model pair or custom group metadata. The custom-group UI successfully assigned one record in the isolated local-test database; the temporary membership and tag were removed afterward. Full seven-record assignment, availability truth, and recent real notes remain unverified.
- **C920 camera and OCR:** Partial pass. Chromium opened the attached HD Pro Webcam C920 at 640×480, changed digital zoom from 1× to 2×, captured a photo, and finished all four browser OCR passes in about five seconds. It produced colored recognized lines and boxes. The camera was aimed at a workbench, not a known label, so this does not validate label accuracy or box alignment. Chromium exposed no hardware focus/zoom capabilities; the UI correctly used digital zoom and reported focus adjustment unavailable.
- **Cabinet contents:** Logic tests pass, but hardware/data acceptance is not run. The isolated local-test database has four locations and no nested location records; it contains no 20-bin cabinet. No cabinet load time or browser request count is claimed.
- **Printer:** Not run. The SUPVAN device is present over USB, but `lpstat -p -d` reports no configured CUPS destination and the UI reports Printer Disconnected. No physical label was sent.
- **Focused verification:** 61 Node tests passed across grouping, cabinet contents, OCR, and camera controls; seven Python child-location preview tests passed.
