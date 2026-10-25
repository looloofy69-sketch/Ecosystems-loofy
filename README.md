# Ecosystems Loofy

An internal, modular control plane for coordinating decision algorithms and tools under explicit policies, shared state, bounded execution, validation, and authorization.

**Current stage:** the v0.7.0 delta-matroid decision module includes a typed RunContext, centrally accounted budget ledger, cooperative checkpoints, and restart recovery for retry-safe declarative workflows. It is an integrated internal prototype—not a production-ready runtime.

## Repository structure

    .
    ├── adapters/
    │   ├── decision-api/            # Authenticated HTTP bridge prototype for server-to-server calls
    │   └── decision-mcp/            # Bounded, read-only MCP server for pure algorithms
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

The v0.7.0 revision was validated in [GitHub Actions run 40133079284](https://github.com/looloofy69-sketch/Ecosystems-loofy/actions/runs/40133079284) at commit 153ae59a629ebdc3a4a2cbcbd8bff1c5943c9693. Registry/link validation, 4 repository tests, package installation, compileall, 70 decision-module tests, CLI smoke tests, and wheel build all passed. This is evidence for an integrated internal prototype, not production readiness.

## Portfolio integration audit

The cross-repository inventory is maintained separately from the local decision-module registry:

- [Portfolio registry](ecosystem/portfolio.json) — nine repositories/projects, verified maturity labels, dependencies, evidence links, known gaps, and explicit connection states.
- [Portfolio integration contract](docs/architecture/portfolio-integration-contract.md) — interface boundaries, security invariants, test gates, and implementation sequence.
- [Portfolio registry schema](schemas/portfolio.schema.json) — machine-readable contract for inventory and connection records.

A listed repository is not automatically an integrated component. The MCP adapter-to-core relationship is recorded as implemented but not end-to-end verified; commerce, jobs, datasets, ARTEMIS, Minna, and OS Diablo remain unconnected or contract-only until their stated gates pass. The portfolio validator checks this inventory without network calls.

## Key documents

- [System model](docs/architecture/system-model.md)
- [Execution contract](docs/architecture/execution-contract.md)
- [Adaptive orchestration](docs/architecture/adaptive-orchestration.md)
- [Component lifecycle](docs/governance/component-lifecycle.md)
- [Quality and release gates](docs/operations/quality-gates.md)
- [Implementation roadmap](docs/roadmap/ROADMAP.md)
- [Decision module README](modules/decision-infrastructure/README.md)
- [Decision MCP adapter](adapters/decision-mcp/README.md)
- [Authenticated Decision API bridge](adapters/decision-api/README.md)
- [Component registry](ecosystem/registry.json)
- [Validation report](modules/decision-infrastructure/VALIDATION_REPORT.md)

## Validate locally

Use Python 3.12 (the CI baseline):

    python scripts/validate_registry.py  # local registry + cross-repository portfolio + Markdown links
    python -m unittest discover -s tests -v
    python -m pip install -e modules/decision-infrastructure
    python -m unittest discover -s modules/decision-infrastructure/tests -v
    python -m pip wheel modules/decision-infrastructure --no-deps -w /tmp/delta-infra-wheel

For workflow recovery, use the same workflow file and SQLite database as the original run:

    python -m delta_infra.workflow_cli examples/workflows/internal_matching_validation.json --db .delta-infra-runs.sqlite3 --resume RUN_ID --pretty

Resume is restricted to the same workflow definition and retry-safe capability contracts. Portfolio-turn resume is not implemented yet.

## Security and licensing

Cancellation is cooperative; blocking libraries need process isolation for hard timeout guarantees. SQLite checkpoints are not a distributed transaction log. Approval flags are not authenticated identity. Run history can contain input/output payloads, so do not submit secrets. See [SECURITY.md](SECURITY.md) and [CONTRIBUTING.md](CONTRIBUTING.md). No license has been selected; the repository must not yet be treated as released under an open-source license.
