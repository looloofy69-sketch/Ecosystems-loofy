# Decision-infrastructure module: import plan

**Status: prototype artifact — not imported into this repository.**

The local v0.5.0 workbench contains delta-matroid local search, signed greedy selection, path routines, skew-matrix Schur pivots, matching separation, adaptive portfolio scheduling, candidate merging, feasibility checks, SQLite history, examples, and standalone runtime guard primitives.

The local suite reported 53 passing tests on 2026-10-24. The source and tests are not tracked here. That result is not an ecosystem CI result and does not prove runtime integration.

## Import procedure
1. Import the exact v0.5.0 source, tests, package metadata, examples, and history.
2. Re-run the complete suite from the committed revision in CI and reconcile differences.
3. Add package-build and dependency checks after an explicit license review.
4. Integrate guards into task and portfolio controller boundaries.
5. Keep StrongPath's verified-lift condition; parity correction alone is not a general correctness guarantee.
6. Preserve the small-instance scope of exact matching verification.
7. Promote the registry status only after the [lifecycle gates](../../docs/governance/component-lifecycle.md) pass.

## Adapter contract
Accept shared run context and immutable input state; return typed candidate(s), evidence, resource metrics, state version, and normalized status. The adapter may not commit authoritative state or trigger side effects directly.

## Acceptance criteria
- Imported tests run in CI from this repository revision.
- Preconditions and limitations are documented.
- Controller boundaries enforce budget, deadline, cancellation, and output limits.
- Candidate feasibility is independently validated.
- Failure, cancellation, unsupported inputs, and timeouts are explicit.
- Provenance and checkpoint semantics are preserved.

Related: [system model](../../docs/architecture/system-model.md), [execution contract](../../docs/architecture/execution-contract.md), [adaptive orchestration](../../docs/architecture/adaptive-orchestration.md).
