# Adaptive orchestration

## Principle
Rotation, alternation, merging, and turn-taking are useful only when justified by the current state, constraints, and observed outcomes. Selection must be policy-controlled and auditable, not cosmetic round-robin scheduling.

## Selection inputs
- State shape: explicit family, oracle-backed, matrix/skew-symmetric, graph/matching, or mixed.
- Mathematical preconditions: parity, feasibility, oracle availability, field/weight domain.
- Candidate history: score, acceptance/rejection reason, cost, runtime, overlap/duplication.
- Run policy: allowed capabilities, risk, remaining budget, stop conditions.
- Evidence quality: independently checked correctness versus heuristic output.

## Scheduling cycle
1. Derive a normalized state descriptor.
2. Filter by mathematical preconditions and run policy.
3. Rank eligible capabilities by fit, expected cost, novelty, and evidence.
4. Select a capability; use alternation/weighted turns only as tie-breakers or starvation protection.
5. Execute under the shared context and budget.
6. Independently validate, merge compatible candidates, and deduplicate.
7. Update history and state descriptors using measured outcomes.
8. Continue only while progress criteria and budget permit.

Record state features, policy rule, capability version, scores, rejected alternatives, and switch rationale.

## Candidate merging
Merging must preserve provenance and be deterministic where possible. A merged candidate is a new candidate and must be revalidated; feasibility of inputs does not imply feasibility of their merge.

## Mathematical caution
- **StrongPath:** parity correction alone does not guarantee a valid delta-matroid lift; keep the verified-lift condition and safe fallback.
- **SchurPath:** each pivot needs a valid nonzero entry under the chosen field; surface singular/unsupported cases explicitly.
- **Matching separator:** exact verification was limited to small prototype instances; do not imply general scalability.
- **Local search/signed greedy:** document representation and oracle assumptions.
- Prior wins or scheduling heuristics never replace independent correctness checks.

## Metrics and stop rules
Track acceptance rate, validation failures, improvement per cost, budget use, starvation, redundant candidates, deadline overruns, and recovery frequency. Stop when no eligible capability remains, progress stalls under the declared rule, state changes unexpectedly, policy forbids work, or budget/deadline is exhausted.
