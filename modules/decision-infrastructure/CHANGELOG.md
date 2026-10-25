# Changelog

## 0.8.0 — Portfolio checkpoint and resume

- Added explicit strategy version and `retry_safe` metadata; retry safety defaults to false.
- Added append-only SQLite portfolio-turn checkpoints carrying committed state, turn history, scheduler cursors, strategy counters, disabled-strategy set, and run-context budget metadata.
- Added resume by run ID for portfolios whose strategies all explicitly declare retry safety.
- Bound recovery to a canonical fingerprint of the initial state, mode, failure policy, and versioned strategy catalog; changed catalogs are rejected.
- Added regression tests for resume behavior, changed strategy fingerprints, and rejection of unsafe strategies.
- Limits: retry safety is a trusted declaration, not a proof; crash recovery may replay the last turn from the previous checkpoint; arbitrary side effects and exactly-once execution are not supported.


## 0.7.0 — Shared execution context and workflow recovery

- Added a typed RunContext with an immutable JSON policy snapshot, trace/run identity, shared deadline/cancellation callback, and centrally accounted budget ledger.
- Propagated context through the workflow controller, portfolio controller, capability registry, and long-running algorithm/precondition checks.
- Added task/input/output consumption accounting and finite-value validation for resource budgets.
- Added append-only SQLite checkpoints with sequence compare-and-swap, canonical workflow fingerprints, and recovery that reuses successful outputs.
- Restricted workflow recovery to retry-safe capabilities and built-in pure handlers; side-effecting capabilities must declare approval requirements and unknown side-effect classes fail closed.
- Added CLI support for resuming from a checkpoint, plus regression tests for recovery, checkpoint conflicts, immutable policy snapshots, cancellation propagation, and approval boundaries.
- Remaining limits: cancellation is cooperative, SQLite checkpoints are not external transaction logs, approval is not authenticated identity, and hard timeouts require process isolation.

# Changelog

## 0.6.0 — Ecosystem integration

- Imported algorithms, capability registry, matrix and matching operations, workflow controller, adaptive portfolio controller, command-line interfaces, examples, and package tests.
- Integrated ExecutionBudget and RuntimeGuard at workflow task and portfolio turn boundaries.
- Added runtime integration tests for planned-work limits, cooperative cancellation, and output-size enforcement before commit.
- Added repository CI for package tests and wheel-build validation.
- Documented remaining limits: cooperative checks do not forcibly preempt blocked work; durable checkpoints, hard isolation, authenticated authorization, and production side-effect orchestration are not implemented.

## 0.5.0 — Local prototype (historical)

The original workbench version included runtime guard primitives, adaptive scheduling, candidate merging, feasibility checks, and SQLite history. Its 53-test result was for the separate local artifact before source import into this repository.
