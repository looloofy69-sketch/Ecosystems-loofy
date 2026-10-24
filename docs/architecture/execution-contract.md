# Execution contract

This is the required semantic interface between the future execution controller and every capability.

## Shared run context
Each run carries:
- `run_id`, immutable policy snapshot, state snapshot and state version;
- monotonic deadline, cooperative cancellation token, central budget ledger;
- trace context, parent/child task lineage, and last durable checkpoint reference;
- authorization context for side effects; absent permission means deny.

## Capability contract
A capability declares ID/version, input and output schemas, resource profile, determinism/retry behavior, side-effect classification, and cancellation support. It receives read-only input and returns status, candidates, evidence, metrics, warnings, and the state version used. It may not write authoritative state directly.

## Enforcement points
1. **Preflight:** validate context/schema, capability eligibility, state version, task count, and serialized input size.
2. **Dispatch:** charge budgets centrally; propagate deadline/cancellation to nested tasks.
3. **Checkpoint:** check cancellation/deadline at bounded intervals and define what is durable.
4. **Result boundary:** enforce serialized output limits, schema, state-version match, and normalized error codes.
5. **Decision gate:** independently validate feasibility, invariants, and policy.
6. **Authorization:** require explicit grants for side effects.
7. **Commit:** compare expected state version atomically, persist transition, emit outcome.
8. **Recovery:** resume from last known-good checkpoint; never silently replay non-idempotent effects.

## Budget semantics
A child cannot reset its parent's deadline or recover consumed budget. Serialized-byte caps do not replace CPU/memory limits. The system must distinguish cooperative checks from hard timeouts.

## Cancellation and isolation
Cooperative cancellation is a request, not a kill switch. Blocking or untrusted work needs process isolation or another enforceable boundary for hard timeouts. Cancellation should propagate, stop new scheduling, and leave an auditable terminal result.

## Fail closed
Stop on unknown capabilities, invalid schemas/constraints, stale state, exhausted budgets, failed validation, or absent authorization. Retry only when declared safe.

## Current gap
The local v0.5.0 prototype includes standalone `ExecutionBudget` and `RuntimeGuard` primitives, but these are not integrated into every controller. The next milestone is controller-boundary enforcement, propagation, checkpointing, and end-to-end tests.
