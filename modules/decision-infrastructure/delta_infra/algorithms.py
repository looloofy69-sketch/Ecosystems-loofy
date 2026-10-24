"""Reusable implementations of Algorithms 1, 2, 3, and 3'.

Every algorithm exposes its oracle-call counts and a structured trace. Oracle-
only algorithms cannot prove global axioms from finite observations, so their
mathematical preconditions are explicit in function signatures/documentation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from math import isfinite
from numbers import Real
from typing import Any, Callable, Hashable, Iterable, Mapping

from .oracles import (
    ExplicitFamilyOracle,
    MembershipOracleProtocol,
    OracleContractError,
    SeparationOracleProtocol,
    TwistedSeparationOracle,
)

Element = Hashable
FrozenSetT = frozenset[Element]


def _validate_ground_set(ground_set: Iterable[Element]) -> tuple[Element, ...]:
    E = tuple(ground_set)
    if len(set(E)) != len(E):
        raise ValueError("Ground-set elements must be unique")
    return E


def _validate_weights(E: tuple[Element, ...], weights: Mapping[Element, Real]) -> None:
    if set(weights) != set(E):
        raise ValueError("Weights must be defined exactly for every ground-set element")
    for e, weight in weights.items():
        if isinstance(weight, (int, Fraction)):
            continue
        if not isinstance(weight, Real) or not isfinite(weight):
            raise ValueError(f"Weight for {e!r} must be a finite real number")


def objective(X: Iterable[Element], weights: Mapping[Element, Real]) -> Real:
    return sum((weights[e] for e in X), 0)


@dataclass
class LocalSearchResult:
    solution: FrozenSetT
    objective_value: Real
    history: list[FrozenSetT]
    membership_queries: int
    improving_moves: int
    converged: bool
    pending_improvement: FrozenSetT | None = None
    trace: list[dict[str, Any]] = field(default_factory=list)


def local_search(
    ground_set: Iterable[Element],
    weights: Mapping[Element, Real],
    initial: Iterable[Element],
    membership_oracle: MembershipOracleProtocol,
    *,
    max_improving_moves: int | None = None,
    checkpoint: Callable[[], None] | None = None,
) -> LocalSearchResult:
    """Algorithm 1: best-improvement search over all one/two-element flips."""
    E = _validate_ground_set(ground_set)
    _validate_weights(E, weights)
    if max_improving_moves is not None and max_improving_moves < 0:
        raise ValueError("max_improving_moves must be non-negative or None")
    X = frozenset(initial)
    if not X <= frozenset(E):
        raise ValueError("Initial set contains elements outside the ground set")
    queries = 1
    if not membership_oracle(X):
        raise ValueError("Initial set must be feasible")

    history = [X]
    order_index = {element: i for i, element in enumerate(E)}
    show = lambda state: [element for element in E if element in state]
    trace: list[dict[str, Any]] = [{"event": "start", "solution": show(X), "objective": objective(X, weights)}]
    moves = 0

    while True:
        best = X
        best_value = objective(X, weights)
        for r in (1, 2):
            from itertools import combinations
            for U_tuple in combinations(E, r):
                if checkpoint is not None:
                    checkpoint()
                candidate = X ^ frozenset(U_tuple)
                queries += 1
                feasible = bool(membership_oracle(candidate))
                candidate_value = objective(candidate, weights)
                trace.append({
                    "event": "candidate", "round": moves, "flip": list(U_tuple),
                    "candidate": show(candidate), "feasible": feasible, "objective": candidate_value,
                })
                if feasible and candidate_value > best_value:
                    best, best_value = candidate, candidate_value
        if best == X:
            trace.append({"event": "converged", "solution": show(X), "objective": objective(X, weights)})
            return LocalSearchResult(X, objective(X, weights), history, queries, moves, True, None, trace)
        if max_improving_moves is not None and moves >= max_improving_moves:
            trace.append({"event": "move_limit", "current": show(X), "pending_improvement": show(best)})
            return LocalSearchResult(X, objective(X, weights), history, queries, moves, False, best, trace)
        previous = X
        X = best
        moves += 1
        history.append(X)
        flipped = sorted(previous ^ X, key=order_index.__getitem__)
        trace.append({"event": "accept_move", "from": show(previous), "to": show(X), "flip": flipped,
                      "objective": objective(X, weights)})


@dataclass
class SignedGreedyResult:
    solution: FrozenSetT
    objective_value: Real
    negative_weight_set: FrozenSetT
    greedy_order: tuple[Element, ...]
    accepted_twisted: FrozenSetT
    rejected_twisted: FrozenSetT
    separation_queries: int
    verification_queries: int
    verified_feasible: bool | None
    decisions: list[dict[str, Any]]


def signed_greedy(
    ground_set: Iterable[Element],
    weights: Mapping[Element, Real],
    separation_oracle: SeparationOracleProtocol,
    *,
    verify_result: bool = True,
    checkpoint: Callable[[], None] | None = None,
) -> SignedGreedyResult:
    """Algorithm 2 using a set-system separation oracle."""
    E = _validate_ground_set(ground_set)
    _validate_weights(E, weights)
    N = frozenset(e for e in E if weights[e] < 0)
    position = {e: i for i, e in enumerate(E)}
    order = tuple(sorted(E, key=lambda e: (-abs(weights[e]), position[e])))
    twisted_oracle = TwistedSeparationOracle(separation_oracle, N)
    S: set[Element] = set()
    T: set[Element] = set()
    decisions: list[dict[str, Any]] = []
    queries = 0

    for e in order:
        if checkpoint is not None:
            checkpoint()
        accepted = bool(twisted_oracle(S | {e}, T))
        queries += 1
        if accepted:
            S.add(e)
        else:
            T.add(e)
        decisions.append({
            "element": e, "weight": weights[e], "decision": "accept" if accepted else "reject",
            "accepted_twisted": tuple(x for x in E if x in S),
            "rejected_twisted": tuple(x for x in E if x in T),
        })

    result = frozenset(S ^ set(N))
    verification_queries = 0
    verified: bool | None = None
    if verify_result:
        if checkpoint is not None:
            checkpoint()
        verification_queries = 1
        verified = bool(separation_oracle(result, frozenset(E) - result))
        if not verified:
            raise OracleContractError(
                "SignedGreedy returned a set that fails the final separator check; "
                "the oracle or delta-matroid precondition may be invalid"
            )

    return SignedGreedyResult(
        solution=result, objective_value=objective(result, weights), negative_weight_set=N,
        greedy_order=order, accepted_twisted=frozenset(S), rejected_twisted=frozenset(T),
        separation_queries=queries, verification_queries=verification_queries,
        verified_feasible=verified, decisions=decisions,
    )


@dataclass
class MonotonePathResult:
    path: list[FrozenSetT]
    steps: int
    exchange_membership_queries: int
    endpoint_validation_queries: int
    trace: list[dict[str, Any]] = field(default_factory=list)

    @property
    def membership_queries(self) -> int:
        return self.exchange_membership_queries + self.endpoint_validation_queries


def monotone_path(
    ground_set: Iterable[Element],
    A: Iterable[Element],
    B: Iterable[Element],
    membership_oracle: MembershipOracleProtocol,
    *,
    assume_even_delta_matroid: bool = False,
    checkpoint: Callable[[], None] | None = None,
) -> MonotonePathResult:
    """Algorithm 3; callers must establish the even-delta-matroid precondition."""
    if not assume_even_delta_matroid:
        raise ValueError(
            "Algorithm 3 requires a verified/externally guaranteed even delta-matroid; "
            "pass assume_even_delta_matroid=True only when that precondition is established"
        )
    E = _validate_ground_set(ground_set)
    rank = {e: i for i, e in enumerate(E)}
    X, target = frozenset(A), frozenset(B)
    E_set = frozenset(E)
    if not X <= E_set or not target <= E_set:
        raise ValueError("Endpoints must be subsets of the ground set")
    endpoint_a_feasible = bool(membership_oracle(X))
    endpoint_b_feasible = bool(membership_oracle(target))
    endpoint_queries = 2
    if not endpoint_a_feasible or not endpoint_b_feasible:
        raise ValueError("Both endpoints must be feasible")
    if (len(X) - len(target)) % 2:
        raise ValueError("Algorithm 3 requires endpoints of the same parity")

    path = [X]
    show = lambda state: [element for element in E if element in state]
    trace = [{"event": "start", "A": show(X), "B": show(target), "distance": len(X ^ target)}]
    exchange_queries = 0
    while X != target:
        if checkpoint is not None:
            checkpoint()
        delta = X ^ target
        x = min(delta, key=rank.__getitem__)
        found = False
        candidates = sorted(delta - {x}, key=rank.__getitem__)
        for y in candidates:
            if checkpoint is not None:
                checkpoint()
            candidate = X ^ frozenset((x, y))
            exchange_queries += 1
            if membership_oracle(candidate):
                found = True
                trace.append({"event": "exchange", "x": x, "y": y, "from": show(X),
                              "to": show(candidate), "remaining_distance": len(candidate ^ target)})
                X = candidate
                path.append(X)
                break
        if not found:
            raise OracleContractError(
                "No exchange partner was found. The system may not be an even delta-matroid, "
                "or the membership oracle may be incorrect."
            )
    trace.append({"event": "complete", "steps": len(path) - 1, "target": show(target)})
    return MonotonePathResult(path, len(path) - 1, exchange_queries, endpoint_queries, trace)


@dataclass
class StrongPathResult:
    path: list[FrozenSetT]
    lifted_path: list[FrozenSetT]
    steps: int
    membership_queries: int
    lift_validated: bool
    trace: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class StrongPathOracleResult:
    path: list[FrozenSetT]
    lifted_path: list[FrozenSetT]
    steps: int
    lifted_membership_queries: int
    original_membership_queries: int
    contract_basis: str
    trace: list[dict[str, Any]] = field(default_factory=list)


def strong_path_oracle(
    lifted_ground_set: Iterable[Element],
    A: Iterable[Element],
    B: Iterable[Element],
    lift: Callable[[Iterable[Element]], Iterable[Element]],
    project: Callable[[Iterable[Element]], Iterable[Element]],
    lifted_membership_oracle: MembershipOracleProtocol,
    original_membership_oracle: MembershipOracleProtocol,
    *,
    lift_exchange_guaranteed: bool = False,
    checkpoint: Callable[[], None] | None = None,
) -> StrongPathOracleResult:
    """Oracle-only Algorithm 3' with an externally guaranteed valid lift."""
    if not lift_exchange_guaranteed:
        raise ValueError(
            "Oracle-only StrongPath requires an externally established theorem/contract "
            "that the supplied lift is an even delta-matroid"
        )
    lifted_E = _validate_ground_set(lifted_ground_set)
    A_set, B_set = frozenset(A), frozenset(B)
    lifted_A, lifted_B = frozenset(lift(A_set)), frozenset(lift(B_set))
    if not lifted_A <= frozenset(lifted_E) or not lifted_B <= frozenset(lifted_E):
        raise ValueError("Lifted endpoints must be subsets of lifted_ground_set")

    result = monotone_path(
        lifted_E, lifted_A, lifted_B, lifted_membership_oracle,
        assume_even_delta_matroid=True,
        checkpoint=checkpoint,
    )
    projected = [frozenset(project(state)) for state in result.path]
    if projected[0] != A_set or projected[-1] != B_set:
        raise OracleContractError("Projection does not map lifted endpoints back to A and B")
    for state in projected:
        if not original_membership_oracle(state):
            raise OracleContractError("A projected lifted-path state is infeasible in the original system")
    return StrongPathOracleResult(
        path=projected, lifted_path=result.path, steps=result.steps,
        lifted_membership_queries=result.membership_queries,
        original_membership_queries=len(projected),
        contract_basis="externally_guaranteed_even_delta_matroid_lift",
        trace=[{"event": "lift_contract", "basis": "externally_guaranteed_even_delta_matroid_lift"}] + result.trace,
    )


