# Security policy

## Scope
Security-relevant areas include authorization, run-context propagation, cancellation, resource limits, persistence/recovery, secrets handling, capability adapters, and future external-tool/model integration.

## Reporting
Do not publish credentials, exploitable details, sensitive inputs, or personal data in public issues. If private vulnerability reporting is enabled for this repository, use it. Otherwise, contact the repository owner through a private GitHub channel and provide a minimal report without secrets.

## Current limitations
This repository is an architecture/tooling foundation, not a production service. It has not undergone a security audit. Production-readiness requires a threat model, dependency review, authorization tests, an isolation strategy for untrusted work, recovery tests, and an operational response/rollback procedure.

## Contributor requirements
- Never commit tokens, passwords, private keys, or live production configuration.
- Treat capability results and serialized inputs as untrusted.
- Deny side effects when authorization is missing or ambiguous.
- Avoid logging sensitive raw inputs.
- Document whether timeout behavior is cooperative or hard-enforced.
