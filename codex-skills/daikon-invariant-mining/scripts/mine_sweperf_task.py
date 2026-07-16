#!/usr/bin/env python3
"""Wrapper for the SWE-Perf showcase real-trace Daikon miner."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def find_repo_root(start: Path) -> Path:
    for path in [start, *start.parents]:
        if (path / "experiments/swe_perf_pilot/daikon_mining/real_trace_task.py").exists():
            return path
    raise SystemExit("Could not find semantic-waste-showcase repo root with real_trace_task.py")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--dataset", default="data/sweperf_small.jsonl")
    parser.add_argument("--target-source", default="patch-functions", choices=["patch-functions", "patch-modules", "test-functions", "union"])
    parser.add_argument("--daikon-jar", default="/tmp/daikon-5.8.24/daikon.jar")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--conda-env", default="sweperf")
    parser.add_argument("--skip-trace", action="store_true")
    args = parser.parse_args()

    root = find_repo_root(Path.cwd().resolve())
    miner = root / "experiments/swe_perf_pilot/daikon_mining/real_trace_task.py"
    cmd = [
        "conda",
        "run",
        "-n",
        args.conda_env,
        sys.executable,
        str(miner),
        "--dataset",
        str((root / args.dataset).resolve() if not Path(args.dataset).is_absolute() else Path(args.dataset)),
        "--instance-id",
        args.task,
        "--target-source",
        args.target_source,
        "--daikon-jar",
        args.daikon_jar,
        "--timeout",
        str(args.timeout),
    ]
    if args.skip_trace:
        cmd.append("--skip-trace")
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=root, check=True)
    context = root / "experiments/swe_perf_pilot/invariants" / f"{args.task}.real-daikon.json"
    print(f"context: {context}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
