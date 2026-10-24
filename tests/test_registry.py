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
        self.assertEqual(component["version"], "0.7.0")
        self.assertEqual(component["source"], "this-repository")
        self.assertEqual(component["validation"]["status"], "ci-passed")
        self.assertEqual(component["validation"]["tests"], 74)
        self.assertIn("40133079284", component["validation"]["scope"])
        self.assertTrue(component["known_limitations"])
        self.assertTrue(any("cannot forcibly interrupt" in item for item in component["known_limitations"]))

    def test_repository_validator_passes(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/validate_registry.py")],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
