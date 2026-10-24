# Execution contract

This document separates the target control-plane contract from enforcement present in the v0.7.0 module.

## Shared run context

The current typed RunContext carries run ID, state version, an immutable JSON policy snapshot, trace ID, parent-run ID, a monotonic deadline, cooperative cancellation, a central BudgetLedger, and the configured ExecutionBudget. Child algorithms invoked through the capability registry receive the same context. The full context is process-local; monotonic timestamps are not persisted directly.

## Capability contract

Capabilities declare ID/version, input keys and preconditions, side-effect classification, and retry safety. The current default algorithms declare side-effect class "none" and retry_safe=True. Custom capabilities default to unknown effects and unsafe retries unless their registration explicitly declares otherwise. A workflow refuses unknown side-effect classifications; write/external capabilities must have requires_approval=true, and the task must also be explicitly approved at execution.

A capability should additionally declare formal input/output schemas, resource profiles, retry semantics, and any side effects. Algorithm proposals must not mutate authoritative state directly.

## Controller enforcement points

1. **Preflight:** validate workflow, capability IDs, required approval declaration, task-plan count, and serialized workflow size before dispatch.
2. **Dispatch:** charge task attempts and serialized task-input bytes to the shared ledger.
3. **Checkpoints:** pass the context to context-aware handlers and check cancellation/deadline in supported search, exchange, pivot, and bounded verification loops. Library calls without callback support may only be checked before and after.
4. **Result boundary:** require JSON-safe finite output and bound serialized accumulated workflow output before committing the task output. Portfolio state proposals are bounded before accepting the next state.
5. **Independent validation:** selected algorithm workflows use independent feasibility/objective checks; there is not yet a universal validator for arbitrary candidate types.
6. **Approval:** write/external capabilities must declare an approval requirement, and the caller must explicitly approve the task ID. This is a declarative gate, not authenticated identity, RBAC, or a full authorization service.
7. **Commit:** outputs and portfolio states are accepted only after post-handler guard checks. A controller-level state version is available in RunContext, but atomic compare-and-swap against an authoritative application state store is not implemented.
8. **Recovery:** WorkflowRunStore writes append-only SQLite checkpoints with sequence compare-and-swap after each task attempt. A canonical workflow fingerprint prevents resuming against changed workflow JSON. Resume reuses successful task outputs and retries only capabilities declared side-effect-free/read-only and retry-safe, plus known pure built-ins.

## Budget semantics

ExecutionBudget defines maximum planned/started tasks, serialized input bytes, serialized output bytes, and duration. The ledger accounts task attempts and cumulative serialized task inputs. Output-size checks apply to the prospective accumulated workflow outputs. These are plan and interface bounds, not a CPU-time or memory ledger. Serialized byte limits do not replace OS/process quotas.

The stored elapsed duration is used to reconstruct the remaining monotonic deadline after a restart. Time spent stopped between process launches is not counted as active execution time.

## Cancellation and isolation

Cooperative cancellation is a request, not a kill switch. Context is checked at controller boundaries and within implemented algorithm loops. NetworkX blossom matching is not internally interruptible via this callback, so the guard checks before and after that call. Hard timeout guarantees for blocking/untrusted work require process isolation or another enforceable execution boundary.

## Checkpoint and retry contract

The checkpoint table is append-only; each write requires the expected previous sequence and is rejected on conflict. Checkpoints contain workflow fingerprint, completed task IDs, committed outputs, task attempts, and RunContext budget/trace metadata. Resume requires the same workflow ID/fingerprint and database file. Successfully completed runs cannot be resumed. Side-effectful/unknown capabilities cannot be retried as part of recovery.

These checkpoints recover declarative workflow execution, not external transactions or arbitrary portfolio state. A crash before a successful-task checkpoint can cause that safe task to run again. No exactly-once side-effect guarantee is claimed.

## Remaining gaps

- Authenticated approval and a deny-by-default application authorization service.
- Atomic commit against a versioned authoritative state store.
- Checkpoint/resume for portfolio controller turns.
- Process isolation and resource enforcement for non-cooperative capabilities.
- External-operation idempotency/reconciliation, recovery runbooks, and SLOs.

## Validation

The 0.7.0 CI run must be recorded against the exact post-change commit in the validation report; the previous 0.6.0 run does not validate this implementation.
