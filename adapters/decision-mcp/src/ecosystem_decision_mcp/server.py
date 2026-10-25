"""Bounded MCP surface for the pure, registered decision-infrastructure capabilities.

This server does not expose workflows, portfolios, shell execution, arbitrary imports,
filesystem access, network access, or state-changing tools.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import threading
import time
import uuid
from typing import Any, Literal, Mapping

from mcp.server import MCPServer

from delta_infra.registry import default_registry
from delta_infra.runtime import (
    ExecutionBudget,
    ExecutionBudgetExceeded,
    ExecutionCancelled,
    RunContext,
    RuntimePolicyError,
)

logging.basicConfig(level=os.getenv("LOG_LEVEL", "WARNING").upper())
logger = logging.getLogger("ecosystem_decision_mcp")

MAX_INPUT_BYTES = 32_768
MAX_OUTPUT_BYTES = 65_536
MAX_GROUND_SET = 10
MAX_FEASIBLE_SETS = 256
MAX_MATRIX_SIZE = 24
MAX_GRAPH_VERTICES = 24
MAX_GRAPH_EDGES = 128
MAX_LABEL_LENGTH = 80
MAX_DURATION_SECONDS = 4.0
TOOL_WAIT_SECONDS = MAX_DURATION_SECONDS + 0.5

CAPABILITY_IDS = (
    "delta_matroid.local_search",
    "delta_matroid.signed_greedy",
    "delta_matroid.monotone_path",
    "delta_matroid.strong_path",
    "delta_matroid.schur_path",
    "matching.separation",
    "matching.signed_greedy",
)
CapabilityId = Literal[
    "delta_matroid.local_search",
    "delta_matroid.signed_greedy",
    "delta_matroid.monotone_path",
    "delta_matroid.strong_path",
    "delta_matroid.schur_path",
    "matching.separation",
    "matching.signed_greedy",
]

INPUT_FIELDS = {
    "delta_matroid.local_search": {
        "required": {"ground_set", "feasible_sets", "weights", "initial"},
        "optional": {"max_improving_moves"},
    },
    "delta_matroid.signed_greedy": {
        "required": {"ground_set", "feasible_sets", "weights"},
        "optional": set(),
    },
    "delta_matroid.monotone_path": {
        "required": {"ground_set", "feasible_sets", "A", "B"},
        "optional": set(),
    },
    "delta_matroid.strong_path": {
        "required": {"ground_set", "feasible_sets", "A", "B"},
        "optional": {"dummy"},
    },
    "delta_matroid.schur_path": {
        "required": {"matrix"},
        "optional": {"field", "labels"},
    },
    "matching.separation": {
        "required": {"vertices", "edges", "S", "T"},
        "optional": set(),
    },
    "matching.signed_greedy": {
        "required": {"vertices", "edges", "weights"},
        "optional": set(),
    },
}

mcp = MCPServer("Ecosystem Decision Infrastructure")
_run_lock = threading.Lock()


class InputRejected(ValueError):
    """The request is malformed or exceeds the adapter's conservative input limits."""


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _reject_constant(value: str) -> None:
    raise InputRejected(f"Non-standard JSON number is not allowed: {value}")


def _is_finite_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and (
        isinstance(value, int) or math.isfinite(value)
    )


