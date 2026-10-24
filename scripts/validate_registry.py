#!/usr/bin/env python3
"""Dependency-light consistency checks for the component registry and Markdown links."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "ecosystem" / "registry.json"
ALLOWED_STATUSES = {
    "design-only", "planned", "prototype-artifact",
    "integrated", "production-ready", "deprecated",
}
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


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
