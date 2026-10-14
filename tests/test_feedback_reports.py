import json
import shutil
import tempfile
from uuid import uuid4
import unittest
from pathlib import Path

from ops.feedback_reports import FeedbackReportService


class FeedbackReportServiceTests(unittest.TestCase):
    def setUp(self):
        temp_root = Path(__file__).resolve().parents[1] / "work" / "test-temp"
        temp_root.mkdir(parents=True, exist_ok=True)
        self.temp = Path(tempfile.mkdtemp(prefix="feedback-", dir=temp_root))
        self.db = self.temp / "reports.sqlite3"
        self.calls = []
        self.token = "server-only-test-token"

        def github(method, url, headers, body):
            self.calls.append((method, url, headers, body))
            if method == "POST":
                return 201, {"html_url": "https://github.com/Spraten/ccrate/issues/123"}
            return 200, {"items": []}

        self.github = github
        self.service = FeedbackReportService(self.db, self.token, github=self.github, repository="Spraten/ccrate")

    def tearDown(self):
        shutil.rmtree(self.temp)

    def test_creates_report_once_and_replays_same_result(self):
        request_id = "f04d2e76-57db-4da3-87a8-51e5c804d5db"
        first = self.service.submit("actor-a", request_id, "bug", "The save button stays disabled after retry.")
        second = self.service.submit("actor-a", request_id, "bug", "The save button stays disabled after retry.")

        self.assertEqual(first[0], 201)
        self.assertEqual(first[1], second[1])
        self.assertEqual(second[0], 200)
        self.assertEqual(sum(call[0] == "POST" for call in self.calls), 1)
        self.assertIn("server-only-test-token", self.calls[0][2]["Authorization"])

    def test_uncertain_create_is_reconciled_without_a_second_post(self):
        request_id = "226ad684-01a7-44b8-9f89-6e09914c9861"
        post_attempts = 0

        def uncertain(method, url, headers, body):
            nonlocal post_attempts
            self.calls.append((method, url, headers, body))
            if method == "POST":
                post_attempts += 1
                raise TimeoutError("connection lost after request")
            return 200, {"items": []}

        self.service.github = uncertain
        first = self.service.submit("actor-a", request_id, "idea", "Show the active location at the top.")
        check = self.service.status("actor-a", request_id)
        retry = self.service.submit("actor-a", request_id, "idea", "Show the active location at the top.")

        self.assertEqual(first[0], 202)
        self.assertEqual(check[1]["status"], "pending")
        self.assertEqual(retry[0], 202)
        self.assertEqual(post_attempts, 1)

    def test_reconciliation_records_issue_when_marker_is_found(self):
        request_id = "9cc42037-b832-4666-b611-6f960f0a3c20"
        marker = request_id.replace("-", "")

        def lost_then_found(method, url, headers, body):
            self.calls.append((method, url, headers, body))
            if method == "POST":
                raise TimeoutError("connection lost")
            return 200, {"items": [{"html_url": "https://github.com/Spraten/ccrate/issues/456",
                                      "body": f"<!-- ccrate-feedback-{marker} -->"}]}

        self.service.github = lost_then_found
        self.service.submit("actor-a", request_id, "other", "Add a useful report template.")
        result = self.service.status("actor-a", request_id)

        self.assertEqual(result[1]["status"], "submitted")
        self.assertEqual(result[1]["issue_url"], "https://github.com/Spraten/ccrate/issues/456")

    def test_status_is_private_to_the_authenticated_actor(self):
        request_id = "ccf90fd5-ae22-433d-b855-083b2572b7e4"
        self.service.submit("actor-a", request_id, "bug", "A bug report with enough detail.")

        self.assertEqual(self.service.status("actor-b", request_id)[0], 404)

    def test_repeated_status_checks_are_throttled(self):
        request_id = "ed2d670a-720e-467f-8ee3-a28943a8b2c0"

        def uncertain(method, url, headers, body):
            self.calls.append((method, url, headers, body))
            if method == "POST":
                raise TimeoutError("connection lost")
            return 200, {"items": []}

        self.service.github = uncertain
        self.service.submit("actor-a", request_id, "bug", "The page loses its current selection.")
        self.service.status("actor-a", request_id)
        self.service.status("actor-a", request_id)

        self.assertEqual(sum(call[0] == "GET" for call in self.calls), 1)

    def test_submission_rate_limit_is_per_actor(self):
        for index in range(5):
            request_id = f"00000000-0000-4000-8000-{index + 1:012d}"
            self.service.submit("actor-a", request_id, "idea", f"Add useful inventory view number {index}.")

        status, result = self.service.submit("actor-a", "00000000-0000-4000-8000-000000000099", "idea", "Add another useful inventory view.")

        self.assertEqual(status, 429)
        self.assertEqual(result["status"], "not_started")

    def test_missing_credential_does_not_create_a_pending_request(self):
        service = FeedbackReportService(self.db, "", github=self.github, repository="Spraten/ccrate")

        status, body = service.submit("actor-a", "f04d2e76-57db-4da3-87a8-51e5c804d5db", "bug", "A bug report with enough detail.")

        self.assertEqual(status, 503)
        self.assertEqual(body["status"], "not_started")
        self.assertFalse(self.db.exists())
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
