# Task 5 report — shared touchscreen verification

## Implemented

- Fixed the companion route so `/checkout-ui.js` reaches the touchscreen asset handler instead of the legacy 404 guard.
- Added static asset route and MIME checks covering the page's checkout and return scripts.
- Fixed the home action grid remaining visible after a flow starts. The `#home` grid's `display:grid` rule overrode the browser's built-in `[hidden]` styling; `#home[hidden]{display:none}` now restores the intended one-task-at-a-time screen.
- Fixed hidden transaction panels being displayed because their `display:grid` rule overrode `[hidden]`. Added explicit hidden selectors for checkout and return.
- Hide the badge form and recognition message after successful verification, clearing both when the shared session resets.
- Added a shared fixed Review/Confirm action bar for checkout and return. The flow content reserves space below its scrollable content so the bar remains available without permanently covering the last fields.
- Replaced the stale verifier with a self-contained `file://` fixture using the real HTML/CSS/JS, synthetic fetch responses, and no Homebox requests. It distinguishes browser startup/load failure from functional assertions and enforces primary button visibility.

## Focused verification

All required focused suites passed:

| Command | Result |
| --- | --- |
| `PYTHONPATH=ops:kiosk python3 -m unittest discover -s tests -p 'test_kiosk_admin_access.py' -v` | 6 passed; anonymous/member direct manager mutations denied; configured manager action through `/workshop-api` passed |
| `python3 -m unittest discover -s tests -p 'test_touchscreen_shell.py' -v` | 3 passed |
| `python3 -m unittest discover -s tests -p 'test_checkout_cart_ui.py' -v` | 1 passed |
| `python3 -m unittest discover -s tests -p 'test_touchscreen_checkout.py' -v` | 4 passed |
| `python3 -m unittest discover -s tests -p 'test_return_scan_contract.py' -v` | 3 passed |
| `python3 -m unittest discover -s tests -p 'test_kiosk_api_status.py' -v` | 3 passed |
| `python3 -m unittest discover -s tests -p 'test_touchscreen_return.py' -v` | 3 passed |
| `python3 -m unittest discover -s tests -p 'test_kiosk_static_assets.py' -v` | 1 passed |

`python3 -m py_compile deploy/verify-checkout-redesign.py` and `git diff --check` passed.

`python3 deploy/verify-checkout-redesign.py` passed checkout and return badge → search → scan → review → confirm → receipt flows. At 800×480 both flows had no horizontal overflow, all buttons were at least 44 px, both primary actions were within the viewport, inactive transaction UI and manager controls were hidden, long names and per-item notes were present, return condition/location were visible, and each confirmation was sent exactly once. Synthetic APIs handled all requests; zero Homebox requests were made.

## Browser evidence and remaining gap

Chromium screenshots were visually inspected: [checkout review](/tmp/ccrate-checkout-review-800x480.png) and [return review](/tmp/ccrate-return-review-800x480.png). The initial screenshots exposed the home/flow hidden-state conflict and primary actions below the viewport; both were fixed and recaptured. The final screenshots show the active flow only and the shared actions anchored at the bottom edge.

No dependencies were downloaded; no Homebox, live inventory, devices, service, or deployment were used. Task 5 is complete for synthetic browser coverage; physical touchscreen/scanner acceptance remains for the Pi.
