"""Oracle contracts and explicit finite-family implementations.

The algorithms depend on these small interfaces rather than on a particular
representation of the feasible family. That makes them usable with in-memory
sets, graph-backed separation routines, or later remote services.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Callable, FrozenSet, Hashable, Iterable, Protocol, TypeAlias

Element: TypeAlias = Hashable
FrozenSetT: TypeAlias = frozenset[Element]
MembershipOracle: TypeAlias = Callable[[FrozenSetT], bool]
SeparationOracle: TypeAlias = Callable[[FrozenSetT, FrozenSetT], bool]


class OracleContractError(RuntimeError):
    """An oracle's answers violate a mathematical contract required by an algorithm."""


class MembershipOracleProtocol(Protocol):
    def __call__(self, candidate: FrozenSetT) -> bool: ...


class SeparationOracleProtocol(Protocol):
    def __call__(self, include: FrozenSetT, exclude: FrozenSetT) -> bool: ...


@dataclass(frozen=True)
class ExplicitFamilyOracle:
    """Membership and separation oracle for an explicitly enumerated set system."""
    ground_set: tuple[Element, ...]
    feasible_sets: frozenset[FrozenSetT]

    def __init__(self, ground_set: Iterable[Element], feasible_sets: Iterable[Iterable[Element]]):
        ground = tuple(ground_set)
        if len(set(ground)) != len(ground):
            raise ValueError("Ground-set elements must be unique")
        ground_set_frozen = frozenset(ground)
        family = frozenset(frozenset(F) for F in feasible_sets)
        if not family:
            raise ValueError("A delta-matroid/set system must have at least one feasible set")
        invalid = [F for F in family if not F <= ground_set_frozen]
        if invalid:
            raise ValueError(f"Feasible sets contain elements outside the ground set: {invalid[:3]!r}")
        object.__setattr__(self, "ground_set", ground)
        object.__setattr__(self, "feasible_sets", family)

    def member(self, candidate: Iterable[Element]) -> bool:
        return frozenset(candidate) in self.feasible_sets

    def __call__(self, candidate: FrozenSetT) -> bool:
        return self.member(candidate)

    def separate(self, include: Iterable[Element], exclude: Iterable[Element]) -> bool:
        P, Q = frozenset(include), frozenset(exclude)
        E = frozenset(self.ground_set)
        if not P <= E or not Q <= E:
            raise ValueError("Separation constraints must be subsets of the ground set")
        if P & Q:
            raise ValueError("Include and exclude constraints must be disjoint")
        return any(P <= F and not (Q & F) for F in self.feasible_sets)

    def is_delta_matroid(self) -> bool:
        """Check symmetric exchange in O(|F|^2 * |E|^2) time."""
        family = self.feasible_sets
        for X in family:
            for Y in family:
                delta = X ^ Y
                for x in delta:
                    if not any((X ^ frozenset((x, y))) in family for y in delta):
                        return False
        return True

    def is_even(self) -> bool:
        return len({len(F) % 2 for F in self.feasible_sets}) == 1

    def verify_delta_matroid(self) -> None:
        if not self.is_delta_matroid():
            raise ValueError("The supplied feasible family violates the symmetric exchange axiom")

    def verify_even_delta_matroid(self) -> None:
        self.verify_delta_matroid()
        if not self.is_even():
            raise ValueError("Algorithm 3 requires all feasible sets to have the same parity")


@dataclass(frozen=True)
class TwistedSeparationOracle:
    r"""Implement Sep_(D △ N)(P,Q) using a separation oracle for D.

    Sep_(D △ N)(P,Q) = Sep_D((P\N) ∪ (Q∩N), (Q\N) ∪ (P∩N)).
    """
    base_oracle: SeparationOracleProtocol
    twist: FrozenSetT

    def __init__(self, base_oracle: SeparationOracleProtocol, twist: Iterable[Element]):
        object.__setattr__(self, "base_oracle", base_oracle)
        object.__setattr__(self, "twist", frozenset(twist))

    def separate(self, include: Iterable[Element], exclude: Iterable[Element]) -> bool:
        P, Q, N = frozenset(include), frozenset(exclude), self.twist
        if P & Q:
            raise ValueError("Include and exclude constraints must be disjoint")
        P_original = (P - N) | (Q & N)
        Q_original = (Q - N) | (P & N)
        return bool(self.base_oracle(P_original, Q_original))

    def __call__(self, include: FrozenSetT, exclude: FrozenSetT) -> bool:
        return self.separate(include, exclude)


def all_subsets(ground_set: Iterable[Element]) -> list[FrozenSetT]:
    """Utility for small-instance tests and independent exact verification only."""
    E = tuple(ground_set)
    return [frozenset(S) for r in range(len(E) + 1) for S in combinations(E, r)]
