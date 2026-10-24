import unittest
from delta_infra.registry import default_registry
from delta_infra.runtime import ExecutionCancelled, RunContext

class RegistryTests(unittest.TestCase):
    def test_registry_lists_and_runs_capability(self):
        registry = default_registry()
        description = registry.describe()
        names = {entry["name"] for entry in description}
        self.assertEqual(names, {
            "delta_matroid.local_search", "delta_matroid.signed_greedy",
            "delta_matroid.monotone_path", "delta_matroid.strong_path",
            "delta_matroid.schur_path", "matching.separation", "matching.signed_greedy",
        })
        result = registry.run("matching.signed_greedy", {
            "vertices": ["a", "b"], "edges": [["a", "b"]], "weights": {"a": 3, "b": -1},
        })
        self.assertEqual(set(result["solution"]), {"a", "b"})
        self.assertEqual(result["objective_value"], 2)
        self.assertIn("capability", result)
        E = ["a", "b", "c", "d"]
        even_family = [[], ["a", "b"], ["a", "c"], ["a", "d"], ["b", "c"], ["b", "d"], ["c", "d"], ["a", "b", "c", "d"]]
        base_payload = {"ground_set": E, "feasible_sets": even_family, "weights": {"a": 5, "b": -3, "c": 4, "d": 2}}
        self.assertTrue(registry.run("delta_matroid.local_search", {**base_payload, "initial": []})["converged"])
        self.assertTrue(registry.run("delta_matroid.signed_greedy", base_payload)["verified_feasible"])
        path = registry.run("delta_matroid.monotone_path", {**base_payload, "A": [], "B": E})
        self.assertEqual(path["steps"], 2)
        mixed_ground = ["x", "y", "z"]
        mixed_family = [[], ["x"], ["y"], ["z"], ["x", "y"], ["x", "z"], ["y", "z"], ["x", "y", "z"]]
        strong = registry.run("delta_matroid.strong_path", {"ground_set": mixed_ground, "feasible_sets": mixed_family, "A": [], "B": ["x", "y", "z"], "dummy": "#"})
        self.assertTrue(strong["lift_validated"])
        matrix = registry.run("delta_matroid.schur_path", {"field": {"type": "GF", "p": 3}, "labels": ["a", "b"], "matrix": [[0, 1], [2, 0]]})
        self.assertTrue(matrix["complete"])
        separator = registry.run("matching.separation", {"vertices": ["a", "b"], "edges": [["a", "b"]], "S": ["a", "b"], "T": []})
        self.assertTrue(separator["feasible"])
    def test_run_context_cancels_inside_explicit_family_exchange_validation(self):
        calls = {"count": 0}
        def cancel_during_validation():
            calls["count"] += 1
            return calls["count"] >= 5
        context = RunContext.create(cancelled=cancel_during_validation)
        E = ["a", "b", "c", "d"]
        family = [[], ["a", "b"], ["a", "c"], ["a", "d"], ["b", "c"], ["b", "d"], ["c", "d"], ["a", "b", "c", "d"]]
        payload = {"ground_set": E, "feasible_sets": family, "weights": {"a": 5, "b": -3, "c": 4, "d": 2}}
        with self.assertRaises(ExecutionCancelled):
            default_registry().run("delta_matroid.signed_greedy", payload, context=context)
        self.assertGreaterEqual(calls["count"], 5)

    def test_missing_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            default_registry().run("matching.signed_greedy", {"vertices": []})

if __name__ == "__main__": unittest.main()
