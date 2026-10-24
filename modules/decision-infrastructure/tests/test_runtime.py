import unittest
from delta_infra.runtime import ExecutionBudget, ExecutionBudgetExceeded, ExecutionCancelled, RuntimeGuard, RuntimePolicyError

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

if __name__ == "__main__": unittest.main()
