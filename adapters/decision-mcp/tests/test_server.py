import asyncio
import json
import threading
import unittest
from unittest.mock import patch

from ecosystem_decision_mcp import server


MATCHING_PAYLOAD = {
    "vertices": ["a", "b"],
    "edges": [["a", "b"]],
    "weights": {"a": 3, "b": -1},
}
EVEN_FAMILY_PAYLOAD = {
    "ground_set": ["a", "b", "c", "d"],
    "feasible_sets": [
        [], ["a", "b"], ["a", "c"], ["a", "d"],
        ["b", "c"], ["b", "d"], ["c", "d"], ["a", "b", "c", "d"],
    ],
    "A": [],
    "B": ["a", "b", "c", "d"],
}


def execute(capability: str, payload: object) -> dict:
    return json.loads(server._execute(capability, json.dumps(payload, allow_nan=True), threading.Event()))


class DecisionMcpTests(unittest.TestCase):
    def test_capability_list_contains_only_registered_pure_allowlisted_tools(self):
        registry = server.default_registry()
        listed = json.loads(asyncio.run(server.ecosystem_list_capabilities()))
        names = {item["name"] for item in listed["capabilities"]}
        self.assertEqual(names, set(server.CAPABILITY_IDS))
        for item in registry.describe():
            if item["name"] in names:
                self.assertEqual(item["side_effect_class"], "none")
                self.assertTrue(item["retry_safe"])
        self.assertEqual(listed["limits"]["concurrent_runs"], 1)
        self.assertEqual(listed["limits"]["timeout_type"], "cooperative")

    def test_matching_signed_greedy_runs_with_trace_and_budget_metadata(self):
        result = execute("matching.signed_greedy", MATCHING_PAYLOAD)
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["capability_id"], "matching.signed_greedy")
        self.assertEqual(result["result"]["objective_value"], 2)
        self.assertEqual(result["result"]["member_verified"], True)
        self.assertIn("trace_id", result)
        self.assertEqual(result["runtime"]["tasks_started"], 1)
        self.assertEqual(result["runtime"]["timeout_type"], "cooperative")

    def test_monotone_path_accepts_its_contract_without_irrelevant_weights(self):
        result = execute("delta_matroid.monotone_path", EVEN_FAMILY_PAYLOAD)
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["result"]["steps"], 2)

    def test_tool_wrapper_returns_valid_structured_json(self):
        result = json.loads(asyncio.run(server.ecosystem_run_capability(
            "matching.signed_greedy", json.dumps(MATCHING_PAYLOAD)
        )))
        self.assertEqual(result["status"], "succeeded")

    def test_unknown_capability_is_rejected(self):
        result = json.loads(server._execute("shell.execute", "{}", threading.Event()))
        self.assertEqual(result["status"], "rejected")
        self.assertIn("allow-list", result["error"]["message"])

    def test_malformed_nonfinite_and_oversized_inputs_are_rejected(self):
        malformed = json.loads(server._execute("matching.signed_greedy", "{", threading.Event()))
        self.assertEqual(malformed["status"], "rejected")

        nonfinite = json.loads(server._execute(
            "matching.signed_greedy",
            '{"vertices":["a","b"],"edges":[["a","b"]],"weights":{"a":NaN,"b":1}}',
            threading.Event(),
        ))
        self.assertEqual(nonfinite["status"], "rejected")

        oversized = json.loads(server._execute(
            "matching.signed_greedy", " " * (server.MAX_INPUT_BYTES + 1), threading.Event()
        ))
        self.assertEqual(oversized["status"], "rejected")

    def test_unknown_fields_and_oversized_graphs_are_rejected(self):
        extra = {**MATCHING_PAYLOAD, "command": "do not execute"}
        self.assertEqual(execute("matching.signed_greedy", extra)["status"], "rejected")

        vertices = [f"v{i}" for i in range(server.MAX_GRAPH_VERTICES + 1)]
        payload = {"vertices": vertices, "edges": [], "weights": {v: 1 for v in vertices}}
        self.assertEqual(execute("matching.signed_greedy", payload)["status"], "rejected")

    def test_bad_weights_and_matrix_shapes_are_rejected(self):
        payload = {**MATCHING_PAYLOAD, "weights": {"a": 1, "b": float("inf")}}
        self.assertEqual(execute("matching.signed_greedy", payload)["status"], "rejected")
        self.assertEqual(execute("delta_matroid.schur_path", {"matrix": [[0, 1], [1]]})["status"], "rejected")

    def test_output_budget_is_enforced(self):
        class FakeCapability:
            side_effect_class = "none"
            retry_safe = True

        class FakeRegistry:
            def get(self, name):
                return FakeCapability()

            def run(self, name, payload, *, context=None):
                return {"data": "x" * (server.MAX_OUTPUT_BYTES + 1)}

        with patch.object(server, "default_registry", return_value=FakeRegistry()):
            result = execute("matching.signed_greedy", MATCHING_PAYLOAD)
        self.assertEqual(result["status"], "budget_exceeded")

    def test_concurrent_call_is_rejected_instead_of_queued(self):
        self.assertTrue(server._run_lock.acquire(blocking=False))
        try:
            result = execute("matching.signed_greedy", MATCHING_PAYLOAD)
        finally:
            server._run_lock.release()
        self.assertEqual(result["status"], "busy")


if __name__ == "__main__":
    unittest.main()