def _string_list(value: Any, field: str, *, maximum: int, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum:
        raise InputRejected(f"{field} must be a list within its item limit")
    if not value and not allow_empty:
        raise InputRejected(f"{field} must not be empty")
    if any(not isinstance(item, str) or not item or len(item) > MAX_LABEL_LENGTH for item in value):
        raise InputRejected(f"{field} must contain short, non-empty string labels")
    if len(value) != len(set(value)):
        raise InputRejected(f"{field} must contain unique labels")
    return value


def _finite_weights(value: Any, labels: list[str]) -> None:
    if not isinstance(value, dict) or set(value) != set(labels):
        raise InputRejected("weights must contain exactly one entry for each label")
    if any(not _is_finite_number(weight) for weight in value.values()):
        raise InputRejected("weights must be finite numbers")


def _validate_explicit_family(payload: dict[str, Any], capability_id: str) -> None:
    ground = _string_list(payload.get("ground_set"), "ground_set", maximum=MAX_GROUND_SET)
    ground_set = set(ground)
    family = payload.get("feasible_sets")
    if not isinstance(family, list) or not family or len(family) > MAX_FEASIBLE_SETS:
        raise InputRejected("feasible_sets must be a non-empty, bounded list")
    seen_family: set[tuple[str, ...]] = set()
    for index, member in enumerate(family):
        member_labels = _string_list(member, f"feasible_sets[{index}]", maximum=len(ground), allow_empty=True)
        if not set(member_labels) <= ground_set:
            raise InputRejected("feasible_sets contains a label outside ground_set")
        key = tuple(sorted(member_labels))
        if key in seen_family:
            raise InputRejected("feasible_sets must not contain duplicate members")
        seen_family.add(key)

    _finite_weights(payload.get("weights"), ground)
    for field in ("initial", "A", "B"):
        if field in payload:
            labels = _string_list(payload[field], field, maximum=len(ground), allow_empty=True)
            if not set(labels) <= ground_set:
                raise InputRejected(f"{field} contains a label outside ground_set")

    if "max_improving_moves" in payload:
        limit = payload["max_improving_moves"]
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 256:
            raise InputRejected("max_improving_moves must be an integer from 1 to 256")
    if "dummy" in payload:
        dummy = payload["dummy"]
        if not isinstance(dummy, str) or not dummy or len(dummy) > MAX_LABEL_LENGTH or dummy in ground_set:
            raise InputRejected("dummy must be a short label not present in ground_set")


def _validate_matrix(payload: dict[str, Any]) -> None:
    matrix = payload.get("matrix")
    if not isinstance(matrix, list) or not 1 <= len(matrix) <= MAX_MATRIX_SIZE:
        raise InputRejected("matrix size must be between 1 and the configured limit")
    size = len(matrix)
    for row in matrix:
        if not isinstance(row, list) or len(row) != size:
            raise InputRejected("matrix must be square")
        if any(not _is_finite_number(item) for item in row):
            raise InputRejected("matrix entries must be finite numbers")

    labels = payload.get("labels")
    if labels is not None:
        labels = _string_list(labels, "labels", maximum=MAX_MATRIX_SIZE)
        if len(labels) != size:
            raise InputRejected("labels length must match matrix size")

    field = payload.get("field", "Q")
    if field is None or field == "Q":
        return
    if not isinstance(field, dict) or set(field) != {"type", "p"} or field.get("type") != "GF":
        raise InputRejected("field must be 'Q' or an object with type='GF' and a prime p")
    prime = field.get("p")
    if isinstance(prime, bool) or not isinstance(prime, int) or not 2 <= prime <= 1_000_003:
        raise InputRejected("GF prime must be an integer between 2 and 1000003")
    if any(isinstance(item, bool) or not isinstance(item, int) for row in matrix for item in row):
        raise InputRejected("GF matrix entries must be integers")


def _validate_matching(payload: dict[str, Any], capability_id: str) -> None:
    vertices = _string_list(payload.get("vertices"), "vertices", maximum=MAX_GRAPH_VERTICES)
    vertex_set = set(vertices)
    edges = payload.get("edges")
    if not isinstance(edges, list) or len(edges) > MAX_GRAPH_EDGES:
        raise InputRejected("edges must be a bounded list")
    seen_edges: set[frozenset[str]] = set()
    for edge in edges:
        if not isinstance(edge, list) or len(edge) != 2 or any(not isinstance(v, str) for v in edge):
            raise InputRejected("each edge must contain exactly two vertex labels")
        u, v = edge
        if u not in vertex_set or v not in vertex_set or u == v:
            raise InputRejected("edge contains an unknown vertex or self-loop")
        key = frozenset(edge)
        if key in seen_edges:
            raise InputRejected("duplicate undirected edge")
        seen_edges.add(key)

    if capability_id == "matching.separation":
        S = _string_list(payload.get("S"), "S", maximum=len(vertices), allow_empty=True)
        T = _string_list(payload.get("T"), "T", maximum=len(vertices), allow_empty=True)
        if not set(S) <= vertex_set or not set(T) <= vertex_set or set(S) & set(T):
            raise InputRejected("S and T must be disjoint subsets of vertices")
    else:
        _finite_weights(payload.get("weights"), vertices)


def _validated_payload(capability_id: str, payload: Any) -> dict[str, Any]:
    if capability_id not in INPUT_FIELDS:
        raise InputRejected("Capability is not on the adapter allow-list")
    if not isinstance(payload, dict):
        raise InputRejected("Input must be a JSON object")
    fields = INPUT_FIELDS[capability_id]
    missing = fields["required"] - payload.keys()
    unknown = payload.keys() - fields["required"] - fields["optional"]
    if missing or unknown:
        raise InputRejected("Input keys do not match the capability contract")

    if capability_id.startswith("delta_matroid.") and capability_id != "delta_matroid.schur_path":
        _validate_explicit_family(payload, capability_id)
    elif capability_id == "delta_matroid.schur_path":
        _validate_matrix(payload)
    else:
        _validate_matching(payload, capability_id)
    return payload


def _error_response(request_id: str, status: str, message: str) -> str:
    return _json_text({
        "request_id": request_id,
        "status": status,
        "error": {"message": message},
    })


def _execute(capability_id: str, input_json: str, cancelled: threading.Event) -> str:
    """Execute one allow-listed pure capability with strict size and runtime budgets."""
    request_id = str(uuid.uuid4())
    if not _run_lock.acquire(blocking=False):
        return _error_response(request_id, "busy", "Another decision request is currently running.")
    started = time.monotonic()
    try:
        if capability_id not in CAPABILITY_IDS:
            return _error_response(request_id, "rejected", "Capability is not on the adapter allow-list.")
        if not isinstance(input_json, str) or len(input_json.encode("utf-8")) > MAX_INPUT_BYTES:
            return _error_response(request_id, "rejected", "Input JSON is missing or exceeds the byte limit.")
        try:
            payload = json.loads(input_json, parse_constant=_reject_constant)
            payload = _validated_payload(capability_id, payload)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            return _error_response(request_id, "rejected", "Input JSON is invalid or violates the capability contract.")

        registry = default_registry()
        capability = registry.get(capability_id)
        if capability.side_effect_class != "none" or capability.retry_safe is not True:
            return _error_response(request_id, "rejected", "Only declared pure, retry-safe capabilities may execute.")

        budget = ExecutionBudget(
            max_tasks=1,
            max_input_bytes=MAX_INPUT_BYTES,
            max_output_bytes=MAX_OUTPUT_BYTES,
            max_duration_seconds=MAX_DURATION_SECONDS,
        )
        context = RunContext.create(
            budget=budget,
            cancelled=cancelled.is_set,
            policy_snapshot={
                "interface": "ecosystem-decision-mcp/v1",
                "capability_id": capability_id,
                "side_effect_class": capability.side_effect_class,
                "retry_safe": capability.retry_safe,
            },
        )
        request_envelope = {"capability_id": capability_id, "input": payload}
        context.check_plan(1, request_envelope)
        context.begin_task(request_envelope)
        result = registry.run(capability_id, payload, context=context)
        context.checkpoint()
        response = {
            "request_id": request_id,
            "trace_id": context.trace_id,
            "status": "succeeded",
            "capability_id": capability_id,
            "result": result,
            "runtime": {
                "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                "tasks_started": context.ledger.tasks_started,
                "input_bytes": context.ledger.input_bytes,
                "output_bytes": context.ledger.output_bytes,
                "checkpoints": context.ledger.checkpoints,
                "max_duration_seconds": MAX_DURATION_SECONDS,
                "timeout_type": "cooperative",
            },
            "verification_note": "Only checks represented by the selected capability's result are claimed; this adapter adds no independent mathematical verification.",
        }
        context.check_output(response)
        response["runtime"]["output_bytes"] = context.ledger.output_bytes
        return _json_text(response)
    except ExecutionBudgetExceeded:
        return _error_response(request_id, "budget_exceeded", "The input, output, or cooperative runtime budget was exceeded.")
    except ExecutionCancelled:
        return _error_response(request_id, "cancelled", "The request was cancelled at a cooperative checkpoint.")
    except (InputRejected, RuntimePolicyError):
        return _error_response(request_id, "rejected", "The request violates the adapter's execution policy.")
    except Exception as exc:
        logger.warning("Decision capability failed: capability=%s error_type=%s", capability_id, type(exc).__name__)
        return _error_response(request_id, "failed", "The registered capability failed; input values are not logged.")
    finally:
        _run_lock.release()


@mcp.tool()
async def ecosystem_list_capabilities() -> str:
    """List the bounded, read-only decision capabilities exposed by this MCP server."""
    registry = default_registry()
    capabilities = [
        entry for entry in registry.describe()
        if entry["name"] in CAPABILITY_IDS
        and entry["side_effect_class"] == "none"
        and entry["retry_safe"] is True
    ]
    return _json_text({
        "service": "ecosystem-decision-mcp",
        "interface_version": "v1",
        "capabilities": capabilities,
        "limits": {
            "max_input_bytes": MAX_INPUT_BYTES,
            "max_output_bytes": MAX_OUTPUT_BYTES,
            "max_duration_seconds": MAX_DURATION_SECONDS,
            "timeout_type": "cooperative",
            "concurrent_runs": 1,
        },
    })


@mcp.tool()
async def ecosystem_run_capability(
    capability_id: CapabilityId,
    input_json: str,
) -> str:
    """Execute one allow-listed pure algorithm using bounded JSON input.

    input_json must be a JSON object conforming to the selected capability's
    registered input contract. No workflow, file, network, shell, or write tool
    is exposed through this interface.
    """
    cancelled = threading.Event()
    worker = asyncio.create_task(asyncio.to_thread(_execute, capability_id, input_json, cancelled))
    try:
        return await asyncio.wait_for(asyncio.shield(worker), timeout=TOOL_WAIT_SECONDS)
    except TimeoutError:
        cancelled.set()
        return _error_response(str(uuid.uuid4()), "budget_exceeded", "The request exceeded the adapter's cooperative time limit.")
    except asyncio.CancelledError:
        cancelled.set()
        raise


def main() -> None:
    """Run the adapter as a local MCP stdio server."""
    mcp.run()


if __name__ == "__main__":
    main()
