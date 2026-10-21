# Task 4: Scan-verified touchscreen returns

Implemented a return workflow in `kiosk/return-ui.js` and mounted it in the existing touchscreen shell. Members must scan a badge, physically scan each selected item, review one batch, and confirm once. Search only selects a candidate. Return review shows the recorded condition and assigned location, supports an optional return note, and requires a separate issue note when changing condition. Kit returns preserve manifest versions and rely on component scan evidence from `/api/kit`.

Added badge-bound `GET /return/availability`. The endpoint accepts only 1–50 unique selected IDs, verifies group membership and session stability, checks custody and unresolved operations, and returns only selected IDs with eligibility, reason, condition, and parent location. It does not serialize custody rows. Anonymous return remains available to existing backend callers but is not exposed by this UI.

Confirmation uses a stable request key and captured badge generation/instance. An uncertain result offers only operation-status recovery; it does not retry confirmation. The completed receipt remains until Done, whose event carries its captured session identity.

Validation completed:

- `python3 -m unittest discover -s tests -p 'test_return_scan_contract.py' -v`
- `python3 -m unittest discover -s tests -p 'test_kiosk_api_status.py' -v`
- `python3 -m unittest discover -s tests -p 'test_touchscreen_return.py' -v`
- `python3 -m unittest discover -s tests -p 'test_touchscreen_checkout.py' -v`
- `python3 -m py_compile deploy/kiosk-server.py`
- `git diff --check`

No live Homebox was accessed.

## Review follow-up

Added executable Node behavior coverage for badge gating, search candidate mismatch, availability blockers, displayed condition/location, issue and return notes, uncertain confirmation recovery, and captured-session Done. Added isolated `Handler.do_GET` fixtures for checked-out and in-stock items, unresolved operations, selected-ID-only response, active-badge requirement, malformed/duplicate/over-limit IDs, and stale sessions. Restored the actual anonymous session endpoint regression test. Existing `test_returns.py` confirms backend anonymous return and verified-kit behavior remain intact; the UI contains no anonymous return mode.

Follow-up checks passed: focused kiosk API, return scan, touchscreen return, touchscreen checkout, and return transaction suites; `py_compile`; `git diff --check`. For `test_returns.py`, `PYTHONPATH=ops` is required by its imports.

## Integration review follow-up

Return requests now send the shell's stable `X-Homebox-Client` UUID, including search, scan, kit manifest, selected-item availability, confirmation, and status recovery requests. Availability permits checked-out damaged items; it blocks unresolved operations, items outside custody, location entities, and quantities other than one. Executable regression fixtures cover client-header propagation and Broken/Needs Attention return eligibility.

The focused touchscreen return, API status, return scan, and checkout suites passed; server compilation and diff checks passed. No live Homebox was accessed.
