#!/usr/bin/env python3
"""Render Daikon mined invariant JSON as agent-readable evidence."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def score_invariant(text: str) -> int:
    score = 0
    useful_tokens = [
        "result_is_same_object",
        "result_is_same_as_arg0",
        "float_value == result_float_value",
        "arg0_float == result",
        "result_is_int",
        "result_is_float",
        "result_is_fraction",
        "is_int == 1",
        "is_float == 1",
        "raised == 0",
    ]
    for token in useful_tokens:
        if token in text:
            score += 3
    if " one of " in text:
        score += 1
    if "==" in text:
        score += 1
    if any(noise in text for noise in ["arg_count", "kwarg_count", "arg1_", "arg0_len", "arg0_shape", "arg0_size"]):
        score -= 4
    if any(token in text for token in ["shape", "size", "len"]) and "result_is_same" not in text:
        score -= 2
    return score


def load_context(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"context file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def select_invariants(context: dict, target: str | None, limit: int) -> list[tuple[str, str, int]]:
    rows: list[tuple[str, str, int]] = []
    for ppt, invariants in context.get("likely_invariants_by_program_point", {}).items():
        if target and target not in ppt:
            continue
        for invariant in invariants:
            score = score_invariant(invariant)
            rows.append((ppt, invariant, score))
    useful = [row for row in rows if row[2] > 0]
    useful.sort(key=lambda item: item[2], reverse=True)
    return useful[:limit]


def implications(rows: list[tuple[str, str, int]]) -> list[str]:
    out: list[str] = []
    text = "\n".join(inv for _, inv, _ in rows)
    if "result_is_same" in text:
        out.append("Some observed paths return the original object; consider identity fast paths when the input type precondition holds.")
    if "float_value == result_float_value" in text:
        out.append("Observed paths preserve numeric value; cheaper rewrites must keep this equivalence.")
    if "result_is_int" in text or "result_is_float" in text or "result_is_fraction" in text:
        out.append("Observed return type is stable on some paths; preserve type-normalization behavior.")
    if "shape" in text or "size" in text or "len" in text:
        out.append("Observed shape/length facts may justify avoiding allocation or repeated validation on the covered path.")
    return out


def classify_invariant(invariant: str) -> dict | None:
    """Map one raw Daikon invariant into a fixed evidence schema.

    The adapter is intentionally rule-based. It should expose affordances that
    are generic across tasks, not case-specific rewrite advice.
    """
    text = invariant.strip()
    if not text:
        return None

    conditional_identity = re.match(r"^([A-Za-z0-9_]+)\s*<=\s*result_is_same_as_arg0$", text)
    if conditional_identity:
        guard = conditional_identity.group(1)
        return {
            "type": "conditional_identity_return",
            "guard": guard,
            "affordance": "possible_guarded_fast_path",
            "safety_constraint": "preserve_fallback_for_unobserved_inputs",
        }

    equivalent_identity = re.match(r"^([A-Za-z0-9_]+)\s*==\s*result_is_same_as_arg0$", text)
    if equivalent_identity:
        guard = equivalent_identity.group(1)
        return {
            "type": "identity_return_equivalence",
            "guard": guard,
            "affordance": "possible_guarded_fast_path_if_guard_is_semantically_valid",
            "safety_constraint": "preserve_fallback_for_unobserved_inputs",
        }

    if text == "result_is_same_as_arg0 one of { 0, 1 }":
        return {
            "type": "observed_identity_return",
            "guard": None,
            "affordance": "inspect_paths_for_guarded_fast_path",
            "safety_constraint": "do_not_assume_identity_for_all_inputs",
        }

    shape_match = re.match(r"^(result_(?:len|size|ndim))\s*==\s*(arg0_(?:len|size|ndim))$", text)
    if shape_match:
        return {
            "type": "shape_preserving",
            "guard": None,
            "affordance": "possible_avoid_redundant_shape_or_size_work",
            "safety_constraint": "preserve_shape_for_unobserved_inputs",
        }

    numeric_match = re.match(r"^(arg0_float|float_value)\s*==\s*(result|result_float_value)$", text)
    if numeric_match:
        return {
            "type": "numeric_value_preserving",
            "guard": None,
            "affordance": "possible_avoid_redundant_numeric_conversion",
            "safety_constraint": "preserve_numeric_equivalence",
        }

    if text == "raised == 0":
        return {
            "type": "stable_non_exception_path",
            "guard": None,
            "affordance": "possible_avoid_repeated_validation_on_observed_path",
            "safety_constraint": "preserve_error_behavior_for_unobserved_inputs",
        }

    return None


def evidence_packet(context: dict, target: str | None, rows: list[tuple[str, str, int]]) -> dict:
    evidence = []
    for ppt, invariant, score in rows:
        classified = classify_invariant(invariant)
        if classified is None:
            continue
        evidence.append(
            {
                "program_point": ppt,
                "raw_invariant": invariant,
                "score": score,
                "confidence": "dynamic_observation",
                **classified,
            }
        )

    return {
        "schema_version": "daikon-evidence-v1",
        "task_id": context.get("task_id"),
        "target_filter": target,
        "trace_source": context.get("trace_source"),
        "trace_target_source": context.get("trace_target_source"),
        "coverage": {
            "runtime_trace_rows": context.get("runtime_trace_rows", 0),
            "deduplicated_trace_rows": context.get("deduplicated_trace_rows", 0),
        },
        "evidence": evidence,
        "warnings": [
            "Daikon invariants are dynamic observations, not proofs.",
            "Use affordances only when they are local to the candidate edit.",
            "Preserve fallback behavior outside observed preconditions.",
        ],
        "rule_table": {
            "X <= result_is_same_as_arg0": "conditional_identity_return",
            "X == result_is_same_as_arg0": "identity_return_equivalence",
            "result_is_same_as_arg0 one of { 0, 1 }": "observed_identity_return",
            "result_len/result_size/result_ndim == arg0_len/arg0_size/arg0_ndim": "shape_preserving",
            "arg0_float == result or float_value == result_float_value": "numeric_value_preserving",
            "raised == 0": "stable_non_exception_path",
        },
    }


def target_name(target: str | None, rows: list[tuple[str, str, int]]) -> str | None:
    if target:
        return target.split(".")[-1]
    if not rows:
        return None
    ppt = rows[0][0].split(":::")[0]
    return ppt.split(".")[-1] if ppt else None


def build_rewrite_opportunities(target: str | None, evidence: list[dict]) -> list[dict]:
    name = target_name(target, [])
    name_l = (name or "").lower()
    types = {item.get("type") for item in evidence}
    guards = [item.get("guard") for item in evidence if item.get("guard")]
    opportunities: list[dict] = []

    if "conditional_identity_return" in types or "identity_return_equivalence" in types:
        opportunities.append(
            {
                "name": "guarded_fast_path",
                "why_safe": "A mined guard implies the function can return the original input on observed paths.",
                "rewrite_shape": "Add an early return under the guard and keep the original logic as fallback.",
                "use_when": "The guarded path is frequent in the measured workload or sits inside a hot caller loop.",
                "safety_checks": [
                    "Do not generalize the guard beyond the mined condition.",
                    "Keep fallback behavior for arrays, custom numeric objects, and exception paths.",
                ],
                "guards": guards,
            }
        )

    if (
        ("conditional_identity_return" in types or "observed_identity_return" in types)
        and any(token in name_l for token in ["validate", "check", "ensure"])
    ):
        opportunities.append(
            {
                "name": "split_validation_from_normalization",
                "why_safe": "Observed identity returns suggest some callers may only need validity checking, while full normalization is only needed at storage or comparison boundaries.",
                "rewrite_shape": "Separate the cheap validation path from the more expensive normalization/conversion path, then call normalization only where normalized representation is required.",
                "use_when": "The validation-like function is called repeatedly by a hot constructor, parser, or inner-loop helper.",
                "safety_checks": [
                    "Keep the original normalization behavior at boundaries that store, compare, or expose canonical values.",
                    "Preserve error behavior for invalid scalar and non-scalar inputs.",
                    "Validate with both correctness tests and the target performance benchmark.",
                ],
                "guards": guards,
            }
        )

    if "numeric_value_preserving" in types:
        opportunities.append(
            {
                "name": "avoid_redundant_numeric_conversion",
                "why_safe": "Mined evidence shows numeric value preservation on observed paths.",
                "rewrite_shape": "Cache, delay, or skip repeated conversion when the value is already in the required representation.",
                "use_when": "Conversion happens repeatedly in a hot helper or loop.",
                "safety_checks": [
                    "Preserve exactness rules for Fraction, Decimal, floats, and custom numeric types.",
                    "Keep fallback conversion for unobserved types.",
                ],
                "guards": guards,
            }
        )

    if "shape_preserving" in types:
        opportunities.append(
            {
                "name": "avoid_redundant_shape_or_size_work",
                "why_safe": "Observed paths preserve shape/size facts.",
                "rewrite_shape": "Avoid repeated shape computation, allocation, or validation when the preserved fact is already known.",
                "use_when": "Shape/size handling is inside a hot vectorized or collection-processing path.",
                "safety_checks": [
                    "Preserve behavior for empty, scalar, and ragged inputs.",
                    "Keep fallback validation where shape is not covered by mined evidence.",
                ],
                "guards": guards,
            }
        )

    return opportunities


def performance_packet(context: dict, target: str | None, rows: list[tuple[str, str, int]]) -> dict:
    packet = evidence_packet(context, target, rows)
    evidence = packet["evidence"]
    packet["schema_version"] = "daikon-performance-guidance-v1"
    packet["hot_path"] = {
        "target": target,
        "runtime_trace_rows": context.get("runtime_trace_rows", 0),
        "deduplicated_trace_rows": context.get("deduplicated_trace_rows", 0),
        "is_cost_proxy": True,
        "note": "Runtime trace rows indicate coverage of instrumented functions, not precise CPU time. Confirm profitability with profiling or the official performance benchmark.",
    }
    packet["rewrite_opportunities"] = build_rewrite_opportunities(target, evidence)
    packet["agent_instructions"] = [
        "First decide whether the target is on the measured hot path.",
        "Use invariants as safety evidence, not as a complete optimization plan.",
        "Prefer rewrite opportunities that are both locally safe and plausibly profitable.",
        "When using split_validation_from_normalization, preserve normalization at representation boundaries.",
        "After editing, run correctness tests and performance evaluation.",
    ]
    packet["warnings"].append(
        "A local invariant can justify safety but still fail to improve benchmark time if the guarded path is not the dominant cost."
    )
    return packet


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--context", required=True, type=Path)
    parser.add_argument("--target", default=None, help="Substring filter for program points, e.g. validate_power")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--evidence-json", action="store_true", help="Emit fixed-schema tool evidence for agent injection")
    parser.add_argument("--performance-json", action="store_true", help="Emit performance-relevant invariant guidance for optimization agents")
    args = parser.parse_args()

    context = load_context(args.context)
    selected = select_invariants(context, args.target, args.limit)
    report = {
        "task_id": context.get("task_id"),
        "trace_source": context.get("trace_source"),
        "trace_target_source": context.get("trace_target_source"),
        "target_filter": args.target,
        "runtime_trace_rows": context.get("runtime_trace_rows", 0),
        "deduplicated_trace_rows": context.get("deduplicated_trace_rows", 0),
        "coverage_warning": None,
        "selected_invariants": [
            {"program_point": ppt, "invariant": inv, "score": score}
            for ppt, inv, score in selected
        ],
        "optimization_implications": implications(selected),
    }
    if report["runtime_trace_rows"] == 0:
        report["coverage_warning"] = "No runtime observations were collected. Treat this as no evidence, not as proof that no invariant exists."
    elif not selected:
        report["coverage_warning"] = "Runtime observations exist, but no invariants matched the target filter."

    if args.evidence_json:
        print(json.dumps(evidence_packet(context, args.target, selected), indent=2))
        return 0

    if args.performance_json:
        print(json.dumps(performance_packet(context, args.target, selected), indent=2))
        return 0

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print("Daikon Invariant Tool Report")
    print(f"Task: {report['task_id']}")
    print(f"Trace source: {report['trace_source']}")
    if report.get("trace_target_source"):
        print(f"Trace target source: {report['trace_target_source']}")
    print(f"Target filter: {args.target or '<none>'}")
    print(f"Coverage: {report['runtime_trace_rows']} observations, {report['deduplicated_trace_rows']} unique observed shapes")
    if report["coverage_warning"]:
        print(f"Warning: {report['coverage_warning']}")
    print("")
    print("Useful invariants:")
    if selected:
        for ppt, inv, score in selected:
            print(f"- {ppt}: {inv}  [score={score}]")
    else:
        print("- <none>")
    print("")
    print("Optimization implications:")
    if report["optimization_implications"]:
        for item in report["optimization_implications"]:
            print(f"- {item}")
    else:
        print("- No optimization implication inferred from the selected invariants.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
