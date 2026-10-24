from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from delta_infra.workflow import TaskExecutionController, WorkflowDefinition, WorkflowDefinitionError, WorkflowInputError, WorkflowRunStore, verify_matching_optimum
from delta_infra.registry import Capability, default_registry

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


class DurableCheckpointTests(unittest.TestCase):
    def test_checkpoint_sequence_uses_compare_and_swap(self):
        with tempfile.TemporaryDirectory() as temp:
            store = WorkflowRunStore(Path(temp) / "runs.sqlite3")
            first = store.save_checkpoint(
                run_id="run-cas", workflow_id="flow", workflow_fingerprint="fingerprint",
                status="running", checkpoint={"step": 1}, expected_previous_sequence=None,
            )
            self.assertEqual(first, 1)
            with self.assertRaises(WorkflowInputError):
                store.save_checkpoint(
                    run_id="run-cas", workflow_id="flow", workflow_fingerprint="fingerprint",
                    status="running", checkpoint={"step": "stale"}, expected_previous_sequence=None,
                )
            second = store.save_checkpoint(
                run_id="run-cas", workflow_id="flow", workflow_fingerprint="fingerprint",
                status="running", checkpoint={"step": 2}, expected_previous_sequence=1,
            )
            self.assertEqual(second, 2)
            latest = store.get_latest_checkpoint("run-cas")
            self.assertEqual(latest["sequence"], 2)
            self.assertEqual(latest["checkpoint"]["step"], 2)
            self.assertEqual(len(store.list_checkpoints("run-cas")), 2)

    def test_resume_reuses_successful_task_output_and_retries_only_failed_safe_task(self):
        with tempfile.TemporaryDirectory() as temp:
            store = WorkflowRunStore(Path(temp) / "runs.sqlite3")
            registry = default_registry()
            calls = {"stable": 0, "transient": 0}

            def stable(payload, *, context=None):
                calls["stable"] += 1
                if context is not None:
                    context.checkpoint()
                return {"value": "cached"}

            def transient(payload, *, context=None):
                calls["transient"] += 1
                if context is not None:
                    context.checkpoint()
                if calls["transient"] == 1:
                    raise RuntimeError("simulated transient failure")
                return {"value": payload["input"] + "-recovered"}

            registry.register(Capability(
                "test.stable", "1.0", "test-only deterministic capability",
                (), (), stable, side_effect_class="none", retry_safe=True,
            ))
            registry.register(Capability(
                "test.transient", "1.0", "test-only retry-safe capability",
                (), ("input",), transient, side_effect_class="none", retry_safe=True,
            ))
            controller = TaskExecutionController(registry=registry, run_store=store)
            doc = {
                "workflow_id": "resume-safe-workflow",
                "tasks": [
                    {"id": "prepare", "type": "capability", "capability": "test.stable", "inputs": {}},
                    {"id": "finish", "type": "capability", "capability": "test.transient",
                     "depends_on": ["prepare"], "inputs": {"input": {"$ref": "prepare.value"}}},
                ],
            }
            first = controller.run(doc)
            self.assertEqual(first["status"], "failed")
            run_id = first["run_id"]
            self.assertEqual(calls, {"stable": 1, "transient": 1})
            latest = store.get_latest_checkpoint(run_id)
            self.assertEqual(latest["checkpoint"]["completed_task_ids"], ["prepare"])
            self.assertIn("prepare", latest["checkpoint"]["outputs"])

            changed = {**doc, "description": "changed fingerprint"}
            with self.assertRaisesRegex(WorkflowInputError, "definition differs"):
                controller.run(changed, resume_from_run_id=run_id)
            self.assertEqual(calls, {"stable": 1, "transient": 1})

            resumed = controller.run(doc, resume_from_run_id=run_id)
            self.assertEqual(resumed["status"], "succeeded")
            self.assertTrue(resumed["resumed_from_checkpoint"])
            self.assertEqual(calls, {"stable": 1, "transient": 2})
            self.assertEqual(resumed["outputs"]["prepare"]["value"], "cached")
            self.assertEqual(resumed["outputs"]["finish"]["value"], "cached-recovered")
            self.assertEqual(resumed["run_id"], run_id)
            self.assertGreaterEqual(len(store.list_checkpoints(run_id)), 5)

    def test_successfully_completed_workflow_cannot_be_resumed(self):
        with tempfile.TemporaryDirectory() as temp:
            store = WorkflowRunStore(Path(temp) / "runs.sqlite3")
            doc = {
                "workflow_id": "completed-resume-test",
                "tasks": [{
                    "id": "gate", "type": "builtin", "handler": "decide_internal_shadow_gate",
                    "inputs": {"optimization": {"member_verified": True}, "verification": {"verified_optimal": True}},
                }],
            }
            controller = TaskExecutionController(run_store=store)
            result = controller.run(doc)
            self.assertEqual(result["status"], "succeeded")
            with self.assertRaisesRegex(WorkflowInputError, "successfully completed"):
                controller.run(doc, resume_from_run_id=result["run_id"])

    def test_resume_refuses_capability_without_retry_safe_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            store = WorkflowRunStore(Path(temp) / "runs.sqlite3")
            registry = default_registry()
            calls = {"count": 0}
            def unsafe(payload):
                calls["count"] += 1
                raise RuntimeError("failure after a possible external side effect")
            registry.register(Capability(
                "test.unsafe", "1.0", "not marked retry-safe", (), (),
                unsafe, side_effect_class="external", retry_safe=False,
            ))
            controller = TaskExecutionController(registry=registry, run_store=store)
            doc = {"workflow_id": "unsafe-resume-test", "tasks": [
                {"id": "unsafe", "type": "capability", "capability": "test.unsafe", "inputs": {}},
            ]}
            first = controller.run(doc)
            self.assertEqual(first["status"], "failed")
            with self.assertRaisesRegex(WorkflowInputError, "not declared retry-safe"):
                controller.run(doc, resume_from_run_id=first["run_id"])
            self.assertEqual(calls["count"], 1)


if __name__=="__main__": unittest.main()
