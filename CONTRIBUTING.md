# Contributing

Read the system model, execution contract, lifecycle policy, and roadmap before changing code or contracts. Identify the component status, state the invariant/behavior being changed, add regression tests, and update documentation and registry evidence as needed.

## Pull request checklist
- [ ] Scope and rationale are clear.
- [ ] Inputs, outputs, preconditions, side effects, and failures are documented.
- [ ] Tests cover boundary, cancellation, and failure paths where applicable.
- [ ] Registry and internal Markdown links validate.
- [ ] New dependencies are justified and managed.
- [ ] No secrets, private user data, or irrelevant generated files are committed.
- [ ] Claims distinguish local tests, CI, benchmarks, and proofs.

Prefer narrow interfaces, explicit preconditions, typed results, and deterministic behavior. Keep proposals separate from independent validation. Do not perform irreversible actions during planning. Avoid hidden retries and unbounded loops.

No license has been selected yet. Until an explicit license and license file are committed, do not assume the repository is available for reuse under an open-source license.
