#!/usr/bin/env python3
"""Small-scale Codex baseline under the official SWE-Perf oracle protocol."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
OFFICIAL_REPO_URL = "https://github.com/SWE-Perf/SWE-Perf.git"
DEFAULT_DATASET_NAME = "SWE-Perf/SWE-Perf"
MODEL_NAME = "codex-cli"


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None, timeout: int | None = None) -> None:
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, env=env, check=True, timeout=timeout)


def run_capture(cmd: list[str], cwd: Path, env: dict[str, str] | None = None, timeout: int | None = None) -> str:
    print("+ " + " ".join(cmd), flush=True)
    result = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
        timeout=timeout,
    )
    return result.stdout


def ensure_official_repo(path: Path) -> None:
    if path.exists():
        if not (path / ".git").exists():
            raise SystemExit(f"official repo path exists but is not a git checkout: {path}")
        return
    run(["git", "clone", OFFICIAL_REPO_URL, str(path)], cwd=Path("/tmp"))


def require_python_module(module: str) -> None:
    try:
        __import__(module)
    except ImportError as exc:
        raise SystemExit(
            f"missing Python module {module!r}. Create the official SWE-Perf environment first."
        ) from exc


def load_dataset_subset(
    dataset_name_or_path: str,
    raw_subset_dir: Path,
    max_instances: int | None,
    instance_ids: list[str] | None,
) -> list[str]:
    require_python_module("datasets")
    from datasets import Dataset, load_dataset, load_from_disk

    dataset_path = Path(dataset_name_or_path)
    if dataset_path.exists() and dataset_path.suffix == ".json":
        data = json.loads(dataset_path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "rows" in data:
            data = [row["row"] for row in data["rows"]]
        if not isinstance(data, list):
            raise SystemExit(f"expected list of SWE-Perf rows in {dataset_path}")
        dataset = Dataset.from_list(data)
    elif dataset_path.exists() and dataset_path.suffix == ".jsonl":
        data = [
            json.loads(line)
            for line in dataset_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        dataset = Dataset.from_list(data)
    elif dataset_path.exists():
        loaded = load_from_disk(str(dataset_path))
        dataset = loaded["test"] if "test" in loaded else loaded
    else:
        dataset = load_dataset(dataset_name_or_path, split="test")
    if instance_ids:
        wanted = set(instance_ids)
        dataset = dataset.filter(lambda row: row["instance_id"] in wanted, load_from_cache_file=False)
        found = set(dataset["instance_id"])
        missing = wanted - found
        if missing:
            raise SystemExit(f"unknown SWE-Perf instance id(s): {', '.join(sorted(missing))}")
    elif max_instances is not None:
        dataset = dataset.select(range(min(max_instances, len(dataset))))
    else:
        raise SystemExit("pass --max-instances or --instance-ids for small-scale reproduction")

    raw_subset_dir.parent.mkdir(parents=True, exist_ok=True)
    if raw_subset_dir.exists():
        shutil.rmtree(raw_subset_dir)
    Dataset.from_list(dataset.to_list()).save_to_disk(str(raw_subset_dir))
    return list(dataset["instance_id"])


def make_oracle_prompt_dataset(official_repo: Path, raw_subset_dir: Path, base_dataset_dir: Path) -> Path:
    if base_dataset_dir.exists():
        shutil.rmtree(base_dataset_dir)
    base_dataset_dir.mkdir(parents=True, exist_ok=True)
    run(
        [
            sys.executable,
            "-m",
            "make_datasets.create_text_dataset",
            "--dataset_name_or_path",
            str(raw_subset_dir),
            "--output_dir",
            str(base_dataset_dir),
            "--prompt_style",
            "efficiency",
            "--file_source",
            "oracle",
            "--split",
            "test",
        ],
        cwd=official_repo / "generation" / "oracle",
    )
    output_name = f"{raw_subset_dir.name}__efficiency__fs-oracle"
    prompt_dataset = base_dataset_dir / output_name
    if not prompt_dataset.exists():
        raise SystemExit(f"expected prompt dataset was not created: {prompt_dataset}")
    return prompt_dataset


def extract_diff(text: str) -> str:
    if not text:
        return ""
    tagged = re.findall(r"<(?:diff|patch)>(.*?)</(?:diff|patch)>", text, flags=re.DOTALL | re.IGNORECASE)
    if tagged:
        return tagged[0].strip() + "\n"
    fenced = re.findall(r"```(?:diff|patch)?\n(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    for block in fenced:
        if "--- a/" in block and "+++ b/" in block:
            return block.strip() + "\n"
    idx = text.find("diff --git ")
    if idx >= 0:
        return text[idx:].strip() + "\n"
    idx = text.find("--- a/")
    if idx >= 0:
        return text[idx:].strip() + "\n"
    return ""


def format_invariant_context(path: Path | None) -> str:
    if path is None:
        return ""
    data = json.loads(path.read_text(encoding="utf-8"))
    candidates = data.get("agent_context_candidates", [])
    by_ppt = data.get("likely_invariants_by_program_point", {})
    selected: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in candidates:
        key = (item.get("program_point", ""), item.get("likely_invariant", ""))
        if key[0] and key[1] and key not in seen:
            selected.append({"program_point": key[0], "likely_invariant": key[1]})
            seen.add(key)
    if not selected:
        for ppt, invariants in by_ppt.items():
            for invariant in invariants[:8]:
                selected.append({"program_point": ppt, "likely_invariant": invariant})

    lines = [
        "Additional machine-mined semantic context:",
        "",
        f"Source: {data.get('trace_source') or data.get('source')}",
        f"Task: {data.get('task_id')}",
    ]
    if "runtime_trace_rows" in data:
        lines.append(
            f"Trace: {data['runtime_trace_rows']} runtime observations "
            f"({data.get('deduplicated_trace_rows', 'unknown')} unique observed shapes)."
        )
    lines.extend(
        [
            "",
            "Daikon mined the following likely invariants from observed SWE-Perf executions.",
            "Treat them as optimization hints and safety conditions, not as proof.",
            "Preserve the original semantics for unobserved boundary cases.",
            "",
            "Likely invariants:",
        ]
    )
    for item in selected[:30]:
        lines.append(f"- {item['program_point']}: {item['likely_invariant']}")
    lines.extend(
        [
            "",
            "Optimization guidance:",
            "- Prefer fast paths only when the mined path condition justifies them.",
            "- Preserve numeric value and type-normalization behavior.",
            "- Avoid deleting conversion or validation logic for cases not covered by the invariants.",
        ]
    )
    return "\n".join(lines).strip()


def resolve_invariant_context(context_path: Path | None, instance_id: str) -> Path | None:
    if context_path is None:
        return None
    if context_path.is_dir():
        candidate = context_path / f"{instance_id}.real-daikon.json"
        if candidate.exists():
            return candidate
        return None
    return context_path


def run_codex_on_prompts(
    prompt_dataset: Path,
    output_dir: Path,
    max_instances: int | None,
    invariant_context_file: Path | None = None,
) -> Path:
    require_python_module("datasets")
    from datasets import load_from_disk

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_output_path = output_dir / "codex__oracle__test.jsonl"
    dataset = load_from_disk(str(prompt_dataset))
    if "test" in dataset:
        dataset = dataset["test"]
    if max_instances is not None:
        dataset = dataset.select(range(min(max_instances, len(dataset))))

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
        invariant_context = format_invariant_context(resolve_invariant_context(invariant_context_file, instance_id))
        last_message = output_dir / f"{instance_id}.last_message.txt"
        prompt_parts = [datum["text"]]
        if invariant_context:
            prompt_parts.append(invariant_context)
        prompt_parts.append("Return only a unified diff patch. Do not include explanations outside the patch.")
        prompt = "\n\n".join(prompt_parts) + "\n"
        prompt_path = output_dir / f"{instance_id}.prompt.txt"
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
            "read-only",
            "--output-last-message",
            str(last_message),
            prompt,
        ]
        try:
            stdout = run_capture(cmd, cwd=ROOT, timeout=900)
            full_output = last_message.read_text(encoding="utf-8", errors="replace") if last_message.exists() else stdout
        except subprocess.CalledProcessError as exc:
            full_output = exc.stdout or ""
        patch = extract_diff(full_output)
        record = {
            "instance_id": instance_id,
            "model_name_or_path": MODEL_NAME,
            "full_output": full_output,
            "model_patch": patch,
        }
        with raw_output_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return raw_output_path


def write_repair_predictions(raw_output_path: Path, predictions_dir: Path) -> Path:
    predictions_dir.mkdir(parents=True, exist_ok=True)
    repair_path = predictions_dir / "codex__oracle__test_repair.jsonl"
    rows = []
    for line in raw_output_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rows.append(
            {
                "instance_id": row["instance_id"],
                "model_name_or_path": row.get("model_name_or_path", MODEL_NAME),
                "model_patch": row.get("model_patch", ""),
            }
        )
    repair_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    return repair_path


def run_transfer_repair(
    official_repo: Path,
    raw_output_path: Path,
    prompt_dataset: Path,
    predictions_dir: Path,
) -> Path:
    """Use SWE-Perf's official converter from SEARCH/REPLACE to unified diff."""
    run(
        [
            sys.executable,
            "-m",
            "transfer_repair.transfer_repair",
            "--model_output_path",
            str(raw_output_path),
            "--dataset_path",
            str(prompt_dataset),
        ],
        cwd=official_repo / "generation" / "oracle",
    )
    generated = raw_output_path.with_name(raw_output_path.stem + "_repair.jsonl")
    if not generated.exists():
        raise SystemExit(f"official transfer_repair did not create {generated}")
    predictions_dir.mkdir(parents=True, exist_ok=True)
    repair_path = predictions_dir / "codex__oracle__test_repair.jsonl"
    shutil.copyfile(generated, repair_path)
    return repair_path


