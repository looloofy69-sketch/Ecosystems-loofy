# Ecosystem Decision MCP Adapter

**Version:** 0.1.0  
**Status:** isolated, bounded prototype; not a production runtime.

This local stdio MCP server exposes a narrow allow-list of pure decision algorithms from [the decision-infrastructure package](../../modules/decision-infrastructure/). It lets a compatible MCP host discover available capabilities and submit one finite JSON request at a time.

It does **not** connect directly to the EL-Rouji web application's backend. A client host would need to configure this server explicitly; no cross-server tool-routing or assistant UI binding is implied.

## Exposed tools

| Tool | Purpose |
|---|---|
| `ecosystem_list_capabilities` | List the fixed allow-list and its declared preconditions. |
| `ecosystem_run_capability` | Run one registered pure capability against a bounded JSON payload. |

The allow-list currently contains:

- `delta_matroid.local_search`
- `delta_matroid.signed_greedy`
- `delta_matroid.monotone_path`
- `delta_matroid.strong_path`
- `delta_matroid.schur_path`
- `matching.separation`
- `matching.signed_greedy`

The adapter checks each selected capability's registry metadata and refuses any capability not explicitly allow-listed or not declared `side_effect_class="none"` and `retry_safe=True`. It does not accept workflow graphs, arbitrary Python, shell commands, arbitrary files, URLs, network calls, or state-changing tools.

## Bounds and limits

- JSON request input: at most 32 KiB.
- Serialized response: at most 64 KiB.
- One running computation at a time; overlapping calls receive a `busy` result rather than queuing.
- Explicit feasible-family algorithms: at most 10 ground-set labels and 256 feasible-family members.
- Matrix algorithms: at most 24 × 24.
- Matching algorithms: at most 24 vertices and 128 edges.
- Execution budget: one task and a 4-second cooperative deadline.
- JSON non-finite constants are rejected; labels, payload fields, weights, and mathematical input shapes are validated before dispatch.

**Timeout limitation:** the algorithm context checks deadlines cooperatively. Python cannot forcibly terminate a blocking operation in a worker thread. Input-size/cardinality bounds reduce risk but are not a hard CPU or memory sandbox. Do not expose this server to untrusted remote clients or a public endpoint; use a process/container boundary when hard termination is required.

## Install and run

Python 3.11 or later is required. From the repository root:

```sh
python -m venv .venv
# Linux/macOS:
. .venv/bin/activate
python -m pip install -e modules/decision-infrastructure
python -m pip install -e adapters/decision-mcp
python -m unittest discover -s adapters/decision-mcp/tests -v
ecosystem-decision-mcp
```

The server uses MCP stdio. Its logs go to stderr; stdout is reserved for the MCP protocol.

## Example MCP host configuration

Use the absolute executable path from your own environment:

```json
{
  "mcpServers": {
    "ecosystem-decisions": {
      "command": "/absolute/path/to/repository/.venv/bin/ecosystem-decision-mcp"
    }
  }
}
```

An MCP host may register this server alongside EL-Rouji's separate MCP adapter. That configuration only makes both sets of tools available to the host; it does not make the EL-Rouji assistant or backend automatically call decision tools.

## Request shape

Call `ecosystem_run_capability` with a fixed `capability_id` and an `input_json` string. For example:

```json
{
  "capability_id": "matching.signed_greedy",
  "input_json": "{\"vertices\":[\"a\",\"b\"],\"edges\":[[\"a\",\"b\"]],\"weights\":{\"a\":3,\"b\":-1}}"
}
```

Success returns a structured JSON string containing `request_id`, `trace_id`, capability metadata, the result, and budget diagnostics. Rejections, budget exhaustion, cancellation, busy state, and capability failures use fixed status values and sanitized error messages. Results only claim the mathematical checks evidenced in that capability's output; this wrapper does not independently re-verify every result.

## Validation

Local CI imports the adapter, tests the allow-list, input validation, success/error envelopes, response budget, cooperative context, and single-run concurrency. These tests do not establish production security, hard timeout guarantees, or connectivity from a live EL-Rouji MCP host.

See the [portfolio integration contract](../../docs/architecture/portfolio-integration-contract.md) for required integration gates.
