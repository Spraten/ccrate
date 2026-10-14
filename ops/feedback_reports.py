"""Authenticated, idempotent C-Crate feedback delivery to GitHub."""
import json
import http.client
import os
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import UUID


MAX_DESCRIPTION = 5000
RATE_WINDOW_SECONDS = 60 * 60
RATE_LIMIT = 5
STATUS_CHECK_SECONDS = 15
REPORT_TYPES = {"bug", "idea", "tweak", "question", "other"}


def _github_request(method, url, headers, body):
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=8) as response:
            payload = response.read(1024 * 1024)
            return response.status, json.loads(payload) if payload else {}
    except HTTPError as error:
        try:
            payload = error.read(64 * 1024)
            details = json.loads(payload) if payload else {}
        except (OSError, ValueError):
            details = {}
        return error.code, details


class FeedbackReportService:
    def __init__(self, database, token, repository="Spraten/ccrate", github=None):
        self.database = Path(database)
        self.token = token.strip()
        self.repository = repository.strip()
        self.github = github or _github_request

    def _connect(self):
        self.database.parent.mkdir(mode=0o700 if os.name != "nt" else 0o777, parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database, timeout=5)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("""CREATE TABLE IF NOT EXISTS feedback_reports (
                actor_id TEXT NOT NULL,
                request_id TEXT NOT NULL,
                report_type TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL,
                issue_url TEXT,
                created_at INTEGER NOT NULL,
                last_checked_at INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (actor_id, request_id)
            )""")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(feedback_reports)")}
            if "last_checked_at" not in columns:
                connection.execute("ALTER TABLE feedback_reports ADD COLUMN last_checked_at INTEGER NOT NULL DEFAULT 0")
            connection.commit()
            if os.name != "nt":
                try:
                    os.chmod(self.database, 0o600)
                except OSError:
                    pass
            return connection
        except sqlite3.Error:
            connection.close()
            raise

    @staticmethod
    def _response(status, request_id, *, issue_url=None, error=None):
        result = {"request_id": request_id, "status": status}
        if issue_url:
            result["issue_url"] = issue_url
        if error:
            result["error"] = error
        return result

    def _request_id(self, request_id):
        if not isinstance(request_id, str):
            return None
        try:
            return str(UUID(request_id))
        except (ValueError, TypeError, AttributeError):
            return None

    def _github_headers(self):
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + self.token,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "C-Crate-feedback",
            "Content-Type": "application/json",
        }

    def _marker(self, request_id):
        return "ccrate-feedback-" + request_id.replace("-", "")

    def _issue_url(self, value):
        if not isinstance(value, str):
            return None
        expected = f"https://github.com/{self.repository}/issues/"
        return value if value.startswith(expected) and value[len(expected):].isdigit() else None

    def _reconcile(self, actor_id, request_id):
        if not self.token:
            return self._response("pending", request_id, error="The report result is pending. Check its status again later.")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.repository):
            return self._response("pending", request_id, error="The report result is pending. Check its status again later.")
        try:
            connection = self._connect()
        except (sqlite3.Error, OSError):
            return self._response("pending", request_id, error="The report result is pending. Check its status again later.")
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT status,last_checked_at FROM feedback_reports WHERE actor_id=? AND request_id=?",
                                     (actor_id, request_id)).fetchone()
            now = int(time.time())
            if not row:
                connection.rollback()
                return self._response("pending", request_id, error="The report result is pending. Check its status again later.")
            if row["status"] == "submitted":
                connection.commit()
                return self._response("submitted", request_id)
            if now - row["last_checked_at"] < STATUS_CHECK_SECONDS:
                connection.commit()
                return self._response("pending", request_id, error="A status check just ran. Wait a few seconds and check again; do not resubmit the report.")
            connection.execute("UPDATE feedback_reports SET last_checked_at=? WHERE actor_id=? AND request_id=?",
                               (now, actor_id, request_id))
            connection.commit()
        except sqlite3.Error:
            connection.rollback()
            return self._response("pending", request_id, error="The report result is pending. Check its status again later.")
        finally:
            connection.close()
        marker = self._marker(request_id)
        query = quote(f'repo:{self.repository} "{marker}" in:body', safe="")
        url = "https://api.github.com/search/issues?q=" + query + "&per_page=10"
        try:
            code, payload = self.github("GET", url, self._github_headers(), None)
        except (OSError, TimeoutError, URLError, ValueError, http.client.HTTPException):
            return self._response("pending", request_id, error="GitHub has not confirmed the report yet. Check status again; do not resubmit it.")
        issue = None
        if code == 200 and isinstance(payload, dict):
            for candidate in payload.get("items", []):
                if isinstance(candidate, dict) and marker in str(candidate.get("body", "")):
                    issue = candidate
                    break
        issue_url = self._issue_url(issue.get("html_url")) if issue else None
        if issue and issue_url:
            try:
                with closing(self._connect()) as connection, connection:
                    connection.execute("UPDATE feedback_reports SET status='submitted', issue_url=? WHERE actor_id=? AND request_id=?",
                                       (issue_url, actor_id, request_id))
            except (sqlite3.Error, OSError):
                return self._response("pending", request_id, error="GitHub found the report, but C-Crate could not save its confirmation yet. Check status again; do not resubmit it.")
            return self._response("submitted", request_id, issue_url=issue_url)
        return self._response("pending", request_id, error="GitHub has not confirmed the report yet. Check status again; do not resubmit it.")

    def _row(self, actor_id, request_id):
        with closing(self._connect()) as connection:
            return connection.execute("SELECT * FROM feedback_reports WHERE actor_id=? AND request_id=?",
                                      (actor_id, request_id)).fetchone()

    def submit(self, actor_id, request_id, report_type, description):
        normalized = self._request_id(request_id)
        if not normalized or not isinstance(report_type, str) or report_type not in REPORT_TYPES or not isinstance(description, str):
            return 400, {"status": "not_started", "error": "Choose a report type and enter a description."}
        description = description.strip()
        if not 10 <= len(description) <= MAX_DESCRIPTION:
            return 400, {"status": "not_started", "error": "Description must be between 10 and 5000 characters."}
        if not self.token:
            return 503, {"status": "not_started", "error": "Feedback reporting is not configured on this server. Your draft is still saved in this browser."}
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.repository):
            return 503, {"status": "not_started", "error": "Feedback reporting is not configured on this server. Your draft is still saved in this browser."}

        now = int(time.time())
        try:
            connection = self._connect()
        except (sqlite3.Error, OSError):
            return 503, {"status": "not_started", "error": "The report could not be saved on this server. Your draft is still saved in this browser."}
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT * FROM feedback_reports WHERE actor_id=? AND request_id=?",
                                          (actor_id, normalized)).fetchone()
            if existing:
                if existing["report_type"] != report_type or existing["description"] != description:
                    connection.rollback()
                    return 409, self._response(existing["status"], normalized,
                        issue_url=existing["issue_url"], error="This request is tied to the saved report. Keep its description unchanged while checking its result.")
                connection.commit()
                if existing["status"] == "submitted":
                    return 200, self._response("submitted", normalized, issue_url=existing["issue_url"])
                if existing["status"] == "pending":
                    status = self._reconcile(actor_id, normalized)
                    return (200 if status["status"] == "submitted" else 202), status
                return 422, self._response("rejected", normalized, error="GitHub rejected this report. Edit the draft and submit it again with a new request.")
            count = connection.execute("SELECT count(*) FROM feedback_reports WHERE actor_id=? AND created_at>=?",
                                       (actor_id, now - RATE_WINDOW_SECONDS)).fetchone()[0]
            if count >= RATE_LIMIT:
                connection.rollback()
                return 429, {"status": "not_started", "error": "You have sent several reports recently. Try again in about an hour."}
            connection.execute("INSERT INTO feedback_reports(actor_id,request_id,report_type,description,status,created_at) VALUES(?,?,?,?,?,?)",
                               (actor_id, normalized, report_type, description, "pending", now))
            connection.commit()
        except sqlite3.Error:
            connection.rollback()
            return 503, {"status": "not_started", "error": "The report could not be saved on this server. Your draft is still saved in this browser."}
        finally:
            connection.close()

        marker = self._marker(normalized)
        body = json.dumps({"title": f"C-Crate feedback: {report_type}",
                           "body": description + "\n\n<!-- " + marker + " -->"}).encode()
        url = "https://api.github.com/repos/" + self.repository + "/issues"
        try:
            code, payload = self.github("POST", url, self._github_headers(), body)
        except (OSError, TimeoutError, URLError, ValueError, http.client.HTTPException):
            # Keep the row pending. A later status check searches for its unique body marker.
            return 202, self._response("pending", normalized, error="GitHub did not confirm the result. Check status again; do not resubmit it.")
        issue_url = self._issue_url(payload.get("html_url")) if isinstance(payload, dict) else None
        if code == 201 and issue_url:
            try:
                with closing(self._connect()) as connection, connection:
                    connection.execute("UPDATE feedback_reports SET status='submitted', issue_url=? WHERE actor_id=? AND request_id=?",
                                       (issue_url, actor_id, normalized))
            except (sqlite3.Error, OSError):
                return 202, self._response("pending", normalized, error="GitHub created the report, but C-Crate could not save its confirmation yet. Check status again; do not resubmit it.")
            return 201, self._response("submitted", normalized, issue_url=issue_url)
        if 400 <= code < 500:
            try:
                with closing(self._connect()) as connection, connection:
                    connection.execute("UPDATE feedback_reports SET status='rejected' WHERE actor_id=? AND request_id=?",
                                       (actor_id, normalized))
            except (sqlite3.Error, OSError):
                return 202, self._response("pending", normalized, error="GitHub rejected the report, but C-Crate could not save the result. Check status again before retrying.")
            return 422, self._response("rejected", normalized, error="GitHub rejected this report. Edit the draft and submit it again with a new request.")
        return 202, self._response("pending", normalized, error="GitHub did not confirm the result. Check status again; do not resubmit it.")

    def status(self, actor_id, request_id):
        normalized = self._request_id(request_id)
        if not normalized:
            return 400, {"error": "Invalid report request."}
        try:
            row = self._row(actor_id, normalized)
        except (sqlite3.Error, OSError):
            return 503, {"status": "pending", "error": "C-Crate could not check report status. Keep this request and try again later."}
        if not row:
            return 404, {"error": "Report request not found."}
        if row["status"] == "pending":
            result = self._reconcile(actor_id, normalized)
            return (200 if result["status"] == "submitted" else 202), result
        return 200, self._response(row["status"], normalized, issue_url=row["issue_url"])
