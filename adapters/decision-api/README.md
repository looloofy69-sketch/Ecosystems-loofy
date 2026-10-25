# Ecosystem Decision API Bridge

**Status:** authenticated service prototype; not deployed or connected to EL-Rouji yet.

This small HTTP service wraps the same fixed, bounded decision capability runner exposed by [the local stdio MCP adapter](../decision-mcp/README.md). It provides a possible service-to-service seam for an authenticated EL-Rouji backend. The bridge is an implementation candidate; no production URL or deployment platform has been selected.

## Endpoints

| Method and path | Access | Purpose |
|---|---|---|
| `GET /health` | Public; minimal response | Liveness only |
| `GET /v1/capabilities` | Bearer token required | Describe the fixed capability allow-list and limits |
| `POST /v1/run` | Bearer token required | Execute one registered pure capability |

The interactive API documentation and OpenAPI route are disabled in this service build.

### Run request

```json
{
  "capability_id": "matching.signed_greedy",
  "input": {
    "vertices": ["a", "b"],
    "edges": [["a", "b"]],
    "weights": {"a": 3, "b": -1}
  }
}
```

Responses use the same structured result envelope and statuses as the MCP capability runner. Successful responses include a generated request ID, trace ID, capability result, and budget diagnostics.

## Security and limits

- `EL_ROUJI_DECISION_API_TOKEN` must be configured as a server-side secret and contain at least 32 characters. Missing/short tokens fail closed: protected routes return 503.
- Protected routes use constant-time bearer-token comparison. Tokens are not returned or logged.
- Request body reads are bounded; the selected capability and payload are validated against the same fixed allow-list and contracts as MCP.
- Default run limit is 30 calls per minute per service token, with a bounded execution concurrency of one. Configure `create_app(rate_limit_per_minute=...)` before deployment to tune this. The rate limiter is **per process/in-memory**; do not horizontally scale this instance without a shared gateway/limiter or equivalent central quota.
- Inputs, outputs, graph/matrix/family sizes, and cooperative runtime are bounded by the underlying shared runner.
- A cooperative deadline is not a hard process kill. For hard CPU/memory isolation, run in a container/process with enforceable resource limits and a supervisor.
- `/health` reveals only liveness; it does not expose configuration or secrets.
- The service uses HTTP internally. Put it behind a trusted HTTPS/TLS ingress before connecting any remote caller; never send the bearer token over public plaintext HTTP.
- Bind the service token only in the EL-Rouji backend's secret configuration. Never include it in browser code, a public repository, a URL, or a prompt.
- This bridge currently has a shared service credential, not per-user identity. The EL-Rouji backend must enforce its own user policy, quotas, and authorization before forwarding a request. The shared credential alone is not end-user authentication or tenant isolation.

No tool for arbitrary code, shell execution, local-file access, arbitrary URLs, workflows, or state-changing actions is exposed.

## Run locally

From the repository root:

```sh
python -m venv .venv
# Linux/macOS:
. .venv/bin/activate
python -m pip install -e modules/decision-infrastructure
python -m pip install -e adapters/decision-mcp
python -m pip install -e "adapters/decision-api[test]"

# Generate a local-only token; keep it out of source control.
export EL_ROUJI_DECISION_API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
python -m unittest discover -s adapters/decision-api/tests -v
ecosystem-decision-api
```

Then use an HTTPS-capable local reverse proxy or a loopback-only tunnel when testing from another process. The service should not be bound to a public network without TLS and the shared-secret policy configured.

## Build container

From the repository root:

```sh
docker build -f adapters/decision-api/Dockerfile -t ecosystem-decision-api:local .
```

Run with a secret injected by your deployment platform, not baked into the image:

```sh
docker run --rm -p 127.0.0.1:8080:8080 \
  -e EL_ROUJI_DECISION_API_TOKEN="$EL_ROUJI_DECISION_API_TOKEN" \
  ecosystem-decision-api:local
```

The container runs as a non-root user and the image does not contain a credential. Do not publish or expose the port publicly unless TLS ingress, secret injection, monitoring, quotas, and deployment rollback are configured.

## Connecting to EL-Rouji

A secure deployment path is possible but **not yet active**:

1. Deploy this bridge behind TLS on a chosen, approved platform and record a concrete base URL and immutable image/revision.
2. Create a secret entry for `EL_ROUJI_DECISION_API_TOKEN` on the service and a separate server-side secret entry in the EL-Rouji AppDeploy app for its outbound bearer token. Use the same random token, but never reveal it to frontend code.
3. Add a narrow core backend integration that calls only `GET /v1/capabilities` and `POST /v1/run`, with fixed origin, timeout, request/output limits, and sanitized errors. Do not allow clients to supply the bridge URL.
4. Apply the chosen public/authenticated-user policy and per-user quotas in EL-Rouji before service invocation; the bridge’s shared service token is not user authorization.
5. Test authentication failures, invalid capabilities, oversized input/output, rate limits, timeouts, cancellation, account isolation, and cost/usage controls against a test deployment.
6. Enable the UI/tool route only after the tests pass and the deployed source version and rollback plan are recorded.

No service has been deployed and no EL-Rouji production source has been modified by this package.
