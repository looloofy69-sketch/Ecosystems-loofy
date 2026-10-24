import unittest
from delta_infra.runtime import BudgetLedger, ExecutionBudget, ExecutionBudgetExceeded, ExecutionCancelled, RunContext, RuntimeGuard, RuntimePolicyError

class RuntimeGuardTests(unittest.TestCase):
    def test_task_budget(self):
        with self.assertRaises(ExecutionBudgetExceeded): RuntimeGuard(ExecutionBudget(max_tasks=1)).preflight(2, {"ok": True})
    def test_input_budget(self):
        with self.assertRaises(ExecutionBudgetExceeded): RuntimeGuard(ExecutionBudget(max_input_bytes=4)).preflight(1, {"long": "payload"})
    def test_output_budget(self):
        with self.assertRaises(ExecutionBudgetExceeded): RuntimeGuard(ExecutionBudget(max_output_bytes=4)).check_output({"long": "payload"})
    def test_cooperative_cancellation(self):
        with self.assertRaises(ExecutionCancelled): RuntimeGuard(cancelled=lambda: True).checkpoint()
    def test_invalid_budget_rejected(self):
        with self.assertRaises(RuntimePolicyError): ExecutionBudget(max_tasks=0)
    def test_normal_checkpoint(self):
        guard = RuntimeGuard(); guard.preflight(1, {"small": True}); guard.check_output({"result": "ok"})


class RunContextTests(unittest.TestCase):

    def test_policy_snapshot_is_deeply_immutable(self):
        context = RunContext.create(policy_snapshot={"nested": {"items": [1, 2]}})
        with self.assertRaises(TypeError):
            context.policy_snapshot["new"] = "not allowed"
        with self.assertRaises(TypeError):
            context.policy_snapshot["nested"]["items"][0] = 9
        with self.assertRaises(RuntimePolicyError):
            context.set_policy_snapshot({"new": "snapshot"})
        self.assertEqual(context.checkpoint_metadata()["policy_snapshot"], {"nested": {"items": [1, 2]}})

    def test_shared_context_tracks_tasks_inputs_outputs_and_checkpoints(self):
        budget = ExecutionBudget(max_tasks=3, max_input_bytes=100, max_output_bytes=1000)
        context = RunContext.create(budget=budget, policy_snapshot={"policy": "test"})
        guard = RuntimeGuard(context=context)
        guard.preflight(2, {"plan": True})
        task_payload = {"task": "one"}
        guard.begin_task(task_payload)
        guard.check_output({"result": "ok"})
        snapshot = context.checkpoint_metadata()
        self.assertEqual(snapshot["run_id"], context.run_id)
        self.assertEqual(snapshot["policy_snapshot"], {"policy": "test"})
        self.assertEqual(snapshot["ledger"]["tasks_started"], 1)
        self.assertEqual(snapshot["ledger"]["input_bytes"], len(b'{"task":"one"}'))
        self.assertEqual(snapshot["ledger"]["output_bytes"], len(b'{"result":"ok"}'))
        self.assertGreater(snapshot["ledger"]["checkpoints"], 0)
        self.assertGreaterEqual(snapshot["remaining_seconds"], 0)

    def test_input_budget_is_cumulative_across_task_dispatches(self):
        context = RunContext.create(budget=ExecutionBudget(max_tasks=3, max_input_bytes=10))
        guard = RuntimeGuard(context=context)
        guard.preflight(2, {"plan": 1})
        guard.begin_task({"x": 1})
        with self.assertRaises(ExecutionBudgetExceeded):
            guard.begin_task({"y": 2})
        self.assertEqual(context.ledger.tasks_started, 1)

    def test_ledger_restores_only_nonnegative_integer_counters(self):
        ledger = BudgetLedger.from_mapping({"tasks_started": 2, "input_bytes": 12, "output_bytes": 7, "checkpoints": 5})
        self.assertEqual(ledger.as_dict(), {"tasks_started": 2, "input_bytes": 12, "output_bytes": 7, "checkpoints": 5})
        with self.assertRaises(RuntimePolicyError):
            BudgetLedger.from_mapping({"tasks_started": -1})

    def test_run_context_cancellation_is_visible_to_guard(self):
        cancelled = {"value": False}
        context = RunContext.create(cancelled=lambda: cancelled["value"])
        guard = RuntimeGuard(context=context)
        guard.checkpoint()
        cancelled["value"] = True
        with self.assertRaises(ExecutionCancelled):
            guard.checkpoint()


if __name__ == "__main__": unittest.main()
