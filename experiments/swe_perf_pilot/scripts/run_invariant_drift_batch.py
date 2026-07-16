#!/usr/bin/env python3
"""Batch runner for Experiment B: invariant drift after SWE-Perf patches.

No AI agent is involved. For each SWE-Perf instance, the script:

1. mines base-program invariants if missing;
2. applies the SWE-Perf human patch and mines patched-program invariants;
3. writes a drift report comparing the two invariant sets.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]


def load_instances(dataset: Path, limit: int | None, instance_ids: list[str] | None) -> list[str]:
    rows = [
        json.loads(line)
        for line in dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    ids = [row["instance_id"] for row in rows]
    if instance_ids:
        wanted = set(instance_ids)
        missing = wanted - set(ids)
        if missing:
            raise SystemExit(f"unknown instance id(s): {', '.join(sorted(missing))}")
        ids = [item for item in ids if item in wanted]
    if limit is not None:
        ids = ids[:limit]
    return ids


def run(cmd: list[str], *, dry_run: bool) -> int:
    print("+ " + " ".join(cmd), flush=True)
    if dry_run:
        return 0
    return subprocess.run(cmd, cwd=ROOT).returncode


def context_paths(instance_id: str, patch_label: str) -> tuple[Path, Path, Path]:
    before = ROOT / "experiments" / "swe_perf_pilot" / "invariants" / f"{instance_id}.real-daikon.json"
    after = (
        ROOT
        / "experiments"
        / "swe_perf_pilot"
        / "results"
        / "daikon_real_trace"
        / instance_id
        / patch_label
        / "invariant_context.json"
    )
    drift = ROOT / "experiments" / "swe_perf_pilot" / "results" / "invariant_drift" / f"{instance_id}.{patch_label}.drift.json"
    return before, after, drift


def read_context_coverage(path: Path, target_source: str | None = None) -> int:
    if not path.exists():
        return -1
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return -1
    if target_source is not None and data.get("trace_target_source") != target_source:
        return -1
    return int(data.get("runtime_trace_rows", 0) or 0)


def drift_has_coverage(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return (
        int(data.get("before_coverage", {}).get("runtime_trace_rows", 0) or 0) > 0
        and int(data.get("after_coverage", {}).get("runtime_trace_rows", 0) or 0) > 0
    )


def load_drift(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def write_aggregate_csv(path: Path, results: list[dict[str, Any]]) -> None:
    columns = [
        "instance_id",
        "status",
        "target_source",
        "before_rows",
        "after_rows",
        "before_invariants",
        "after_invariants",
        "preserved",
        "removed",
        "added",
        "risk_notes",
        "drift_report",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for item in results:
            drift = load_drift(Path(item["drift_report"]))
            counts = drift.get("counts", {})
            before_cov = drift.get("before_coverage", {})
            after_cov = drift.get("after_coverage", {})
            writer.writerow(
                {
                    "instance_id": item["instance_id"],
                    "status": item["status"],
                    "target_source": item.get("target_source", ""),
                    "before_rows": before_cov.get("runtime_trace_rows", item.get("before_rows", "")),
                    "after_rows": after_cov.get("runtime_trace_rows", item.get("after_rows", "")),
                    "before_invariants": counts.get("before", ""),
                    "after_invariants": counts.get("after", ""),
                    "preserved": counts.get("preserved", ""),
                    "removed": counts.get("removed", ""),
                    "added": counts.get("added", ""),
                    "risk_notes": " | ".join(drift.get("risk_notes", [])),
                    "drift_report": item["drift_report"],
                }
            )


def trace_cmd(args: argparse.Namespace, instance_id: str, target_source: str, patched: bool) -> list[str]:
    cmd = [
        sys.executable,
        "experiments/swe_perf_pilot/daikon_mining/real_trace_task.py",
        "--dataset",
        str(args.dataset),
        "--instance-id",
        instance_id,
        "--target-source",
        target_source,
        "--daikon-jar",
        str(args.daikon_jar),
        "--timeout",
        str(args.timeout),
    ]
    if patched:
        cmd.extend(["--use-human-patch", "--prediction-label", args.patch_label])
    return cmd


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/sweperf_small.jsonl")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--instance-ids", nargs="+", default=None)
    parser.add_argument("--patch-source", choices=["human"], default="human")
    parser.add_argument("--patch-label", default="human_patch")
    parser.add_argument("--target", default=None, help="Optional invariant target filter, e.g. validate_power")
    parser.add_argument("--target-source", choices=["patch-functions", "patch-modules", "test-functions", "union"], default="patch-functions")
    parser.add_argument(
        "--fallback-target-sources",
        nargs="+",
        default=["patch-functions", "patch-modules", "union"],
        choices=["patch-functions", "patch-modules", "test-functions", "union"],
    )
    parser.add_argument("--daikon-jar", type=Path, default=Path("/tmp/daikon-5.8.24/daikon.jar"))
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    instance_ids = load_instances(args.dataset, args.limit, args.instance_ids)
    summary: dict[str, Any] = {
        "dataset": str(args.dataset),
        "count": len(instance_ids),
        "patch_source": args.patch_source,
        "patch_label": args.patch_label,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "results": [],
    }

    for instance_id in instance_ids:
        before, after, drift = context_paths(instance_id, args.patch_label)
        item: dict[str, Any] = {
            "instance_id": instance_id,
            "before_context": str(before),
            "after_context": str(after),
            "drift_report": str(drift),
            "status": "pending",
        }
        summary["results"].append(item)

        if args.skip_existing and drift_has_coverage(drift):
            item["status"] = "skipped_existing"
            item["target_source"] = load_drift(drift).get("before_coverage", {}).get("trace_target_source", "")
            continue

        selected_source = ""
        for target_source in args.fallback_target_sources:
            before_rows = read_context_coverage(before, target_source)
            if before_rows <= 0:
                rc = run(trace_cmd(args, instance_id, target_source, False), dry_run=args.dry_run)
                if rc != 0:
                    item.setdefault("failed_sources", []).append({"target_source": target_source, "phase": "base", "returncode": rc})
                    continue
                before_rows = read_context_coverage(before, target_source)

            after_rows = read_context_coverage(after, target_source)
            if after_rows <= 0:
                rc = run(trace_cmd(args, instance_id, target_source, True), dry_run=args.dry_run)
                if rc != 0:
                    item.setdefault("failed_sources", []).append({"target_source": target_source, "phase": "after", "returncode": rc})
                    continue
                after_rows = read_context_coverage(after, target_source)

            item["before_rows"] = before_rows
            item["after_rows"] = after_rows
            item["target_source"] = target_source
            if before_rows > 0 and after_rows > 0:
                selected_source = target_source
                break

        if not selected_source:
            item["status"] = "excluded_no_coverage"
            continue

        cmd = [
            sys.executable,
            "experiments/swe_perf_pilot/scripts/check_invariant_drift.py",
            "--dataset",
            str(args.dataset),
            "--instance-id",
            instance_id,
            "--patch-source",
            args.patch_source,
            "--patch-label",
            args.patch_label,
        ]
        if args.target:
            cmd.extend(["--target", args.target])
        rc = run(cmd, dry_run=args.dry_run)
        if rc != 0:
            item["status"] = "drift_failed"
            item["returncode"] = rc
            continue
        item["status"] = "ok"

    out_dir = ROOT / "experiments" / "swe_perf_pilot" / "results" / "invariant_drift"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"batch_{args.patch_label}.summary.json"
    csv_path = out_dir / f"batch_{args.patch_label}.aggregate.csv"
    summary["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_aggregate_csv(csv_path, summary["results"])
    print(f"wrote: {out_path}")
    print(f"wrote: {csv_path}")
    successful_statuses = {"ok", "skipped_existing", "excluded_no_coverage"}
    ok = sum(1 for item in summary["results"] if item["status"] in successful_statuses)
    print(f"ok_or_skipped: {ok}/{len(summary['results'])}")
    return 0 if ok == len(summary["results"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
