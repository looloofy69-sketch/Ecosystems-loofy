from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from delta_infra.workflow import TaskExecutionController, WorkflowDefinition, WorkflowDefinitionError, WorkflowRunStore, verify_matching_optimum

ROOT=Path(__file__).resolve().parents[1]
EXAMPLE=ROOT/"examples"/"workflows"/"internal_matching_validation.json"

class WorkflowControllerTests(unittest.TestCase):
    def test_end_to_end_matching_validation_and_persistent_history(self):
        document=json.loads(EXAMPLE.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temp:
            store=WorkflowRunStore(Path(temp)/"runs.sqlite3"); result=TaskExecutionController(run_store=store).run(document)
            self.assertEqual(result["status"],"succeeded"); self.assertEqual([t["status"] for t in result["tasks"]],["succeeded"]*3)
            optimize=result["outputs"]["optimize"]; verify=result["outputs"]["verify"]; gate=result["outputs"]["shadow_gate"]
            self.assertEqual(set(optimize["solution"]),{"A","B","C","D"}); self.assertEqual(optimize["objective_value"],8)
            self.assertTrue(verify["verified_optimal"]); self.assertEqual(verify["best_objective_value"],8)
            self.assertEqual(gate["decision"],"ELIGIBLE_FOR_INTERNAL_SHADOW_MODE"); self.assertFalse(gate["production_deployment_authorized"])
            persisted=store.get(result["run_id"]); self.assertEqual(persisted["workflow_id"],"internal-matching-validation")
            self.assertEqual(persisted["outputs"]["verify"]["verified_optimal"],True); self.assertEqual(store.list_runs(1)[0]["run_id"],result["run_id"])
    def test_dependency_failure_skips_downstream_tasks(self):
        doc={"workflow_id":"bad-input-propagation","tasks":[
            {"id":"broken","type":"capability","capability":"matching.signed_greedy","inputs":{"vertices":[]}},
            {"id":"blocked","type":"builtin","handler":"decide_internal_shadow_gate","depends_on":["broken"],"inputs":{"optimization":{"$ref":"broken"},"verification":{"$ref":"broken"}}}]}
        result=TaskExecutionController().run(doc)
        self.assertEqual(result["status"],"failed"); self.assertEqual(result["tasks"][0]["status"],"failed"); self.assertEqual(result["tasks"][1]["status"],"skipped"); self.assertNotIn("blocked",result["outputs"])
    def test_approval_gate_blocks_task_and_resumes_on_approval(self):
        doc={"workflow_id":"approval-gate-test","tasks":[
            {"id":"prepare","type":"builtin","handler":"decide_internal_shadow_gate","inputs":{"optimization":{"member_verified":True},"verification":{"verified_optimal":True}}},
            {"id":"publish","type":"builtin","handler":"decide_internal_shadow_gate","depends_on":["prepare"],"requires_approval":True,"inputs":{"optimization":{"$ref":"prepare"},"verification":{"$ref":"prepare"}}}]}
        controller=TaskExecutionController(); first=controller.run(doc)
        self.assertEqual(first["status"],"approval_required"); self.assertEqual(first["tasks"][1]["status"],"approval_required")
        second=controller.run(doc,approved_task_ids=["publish"]); self.assertEqual(second["status"],"succeeded"); self.assertEqual(second["tasks"][1]["status"],"succeeded")
    def test_cycle_is_rejected_before_execution(self):
        doc={"workflow_id":"cycle","tasks":[
            {"id":"a","type":"builtin","handler":"decide_internal_shadow_gate","depends_on":["b"],"inputs":{}},
            {"id":"b","type":"builtin","handler":"decide_internal_shadow_gate","depends_on":["a"],"inputs":{}}]}
        with self.assertRaisesRegex(WorkflowDefinitionError,"cycle"): WorkflowDefinition.from_mapping(doc)
    def test_reference_requires_declared_dependency(self):
        doc={"workflow_id":"undeclared-reference","tasks":[
            {"id":"a","type":"builtin","handler":"decide_internal_shadow_gate","inputs":{"optimization":{},"verification":{}}},
            {"id":"b","type":"builtin","handler":"decide_internal_shadow_gate","inputs":{"optimization":{"$ref":"a"},"verification":{}}}]}
        with self.assertRaisesRegex(WorkflowDefinitionError,"does not declare it in depends_on"): WorkflowDefinition.from_mapping(doc)
    def test_approval_unknown_task_rejected(self):
        doc={"workflow_id":"approval-unknown","tasks":[{"id":"t","type":"builtin","handler":"decide_internal_shadow_gate","inputs":{"optimization":{},"verification":{}}}]}
        with self.assertRaisesRegex(ValueError,"unknown task ids"): TaskExecutionController().run(doc,approved_task_ids=["missing"])
    def test_independent_verifier_rejects_bad_objective_and_infeasible_solution(self):
        base={"vertices":["a","b","c"],"edges":[["a","b"],["b","c"]],"weights":{"a":3,"b":-1,"c":2},"max_vertices":5}
        wrong=verify_matching_optimum({**base,"solution":["a","b"],"reported_objective_value":99})
        self.assertFalse(wrong["verified_optimal"]); self.assertFalse(wrong["reported_objective_matches_recomputed"])
        infeasible=verify_matching_optimum({**base,"solution":["a","c"],"reported_objective_value":5})
        self.assertFalse(infeasible["solution_feasible"]); self.assertFalse(infeasible["verified_optimal"])
    def test_independent_verifier_enforces_size_limit(self):
        payload={"vertices":["a","b"],"edges":[["a","b"]],"weights":{"a":1,"b":1},"solution":["a","b"],"reported_objective_value":2,"max_vertices":1}
        with self.assertRaisesRegex(ValueError,"limited to 1 vertices"): verify_matching_optimum(payload)

if __name__=="__main__": unittest.main()
