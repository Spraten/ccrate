# C-Crate item barcode capture

## Goal

Let a user scan or type an item's barcode while adding an item, retain that exact code for C-Crate's internal tracking even when no public product data exists, and optionally use the existing product lookup to prefill editable details. Keep the flow in C-Crate's inventory UI and reuse its current camera scanner and lookup providers.

## User flow

- In Add Item, the user can open the webcam scanner or enter a barcode manually. The captured value remains visible and editable in the item form.
- Scanning or entering a code attempts the existing product lookup when applicable. A match offers editable prefilled fields (name, manufacturer, model, description, and image); no match leaves the form ready for manual entry and preserves the code.
- Saving creates a normal item with the barcode attached. The barcode remains viewable and editable in item details/editing and searchable from inventory.
- A code already used by another item is allowed. Show matching items when an exact duplicate is scanned or entered so the user can choose to open one or continue creating another.

## Data and API

- Add an optional nullable `barcode` string to the item/entity model and its create, update, and output contracts. Preserve existing records as empty/null through a backward-compatible database migration.
- Accept the scanned/manual code as an opaque string up to 80 characters, trim surrounding whitespace, and preserve leading zeroes and internal characters. Do not impose uniqueness; add an index for exact lookup.
- Include barcode in exact inventory search and return all exact matches. The standard item UUID and asset ID remain unchanged.
- Keep the existing product-search endpoint as an optional enrichment source. Numeric retail codes may return candidates; alphanumeric or unsupported codes still save and search internally without treating a lookup miss as an item-creation error.

## Scanner and interface

- Reuse the existing ZXing camera path. Support the common EAN/UPC formats already recognized and Code 128, without adding a scanner dependency.
- Provide a clear manual-entry path when camera permission, camera hardware, or decoding is unavailable.
- Keep barcode capture inside the C-Crate Add Item form; do not route the user through a separate product-import flow that loses the code.
- Do not add OCR, image scraping, external catalog integrations, kiosk behavior, or a new settings subsystem.

## Acceptance criteria

1. A user can type an alphanumeric code such as `X9TEUJR4L`, fill in the item manually, save, reopen it, and find it by that code.
2. A user can scan a supported UPC/EAN or Code 128 barcode, see its value in the item form, and save it even when lookup returns no result.
3. A successful public lookup can prefill editable item fields without overwriting user edits silently.
4. Multiple items may share a product barcode; exact lookup shows each match and never blocks saving a duplicate.
5. Existing items and API clients that omit barcode continue to work.
6. Manual entry works if camera access is denied or unavailable.

## Boundaries and risks

Product catalogs may not recognize supplier or internal labels, including the alphanumeric code shown in the example. The barcode is therefore first-class C-Crate data, while catalog enrichment remains best-effort. Barcodes identify a product/package code, not necessarily a unique physical unit; uniqueness is intentionally not enforced.
