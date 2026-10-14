import importlib.util
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


if __name__ == "__main__":
    unittest.main()
