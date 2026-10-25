"""CLI for a state-aware explicit-delta-matroid algorithm portfolio."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping

from .portfolio import (
    AlgorithmStrategy, CandidateMergeError, PortfolioController, StatePredicate,
    StrategyCatalog, StrategyTurn, merge_candidate_outputs,
)
from .registry import default_registry
from .runtime import RunContext
from .workflow import WorkflowRunStore


def _weight_map(ground: list[Any], raw: Mapping[str, Any]) -> dict[Any, int | float]:
    if not isinstance(raw, Mapping):
        raise ValueError("weights must be a JSON object")
    if set(raw) == set(ground):
        weights = dict(raw)
    else:
        reverse = {str(item): item for item in ground}
        if len(reverse) != len(ground) or set(raw) != set(reverse):
            raise ValueError("weights must contain exactly one value per ground-set element")
        weights = {reverse[key]: val for key, val in raw.items()}
    for item, value in weights.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or (isinstance(value, float) and not math.isfinite(value)):
            raise ValueError(f"weight for {item!r} must be a finite number")
    return weights


def build_explicit_optimization_portfolio(instance: Mapping[str, Any]):
    """Build compatible optimization candidates plus an independent explicit-family verifier."""
    required = {"ground_set", "feasible_sets", "weights"}
    missing = required - set(instance)
    if missing:
        raise ValueError(f"instance is missing fields: {sorted(missing)}")
    if not isinstance(instance["ground_set"], list):
        raise ValueError("ground_set must be an array")
    ground = list(instance["ground_set"])
    if len(ground) > 10:
        raise ValueError("explicit portfolio demo is bounded to at most 10 ground-set elements")
    try:
        unique_ground = set(ground)
    except TypeError as exc:
        raise ValueError("ground_set labels must be hashable JSON scalars") from exc
    if len(ground) != len(unique_ground):
        raise ValueError("ground_set elements must be unique")
    if not isinstance(instance["feasible_sets"], list) or not instance["feasible_sets"]:
        raise ValueError("feasible_sets must be a non-empty array of arrays")
    if any(not isinstance(row, list) for row in instance["feasible_sets"]):
        raise ValueError("each feasible set must be a JSON array")
    if len(instance["feasible_sets"]) > 1024:
        raise ValueError("explicit portfolio demo is bounded to at most 1024 feasible sets")
    try:
        family = [frozenset(row) for row in instance["feasible_sets"]]
    except TypeError as exc:
        raise ValueError("feasible set elements must be hashable JSON scalars") from exc
    if any(not X <= set(ground) for X in family):
        raise ValueError("feasible_sets contains elements outside ground_set")
    if len(set(family)) != len(family):
        raise ValueError("feasible_sets must not contain duplicates")
    weights = _weight_map(ground, instance["weights"])
    initial_raw = instance.get("initial", [])
    if not isinstance(initial_raw, list):
        raise ValueError("initial must be a JSON array")
    initial = list(initial_raw)
    try:
        initial_set = frozenset(initial)
    except TypeError as exc:
        raise ValueError("initial elements must be hashable JSON scalars") from exc
    if initial_set not in set(family):
        raise ValueError("initial must be a member of feasible_sets")
    alternate_raw = instance.get("alternate_initial")
    if alternate_raw is not None and not isinstance(alternate_raw, list):
        raise ValueError("alternate_initial must be a JSON array when supplied")
    alternate = list(alternate_raw) if alternate_raw is not None else None
    if alternate is not None and frozenset(alternate) not in set(family):
        raise ValueError("alternate_initial must be a member of feasible_sets")
    if alternate is None:
        alternate_set = next((X for X in family if X != frozenset(initial)), None)
        if alternate_set is not None:
            alternate = [item for item in ground if item in alternate_set]

    registry = default_registry()
    catalog = StrategyCatalog()
    preserve = ("problem_id", "ground_set", "feasible_sets", "weights", "initial")
    if alternate is not None:
        preserve = (*preserve, "alternate_initial")

    def solver_step(strategy_name: str, capability: str, start_key: str | None = None):
        def step(state: Mapping[str, Any], *, context: RunContext | None = None) -> StrategyTurn:
            start = state["initial"] if start_key is None else state[start_key]
            payload = {"ground_set": state["ground_set"], "feasible_sets": state["feasible_sets"],
                       "weights": state["weights"],
                       **({"initial": start} if capability == "delta_matroid.local_search" else {})}
            result = registry.run(capability, payload, context=context)
            next_state = dict(state)
            next_features = dict(state["features"])
            pending = list(next_features["pending_solvers"])
            pending.remove(strategy_name)
            next_features["pending_solvers"] = pending
            next_state["features"] = next_features
            next_results = dict(state["results"])
            if capability == "delta_matroid.local_search":
                details = {
                    "solution": result["solution"], "objective_value": result["objective_value"],
                    "converged": result["converged"], "membership_queries": result["membership_queries"],
                    "improving_moves": result["improving_moves"],
                }
            elif capability == "delta_matroid.signed_greedy":
                details = {
                    "solution": result["solution"], "objective_value": result["objective_value"],
                    "verified_feasible": result["verified_feasible"],
                    "separation_queries": result["separation_queries"], "verification_queries": result["verification_queries"],
                }
            else:
                details = {
                    "solution": result["solution"], "objective_value": result["objective_value"],
                    "member_verified": result["member_verified"],
                    "separation_queries": result["separation_queries"], "verification_queries": result["verification_queries"],
                }
            next_results[strategy_name] = details
            next_state["results"] = next_results
            if not pending:
                next_state["phase"] = "verify"
            metric_key = "membership_queries" if capability == "delta_matroid.local_search" else "separation_queries"
            return StrategyTurn("progress", next_state,
                                metrics={"objective_value": result["objective_value"], metric_key: details[metric_key]},
                                message=f"Executed {capability} as portfolio strategy {strategy_name}")
        return step

    optimization_phase = StatePredicate("phase", "eq", "optimize")
    pending_local = StatePredicate("features.pending_solvers", "contains", "local_search_primary")
    catalog.register(AlgorithmStrategy(
        "local_search_primary", "local-search",
        solver_step("local_search_primary", "delta_matroid.local_search"),
        (optimization_phase, pending_local), priority=10, turn_quota=1,
        preserve_keys=preserve, description="Best-improvement search from requested feasible initial set.", retry_safe=True, version="1.0.0",
    ))
    if alternate is not None:
        def restart_step(state: Mapping[str, Any], *, context: RunContext | None = None) -> StrategyTurn:
            payload = {"ground_set": state["ground_set"], "feasible_sets": state["feasible_sets"],
                       "weights": state["weights"], "initial": state["alternate_initial"]}
            result = registry.run("delta_matroid.local_search", payload, context=context)
            next_state = dict(state)
            features = dict(state["features"])
            pending = list(features["pending_solvers"])
            pending.remove("local_search_restart")
            features["pending_solvers"] = pending
            next_state["features"] = features
            results = dict(state["results"])
            results["local_search_restart"] = {
                "solution": result["solution"], "objective_value": result["objective_value"],
                "converged": result["converged"], "membership_queries": result["membership_queries"],
                "improving_moves": result["improving_moves"],
            }
            next_state["results"] = results
            if not pending:
                next_state["phase"] = "verify"
            return StrategyTurn("progress", next_state,
                                metrics={"objective_value": result["objective_value"],
                                         "membership_queries": result["membership_queries"]},
                                message="Executed LocalSearch from an alternate feasible starting set")
        catalog.register(AlgorithmStrategy(
            "local_search_restart", "local-search", restart_step,
            (optimization_phase, StatePredicate("features.pending_solvers", "contains", "local_search_restart")),
            priority=5, turn_quota=1, preserve_keys=preserve,
            description="Repeat LocalSearch from a distinct feasible starting set to inspect path dependence.",
            retry_safe=True, version="1.0.0",
        ))
    catalog.register(AlgorithmStrategy(
        "signed_greedy", "signed-greedy", solver_step("signed_greedy", "delta_matroid.signed_greedy"),
        (optimization_phase, StatePredicate("features.pending_solvers", "contains", "signed_greedy")),
        priority=10, turn_quota=1, preserve_keys=preserve,
        description="Optimize using signed greedy and the separation oracle.", retry_safe=True, version="1.0.0",
    ))

    def independent_verify(state: Mapping[str, Any]) -> StrategyTurn:
        feasible_sets = [frozenset(row) for row in state["feasible_sets"]]
        ground_order = list(state["ground_set"])
        weight_values = _weight_map(ground_order, state["weights"])
        objective = lambda X: sum(weight_values[item] for item in X)
        best_objective = max(objective(X) for X in feasible_sets)
        if not state["results"]:
            return StrategyTurn("failed", metrics={"candidate_count": 0},
                                message="No algorithm candidate ran; refusing to claim a portfolio result")
        checks: dict[str, Any] = {}
        candidate_rows: list[dict[str, Any]] = []
        known_feasible = set(feasible_sets)
        for name, record in state["results"].items():
            solution = frozenset(record["solution"])
            in_ground = solution <= set(ground_order)
            feasible = in_ground and solution in known_feasible
            actual = objective(solution) if in_ground else None
            report_matches = actual == record["objective_value"]
            checks[name] = {"solution_feasible": feasible, "objective_recomputed": actual,
                            "reported_objective_matches": report_matches,
                            "matches_best_objective": feasible and report_matches and actual == best_objective}
            candidate_rows.append({"name": name, "solution": list(record["solution"]),
                                   "objective_value": actual, "feasible": feasible and report_matches})
        try:
            merged = merge_candidate_outputs(candidate_rows, objective_key="objective_value", feasible_key="feasible")
        except CandidateMergeError:
            merged = None
        exact_solution = next(X for X in feasible_sets if objective(X) == best_objective)
        if merged is not None and merged["objective_value"] == best_objective:
            selected_solution, selected_by, fallback_used = merged["winner"]["solution"], merged["winner_name"], False
        else:
            selected_solution = [item for item in ground_order if item in exact_solution]
            selected_by, fallback_used = "explicit-family-exact-fallback", True
        selected_set = frozenset(selected_solution)
        selected_objective = objective(selected_set)
        selected_verified = selected_set in known_feasible and selected_objective == best_objective
        if not selected_verified:
            return StrategyTurn("failed", metrics={"checks": checks, "best_objective_value": best_objective},
                                message="Independent verification could not certify merged/fallback result")
        next_state = dict(state)
        next_state["portfolio_result"] = {
            "solution": selected_solution, "objective_value": selected_objective,
            "selected_by": selected_by, "fallback_used": fallback_used, "candidate_merge": merged,
        }
        next_state["verification"] = {
            "verified": True, "best_objective_value": best_objective, "candidate_checks": checks,
            "all_candidates_optimal": bool(checks) and all(item["matches_best_objective"] for item in checks.values()),
            "scope": "exact scan of the supplied explicit feasible family",
        }
        next_state["phase"] = "complete"
        next_state["done"] = True
        return StrategyTurn("complete", next_state,
                            metrics={"best_objective_value": best_objective, "candidates_verified": len(checks),
                                     "fallback_used": fallback_used},
                            message="Merged candidate outputs and independently verified selected optimum")

    catalog.register(AlgorithmStrategy(
        "independent_verify", "verification", independent_verify, (StatePredicate("phase", "eq", "verify"),),
        priority=100, preserve_keys=preserve,
        description="Independently verify feasibility and objective values by scanning the explicit family.",
        retry_safe=True, version="1.0.0",
    ))

    pending = ["local_search_primary"]
    if alternate is not None:
        pending.append("local_search_restart")
    pending.append("signed_greedy")
    state = {
        "kind": "explicit-delta-matroid", "phase": "optimize",
        "problem_id": str(instance.get("problem_id", "portfolio-demo")),
        "ground_set": ground, "feasible_sets": [list(X) for X in instance["feasible_sets"]],
        "weights": {str(k): v for k, v in weights.items()}, "initial": initial,
        "features": {"pending_solvers": pending}, "results": {}, "done": False,
    }
    if alternate is not None:
        state["alternate_initial"] = alternate
    for policy_key in ("scheduler_mode", "scheduler_rules", "portfolio_id"):
        if policy_key in instance:
            state[policy_key] = instance[policy_key]
    return PortfolioController(catalog), state, catalog


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a state-aware algorithm portfolio on an explicit delta-matroid instance")
    parser.add_argument("instance", type=Path, help="JSON instance with ground_set, feasible_sets and weights")
    parser.add_argument("--mode", choices=("rotation", "alternation", "turn-taking", "shape-driven", "auto"), default="rotation")
    parser.add_argument("--max-turns", type=int, default=20)
    parser.add_argument("--db", default=None, help="Optional SQLite run ledger path")
    parser.add_argument("--resume", default=None, help="Resume a retry-safe portfolio run by run ID; requires --db")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    try:
        instance = json.loads(args.instance.read_text(encoding="utf-8"))
        controller, state, catalog = build_explicit_optimization_portfolio(instance)
        if args.resume and not args.db:
            raise ValueError("--resume requires --db")
        if args.db:
            controller.run_store = WorkflowRunStore(args.db)
        result = controller.run(state, mode=args.mode, max_turns=args.max_turns, resume_from_run_id=args.resume)
        result["registered_strategies"] = catalog.describe()
        print(json.dumps(result, indent=2 if args.pretty else None, ensure_ascii=False, allow_nan=False))
        if result["status"] in {"failed", "blocked", "turn_limit_reached", "cancelled", "budget_exceeded"}:
            raise SystemExit(1)
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        print(f"portfolio error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
