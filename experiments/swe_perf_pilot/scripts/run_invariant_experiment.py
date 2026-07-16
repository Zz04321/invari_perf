#!/usr/bin/env python3
"""Summarize the two invariant hypotheses over existing SWE-Perf pilot runs.

H1: adding mined invariants changes/improves the optimization agent result.
H2: tests-only optimization should be audited for invariant preservation.

This script intentionally uses artifacts already produced by the real
SWE-Perf/Codex pipeline. It does not fabricate benchmark outcomes.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
INSTANCE_ID = "astropy__astropy-16058"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def prediction_for(path: Path, instance_id: str) -> dict[str, Any]:
    for row in read_jsonl(path):
        if row.get("instance_id") == instance_id:
            return row
    raise SystemExit(f"missing prediction for {instance_id}: {path}")


def read_eval_csv(path: Path) -> dict[str, Any]:
    rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
    total = next((row for row in rows if row.get("repo") == "total"), rows[0] if rows else {})
    out: dict[str, Any] = {"path": str(path), "rows": rows}
    for key in ["total", "with_prediction", "with_run", "success"]:
        if key in total:
            out[key] = int(float(total[key]))
    for key in ["apply", "correctness", "performance", "model_improved"]:
        if key in total:
            out[key] = float(total[key])
    return out


def dataset_row(dataset_path: Path, instance_id: str) -> dict[str, Any]:
    for row in read_jsonl(dataset_path):
        if row.get("instance_id") == instance_id:
            return row
    raise SystemExit(f"missing dataset row for {instance_id}: {dataset_path}")


def duration_summary(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("duration_changes", "[]")
    changes = json.loads(raw) if isinstance(raw, str) else raw
    bases = []
    heads = []
    for item in changes:
        for values in item.values():
            bases.append(float(values["base"]))
            heads.append(float(values["head"]))
    if not bases:
        return {"runs": 0}
    base_mean = sum(bases) / len(bases)
    head_mean = sum(heads) / len(heads)
    base_median = statistics.median(bases)
    head_median = statistics.median(heads)
    return {
        "runs": len(bases),
        "base_mean": base_mean,
        "head_mean": head_mean,
        "relative_gain": (base_mean - head_mean) / base_mean,
        "base_median": base_median,
        "head_median": head_median,
        "median_relative_gain": (base_median - head_median) / base_median,
        "head_min": min(heads),
        "head_max": max(heads),
    }


def changed_files(patch: str) -> list[str]:
    return re.findall(r"^diff --git a/(\S+) b/\S+", patch, flags=re.MULTILINE)


def patch_touches(patch: str, token: str) -> bool:
    return token in patch


def patch_summary(label: str, row: dict[str, Any]) -> dict[str, Any]:
    patch = row.get("model_patch", "")
    return {
        "label": label,
        "instance_id": row.get("instance_id"),
        "patch_bytes": len(patch.encode("utf-8")),
        "changed_files": changed_files(patch),
        "touches_validate_power": patch_touches(patch, "validate_power"),
        "touches_maybe_simple_fraction": patch_touches(patch, "maybe_simple_fraction"),
        "touches_sanitize_power": patch_touches(patch, "sanitize_power"),
        "touches_expand_and_gather": patch_touches(patch, "_expand_and_gather"),
        "has_int_identity_fast_path": bool(re.search(r"p\.__class__ is int|type\(p\) is int", patch)),
        "has_fraction_identity_fast_path": bool(re.search(r"p\.__class__ is Fraction|type\(p\) is Fraction", patch)),
        "has_fallback_or_slow_path_split": "def sanitize_power" in patch,
    }


def load_daikon_evidence(path: Path, target: str) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    selected = []
    for ppt, invariants in data.get("likely_invariants_by_program_point", {}).items():
        if target not in ppt:
            continue
        for invariant in invariants:
            if any(token in invariant for token in ["result_is_same_as_arg0", "arg0_is_int", "arg0_is_float"]):
                selected.append({"program_point": ppt, "invariant": invariant})
    return {
        "path": str(path),
        "task_id": data.get("task_id"),
        "target": target,
        "runtime_trace_rows": data.get("runtime_trace_rows", 0),
        "deduplicated_trace_rows": data.get("deduplicated_trace_rows", 0),
        "selected_invariants": selected[:12],
    }


def invariant_audit(patch: str, evidence: dict[str, Any]) -> dict[str, Any]:
    """Patch-level audit of whether mined invariant evidence is used/preserved.

    This is a static/semantic audit over the generated patch, not a replacement
    for rerunning Daikon on the patched program.
    """

    checks = []
    inv_text = "\n".join(item["invariant"] for item in evidence["selected_invariants"])
    has_int_identity_inv = "arg0_is_int <= result_is_same_as_arg0" in inv_text
    has_observed_identity_inv = "result_is_same_as_arg0" in inv_text

    checks.append(
        {
            "name": "uses_int_identity_condition",
            "invariant": "arg0_is_int <= result_is_same_as_arg0",
            "expected_patch_shape": "guarded direct return for int input",
            "status": "pass" if re.search(r"p\.__class__ is int|type\(p\) is int", patch) else "missing",
            "applicable": has_int_identity_inv,
        }
    )
    checks.append(
        {
            "name": "preserves_fallback_path",
            "invariant": "observed identity is a precondition, not a global rewrite",
            "expected_patch_shape": "fallback conversion/validation remains for uncovered cases",
            "status": "pass"
            if ("maybe_simple_fraction" in patch or "getattr(p, \"denominator\"" in patch or "def sanitize_power" in patch)
            else "risky",
            "applicable": has_observed_identity_inv,
        }
    )
    checks.append(
        {
            "name": "separates_check_from_normalization",
            "invariant": "some validate_power paths return the input unchanged",
            "expected_patch_shape": "validation remains cheap; normalization moves to explicit path",
            "status": "pass" if "def sanitize_power" in patch else "not_present",
            "applicable": has_observed_identity_inv,
        }
    )
    return {
        "audit_type": "patch-level invariant audit",
        "warning": "This checks whether the patch appears to use/preserve mined invariants. It does not prove the patched runtime still satisfies them.",
        "checks": checks,
    }


def write_markdown(path: Path, summary: dict[str, Any]) -> None:
    h1 = summary["H1_invariant_as_agent_guidance"]
    h2 = summary["H2_invariant_as_post_optimization_audit"]
    lines = [
        "# Invariant Experiment Summary",
        "",
        "## Dataset expert patch",
        "",
        f"- Repo: `{summary['dataset_expert_patch']['repo']}`",
        f"- Human performance field: `{summary['dataset_expert_patch']['human_performance']}`",
        f"- Human patch mean: `{summary['dataset_expert_patch']['duration_summary'].get('base_mean')}` -> `{summary['dataset_expert_patch']['duration_summary'].get('head_mean')}`",
        f"- Human patch median: `{summary['dataset_expert_patch']['duration_summary'].get('base_median')}` -> `{summary['dataset_expert_patch']['duration_summary'].get('head_median')}`",
        f"- Median relative gain: `{summary['dataset_expert_patch']['duration_summary'].get('median_relative_gain')}`",
        f"- Human patch splits `sanitize_power`: `{summary['dataset_expert_patch']['patch']['has_fallback_or_slow_path_split']}`",
        "",
        "## H1: invariant evidence as agent guidance",
        "",
        f"- Instance: `{summary['instance_id']}`",
        f"- Baseline success: `{h1['baseline_eval'].get('success')}` / `{h1['baseline_eval'].get('total')}`",
        f"- Daikon-skill success: `{h1['daikon_eval'].get('success')}` / `{h1['daikon_eval'].get('total')}`",
        f"- Baseline aggregate performance: `{h1['baseline_eval'].get('performance')}`",
        f"- Daikon-skill aggregate performance: `{h1['daikon_eval'].get('performance')}`",
        "",
        "Patch shape:",
        f"- Baseline changed files: `{', '.join(h1['baseline_patch']['changed_files'])}`",
        f"- Daikon changed files: `{', '.join(h1['daikon_patch']['changed_files'])}`",
        f"- Baseline splits `sanitize_power`: `{h1['baseline_patch']['has_fallback_or_slow_path_split']}`",
        f"- Daikon splits `sanitize_power`: `{h1['daikon_patch']['has_fallback_or_slow_path_split']}`",
        "",
        "Interpretation: the existing run supports the mechanism story that the Daikon-context prompt pushed Codex toward an explicit validation-vs-normalization split.",
        "",
        "## H2: invariant evidence as post-optimization audit",
        "",
        f"- Mined trace rows: `{h2['evidence']['runtime_trace_rows']}`",
        f"- Unique observed shapes: `{h2['evidence']['deduplicated_trace_rows']}`",
        "",
        "Selected invariants:",
    ]
    for item in h2["evidence"]["selected_invariants"][:6]:
        lines.append(f"- `{item['program_point']}: {item['invariant']}`")
    lines.extend(["", "Patch-level audit:"])
    for label, audit in h2["patch_audits"].items():
        lines.append(f"- `{label}`:")
        for check in audit["checks"]:
            lines.append(f"  - `{check['name']}`: `{check['status']}`")
    lines.extend(
        [
            "",
            "Next real check:",
            "",
            "```bash",
            h2["next_real_trace_check"]["human_patch_command"],
            "```",
            "",
            "```bash",
            h2["next_real_trace_check"]["codex_daikon_command"],
            "```",
            "",
            "The next check reruns Daikon on the patched program. That is the real semantic-regression test; this summary only audits the generated patch shape.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance-id", default=INSTANCE_ID)
    parser.add_argument("--baseline-dir", type=Path, default=ROOT / "experiments/swe_perf_pilot/results/codex_baseline_small")
    parser.add_argument("--daikon-dir", type=Path, default=ROOT / "experiments/swe_perf_pilot/results/codex_daikon_skill_16058")
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/sweperf_small.jsonl")
    parser.add_argument("--invariant-file", type=Path, default=ROOT / "experiments/swe_perf_pilot/invariants/astropy__astropy-16058.real-daikon.json")
    parser.add_argument("--target", default="validate_power")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "experiments/swe_perf_pilot/results/invariant_hypotheses")
    args = parser.parse_args()

    baseline_pred = prediction_for(args.baseline_dir / "predictions/codex__oracle__test_repair.jsonl", args.instance_id)
    daikon_pred = prediction_for(args.daikon_dir / "predictions/codex__oracle__test_repair.jsonl", args.instance_id)
    human_row = dataset_row(args.dataset, args.instance_id)
    human_pred = {
        "instance_id": args.instance_id,
        "model_patch": human_row.get("patch", ""),
    }
    evidence = load_daikon_evidence(args.invariant_file, args.target)

    summary = {
        "instance_id": args.instance_id,
        "dataset_expert_patch": {
            "repo": human_row.get("repo"),
            "base_commit": human_row.get("base_commit"),
            "head_commit": human_row.get("head_commit"),
            "efficiency_test": human_row.get("efficiency_test"),
            "human_performance": human_row.get("human_performance"),
            "duration_summary": duration_summary(human_row),
            "patch": patch_summary("human_expert", human_pred),
        },
        "H1_invariant_as_agent_guidance": {
            "baseline_eval": read_eval_csv(args.baseline_dir / "evaluation/codex_result.csv"),
            "daikon_eval": read_eval_csv(args.daikon_dir / "evaluation/codex_result.csv"),
            "baseline_patch": patch_summary("baseline", baseline_pred),
            "daikon_patch": patch_summary("codex_plus_daikon", daikon_pred),
        },
        "H2_invariant_as_post_optimization_audit": {
            "evidence": evidence,
            "patch_audits": {
                "human_expert": invariant_audit(human_pred.get("model_patch", ""), evidence),
                "baseline": invariant_audit(baseline_pred.get("model_patch", ""), evidence),
                "codex_plus_daikon": invariant_audit(daikon_pred.get("model_patch", ""), evidence),
            },
            "next_real_trace_check": {
                "status": "not_run_by_this_script",
                "reason": "requires official SWE-Perf checkout, Docker image, and patched-program trace mining",
                "human_patch_command": (
                    "conda run -n sweperf python "
                    "experiments/swe_perf_pilot/daikon_mining/real_trace_task.py "
                    f"--instance-id {args.instance_id} "
                    "--target-source patch-functions "
                    "--use-human-patch "
                    "--prediction-label human_patch"
                ),
                "codex_daikon_command": (
                    "conda run -n sweperf python "
                    "experiments/swe_perf_pilot/daikon_mining/real_trace_task.py "
                    f"--instance-id {args.instance_id} "
                    "--target-source patch-functions "
                    "--prediction-file experiments/swe_perf_pilot/results/codex_daikon_skill_16058/predictions/codex__oracle__test_repair.jsonl "
                    "--prediction-label codex_plus_daikon"
                ),
            },
        },
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / f"{args.instance_id}.summary.json"
    md_path = args.out_dir / f"{args.instance_id}.summary.md"
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(md_path, summary)
    print(f"wrote: {json_path}")
    print(f"wrote: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
