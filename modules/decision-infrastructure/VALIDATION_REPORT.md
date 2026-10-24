# Validation report — Delta-Infrastructure 0.7.0

## Scope of this revision

This revision adds a typed RunContext, immutable policy snapshots, shared budget accounting, inner-loop cooperative cancellation, append-only SQLite task checkpoints with sequence conflict protection, deterministic workflow fingerprinting, retry-safety checks, workflow CLI resume support, and explicit approval declarations for side-effecting capabilities.

## Previous validated baseline (0.6.0)

- **Workflow:** [Repository validation, run 40130032418](https://github.com/looloofy69-sketch/Ecosystems-loofy/actions/runs/40130032418)
- **Validated commit:** `9439c0ebcff2901a505adbdf0a6d0434b44c24ce`
- **Conclusion:** success
- **Tests:** 59 decision-module tests plus 4 repository tests; compilation and wheel build passed.

## Validation for 0.7.0

The 0.7.0 validation run must be recorded only after GitHub Actions finishes on the exact current commit. It must cover repository registry/link checks, root tests, package installation, compileall, the full decision-module tests, and wheel creation. The 0.6.0 result above does not validate these new changes.

## Known limitations

- Cancellation/deadline checks are cooperative; blocking code is not forcibly terminated.
- The task controller recovers only registered capabilities that explicitly declare retry safety and no external/write effects, plus known pure built-ins. A failed in-flight task may be re-executed if no success checkpoint was committed.
- Checkpoint history is an internal task ledger, not a checkpoint/resume protocol for external side effects or distributed transactions.
- RunContext currently propagates to algorithms but not to every library-internal operation; NetworkX blossom matching is checked before/after its non-interruptible call.
- Serialized byte limits do not replace process-level CPU/memory quotas.
- Portfolio state is not yet restart-resumable from per-turn checkpoints.
- Workflow approval flags do not provide authenticated identity, RBAC, or cryptographic audit.
- Matching optimum verification is bounded exhaustive verification for small instances.
- No production deployment, security audit, or SLO has been claimed.
