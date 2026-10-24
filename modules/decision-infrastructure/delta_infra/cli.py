"""Command-line entry point for the default capability registry."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Any
from .registry import default_registry


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a registered delta-infrastructure algorithm")
    parser.add_argument("instance", type=Path, nargs="?", help="JSON input instance")
    parser.add_argument("--capability", default="matching.signed_greedy")
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--list-capabilities", action="store_true")
    args = parser.parse_args()
    registry = default_registry()
    if args.list_capabilities:
        print(json.dumps(registry.describe(), indent=2 if args.pretty else None))
        return
    if args.instance is None:
        parser.error("instance is required unless --list-capabilities is specified")
    payload: dict[str, Any] = json.loads(args.instance.read_text(encoding="utf-8"))
    result = registry.run(args.capability, payload)
    print(json.dumps(result, indent=2 if args.pretty else None, default=str))

if __name__ == "__main__":
    main()
