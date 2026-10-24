"""Shared execution context, centrally accounted budgets, and cooperative guards.

A guard can stop work at controller or algorithm checkpoints, but cannot preempt
code that blocks without calling a checkpoint. Hard timeouts require isolation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import time
import uuid
from types import MappingProxyType
from typing import Any, Callable, Mapping


class RuntimePolicyError(ValueError):
    """An execution request violates configured runtime policy."""


class ExecutionCancelled(RuntimeError):
    """A cooperative checkpoint observed cancellation."""


class ExecutionBudgetExceeded(RuntimeError):
    """A configured execution budget was exceeded."""


def _serialized_size(payload: Any) -> int:
    try:
        return len(json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise RuntimePolicyError(f"Runtime payload must be finite JSON-compatible data: {exc}") from exc


def _plain_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_json(item) for item in value]
    return value


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    return value


def _safe_snapshot(value: Mapping[str, Any], *, label: str) -> dict[str, Any]:
    try:
        return json.loads(json.dumps(_plain_json(value), ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise RuntimePolicyError(f"{label} must be JSON-compatible: {exc}") from exc


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
        value = self.max_duration_seconds
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise RuntimePolicyError("max_duration_seconds must be a finite positive number")


@dataclass
class BudgetLedger:
    """Mutable consumption counters owned by one RunContext."""
    tasks_started: int = 0
    input_bytes: int = 0
    output_bytes: int = 0
    checkpoints: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "tasks_started": self.tasks_started,
            "input_bytes": self.input_bytes,
            "output_bytes": self.output_bytes,
            "checkpoints": self.checkpoints,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "BudgetLedger":
        value = value or {}
        result = cls()
        for key in ("tasks_started", "input_bytes", "output_bytes", "checkpoints"):
            number = value.get(key, 0)
            if isinstance(number, bool) or not isinstance(number, int) or number < 0:
                raise RuntimePolicyError(f"ledger.{key} must be a non-negative integer")
            setattr(result, key, number)
        return result


@dataclass
class RunContext:
    """Shared mutable execution context for one logical run.

    The monotonic deadline is process-local. For restart recovery, persist elapsed
    active runtime and construct a new context with only the remaining duration.
    """
    run_id: str
    budget: ExecutionBudget
    cancelled: Callable[[], bool] = field(default=lambda: False, repr=False, compare=False)
    state_version: int = 0
    policy_snapshot: Mapping[str, Any] = field(default_factory=dict)
    trace_id: str = ""
    parent_run_id: str | None = None
    ledger: BudgetLedger = field(default_factory=BudgetLedger)
    started_monotonic: float = field(default_factory=time.monotonic)
    elapsed_before_start_seconds: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            raise RuntimePolicyError("run_id must be non-empty")
        if isinstance(self.state_version, bool) or not isinstance(self.state_version, int) or self.state_version < 0:
            raise RuntimePolicyError("state_version must be a non-negative integer")
        if not isinstance(self.budget, ExecutionBudget):
            raise RuntimePolicyError("budget must be an ExecutionBudget")
        if not callable(self.cancelled):
            raise RuntimePolicyError("cancelled must be callable")
        if not isinstance(self.policy_snapshot, Mapping):
            raise RuntimePolicyError("policy_snapshot must be a mapping")
        self.policy_snapshot = _freeze_json(_safe_snapshot(self.policy_snapshot, label="policy_snapshot"))
        if not self.trace_id:
            self.trace_id = str(uuid.uuid4())
        if isinstance(self.elapsed_before_start_seconds, bool) or not isinstance(self.elapsed_before_start_seconds, (int, float)) or not math.isfinite(self.elapsed_before_start_seconds) or self.elapsed_before_start_seconds < 0:
            raise RuntimePolicyError("elapsed_before_start_seconds must be a finite non-negative number")

    def set_policy_snapshot(self, value: Mapping[str, Any]) -> None:
        if self.policy_snapshot:
            raise RuntimePolicyError("policy_snapshot is already set and cannot be replaced")
        self.policy_snapshot = _freeze_json(_safe_snapshot(value, label="policy_snapshot"))

    @classmethod
    def create(
        cls,
        *,
        budget: ExecutionBudget | None = None,
        cancelled: Callable[[], bool] | None = None,
        run_id: str | None = None,
        state_version: int = 0,
        policy_snapshot: Mapping[str, Any] | None = None,
        trace_id: str | None = None,
        parent_run_id: str | None = None,
        ledger: BudgetLedger | None = None,
        elapsed_before_start_seconds: float = 0.0,
    ) -> "RunContext":
        return cls(
            run_id=run_id or str(uuid.uuid4()),
            budget=budget or ExecutionBudget(),
            cancelled=cancelled or (lambda: False),
            state_version=state_version,
            policy_snapshot=policy_snapshot or {},
            trace_id=trace_id or "",
            parent_run_id=parent_run_id,
            ledger=ledger or BudgetLedger(),
            started_monotonic=time.monotonic(),
            elapsed_before_start_seconds=elapsed_before_start_seconds,
        )

    @property
    def deadline_monotonic(self) -> float:
        remaining = self.budget.max_duration_seconds - self.elapsed_before_start_seconds
        return self.started_monotonic + max(0.0, remaining)

    @property
    def elapsed_seconds(self) -> float:
        return self.elapsed_before_start_seconds + max(0.0, time.monotonic() - self.started_monotonic)

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.budget.max_duration_seconds - self.elapsed_seconds)

    def checkpoint(self) -> None:
        self.ledger.checkpoints += 1
        if self.cancelled():
            raise ExecutionCancelled("execution cancelled at cooperative checkpoint")
        if self.elapsed_seconds >= self.budget.max_duration_seconds:
            raise ExecutionBudgetExceeded("execution deadline exceeded at cooperative checkpoint")

    def check_plan(self, task_count: int, payload: Mapping[str, Any]) -> None:
        if isinstance(task_count, bool) or not isinstance(task_count, int) or task_count < 0:
            raise RuntimePolicyError("task_count must be a non-negative integer")
        if task_count > self.budget.max_tasks:
            raise ExecutionBudgetExceeded(f"planned task count {task_count} exceeds max_tasks={self.budget.max_tasks}")
        size = _serialized_size(payload)
        if size > self.budget.max_input_bytes:
            raise ExecutionBudgetExceeded(f"serialized preflight input size {size} exceeds max_input_bytes={self.budget.max_input_bytes}")
        self.checkpoint()

    def begin_task(self, payload: Mapping[str, Any]) -> None:
        self.checkpoint()
        size = _serialized_size(payload)
        if size > self.budget.max_input_bytes:
            raise ExecutionBudgetExceeded(f"serialized task input size {size} exceeds max_input_bytes={self.budget.max_input_bytes}")
        if self.ledger.tasks_started + 1 > self.budget.max_tasks:
            raise ExecutionBudgetExceeded(f"started task count would exceed max_tasks={self.budget.max_tasks}")
        if self.ledger.input_bytes + size > self.budget.max_input_bytes:
            raise ExecutionBudgetExceeded(
                f"cumulative task input bytes {self.ledger.input_bytes + size} exceed max_input_bytes={self.budget.max_input_bytes}"
            )
        self.ledger.tasks_started += 1
        self.ledger.input_bytes += size

    def check_output(self, payload: Any) -> None:
        self.checkpoint()
        size = _serialized_size(payload)
        if size > self.budget.max_output_bytes:
            raise ExecutionBudgetExceeded(f"serialized output size {size} exceeds max_output_bytes={self.budget.max_output_bytes}")
        self.ledger.output_bytes = size

    def budget_snapshot(self) -> dict[str, Any]:
        return {
            "max_tasks": self.budget.max_tasks,
            "max_input_bytes": self.budget.max_input_bytes,
            "max_output_bytes": self.budget.max_output_bytes,
            "max_duration_seconds": self.budget.max_duration_seconds,
        }

    def checkpoint_metadata(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "state_version": self.state_version,
            "trace_id": self.trace_id,
            "parent_run_id": self.parent_run_id,
            "policy_snapshot": _safe_snapshot(self.policy_snapshot, label="policy_snapshot"),
            "budget": self.budget_snapshot(),
            "ledger": self.ledger.as_dict(),
            "elapsed_seconds": self.elapsed_seconds,
            "remaining_seconds": self.remaining_seconds,
        }


@dataclass
class RuntimeGuard:
    budget: ExecutionBudget = field(default_factory=ExecutionBudget)
    cancelled: Callable[[], bool] = field(default=lambda: False, repr=False, compare=False)
    started_at: float = field(default_factory=time.monotonic)
    context: RunContext | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.context is not None:
            self.budget = self.context.budget
            self.cancelled = self.context.cancelled
            self.started_at = self.context.started_monotonic

    @property
    def deadline(self) -> float:
        if self.context is not None:
            return self.context.deadline_monotonic
        return self.started_at + self.budget.max_duration_seconds

    def preflight(self, task_count: int, payload: Mapping[str, Any]) -> None:
        if self.context is not None:
            self.context.check_plan(task_count, payload)
            return
        if task_count > self.budget.max_tasks:
            raise ExecutionBudgetExceeded(f"task count {task_count} exceeds max_tasks={self.budget.max_tasks}")
        size = _serialized_size(payload)
        if size > self.budget.max_input_bytes:
            raise ExecutionBudgetExceeded(f"serialized input size {size} exceeds max_input_bytes={self.budget.max_input_bytes}")
        self.checkpoint()

    def begin_task(self, payload: Mapping[str, Any]) -> None:
        if self.context is not None:
            self.context.begin_task(payload)
            return
        self.checkpoint()
        size = _serialized_size(payload)
        if size > self.budget.max_input_bytes:
            raise ExecutionBudgetExceeded(f"serialized input size {size} exceeds max_input_bytes={self.budget.max_input_bytes}")

    def checkpoint(self) -> None:
        if self.context is not None:
            self.context.checkpoint()
            return
        if self.cancelled():
            raise ExecutionCancelled("execution cancelled at cooperative checkpoint")
        if time.monotonic() > self.deadline:
            raise ExecutionBudgetExceeded("execution deadline exceeded at cooperative checkpoint")

    def check_output(self, payload: Any) -> None:
        if self.context is not None:
            self.context.check_output(payload)
            return
        self.checkpoint()
        size = _serialized_size(payload)
        if size > self.budget.max_output_bytes:
            raise ExecutionBudgetExceeded(f"serialized output size {size} exceeds max_output_bytes={self.budget.max_output_bytes}")
