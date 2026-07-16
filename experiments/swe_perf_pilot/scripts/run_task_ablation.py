#!/usr/bin/env python3
"""Generate and optionally run a SWE-Perf plain-vs-invariant ablation.

This script is intentionally small and dependency-free. It does not know about
one invariant miner. It standardizes one intervention over real SWE-Perf tasks:
plain task context vs. the same task context plus structured invariants.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
PILOT_ROOT = ROOT / "experiments" / "swe_perf_pilot"
TEMPLATE_PATH = PILOT_ROOT / "config" / "prompt_templates.json"
RESULTS_ROOT = PILOT_ROOT / "results"


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"expected JSON object in {path}")
    return data


def require_fields(data: dict[str, Any], fields: list[str], label: str) -> None:
    missing = [field for field in fields if field not in data]
    if missing:
        raise SystemExit(f"{label} missing required field(s): {', '.join(missing)}")


def resolve_from_root(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return ROOT / path


def format_list(values: Any) -> str:
    if isinstance(values, list):
        return "\n".join(f"- {value}" for value in values)
    return str(values)


def build_prompts(task: dict[str, Any], invariants: dict[str, Any]) -> dict[str, str]:
    templates = read_json(TEMPLATE_PATH)
    require_fields(templates, ["plain", "invariant"], "prompt templates")
    invariant_context = json.dumps(invariants, indent=2, ensure_ascii=False)
    values = {
        "task_id": task["task_id"],
        "dataset": task["dataset"],
        "repo": task["repo"],
        "base_commit": task["base_commit"],
        "repo_path": str(resolve_from_root(task["repo_path"])),
        "target_files": format_list(task.get("target_files", [])),
        "target_functions": format_list(task.get("target_functions", [])),
        "performance_tests": format_list(task.get("performance_tests", [])),
        "correctness_command": task["correctness_command"],
        "performance_command": task["performance_command"],
        "invariant_context": invariant_context,
    }
    return {
        "plain": templates["plain"].format(**values),
        "invariant": templates["invariant"].format(**values),
    }


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run_command(command: str, repo_path: Path, timeout: int) -> dict[str, Any]:
    result = subprocess.run(
        command,
        cwd=repo_path,
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=timeout,
    )
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-4000:],
    }


def run_codex(prompt: str, repo_path: Path, output_path: Path) -> dict[str, Any]:
    cmd = [
        "codex",
        "-a",
        "never",
        "exec",
        "--cd",
        str(repo_path),
        "--skip-git-repo-check",
        "--ephemeral",
        "--sandbox",
        "read-only",
        "--output-last-message",
        str(output_path),
        prompt,
    ]
    env = os.environ.copy()
    result = subprocess.run(
        cmd,
        cwd=repo_path,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=600,
    )
    return {
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-4000:],
        "output_path": str(output_path),
    }


def score_message(text: str, invariants: dict[str, Any]) -> dict[str, Any]:
    lowered = text.lower()
    named_invariant_ids = [
        str(item.get("id", "")).lower()
        for item in invariants.get("invariants", [])
        if isinstance(item, dict) and item.get("id")
    ]
    checks = {
        "mentions_invariant": any(
            word in lowered for word in ["invariant", "precondition", "equivalence", "equivalent"]
        ),
        "mentions_boundary_case": any(
            word in lowered for word in ["boundary", "counterexample", "unsafe", "naive", "cross"]
        ),
        "mentions_cost_evidence": any(
            word in lowered for word in ["benchmark", "speedup", "elapsed", "parse_key calls", "lower_is_better"]
        ),
        "mentions_correctness_evidence": any(
            word in lowered for word in ["test", "unittest", "correctness", "passed", "ok"]
        ),
        "mentions_specific_safety_condition": any(
            phrase in lowered
            for phrase in [
                "only when",
                "safe if",
                "safe when",
                "requires",
                "precondition",
                "must hold",
            ]
        ),
        "uses_named_invariant_evidence": any(invariant_id in lowered for invariant_id in named_invariant_ids),
        "distinguishes_candidate_from_verified_patch": any(
            phrase in lowered
            for phrase in [
                "candidate patch idea",
                "safety argument",
                "expected performance effect",
                "tests run",
            ]
        ),
    }
    score = sum(1 for value in checks.values() if value)
    return {
        **checks,
        "diagnostic_score": score,
    }


def score_existing_output(path: Path, invariants: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return {"missing": True, "diagnostic_score": 0}
    return score_message(path.read_text(encoding="utf-8", errors="replace"), invariants)


def swe_perf_primary_metrics(task: dict[str, Any], verification: dict[str, Any]) -> dict[str, Any]:
    correctness = verification.get("correctness")
    performance = verification.get("performance")
    correctness_passed = (
        correctness.get("returncode") == 0 if isinstance(correctness, dict) else None
    )
    performance_command_completed = (
        performance.get("returncode") == 0 if isinstance(performance, dict) else None
    )
    return {
        "dataset": "SWE-Perf",
        "instance_id": task["task_id"],
        "apply": None,
        "correctness": correctness_passed,
        "performance_command_completed": performance_command_completed,
        "performance_improved": None,
        "runtime_gain": None,
        "resolved": None,
        "note": (
            "Primary scoring should be filled by the official SWE-Perf evaluator. "
            "This runner records command completion locally and keeps semantic "
            "evidence as diagnostic-only metadata."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True, help="Path to a task config JSON file.")
    parser.add_argument("--dry-run", action="store_true", help="Only validate and write prompts.")
    parser.add_argument("--verify-commands", action="store_true", help="Run correctness and performance commands from the task config.")
    parser.add_argument("--run-codex", action="store_true", help="Actually run Codex for both prompt conditions.")
    parser.add_argument("--score-existing", action="store_true", help="Compute diagnostic semantic-evidence scores for existing Codex outputs.")
    args = parser.parse_args()

    selected_modes = [args.dry_run, args.run_codex, args.score_existing]
    if sum(1 for selected in selected_modes if selected) > 1:
        raise SystemExit("choose only one of --dry-run, --run-codex, or --score-existing")

    task_path = resolve_from_root(args.task)
    task = read_json(task_path)
    require_fields(
        task,
        [
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
        ],
        "task config",
    )
    if task["dataset"] != "SWE-Perf":
        raise SystemExit(
            f"expected a real SWE-Perf task config with dataset='SWE-Perf', got {task['dataset']!r}"
        )

    invariant_path = resolve_from_root(task["invariant_context_path"])
    invariants = read_json(invariant_path)
    require_fields(invariants, ["task_id", "invariants"], "invariant context")

    if invariants["task_id"] != task["task_id"]:
        raise SystemExit(
            f"task_id mismatch: task has {task['task_id']}, invariants have {invariants['task_id']}"
        )

    prompts = build_prompts(task, invariants)
    result_dir = RESULTS_ROOT / task["task_id"]
    write_text(result_dir / "plain_prompt.md", prompts["plain"])
    write_text(result_dir / "invariant_prompt.md", prompts["invariant"])

    summary: dict[str, Any] = {
        "task_id": task["task_id"],
        "mode": "run-codex" if args.run_codex else "score-existing" if args.score_existing else "dry-run",
        "prompt_outputs": {
            "plain": str(result_dir / "plain_prompt.md"),
            "invariant": str(result_dir / "invariant_prompt.md"),
        },
        "invariant_count": len(invariants.get("invariants", [])),
        "verification": {},
        "codex": {},
        "swe_perf_primary_metrics": {},
        "diagnostic_semantic_evidence": {},
    }

    repo_path = resolve_from_root(task["repo_path"])

    if args.verify_commands:
        summary["verification"]["correctness"] = run_command(
            task["correctness_command"],
            repo_path,
            timeout=120,
        )
        summary["verification"]["performance"] = run_command(
            task["performance_command"],
            repo_path,
            timeout=120,
        )
        summary["swe_perf_primary_metrics"] = swe_perf_primary_metrics(task, summary["verification"])

    if args.run_codex:
        summary["codex"]["plain"] = run_codex(
            prompts["plain"],
            repo_path,
            result_dir / "plain_codex_last_message.md",
        )
        summary["codex"]["invariant"] = run_codex(
            prompts["invariant"],
            repo_path,
            result_dir / "invariant_codex_last_message.md",
        )

    if args.run_codex or args.score_existing:
        plain_score = score_existing_output(result_dir / "plain_codex_last_message.md", invariants)
        invariant_score = score_existing_output(result_dir / "invariant_codex_last_message.md", invariants)
        summary["diagnostic_semantic_evidence"] = {
            "plain": plain_score,
            "invariant": invariant_score,
            "delta": invariant_score.get("diagnostic_score", 0) - plain_score.get("diagnostic_score", 0),
            "note": "Diagnostic only. Primary evaluation follows SWE-Perf apply/correctness/performance metrics.",
        }

    write_text(result_dir / "summary.json", json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
