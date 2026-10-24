# Validation report — Delta-Infrastructure 0.6.0

## Scope

Source is imported under modules/decision-infrastructure. The test suite covers oracle-based algorithms, exhaustive small mathematical instances, matching separation/optimization against independent definitions, Schur-pivot exactness, portfolio scheduling and transition contracts, workflow validation/persistence, runtime guard primitives, and controller-boundary enforcement.

## Local artifact baseline

Before import, the local v0.6.0 workbench suite reported 59 passing tests using:

    python -m unittest discover -s tests -v

That local result is baseline evidence for the workbench folder, not evidence about the GitHub revision.

## Repository validation

The GitHub Actions run for the imported revision is authoritative. It should run repository registry/link checks, root tests, package tests, and a wheel build. Record the actual run URL, commit SHA, result, and test count after the run finishes; do not copy local totals into the CI result.

## Known limitations

- Guards observe cancellation/deadline only at cooperative boundaries; blocking code is not forcefully terminated.
- Serialized size limits do not replace process-level CPU/memory quotas.
- SQLite history is not a checkpoint-and-resume or exactly-once side-effect protocol.
- Workflow approval flags do not provide authenticated identity, role-based access control, or cryptographic audit.
- Matching optimum verification is bounded exhaustive verification for small instances.
- No production deployment, security audit, or SLO has been claimed.
