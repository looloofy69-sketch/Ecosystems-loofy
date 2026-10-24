# Delta-Infrastructure Decision Module

**Version:** 0.7.0  
**Status:** integrated module; not production-ready.

This package provides deterministic delta-matroid algorithms, a capability registry, a declarative workflow controller, a state-aware strategy portfolio, a SQLite run ledger, and a shared RunContext with budget accounting, cooperative runtime guard enforcement, and durable task-level checkpoints for retry-safe workflow recovery.

## Included algorithms

| Algorithm | Implementation |
|---|---|
| LocalSearch | Membership-oracle local improvement through one/two-element flips |
| SignedGreedy | Twisted separation-oracle optimization |
| MonotonePath | Pair exchange for even delta-matroids; precondition must be established |
| StrongPath | Explicit-family mode verifies lifted exchange/parity conditions; oracle mode requires an external contract |
| SchurPath | Alternating matrix pivots over rationals or prime fields |
| MatchingSep | Maximum-weight matching for matching-delta-matroid separation |
| Matching SignedGreedy | Optimization using NetworkX matching |

The registry exposes seven JSON-callable capabilities. Workflow documents may invoke only registered capabilities and allow-listed built-ins; they cannot load Python modules, execute shell commands, or evaluate expressions.

## Runtime integration in v0.7.0

TaskExecutionController and PortfolioController accept an ExecutionBudget and cooperative cancellation callback. Controller-boundary checks cover planned task/turn counts, serialized input sizes, deadline/cancellation checkpoints, and output-size checks before task output or portfolio state is committed. Runtime stop outcomes are recorded as cancelled or budget-exceeded where execution has begun. The immutable policy snapshot and budget ledger travel with the RunContext; deterministic handlers receive checkpoints inside longer algorithm loops.

Checkpoints are append-only and sequence-checked in SQLite. Resume requires the same canonical workflow definition and database, rejects completed runs, and permits retry only for capabilities declared side-effect-free/read-only and retry-safe. To resume, supply the same workflow file and `--db` path with `--resume RUN_ID`.\n\nImportant limits remain:
- Preflight rejection happens before a run record exists.
- Runtime checks are cooperative. They do not interrupt a blocking capability or strategy.
- Serialized byte limits do not enforce CPU or memory usage.
- SQLite history is not transactional side-effect management; replay/resume and exactly-once semantics are not provided.
- Workflow input/output history can contain sensitive data; do not submit secrets.
- The portfolio is an internal strategy scheduler, not a general autonomous-agent runtime.

## Install and test

Requires Python 3.10+ and NetworkX 3.x.

    python -m pip install -e .
    python -m unittest discover -s tests -v
    python -m delta_infra.cli --list-capabilities --pretty
    python -m delta_infra.workflow_cli examples/workflows/internal_matching_validation.json --pretty
    python -m delta_infra.portfolio_cli examples/portfolio_adaptive_instance.json --mode auto --pretty

See ARCHITECTURE.md, VALIDATION_REPORT.md, CHANGELOG.md, and the root roadmap.

## Correctness boundaries

- Explicit feasible-family routines validate axioms only on the supplied finite family.
- Oracle-only path routines require externally established mathematical preconditions.
- Parity correction is not universally a valid delta-matroid lift; StrongPath must reject failed lift checks.
- The independent matching optimum verifier uses bounded exhaustive subset enumeration and defaults to at most 12 vertices; it is for small-instance verification, not large-scale solving.
