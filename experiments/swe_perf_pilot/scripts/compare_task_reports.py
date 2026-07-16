#!/usr/bin/env python3
"""Compare two SWE-Perf per-instance report.json files."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


def load_report(path: Path) -> dict[str, dict[str, float]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, dict[str, float]] = {}
    for test, runs in data.items():
        base = [item["duration"] for _, item in sorted(runs["base"].items(), key=lambda kv: int(kv[0]))]
        patched = [item["duration"] for _, item in sorted(runs["human"].items(), key=lambda kv: int(kv[0]))]
        base_mean = statistics.mean(base)
        patched_mean = statistics.mean(patched)
        result[test] = {
            "base_mean": base_mean,
            "patched_mean": patched_mean,
            "relative_gain": (base_mean - patched_mean) / base_mean,
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--left-label", default="left")
    parser.add_argument("--left-report", required=True, type=Path)
    parser.add_argument("--right-label", default="right")
    parser.add_argument("--right-report", required=True, type=Path)
    args = parser.parse_args()

    reports = {
        args.left_label: load_report(args.left_report),
        args.right_label: load_report(args.right_report),
    }
    tests = sorted(set().union(*(report.keys() for report in reports.values())))
    print("setting,test,base_mean,patched_mean,relative_gain")
    for label, report in reports.items():
        for test in tests:
            if test not in report:
                continue
            row = report[test]
            print(
                f"{label},{test},{row['base_mean']:.9f},"
                f"{row['patched_mean']:.9f},{row['relative_gain']:.6f}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
