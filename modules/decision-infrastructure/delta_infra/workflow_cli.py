"""CLI for running declarative workflow DAGs and browsing durable run history."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .runtime import ExecutionBudgetExceeded, RuntimePolicyError
from .workflow import TaskExecutionController, WorkflowDefinitionError, WorkflowInputError, WorkflowRunStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an approved, declarative Delta-Infrastructure workflow")
    parser.add_argument("workflow", nargs="?", type=Path, help="Workflow JSON file")
    parser.add_argument("--db", default=".delta-infra-runs.sqlite3", help="SQLite run ledger path")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    parser.add_argument("--approve", nargs="*", default=[], metavar="TASK_ID",
                        help="Explicitly approve tasks that declare requires_approval=true")
    parser.add_argument("--history", action="store_true", help="List recent runs instead of executing a workflow")
    parser.add_argument("--show-run", metavar="RUN_ID", help="Print a previously saved run")
    parser.add_argument("--resume", metavar="RUN_ID", help="Resume a compatible checkpointed run from the same workflow JSON and SQLite database")
    parser.add_argument("--limit", type=int, default=20, help="Maximum recent runs to show with --history (1..1000)")
    args = parser.parse_args()
    selected_modes = sum(bool(value) for value in (args.history, args.show_run, args.resume))
    if selected_modes > 1:
        parser.error("--history, --show-run, and --resume are mutually exclusive modes")

    store = WorkflowRunStore(args.db)
    if args.history:
        output: Any = store.list_runs(args.limit)
    elif args.show_run:
        output = store.get(args.show_run)
        if output is None:
            print(f"No workflow run found for {args.show_run}", file=sys.stderr)
            raise SystemExit(2)
    else:
        if args.workflow is None:
            parser.error("workflow JSON path is required unless --history or --show-run is specified")
        try:
            workflow = json.loads(args.workflow.read_text(encoding="utf-8"))
        except OSError as exc:
            parser.error(f"Cannot read workflow file: {exc}")
        except json.JSONDecodeError as exc:
            parser.error(f"Invalid workflow JSON: {exc}")
        controller = TaskExecutionController(run_store=store)
        try:
            if args.resume:
                output = controller.run(workflow, approved_task_ids=args.approve, resume_from_run_id=args.resume)
            else:
                output = controller.run(workflow, approved_task_ids=args.approve)
        except (WorkflowDefinitionError, WorkflowInputError, ExecutionBudgetExceeded, RuntimePolicyError) as exc:
            print(f"workflow error: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
    print(json.dumps(output, indent=2 if args.pretty else None, ensure_ascii=False, allow_nan=False, default=str))
    if isinstance(output, dict) and output.get("status") in {"failed", "blocked"}:
        raise SystemExit(1)
    if isinstance(output, dict) and output.get("status") == "approval_required":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
