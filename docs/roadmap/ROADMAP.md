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
- [x] Preserve algorithm preconditions and mathematical limitations.
- [x] Run package tests and build a wheel in GitHub Actions.
- [x] Add CI coverage for repository checks, compilation, package tests, and wheel build.
- [x] Integrate cooperative guards into workflow-task and portfolio-turn controller boundaries.

Evidence for that baseline: [CI run 40130032418](https://github.com/looloofy69-sketch/Ecosystems-loofy/actions/runs/40130032418).

## Phase 2 — Shared run context and bounded execution

- [x] Introduce typed RunContext with run ID, immutable policy snapshot, state version, budget ledger, deadline/cancellation, and trace lineage.
- [x] Propagate context through workflow and portfolio controller boundaries, the capability registry, and supported algorithm loops.
- [x] Enforce plan/task counts, cumulative task-input bytes, and accumulated output-size limits.
- [x] Reject non-finite duration/resource policy values.
- [x] Test budget rejection, cancellation inside algorithm/precondition loops, and output rejection before state commit.
- [x] Document cooperative versus hard-timeout guarantees.
- [ ] Implement process isolation for blocking or untrusted capabilities where hard timeouts are required.
- [ ] Add CPU/memory accounting where required; serialized byte limits are not resource quotas.

## Phase 3 — Workflow checkpoints and action boundary

- [x] Add append-only SQLite task checkpoints with sequence compare-and-swap.
- [x] Bind checkpoints to a canonical workflow fingerprint and preserve completed outputs and budget state.
- [x] Add restart recovery tests: reuse successes, retry only retry-safe capabilities, reject changed workflow definitions, and prevent retry of unsafe capabilities.
- [x] Expose recovery via workflow CLI using the same workflow JSON and database with --resume RUN_ID.
- [x] Fail closed on unknown side-effect classifications; require an approval declaration for write/external capabilities.
- [ ] Add authenticated approval/authorization, RBAC, and an auditable policy decision record.
- [ ] Bind state-changing commits to an authoritative state version using atomic compare-and-swap.
- [ ] Add checkpoint/resume for adaptive portfolio turns.
- [ ] Define idempotency/reconciliation for external operations; SQLite checkpoints do not provide exactly-once side effects.

## Phase 4 — Adaptive policy and evaluation evidence

- [ ] Version state descriptors and mathematical capability preconditions.
- [ ] Record policy reasons, score components, rejected alternatives, and switch rationale for each strategy choice.
- [ ] Add validated candidate merging/deduplication with provenance.
- [ ] Build reproducible evaluations for representative state families, failures, and edge cases.
- [ ] Report quality, cost, strategy starvation, and recovery metrics with methodology.

## Phase 5 — Hardening and release

- [ ] Select and commit a license.
- [ ] Establish a threat model, dependency/security review, operations runbook, telemetry-retention policy, compatibility policy, and rollback.
- [ ] Define a bounded production use case and SLOs before production-readiness promotion.
- [ ] Tie each release's tests, wheel, and checksums to an exact commit.

Do not add algorithms just to increase count. Add a capability when its preconditions, measured benefit, validation, and safe fallback are defined.
