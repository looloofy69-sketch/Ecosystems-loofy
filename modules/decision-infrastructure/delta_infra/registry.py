"""Capability registry for embedding algorithms in an orchestration runtime.

The registry is an execution boundary: it publishes each algorithm's actual
input contract and checks required payload fields. It does not infer that a
mathematical model fits a task; handlers validate the relevant preconditions.
"""
from __future__ import annotations

from dataclasses import dataclass
import inspect
from typing import Any, Callable, Mapping

from .runtime import RunContext


@dataclass(frozen=True)
class Capability:
    name: str
    version: str
    purpose: str
    preconditions: tuple[str, ...]
    input_keys: tuple[str, ...]
    handler: Callable[..., Mapping[str, Any]]
    side_effect_class: str = "unknown"
    retry_safe: bool = False

    def __post_init__(self) -> None:
        allowed = {"none", "read", "write", "external", "unknown"}
        if self.side_effect_class not in allowed:
            raise ValueError(f"side_effect_class must be one of {sorted(allowed)}")
        if not isinstance(self.retry_safe, bool):
            raise ValueError("retry_safe must be boolean")
        if self.retry_safe and self.side_effect_class not in {"none", "read"}:
            raise ValueError("Only side-effect-free/read-only capabilities may declare retry_safe=True")


class CapabilityRegistry:
    def __init__(self) -> None:
        self._capabilities: dict[str, Capability] = {}

    def register(self, capability: Capability) -> None:
        if capability.name in self._capabilities:
            raise ValueError(f"Capability already registered: {capability.name}")
        self._capabilities[capability.name] = capability

    def describe(self) -> list[dict[str, Any]]:
        return [
            {"name": c.name, "version": c.version, "purpose": c.purpose,
             "preconditions": list(c.preconditions), "input_keys": list(c.input_keys),
             "side_effect_class": c.side_effect_class, "retry_safe": c.retry_safe}
            for c in sorted(self._capabilities.values(), key=lambda item: item.name)
        ]

    def get(self, name: str) -> Capability:
        try:
            return self._capabilities[name]
        except KeyError as exc:
            raise KeyError(f"Unknown capability {name!r}; available: {sorted(self._capabilities)}") from exc

    def run(
        self, name: str, payload: Mapping[str, Any], *, context: RunContext | None = None
    ) -> Mapping[str, Any]:
        capability = self.get(name)
        missing = set(capability.input_keys) - set(payload)
        if missing:
            raise ValueError(f"Capability {name!r} is missing inputs: {sorted(missing)}")
        if context is not None:
            context.checkpoint()
        parameters = inspect.signature(capability.handler).parameters
        if context is not None and "context" in parameters:
            result = dict(capability.handler(payload, context=context))
        else:
            result = dict(capability.handler(payload))
        if context is not None:
            context.checkpoint()
        result["capability"] = {
            "name": capability.name, "version": capability.version,
            "side_effect_class": capability.side_effect_class,
        }
        return result


def _normalise_weights(ground_set, raw_weights):
    """Normalize Python mappings or JSON objects whose keys are always strings."""
    E = tuple(ground_set)
    if set(raw_weights) == set(E):
        return dict(raw_weights)
    lookup = {str(e): e for e in E}
    if len(lookup) != len(E):
        raise ValueError("Ground-set labels must have unique string representations in JSON inputs")
    if set(raw_weights) != set(lookup):
        raise ValueError("Weights must contain exactly one entry per ground-set element")
    return {lookup[str_key]: value for str_key, value in raw_weights.items()}


def _ordered(values, order):
    position = {element: i for i, element in enumerate(order)}
    return sorted(values, key=position.__getitem__)


def _explicit_system(payload):
    from .oracles import ExplicitFamilyOracle
    ground = tuple(payload["ground_set"])
    system = ExplicitFamilyOracle(ground, payload["feasible_sets"])
    return ground, system


