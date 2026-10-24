# Quality and release gates

## Repository gate
- Parse registry JSON and check required fields, unique IDs, lifecycle statuses, and target paths.
- Verify relative Markdown links.
- Run unit tests for repository tooling.
- Keep CI deterministic and dependency-light.

## Component integration gate
- Unit tests for invariants, boundaries, and failure cases.
- Property/exhaustive small-instance tests for critical math claims where feasible.
- Contract tests for schema and state-version handling.
- Budget exhaustion, cancellation, deadlines, oversized input/output, and nested-work propagation tests.
- Independent feasibility validation after candidate generation.
- Merge/deduplication tests that preserve provenance.
- Reproducible examples and assumptions.

## Runtime gate
- Controller-level tests prove actual enforcement; guard primitive tests alone are insufficient.
- Test isolation against unresponsive tasks when hard timeouts are required.
- Verify cancellation stops new work and propagates to children.
- Verify stale state cannot be committed.
- Verify authorization denies by default.
- Verify persistence/recovery does not duplicate side effects.
- Keep secrets and unbounded raw inputs out of logs.

## Release gate
Record version, commit SHA, test summary, build/checksum, known issues, migration notes, and rollback instructions. Do not promote registry status until relevant gates pass.

A green lint job, one successful example, local tests from a separate artifact, or an undocumented benchmark is not sufficient evidence.
