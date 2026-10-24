# Execution contract

This document separates the desired control-plane contract from enforcement present in the current v0.6.0 module.

## Target shared run context

The intended typed RunContext carries:
- run ID, immutable policy snapshot, input state snapshot, and state version;
- monotonic deadline, cooperative cancellation signal, and central budget ledger;
- trace context and parent/child task lineage;
- last durable checkpoint reference;
- explicit authorization context for side effects, with absent permission meaning deny.

**Status:** the current module has ExecutionBudget and RuntimeGuard primitives and accepts a budget/cancellation callback at the workflow and portfolio controller boundaries. The full typed shared RunContext is not yet implemented, and the current cancellation signal is not propagated into every inner algorithm loop.

## Capability contract

A capability should declare ID/version, input/output schemas, resource profile, determinism/retry behavior, side-effect classification, and cancellation support. It receives read-only input and returns status, candidates, evidence, metrics, warnings, and the state version used. It must not write authoritative state directly.

## Enforcement points

1. **Preflight:** current code bounds the declared task/turn plan and serialized workflow/initial state.
2. **Dispatch:** current code checks the guard before dispatch and sizes resolved input. Central accounting of every child operation is still incomplete.
3. **Checkpoint:** current code checks cancellation/deadline at controller boundaries and immediately after a handler/strategy returns. Long inner loops are not automatically interrupted.
4. **Result boundary:** current code validates JSON-safe output, caps serialized output and accumulated workflow outputs, and rejects an oversized portfolio candidate before state commit.
5. **Decision gate:** domain-specific verification exists for selected small-instance examples. A general independent validator for arbitrary capability candidates remains future work.
6. **Authorization:** workflow approval flags are only a declarative gate, not authenticated identity or an authorization service. A production authorization policy remains future work.
7. **Commit:** the portfolio controller preserves its last committed state on a guard failure. Workflow results are recorded after the run; atomic compare-and-swap against an authoritative external state version is not implemented.
8. **Recovery:** SQLite run history is durable history only. Checkpoint resume and replay-safe external side effects are not implemented.

## Budget semantics

The current ExecutionBudget includes maximum declared task/turn count, serialized input/output bytes, and duration. The task controller applies max_tasks to the planned DAG; the portfolio controller applies it to max_turns. These are plan-size bounds, not a decrementing CPU/task-cost ledger. Serialized-byte caps do not replace CPU or memory quotas. Deadline checks use monotonic time.

## Cancellation and isolation

Cooperative cancellation is a request, not a kill switch. Current controllers detect it before work and after registered handlers/strategies return. A blocking capability cannot be interrupted during its call by this mechanism. A process-isolation boundary or another enforceable runtime mechanism is required for hard timeout guarantees.

## Fail closed

Unknown capabilities, invalid schemas/constraints, oversized inputs/outputs, exhausted budgets, failed checks, stale state, or absent authorization should stop execution. The current module implements many of these checks but not the entire production policy boundary.

## Validation status

The imported module's package tests and wheel build passed in [GitHub Actions run 40130032418](https://github.com/looloofy69-sketch/Ecosystems-loofy/actions/runs/40130032418), validated at commit 9439c0ebcff2901a505adbdf0a6d0434b44c24ce. The next runtime milestone is a typed shared context and propagation through all capability boundaries, followed by checkpoint/recovery and action authorization.
