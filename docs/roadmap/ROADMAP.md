# Roadmap

Completion means evidence is present in the repository, not that a status label changed.

## Phase 0 — Foundation

- [x] Initialize structure, architecture, governance, and roadmap.
- [x] Add machine-readable registry and component schema.
- [x] Add registry/Markdown validation and CI.
- [x] Record prototype status and limitations.
- [ ] Select a license before a release intended for reuse.

## Phase 1 — Import and validate the decision module

- [x] Import the v0.6.0 module source, tests, package metadata, examples, changelog, and architecture notes.
- [x] Preserve the algorithm preconditions and documented mathematical limitations.
- [x] Run the package tests and build a wheel in GitHub Actions.
- [x] Add CI coverage for repository checks, package compilation, package tests, and wheel build.
- [x] Integrate cooperative guards into workflow-task and portfolio-turn controller boundaries.

Evidence: [successful GitHub Actions run 40130032418](https://github.com/looloofy69-sketch/Ecosystems-loofy/actions/runs/40130032418), checked at commit 9439c0ebcff2901a505adbdf0a6d0434b44c24ce.

## Phase 2 — Unified run context and stronger runtime enforcement

- [ ] Introduce a typed RunContext carrying run ID, immutable policy snapshot, state version, budget ledger, deadline, cancellation, and trace lineage.
- [ ] Propagate the shared context into capability handlers and any nested work.
- [x] Bound planned task/turn counts and serialized input/output at controller boundaries.
- [x] Test budget rejection, cancellation, and output-bound enforcement before accepting task output or portfolio state.
- [x] Document cooperative versus hard-timeout guarantees.
- [ ] Decide and implement process isolation for blocking or untrusted capabilities where hard timeout guarantees are required.
- [ ] Add CPU/memory accounting where required; serialized byte limits are not resource quotas.

## Phase 3 — State, checkpoint, and action boundary

- [ ] Add versioned durable checkpoints and restart/recovery tests.
- [ ] Separate candidate proposal, independent validation, authorization, and commit in typed APIs.
- [ ] Add a deny-by-default authorization policy with authenticated identity for state-changing external operations.
- [ ] Define idempotency/reconciliation for non-idempotent effects and make retries explicit.
- [ ] Verify stale state cannot commit after the authoritative state version changes.

## Phase 4 — Adaptive policy and evidence

- [ ] Define and version state descriptors and capability precondition contracts.
- [ ] Record policy reasons, scores, rejected alternatives, and switch rationale for every strategy choice.
- [ ] Add validated candidate merge/deduplication with provenance.
- [ ] Build reproducible evaluations for representative state families, failures, and edge cases.
- [ ] Report quality, cost, starvation, and recovery metrics with methodology.

## Phase 5 — Hardening and release

- [ ] Select and commit a license.
- [ ] Establish a threat model, dependency/security review, operations runbook, telemetry-retention policy, compatibility policy, and rollback.
- [ ] Define a bounded production use case and SLOs before production-readiness promotion.
- [ ] Keep CI evidence tied to an exact commit and release artifact checksum.

Do not add algorithms just to increase count. Add a capability when its preconditions, measured benefit, validation, and safe fallback are defined.
