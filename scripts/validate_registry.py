#!/usr/bin/env python3
"""Dependency-light consistency checks for the component registry and Markdown links."""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "ecosystem" / "registry.json"
PORTFOLIO_PATH = ROOT / "ecosystem" / "portfolio.json"
ALLOWED_STATUSES = {
    "design-only", "planned", "prototype-artifact",
    "integrated", "production-ready", "deprecated",
}
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
PORTFOLIO_MATURITY = {
    "deployed", "implemented-unverified", "prototype",
    "specification-only", "governance-only",
}
INTEGRATION_STATES = {
    "live-core", "adapter-to-core", "local-library",
    "standalone-mcp", "contract-only", "not-connected",
}
CONNECTION_STATES = {
    "implemented-but-not-end-to-end-verified",
    "proposed", "blocked", "not-proposed",
}
EVIDENCE_KINDS = {"source", "ci", "deployment", "test", "specification"}


def validate_registry(errors: list[str]) -> None:
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"Cannot read valid registry JSON: {exc}")
        return
    if data.get("schema_version") != "1.0.0":
        errors.append("schema_version must be 1.0.0")
    components = data.get("components")
    if not isinstance(components, list):
        errors.append("components must be a list")
        return

    seen: set[str] = set()
    required = {
        "id", "name", "type", "status", "version", "source", "target_path",
        "summary", "capabilities", "known_limitations", "validation",
    }
    for index, component in enumerate(components):
        prefix = f"components[{index}]"
        if not isinstance(component, dict):
            errors.append(f"{prefix} must be an object")
            continue
        missing = sorted(required - component.keys())
        if missing:
            errors.append(f"{prefix} missing fields: {', '.join(missing)}")
            continue
        component_id = component["id"]
        if not isinstance(component_id, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", component_id):
            errors.append(f"{prefix}.id must be kebab-case")
        elif component_id in seen:
            errors.append(f"Duplicate component id: {component_id}")
        else:
            seen.add(component_id)
        if component["status"] not in ALLOWED_STATUSES:
            errors.append(f"{prefix}.status is unknown")
        if not isinstance(component["capabilities"], list) or not isinstance(component["known_limitations"], list):
            errors.append(f"{prefix} capabilities/known_limitations must be lists")

        target = component["target_path"]
        if not isinstance(target, str) or not target.strip():
            errors.append(f"{prefix}.target_path must be a non-empty path")
        else:
            resolved = (ROOT / target).resolve()
            if ROOT not in resolved.parents and resolved != ROOT:
                errors.append(f"{prefix}.target_path escapes the repository")
            elif not resolved.exists():
                errors.append(f"{prefix}.target_path does not exist: {target}")

        validation = component["validation"]
        if not isinstance(validation, dict):
            errors.append(f"{prefix}.validation must be an object")
            continue
        for key in ("status", "tests", "date", "scope"):
            if key not in validation:
                errors.append(f"{prefix}.validation missing {key}")
        if validation.get("status") == "passed-locally":
            scope = validation.get("scope", "")
            note = validation.get("note", "")
            if "not this repository" not in scope and "not this repository" not in note:
                errors.append(f"{prefix} local validation must explicitly state its scope")


def _is_https_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def validate_portfolio(errors: list[str]) -> None:
    """Validate the cross-repository inventory without requiring network access."""
    try:
        data = json.loads(PORTFOLIO_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"Cannot read valid portfolio JSON: {exc}")
        return

    if data.get("schema_version") != "1.0.0":
        errors.append("portfolio schema_version must be 1.0.0")
    if data.get("registry") != "ecosystem/portfolio.json":
        errors.append("portfolio registry must be ecosystem/portfolio.json")
    if data.get("repository") != "looloofy69-sketch/Ecosystems-loofy":
        errors.append("portfolio repository must identify this canonical repository")
    try:
        date.fromisoformat(data.get("updated_at", ""))
    except (TypeError, ValueError):
        errors.append("portfolio updated_at must be an ISO date")

    policy = data.get("policy")
    if not isinstance(policy, dict) or not policy.get("production_claim_requires") or not isinstance(policy.get("rule"), str):
        errors.append("portfolio policy must define promotion requirements and a rule")

    components = data.get("components")
    if not isinstance(components, list) or not components:
        errors.append("portfolio components must be a non-empty list")
        return

    seen_ids: set[str] = set()
    seen_repositories: set[str] = set()
    required_component = {
        "id", "name", "repository_url", "role", "maturity", "integration_state",
        "production_endpoint", "dependencies", "interfaces", "known_gaps", "evidence",
    }
    for index, component in enumerate(components):
        prefix = f"portfolio.components[{index}]"
        if not isinstance(component, dict):
            errors.append(f"{prefix} must be an object")
            continue
        missing = sorted(required_component - component.keys())
        if missing:
            errors.append(f"{prefix} missing fields: {', '.join(missing)}")
            continue

        component_id = component["id"]
        if not isinstance(component_id, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", component_id):
            errors.append(f"{prefix}.id must be kebab-case")
        elif component_id in seen_ids:
            errors.append(f"Duplicate portfolio component id: {component_id}")
        else:
            seen_ids.add(component_id)

        repository_url = component["repository_url"]
        if not _is_https_url(repository_url) or not repository_url.startswith("https://github.com/looloofy69-sketch/"):
            errors.append(f"{prefix}.repository_url must be an HTTPS repository URL under the expected owner")
        elif repository_url in seen_repositories:
            errors.append(f"Duplicate portfolio repository URL: {repository_url}")
        else:
            seen_repositories.add(repository_url)

        if not isinstance(component["name"], str) or not component["name"].strip():
            errors.append(f"{prefix}.name must be non-empty")
        if not isinstance(component["role"], str) or not component["role"].strip():
            errors.append(f"{prefix}.role must be non-empty")
        if component["maturity"] not in PORTFOLIO_MATURITY:
            errors.append(f"{prefix}.maturity is unknown")
        if component["integration_state"] not in INTEGRATION_STATES:
            errors.append(f"{prefix}.integration_state is unknown")

        endpoint = component["production_endpoint"]
        if endpoint is not None and not _is_https_url(endpoint):
            errors.append(f"{prefix}.production_endpoint must be HTTPS or null")
        if component["maturity"] == "deployed" and endpoint is None:
            errors.append(f"{prefix} is marked deployed without a production endpoint")
        if component["maturity"] != "deployed" and endpoint is not None:
            errors.append(f"{prefix} has a production endpoint without deployed maturity")
        if component["integration_state"] == "live-core" and component["maturity"] != "deployed":
            errors.append(f"{prefix} live-core state requires deployed maturity")

        for field in ("dependencies", "interfaces", "known_gaps", "evidence"):
            if not isinstance(component[field], list):
                errors.append(f"{prefix}.{field} must be a list")
        if isinstance(component["dependencies"], list):
            if len(component["dependencies"]) != len(set(component["dependencies"])):
                errors.append(f"{prefix}.dependencies contains duplicates")
        for field in ("interfaces", "known_gaps"):
            values = component[field]
            if isinstance(values, list) and any(not isinstance(value, str) or not value.strip() for value in values):
                errors.append(f"{prefix}.{field} must contain non-empty strings")

        evidence = component["evidence"]
        if isinstance(evidence, list):
            for evidence_index, entry in enumerate(evidence):
                evidence_prefix = f"{prefix}.evidence[{evidence_index}]"
                if not isinstance(entry, dict):
                    errors.append(f"{evidence_prefix} must be an object")
                    continue
                if set(entry) != {"kind", "url", "claim"}:
                    errors.append(f"{evidence_prefix} must contain only kind, url, and claim")
                if entry.get("kind") not in EVIDENCE_KINDS:
                    errors.append(f"{evidence_prefix}.kind is unknown")
                if not _is_https_url(entry.get("url")):
                    errors.append(f"{evidence_prefix}.url must be HTTPS")
                if not isinstance(entry.get("claim"), str) or not entry.get("claim", "").strip():
                    errors.append(f"{evidence_prefix}.claim must be non-empty")

    for component in components:
        if not isinstance(component, dict) or not isinstance(component.get("dependencies"), list):
            continue
        component_id = component.get("id")
        for dependency in component["dependencies"]:
            if dependency == component_id:
                errors.append(f"portfolio component {component_id} cannot depend on itself")
            if dependency not in seen_ids:
                errors.append(f"portfolio component {component_id} has unknown dependency: {dependency}")

    connections = data.get("connections")
    if not isinstance(connections, list):
        errors.append("portfolio connections must be a list")
        return
    seen_connection_ids: set[str] = set()
    required_connection = {"id", "from", "to", "interface", "state", "required_gates"}
    for index, connection in enumerate(connections):
        prefix = f"portfolio.connections[{index}]"
        if not isinstance(connection, dict):
            errors.append(f"{prefix} must be an object")
            continue
        missing = sorted(required_connection - connection.keys())
        if missing:
            errors.append(f"{prefix} missing fields: {', '.join(missing)}")
            continue
        connection_id = connection["id"]
        if not isinstance(connection_id, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", connection_id):
            errors.append(f"{prefix}.id must be kebab-case")
        elif connection_id in seen_connection_ids:
            errors.append(f"Duplicate portfolio connection id: {connection_id}")
        else:
            seen_connection_ids.add(connection_id)
        for endpoint in ("from", "to"):
            if connection[endpoint] not in seen_ids:
                errors.append(f"{prefix}.{endpoint} references an unknown component")
        if connection.get("from") == connection.get("to"):
            errors.append(f"{prefix} cannot connect a component to itself")
        if connection["state"] not in CONNECTION_STATES:
            errors.append(f"{prefix}.state is unknown")
        if not isinstance(connection["interface"], str) or not connection["interface"].strip():
            errors.append(f"{prefix}.interface must be non-empty")
        gates = connection["required_gates"]
        if not isinstance(gates, list) or not gates or any(not isinstance(gate, str) or not gate.strip() for gate in gates):
            errors.append(f"{prefix}.required_gates must be a non-empty list of strings")


def validate_markdown_links(errors: list[str]) -> None:
    for markdown in sorted(ROOT.rglob("*.md")):
        if any(part in {".git", ".venv", "venv", "__pycache__"} for part in markdown.parts):
            continue
        try:
            content = markdown.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"Cannot read {markdown.relative_to(ROOT)}: {exc}")
            continue
        for raw_target in MARKDOWN_LINK.findall(content):
            target = raw_target.strip()
            if not target or target.startswith("#"):
                continue
            parsed = urlparse(target)
            if parsed.scheme or parsed.netloc:
                continue
            path_part = target.split("#", 1)[0].split("?", 1)[0]
            if not path_part:
                continue
            resolved = (markdown.parent / path_part).resolve()
            if ROOT not in resolved.parents and resolved != ROOT:
                errors.append(f"{markdown.relative_to(ROOT)} links outside repository: {target}")
            elif not resolved.exists():
                errors.append(f"Broken Markdown link in {markdown.relative_to(ROOT)}: {target}")


def main() -> int:
    errors: list[str] = []
    validate_registry(errors)
    validate_portfolio(errors)
    validate_markdown_links(errors)
    if errors:
        print("Repository validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Repository validation passed: registry fields, target paths, and Markdown links are consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
