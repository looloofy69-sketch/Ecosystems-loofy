"""State-aware, contract-checked scheduling for internal algorithm portfolios.

The portfolio layer does not pretend that algorithms are interchangeable. Each
strategy declares when it is eligible, which state fields it must preserve, and
whether its output must remain feasible. Strategy code is registered in Python;
portfolio data never imports modules or evaluates executable expressions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
import time
import uuid
from typing import Any, Callable, Mapping, Sequence

from .runtime import BudgetLedger, ExecutionBudget, ExecutionBudgetExceeded, ExecutionCancelled, RunContext, RuntimeGuard

PORTFOLIO_MODES = ("rotation", "alternation", "turn-taking", "shape-driven", "auto")
TURN_STATUSES = ("progress", "no_change", "complete", "failed")


class PortfolioDefinitionError(ValueError):
    """A strategy or portfolio definition violates its declared contract."""


class TransitionContractError(RuntimeError):
    """A strategy returned a state that violates its transition contract."""


class CandidateMergeError(ValueError):
    """Candidate outputs cannot be safely merged under the requested objective."""


def merge_candidate_outputs(
    candidates: Sequence[Mapping[str, Any]],
    *,
    objective_key: str = "objective_value",
    feasible_key: str = "feasible",
    maximize: bool = True,
) -> dict[str, Any]:
    """Select the best valid candidate deterministically, preserving tie diagnostics."""
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        raise CandidateMergeError("candidates must be a sequence of candidate mappings")
    eligible: list[tuple[int, Mapping[str, Any], int | float]] = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            raise CandidateMergeError(f"candidate {index} must be a mapping")
        if candidate.get(feasible_key) is not True:
            continue
        score = candidate.get(objective_key)
        if not _finite_number(score):
            continue
        eligible.append((index, candidate, score))
    if not eligible:
        raise CandidateMergeError("no feasible candidate with a finite objective can be merged")
    best_score = (max if maximize else min)(score for _, _, score in eligible)
    winners = [(index, candidate, score) for index, candidate, score in eligible if score == best_score]
    winner_index, winner, _ = winners[0]
    return {
        "winner_index": winner_index,
        "winner_name": winner.get("name", f"candidate_{winner_index}"),
        "objective_value": best_score,
        "winner": _json_copy(dict(winner), label="merged candidate"),
        "feasible_candidate_count": len(eligible),
        "candidate_count": len(candidates),
        "tie_count": len(winners),
        "tied_winners": [candidate.get("name", f"candidate_{index}") for index, candidate, _ in winners],
        "direction": "maximize" if maximize else "minimize",
    }


def _json_copy(value: Any, *, label: str) -> Any:
    try:
        return json.loads(json.dumps(value, allow_nan=False, ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise PortfolioDefinitionError(f"{label} must be finite JSON-compatible data: {exc}") from exc


def _read_path(value: Mapping[str, Any], path: str) -> tuple[bool, Any]:
    current: Any = value
    for part in path.split("."):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        else:
            return False, None
    return True, current


def _finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return True if isinstance(value, int) else math.isfinite(value)


@dataclass(frozen=True)
class StateShape:
    """A normalized, observable summary of the current computational state."""
    kind: str
    phase: str
    feasible: bool | None
    parity: str
    selected_parity: str
    size: int | None
    ground_size: int | None
    distance: int | None
    objective: int | float | None
    stagnation: int
    density: float | None
    matrix_size: int | None
    features: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_state(cls, state: Mapping[str, Any]) -> "StateShape":
        if not isinstance(state, Mapping):
            raise PortfolioDefinitionError("state must be a mapping")
        selected, target = state.get("selected"), state.get("target")
        vertices, ground, matrix = state.get("vertices"), state.get("ground_set"), state.get("matrix")

        def sequence_size(value: Any) -> int | None:
            return len(value) if isinstance(value, (list, tuple, set, frozenset)) else None

        selected_size = sequence_size(selected)
        raw_size = state.get("size", selected_size)
        if raw_size is None:
            raw_size = sequence_size(vertices)
        size = raw_size if isinstance(raw_size, int) and not isinstance(raw_size, bool) and raw_size >= 0 else None
        raw_ground_size = state.get("ground_size", sequence_size(ground))
        if raw_ground_size is None:
            raw_ground_size = sequence_size(vertices)
        ground_size = raw_ground_size if isinstance(raw_ground_size, int) and not isinstance(raw_ground_size, bool) and raw_ground_size >= 0 else None

        parity = state.get("parity", "unknown")
        if not isinstance(parity, str) or parity not in {"even", "odd", "mixed", "unknown"}:
            raise PortfolioDefinitionError("state.parity must be even, odd, mixed, or unknown")
        selected_parity = state.get("selected_parity")
        if selected_parity is None:
            selected_parity = ("even" if selected_size % 2 == 0 else "odd") if selected_size is not None else "unknown"
        if not isinstance(selected_parity, str) or selected_parity not in {"even", "odd", "unknown"}:
            raise PortfolioDefinitionError("state.selected_parity must be even, odd, or unknown")
        feasible = state.get("feasible")
        if feasible is not None and not isinstance(feasible, bool):
            raise PortfolioDefinitionError("state.feasible must be a boolean when supplied")
        distance = state.get("distance")
        if distance is None and isinstance(selected, (list, tuple, set, frozenset)) and isinstance(target, (list, tuple, set, frozenset)):
            try:
                distance = len(set(selected).symmetric_difference(set(target)))
            except TypeError:
                distance = None
        if distance is not None and (isinstance(distance, bool) or not isinstance(distance, int) or distance < 0):
            raise PortfolioDefinitionError("state.distance must be a non-negative integer")
        objective = state.get("objective_value", state.get("objective"))
        if objective is not None and not _finite_number(objective):
            raise PortfolioDefinitionError("state objective must be a finite number")
        stagnation = state.get("stagnation", 0)
        if isinstance(stagnation, bool) or not isinstance(stagnation, int) or stagnation < 0:
            raise PortfolioDefinitionError("state.stagnation must be a non-negative integer")
        density = state.get("density")
        if density is None and isinstance(vertices, (list, tuple, set)) and isinstance(state.get("edges"), (list, tuple, set)):
            n, m = len(vertices), len(state["edges"])
            density = (2 * m / (n * (n - 1))) if n > 1 else 0.0
        if density is not None and (not _finite_number(density) or not 0 <= density <= 1):
            raise PortfolioDefinitionError("state.density must be a finite number between 0 and 1")
        matrix_size = state.get("matrix_size")
        if matrix_size is None and isinstance(matrix, (list, tuple)):
            matrix_size = len(matrix)
        if matrix_size is not None and (isinstance(matrix_size, bool) or not isinstance(matrix_size, int) or matrix_size < 0):
            raise PortfolioDefinitionError("state.matrix_size must be a non-negative integer")
        kind, phase = state.get("kind", state.get("state_kind", "generic")), state.get("phase", "")
        if not isinstance(kind, str) or not kind:
            raise PortfolioDefinitionError("state kind must be a non-empty string")
        if not isinstance(phase, str):
            raise PortfolioDefinitionError("state phase must be a string")
        features = state.get("features", {})
        if not isinstance(features, Mapping):
            raise PortfolioDefinitionError("state.features must be an object")
        _json_copy(dict(features), label="state.features")
        return cls(kind, phase, feasible, parity, selected_parity, size, ground_size,
                   distance, objective, stagnation, density, matrix_size, dict(features))

    def as_mapping(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "phase": self.phase, "feasible": self.feasible,
            "parity": self.parity, "selected_parity": self.selected_parity,
            "size": self.size, "ground_size": self.ground_size, "distance": self.distance,
            "objective": self.objective, "stagnation": self.stagnation,
            "density": self.density, "matrix_size": self.matrix_size, "features": dict(self.features),
        }


@dataclass(frozen=True)
class StatePredicate:
    """A safe, declarative predicate over normalized state-shape fields."""
    field: str
    op: str
    value: Any = None

    def __post_init__(self) -> None:
        valid = {"exists", "eq", "ne", "in", "not_in", "lt", "lte", "gt", "gte", "contains", "truthy"}
        if not isinstance(self.field, str) or not self.field or not isinstance(self.op, str) or self.op not in valid:
            raise PortfolioDefinitionError(f"Invalid state predicate: {self.field!r} {self.op!r}")
        if self.op in {"exists", "truthy"} and self.value is not None and not isinstance(self.value, bool):
            raise PortfolioDefinitionError(f"Predicate {self.op!r} value must be boolean or null")
        _json_copy(self.value, label=f"predicate value for {self.field}")

    def matches(self, shape: StateShape) -> bool:
        view = shape.as_mapping()
        present, actual = _read_path(view, self.field)
        if self.op == "exists":
            return present if self.value is None else present is bool(self.value)
        if not present:
            return False
        try:
            if self.op == "eq": return actual == self.value
            if self.op == "ne": return actual != self.value
            if self.op == "in": return actual in self.value
            if self.op == "not_in": return actual not in self.value
            if self.op == "lt": return actual < self.value
            if self.op == "lte": return actual <= self.value
            if self.op == "gt": return actual > self.value
            if self.op == "gte": return actual >= self.value
            if self.op == "contains": return self.value in actual
            if self.op == "truthy": return bool(actual) is (True if self.value is None else bool(self.value))
        except (TypeError, ValueError):
            return False
        return False

    def describe(self) -> dict[str, Any]:
        return {"field": self.field, "op": self.op, "value": self.value}


@dataclass(frozen=True)
class StrategyTurn:
    """A single strategy result. next_state is required for state-changing progress."""
    status: str
    next_state: Mapping[str, Any] | None = None
    metrics: Mapping[str, Any] = field(default_factory=dict)
    message: str = ""

    def __post_init__(self) -> None:
        if self.status not in TURN_STATUSES:
            raise PortfolioDefinitionError(f"Turn status must be one of {TURN_STATUSES}")
        if not isinstance(self.metrics, Mapping):
            raise PortfolioDefinitionError("turn metrics must be a mapping")
        _json_copy(dict(self.metrics), label="turn metrics")
        if self.next_state is not None:
            if not isinstance(self.next_state, Mapping):
                raise PortfolioDefinitionError("next_state must be a mapping")
            _json_copy(dict(self.next_state), label="next_state")
        if not isinstance(self.message, str):
            raise PortfolioDefinitionError("turn message must be a string")


StepFunction = Callable[[Mapping[str, Any]], StrategyTurn]


@dataclass(frozen=True)
class AlgorithmStrategy:
    """A callable algorithm with shape eligibility and transition guarantees."""
    name: str
    family: str
    step: StepFunction
    when: tuple[StatePredicate, ...] = ()
    priority: int = 0
    turn_quota: int = 1
    preserve_keys: tuple[str, ...] = ()
    require_after_feasible: bool = False
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name or not isinstance(self.family, str) or not self.family:
            raise PortfolioDefinitionError("strategy name and family must be non-empty strings")
        if not callable(self.step):
            raise PortfolioDefinitionError(f"strategy {self.name!r} requires a callable step")
        if not isinstance(self.when, tuple) or any(not isinstance(item, StatePredicate) for item in self.when):
            raise PortfolioDefinitionError("strategy when must be a tuple of StatePredicate values")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise PortfolioDefinitionError("strategy priority must be an integer")
        if isinstance(self.turn_quota, bool) or not isinstance(self.turn_quota, int) or self.turn_quota < 1:
            raise PortfolioDefinitionError("strategy turn_quota must be a positive integer")
        if not isinstance(self.preserve_keys, tuple) or any(not isinstance(key, str) or not key for key in self.preserve_keys):
            raise PortfolioDefinitionError("preserve_keys must be a tuple of non-empty string keys")
        if len(set(self.preserve_keys)) != len(self.preserve_keys):
            raise PortfolioDefinitionError("preserve_keys must be unique")
        if "stagnation" in self.preserve_keys:
            raise PortfolioDefinitionError("stagnation is scheduler-managed and cannot be a preserved key")

    def eligibility_reasons(self, shape: StateShape) -> list[str]:
        return [f"shape predicate not satisfied: {p.field} {p.op} {p.value!r}"
                for p in self.when if not p.matches(shape)]

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name, "family": self.family, "priority": self.priority,
            "turn_quota": self.turn_quota, "preserve_keys": list(self.preserve_keys),
            "require_after_feasible": self.require_after_feasible,
            "when": [p.describe() for p in self.when], "description": self.description,
        }


class StrategyCatalog:
    """In-process catalog. It never loads strategy code from user-supplied JSON."""
    def __init__(self) -> None:
        self._strategies: list[AlgorithmStrategy] = []
        self._by_name: dict[str, AlgorithmStrategy] = {}
    def register(self, strategy: AlgorithmStrategy) -> None:
        if strategy.name in self._by_name:
            raise PortfolioDefinitionError(f"Strategy already registered: {strategy.name}")
        self._strategies.append(strategy)
        self._by_name[strategy.name] = strategy
    def get(self, name: str) -> AlgorithmStrategy:
        try:
            return self._by_name[name]
        except KeyError as exc:
            raise KeyError(f"Unknown strategy {name!r}; available: {sorted(self._by_name)}") from exc
    def all(self) -> tuple[AlgorithmStrategy, ...]:
        return tuple(self._strategies)
    def describe(self) -> list[dict[str, Any]]:
        return [strategy.describe() for strategy in self._strategies]


class PortfolioController:
    """State-aware scheduler for trusted, registered in-process strategies."""
    def __init__(self, catalog: StrategyCatalog, *, on_failure: str = "stop", run_store: Any = None) -> None:
        if on_failure not in {"stop", "skip_strategy"}:
            raise PortfolioDefinitionError("on_failure must be 'stop' or 'skip_strategy'")
        self.catalog = catalog
        self.on_failure = on_failure
        self.run_store = run_store

    @staticmethod
    def _auto_mode_for(state: Mapping[str, Any], shape: StateShape) -> str:
        rules = state.get("scheduler_rules", [])
        if not isinstance(rules, list):
            raise PortfolioDefinitionError("state.scheduler_rules must be an array")
        permitted = {"rotation", "alternation", "turn-taking", "shape-driven"}
        for index, rule in enumerate(rules):
            if not isinstance(rule, Mapping):
                raise PortfolioDefinitionError(f"scheduler_rules[{index}] must be an object")
            extra = set(rule) - {"name", "mode", "when"}
            if extra:
                raise PortfolioDefinitionError(f"scheduler_rules[{index}] has unknown keys: {sorted(extra)}")
            selected_mode, conditions = rule.get("mode"), rule.get("when")
            if not isinstance(selected_mode, str) or selected_mode not in permitted:
                raise PortfolioDefinitionError(f"scheduler_rules[{index}].mode must be one of {sorted(permitted)}")
            if not isinstance(conditions, list) or not conditions:
                raise PortfolioDefinitionError(f"scheduler_rules[{index}].when must be a non-empty array")
            predicates: list[StatePredicate] = []
            for predicate_index, raw in enumerate(conditions):
                if not isinstance(raw, Mapping) or set(raw) - {"field", "op", "value"}:
                    raise PortfolioDefinitionError(
                        f"scheduler_rules[{index}].when[{predicate_index}] must contain only field/op/value"
                    )
                if "field" not in raw or "op" not in raw:
                    raise PortfolioDefinitionError(
                        f"scheduler_rules[{index}].when[{predicate_index}] requires field and op"
                    )
                predicates.append(StatePredicate(str(raw["field"]), str(raw["op"]), raw.get("value")))
            if all(predicate.matches(shape) for predicate in predicates):
                return selected_mode
        fallback = state.get("scheduler_mode", "shape-driven")
        if not isinstance(fallback, str) or fallback not in permitted:
            raise PortfolioDefinitionError(f"state.scheduler_mode has unsupported mode {fallback!r}")
        return fallback

    def run(
        self,
        initial_state: Mapping[str, Any],
        *,
        mode: str = "auto",
        max_turns: int = 100,
        budget: ExecutionBudget | None = None,
        cancelled: Callable[[], bool] | None = None,
        run_context: RunContext | None = None,
        resume_from_run_id: str | None = None,
    ) -> dict[str, Any]:
        if mode not in PORTFOLIO_MODES:
            raise PortfolioDefinitionError(f"mode must be one of {PORTFOLIO_MODES}")
        if isinstance(max_turns, bool) or not isinstance(max_turns, int) or max_turns < 1:
            raise PortfolioDefinitionError("max_turns must be a positive integer")
        if not isinstance(initial_state, Mapping):
            raise PortfolioDefinitionError("initial_state must be a mapping")
        original_state = _json_copy(dict(initial_state), label="initial_state")
        state = _json_copy(original_state, label="initial_state")
        if run_context is not None and budget is not None and run_context.budget != budget:
            raise PortfolioDefinitionError("budget must match the supplied run_context budget")
        if resume_from_run_id is not None and run_context is not None:
            raise PortfolioDefinitionError("Do not pass run_context when resuming; the checkpoint restores it")
        if cancelled is not None and run_context is not None:
            raise PortfolioDefinitionError("Pass cancellation through run_context or cancelled, not both")

        resume_checkpoint = None
        resume_record = None
        if resume_from_run_id is not None:
            if self.run_store is None:
                raise PortfolioDefinitionError("resume requires a configured run_store")
            if not all(strategy.retry_safe for strategy in self.catalog.all()):
                unsafe = [s.name for s in self.catalog.all() if not s.retry_safe]
                raise PortfolioDefinitionError(f"portfolio resume requires every strategy to declare retry_safe=true; unsafe: {unsafe}")
            resume_checkpoint = self.run_store.get_latest_checkpoint(resume_from_run_id)
            if resume_checkpoint is None:
                raise PortfolioDefinitionError(f"no portfolio checkpoint exists for run {resume_from_run_id!r}")
            resume_record = self.run_store.get(resume_from_run_id)
            if resume_record is not None and resume_record.get("status") not in {"turn_limit_reached", "cancelled", "budget_exceeded"}:
                raise PortfolioDefinitionError(f"portfolio run {resume_from_run_id!r} with status {resume_record.get('status')!r} is not resumable")
            checkpoint_context = resume_checkpoint["checkpoint"].get("run_context")
            if not isinstance(checkpoint_context, Mapping):
                raise PortfolioDefinitionError("portfolio checkpoint is missing run_context metadata")
            saved_budget = ExecutionBudget(**checkpoint_context["budget"])
            if budget is not None and budget != saved_budget:
                raise PortfolioDefinitionError("resume budget must match the checkpoint budget")
            run_context = RunContext.create(
                budget=saved_budget, cancelled=cancelled, run_id=resume_from_run_id,
                state_version=checkpoint_context.get("state_version", 0),
                policy_snapshot=checkpoint_context.get("policy_snapshot", {}),
                trace_id=checkpoint_context.get("trace_id", ""),
                parent_run_id=checkpoint_context.get("parent_run_id"),
                ledger=BudgetLedger.from_mapping(checkpoint_context.get("ledger")),
                elapsed_before_start_seconds=checkpoint_context.get("elapsed_seconds", 0.0),
            )
        elif run_context is None:
            run_context = RunContext.create(
                budget=budget or ExecutionBudget(), cancelled=cancelled,
                policy_snapshot={"component": "portfolio", "mode": mode,
                                 "portfolio_id": str(original_state.get("portfolio_id", "algorithm-portfolio"))},
            )
        guard = RuntimeGuard(context=run_context)
        guard.preflight(max_turns, {"mode": mode, "initial_state": original_state})
        run_id = run_context.run_id
        started_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        start_clock = time.perf_counter()
        strategies = self.catalog.all()
        if not strategies:
            raise PortfolioDefinitionError("portfolio has no registered strategies")

        portfolio_id = str(original_state.get("portfolio_id", "algorithm-portfolio"))
        checkpoint_workflow_id = f"portfolio:{portfolio_id}"
        fingerprint_payload = {
            "portfolio_id": portfolio_id, "mode": mode, "initial_state": original_state,
            "on_failure": self.on_failure, "strategies": [strategy.describe() for strategy in strategies],
        }
        fingerprint = hashlib.sha256(json.dumps(
            fingerprint_payload, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        checkpoint_sequence = None
        start_turn_index = 0

        run_mode = mode
        turns: list[dict[str, Any]] = []
        run_counts = {s.name: 0 for s in strategies}
        disabled: set[str] = set()
        cursor = -1
        family_order = list(dict.fromkeys(s.family for s in strategies))
        family_cursor = -1
        family_strategy_cursor = {family: -1 for family in family_order}
        queue = [s.name for s in strategies for _ in range(s.turn_quota)]
        queue_cursor = -1
        last_mode: str | None = None
        last_strategy_name: str | None = None
        stop_reason = "max_turns_reached"
        status = "turn_limit_reached"

        if resume_checkpoint is not None:
            if resume_checkpoint["workflow_id"] != checkpoint_workflow_id or resume_checkpoint["workflow_fingerprint"] != fingerprint:
                raise PortfolioDefinitionError("portfolio definition or strategy catalog differs from the checkpoint")
            checkpoint = resume_checkpoint["checkpoint"]
            state = _json_copy(checkpoint["state"], label="checkpoint state")
            turns = _json_copy(checkpoint["turns"], label="checkpoint turns")
            run_counts = {name: int(count) for name, count in checkpoint["run_counts"].items()}
            disabled = set(checkpoint["disabled"])
            cursor = int(checkpoint["cursor"])
            family_cursor = int(checkpoint["family_cursor"])
            family_strategy_cursor = {name: int(value) for name, value in checkpoint["family_strategy_cursor"].items()}
            queue_cursor = int(checkpoint["queue_cursor"])
            last_mode = checkpoint.get("last_mode")
            last_strategy_name = checkpoint.get("last_strategy_name")
            run_mode = checkpoint.get("run_mode", mode)
            stop_reason = checkpoint.get("stop_reason", "max_turns_reached")
            status = checkpoint.get("status", "turn_limit_reached")
            start_turn_index = int(checkpoint["next_turn_index"])
            checkpoint_sequence = resume_checkpoint["sequence"]
            started_at = checkpoint.get("started_at", started_at)

        def persist_checkpoint(next_turn_index: int) -> None:
            nonlocal checkpoint_sequence
            if self.run_store is None or not all(strategy.retry_safe for strategy in strategies):
                return
            payload = {
                "kind": "portfolio-turn-checkpoint", "next_turn_index": next_turn_index,
                "state": state, "turns": turns, "run_counts": run_counts,
                "disabled": sorted(disabled), "cursor": cursor, "family_cursor": family_cursor,
                "family_strategy_cursor": family_strategy_cursor, "queue_cursor": queue_cursor,
                "last_mode": last_mode, "last_strategy_name": last_strategy_name,
                "run_mode": run_mode, "stop_reason": stop_reason, "status": status,
                "started_at": started_at, "run_context": run_context.checkpoint_metadata(),
            }
            checkpoint_sequence = self.run_store.save_checkpoint(
                run_id=run_id, workflow_id=checkpoint_workflow_id, workflow_fingerprint=fingerprint,
                status=status, checkpoint=payload, expected_previous_sequence=checkpoint_sequence,
            )

        for turn_index in range(start_turn_index, max_turns):
            persist_checkpoint(turn_index)
            try:
                guard.checkpoint()
            except ExecutionCancelled as exc:
                stop_reason, status = "execution_cancelled", "cancelled"
                turns.append({"turn": turn_index + 1, "decision": "stop", "status": status, "reason": str(exc)})
                break
            except ExecutionBudgetExceeded as exc:
                stop_reason, status = "execution_budget_exceeded", "budget_exceeded"
                turns.append({"turn": turn_index + 1, "decision": "stop", "status": status, "reason": str(exc)})
                break
            if state.get("done") is True:
                stop_reason, status = "state_marked_done", "completed"
                break
            shape = StateShape.from_state(state)
            run_mode = self._auto_mode_for(state, shape) if mode == "auto" else mode
            if last_strategy_name is not None and run_mode != last_mode:
                prior = self.catalog.get(last_strategy_name)
                prior_index = strategies.index(prior)
                if run_mode in {"rotation", "shape-driven"}:
                    cursor = prior_index
                elif run_mode == "alternation":
                    family_cursor = family_order.index(prior.family)
                    family_strategy_cursor[prior.family] = prior_index
                elif run_mode == "turn-taking":
                    prior_slots = [i for i, name in enumerate(queue) if name == prior.name]
                    if prior_slots:
                        queue_cursor = prior_slots[0]

            eligible = [s for s in strategies if s.name not in disabled and not s.eligibility_reasons(shape)]
            reasons = {s.name: ("disabled after failure" if s.name in disabled else s.eligibility_reasons(shape))
                       for s in strategies if s not in eligible}
            if not eligible:
                stop_reason, status = "no_eligible_strategy_for_state_shape", "blocked"
                turns.append({
                    "turn": turn_index + 1, "mode": run_mode, "state_shape": shape.as_mapping(),
                    "eligible": [], "ineligible": reasons, "decision": "stop", "reason": stop_reason,
                })
                break

            chosen: AlgorithmStrategy | None = None
            chosen_index = -1
            if run_mode == "rotation":
                for offset in range(1, len(strategies) + 1):
                    idx = (cursor + offset) % len(strategies)
                    if strategies[idx] in eligible:
                        chosen, chosen_index, cursor = strategies[idx], idx, idx
                        break
            elif run_mode == "alternation":
                eligible_families = {s.family for s in eligible}
                for offset in range(1, len(family_order) + 1):
                    family_idx = (family_cursor + offset) % len(family_order)
                    family = family_order[family_idx]
                    family_eligible = [s for s in strategies if s.family == family and s in eligible]
                    if family in eligible_families and family_eligible:
                        local_cursor = family_strategy_cursor[family]
                        selected = None
                        for local_offset in range(1, len(strategies) + 1):
                            global_idx = (local_cursor + local_offset) % len(strategies)
                            candidate = strategies[global_idx]
                            if candidate.family == family and candidate in family_eligible:
                                selected = candidate
                                family_strategy_cursor[family] = global_idx
                                break
                        if selected is not None:
                            chosen, chosen_index, family_cursor = selected, strategies.index(selected), family_idx
                            break
            elif run_mode == "turn-taking":
                for offset in range(1, len(queue) + 1):
                    slot = (queue_cursor + offset) % len(queue)
                    candidate = self.catalog.get(queue[slot])
                    if candidate in eligible:
                        chosen, chosen_index, queue_cursor = candidate, strategies.index(candidate), slot
                        break
            else:
                best_priority = max(s.priority for s in eligible)
                priority_eligible = [s for s in eligible if s.priority == best_priority]
                least_used = min(run_counts[s.name] for s in priority_eligible)
                finalists = [s for s in priority_eligible if run_counts[s.name] == least_used]
                for offset in range(1, len(strategies) + 1):
                    idx = (cursor + offset) % len(strategies)
                    if strategies[idx] in finalists:
                        chosen, chosen_index, cursor = strategies[idx], idx, idx
                        break
            if chosen is None:
                stop_reason, status = "scheduler_could_not_select_eligible_strategy", "blocked"
                break

            last_mode = run_mode
            last_strategy_name = chosen.name
            before = state
            entry = {
                "turn": turn_index + 1, "mode": run_mode, "state_shape": shape.as_mapping(),
                "eligible": [s.name for s in eligible], "ineligible": reasons,
                "strategy": chosen.name, "family": chosen.family, "decision": "execute",
            }
            try:
                guard.begin_task({"strategy": chosen.name, "state": before})
                parameters = __import__("inspect").signature(chosen.step).parameters
                if "context" in parameters:
                    outcome = chosen.step(_json_copy(before, label="strategy input"), context=run_context)
                else:
                    outcome = chosen.step(_json_copy(before, label="strategy input"))
                guard.checkpoint()
                if not isinstance(outcome, StrategyTurn):
                    raise TransitionContractError(f"strategy {chosen.name!r} must return StrategyTurn")
                next_state = before if outcome.next_state is None else _json_copy(dict(outcome.next_state), label="strategy next_state")
                if outcome.status == "progress" and next_state == before:
                    raise TransitionContractError(f"strategy {chosen.name!r} claimed progress without changing state")
                if outcome.status == "no_change" and next_state != before:
                    raise TransitionContractError(f"strategy {chosen.name!r} reported no_change but changed state")
                guard.check_output({"next_state": next_state, "turn": entry})
                for key in chosen.preserve_keys:
                    before_has, before_value = key in before, before.get(key)
                    after_has, after_value = key in next_state, next_state.get(key)
                    if before_has != after_has or before_value != after_value:
                        raise TransitionContractError(f"strategy {chosen.name!r} violated preserved state key {key!r}")
                if chosen.require_after_feasible and next_state.get("feasible") is not True:
                    raise TransitionContractError(f"strategy {chosen.name!r} must preserve feasible=true")
                run_counts[chosen.name] += 1
                entry.update({"status": outcome.status, "metrics": dict(outcome.metrics), "message": outcome.message})
                if outcome.status == "failed":
                    entry["status"] = "failed"
                    entry["error"] = outcome.message or "strategy returned failed status"
                    disabled.add(chosen.name)
                    turns.append(entry)
                    if self.on_failure == "stop":
                        stop_reason, status = "strategy_failed", "failed"
                        break
                    continue
                if outcome.status == "no_change":
                    next_state = dict(before)
                    next_state["stagnation"] = int(before.get("stagnation", 0)) + 1
                elif outcome.status == "complete":
                    next_state = dict(next_state)
                    next_state["done"] = True
                elif outcome.status == "progress":
                    next_state = dict(next_state)
                    next_state["stagnation"] = 0
                state = _json_copy(next_state, label="committed state")
                entry["after_shape"] = StateShape.from_state(state).as_mapping()
                entry["state_changed"] = state != before
                turns.append(entry)
                if outcome.status == "complete" or state.get("done") is True:
                    stop_reason, status = "strategy_completed_or_state_done", "completed"
                    break
            except ExecutionCancelled as exc:
                entry.update({"status": "cancelled", "error_type": type(exc).__name__, "error": str(exc)})
                turns.append(entry)
                stop_reason, status = "execution_cancelled", "cancelled"
                break
            except ExecutionBudgetExceeded as exc:
                entry.update({"status": "budget_exceeded", "error_type": type(exc).__name__, "error": str(exc)})
                turns.append(entry)
                stop_reason, status = "execution_budget_exceeded", "budget_exceeded"
                break
            except TransitionContractError as exc:
                entry.update({"status": "contract_error", "error_type": type(exc).__name__, "error": str(exc)})
                turns.append(entry)
                disabled.add(chosen.name)
                if self.on_failure == "stop":
                    stop_reason, status = "strategy_transition_contract_failed", "failed"
                    break
            except Exception as exc:
                entry.update({"status": "strategy_error", "error_type": type(exc).__name__, "error": str(exc)})
                turns.append(entry)
                disabled.add(chosen.name)
                if self.on_failure == "stop":
                    stop_reason, status = "strategy_execution_failed", "failed"
                    break
        else:
            stop_reason, status = "max_turns_reached", "turn_limit_reached"

        if state.get("done") is True and status == "turn_limit_reached":
            stop_reason, status = "state_marked_done", "completed"
        finished_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        record = {
            "schema_version": "1.0", "run_id": run_id,
            "workflow_id": str(original_state.get("portfolio_id", "algorithm-portfolio")),
            "description": "State-aware algorithm portfolio execution",
            "status": status, "started_at": started_at, "finished_at": finished_at,
            "duration_ms": round((time.perf_counter() - start_clock) * 1000, 3),
            "mode_requested": mode, "mode_last_used": run_mode, "stop_reason": stop_reason,
            "turn_count": len(turns), "strategy_run_counts": run_counts,
            "disabled_strategies": sorted(disabled), "initial_state": original_state,
            "final_state": state, "turns": turns, "outputs": {"final_state": state},
            "run_context": run_context.checkpoint_metadata(),
        }
        if self.run_store is not None:
            self.run_store.save(record)
        return record


def capability_strategy(
    *,
    name: str,
    family: str,
    registry: Any,
    capability_name: str,
    payload_builder: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    next_state_builder: Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]],
    when: Sequence[StatePredicate] = (),
    priority: int = 0,
    turn_quota: int = 1,
    preserve_keys: Sequence[str] = (),
    require_after_feasible: bool = False,
    description: str = "",
) -> AlgorithmStrategy:
    """Adapt a registered capability into one controlled portfolio turn."""
    if not callable(payload_builder) or not callable(next_state_builder):
        raise PortfolioDefinitionError("capability strategy builders must be callable")

    def step(state: Mapping[str, Any], *, context: RunContext | None = None) -> StrategyTurn:
        payload = payload_builder(state)
        if not isinstance(payload, Mapping):
            raise PortfolioDefinitionError("payload_builder must return a mapping")
        result = registry.run(capability_name, payload, context=context)
        next_state = next_state_builder(state, result)
        if not isinstance(next_state, Mapping):
            raise PortfolioDefinitionError("next_state_builder must return a mapping")
        return StrategyTurn(
            status="progress", next_state=next_state,
            metrics={"capability": capability_name, "capability_version": result.get("capability", {}).get("version")},
            message=f"Executed capability {capability_name}",
        )

    return AlgorithmStrategy(name, family, step, tuple(when), priority, turn_quota,
                             tuple(preserve_keys), require_after_feasible, description)
