"""Algorithm 4: Schur-pivot path construction over exact supported fields."""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import isqrt
from typing import Any, Hashable, Iterable, Protocol, Sequence


class Field(Protocol):
    name: str
    def normalize(self, value: Any) -> Any: ...
    def zero(self) -> Any: ...
    def one(self) -> Any: ...
    def add(self, a: Any, b: Any) -> Any: ...
    def sub(self, a: Any, b: Any) -> Any: ...
    def mul(self, a: Any, b: Any) -> Any: ...
    def div(self, a: Any, b: Any) -> Any: ...
    def neg(self, a: Any) -> Any: ...
    def is_zero(self, a: Any) -> bool: ...


@dataclass(frozen=True)
class RationalField:
    name: str = "Q"
    def normalize(self, value: Any) -> Fraction:
        if isinstance(value, Fraction): return value
        if isinstance(value, float): return Fraction(str(value))
        return Fraction(value)
    def zero(self) -> Fraction: return Fraction(0)
    def one(self) -> Fraction: return Fraction(1)
    def add(self, a: Any, b: Any) -> Fraction: return self.normalize(a) + self.normalize(b)
    def sub(self, a: Any, b: Any) -> Fraction: return self.normalize(a) - self.normalize(b)
    def mul(self, a: Any, b: Any) -> Fraction: return self.normalize(a) * self.normalize(b)
    def div(self, a: Any, b: Any) -> Fraction:
        b = self.normalize(b)
        if b == 0: raise ZeroDivisionError("Division by zero in Q")
        return self.normalize(a) / b
    def neg(self, a: Any) -> Fraction: return -self.normalize(a)
    def is_zero(self, a: Any) -> bool: return self.normalize(a) == 0


@dataclass(frozen=True)
class PrimeField:
    """Prime field GF(p), supporting exact arithmetic modulo a prime p."""
    p: int
    name: str = ""
    def __post_init__(self) -> None:
        if self.p < 2 or any(self.p % d == 0 for d in range(2, isqrt(self.p) + 1)):
            raise ValueError("PrimeField requires a prime modulus")
        object.__setattr__(self, "name", f"GF({self.p})")
    def normalize(self, value: Any) -> int:
        if isinstance(value, Fraction):
            numerator, denominator = value.numerator, value.denominator
            return (numerator * pow(denominator, -1, self.p)) % self.p
        return int(value) % self.p
    def zero(self) -> int: return 0
    def one(self) -> int: return 1
    def add(self, a: Any, b: Any) -> int: return (self.normalize(a) + self.normalize(b)) % self.p
    def sub(self, a: Any, b: Any) -> int: return (self.normalize(a) - self.normalize(b)) % self.p
    def mul(self, a: Any, b: Any) -> int: return (self.normalize(a) * self.normalize(b)) % self.p
    def div(self, a: Any, b: Any) -> int:
        b = self.normalize(b)
        if b == 0: raise ZeroDivisionError(f"Division by zero in {self.name}")
        return (self.normalize(a) * pow(b, -1, self.p)) % self.p
    def neg(self, a: Any) -> int: return (-self.normalize(a)) % self.p
    def is_zero(self, a: Any) -> bool: return self.normalize(a) == 0


@dataclass
class SchurPathResult:
    pairs: list[tuple[Hashable, Hashable]]
    prefix_sets: list[frozenset[Hashable]]
    complete: bool
    remaining_labels: tuple[Hashable, ...]
    residual_matrix: list[list[Any]]
    field_name: str
    failure_reason: str | None = None
    pivot_count: int = 0
    elimination_field_operations: int = 0


def schur_path(
    matrix: Sequence[Sequence[Any]],
    labels: Iterable[Hashable] | None = None,
    *,
    field: Field | None = None,
) -> SchurPathResult:
    """Find successive nonzero 2x2 pivots and apply Schur complements."""
    F: Field = field or RationalField()
    S = [[F.normalize(value) for value in row] for row in matrix]
    n = len(S)
    if any(len(row) != n for row in S):
        raise ValueError("Matrix must be square")
    L = tuple(range(n)) if labels is None else tuple(labels)
    if len(L) != n or len(set(L)) != len(L):
        raise ValueError("Labels must be unique and match the matrix dimension")
    for i in range(n):
        if not F.is_zero(S[i][i]):
            raise ValueError("Alternating matrix must have a zero diagonal")
        for j in range(i + 1, n):
            if F.normalize(S[j][i]) != F.neg(S[i][j]):
                raise ValueError("Matrix must satisfy A[j,i] = -A[i,j] over the selected field")

    alive = list(L)
    pairs: list[tuple[Hashable, Hashable]] = []
    prefixes: list[frozenset[Hashable]] = []
    prefix_elements: set[Hashable] = set()
    elimination_field_operations = 0

    while alive:
        x_index = 0
        y_index = next((j for j in range(1, len(alive)) if not F.is_zero(S[x_index][j])), None)
        if y_index is None:
            return SchurPathResult(
                pairs, prefixes, False, tuple(alive), S, F.name,
                "Residual first row has no nonzero partner; residual matrix is singular.", len(pairs),
                elimination_field_operations,
            )
        i, j = x_index, y_index
        x, y = alive[i], alive[j]
        a = S[i][j]
        inv_a = F.div(F.one(), a)
        elimination_field_operations += 1
        pair = (x, y)
        pairs.append(pair)
        prefix_elements.update(pair)
        prefixes.append(frozenset(prefix_elements))

        pivot_indices = {i, j}
        rest = [k for k in range(len(alive)) if k not in pivot_indices]
        if not rest:
            S = []
            alive = []
            break

        neg_inv_a = F.neg(inv_a)
        elimination_field_operations += 1
        next_S: list[list[Any]] = []
        for r in rest:
            row = []
            for c in rest:
                term_1 = F.mul(F.mul(S[r][i], neg_inv_a), S[j][c])
                term_2 = F.mul(F.mul(S[r][j], inv_a), S[i][c])
                product_term = F.add(term_1, term_2)
                row.append(F.sub(S[r][c], product_term))
            next_S.append(row)
        S = next_S
        elimination_field_operations += 6 * len(rest) * len(rest)
        alive = [alive[k] for k in rest]

        for r in range(len(S)):
            if not F.is_zero(S[r][r]):
                raise ArithmeticError("Schur complement lost the zero-diagonal invariant")
            for c in range(r + 1, len(S)):
                if F.normalize(S[c][r]) != F.neg(S[r][c]):
                    raise ArithmeticError("Schur complement lost the alternating-matrix invariant")

    return SchurPathResult(
        pairs, prefixes, True, tuple(), [], F.name, None, len(pairs), elimination_field_operations,
    )
