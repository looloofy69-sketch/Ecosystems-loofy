import json
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ecosystem_decision_api.server import (
    MAX_REQUEST_BODY_BYTES,
    MIN_TOKEN_LENGTH,
    create_app,
)


TOKEN = "test-service-token-" + "x" * (MIN_TOKEN_LENGTH + 4)
MATCHING_BODY = {
    "capability_id": "matching.signed_greedy",
    "input": {
        "vertices": ["a", "b"],
        "edges": [["a", "b"]],
        "weights": {"a": 3, "b": -1},
    },
}


class DecisionApiTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"EL_ROUJI_DECISION_API_TOKEN": TOKEN}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = TestClient(create_app())

    def auth(self):
        return {"Authorization": f"Bearer {TOKEN}"}

    def test_public_health_returns_only_minimal_liveness(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})

    def test_protected_endpoints_reject_missing_and_wrong_bearer_tokens(self):
        for headers in ({}, {"Authorization": "Bearer wrong"}):
            with self.subTest(headers=headers):
                response = self.client.get("/v1/capabilities", headers=headers)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["status"], "unauthorized")
                self.assertNotIn(TOKEN, response.text)

    def test_missing_service_token_configuration_fails_closed(self):
        with patch.dict(os.environ, {"EL_ROUJI_DECISION_API_TOKEN": ""}, clear=False):
            response = self.client.get("/v1/capabilities", headers=self.auth())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "unavailable")

    def test_capability_list_is_allowlisted_and_reports_bounds(self):
        response = self.client.get("/v1/capabilities", headers=self.auth())
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["interface_version"], "v1")
        self.assertEqual(
            {item["name"] for item in body["capabilities"]},
            {
                "delta_matroid.local_search",
                "delta_matroid.signed_greedy",
                "delta_matroid.monotone_path",
                "delta_matroid.strong_path",
                "delta_matroid.schur_path",
                "matching.separation",
                "matching.signed_greedy",
            },
        )
        self.assertEqual(body["limits"]["concurrent_runs"], 1)
        self.assertEqual(body["limits"]["timeout_type"], "cooperative")

    def test_run_executes_allowlisted_algorithm_and_returns_evidence(self):
        response = self.client.post("/v1/run", headers=self.auth(), json=MATCHING_BODY)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["status"], "succeeded")
        self.assertTrue(body["request_id"])
        self.assertTrue(body["trace_id"])
        self.assertEqual(body["capability_id"], "matching.signed_greedy")
        self.assertEqual(body["result"]["objective_value"], 2)
        self.assertTrue(body["result"]["member_verified"])
        self.assertLessEqual(body["runtime"]["input_bytes"], 32768)

    def test_unknown_capability_and_unknown_payload_fields_are_rejected(self):
        unknown = self.client.post(
            "/v1/run",
            headers=self.auth(),
            json={"capability_id": "shell.execute", "input": {"cmd": "whoami"}},
        )
        self.assertEqual(unknown.status_code, 422)
        self.assertEqual(unknown.json()["status"], "rejected")

        extra = {**MATCHING_BODY["input"], "cmd": "do not execute"}
        response = self.client.post(
            "/v1/run",
            headers=self.auth(),
            json={"capability_id": "matching.signed_greedy", "input": extra},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["status"], "rejected")

    def test_malformed_or_nonfinite_json_is_rejected(self):
        malformed = self.client.post(
            "/v1/run",
            headers={**self.auth(), "Content-Type": "application/json"},
            content=b'{"capability_id":',
        )
        self.assertEqual(malformed.status_code, 400)

        nonfinite = self.client.post(
            "/v1/run", headers={**self.auth(), "Content-Type": "application/json"},
            content=b'{"capability_id":"matching.signed_greedy","input":{"vertices":["a","b"],"edges":[["a","b"]],"weights":{"a":NaN,"b":1}}}',
        )
        self.assertEqual(nonfinite.status_code, 400)
        self.assertEqual(nonfinite.json()["status"], "rejected")

    def test_oversized_streamed_body_is_rejected(self):
        body = b"x" * (MAX_REQUEST_BODY_BYTES + 1)
        response = self.client.post(
            "/v1/run",
            headers={**self.auth(), "Content-Type": "application/json"},
            content=body,
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["status"], "rejected")

    def test_rate_limit_is_enforced_per_service_token(self):
        client = TestClient(create_app(rate_limit_per_minute=1))
        first = client.post("/v1/run", headers=self.auth(), json=MATCHING_BODY)
        second = client.post("/v1/run", headers=self.auth(), json=MATCHING_BODY)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.headers.get("retry-after"), "60")
        self.assertEqual(second.json()["status"], "rate_limited")


if __name__ == "__main__":
    unittest.main()
