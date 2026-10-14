import importlib.util
import io
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("feedback_gateway", ROOT / "deploy" / "workshop-gateway.py")
GATEWAY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATEWAY)


class FeedbackGatewayAuthTests(unittest.TestCase):
    def test_report_requires_the_actor_id_captured_by_the_browser(self):
        actor = "c7f51d15-7df9-4a52-9c13-399ed84509d8"
        self.assertTrue(GATEWAY.feedback_actor_matches(actor, actor))
        self.assertFalse(GATEWAY.feedback_actor_matches("", actor))
        self.assertFalse(GATEWAY.feedback_actor_matches("forged", actor))
        self.assertFalse(GATEWAY.feedback_actor_matches("6b44c74c-4a1b-4738-bc1c-b64d9ac63f44", actor))

    def test_actor_comes_from_native_authenticated_self_response(self):
        sent = {}

        class Response:
            status = 200

            def read(self, _limit):
                return json.dumps({"item": {"id": "c7f51d15-7df9-4a52-9c13-399ed84509d8"}}).encode()

        class Connection:
            def __init__(self, host, port, timeout):
                sent["target"] = (host, port, timeout)

            def request(self, method, path, headers):
                sent.update(method=method, path=path, headers=headers)

            def getresponse(self):
                return Response()

            def close(self):
                pass

        handler = SimpleNamespace(headers={"Authorization": "Bearer native-session", "X-Actor-ID": "forged"})
        with patch.object(GATEWAY.http.client, "HTTPConnection", Connection):
            actor = GATEWAY.Handler.feedback_actor(handler)

        self.assertEqual(actor, "c7f51d15-7df9-4a52-9c13-399ed84509d8")
        self.assertEqual(sent["path"], "/api/v1/users/self")
        self.assertEqual(sent["headers"], {"Accept": "application/json", "Authorization": "Bearer native-session"})

    def test_no_native_authentication_header_means_no_actor(self):
        handler = SimpleNamespace(headers={"X-Actor-ID": "forged"})

        with patch.object(GATEWAY.http.client, "HTTPConnection", side_effect=AssertionError("must not call Homebox")):
            self.assertIsNone(GATEWAY.Handler.feedback_actor(handler))

    def test_authenticated_report_accepts_3000_cjk_characters(self):
        payload = json.dumps({"type": "bug", "description": "界" * 3000}, ensure_ascii=False).encode()
        response = self._post_report(payload)
        self.assertEqual(response[0], 202)
        self.assertEqual(response[1], "界" * 3000)

    def test_authenticated_report_rejects_body_over_hard_limit(self):
        response = self._post_report(b" " * (GATEWAY.MAX_FEEDBACK_BODY_BYTES + 1))
        self.assertEqual(response[0], 413)
        self.assertEqual(json.loads(response[1])["error"], "The report request is too large.")

    def _post_report(self, body):
        captured = {}

        class Handler(GATEWAY.Handler):
            def send_bytes(self, status, body, *_args, **_kwargs):
                captured.update(status=status, body=body)

        request = Handler.__new__(Handler)
        request.command = "POST"
        request.headers = {"Origin": "http://localhost", "Host": "localhost",
                           "Content-Length": str(len(body)), "X-Crate-Actor-ID": "c7f51d15-7df9-4a52-9c13-399ed84509d8"}
        request.rfile = io.BytesIO(body)
        request.feedback_actor = lambda: "c7f51d15-7df9-4a52-9c13-399ed84509d8"
        request.path = "/ccrate-api/feedback"

        class Service:
            def __init__(self, *_args): pass
            def submit(self, actor_id, _request_id, report_type, description):
                captured["description"] = description
                return 202, {"status": "pending"}

        with patch.object(GATEWAY, "FeedbackReportService", Service):
            request.feedback_report(request.path)
        return captured["status"], captured.get("description", captured["body"])


if __name__ == "__main__":
    unittest.main()
