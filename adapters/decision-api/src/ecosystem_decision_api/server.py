"""Private HTTP bridge for the bounded, pure decision capability adapter.

The service reuses the exact same fixed capability runner as the local MCP
server. It never accepts arbitrary code, URLs, file paths, or workflow documents.
"""
from __future__ import annotations

import asyncio
from collections import deque
import hashlib
import hmac
import json
import logging
import os
import threading
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ecosystem_decision_mcp.server import (
    CAPABILITY_IDS,
    MAX_INPUT_BYTES,
    MAX_OUTPUT_BYTES,
    TOOL_WAIT_SECONDS,
    _execute,
    _reject_constant,
)

logging.basicConfig(level=os.getenv("LOG_LEVEL", "WARNING").upper())
logger = logging.getLogger("ecosystem_decision_api")

MAX_REQUEST_BODY_BYTES = MAX_INPUT_BYTES + 4096
RATE_WINDOW_SECONDS = 60.0
DEFAULT_RATE_LIMIT_PER_MINUTE = 30
MIN_TOKEN_LENGTH = 32


class SlidingWindowRateLimiter:
    """Per-process, per-service-token request limiter; no caller-controlled identity."""

    def __init__(self, max_requests: int, window_seconds: float = RATE_WINDOW_SECONDS) -> None:
        if isinstance(max_requests, bool) or not isinstance(max_requests, int) or max_requests < 1:
            raise ValueError("max_requests must be a positive integer")
        if not isinstance(window_seconds, (int, float)) or window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.max_requests = max_requests
        self.window_seconds = float(window_seconds)
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        with self._lock:
            events = self._events.setdefault(key, deque())
            cutoff = current - self.window_seconds
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.max_requests:
                return False
            events.append(current)
            return True


def _error(status: str, message: str, http_status: int, *, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=http_status,
        content={"status": status, "error": {"message": message}},
        headers=headers,
    )


