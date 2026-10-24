# System model

## Purpose
An internal control plane coordinates decision components under shared state, policy, budgets, validation, and authorization. Components are replaceable capabilities, not independent authorities over the system.

## Logical layers
1. **Intent and constraints** — requested outcome, acceptance criteria, permitted side effects.
2. **Run context** — run ID, state version, policy snapshot, deadline, cancellation signal, budget ledger, trace IDs, checkpoints.
3. **Planner/portfolio selector** — proposes bounded strategies based on state shape and declared capability preconditions.
4. **Capability adapters** — execute against immutable inputs and return typed candidates with evidence.
5. **Validation gate** — checks schemas, feasibility, invariants, objective values, and policy independently of the proposer.
6. **Authorization boundary** — controls whether a validated candidate may cause a side effect.
7. **State store/history** — persists accepted checkpoints and outcomes with versions and provenance.
8. **Observability** — records strategy choice, timings, budget use, validation, and failure reasons.

## Trust boundaries
- Treat all capability output as untrusted until validated.
- Algorithms must not mutate authoritative state directly; they return candidates and evidence.
- Bind state-changing operations to an expected state version.
- Distinguish proposal, validation, authorization, and commit in types and logs.
- Do not store secrets in the registry or examples.
- Future model/plugin capabilities must pass the same validation and authorization gates as deterministic code.

## Run lifecycle
`created → preflighted → planned → executing → candidate-produced → validating → awaiting-authorization (when needed) → committed`

Terminal outcomes include `cancelled`, `budget-exceeded`, `deadline-exceeded`, `validation-failed`, `authorization-denied`, and `failed`. Preserve the last valid checkpoint and a structured reason. Retrying a side effect requires idempotency or explicit reconciliation.

## Invariants
- One effective run context per run; child tasks get a bounded projection.
- Every capability declares schemas, budget behavior, cancellation semantics, side effects, and evidence.
- A strategy switch records the state features and policy rule behind it.
- Every irreversible action passes through authorization.
- Registry status is metadata, not runtime permission.

This is the target architecture, not a claim that the production runtime is implemented. See the registry and roadmap for maturity.