def parity_correcting_lift(X: Iterable[Element], dummy: Element = "*") -> FrozenSetT:
    """Candidate lift: add a dummy element iff |X| is odd.

    This lift is not valid for every delta-matroid. Explicit StrongPath validates
    the lifted exchange axiom before using it.
    """
    F = frozenset(X)
    if dummy in F:
        raise ValueError("Dummy element collides with an original ground-set element")
    return F | ({dummy} if len(F) % 2 else set())


def strong_path_explicit(
    ground_set: Iterable[Element],
    feasible_sets: Iterable[Iterable[Element]],
    A: Iterable[Element],
    B: Iterable[Element],
    *,
    dummy: Element = "*",
    lift: Callable[[Iterable[Element]], Iterable[Element]] | None = None,
    checkpoint: Callable[[], None] | None = None,
) -> StrongPathResult:
    """Algorithm 3' for explicit families with lift precondition verification."""
    E = _validate_ground_set(ground_set)
    if dummy in E:
        raise ValueError("Dummy element must be outside the original ground set")
    original = ExplicitFamilyOracle(E, feasible_sets)
    if checkpoint is not None:
        checkpoint()
    original.verify_delta_matroid(checkpoint=checkpoint)
    A_set, B_set = frozenset(A), frozenset(B)
    if A_set not in original.feasible_sets or B_set not in original.feasible_sets:
        raise ValueError("Both endpoints must be feasible")

    lift_function = lift if lift is not None else (lambda X: parity_correcting_lift(X, dummy=dummy))
    lifted_list = []
    for feasible_set in original.feasible_sets:
        if checkpoint is not None:
            checkpoint()
        lifted_list.append(frozenset(lift_function(feasible_set)))
    if len(set(lifted_list)) != len(lifted_list):
        raise ValueError("Lift is not injective over the feasible family")
    if len({len(F) % 2 for F in lifted_list}) != 1:
        raise ValueError("Lifted family does not have uniform parity")
    lifted_family = frozenset(lifted_list)
    lift_oracle = ExplicitFamilyOracle(tuple(E) + (dummy,), lifted_family)
    if checkpoint is not None:
        checkpoint()
    if not lift_oracle.is_delta_matroid(checkpoint=checkpoint):
        raise ValueError("StrongPath precondition failed: lifted family violates symmetric exchange")
    if not lift_oracle.is_even():
        raise ValueError("StrongPath precondition failed: lifted family is not even")

    lifted_A, lifted_B = frozenset(lift_function(A_set)), frozenset(lift_function(B_set))
    path_result = monotone_path(
        tuple(E) + (dummy,), lifted_A, lifted_B, lift_oracle.member,
        assume_even_delta_matroid=True,
    )
    projected = [frozenset(v for v in state if v != dummy) for state in path_result.path]
    if not all(P in original.feasible_sets for P in projected):
        raise OracleContractError("Projection of a lifted feasible path produced an infeasible original set")
    trace = [{"event": "lift_verified", "lifted_feasible_count": len(lifted_family)}] + path_result.trace
    return StrongPathResult(
        projected, path_result.path, path_result.steps,
        path_result.membership_queries, True, trace,
    )
