# Decision module architecture

## Components

- Oracle layer: membership/separation protocols; explicit-family oracle for bounded validation; twist adapter for signed greedy.
- Algorithm layer: local search, signed greedy, monotone path, validated StrongPath, Schur pivot sequence, and matching-separator solver.
- Capability registry: stable names, input keys, preconditions, and handlers.
- Workflow controller: validates a declarative DAG, resolves data-only references to declared dependencies, enforces approval gates, executes in topological order, and records runs to SQLite.
- Portfolio controller: schedules trusted in-process strategies using declared eligibility predicates, scheduler modes, transition contracts, and candidate merging.
- Runtime guard: task/turn plan bounds, cooperative deadline/cancellation checkpoints, serialized input/output bounds.
- Run ledger: SQLite persistence of structured run records.

## Trust and state-transition model

Algorithm handlers propose candidates; independent checks establish feasibility/objective correctness where possible; the controller owns state transitions. Workflow built-ins are allow-listed in Python. Portfolio strategies are registered trusted functions; portfolio JSON does not define executable code.

## Runtime enforcement

The workflow controller preflights the task count and serialized workflow definition. Before dispatch it checks the guard and resolved inputs; after the handler returns it checks cancellation/deadline and prospective accumulated output size before adding the output to the run result.

The portfolio controller preflights the maximum turn count and initial state. Each turn checks the guard before strategy invocation, after it returns, and on the proposed candidate before accepting new state. If cancellation is observed after a strategy returns, the proposed candidate is rejected and the last committed state is preserved.

These are cooperative in-process checks, not an OS-level kill mechanism. A blocking strategy cannot be interrupted until it returns unless a separate process boundary is used. The task/turn budget counts the declared plan as an upper bound and is not CPU-time metering. The shared typed RunContext and inner-loop cancellation propagation are not yet implemented.

## Durability and authorization gaps

Completed run records are stored in SQLite. This is history, not a checkpoint/recovery protocol: the controller does not restore and resume partially executed workflows, coordinate external transactions, guarantee exactly-once side effects, or provide cross-process lease management. Approval flags are workflow gates, not authenticated identities or an authorization service.

## Mathematical preconditions

- Algorithms 1 and 2 rely on delta-matroid properties and additive finite weights.
- Algorithm 3 requires a verified even-delta-matroid precondition.
- Algorithm 3' validates explicit lifts or requires a separate oracle-only lift contract.
- SchurPath requires an alternating matrix over a supported exact field.
- MatchingSep operates on finite simple undirected graphs. Exact optimum checking is only for small instances.

## Validation

The imported source, tests, package compilation, and wheel build passed in [GitHub Actions run 40130032418](https://github.com/looloofy69-sketch/Ecosystems-loofy/actions/runs/40130032418), validated at commit 9439c0ebcff2901a505adbdf0a6d0434b44c24ce. Production readiness remains unclaimed until isolation, durable checkpoints/recovery, authorization, security, performance, and operational gates pass.