def _authorize(request: Request) -> tuple[str | None, JSONResponse | None]:
    expected = os.getenv("EL_ROUJI_DECISION_API_TOKEN", "")
    if len(expected) < MIN_TOKEN_LENGTH:
        return None, _error(
            "unavailable",
            "Service authentication is not configured.",
            503,
        )

    auth_header = request.headers.get("authorization", "")
    scheme, separator, presented = auth_header.partition(" ")
    if not separator or scheme.lower() != "bearer" or not presented:
        return None, _error(
            "unauthorized",
            "A valid service bearer token is required.",
            401,
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not hmac.compare_digest(presented, expected):
        return None, _error(
            "unauthorized",
            "A valid service bearer token is required.",
            401,
            headers={"WWW-Authenticate": "Bearer"},
        )
    token_fingerprint = hashlib.sha256(expected.encode("utf-8")).hexdigest()
    return token_fingerprint, None


def _loads_strict(raw: bytes) -> Any:
    try:
        decoded = raw.decode("utf-8")
        return json.loads(decoded, parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("Request body must contain valid UTF-8 JSON with finite numbers.") from exc


def _http_status_for_execution(status: str) -> int:
    return {
        "succeeded": 200,
        "rejected": 422,
        "budget_exceeded": 408,
        "cancelled": 408,
        "busy": 429,
        "failed": 500,
    }.get(status, 502)


def create_app(*, rate_limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE) -> FastAPI:
    app = FastAPI(
        title="Ecosystem Decision API",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    rate_limiter = SlidingWindowRateLimiter(rate_limit_per_minute)

    @app.get("/health")
    async def health() -> dict[str, bool]:
        # Deliberately public and minimal: do not report secrets, dependency versions,
        # configuration details, or whether the service token has been configured.
        return {"ok": True}

    @app.get("/v1/capabilities")
    async def list_capabilities(request: Request):
        _, denial = _authorize(request)
        if denial is not None:
            return denial
        from ecosystem_decision_mcp.server import default_registry

        registry = default_registry()
        records = [
            item for item in registry.describe()
            if item["name"] in CAPABILITY_IDS
            and item["side_effect_class"] == "none"
            and item["retry_safe"] is True
        ]
        return {
            "interface_version": "v1",
            "capabilities": records,
            "limits": {
                "max_input_bytes": MAX_INPUT_BYTES,
                "max_output_bytes": MAX_OUTPUT_BYTES,
                "max_duration_seconds": 4.0,
                "timeout_type": "cooperative",
                "concurrent_runs": 1,
                "rate_limit_per_minute": rate_limit_per_minute,
            },
        }

    @app.post("/v1/run")
    async def run_capability(request: Request):
        fingerprint, denial = _authorize(request)
        if denial is not None:
            return denial
        assert fingerprint is not None

        if not rate_limiter.allow(fingerprint):
            return _error(
                "rate_limited",
                "The service request limit was reached. Retry after the current rate window.",
                429,
                headers={"Retry-After": str(int(RATE_WINDOW_SECONDS))},
            )

        declared_length = request.headers.get("content-length")
        if declared_length:
            try:
                if int(declared_length) > MAX_REQUEST_BODY_BYTES:
                    return _error("rejected", "Request body exceeds the configured byte limit.", 413)
            except ValueError:
                return _error("rejected", "Content-Length header is invalid.", 400)

        raw = await request.body()
        if len(raw) > MAX_REQUEST_BODY_BYTES:
            return _error("rejected", "Request body exceeds the configured byte limit.", 413)

        try:
            body = _loads_strict(raw)
        except ValueError:
            return _error("rejected", "Request body must be valid UTF-8 JSON with finite numbers.", 400)

        if not isinstance(body, dict) or set(body) != {"capability_id", "input"}:
            return _error(
                "rejected",
                "Body must contain exactly capability_id and input.",
                400,
            )
        capability_id = body["capability_id"]
        payload = body["input"]
        if not isinstance(capability_id, str) or capability_id not in CAPABILITY_IDS:
            return _error("rejected", "Capability is not on the service allow-list.", 422)
        if not isinstance(payload, dict):
            return _error("rejected", "input must be a JSON object.", 422)

        try:
            input_json = json.dumps(
                payload,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
        except (TypeError, ValueError):
            return _error("rejected", "input must contain finite JSON-compatible values.", 422)
        if len(input_json.encode("utf-8")) > MAX_INPUT_BYTES:
            return _error("rejected", "Serialized input exceeds the configured byte limit.", 413)

        cancelled = threading.Event()
        worker = asyncio.create_task(
            asyncio.to_thread(_execute, capability_id, input_json, cancelled)
        )
        try:
            result_text = await asyncio.wait_for(
                asyncio.shield(worker),
                timeout=TOOL_WAIT_SECONDS,
            )
        except TimeoutError:
            cancelled.set()
            return _error(
                "budget_exceeded",
                "The computation exceeded the service's cooperative time limit.",
                408,
            )
        except asyncio.CancelledError:
            cancelled.set()
            raise

        try:
            result = json.loads(result_text, parse_constant=_reject_constant)
        except (ValueError, json.JSONDecodeError):
            logger.error("Decision executor returned non-JSON output.")
            return _error("failed", "Decision executor returned an invalid response.", 502)

        if not isinstance(result, dict) or not isinstance(result.get("status"), str):
            return _error("failed", "Decision executor returned an unexpected response shape.", 502)
        status = result["status"]
        http_status = _http_status_for_execution(status)
        if status == "busy":
            return JSONResponse(status_code=http_status, content=result, headers={"Retry-After": "1"})
        return JSONResponse(status_code=http_status, content=result)

    return app


app = create_app()


def main() -> None:
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    try:
        port = int(os.getenv("PORT", "8080"))
    except ValueError as exc:
        raise SystemExit("PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise SystemExit("PORT must be between 1 and 65535")
    uvicorn.run(app, host=host, port=port, log_level=os.getenv("LOG_LEVEL", "warning").lower())


if __name__ == "__main__":
    main()