def run_official_evaluation(
    official_repo: Path,
    eval_dataset_name_or_path: str,
    predictions_path: Path,
    work_dir: Path,
    run_id: str,
    max_workers: int,
    timeout: int,
) -> Path:
    eval_dir = official_repo / "evaluation"
    eval_dataset_path = Path(eval_dataset_name_or_path)
    if eval_dataset_path.exists():
        eval_dataset_name_or_path = str(eval_dataset_path.resolve())
    run(
        [
            sys.executable,
            "-m",
            "run_evaluation",
            "--dataset_name",
            eval_dataset_name_or_path,
            "--split",
            "test",
            "--predictions_path",
            str(predictions_path),
            "--max_workers",
            str(max_workers),
            "--run_id",
            run_id,
            "--cache_level",
            "instance",
            "--timeout",
            str(timeout),
        ],
        cwd=eval_dir,
    )
    csv_path = work_dir / "evaluation" / "codex_result.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    log_root = official_repo / "datasets" / "logs" / "run_evaluation" / run_id / MODEL_NAME
    run(
        [
            sys.executable,
            "-m",
            "check_evaluation",
            "--dataset_dir",
            eval_dataset_name_or_path,
            "--log_root",
            str(log_root),
            "--output_path",
            str(csv_path),
        ],
        cwd=eval_dir,
    )
    return csv_path