def _register_explicit_optimization(registry: CapabilityRegistry) -> None:
    from .algorithms import local_search, signed_greedy

    def run_local_search(payload):
        ground, system = _explicit_system(payload)
        system.verify_delta_matroid()
        weights = _normalise_weights(ground, payload["weights"])
        result = local_search(ground, weights, payload["initial"], system.member,
                              max_improving_moves=payload.get("max_improving_moves"))
        return {
            "solution": _ordered(result.solution, ground), "objective_value": result.objective_value,
            "history": [_ordered(X, ground) for X in result.history],
            "membership_queries": result.membership_queries, "improving_moves": result.improving_moves,
            "converged": result.converged,
            "pending_improvement": None if result.pending_improvement is None else _ordered(result.pending_improvement, ground),
            "trace": result.trace,
        }

    def run_signed_greedy(payload):
        ground, system = _explicit_system(payload)
        system.verify_delta_matroid()
        weights = _normalise_weights(ground, payload["weights"])
        result = signed_greedy(ground, weights, system.separate, verify_result=True)
        return {
            "solution": _ordered(result.solution, ground), "objective_value": result.objective_value,
            "negative_weight_set": _ordered(result.negative_weight_set, ground),
            "greedy_order": list(result.greedy_order), "accepted_twisted": _ordered(result.accepted_twisted, ground),
            "rejected_twisted": _ordered(result.rejected_twisted, ground),
            "separation_queries": result.separation_queries, "verification_queries": result.verification_queries,
            "verified_feasible": result.verified_feasible, "decisions": result.decisions,
        }

    registry.register(Capability(
        "delta_matroid.local_search", "0.3.0",
        "Best-improvement optimization using one- and two-element flips.",
        ("Explicit feasible family satisfies symmetric exchange.", "Initial set is feasible.", "Objective is additive with finite real weights."),
        ("ground_set", "feasible_sets", "weights", "initial"), run_local_search, side_effect_class="none", retry_safe=True,
    ))
    registry.register(Capability(
        "delta_matroid.signed_greedy", "0.3.0",
        "Signed greedy optimization using a set-system separation oracle.",
        ("Explicit feasible family satisfies symmetric exchange.", "Weights are finite real values."),
        ("ground_set", "feasible_sets", "weights"), run_signed_greedy, side_effect_class="none", retry_safe=True,
    ))


def _register_path_capabilities(registry: CapabilityRegistry) -> None:
    from .algorithms import monotone_path, strong_path_explicit

    def run_monotone_path(payload):
        ground, system = _explicit_system(payload)
        system.verify_even_delta_matroid()
        result = monotone_path(ground, payload["A"], payload["B"], system.member,
                               assume_even_delta_matroid=True)
        return {
            "path": [_ordered(X, ground) for X in result.path], "steps": result.steps,
            "membership_queries": result.membership_queries,
            "exchange_membership_queries": result.exchange_membership_queries,
            "endpoint_validation_queries": result.endpoint_validation_queries, "trace": result.trace,
        }

    def run_strong_path(payload):
        ground, system = _explicit_system(payload)
        result = strong_path_explicit(ground, system.feasible_sets, payload["A"], payload["B"],
                                      dummy=payload.get("dummy", "*"))
        lifted_order = tuple(ground) + (payload.get("dummy", "*"),)
        return {
            "path": [_ordered(X, ground) for X in result.path],
            "lifted_path": [_ordered(X, lifted_order) for X in result.lifted_path],
            "steps": result.steps, "membership_queries": result.membership_queries,
            "lift_validated": result.lift_validated, "trace": result.trace,
        }

    registry.register(Capability(
        "delta_matroid.monotone_path", "0.3.0",
        "Construct a distance-decreasing feasible path in an even delta-matroid.",
        ("Explicit feasible family satisfies symmetric exchange and uniform parity.", "Both endpoints are feasible."),
        ("ground_set", "feasible_sets", "A", "B"), run_monotone_path, side_effect_class="none", retry_safe=True,
    ))
    registry.register(Capability(
        "delta_matroid.strong_path", "0.3.0",
        "Validate a candidate lift and construct a path only if the lifted system is an even delta-matroid.",
        ("Explicit original family is a delta-matroid.", "Lift is injective, even, and satisfies symmetric exchange."),
        ("ground_set", "feasible_sets", "A", "B"), run_strong_path, side_effect_class="none", retry_safe=True,
    ))


