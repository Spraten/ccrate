# OCR Camera Zoom and Focus Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user frame and focus a label in the OCR camera preview, then capture that same framing for local text recognition.

**Architecture:** Add a small browser-only camera-controls helper to inspect the active video track’s capabilities/settings and apply only supported controls. Use hardware zoom/focus where exposed; provide a local digital crop fallback for zoom, clearly labeled as digital. Do not control a remote Pi camera through server-side `v4l2-ctl`; the browser owns the active camera stream. Keep current OCR line boxes, colored lines, editable text, local image handling, and edit-protection behavior.

**Tech Stack:** Vue 3, `MediaStreamTrack.getCapabilities()`, `getSettings()`, `getConstraints()`, `applyConstraints()`, browser canvas/ImageBitmap, Node built-in test runner.

**Spec:** `docs/research/2026-10-16-inventory-browsing-and-grouping.md`; OCR local structured recognition is defined in `docs/superpowers/plans/2026-10-16-ocr-lines-and-confidence.md`.

## Global Constraints

- Use only the active browser media stream; no Pi service or camera-control dependency is added.
- Detect capabilities per track. Do not show a hardware focus/zoom control when the browser reports it unsupported; when focus cannot be controlled, explain that focus remains under camera autofocus/device behavior.
- Preserve existing camera permission, generation/stale-response guards, stop-on-close/minimize/unmount, and camera barcode scanning.
- Captured images and OCR stay in the browser. Continue to disclose that the OCR runtime/model downloads on first use even though the photo is not uploaded.
- When applying a constraint, preserve current track constraints and verify actual settings afterward; `applyConstraints()` replaces custom constraints omitted from its argument.
- Do not claim optical zoom for a digital crop, and do not claim manual focus where only autofocus is available. Do not implement tap-to-focus or focus-point dragging in this first slice.
- Keep Playwright out of the supported project workflow; automated coverage is for pure helpers and mocked tracks. Actual hardware behavior needs the manual camera checklist.

## Review Focus

- Camera exposes neither zoom nor focus: preview/capture still work, digital zoom remains available, and focus limitation is explained.
- Browser reports capability but rejects `applyConstraints`: keep the camera live and expose a recoverable error.
- User changes controls while camera start/stop/retake races: stale settings cannot apply to a later stream.
- Existing facing-mode or resolution constraints: control changes do not accidentally reset them.
- Digital crop at maximum zoom or extreme aspect ratio: crop remains inside source dimensions and captured OCR image matches preview.

---

## File map

- `homebox-ui/overlay/lib/ocr-camera-controls.js`: normalize capabilities, clamp requested values, preserve prior constraints, and calculate safe digital crop rectangles.
- `homebox-ui/overlay/components/Workshop/OcrPopover.vue`: initialize controls after camera start, render capability-driven UI, apply settings to current track, and capture the displayed crop.
- `tests/ocr_camera_controls.test.mjs`: pure helper tests and mocked `MediaStreamTrack` capability/constraint cases.
- `tests/local_ocr.test.mjs`: regression checks that the resulting capture Blob still flows through structured OCR and existing edit protection.
- Manual checklist: C920 in target browser/Pi environment and one desktop webcam; no physical/device test is inferred from mocked tracks.

## Task 1: Capability discovery and safe setting helpers

**Files:**
- Create: `homebox-ui/overlay/lib/ocr-camera-controls.js`
- Create: `tests/ocr_camera_controls.test.mjs`

**Interfaces:**
- Consumes: `MediaStreamTrack`-like object with optional `getCapabilities()`, `getConstraints()`, `getSettings()`, and `applyConstraints()`.
- Produces: `describeCameraControls(track) -> { zoom?: {min,max,step,value}, focusModes: string[], focusDistance?: {min,max,step,value} }` and `applyCameraControl(track, name, value) -> Promise<MediaTrackSettingsLike>`; only capabilities actually reported by the track are exposed, and unsupported or invalid values return a typed failure without changing the track.

- [ ] **Step 1: Add failing unit cases** for optional zoom range normalization, focus mode detection (`none`, `manual`, `single-shot`, `continuous` where reported), optional manual focus distance, unsupported capabilities, clamping/step rounding, preservation of existing constraints, stale-track rejection, and rejected apply without stopping the camera.
- [ ] **Step 2: Run** `node --test tests/ocr_camera_controls.test.mjs`; expected: new exports are missing.
- [ ] **Step 3: Implement the helper** using the exact ranges and modes returned by the track. Preserve existing constraints by merging the chosen supported control value into the current `getConstraints()` object; do not send unsupported keys or overwrite facing mode/resolution constraints.
- [ ] **Step 4: Run** `node --test tests/ocr_camera_controls.test.mjs`; expected: all helper cases pass.

