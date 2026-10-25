# EL-Rouji portfolio integration contract

**Status:** source-backed integration baseline; not a declaration that all listed systems are connected.  
**Checked:** 25 October 2026.  
**Canonical inventory:** [`ecosystem/portfolio.json`](../../ecosystem/portfolio.json).  
**Registry schema:** [`schemas/portfolio.schema.json`](../../schemas/portfolio.schema.json).

## 1. Purpose and authority

This contract records which repositories exist, the interfaces they expose or propose, their evidence-backed maturity, known gaps, and the gates required before a connection can be called operational.

The portfolio registry is an inventory, not a runtime orchestrator. It must not be used as an executable tool catalog by itself. Only registered interfaces that have separately passed policy, schema, authorization, and runtime tests may be invoked.

Source-of-truth boundaries:

- **Core code:** `looloofy69-sketch/EL-Rouji`; **deployed service:** AppDeploy app `el-rouji-70120b`.
- **Core-to-MCP adapter:** `looloofy69-sketch/Mcps-EL-Rouji-`; it forwards a small allow-list to the core HTTP API and is not an independent model runtime.
- **Decision algorithms:** `modules/decision-infrastructure/` in this repository; the portfolio entry describes it as a tested internal prototype, not a deployed service.
- **Commerce, jobs, and datasets:** their named repositories are contract/specification or governance workspaces until implementation/release evidence says otherwise.
- **ARTEMIS, Minna, and OS Diablo:** separate repositories. No cross-runtime connection should be inferred from their presence in the same account.

## 2. Verified current connections

### MCP adapter to core API

The MCP server makes fixed HTTP requests to the configured EL-Rouji origin. Its declared tool surface includes health, chat, research, and text analysis. Generation tools are disabled by default. The adapter validates the base origin, constrains API paths, bounds timeouts/response size, and disables redirects.

**State:** adapter implemented; live end-to-end MCP-to-AppDeploy verification remains a gate.

Minimum verification before enabling generation tools:

1. Run `el_rouji_health` through the MCP host against the intended origin.
2. In a controlled test, exercise chat, query-based research, and text analysis, with usage/cost limits in place.
3. Confirm error handling, timeout behavior, no redirect following, response-size bounds, and that logs do not disclose prompts, credentials, or private outputs.
4. Verify that the client and upstream agree on mode/language validation and response shapes.
5. Preserve the default-off behavior for generation unless an operator explicitly configures the opt-in.

## 3. Interfaces for future connections

### Decision infrastructure

A first isolated adapter exists at [`adapters/decision-mcp/`](../../adapters/decision-mcp/README.md). It runs as a separate MCP-over-stdio process and exposes capability discovery plus one bounded execution call against a fixed allow-list of pure, retry-safe decision algorithms.

A second prototype at [`adapters/decision-api/`](../../adapters/decision-api/README.md) exposes authenticated `GET /v1/capabilities` and `POST /v1/run` endpoints for a possible server-to-server connection. It reuses the same decision runner, requires a high-entropy bearer token, bounds request size, rate-limits by the service-token fingerprint, and maps results to structured HTTP statuses. The token is a service credential, not user identity; EL-Rouji must enforce its own user access policy and per-user quotas.

**Neither adapter is yet connected to the EL-Rouji application.** The HTTP bridge is not deployed, and no service URL or token is configured in AppDeploy. The local MCP process is not directly callable by the hosted app. Hosting approval, TLS ingress, secret injection, a fixed backend origin, endpoint tests, and deployed version/rollback evidence remain release gates. The HTTP bridge currently uses an in-memory rate limiter and cooperative—not hard—timeouts, so horizontal scaling or hostile remote workloads require additional controls.

The local MCP request is `ecosystem_run_capability(capability_id, input_json)`. Both adapters expose the same underlying seven-capability allow-list; neither exposes workflows, arbitrary code, shell commands, arbitrary URLs, file access, or state-changing operations.

Security invariants:

- Allow-listed capability identifiers only. Unknown side-effect classification is a rejection, not permission.
- Validate candidate outputs independently before accepting them as authoritative state.
- Bound task count, serialized input/output, deadline, and provider spend. Cooperative cancellation is not a hard timeout; isolate blocking/untrusted handlers when hard termination is required.
- Do not claim exactly-once execution. Recovery for a pure/retry-safe computation is not a distributed transaction for external side effects.

