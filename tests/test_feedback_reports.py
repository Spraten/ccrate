import json
import shutil
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
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

    def seed_report(self, request_id, status):
        connection = self.service._connect()
        try:
            connection.execute(
                "INSERT INTO feedback_reports(actor_id,request_id,report_type,description,status,created_at) VALUES(?,?,?,?,?,?)",
                ("actor-a", request_id, "idea", "Show the active location at the top.", status, 1),
            )
            connection.commit()
        finally:
            connection.close()

    def test_creates_report_once_and_replays_same_result(self):
        request_id = "f04d2e76-57db-4da3-87a8-51e5c804d5db"
        first = self.service.submit("actor-a", request_id, "bug", "The save button stays disabled after retry.")
        second = self.service.submit("actor-a", request_id, "bug", "The save button stays disabled after retry.")

        self.assertEqual(first[0], 201)
        self.assertEqual(first[1], second[1])
        self.assertEqual(second[0], 200)
        self.assertEqual(sum(call[0] == "POST" for call in self.calls), 1)
        self.assertIn("server-only-test-token", self.calls[0][2]["Authorization"])

    def test_tweak_category_is_accepted_by_the_existing_report_api(self):
        request_id = "f04d2e76-57db-4da3-87a8-51e5c804d5db"

        status, result = self.service.submit("actor-a", request_id, "tweak", "Make the report form easier to use.")

        self.assertEqual(status, 201)
        self.assertEqual(result["status"], "submitted")
        payload = json.loads(self.calls[0][3])
        self.assertEqual(payload["title"], "C-Crate feedback: tweak")

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

    def test_ready_report_is_dispatched_after_service_restart(self):
        request_id = str(uuid4())
        self.seed_report(request_id, "ready")
        calls = []

        def github(method, url, headers, body):
            calls.append(method)
            if method == "POST":
                return 201, {"html_url": "https://github.com/Spraten/ccrate/issues/456"}
            return 200, {"items": []}

        restarted = FeedbackReportService(self.db, self.token, github=github, repository="Spraten/ccrate")

        status, result = restarted.status("actor-a", request_id)
        replay = restarted.status("actor-a", request_id)

        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "submitted")
        self.assertEqual(result["issue_url"], "https://github.com/Spraten/ccrate/issues/456")
        self.assertEqual(replay[1]["status"], "submitted")
        self.assertEqual(calls, ["POST"])

    def test_ready_is_not_exposed_when_request_payload_conflicts(self):
        request_id = str(uuid4())
        self.seed_report(request_id, "ready")

        status, result = self.service.submit("actor-a", request_id, "idea", "Show the active location at the bottom.")

        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "pending")
        self.assertEqual(self.calls, [])

    def test_concurrent_ready_recovery_claims_only_one_github_post(self):
        request_id = str(uuid4())
        self.seed_report(request_id, "ready")
        calls = []
        calls_lock = threading.Lock()
        read_barrier = threading.Barrier(2)

        def github(method, url, headers, body):
            with calls_lock:
                calls.append(method)
            if method == "POST":
                return 201, {"html_url": "https://github.com/Spraten/ccrate/issues/456"}
            return 200, {"items": []}

        services = [
            FeedbackReportService(self.db, self.token, github=github, repository="Spraten/ccrate")
            for _ in range(2)
        ]
        for service in services:
            original_row = service._row

            def synchronized_row(actor_id, normalized, original_row=original_row):
                row = original_row(actor_id, normalized)
                if row and row["status"] == "ready":
                    read_barrier.wait(timeout=5)
                return row

            service._row = synchronized_row

        with ThreadPoolExecutor(max_workers=2) as workers:
            futures = [workers.submit(service.status, "actor-a", request_id) for service in services]
            results = [future.result(timeout=10) for future in futures]

        self.assertEqual(sum(method == "POST" for method in calls), 1)
        self.assertTrue(all(result[1]["status"] in {"pending", "submitted"} for result in results))

    def test_pending_report_without_marker_remains_get_only_after_restart(self):
        request_id = str(uuid4())
        self.seed_report(request_id, "pending")
        calls = []

        def github(method, url, headers, body):
            calls.append(method)
            return 200, {"items": []}

        restarted = FeedbackReportService(self.db, self.token, github=github, repository="Spraten/ccrate")

        result = restarted.status("actor-a", request_id)

        self.assertEqual(result[1]["status"], "pending")
        self.assertEqual(calls, ["GET"])

    def test_issue_url_accepts_repository_path_case_variations_but_requires_numeric_issue_id(self):
        service = FeedbackReportService(self.db, self.token, github=self.github,
                                        repository="Spraten/ccrate")

        self.assertEqual(
            service._issue_url("https://github.com/sPrAtEn/CCrate/issues/456"),
            "https://github.com/sPrAtEn/CCrate/issues/456",
        )
        self.assertIsNone(service._issue_url("https://github.com/sPrAtEn/CCrate/issues/not-a-number"))

    def test_concurrent_status_check_returns_saved_issue_url(self):
        request_id = "d306ad72-5b84-4e83-8c2e-c4e95ae1f5fb"
        def uncertain_create(method, url, headers, body):
            self.calls.append((method, url, headers, body))
            if method == "POST":
                raise TimeoutError("connection lost after request")
            return 200, {"items": []}

        self.service.github = uncertain_create
        self.service.submit("actor-a", request_id, "idea", "Show the active location at the top.")
        saved_url = "https://github.com/Spraten/ccrate/issues/789"
        original_row = self.service._row

        def row_then_concurrent_submission(actor_id, normalized):
            row = original_row(actor_id, normalized)
            connection = self.service._connect()
            try:
                connection.execute(
                    "UPDATE feedback_reports SET status='submitted', issue_url=? WHERE actor_id=? AND request_id=?",
                    (saved_url, actor_id, normalized),
                )
                connection.commit()
            finally:
                connection.close()
            return row

        self.service._row = row_then_concurrent_submission
        status, result = self.service.status("actor-a", request_id)

        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "submitted")
        self.assertEqual(result["issue_url"], saved_url)
        self.assertFalse(any(call[0] == "GET" for call in self.calls))

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