## Task 2: Add camera controls and digital zoom fallback

**Files:**
- Modify: `homebox-ui/overlay/components/Workshop/OcrPopover.vue`
- Modify: `homebox-ui/overlay/lib/ocr-camera-controls.js` only if a pure crop helper is needed
- Test: `tests/ocr_camera_controls.test.mjs`
- Test: `tests/local_ocr.test.mjs`

**Interfaces:**
- Consumes: Task 1 capability description and `stream` video track; existing camera generation and capture state.
- Produces: While the camera is active, a labeled hardware Zoom slider when supported, otherwise a labeled Digital zoom slider (1×–4×); a Focus mode control only for modes reported by the track; a manual focus distance slider only when that range is reported; Reset controls; a visible capability/error status. Never show a tap-to-focus control in this first version.

- [ ] **Step 1: Add failing pure cases** proving digital crop bounds at 1× and 4×, integer-safe source rectangles, and identical preview/capture crop mapping for wide and tall video dimensions.
- [ ] **Step 2: Run** `node --test tests/ocr_camera_controls.test.mjs`; expected: crop cases fail before implementation.
- [ ] **Step 3: Initialize controls only after the current camera generation is accepted.** Read the video track’s capabilities/settings and update the UI only if that same stream remains active.
- [ ] **Step 4: Apply zoom/focus changes** through `applyCameraControl`; retain active preview on errors, update actual values from `getSettings()`, and provide reset-to-reported-default. State when focus is automatic or unavailable; do not imply focus was changed if settings readback does not confirm it.
- [ ] **Step 5: For tracks without hardware zoom, implement digital zoom** as a centered crop, clamped to 1×–4×. Apply the same source rectangle to the live preview and captured canvas using the 9-argument `drawImage`; label it “Digital zoom” and explain that it crops/enlarges the image without adding detail.
- [ ] **Step 6: Use `object-fit: contain` for the live preview** so edge text is not hidden at 1×. When digitally zoomed, render the matching cropped preview without changing the source rectangle used for capture. Ensure OCR boxes stay aligned with the resulting captured image coordinates.
- [ ] **Step 7: Run** `node --test tests/ocr_camera_controls.test.mjs tests/local_ocr.test.mjs`; expected: capability logic, crop geometry, and existing OCR helper tests pass.

## Task 3: Camera lifecycle, accessibility, and manual validation

**Files:**
- Modify: `homebox-ui/overlay/components/Workshop/OcrPopover.vue`
- Test: `tests/ocr_camera_controls.test.mjs`
- Test: `tests/local_ocr.test.mjs`

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces: accessible control labels and values, capability/unavailable announcements, safe reset behavior, and a captured Blob using the current hardware zoom/digital crop.

- [ ] **Step 1: Add tests** for track stop/reset clearing UI state, stale track control results ignored after restart, unsupported control rejection not blocking capture, and captured crop sent to OCR.
- [ ] **Step 2: Run** `node --test tests/ocr_camera_controls.test.mjs tests/local_ocr.test.mjs`; expected: new lifecycle cases initially fail.
- [ ] **Step 3: Ensure** every slider has a label, numeric value, keyboard operation, and visible focus. Announce unsupported controls and apply failures without relying on color.
- [ ] **Step 4: Manually inspect** keyboard access, normal light, near/far label framing, retake, and scan on desktop webcam and the target C920/browser. Record browser/version, device, advertised capabilities, actual settings readback, whether the captured image matches preview crop, and whether hardware focus/zoom visibly affected the result. If the C920/browser does not expose focus control, document that limit while verifying OCR capture still works.
- [ ] **Step 5: Run the focused Node checks** again and record the device checklist separately; mocked tests do not prove autofocus or optical hardware behavior.

## Deferred

- Pi-side V4L2 controls, camera settings saved across sessions, focus-point dragging, and continuous autofocus diagnostics.
- OCR algorithm tuning or reducing its four recognition passes; measure performance separately on the Pi before changing recognition quality.
- Camera selection/settings page beyond the OCR popover.
