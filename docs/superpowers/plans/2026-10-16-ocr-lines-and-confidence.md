# OCR Lines and Confidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recreate the desktop scanner’s matching colored OCR boxes and lines in C-Crate, while improving recognition with local image enhancement and alternate Tesseract layouts.

**Architecture:** Keep capture and OCR in the existing browser popover. Return line text, bounding boxes, image dimensions, and confidence from the OCR helper; compare the original image and a locally contrast-enhanced copy using two page segmentation modes, then use the higher-confidence result. Render SVG boxes over the captured image and matching colored line labels alongside the existing editable text.

**Tech Stack:** Vue 3, TypeScript, Tesseract.js 6.0.1, browser Canvas/ImageBitmap, Node built-in test runner.

**Spec:** Approved in-chat design (2026-10-16); no separate spec file for this bounded feature. Keep the captured photo on screen, draw a distinct colored box for each recognized text line, show each line in the same color, and improve recognition with original/enhanced image passes and alternate layouts. Photos remain in-browser.

## Global Constraints

- Keep the change limited to the existing OCR helper, popover, and focused OCR unit tests; add no dependencies.
- Preserve browser-only image processing and existing edit protection, scan cancellation, and worker cleanup behavior.
- Keep the existing editable full-text result; boxes and colored line labels are a visual aid.
- Do not deploy or restart services as part of implementation.

## Review Focus

- Tesseract output with missing or malformed line boxes: retain readable full text and omit invalid overlays.
- Images with no recognizable text: preserve the current empty-result message and avoid stale boxes.
- User edits made during scanning: retain edits and do not replace them with OCR output.
- Slow or cancelled scans: discard stale structured results and always terminate the worker.
- Narrow or unusually proportioned photos: keep SVG boxes aligned with the contained image and within its bounds.

---

### Task 1: Structured, confidence-ranked browser OCR

**Files:**
- Modify: `homebox-ui/overlay/lib/local-ocr.js`
- Test: `tests/local_ocr.test.mjs`

**Interfaces:**
- Consumes: Existing `recognizeTextFromImage(image: Blob, loadEngine?)` and `applyRecognizedTextWithoutOverwritingEdits(...)` callers.
- Produces: `recognizeStructuredTextFromImage(image: Blob, loadEngine?) -> Promise<{ text: string, lines: Array<{ text: string, bbox: OCRBox, confidence: number }>, imageWidth: number, imageHeight: number, confidence: number }>`; preserve `recognizeTextFromImage(image: Blob, loadEngine?) -> Promise<string>` for existing callers. In browsers, the string API delegates to structured OCR and returns `.text`; outside browsers, retain its existing one-pass worker path. The apply helper accepts either a string or structured result and calls `setText` with the text value.

- [ ] **Step 1: Add focused failing tests** for structured line extraction from block lines, missing/malformed boxes, selection of the higher-confidence pass, enhanced-image creation, and applying structured text without overwriting in-flight edits. Assert OCR requests text and blocks and terminates the worker.
- [ ] **Step 2: Run the focused tests** with `node --test tests/local_ocr.test.mjs`; confirm the new cases fail against the current text-only API.
- [ ] **Step 3: Implement `recognizeStructuredTextFromImage`** in `local-ocr.js`. Decode the input with `createImageBitmap`, create a contrast-enhanced canvas copy locally, run both original and enhanced images under Tesseract page segmentation modes `6` (single block) and `11` (sparse text), request `{ text: true, blocks: true }`, and select the result with the highest finite `data.confidence`. Use a stable pass order to break ties. Flatten block paragraph lines, preserve only non-empty lines with finite positive bounding boxes fully within the source image dimensions, normalize full text as today, and return bitmap dimensions. Close the bitmap and terminate the worker in `finally` paths. Keep `recognizeTextFromImage` string-compatible and allow the edit-protection helper to consume either string or structured results.
- [ ] **Step 4: Run** `node --test tests/local_ocr.test.mjs`; expect all existing and new OCR helper tests to pass.

### Task 2: Matching image boxes and colored OCR lines

**Files:**
- Modify: `homebox-ui/overlay/components/Workshop/OcrPopover.vue`
- Test: `tests/local_ocr.test.mjs` (only if component behavior is covered by an existing component-test harness; otherwise keep UI validation to the focused manual checklist below)

**Interfaces:**
- Consumes: Task 1 `recognizeStructuredTextFromImage` result: `text`, `lines[]` with `bbox`, and `imageWidth`/`imageHeight`.
- Produces: A captured-image overlay with a stable per-line color mapping and a corresponding colored list of recognized lines; existing editable textarea continues to display the complete recognized text.

- [ ] **Step 1: Add a helper test** for stable color assignment across the same ordered lines and exclusion of lines without valid boxes, if an existing pure helper test pattern is available; otherwise skip extracting a helper solely for testing.
- [ ] **Step 2: Update scan state** to retain structured line data only when the scan result is current and successfully applied; clear line data on retake, empty result, capture replacement, or stale scan.
- [ ] **Step 3: Overlay boxes and matching line colors** in the captured photo area using an SVG `viewBox` of `0 0 imageWidth imageHeight` and `preserveAspectRatio="xMidYMid meet"` matching the image’s contain behavior. Assign each line a deterministic color from a small high-contrast palette, reuse that color for its SVG rectangle and line label, and provide accessible text labels for the visual list.
- [ ] **Step 4: Manually inspect** a wide and a portrait captured image with several recognized lines; confirm boxes align with text, colors match the displayed lines, invalid boxes are omitted, and the editable result and retake flow still work.

### Task 3: Final review and integration check

**Files:**
- Review: `homebox-ui/overlay/lib/local-ocr.js`
- Review: `homebox-ui/overlay/components/Workshop/OcrPopover.vue`
- Review: `tests/local_ocr.test.mjs`

**Interfaces:**
- Consumes: Structured OCR API and overlay behavior from Tasks 1–2.
- Produces: A coherent local change ready for user review and optional application to the running development UI.

- [ ] **Step 1: Run the focused unit checks** with `node --test tests/local_ocr.test.mjs` and record the result.
- [ ] **Step 2: Inspect the diff** for accidental edits outside the three scoped files and confirm no image is sent to a remote service.
- [ ] **Step 3: Report** changed files, test output, and whether the local running UI needs an explicit refresh or separate update step.
