#!/usr/bin/env python3
"""Run Codex on SWE-Perf with Daikon skill output as a tool result."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from run_codex_sweperf_baseline import (
    MODEL_NAME,
    ROOT,
    ensure_official_repo,
    load_dataset_subset,
    make_oracle_prompt_dataset,
    run_capture,
    run_official_evaluation,
    run_transfer_repair,
    write_manifest,
)


def run_skill_report(skill_dir: Path, context_file: Path, target: str, output_path: Path) -> str:
    tool = skill_dir / "scripts" / "invariant_tool.py"
    if not tool.exists():
        raise SystemExit(f"Daikon skill tool not found: {tool}")
    output = run_capture(
        [
            sys.executable,
            str(tool),
            "--context",
            str(context_file),
            "--target",
            target,
            "--limit",
            "12",
            "--performance-json",
        ],
        cwd=ROOT,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output, encoding="utf-8")
    return output


def run_codex_with_tool_result(
    prompt_dataset: Path,
    output_dir: Path,
    skill_report_by_instance: dict[str, str],
    instance_ids: list[str],
) -> Path:
    from datasets import load_from_disk

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_output_path = output_dir / "codex__oracle__test.jsonl"
    dataset = load_from_disk(str(prompt_dataset))
    if "test" in dataset:
        dataset = dataset["test"]
    wanted = set(instance_ids)
    dataset = dataset.filter(lambda row: row["instance_id"] in wanted, load_from_cache_file=False)

    completed: set[str] = set()
    if raw_output_path.exists():
        for line in raw_output_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                completed.add(json.loads(line)["instance_id"])

    scratch = output_dir / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    for datum in dataset:
        instance_id = datum["instance_id"]
        if instance_id in completed:
            continue
        tool_report = skill_report_by_instance.get(instance_id, "")
        prompt = "\n\n".join(
            [
                datum["text"],
                "You may use the following standardized tool result from daikon-invariant-mining. It contains dynamic runtime evidence and performance-rewrite guidance, not proof.",
                "[Tool: daikon-invariant-mining]\n" + tool_report.strip() + "\n[/Tool]",
                "Use this tool result only when it is local to the candidate edit. Treat rewrite opportunities as generic hints. Preserve fallback behavior outside observed preconditions.",
                "Return only SEARCH/REPLACE edits in the requested format. Do not include explanations outside the patch blocks.",
            ]
        )
        prompt_path = output_dir / f"{instance_id}.prompt.txt"
        last_message = output_dir / f"{instance_id}.last_message.txt"
        prompt_path.write_text(prompt, encoding="utf-8")
        cmd = [
            "codex",
            "-a",
            "never",
            "exec",
            "--cd",
            str(scratch),
            "--skip-git-repo-check",
            "--ephemeral",
            "--sandbox",
            "workspace-write",
            "--output-last-message",
            str(last_message),
            prompt,
        ]
        try:
            stdout = run_capture(cmd, cwd=ROOT, timeout=900)
            full_output = last_message.read_text(encoding="utf-8", errors="replace") if last_message.exists() else stdout
        except subprocess.CalledProcessError as exc:
            full_output = exc.stdout or ""
        record = {
            "instance_id": instance_id,
            "model_name_or_path": MODEL_NAME,
            "full_output": full_output,
            "model_patch": "",
        }
        with raw_output_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return raw_output_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--official-repo", default="/tmp/swe-perf-official")
    parser.add_argument("--dataset-name-or-path", default="data/sweperf_small.jsonl")
    parser.add_argument(
        "--prompt-dataset",
        default=None,
        help="Optional prebuilt official SWE-Perf prompt dataset. When set, skip prompt generation.",
    )
    parser.add_argument("--work-dir", default="experiments/swe_perf_pilot/results/codex_daikon_skill_16058")
    parser.add_argument("--instance-id", default="astropy__astropy-16058")
    parser.add_argument("--target", default="validate_power")
    parser.add_argument("--context-file", default="experiments/swe_perf_pilot/invariants/astropy__astropy-16058.real-daikon.json")
    parser.add_argument("--skill-dir", default="codex-skills/daikon-invariant-mining")
    parser.add_argument("--run-codex", action="store_true")
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument("--run-id", default="codex_daikon_skill_16058")
    parser.add_argument("--max-workers", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()

    official_repo = Path(args.official_repo).resolve()
    work_dir = (ROOT / args.work_dir).resolve() if not Path(args.work_dir).is_absolute() else Path(args.work_dir)
    raw_subset_dir = work_dir / "raw_subset"
    base_dataset_dir = work_dir / "base_datasets"
    codex_output_dir = work_dir / "codex_outputs"
    predictions_dir = work_dir / "predictions"
    context_file = (ROOT / args.context_file).resolve() if not Path(args.context_file).is_absolute() else Path(args.context_file)
    skill_dir = (ROOT / args.skill_dir).resolve() if not Path(args.skill_dir).is_absolute() else Path(args.skill_dir)

    ensure_official_repo(official_repo)
    instance_ids = load_dataset_subset(
        args.dataset_name_or_path,
        raw_subset_dir,
        None,
        [args.instance_id],
    )
    if args.prompt_dataset:
        prompt_dataset = Path(args.prompt_dataset)
        if not prompt_dataset.is_absolute():
            prompt_dataset = (ROOT / prompt_dataset).resolve()
        if not prompt_dataset.exists():
            raise SystemExit(f"prompt dataset does not exist: {prompt_dataset}")
    else:
        prompt_dataset = make_oracle_prompt_dataset(official_repo, raw_subset_dir, base_dataset_dir)

    tool_report_path = work_dir / "tool_reports" / f"{args.instance_id}.daikon-performance-guidance.json"
    tool_report = run_skill_report(skill_dir, context_file, args.target, tool_report_path)

    manifest: dict[str, Any] = {
        "dataset": args.dataset_name_or_path,
        "setting": "oracle",
        "agent": "Codex CLI",
        "prompt_label": "daikon-skill",
        "tool_result_schema": "daikon-performance-guidance-v1",
        "tool_result_mode": "performance-guidance-json",
        "model_name_or_path": MODEL_NAME,
        "official_repo": str(official_repo),
        "work_dir": str(work_dir),
        "instance_ids": instance_ids,
        "prompt_dataset": str(prompt_dataset),
        "skill_dir": str(skill_dir),
        "skill_tool": str(skill_dir / "scripts" / "invariant_tool.py"),
        "context_file": str(context_file),
        "tool_report": str(tool_report_path),
        "tool_report_preview": tool_report,
        "definition": "Codex CLI on official SWE-Perf oracle prompt with Daikon skill output inserted as a tool result.",
    }

    raw_output_path = codex_output_dir / "codex__oracle__test.jsonl"
    if args.run_codex:
        raw_output_path = run_codex_with_tool_result(
            prompt_dataset,
            codex_output_dir,
            {args.instance_id: tool_report},
            instance_ids,
        )
        manifest["raw_codex_output"] = str(raw_output_path)
        repair_path = run_transfer_repair(official_repo, raw_output_path, prompt_dataset, predictions_dir)
        manifest["predictions_path"] = str(repair_path)
    elif raw_output_path.exists():
        repair_path = run_transfer_repair(official_repo, raw_output_path, prompt_dataset, predictions_dir)
        manifest["raw_codex_output"] = str(raw_output_path)
        manifest["predictions_path"] = str(repair_path)

    if args.evaluate:
        predictions_path = Path(manifest.get("predictions_path", predictions_dir / "codex__oracle__test_repair.jsonl"))
        if not predictions_path.exists():
            raise SystemExit("no predictions found; run with --run-codex first")
        csv_path = run_official_evaluation(
            official_repo,
            args.dataset_name_or_path,
            predictions_path,
            work_dir,
            args.run_id,
            args.max_workers,
            args.timeout,
        )
        manifest["official_evaluation_csv"] = str(csv_path)

    write_manifest(work_dir / "manifest.json", manifest)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
