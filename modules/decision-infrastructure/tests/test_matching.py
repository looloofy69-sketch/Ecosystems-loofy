from __future__ import annotations
import itertools
import unittest
from delta_infra.matching import MatchingDeltaMatroid, matching_separate, signed_greedy_matching_delta_matroid
from delta_infra.oracles import all_subsets

def perfect_matching_exists(X, edges):
    X = frozenset(X)
    if not X: return True
    if len(X) % 2: return False
    v = min(X, key=repr)
    for a, b in edges:
        if a == v and b in X:
            if perfect_matching_exists(X - {a, b}, edges): return True
        elif b == v and a in X:
            if perfect_matching_exists(X - {a, b}, edges): return True
    return False

def direct_sep(V, edges, S, T):
    allowed = set(V) - set(T)
    for F in all_subsets(allowed):
        if set(S) <= F and perfect_matching_exists(F, edges): return True
    return False

class MatchingTests(unittest.TestCase):
    def test_known_instance_and_registry_facing_result(self):
        V = ("1", "2", "3", "4"); E = (("1", "2"), ("2", "3"), ("3", "4")); W = {"1": 5, "2": -3, "3": 4, "4": 2}
        result = signed_greedy_matching_delta_matroid(V, E, W)
        self.assertEqual(set(result["solution"]), set(V)); self.assertEqual(result["objective_value"], 8); self.assertTrue(result["member_verified"])
    def test_matching_separator_against_direct_definition(self):
        checked = 0
        for n in range(1, 5):
            V = tuple(range(n)); possible_edges = list(itertools.combinations(V, 2))
            for bits in itertools.product((0, 1), repeat=len(possible_edges)):
                E = tuple(e for e, bit in zip(possible_edges, bits) if bit)
                for state in itertools.product((0, 1, 2), repeat=n):
                    S = {V[i] for i,x in enumerate(state) if x == 1}; T = {V[i] for i,x in enumerate(state) if x == 2}
                    result = matching_separate(V, E, S, T)
                    self.assertEqual(result.feasible, direct_sep(V,E,S,T), (V,E,S,T))
                    self.assertEqual(result.score, len(result.covered_required_vertices)); checked += 1
        self.assertEqual(checked, 5421)
    def test_signed_greedy_exhaustive_on_all_graphs_up_to_four_vertices(self):
        checked = 0
        for n in range(1,5):
            V=tuple(range(n)); potential=list(itertools.combinations(V,2))
            for bits in itertools.product((0,1), repeat=len(potential)):
                edges=tuple(e for e,b in zip(potential,bits) if b); system=MatchingDeltaMatroid(V,edges)
                feasible_sets=[F for F in all_subsets(V) if system.member(F)]
                for weights_tuple in itertools.product((-2,0,2), repeat=n):
                    weights=dict(zip(V,weights_tuple)); result=signed_greedy_matching_delta_matroid(V,edges,weights)
                    optimum=max(sum(weights[x] for x in F) for F in feasible_sets)
                    self.assertEqual(result["objective_value"], optimum, (V,edges,weights))
                    self.assertTrue(system.member(result["solution"])); checked += 1
        self.assertEqual(checked, 5421)
    def test_bad_graph_inputs_are_rejected(self):
        with self.assertRaises(ValueError): MatchingDeltaMatroid((1,2), ((1,3),))
        with self.assertRaises(ValueError): MatchingDeltaMatroid((1,2), ((1,1),))

if __name__ == "__main__": unittest.main()
