"""Tests for the machine-readable ecosystem registry."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RegistryTests(unittest.TestCase):
    def test_registry_is_valid_json(self):
        registry = json.loads((ROOT / "ecosystem/registry.json").read_text(encoding="utf-8"))
        self.assertEqual(registry["schema_version"], "1.0.0")
        self.assertTrue(registry["components"])

    def test_component_ids_are_unique(self):
        registry = json.loads((ROOT / "ecosystem/registry.json").read_text(encoding="utf-8"))
        ids = [component["id"] for component in registry["components"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_imported_decision_module_has_ci_evidence_and_disclosed_limits(self):
        registry = json.loads((ROOT / "ecosystem/registry.json").read_text(encoding="utf-8"))
        component = next(c for c in registry["components"] if c["id"] == "delta-decision-infrastructure")
        self.assertEqual(component["status"], "integrated")
        self.assertEqual(component["version"], "0.8.0")
        self.assertEqual(component["source"], "this-repository")
        self.assertEqual(component["validation"]["status"], "ci-passed")
        self.assertEqual(component["validation"]["tests"], 77)
        self.assertIn("40150302288", component["validation"]["scope"])
        self.assertTrue(component["known_limitations"])
        self.assertTrue(any("cannot forcibly interrupt" in item for item in component["known_limitations"]))

    def test_portfolio_inventory_covers_connected_and_adjacent_repositories(self):
        portfolio = json.loads((ROOT / "ecosystem/portfolio.json").read_text(encoding="utf-8"))
        components = {component["id"]: component for component in portfolio["components"]}
        self.assertGreaterEqual(len(components), 9)
        self.assertEqual(components["el-rouji-core"]["maturity"], "deployed")
        self.assertEqual(components["el-rouji-mcp-adapter"]["maturity"], "implemented-unverified")
        self.assertEqual(components["el-rouji-commerce"]["maturity"], "specification-only")
        self.assertEqual(components["el-rouji-jobs"]["maturity"], "specification-only")
        self.assertEqual(components["el-rouji-datasets"]["maturity"], "specification-only")
        self.assertIsNone(components["el-rouji-mcp-adapter"]["production_endpoint"])
        self.assertTrue(components["el-rouji-core"]["known_gaps"])

    def test_portfolio_dependencies_and_connections_are_grounded(self):
        portfolio = json.loads((ROOT / "ecosystem/portfolio.json").read_text(encoding="utf-8"))
        ids = {component["id"] for component in portfolio["components"]}
        for component in portfolio["components"]:
            self.assertTrue(set(component["dependencies"]).issubset(ids), component["id"])
        connection_ids = [connection["id"] for connection in portfolio["connections"]]
        self.assertEqual(len(connection_ids), len(set(connection_ids)))
        for connection in portfolio["connections"]:
            self.assertIn(connection["from"], ids)
            self.assertIn(connection["to"], ids)
            self.assertTrue(connection["required_gates"], connection["id"])
        self.assertEqual(
            next(c for c in portfolio["connections"] if c["id"] == "mcp-to-core")["state"],
            "implemented-but-not-end-to-end-verified",
        )

    def test_repository_validator_passes(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/validate_registry.py")],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
