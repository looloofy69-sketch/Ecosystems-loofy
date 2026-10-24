from __future__ import annotations
import itertools
import unittest
from delta_infra.algorithms import local_search, monotone_path, signed_greedy, strong_path_explicit, strong_path_oracle, parity_correcting_lift
from delta_infra.oracles import ExplicitFamilyOracle, all_subsets

def is_delta_matroid(family):
    for X in family:
        for Y in family:
            delta=X^Y
            for x in delta:
                if not any((X^frozenset((x,y))) in family for y in delta): return False
    return bool(family)

def all_delta_matroids(E):
    subsets=all_subsets(E)
    for mask in range(1,1<<len(subsets)):
        family=frozenset(subsets[i] for i in range(len(subsets)) if mask&(1<<i))
        if is_delta_matroid(family): yield family

class OracleTests(unittest.TestCase):
    def test_separation_and_twist_contract(self):
        family={frozenset(),frozenset({0,1}),frozenset({1,2})}
        oracle=ExplicitFamilyOracle((0,1,2),family)
        self.assertTrue(oracle.separate({0},{2})); self.assertFalse(oracle.separate({0},{1})); self.assertTrue(oracle.is_delta_matroid())
    def test_algorithms_1_and_2_exhaustive_on_three_elements(self):
        E=(0,1,2); weight_vectors=list(itertools.product((-1,0,1),repeat=len(E))); systems=0
        for family in all_delta_matroids(E):
            oracle=ExplicitFamilyOracle(E,family); systems+=1
            for values in weight_vectors:
                weights=dict(zip(E,values)); optimum=max(sum(weights[e] for e in X) for X in family)
                greedy=signed_greedy(E,weights,oracle.separate)
                self.assertEqual(greedy.objective_value,optimum); self.assertTrue(oracle.member(greedy.solution)); self.assertTrue(greedy.verified_feasible)
                for start in family:
                    local=local_search(E,weights,start,oracle.member)
                    self.assertTrue(local.converged); self.assertEqual(local.objective_value,optimum); self.assertTrue(all(X in family for X in local.history))
        self.assertEqual(systems,155)
    def test_local_search_limit_is_explicitly_nonconverged(self):
        family={frozenset(),frozenset({0,1})}; oracle=ExplicitFamilyOracle((0,1),family)
        result=local_search((0,1),{0:1,1:1},set(),oracle.member,max_improving_moves=0)
        self.assertFalse(result.converged); self.assertEqual(result.solution,frozenset()); self.assertEqual(result.pending_improvement,frozenset({0,1}))
    def test_monotone_path_requires_declared_even_contract(self):
        family={X for X in all_subsets((0,1,2,3)) if len(X)%2==0}; oracle=ExplicitFamilyOracle((0,1,2,3),family); oracle.verify_even_delta_matroid()
        with self.assertRaises(ValueError): monotone_path((0,1,2,3),set(),{0,1,2,3},oracle.member)
        result=monotone_path((0,1,2,3),set(),{0,1,2,3},oracle.member,assume_even_delta_matroid=True)
        self.assertEqual(result.path[0],frozenset()); self.assertEqual(result.path[-1],frozenset({0,1,2,3}))
        self.assertEqual(result.steps,2); self.assertLessEqual(result.exchange_membership_queries,4)
    def test_monotone_path_exhaustive_on_even_delta_matroids_of_order_four(self):
        E=(0,1,2,3); systems=endpoint_pairs=0
        for family in all_delta_matroids(E):
            if len({len(F)%2 for F in family})!=1: continue
            oracle=ExplicitFamilyOracle(E,family); oracle.verify_even_delta_matroid(); systems+=1
            for A in family:
                for B in family:
                    result=monotone_path(E,A,B,oracle.member,assume_even_delta_matroid=True)
                    self.assertEqual(result.path[0],A); self.assertEqual(result.path[-1],B)
                    self.assertTrue(all(X in family for X in result.path))
                    distances=[len(X^B) for X in result.path]
                    self.assertTrue(all(distances[i+1]==distances[i]-2 for i in range(len(distances)-1)))
                    h=len(A^B); self.assertEqual(result.steps,h//2); self.assertLessEqual(result.exchange_membership_queries,(h//2)**2); endpoint_pairs+=1
        self.assertEqual(systems,294); self.assertEqual(endpoint_pairs,5616)
    def test_monotone_path_supports_none_as_a_ground_element(self):
        E=(1,None); family={frozenset(),frozenset(E)}; oracle=ExplicitFamilyOracle(E,family); oracle.verify_even_delta_matroid()
        result=monotone_path(E,set(),set(E),oracle.member,assume_even_delta_matroid=True)
        self.assertEqual(result.path[-1],frozenset(E)); self.assertEqual(result.steps,1)
    def test_parity_lift_diagnostic_exhaustive_on_three_elements(self):
        E=(0,1,2); valid=invalid=0
        for family in all_delta_matroids(E):
            lifted={parity_correcting_lift(F) for F in family}
            if is_delta_matroid(lifted): valid+=1
            else: invalid+=1
        self.assertEqual(valid,147); self.assertEqual(invalid,8)
    def test_strong_path_oracle_requires_external_lift_contract(self):
        original_family={frozenset(),frozenset({0}),frozenset({1}),frozenset({0,1})}
        lifted_family={frozenset(),frozenset({0,"#"}),frozenset({1,"#"}),frozenset({0,1})}
        original_member=lambda X:frozenset(X) in original_family
        lifted_member=lambda X:frozenset(X) in lifted_family
        lift=lambda X:frozenset(X) if len(X)%2==0 else frozenset(X)|{"#"}
        project=lambda X:frozenset(X)-{"#"}
        args=((0,1,"#"),set(),{0},lift,project,lifted_member,original_member)
        with self.assertRaisesRegex(ValueError,"externally established"): strong_path_oracle(*args)
        result=strong_path_oracle(*args,lift_exchange_guaranteed=True)
        self.assertEqual(result.path[0],frozenset()); self.assertEqual(result.path[-1],frozenset({0}))
        self.assertEqual(result.contract_basis,"externally_guaranteed_even_delta_matroid_lift")
    def test_strong_path_validates_lift(self):
        E=(0,1,2); free_family=all_subsets(E)
        result=strong_path_explicit(E,free_family,set(),set(E))
        self.assertTrue(result.lift_validated); self.assertEqual(result.path[0],frozenset()); self.assertEqual(result.path[-1],frozenset(E)); self.assertTrue(all(X in free_family for X in result.path))
        custom_dummy=strong_path_explicit(E,free_family,set(),set(E),dummy="DUMMY")
        self.assertEqual(custom_dummy.path[0],frozenset()); self.assertEqual(custom_dummy.path[-1],frozenset(E))
        invalid_lift_family={frozenset(),frozenset({0}),frozenset({0,1}),frozenset({0,2}),frozenset({1,2})}
        with self.assertRaisesRegex(ValueError,"lifted family violates symmetric exchange"):
            strong_path_explicit((0,1,2),invalid_lift_family,set(),{0,1})

if __name__ == "__main__": unittest.main()