### ARTEMIS device automation

Treat ARTEMIS as a separate MCP tool provider that may later be reached through an explicit host/orchestrator connection. No direct core API connection is currently claimed.

Before connection, separate observation tools from actions, bind tools to a named/authorized device, require user approval for consequential actions, use short-lived/one-use approval grants, support cancellation, redact sensitive captures, and test on a controlled device. Unknown action outcomes must be reconciled rather than blindly repeated.

### Commerce

The current commerce repository contains draft schemas/contracts, not a commerce service. Do not expose checkout or payment operations through EL-Rouji until a server-owned catalog/inventory/order implementation exists. The backend must recalculate price and stock, scope records to their owner/tenant, verify payment-provider webhooks, use idempotency for financial side effects, and keep payment/fulfillment state distinct.

### Jobs

The jobs workspace is a proposal, not an operational scheduler. Before adding an endpoint or cron handler, pick one concrete named job and define its owner scope, lifecycle, retention, retry/backoff, idempotency, cancellation, time-zone/DST, overlap, and missed-run semantics. Prove the due-job query is bounded under representative load. Do not promise exactly-once execution or general-purpose arbitrary jobs.

### Dataset evaluation

The dataset workspace currently supplies metadata/contracts/templates, not production datasets. Start with a small, synthetic, versioned regression set and a reproducible evaluator. Record provenance, license/permission, locale, checksum, quality limits, and review status. Evaluation permission does not grant training or redistribution permission. Do not export private conversation content by default.

### Minna and OS Diablo

Keep these projects separate until a concrete capability, authoritative implementation, versioned interface, and non-duplicative ownership boundary are established. In particular, the OS Diablo repository is a governance/planning home rather than the business-management executable source.

## 4. Core application security gates

The current inspected source has `POST /api/research` without route-local `requireAuth()`. This alone does not prove the route is publicly exploitable, but the intended access policy must be made explicit and server-enforced. If research is intentionally anonymous, enforce request quotas, concurrency limits, provider-spend ceilings, and abuse protection at trusted server/platform boundaries rather than relying only on client checks.

Before broad rollout, verify and record:

- authentication/authorization policy for every route;
- rate limiting and spend/concurrency ceilings for AI and search calls;
- user/tenant isolation for every cloud conversation read/write/delete;
- input length, payload size, MIME/content validation, and safe errors;
- retention and deletion behavior for browser-local and cloud history separately;
- search secret validity and research success/failure cases;
- deployed snapshot parity with reviewed GitHub source;
- Arabic RTL, French, and English behavior on mobile and desktop.

Direct page scraping is disabled in the inspected source while DNS/redirect/destination protections remain unresolved. Keep it disabled until a secure fetch boundary and live negative/positive tests prove the controls. A URL syntax validator alone is not an SSRF defense.

## 5. Maturity and promotion rules

The portfolio registry uses these meanings:

- `deployed`: a named deployed endpoint/version has been observed. This is not automatically a production-readiness claim.
- `implemented-unverified`: relevant code exists, but the required live or full integration evidence is incomplete.
- `prototype`: meaningful implementation and/or tests exist, but production operations/security/resource guarantees are incomplete.
- `specification-only`: contracts or architecture exist without an operational implementation of the claimed system.
- `governance-only`: planning, backlog, or governance artifacts exist; the executable implementation is not present in that repository.

Every connection uses a separate state and explicit required gates. Do not promote an entry because a README changed, an issue closed, a schema test passed, or CI is green if the required interface was not tested. Evidence should include immutable commit/release identifiers, test scope, date, and the deployed snapshot where applicable.

## 6. Immediate delivery order

1. Keep this portfolio inventory and its validator green; review changes through a pull request.
2. Finish the core API access-policy and rate-limit decision, then test the live research route and account isolation.
3. Run the MCP adapter against the intended deployed core in a controlled integration test.
4. Build an isolated decision-module adapter with request/response schemas and budget/approval enforcement.
5. Release one synthetic evaluation dataset and reproducible evaluation runner.
6. Implement one bounded job type only after queue query, idempotency, authorization, and recovery behavior are proven.
7. Start commerce implementation only after product/payment/fulfillment requirements are settled.
8. Connect device automation only after device scoping, approval, cancellation, and audit gates are covered.

This ordering deliberately prioritizes verifiable interfaces and safety boundaries before adding more tool surface.
