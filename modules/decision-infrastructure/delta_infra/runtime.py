"""Execution budgets and cooperative cancellation primitives.

These controls stop work at explicit checkpoints. They cannot preempt a capability
that blocks internally; long-running capabilities must call checkpoint themselves.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import json
import time
from typing import Any, Callable, Mapping

class RuntimePolicyError(ValueError):
    """An execution request violates configured runtime policy."""
class ExecutionCancelled(RuntimeError):
    """A cooperative checkpoint observed cancellation."""
class ExecutionBudgetExceeded(RuntimeError):
    """A configured execution budget was exceeded."""

@dataclass(frozen=True)
class ExecutionBudget:
    max_tasks: int = 100
    max_input_bytes: int = 1_000_000
    max_output_bytes: int = 2_000_000
    max_duration_seconds: float = 60.0
    def __post_init__(self) -> None:
        for name in ("max_tasks", "max_input_bytes", "max_output_bytes"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise RuntimePolicyError(f"{name} must be a positive integer")
        if isinstance(self.max_duration_seconds, bool) or not isinstance(self.max_duration_seconds, (int, float)) or self.max_duration_seconds <= 0:
            raise RuntimePolicyError("max_duration_seconds must be positive")

@dataclass
class RuntimeGuard:
    budget: ExecutionBudget = field(default_factory=ExecutionBudget)
    cancelled: Callable[[], bool] = lambda: False
    started_at: float = field(default_factory=time.monotonic)
    @property
    def deadline(self) -> float:
        return self.started_at + self.budget.max_duration_seconds
    def preflight(self, task_count: int, payload: Mapping[str, Any]) -> None:
        if task_count > self.budget.max_tasks:
            raise ExecutionBudgetExceeded(f"task count {task_count} exceeds max_tasks={self.budget.max_tasks}")
        size = len(json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8"))
        if size > self.budget.max_input_bytes:
            raise ExecutionBudgetExceeded(f"serialized input size {size} exceeds max_input_bytes={self.budget.max_input_bytes}")
        self.checkpoint()
    def checkpoint(self) -> None:
        if self.cancelled():
            raise ExecutionCancelled("execution cancelled at cooperative checkpoint")
        if time.monotonic() > self.deadline:
            raise ExecutionBudgetExceeded("execution deadline exceeded at cooperative checkpoint")
    def check_output(self, payload: Any) -> None:
        self.checkpoint()
        size = len(json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8"))
        if size > self.budget.max_output_bytes:
            raise ExecutionBudgetExceeded(f"serialized output size {size} exceeds max_output_bytes={self.budget.max_output_bytes}")
