#!/usr/bin/env python3
"""Check whether a SWE-Perf performance patch changes mined invariants.

This is Experiment B only:

    before optimization: Daikon context on the base program
    after optimization:  Daikon context on the patched program
    output:              invariant drift report

It is intentionally independent from the agent-guidance experiment.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INSTANCE = "astropy__astropy-16058"


IMPORTANT_TOKENS = (
    "result_is_same_as_arg0",
    "result_is_none",
    "raised",
    "arg0_is_int",
    "arg0_is_float",
    "arg0_is_bool",
    "arg0_float",
    "arg0_truth",
    "result_len",
    "result_size",
)


def load_context(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_invariant(text: str) -> str:
    return " ".join(text.strip().split())


def invariant_set(context: dict[str, Any], target: str | None, important_only: bool) -> set[str]:
    out: set[str] = set()
    for ppt, invariants in context.get("likely_invariants_by_program_point", {}).items():
        if target and target not in ppt:
            continue
        for invariant in invariants:
            normalized = normalize_invariant(invariant)
            if important_only and not any(token in normalized for token in IMPORTANT_TOKENS):
                continue
            out.add(f"{ppt}: {normalized}")
    return out


def coverage(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "trace_source": context.get("trace_source"),
        "prediction_label": context.get("prediction_label"),
        "runtime_trace_rows": context.get("runtime_trace_rows", 0),
        "deduplicated_trace_rows": context.get("deduplicated_trace_rows", 0),
        "trace_target_source": context.get("trace_target_source"),
    }


def risk_notes(removed: set[str], added: set[str], after: set[str]) -> list[str]:
    notes = []
    removed_text = "\n".join(sorted(removed))
    added_text = "\n".join(sorted(added))
    after_text = "\n".join(sorted(after))
    identity_strengthened = (
        "result_is_same_as_arg0 one of { 0, 1 }" in removed_text
        and "arg0_truth == result_is_same_as_arg0" in added_text
        and "arg0_truth == 1" in after_text
    )
    if identity_strengthened:
        notes.append(
            "The return-identity relation changed shape but appears stronger: after the patch, observed validate_power returns satisfy result_is_same_as_arg0 == 1."
        )
    elif "result_is_same_as_arg0" in removed_text:
        notes.append("A return-identity invariant disappeared; a fast path or object-identity assumption may have changed.")
    if "raised" in removed_text or "raised" in added_text:
        notes.append("Exception-related invariants changed; check whether validation/error behavior changed.")
    if "arg0_float" in removed_text or "arg0_float" in added_text:
        notes.append("Numeric-value invariants changed; check whether normalization changed values or types.")
    if not notes and (removed or added):
        notes.append("Invariant set changed, but no high-priority semantic token was detected.")
    if not removed and not added:
        notes.append("No invariant drift detected under the selected filter.")
    return notes


def run_after_trace(args: argparse.Namespace, after_context: Path) -> None:
    cmd = [
        sys.executable,
        "experiments/swe_perf_pilot/daikon_mining/real_trace_task.py",
        "--dataset",
        str(args.dataset),
        "--instance-id",
        args.instance_id,
        "--target-source",
        args.target_source,
        "--daikon-jar",
        str(args.daikon_jar),
        "--timeout",
        str(args.timeout),
    ]
    if args.patch_source == "human":
        cmd.extend(["--use-human-patch", "--prediction-label", args.patch_label])
    elif args.patch_source == "prediction":
        if not args.prediction_file:
            raise SystemExit("--prediction-file is required when --patch-source prediction")
        cmd.extend(
            [
                "--prediction-file",
                str(args.prediction_file),
                "--prediction-label",
                args.patch_label,
            ]
        )
    else:
        raise SystemExit(f"unsupported patch source: {args.patch_source}")

    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)
    if not after_context.exists():
        raise RuntimeError(f"trace command finished but did not create {after_context}")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Invariant Drift Report",
        "",
        f"- Instance: `{report['instance_id']}`",
        f"- Patch source: `{report['patch_source']}`",
        f"- Target filter: `{report['target_filter'] or '<all>'}`",
        "",
        "## Coverage",
        "",
        f"- Before rows: `{report['before_coverage']['runtime_trace_rows']}`; unique: `{report['before_coverage']['deduplicated_trace_rows']}`",
        f"- After rows: `{report['after_coverage']['runtime_trace_rows']}`; unique: `{report['after_coverage']['deduplicated_trace_rows']}`",
        "",
        "## Drift",
        "",
        f"- Preserved: `{report['counts']['preserved']}`",
        f"- Removed: `{report['counts']['removed']}`",
        f"- Added: `{report['counts']['added']}`",
        "",
        "## Risk Notes",
        "",
    ]
    lines.extend(f"- {item}" for item in report["risk_notes"])
    lines.extend(["", "## Removed Invariants", ""])
    lines.extend(f"- `{item}`" for item in report["removed"][:30])
    if not report["removed"]:
        lines.append("- `<none>`")
    lines.extend(["", "## Added Invariants", ""])
    lines.extend(f"- `{item}`" for item in report["added"][:30])
    if not report["added"]:
        lines.append("- `<none>`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance-id", default=DEFAULT_INSTANCE)
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/sweperf_small.jsonl")
    parser.add_argument("--before-context", type=Path, default=None)
    parser.add_argument("--after-context", type=Path, default=None)
    parser.add_argument("--target", default=None)
    parser.add_argument("--important-only", action="store_true", default=True)
    parser.add_argument("--all-invariants", dest="important_only", action="store_false")
    parser.add_argument("--patch-source", choices=["human", "prediction"], default="human")
    parser.add_argument("--patch-label", default="human_patch")
    parser.add_argument("--prediction-file", type=Path, default=None)
    parser.add_argument("--target-source", choices=["patch-functions", "patch-modules", "test-functions", "union"], default="patch-functions")
    parser.add_argument("--daikon-jar", type=Path, default=Path("/tmp/daikon-5.8.24/daikon.jar"))
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--run-after", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "experiments/swe_perf_pilot/results/invariant_drift")
    args = parser.parse_args()

    before_context = args.before_context
    if before_context is None:
        before_context = ROOT / "experiments" / "swe_perf_pilot" / "invariants" / f"{args.instance_id}.real-daikon.json"

    after_context = args.after_context
    if after_context is None:
        after_context = (
            ROOT
            / "experiments"
            / "swe_perf_pilot"
            / "results"
            / "daikon_real_trace"
            / args.instance_id
            / args.patch_label
            / "invariant_context.json"
        )

    if args.run_after and not after_context.exists():
        run_after_trace(args, after_context)

    before = load_context(before_context)
    after = load_context(after_context)
    before_set = invariant_set(before, args.target, args.important_only)
    after_set = invariant_set(after, args.target, args.important_only)
    preserved = sorted(before_set & after_set)
    removed = sorted(before_set - after_set)
    added = sorted(after_set - before_set)

    report = {
        "instance_id": args.instance_id,
        "patch_source": args.patch_source,
        "patch_label": args.patch_label,
        "target_filter": args.target,
        "important_only": args.important_only,
        "before_context": str(before_context),
        "after_context": str(after_context),
        "before_coverage": coverage(before),
        "after_coverage": coverage(after),
        "counts": {
            "before": len(before_set),
            "after": len(after_set),
            "preserved": len(preserved),
            "removed": len(removed),
            "added": len(added),
        },
        "risk_notes": risk_notes(set(removed), set(added), after_set),
        "preserved": preserved[:200],
        "removed": removed[:200],
        "added": added[:200],
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / f"{args.instance_id}.{args.patch_label}.drift.json"
    md_path = args.out_dir / f"{args.instance_id}.{args.patch_label}.drift.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(md_path, report)
    print(f"wrote: {json_path}")
    print(f"wrote: {md_path}")
    print(json.dumps(report["counts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
