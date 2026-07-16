#!/usr/bin/env python3
"""Validate that a task config points at a real SWE-Perf checkout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]


REQUIRED_TASK_FIELDS = [
    "task_id",
    "dataset",
    "repo",
    "base_commit",
    "repo_path",
    "target_files",
    "target_functions",
    "performance_tests",
    "correctness_command",
    "performance_command",
    "invariant_context_path",
]


def resolve_from_root(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return ROOT / path


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"expected JSON object in {path}")
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    args = parser.parse_args()

    task_path = resolve_from_root(args.task)
    task = read_json(task_path)
    errors: list[str] = []

    for field in REQUIRED_TASK_FIELDS:
        if field not in task:
            errors.append(f"missing task field: {field}")

    if task.get("dataset") != "SWE-Perf":
        errors.append("dataset must be exactly 'SWE-Perf'")

    repo_path = resolve_from_root(str(task.get("repo_path", "")))
    if not repo_path.exists():
        errors.append(f"repo_path does not exist: {repo_path}")
    elif not (repo_path / ".git").exists():
        errors.append(f"repo_path is not a git checkout: {repo_path}")

    invariant_path = resolve_from_root(str(task.get("invariant_context_path", "")))
    if not invariant_path.exists():
        errors.append(f"invariant_context_path does not exist: {invariant_path}")
    else:
        invariants = read_json(invariant_path)
        if invariants.get("task_id") != task.get("task_id"):
            errors.append(
                "invariant task_id does not match task config: "
                f"{invariants.get('task_id')!r} != {task.get('task_id')!r}"
            )
        if not isinstance(invariants.get("invariants"), list):
            errors.append("invariant context must contain an invariants list")

    if errors:
        print("INVALID")
        for error in errors:
            print(f"- {error}")
        return 1

    print("VALID")
    print(f"task_id: {task['task_id']}")
    print(f"repo: {task['repo']}")
    print(f"base_commit: {task['base_commit']}")
    print(f"repo_path: {repo_path}")
    print(f"invariant_context_path: {invariant_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
