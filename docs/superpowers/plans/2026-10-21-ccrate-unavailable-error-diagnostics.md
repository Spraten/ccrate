# C-Crate Unavailable Error Diagnostics Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Identify the cause of recurring “C-Crate unavailable; no confirmation received” responses without logging badge codes, request bodies, or credentials.

**Architecture:** The companion currently catches broad `OSError` exceptions in `do_POST` and returns a generic 503. Add a correlation ID and sanitized server-side classification to that boundary, retain operation status recovery, then use the resulting route and error class to scope a separate root-cause fix.

**Tech Stack:** Python 3.13 `http.server`, stdlib logging/UUID, fixture-based pytest.

**Spec:** `TODO.md` section “Touchscreen check-in and checkout”; project safety constraints in `AGENTS.md`.

## Global Constraints

- Do not log request/response bodies, badge codes, auth headers, cookies, tokens, or passwords.
- Never automatically repeat a possibly saved checkout, return, note, or create operation.
- Never run mutation checks against operational Homebox; use isolated handler fixtures.
- Keep the cause marked unknown until captured evidence identifies a specific route and failure.

## Review Focus

- A DNS/connection error logs safe class and errno (`test_post_oserror_logs_safe_exception_class_and_errno`).
- A timeout log links to the response with the same request ID (`test_post_oserror_response_and_log_share_request_id`).
- A malicious exception message containing credential-like text is not written verbatim (`test_post_oserror_does_not_log_exception_message_or_body`).
- 400/409 validation conflicts do not get mislabeled as unavailable (`test_post_validation_conflict_keeps_client_error`).
- A confirm 503 remains status-only recovery and cannot be submitted twice (`test_uncertain_checkout_recovery_is_status_only`, `test_uncertain_return_recovery_is_status_only`).

---

### Task 1: Correlate generic POST failures with safe diagnostics

**Files:**
- Modify: `deploy/kiosk-server.py`
- Test: new `tests/test_kiosk_api_failure_diagnostics.py`
- Regression test: `tests/test_touchscreen_checkout.py`, `tests/test_touchscreen_return.py`

**Interfaces:**
- Consumes: caught `OSError`, `self.path`, existing request handler, checkout/return request key where supplied.
- Produces: `reply_api_unavailable(error: OSError) -> None`, which creates a UUID request ID, logs only query-free route, exception class, and numeric errno, then returns HTTP 503 JSON containing the same request ID and the existing safe message. It never logs exception text or request body.

- [ ] **Step 1: Write failing tests** `test_post_oserror_logs_safe_exception_class_and_errno`, `test_post_oserror_response_and_log_share_request_id`, `test_post_oserror_does_not_log_exception_message_or_body`, and `test_post_validation_conflict_keeps_client_error` using a fake handler and captured logger.
- [ ] **Step 2: Run** `pytest tests/test_kiosk_api_failure_diagnostics.py -q`; expected: the shared helper and response correlation field are absent.
- [ ] **Step 3: Add `reply_api_unavailable(error)`** and route caught POST `OSError` cases through it. Keep existing 400, 403, and 409 branches unchanged. Preserve checkout/return status-only behavior for 503 responses.
- [ ] **Step 4: Run** `pytest tests/test_kiosk_api_failure_diagnostics.py tests/test_touchscreen_checkout.py tests/test_touchscreen_return.py -q`; expected: PASS, and captured logs contain no submitted body or raw exception text.
- [ ] **Step 5: Commit** `fix: correlate safe kiosk unavailable diagnostics`.

### Task 2: Resolve the observed failing route

The exact remediation cannot be specified yet: the current implementation hides the exception, and the user has not identified which action triggers the message. After Task 1 is available, capture the correlation ID and route/error class from a naturally occurring report, reproduce that specific failure in a fixture, and write a narrow follow-up plan naming the failing function and regression test. Do not infer a root cause from the generic message alone.
