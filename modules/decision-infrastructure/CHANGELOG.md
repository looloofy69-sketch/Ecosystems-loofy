# Changelog

## 0.6.0 — Ecosystem integration

- Imported algorithms, capability registry, matrix and matching operations, workflow controller, adaptive portfolio controller, command-line interfaces, examples, and package tests.
- Integrated ExecutionBudget and RuntimeGuard at workflow task and portfolio turn boundaries.
- Added runtime integration tests for planned-work limits, cooperative cancellation, and output-size enforcement before commit.
- Added repository CI for package tests and wheel-build validation.
- Documented remaining limits: cooperative checks do not forcibly preempt blocked work; durable checkpoints, hard isolation, authenticated authorization, and production side-effect orchestration are not implemented.

## 0.5.0 — Local prototype (historical)

The original workbench version included runtime guard primitives, adaptive scheduling, candidate merging, feasibility checks, and SQLite history. Its 53-test result was for the separate local artifact before source import into this repository.
