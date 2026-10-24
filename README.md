# Ecosystems Loofy

An internal, modular control plane for coordinating decision algorithms and tools under explicit policies, shared state, bounded execution, validation, and authorization.

**Current stage:** the v0.7.0 delta-matroid decision module includes a typed RunContext, centrally accounted budget ledger, cooperative checkpoints, and restart recovery for retry-safe declarative workflows. It is an integrated internal prototype—not a production-ready runtime.

## Repository structure

    .
    ├── ecosystem/                   # Component registry and maturity records
    ├── docs/
    │   ├── architecture/            # System boundaries, execution contract, adaptive orchestration
    │   ├── governance/              # Lifecycle and promotion rules
    │   ├── operations/              # Quality gates
    │   └── roadmap/                 # Sequenced implementation plan
    ├── modules/
    │   └── decision-infrastructure/ # Algorithms, controllers, recovery tests and examples
    ├── schemas/                     # Component manifest schema
    ├── scripts/                     # Repository validation tooling
    ├── tests/                       # Repository-level tests
    └── .github/workflows/           # Automated validation and package build

## Integrated decision module

The module provides LocalSearch, SignedGreedy, MonotonePath, guarded StrongPath, SchurPath over supported exact fields, MatchingSep, a capability registry, declarative workflow DAG execution, state-aware portfolio scheduling, SQLite run history/checkpoints, and budget/cancellation guards.

The module has a shared RunContext with an immutable policy snapshot and a budget ledger. Context-aware capability handlers check deadlines/cancellation during implemented inner loops. WorkflowRunStore writes append-only task checkpoints; resume verifies the canonical workflow fingerprint, reuses successful outputs, and retries only capabilities explicitly declared safe.

## Validation and release evidence

Every code-changing push triggers repository checks, package compilation, package tests, and a wheel build. The previous validated baseline was [CI run 40130032418](https://github.com/looloofy69-sketch/Ecosystems-loofy/actions/runs/40130032418) for v0.6.0. The 0.7.0 validation report will record the exact successful run for the current shared-context and recovery implementation before release status is finalized.

## Key documents

- [System model](docs/architecture/system-model.md)
- [Execution contract](docs/architecture/execution-contract.md)
- [Adaptive orchestration](docs/architecture/adaptive-orchestration.md)
- [Component lifecycle](docs/governance/component-lifecycle.md)
- [Quality and release gates](docs/operations/quality-gates.md)
- [Implementation roadmap](docs/roadmap/ROADMAP.md)
- [Decision module README](modules/decision-infrastructure/README.md)
- [Component registry](ecosystem/registry.json)
- [Validation report](modules/decision-infrastructure/VALIDATION_REPORT.md)

## Validate locally

Use Python 3.12 (the CI baseline):

    python scripts/validate_registry.py
    python -m unittest discover -s tests -v
    python -m pip install -e modules/decision-infrastructure
    python -m unittest discover -s modules/decision-infrastructure/tests -v
    python -m pip wheel modules/decision-infrastructure --no-deps -w /tmp/delta-infra-wheel

For workflow recovery, use the same workflow file and SQLite database as the original run:

    python -m delta_infra.workflow_cli examples/workflows/internal_matching_validation.json --db .delta-infra-runs.sqlite3 --resume RUN_ID --pretty

Resume is restricted to the same workflow definition and retry-safe capability contracts. Portfolio-turn resume is not implemented yet.

## Security and licensing

Cancellation is cooperative; blocking libraries need process isolation for hard timeout guarantees. SQLite checkpoints are not a distributed transaction log. Approval flags are not authenticated identity. Run history can contain input/output payloads, so do not submit secrets. See [SECURITY.md](SECURITY.md) and [CONTRIBUTING.md](CONTRIBUTING.md). No license has been selected; the repository must not yet be treated as released under an open-source license.
