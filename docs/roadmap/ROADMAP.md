# Roadmap

Completion means evidence is present in the repository, not that a status label changed.

## Phase 0 — Foundation
- [x] Initialize structure, architecture, governance, and roadmap.
- [x] Add machine-readable registry and component schema.
- [x] Add registry/Markdown validation and CI.
- [x] Record prototype status and limitations.
- [ ] Select a license before a release intended for reuse.

## Phase 1 — Import the prototype
- [ ] Import exact v0.5.0 source and tests into `modules/decision-infrastructure/` or an approved package layout.
- [ ] Preserve provenance, changelog, docs, examples, and tests.
- [ ] Run tests from the committed revision in CI and reconcile any differences.
- [ ] Add package/build/dependency checks after license review.

## Phase 2 — Unified runtime enforcement
- [ ] Define typed `RunContext`, capability protocol, result/error types.
- [ ] Integrate guards into task and portfolio controllers.
- [ ] Propagate deadline, cancellation, trace, and budgets to nested work.
- [ ] Bound serialized input/output and account centrally.
- [ ] Test enforcement at controller level.
- [ ] Document cooperative versus hard timeout guarantees.

## Phase 3 — State and action boundary
- [ ] Add versioned checkpoints and restart/recovery tests.
- [ ] Separate propose, validate, authorize, and commit.
- [ ] Add deny-by-default side-effect policy.
- [ ] Define idempotency/reconciliation for non-idempotent operations.

## Phase 4 — Adaptive policy and evidence
- [ ] Define state descriptor and capability precondition contracts.
- [ ] Record selection rationale and rejected alternatives.
- [ ] Add validated merging/deduplication and stop rules.
- [ ] Build reproducible evaluations for representative state families/failures.
- [ ] Report quality, cost, starvation, and recovery metrics with methodology.

## Phase 5 — Hardening
- [ ] Decide isolation strategy for untrusted/non-cooperative capabilities.
- [ ] Establish threat model, runbook, telemetry retention, compatibility, rollback.
- [ ] Define bounded production scope and SLOs before promotion.

Do not add algorithms just to increase count. Add a capability when its preconditions, measured benefit, validation, and safe fallback are defined.
