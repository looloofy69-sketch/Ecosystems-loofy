"""Deterministic workflow orchestration for registered Delta-Infrastructure capabilities.

This module is a bounded execution kernel, not an autonomous agent. Workflow files can invoke
only registered capabilities or explicitly allow-listed built-in handlers. Input references use
the safe JSON form {"$ref": "task_id.output_key"}; no expressions, imports, shell commands, or
dynamic code execution are supported.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
import json
import math
import sqlite3
from contextlib import contextmanager
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .matching import normalize_graph
from .registry import CapabilityRegistry, default_registry
from .runtime import ExecutionBudget, ExecutionBudgetExceeded, ExecutionCancelled, RuntimeGuard


class WorkflowDefinitionError(ValueError):
    """Workflow schema or dependency graph is invalid."""


class WorkflowInputError(ValueError):
    """A task input/reference cannot be resolved safely."""


@dataclass(frozen=True)
class WorkflowTask:
    id: str
    kind: str
    inputs: Mapping[str, Any]
    depends_on: tuple[str, ...] = ()
    capability: str | None = None
    handler: str | None = None
    requires_approval: bool = False


@dataclass(frozen=True)
class WorkflowDefinition:
    workflow_id: str
    description: str
    tasks: tuple[WorkflowTask, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "WorkflowDefinition":
        if not isinstance(value, Mapping):
            raise WorkflowDefinitionError("Workflow document must be a JSON object")
        allowed_top = {"workflow_id", "description", "tasks"}
        extra_top = set(value) - allowed_top
        if extra_top:
            raise WorkflowDefinitionError(f"Unknown workflow keys: {sorted(extra_top)}")
        workflow_id = value.get("workflow_id")
        if not isinstance(workflow_id, str) or not workflow_id.strip():
            raise WorkflowDefinitionError("workflow_id must be a non-empty string")
        description = value.get("description", "")
        if not isinstance(description, str):
            raise WorkflowDefinitionError("description must be a string")
        raw_tasks = value.get("tasks")
        if not isinstance(raw_tasks, list) or not raw_tasks:
            raise WorkflowDefinitionError("tasks must be a non-empty array")
        tasks: list[WorkflowTask] = []
        allowed_task = {"id", "type", "inputs", "depends_on", "capability", "handler", "requires_approval"}
        for index, raw in enumerate(raw_tasks):
            if not isinstance(raw, Mapping):
                raise WorkflowDefinitionError(f"tasks[{index}] must be an object")
            extra = set(raw) - allowed_task
            if extra:
                raise WorkflowDefinitionError(f"Unknown keys in tasks[{index}]: {sorted(extra)}")
            task_id = raw.get("id")
            if not isinstance(task_id, str) or not task_id.strip() or "." in task_id:
                raise WorkflowDefinitionError(f"tasks[{index}].id must be a non-empty string without dots")
            kind = raw.get("type")
            if kind not in {"capability", "builtin"}:
                raise WorkflowDefinitionError(f"Task {task_id!r}: type must be 'capability' or 'builtin'")
            inputs = raw.get("inputs", {})
            if not isinstance(inputs, Mapping):
                raise WorkflowDefinitionError(f"Task {task_id!r}: inputs must be an object")
            deps = raw.get("depends_on", [])
            if not isinstance(deps, list) or any(not isinstance(x, str) for x in deps):
                raise WorkflowDefinitionError(f"Task {task_id!r}: depends_on must be an array of task ids")
            if len(set(deps)) != len(deps):
                raise WorkflowDefinitionError(f"Task {task_id!r}: duplicate dependency")
            approval = raw.get("requires_approval", False)
            if not isinstance(approval, bool):
                raise WorkflowDefinitionError(f"Task {task_id!r}: requires_approval must be boolean")
            capability = raw.get("capability")
            handler = raw.get("handler")
            if kind == "capability":
                if not isinstance(capability, str) or not capability:
                    raise WorkflowDefinitionError(f"Task {task_id!r}: capability name is required")
                if handler is not None:
                    raise WorkflowDefinitionError(f"Task {task_id!r}: builtin handler is invalid for capability task")
            else:
                if not isinstance(handler, str) or not handler:
                    raise WorkflowDefinitionError(f"Task {task_id!r}: builtin handler is required")
                if capability is not None:
                    raise WorkflowDefinitionError(f"Task {task_id!r}: capability is invalid for builtin task")
            tasks.append(WorkflowTask(
                id=task_id, kind=kind, inputs=dict(inputs), depends_on=tuple(deps),
                capability=capability, handler=handler, requires_approval=approval,
            ))
        ids = [t.id for t in tasks]
        if len(ids) != len(set(ids)):
            raise WorkflowDefinitionError("Task ids must be unique")
        known = set(ids)
        for task in tasks:
            missing = set(task.depends_on) - known
            if missing:
                raise WorkflowDefinitionError(f"Task {task.id!r}: unknown dependencies {sorted(missing)}")
            if task.id in task.depends_on:
                raise WorkflowDefinitionError(f"Task {task.id!r} cannot depend on itself")
        definition = cls(workflow_id, description, tuple(tasks))
        definition.topological_order()
        dependency_map = {task.id: set(task.depends_on) for task in tasks}
        for task in tasks:
            for ref_task in _referenced_task_ids(task.inputs):
                if ref_task not in dependency_map:
                    raise WorkflowDefinitionError(f"Task {task.id!r} references unknown task {ref_task!r}")
                if ref_task not in dependency_map[task.id]:
                    raise WorkflowDefinitionError(
                        f"Task {task.id!r} references {ref_task!r} but does not declare it in depends_on"
                    )
        return definition

    def topological_order(self) -> list[WorkflowTask]:
        by_id = {task.id: task for task in self.tasks}
        remaining = {task.id: set(task.depends_on) for task in self.tasks}
        result: list[WorkflowTask] = []
        while remaining:
            ready = [task.id for task in self.tasks if task.id in remaining and not remaining[task.id]]
            if not ready:
                raise WorkflowDefinitionError(f"Workflow dependency cycle detected among: {sorted(remaining)}")
            for task_id in ready:
                result.append(by_id[task_id])
                del remaining[task_id]
                for deps in remaining.values():
                    deps.discard(task_id)
        return result


def _referenced_task_ids(value: Any):
    if isinstance(value, Mapping):
        if set(value.keys()) == {"$ref"} and isinstance(value["$ref"], str):
            yield value["$ref"].split(".", 1)[0]
        else:
            for item in value.values():
                yield from _referenced_task_ids(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _referenced_task_ids(item)


def _resolve_references(value: Any, completed_outputs: Mapping[str, Mapping[str, Any]]) -> Any:
    if isinstance(value, Mapping):
        if set(value.keys()) == {"$ref"}:
            reference = value["$ref"]
            if not isinstance(reference, str) or not reference:
                raise WorkflowInputError(f"Invalid reference: {reference!r}")
            task_id, separator, path = reference.partition(".")
            if task_id not in completed_outputs:
                raise WorkflowInputError(f"Referenced task {task_id!r} has no successful output")
            current: Any = completed_outputs[task_id]
            if separator:
                for component in path.split("."):
                    if isinstance(current, Mapping) and component in current:
                        current = current[component]
                    elif isinstance(current, (list, tuple)) and component.isdigit() and int(component) < len(current):
                        current = current[int(component)]
                    else:
                        raise WorkflowInputError(f"Reference path {reference!r} does not exist")
            return json.loads(json.dumps(current, allow_nan=False))
        return {key: _resolve_references(item, completed_outputs) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_references(item, completed_outputs) for item in value]
    return value


def _json_safe(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise TypeError(f"Task output must be JSON serializable and finite: {exc}") from exc


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _normalise_graph_and_weights(payload: Mapping[str, Any]):
    vertices, vertex_set, edges = normalize_graph(payload["vertices"], payload["edges"])
    raw_weights = payload["weights"]
    if not isinstance(raw_weights, Mapping):
        raise ValueError("weights must be an object")
    if set(raw_weights) == set(vertices):
        weights = dict(raw_weights)
    else:
        lookup = {str(v): v for v in vertices}
        if len(lookup) != len(vertices) or set(raw_weights) != set(lookup):
            raise ValueError("weights must contain exactly one weight per vertex")
        weights = {lookup[str_key]: val for str_key, val in raw_weights.items()}
    for vertex, weight in weights.items():
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight):
            raise ValueError(f"Weight for {vertex!r} must be a finite number")
    return vertices, vertex_set, edges, weights


def verify_matching_optimum(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Independently verify a matching-delta-matroid optimum by bounded subset enumeration."""
    required = {"vertices", "edges", "weights", "solution", "reported_objective_value"}
    missing = required - set(payload)
    if missing:
        raise ValueError(f"Verifier is missing inputs: {sorted(missing)}")
    vertices, vertex_set, edges, weights = _normalise_graph_and_weights(payload)
    max_vertices = payload.get("max_vertices", 12)
    if isinstance(max_vertices, bool) or not isinstance(max_vertices, int) or max_vertices < 0:
        raise ValueError("max_vertices must be a non-negative integer")
    if len(vertices) > max_vertices:
        raise ValueError(f"Independent brute-force verification is limited to {max_vertices} vertices; got {len(vertices)}")
    solution_raw = payload["solution"]
    if not isinstance(solution_raw, (list, tuple)):
        raise ValueError("solution must be an array of vertex labels")
    if len(solution_raw) != len(set(solution_raw)):
        raise ValueError("solution contains duplicate vertices")
    solution = frozenset(solution_raw)
    if not solution <= vertex_set:
        raise ValueError("solution contains vertices outside the graph")
    reported = payload["reported_objective_value"]
    if isinstance(reported, bool) or not isinstance(reported, (int, float)) or not math.isfinite(reported):
        raise ValueError("reported_objective_value must be finite numeric value")

    vertex_index = {v: i for i, v in enumerate(vertices)}
    adjacency = [0] * len(vertices)
    for u, v in edges:
        i, j = vertex_index[u], vertex_index[v]
        adjacency[i] |= 1 << j
        adjacency[j] |= 1 << i

    @lru_cache(maxsize=None)
    def perfect_matching(mask: int) -> tuple[tuple[int, int], ...] | None:
        if mask == 0:
            return ()
        if mask.bit_count() % 2:
            return None
        first_bit = mask & -mask
        i = first_bit.bit_length() - 1
        candidate_partners = adjacency[i] & mask & ~first_bit
        while candidate_partners:
            partner_bit = candidate_partners & -candidate_partners
            j = partner_bit.bit_length() - 1
            sub = perfect_matching(mask & ~first_bit & ~partner_bit)
            if sub is not None:
                return ((i, j),) + sub
            candidate_partners &= ~partner_bit
        return None

    selected_mask = 0
    for vertex in solution:
        selected_mask |= 1 << vertex_index[vertex]
    selected_pairing = perfect_matching(selected_mask)
    solution_feasible = selected_pairing is not None
    solution_objective = sum(weights[v] for v in solution)
    best_objective: float | int | None = None
    best_mask = 0
    feasible_count = 0
    subsets_examined = 0
    best_pairing: tuple[tuple[int, int], ...] | None = None
    for mask in range(1 << len(vertices)):
        subsets_examined += 1
        pairing = perfect_matching(mask)
        if pairing is None:
            continue
        feasible_count += 1
        score = sum(weights[vertices[i]] for i in range(len(vertices)) if mask & (1 << i))
        if best_objective is None or score > best_objective:
            best_objective, best_mask, best_pairing = score, mask, pairing
    assert best_objective is not None and best_pairing is not None
    best_solution = [vertices[i] for i in range(len(vertices)) if best_mask & (1 << i)]
    matching_witness = [[vertices[i], vertices[j]] for i, j in selected_pairing] if selected_pairing is not None else []
    best_matching_witness = [[vertices[i], vertices[j]] for i, j in best_pairing]
    reported_matches = math.isclose(float(solution_objective), float(reported), rel_tol=1e-9, abs_tol=1e-9)
    optimum_matches = math.isclose(float(solution_objective), float(best_objective), rel_tol=1e-9, abs_tol=1e-9)
    verified = solution_feasible and reported_matches and optimum_matches
    return {
        "verified_optimal": verified, "solution_feasible": solution_feasible,
        "reported_objective_matches_recomputed": reported_matches,
        "solution_objective_value": solution_objective, "reported_objective_value": reported,
        "best_objective_value": best_objective, "optimality_matches": optimum_matches,
        "best_solution": best_solution, "solution_matching_witness": matching_witness,
        "best_matching_witness": best_matching_witness, "feasible_sets_examined": feasible_count,
        "subsets_examined": subsets_examined, "vertices": len(vertices),
        "verification_method": "independent_bitmask_perfect_matching_plus_exhaustive_subset_search",
        "verification_limit_vertices": max_vertices,
    }


