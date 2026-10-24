# Ecosystems Loofy

An internal, modular control plane for coordinating decision components, algorithms, and tools under explicit policies.

**Current stage:** architecture and repository foundation. The repository does not yet contain a production execution runtime. The decision-infrastructure prototype described in the registry is a local v0.5.0 artifact and has not yet been imported into this repository.

## Objectives

- Maintain a machine-readable registry of internal components and their maturity.
- Define stable contracts for run context, capabilities, budgets, cancellation, checkpoints, validation, and authorized actions.
- Coordinate compatible decision strategies using explicit state, constraints, policy, and evidence—not arbitrary rotation.
- Keep execution bounded, observable, testable, and recoverable.
- Make experimental code distinguishable from validated, integrated, production-ready components.

## Repository map

```text
.
├── ecosystem/              # Registry of components and their current integration status
├── docs/
│   ├── architecture/       # System boundaries, runtime contract, adaptive orchestration
│   ├── governance/          # Component lifecycle and change policy
│   ├── operations/          # Validation and release gates
│   └── roadmap/             # Sequenced implementation plan
├── modules/
│   └── decision-infrastructure/  # Import plan for the current delta-matroid prototype
├── schemas/                 # Machine-readable manifest contracts
├── scripts/                 # Dependency-light repository checks
├── tests/                   # Tests for repository tooling and contracts
└── .github/workflows/       # Automated consistency checks
```

## Working principles

1. **One run context.** Every dispatched capability receives the same run identifier, state snapshot/version, policy, deadline, cancellation signal, budget ledger, and trace context.
2. **Algorithms propose; policy decides.** An algorithm may rank or propose a candidate. Feasibility checks, policy validation, and explicit authorization govern whether it may proceed.
3. **Bound every boundary.** Validate inputs before work, check cancellation/deadlines at cooperative checkpoints, cap outputs, and isolate untrusted or non-cooperative work when hard enforcement is required.
4. **Make state transitions explicit.** Persist checkpoints and outcomes before claiming durable completion.
5. **Fail closed.** Missing policy, invalid state, exceeded budget, failed invariants, or unresolved authorization must stop execution safely.
6. **Publish evidence, not adjectives.** Maturity claims must cite tests, reproducible validation, known limitations, and the exact revision assessed.

## Current implementation status

The registry records the decision-infrastructure workbench as a prototype artifact. Its v0.5.0 package includes delta-matroid algorithms, adaptive portfolio scheduling, SQLite history, and standalone runtime guard primitives. The previously run local test suite reported 53 passing tests. These are facts about that local artifact only: they are **not** CI results for this repository, and the runtime guards are not yet integrated into every controller.

See:
- [System model](docs/architecture/system-model.md)
- [Execution contract](docs/architecture/execution-contract.md)
- [Adaptive orchestration](docs/architecture/adaptive-orchestration.md)
- [Component lifecycle](docs/governance/component-lifecycle.md)
- [Roadmap](docs/roadmap/ROADMAP.md)
- [Decision-infrastructure import plan](modules/decision-infrastructure/README.md)
- [Registry](ecosystem/registry.json)

## Validate the repository

Requires Python 3.11 or newer; no third-party package is needed for the repository checks.

```bash
python scripts/validate_registry.py
python -m unittest discover -s tests -v
```

## Scope and non-goals

This repository is the source of truth for architecture and integration contracts. It is not yet a hosted service, agent marketplace, workflow SaaS product, or claim that each listed subsystem is implemented. Local prototypes remain experimental until their source is imported, tested in CI, integrated behind the declared interfaces, and reviewed against the release gates.

## Security and contribution

Do not commit credentials, user data, private keys, or production secrets. See [SECURITY.md](SECURITY.md) and [CONTRIBUTING.md](CONTRIBUTING.md). No license has been selected yet; the repository should not be treated as open-source licensed until an explicit license decision and license file are committed.
