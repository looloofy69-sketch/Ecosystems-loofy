"""NetworkX-backed implementation of Algorithm 5 and its matching delta-matroid."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Hashable, Iterable, Mapping

try:
    import networkx as nx
except ImportError as exc:  # pragma: no cover
    raise ImportError("Matching backend requires NetworkX; install networkx>=3.2,<4") from exc

Vertex = Hashable
Edge = tuple[Vertex, Vertex]


def normalize_graph(vertices: Iterable[Vertex], edges: Iterable[Iterable[Vertex]]):
    V = tuple(vertices)
    Vset = set(V)
    if len(V) != len(Vset):
        raise ValueError("Vertices must be unique")
    normalized: list[Edge] = []
    seen: set[frozenset[Vertex]] = set()
    for raw in edges:
        edge = tuple(raw)
        if len(edge) != 2:
            raise ValueError(f"Each edge must have exactly two endpoints: {edge!r}")
        u, v = edge
        if u not in Vset or v not in Vset:
            raise ValueError(f"Edge endpoint missing from vertices: {edge!r}")
        if u == v:
            raise ValueError("Self-loops are not supported")
        key = frozenset((u, v))
        if key in seen:
            raise ValueError(f"Duplicate undirected edge: {edge!r}")
        seen.add(key)
        normalized.append((u, v))
    return V, Vset, tuple(normalized)


@dataclass
class MatchingSepResult:
    feasible: bool
    score: int
    required_score: int
    matching: tuple[Edge, ...]
    covered_required_vertices: frozenset[Vertex]
    witness_feasible_set: frozenset[Vertex]


class MatchingDeltaMatroid:
    """Feasible subsets are vertex sets whose induced graph has a perfect matching."""
    def __init__(self, vertices: Iterable[Vertex], edges: Iterable[Edge]):
        self.vertices, self.vertex_set, self.edges = normalize_graph(vertices, edges)
        self.graph = nx.Graph()
        self.graph.add_nodes_from(self.vertices)
        self.graph.add_edges_from(self.edges)
    def member(self, candidate: Iterable[Vertex]) -> bool:
        X = frozenset(candidate)
        if not X <= self.vertex_set:
            return False
        if len(X) % 2:
            return False
        if not X:
            return True
        H = self.graph.subgraph(X)
        matching = nx.max_weight_matching(H, maxcardinality=True)
        return 2 * len(matching) == len(X)
    def separate(self, include: Iterable[Vertex], exclude: Iterable[Vertex]) -> bool:
        return matching_separate(self.vertices, self.edges, include, exclude).feasible
    def __call__(self, candidate: frozenset[Vertex]) -> bool:
        return self.member(candidate)


def matching_separate(vertices: Iterable[Vertex], edges: Iterable[Edge], S: Iterable[Vertex], T: Iterable[Vertex]) -> MatchingSepResult:
    """Algorithm 5 using maximum-weight matching in an arbitrary simple graph.

    Returns True iff there is a feasible induced vertex subset F with S⊆F and
    F∩T=∅. Edge weights are |e∩S|; the max score equals |S| exactly when all
    required vertices can be covered by one matching.
    """
    V, Vset, E = normalize_graph(vertices, edges)
    Sset, Tset = frozenset(S), frozenset(T)
    if not Sset <= Vset or not Tset <= Vset:
        raise ValueError("S and T must be subsets of the vertex set")
    if Sset & Tset:
        raise ValueError("S and T must be disjoint")
    H_vertices = Vset - Tset
    if not Sset <= H_vertices:
        return MatchingSepResult(False, -1, len(Sset), tuple(), frozenset(), frozenset())

    H = nx.Graph()
    H.add_nodes_from(H_vertices)
    for u, v in E:
        if u in H_vertices and v in H_vertices:
            H.add_edge(u, v, weight=int(u in Sset) + int(v in Sset))
    raw_matching = nx.max_weight_matching(H, maxcardinality=False, weight="weight")
    vertex_order = {v: i for i, v in enumerate(V)}
    matching: list[Edge] = []
    covered: set[Vertex] = set()
    score = 0
    for edge_pair in raw_matching:
        u, v = tuple(edge_pair)
        if vertex_order[u] > vertex_order[v]:
            u, v = v, u
        matching.append((u, v))
        if u in Sset: covered.add(u); score += 1
        if v in Sset: covered.add(v); score += 1
    feasible = score == len(Sset)
    witness = frozenset(v for edge in matching for v in edge) if feasible else frozenset()
    matching.sort(key=lambda edge: (vertex_order[edge[0]], vertex_order[edge[1]]))
    return MatchingSepResult(feasible, score, len(Sset), tuple(matching), frozenset(covered), witness)


def signed_greedy_matching_delta_matroid(
    vertices: Iterable[Vertex],
    edges: Iterable[Edge],
    weights: Mapping[Vertex, int | float],
) -> dict[str, Any]:
    """Run Algorithm 2 over the matching delta-matroid without enumerating sets."""
    from .algorithms import signed_greedy
    system = MatchingDeltaMatroid(vertices, edges)
    if set(weights) != system.vertex_set:
        raise ValueError("Weights must be defined exactly for every vertex")
    separator_trace: list[dict[str, Any]] = []
    vertex_order = {v: i for i, v in enumerate(system.vertices)}
    ordered = lambda values: sorted(values, key=vertex_order.__getitem__)
    def audited_separator(include, exclude):
        diagnostic = matching_separate(system.vertices, system.edges, include, exclude)
        query_index = len(separator_trace) + 1
        phase = "greedy_decision" if query_index <= len(system.vertices) else "final_feasibility_verification"
        separator_trace.append({
            "query_index": query_index, "phase": phase,
            "decision_index": query_index if phase == "greedy_decision" else None,
            "include": ordered(include), "exclude": ordered(exclude), "feasible": diagnostic.feasible,
            "score": diagnostic.score, "required_score": diagnostic.required_score,
            "matching": [list(edge) for edge in diagnostic.matching],
            "covered_required_vertices": ordered(diagnostic.covered_required_vertices),
            "witness_feasible_set": ordered(diagnostic.witness_feasible_set),
        })
        return diagnostic.feasible
    result = signed_greedy(system.vertices, weights, audited_separator, verify_result=True)
    member_verified = system.member(result.solution)
    if not member_verified:
        raise RuntimeError("Postcondition failed: returned set has no induced perfect matching")
    return {
        "solution": ordered(result.solution), "objective_value": result.objective_value,
        "negative_weight_set": ordered(result.negative_weight_set), "greedy_order": list(result.greedy_order),
        "accepted_twisted": ordered(result.accepted_twisted), "rejected_twisted": ordered(result.rejected_twisted),
        "separation_queries": result.separation_queries, "verification_queries": result.verification_queries,
        "member_verified": member_verified, "decisions": result.decisions, "separator_trace": separator_trace,
        "algorithm": "SignedGreedy + MatchingSep (NetworkX blossom backend)",
    }
