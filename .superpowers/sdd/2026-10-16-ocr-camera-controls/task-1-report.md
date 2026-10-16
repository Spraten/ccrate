# Task 1 report — capability discovery and safe setting helpers

Implemented `describeCameraControls()` and `applyCameraControl()` in `homebox-ui/overlay/lib/ocr-camera-controls.js`, with mocked MediaStreamTrack-like tests in `tests/ocr_camera_controls.test.mjs`.

The helper reports only capabilities provided by the track, including reported focus modes, and uses current track settings for values. It validates focus modes, clamps and step-rounds numeric controls, merges the selected supported key into existing constraints, rejects ended tracks, and never stops the camera. Unsupported/invalid operations throw `CameraControlError` with `code` values `unsupported`, `invalid-value`, or `stale-track`.

## TDD and verification

- RED: `node --test tests/ocr_camera_controls.test.mjs` failed because the helper module did not yet exist (`ERR_MODULE_NOT_FOUND`).
- GREEN: `node --test tests/ocr_camera_controls.test.mjs` passed all 4 tests.
- `git diff --check` passed.

Commit: `361e249 Add safe OCR camera control helpers`.