def decide_internal_shadow_gate(payload: Mapping[str, Any]) -> dict[str, Any]:
    verification = payload.get("verification")
    optimization = payload.get("optimization")
    if not isinstance(verification, Mapping) or not isinstance(optimization, Mapping):
        raise ValueError("verification and optimization outputs must be objects")
    passed = bool(verification.get("verified_optimal")) and bool(optimization.get("member_verified"))
    return {
        "decision": "ELIGIBLE_FOR_INTERNAL_SHADOW_MODE" if passed else "REJECTED",
        "passed": passed,
        "production_deployment_authorized": False,
        "reason": (
            "Independent verifier confirms feasibility and optimality on this bounded test instance."
            if passed else "Independent verification did not confirm feasibility and optimality."
        ),
        "next_boundary": "Human review and separate integration approval are required before any operational actuation.",
    }


@dataclass
class WorkflowRunStore:
    """SQLite-backed durable run ledger, implemented with the Python standard library."""
    path: str | Path

    def __post_init__(self) -> None:
        self.path = str(self.path)
        if self.path != ":memory:":
            Path(self.path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS workflow_runs (
                    run_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    record_json TEXT NOT NULL
                )
            """)
            connection.execute("CREATE INDEX IF NOT EXISTS workflow_runs_started_at_idx ON workflow_runs(started_at DESC)")

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def save(self, record: Mapping[str, Any]) -> None:
        serialized = json.dumps(record, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO workflow_runs(run_id, workflow_id, started_at, finished_at, status, record_json) VALUES (?, ?, ?, ?, ?, ?)",
                (record["run_id"], record["workflow_id"], record["started_at"], record["finished_at"], record["status"], serialized),
            )

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT record_json FROM workflow_runs WHERE run_id = ?", (run_id,)).fetchone()
        return json.loads(row["record_json"]) if row else None

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1 or limit > 1000:
            raise ValueError("limit must be an integer from 1 to 1000")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT run_id, workflow_id, started_at, finished_at, status FROM workflow_runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]


class TaskExecutionController:
    """Run declarative DAG workflows through the capability registry and allow-listed built-ins."""

    def __init__(
        self,
        registry: CapabilityRegistry | None = None,
        run_store: WorkflowRunStore | None = None,
        builtin_handlers: Mapping[str, Callable[[Mapping[str, Any]], Mapping[str, Any]]] | None = None,
    ) -> None:
        self.registry = registry or default_registry()
        self.run_store = run_store
        self.builtin_handlers: dict[str, Callable[[Mapping[str, Any]], Mapping[str, Any]]] = {
            "verify_matching_optimum": verify_matching_optimum,
            "decide_internal_shadow_gate": decide_internal_shadow_gate,
        }
        if builtin_handlers:
            overlap = set(self.builtin_handlers) & set(builtin_handlers)
            if overlap:
                raise ValueError(f"Cannot override protected built-in handlers: {sorted(overlap)}")
            self.builtin_handlers.update(builtin_handlers)

    def run(
        self,
        workflow: WorkflowDefinition | Mapping[str, Any],
        *,
        approved_task_ids: Sequence[str] = (),
        budget: ExecutionBudget | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        definition = workflow if isinstance(workflow, WorkflowDefinition) else WorkflowDefinition.from_mapping(workflow)
        approved = set(approved_task_ids)
        known_ids = {task.id for task in definition.tasks}
        unknown_approvals = approved - known_ids
        if unknown_approvals:
            raise WorkflowInputError(f"Approval provided for unknown task ids: {sorted(unknown_approvals)}")
        available = {item["name"] for item in self.registry.describe()}
        for task in definition.tasks:
            if task.kind == "capability" and task.capability not in available:
                raise WorkflowDefinitionError(f"Task {task.id!r} references unknown capability {task.capability!r}")
            if task.kind == "builtin" and task.handler not in self.builtin_handlers:
                raise WorkflowDefinitionError(f"Task {task.id!r} references unknown builtin handler {task.handler!r}")

        guard = RuntimeGuard(budget=budget or ExecutionBudget(), cancelled=cancelled or (lambda: False))
        serialized_workflow = {
            "workflow_id": definition.workflow_id, "description": definition.description,
            "tasks": [
                {"id": task.id, "type": task.kind, "inputs": task.inputs,
                 "depends_on": list(task.depends_on), "capability": task.capability,
                 "handler": task.handler, "requires_approval": task.requires_approval}
                for task in definition.tasks
            ],
        }
        guard.preflight(len(definition.tasks), serialized_workflow)

        run_id = str(uuid.uuid4())
        started_at = _utc_now()
        start_clock = time.perf_counter()
        task_records: list[dict[str, Any]] = []
        output_by_id: dict[str, Mapping[str, Any]] = {}
        status_by_id: dict[str, str] = {}
        runtime_stop_status: str | None = None
        for task in definition.topological_order():
            task_started = _utc_now()
            task_clock = time.perf_counter()
            failed_dependencies = [dep for dep in task.depends_on if status_by_id.get(dep) != "succeeded"]
            if failed_dependencies:
                record = {
                    "task_id": task.id, "type": task.kind, "status": "skipped",
                    "reason": "dependency_not_succeeded", "blocked_by": failed_dependencies,
                    "started_at": task_started, "finished_at": _utc_now(), "duration_ms": 0.0,
                }
                task_records.append(record)
                status_by_id[task.id] = "skipped"
                continue
            if task.requires_approval and task.id not in approved:
                record = {
                    "task_id": task.id, "type": task.kind, "status": "approval_required",
                    "reason": "task_requires_explicit_approval", "started_at": task_started,
                    "finished_at": _utc_now(), "duration_ms": 0.0,
                }
                task_records.append(record)
                status_by_id[task.id] = "approval_required"
                continue
            if runtime_stop_status is not None:
                record = {
                    "task_id": task.id, "type": task.kind, "status": "skipped",
                    "reason": f"runtime_stopped:{runtime_stop_status}",
                    "started_at": task_started, "finished_at": _utc_now(), "duration_ms": 0.0,
                }
                task_records.append(record)
                status_by_id[task.id] = "skipped"
                continue
            try:
                guard.checkpoint()
                resolved_inputs = _resolve_references(task.inputs, output_by_id)
                guard.preflight(len(definition.tasks), {"task_id": task.id, "inputs": resolved_inputs})
                if task.kind == "capability":
                    result = self.registry.run(task.capability, resolved_inputs)  # type: ignore[arg-type]
                else:
                    result = dict(self.builtin_handlers[task.handler](resolved_inputs))  # type: ignore[index]
                safe_result = _json_safe(dict(result))
                guard.checkpoint()
                prospective_outputs = dict(output_by_id)
                prospective_outputs[task.id] = safe_result
                guard.check_output(prospective_outputs)
                elapsed_ms = round((time.perf_counter() - task_clock) * 1000, 3)
                record = {
                    "task_id": task.id, "type": task.kind, "capability": task.capability,
                    "handler": task.handler, "status": "succeeded",
                    "inputs": _json_safe(resolved_inputs), "output": safe_result,
                    "started_at": task_started, "finished_at": _utc_now(), "duration_ms": elapsed_ms,
                }
                output_by_id[task.id] = safe_result
                status_by_id[task.id] = "succeeded"
            except ExecutionCancelled as exc:
                elapsed_ms = round((time.perf_counter() - task_clock) * 1000, 3)
                record = {
                    "task_id": task.id, "type": task.kind, "capability": task.capability,
                    "handler": task.handler, "status": "cancelled",
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                    "started_at": task_started, "finished_at": _utc_now(), "duration_ms": elapsed_ms,
                }
                status_by_id[task.id] = "cancelled"
                runtime_stop_status = "cancelled"
            except ExecutionBudgetExceeded as exc:
                elapsed_ms = round((time.perf_counter() - task_clock) * 1000, 3)
                record = {
                    "task_id": task.id, "type": task.kind, "capability": task.capability,
                    "handler": task.handler, "status": "budget_exceeded",
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                    "started_at": task_started, "finished_at": _utc_now(), "duration_ms": elapsed_ms,
                }
                status_by_id[task.id] = "budget_exceeded"
                runtime_stop_status = "budget_exceeded"
            except Exception as exc:
                elapsed_ms = round((time.perf_counter() - task_clock) * 1000, 3)
                record = {
                    "task_id": task.id, "type": task.kind, "capability": task.capability,
                    "handler": task.handler, "status": "failed",
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                    "started_at": task_started, "finished_at": _utc_now(), "duration_ms": elapsed_ms,
                }
                status_by_id[task.id] = "failed"
            task_records.append(record)

        statuses = set(status_by_id.values())
        if runtime_stop_status is not None:
            overall_status = runtime_stop_status
        elif "failed" in statuses:
            overall_status = "failed"
        elif "approval_required" in statuses:
            overall_status = "approval_required"
        elif "skipped" in statuses:
            overall_status = "blocked"
        else:
            overall_status = "succeeded"
        record = {
            "schema_version": "1.0", "run_id": run_id,
            "workflow_id": definition.workflow_id, "description": definition.description,
            "status": overall_status, "started_at": started_at, "finished_at": _utc_now(),
            "duration_ms": round((time.perf_counter() - start_clock) * 1000, 3),
            "approved_task_ids": sorted(approved), "tasks": task_records, "outputs": dict(output_by_id),
        }
        if self.run_store:
            self.run_store.save(record)
        return record
