# C-Crate beta: quick human feature check

Use the local test app and disposable test items. This is a short acceptance pass for the features you want to try; skip exhaustive error and edge-case scenarios for now. Record **Pass** or **Fail** for each flow and include the page and step when something fails.

1. **Inventory:** Create an item with a name and location, save it, find it in Inventory, open it, edit one field, and save. Confirm it remains visible with the updated value.
2. **Scan and text capture:** Scan a product barcode with the webcam and confirm the decoded value appears. Open the header text-capture pop-out, take a photo of packaging, and confirm the recognized text can be edited and copied without replacing edits.
3. **Labels:** Open Label, choose or create a template, move a text or code element, and save it. Preview it for the test item; confirm the item details and short code are present. Export a PDF or print one label if the printer is available.
4. **Workshop map:** Open a room, add an object, change its dimensions and save. Click the object and confirm there is no oversized selection border. Drag the empty map area to pan, then reload and confirm the saved layout remains.
5. **Storage browsing:** Open a parent location and expand a child location. Confirm its item is visible without leaving the parent page. Move the test item to another location and confirm its generated display ID follows the new location.

Kiosk checkout, physical printer recovery, camera-device compatibility, scanner pairing variants, and failure-injection scenarios are deferred from this quick pass. Test those only when you specifically want to validate them or when a reported bug points there.

## Result

| Flow | Pass / Fail | Notes |
|---|---|---|
| Inventory create/edit | | |
| Barcode and text capture | | |
| Label design and preview | | |
| Workshop map | | |
| Child-location browsing and move | | |
