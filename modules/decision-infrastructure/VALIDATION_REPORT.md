# Validation report — Delta-Infrastructure 0.8.0

## Verified CI result

- **Workflow:** [Repository validation, run 40150302288](https://github.com/looloofy69-sketch/Ecosystems-loofy/actions/runs/40150302288)
- **Validated code commit:** `b95724360eb3cf3983f38b3229e6c01accec88cc`
- **Conclusion:** success
- **Tests:** 73 decision-module tests and 4 repository tests passed.
- **Additional steps:** registry/Markdown consistency, editable package installation, package compilation, CLI smoke tests, and wheel build all passed.

This run validated the portfolio checkpoint/resume implementation and regression tests. The package metadata/documentation was then advanced to 0.8.0; CI is triggered again for those changes, and its latest result should be checked before claiming the final metadata commit passed.

## Scope

The package suite covers oracle-based algorithms, exhaustive small mathematical instances, matching separation/optimization against independent definitions, Schur-pivot exactness, portfolio scheduling and transition contracts, workflow validation/persistence, RunContext budget accounting and immutability, controller-boundary enforcement, workflow checkpoint sequence compare-and-swap, fingerprint mismatch rejection, retry-safe workflow recovery, and portfolio checkpoint/resume.

## Portfolio recovery semantics

Portfolio checkpoints are written before each turn and include committed state, prior turn records, scheduler cursors, strategy counters, disabled strategies, and RunContext metadata. Recovery is bound to the original initial state, requested mode, failure policy, portfolio ID, and versioned strategy descriptors.

Resume is refused unless every strategy explicitly declares `retry_safe=true`; the default is false. This is a trusted contract, not a formal proof. If the process fails after a turn commits but before the next checkpoint, recovery may replay that turn from the previous checkpoint. Exactly-once side effects are not guaranteed. Completed or failed portfolio runs are not resumable; turn-limit, cancellation, and budget-exceeded runs can be resumed when a valid checkpoint exists.

## Known limitations

- Cancellation/deadline checks are cooperative; blocking code is not forcibly terminated.
- The task controller recovers only registered capabilities that explicitly declare retry safety and no write/external effects, plus known pure built-ins. A failed in-flight task can be re-executed if no success checkpoint was committed.
- Checkpoint history is not an external transaction log or distributed transaction protocol.
- Some library-internal operations are not interruptible; NetworkX blossom matching is checked before and after its call.
- Serialized byte limits do not replace process-level CPU/memory quotas.
- Workflow approval flags do not provide authenticated identity, RBAC, or cryptographic audit.
- Matching optimum verification is bounded exhaustive verification for small instances.
- No production deployment, security audit, or SLO has been claimed.
