# Component lifecycle and change policy

## Status definitions
- **design-only** — documented; no runnable implementation claimed.
- **planned** — scoped but not implemented.
- **prototype-artifact** — implementation exists outside this repository or as an isolated experiment; not integrated.
- **integrated** — source is tracked here, interfaces are implemented, CI covers it, integration tests pass.
- **production-ready** — integration plus security, recovery, performance, operational, and rollback gates for a bounded use case.
- **deprecated** — retained temporarily with a migration/removal plan.

Do not promote a component based on a README, smoke test, or source files alone.

## Promotion to integrated
1. Import source, tests, package metadata, and license/dependency information.
2. Encode key invariants and mathematical assumptions in tests where possible.
3. Add deterministic unit and integration tests to CI.
4. Wire through the shared execution contract.
5. Enforce budgets, deadlines, cancellation, output validation, and normalized errors.
6. Demonstrate telemetry and durable checkpoints where required.
7. Review trust boundaries, side effects, and retry semantics.
8. Update registry status only after evidence is attached to the change.

Production-ready additionally requires a threat review, recovery/failure tests, performance bounds, runbook, compatibility policy, and rollback path.

## Versioning and evidence
Use semantic versioning for published interfaces. Breaking changes require a major version or documented migration. Every validation report identifies revision, commands, environment, outcomes, skipped tests, and limitations. Local, CI, and production evidence are distinct and must not be conflated.