def write_manifest(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--official-repo", default="/tmp/swe-perf-official")
    parser.add_argument("--dataset-name-or-path", default=DEFAULT_DATASET_NAME)
    parser.add_argument("--work-dir", default="experiments/swe_perf_pilot/results/codex_baseline_small")
    parser.add_argument("--max-instances", type=int, default=None)
    parser.add_argument("--instance-ids", nargs="+", default=None)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--run-codex", action="store_true")
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument("--max-workers", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--run-id", default="codex_small_oracle")
    parser.add_argument("--prompt-label", default="baseline")
    parser.add_argument("--invariant-context-file", default=None)
    args = parser.parse_args()

    official_repo = Path(args.official_repo).resolve()
    work_dir = (ROOT / args.work_dir).resolve() if not Path(args.work_dir).is_absolute() else Path(args.work_dir)
    raw_subset_dir = work_dir / "raw_subset"
    base_dataset_dir = work_dir / "base_datasets"
    codex_output_dir = work_dir / "codex_outputs"
    predictions_dir = work_dir / "predictions"
    invariant_context_file = Path(args.invariant_context_file).resolve() if args.invariant_context_file else None
    if invariant_context_file is not None and not invariant_context_file.exists():
        raise SystemExit(f"invariant context file does not exist: {invariant_context_file}")

    ensure_official_repo(official_repo)
    instance_ids = load_dataset_subset(
        args.dataset_name_or_path,
        raw_subset_dir,
        args.max_instances,
        args.instance_ids,
    )
    prompt_dataset = make_oracle_prompt_dataset(official_repo, raw_subset_dir, base_dataset_dir)

    manifest: dict[str, Any] = {
        "dataset": args.dataset_name_or_path,
        "setting": "oracle",
        "agent": "Codex CLI",
        "prompt_label": args.prompt_label,
        "model_name_or_path": MODEL_NAME,
        "official_repo": str(official_repo),
        "work_dir": str(work_dir),
        "instance_ids": instance_ids,
        "raw_subset_dir": str(raw_subset_dir),
        "prompt_dataset": str(prompt_dataset),
        "baseline_definition": "Codex CLI on official SWE-Perf oracle prompts, evaluated by official SWE-Perf scripts.",
    }
    if invariant_context_file:
        manifest["invariant_context_file"] = str(invariant_context_file)
        previews = {}
        for instance_id in instance_ids:
            resolved_context = resolve_invariant_context(invariant_context_file, instance_id)
            previews[instance_id] = format_invariant_context(resolved_context) if resolved_context else ""
        manifest["invariant_context_preview_by_instance"] = previews

    raw_output_path = codex_output_dir / "codex__oracle__test.jsonl"
    if args.run_codex:
        raw_output_path = run_codex_on_prompts(
            prompt_dataset,
            codex_output_dir,
            args.max_instances,
            invariant_context_file,
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
