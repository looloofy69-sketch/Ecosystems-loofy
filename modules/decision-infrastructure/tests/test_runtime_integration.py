"""Runtime budget and cancellation integration at controller boundaries."""
from __future__ import annotations
import unittest
from delta_infra.portfolio import AlgorithmStrategy, PortfolioController, StrategyCatalog, StrategyTurn
from delta_infra.runtime import ExecutionBudget, ExecutionBudgetExceeded
from delta_infra.workflow import TaskExecutionController

class WorkflowRuntimeIntegrationTests(unittest.TestCase):
    @staticmethod
    def document():
        return {"workflow_id": "runtime-integration-test", "tasks": [
            {"id": "first", "type": "builtin", "handler": "emit", "inputs": {"value": "ok"}},
            {"id": "second", "type": "builtin", "handler": "emit", "depends_on": ["first"],
             "inputs": {"value": {"$ref": "first.value"}}},
        ]}
    def test_task_budget_rejects_workflow_before_any_handler_runs(self):
        calls = []
        controller = TaskExecutionController(builtin_handlers={"emit": lambda payload: (calls.append(payload), dict(payload))[1]})
        with self.assertRaises(ExecutionBudgetExceeded):
            controller.run(self.document(), budget=ExecutionBudget(max_tasks=1))
        self.assertEqual(calls, [])
    def test_cancellation_after_handler_stops_run_without_committing_output(self):
        signal = {"cancel": False}
        def cancel_after_work(payload):
            signal["cancel"] = True
            return {"value": "computed"}
        controller = TaskExecutionController(builtin_handlers={"cancel_after_work": cancel_after_work})
        document = {"workflow_id": "cancel-test", "tasks": [
            {"id": "one", "type": "builtin", "handler": "cancel_after_work", "inputs": {}}
        ]}
        result = controller.run(document, cancelled=lambda: signal["cancel"])
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["tasks"][0]["status"], "cancelled")
        self.assertNotIn("one", result["outputs"])
    def test_output_limit_stops_workflow_and_marks_budget_exceeded(self):
        controller = TaskExecutionController(builtin_handlers={"large": lambda payload: {"value": "x" * 300}})
        document = {"workflow_id": "output-limit-test", "tasks": [
            {"id": "one", "type": "builtin", "handler": "large", "inputs": {}}
        ]}
        result = controller.run(document, budget=ExecutionBudget(max_output_bytes=64))
        self.assertEqual(result["status"], "budget_exceeded")
        self.assertEqual(result["tasks"][0]["status"], "budget_exceeded")
        self.assertNotIn("one", result["outputs"])

class PortfolioRuntimeIntegrationTests(unittest.TestCase):
    @staticmethod
    def controller(step):
        catalog = StrategyCatalog()
        catalog.register(AlgorithmStrategy("stepper", "test", step))
        return PortfolioController(catalog)
    def test_task_budget_rejects_excessive_turn_plan(self):
        calls = []
        controller = self.controller(lambda state: (calls.append(1), StrategyTurn("complete", dict(state)))[1])
        with self.assertRaises(ExecutionBudgetExceeded):
            controller.run({"counter": 0}, mode="rotation", max_turns=4, budget=ExecutionBudget(max_tasks=2))
        self.assertEqual(calls, [])
    def test_cancellation_after_strategy_does_not_commit_candidate_state(self):
        signal = {"cancel": False}
        def cancel_after_work(state):
            signal["cancel"] = True
            updated = dict(state); updated["counter"] = 99
            return StrategyTurn("progress", updated)
        initial = {"counter": 0}
        result = self.controller(cancel_after_work).run(initial, mode="rotation", max_turns=2, cancelled=lambda: signal["cancel"])
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["final_state"], initial)
        self.assertEqual(result["turns"][0]["status"], "cancelled")
    def test_output_limit_rejects_candidate_before_state_commit(self):
        initial = {"counter": 0}
        def large_candidate(state):
            updated = dict(state); updated["payload"] = "x" * 300
            return StrategyTurn("progress", updated)
        result = self.controller(large_candidate).run(initial, mode="rotation", max_turns=2, budget=ExecutionBudget(max_output_bytes=64))
        self.assertEqual(result["status"], "budget_exceeded")
        self.assertEqual(result["final_state"], initial)
        self.assertEqual(result["turns"][0]["status"], "budget_exceeded")

if __name__ == "__main__": unittest.main()
