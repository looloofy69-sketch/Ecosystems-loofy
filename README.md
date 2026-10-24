# Ecosystems Loofy

An internal, modular control plane for coordinating decision algorithms and tools under explicit policies, shared state, bounded execution, validation, and authorization.

**Current stage:** the v0.6.0 delta-matroid decision module is imported and CI-tested. This is an integrated internal prototype—not a production-ready runtime. Durable checkpoints/recovery, hard isolation for blocking work, authenticated authorization, and production side-effect controls remain open work.

## Repository structure

```text
.
├── ecosystem/                   # Component registry and maturity records
├── docs/
│   ├── architecture/            # System boundaries, execution contract, adaptive orchestration
│   ├── governance/              # Lifecycle and promotion rules
│   ├── operations/              # Quality gates
│   └── roadmap/                 # Sequenced implementation plan
├── modules/
│   └── decision-infrastructure/ # Algorithms, workflow/portfolio controllers, tests and examples
├── schemas/                     # Component manifest schema
├── scripts/                     # Repository validation tooling
├── tests/                       # Repository-level tests
└── .github/workflows/           # Automated validation and package build
```

## Integrated decision module

The imported module provides LocalSearch, SignedGreedy, MonotonePath, guarded StrongPath, SchurPath over exact supported fields, MatchingSep, a capability registry, a declarative workflow DAG controller, adaptive state-aware portfolio scheduling, SQLite run history, and bounded runtime checks.

The current CI validates registry paths and Markdown links, runs root tests, installs and compiles the decision module, runs its 59-test package suite, and builds a wheel. The successful import/CI run is [GitHub Actions run 40130032418](https://github.com/looloofy69-sketch/Ecosystems-loofy/actions/runs/40130032418), which passed at commit `9439c0ebcff2901a505adbdf0a6d0434b44c24ce`.

## Operating principles

1. **One effective run context:** propagate run ID, state version, policy, deadlines, cancellation, budget, and trace data consistently.
2. **Algorithms propose; validation decides:** no strategy is trusted solely because it reports success.
3. **Bound execution:** use preflight checks, cooperative cancellation/deadline checkpoints, and input/output size limits; use process isolation where hard enforcement is necessary.
4. **Separate proposal, validation, authorization, and commit:** planning does not grant permission to cause side effects.
5. **Persisted history is not recovery:** SQLite run logs do not yet provide checkpoints, resume semantics, or exactly-once external operations.
6. **Publish evidence, not adjectives:** component status must match tests, CI, documented limitations, and the revision assessed.

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

Use Python 3.12 (the CI baseline) and install the package:

    python scripts/validate_registry.py
    python -m unittest discover -s tests -v
    python -m pip install -e modules/decision-infrastructure
    python -m unittest discover -s modules/decision-infrastructure/tests -v
    python -m pip wheel modules/decision-infrastructure --no-deps -w /tmp/delta-infra-wheel

The package requires NetworkX 3.x. See the module README for CLI examples and mathematical preconditions.

## Security and licensing

Do not commit credentials, private keys, production secrets, or sensitive inputs. Workflow run history can store input/output payloads. See [SECURITY.md](SECURITY.md) and [CONTRIBUTING.md](CONTRIBUTING.md). No license has been selected; the repository must not yet be treated as released under an open-source license.
