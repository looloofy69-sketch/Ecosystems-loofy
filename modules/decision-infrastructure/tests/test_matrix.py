from __future__ import annotations
import itertools
import unittest
from delta_infra.matrix import PrimeField, RationalField, schur_path

def rank_mod_p(matrix, p):
    A=[[int(x)%p for x in row] for row in matrix]; n=len(A); rank=0
    for col in range(n):
        pivot=next((r for r in range(rank,n) if A[r][col]%p),None)
        if pivot is None: continue
        A[rank],A[pivot]=A[pivot],A[rank]; inverse=pow(A[rank][col],-1,p)
        A[rank]=[(x*inverse)%p for x in A[rank]]
        for r in range(n):
            if r!=rank and A[r][col]:
                factor=A[r][col]; A[r]=[(x-factor*y)%p for x,y in zip(A[r],A[rank])]
        rank+=1
        if rank==n: break
    return rank

class SchurPathTests(unittest.TestCase):
    def test_exhaustive_alternating_matrices_gf2(self):
        tested=0
        for n in (0,2,4):
            pairs=list(itertools.combinations(range(n),2))
            for bits in itertools.product((0,1),repeat=len(pairs)):
                A=[[0]*n for _ in range(n)]
                for (i,j),bit in zip(pairs,bits): A[i][j]=bit; A[j][i]=bit
                result=schur_path(A,range(n),field=PrimeField(2)); nonsingular=rank_mod_p(A,2)==n
                self.assertEqual(result.complete,nonsingular,A)
                if result.complete:
                    self.assertEqual(len(result.pairs)*2,n); self.assertEqual(len(result.prefix_sets),len(result.pairs))
                tested+=1
        self.assertEqual(tested,1+2+64)
    def test_exhaustive_4x4_alternating_matrices_gf3(self):
        n=4; pairs=list(itertools.combinations(range(n),2)); tested=0
        for entries in itertools.product((0,1,2),repeat=len(pairs)):
            A=[[0]*n for _ in range(n)]
            for (i,j),value in zip(pairs,entries): A[i][j]=value; A[j][i]=(-value)%3
            result=schur_path(A,range(n),field=PrimeField(3)); nonsingular=rank_mod_p(A,3)==n
            self.assertEqual(result.complete,nonsingular,A)
            if result.complete: self.assertEqual(len(result.pairs),2)
            tested+=1
        self.assertEqual(tested,729)
    def test_rational_field(self):
        A=[[0,2,1,0],[-2,0,0,1],[-1,0,0,3],[0,-1,-3,0]]
        result=schur_path(A,("a","b","c","d"),field=RationalField())
        self.assertTrue(result.complete); self.assertEqual(len(result.pairs),2); self.assertTrue(result.prefix_sets)
    def test_failure_preserves_certified_prefix(self):
        A=[[0,1,0,0],[-1,0,0,0],[0,0,0,0],[0,0,0,0]]
        result=schur_path(A,range(4),field=RationalField())
        self.assertFalse(result.complete); self.assertEqual(result.pairs,[(0,1)])
        self.assertEqual(result.prefix_sets,[frozenset({0,1})]); self.assertEqual(result.remaining_labels,(2,3))
    def test_rejects_non_alternating_matrix(self):
        with self.assertRaises(ValueError): schur_path([[1]],[0],field=RationalField())
        with self.assertRaises(ValueError): schur_path([[0,1],[1,0]],[0,1],field=RationalField())

if __name__ == "__main__": unittest.main()