def _register_matrix_capability(registry: CapabilityRegistry) -> None:
    from .matrix import PrimeField, RationalField, schur_path

    def run_schur(payload):
        field_spec = payload.get("field", "Q")
        if field_spec == "Q" or field_spec is None:
            selected_field = RationalField()
        elif isinstance(field_spec, dict) and field_spec.get("type") == "GF":
            selected_field = PrimeField(int(field_spec["p"]))
        else:
            raise ValueError("field must be 'Q' or {'type': 'GF', 'p': prime_integer}")
        labels = payload.get("labels")
        result = schur_path(payload["matrix"], labels, field=selected_field)
        label_order = tuple(range(len(payload["matrix"]))) if labels is None else tuple(labels)
        return {
            "complete": result.complete, "pairs": [list(pair) for pair in result.pairs],
            "prefix_sets": [_ordered(X, label_order) for X in result.prefix_sets],
            "remaining_labels": list(result.remaining_labels), "residual_matrix": result.residual_matrix,
            "field": result.field_name, "pivot_count": result.pivot_count,
            "elimination_field_operations": result.elimination_field_operations,
            "failure_reason": result.failure_reason,
        }

    registry.register(Capability(
        "delta_matroid.schur_path", "0.3.0",
        "Build a sequence of nonsingular principal prefixes using 2x2 Schur pivots.",
        ("Matrix is square and alternating over the selected exact field.",), ("matrix",), run_schur, side_effect_class="none", retry_safe=True,
    ))


def _register_matching_capabilities(registry: CapabilityRegistry) -> None:
    from .matching import matching_separate, signed_greedy_matching_delta_matroid

    def run_match_sep(payload):
        vertices = tuple(payload["vertices"])
        result = matching_separate(vertices, payload["edges"], payload["S"], payload["T"])
        return {
            "feasible": result.feasible, "score": result.score, "required_score": result.required_score,
            "matching": [list(edge) for edge in result.matching],
            "covered_required_vertices": _ordered(result.covered_required_vertices, vertices),
            "witness_feasible_set": _ordered(result.witness_feasible_set, vertices),
        }

    def run_matching_greedy(payload):
        vertices = tuple(payload["vertices"])
        weights = _normalise_weights(vertices, payload["weights"])
        return signed_greedy_matching_delta_matroid(vertices, payload["edges"], weights)

    registry.register(Capability(
        "matching.separation", "0.3.0",
        "Answer a matching-delta-matroid separability query with a maximum-weight matching witness.",
        ("Finite simple undirected graph.", "S and T are disjoint vertex subsets."),
        ("vertices", "edges", "S", "T"), run_match_sep, side_effect_class="none", retry_safe=True,
    ))
    registry.register(Capability(
        "matching.signed_greedy", "0.3.0",
        "Maximize additive vertex weights over vertex sets whose induced subgraph has a perfect matching.",
        ("Finite simple undirected graph.", "Every vertex has a finite real weight."),
        ("vertices", "edges", "weights"), run_matching_greedy, side_effect_class="none", retry_safe=True,
    ))


def default_registry() -> CapabilityRegistry:
    """Return all JSON-callable algorithm capabilities with declared preconditions."""
    registry = CapabilityRegistry()
    _register_explicit_optimization(registry)
    _register_path_capabilities(registry)
    _register_matrix_capability(registry)
    _register_matching_capabilities(registry)
    return registry
