#!/usr/bin/env python3
"""Mine likely invariants for SWE-Perf task astropy__astropy-16058 with Daikon.

This is a Python-to-Daikon adapter. It emits Daikon declaration/trace files from
observed values around the functions touched by the real SWE-Perf patch, then
invokes Daikon to infer likely invariants.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Iterable


TASK_ID = "astropy__astropy-16058"
ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "experiments" / "swe_perf_pilot" / "results" / "daikon_mining" / TASK_ID
STABLE_CONTEXT = ROOT / "experiments" / "swe_perf_pilot" / "invariants" / f"{TASK_ID}.daikon.json"


@dataclass(frozen=True)
class Observation:
    ppt: str
    values: dict[str, int | float]


def maybe_simple_fraction(p, max_denominator=100):
    """Equivalent model of the relevant Astropy helper from SWE-Perf 16058."""
    if p == 0 or p.__class__ is int or p.__class__ is Fraction:
        return p
    n, d = p.as_integer_ratio()
    a = n // d
    p0, q0, p1, q1 = 0, 1, 1, 0
    while True:
        q2 = q0 + a * q1
        if q2 > max_denominator:
            break
        p0, q0, p1, q1 = p1, q1, p0 + a * p1, q2
        n, d = d, n - a * d
        a = n // d
    k = (max_denominator - q0) // q1
    bound1 = Fraction(p0 + k * p1, q0 + k * q1)
    bound2 = Fraction(p1, q1)
    if abs(bound2 - p) <= abs(bound1 - p):
        return bound2
    return bound1


def validate_power(p):
    """Equivalent model of the real patched validate_power fast paths."""
    if p.__class__ is int or p.__class__ is Fraction:
        return p
    try:
        float(p)
    except Exception:
        raise ValueError("non-scalar powers omitted from this pilot") from None
    return p


def sanitize_power(p):
    """Equivalent model of the new helper introduced by SWE-Perf 16058."""
    if p.__class__ is int:
        return p

    denom = getattr(p, "denominator", None)
    if denom is None:
        p = maybe_simple_fraction(p)
        if p.__class__ is float:
            return p

    if p.denominator == 1:
        return p.numerator

    if p.numerator == 0:
        return 0

    return p


def numeric_features(p, result) -> dict[str, int | float]:
    denominator = getattr(p, "denominator", 0)
    numerator = getattr(p, "numerator", 0)
    return {
        "is_int": int(p.__class__ is int),
        "is_fraction": int(p.__class__ is Fraction),
        "is_float": int(p.__class__ is float),
        "is_zero": int(p == 0),
        "denominator": int(denominator),
        "numerator": int(numerator),
        "float_value": float(p),
        "result_is_same_object": int(result is p),
        "result_is_int": int(result.__class__ is int),
        "result_is_fraction": int(result.__class__ is Fraction),
        "result_is_float": int(result.__class__ is float),
        "result_float_value": float(result),
    }


def branch_for(function_name: str, p, result) -> str:
    if function_name == "validate_power":
        if p.__class__ is int or p.__class__ is Fraction:
            return "fast_exact_type"
        return "float_convertible"

    if function_name == "maybe_simple_fraction":
        if p == 0 or p.__class__ is int or p.__class__ is Fraction:
            return "fast_identity"
        if result.__class__ is Fraction:
            return "fraction_result"
        return "float_result"

    if function_name == "sanitize_power":
        if p.__class__ is int:
            return "fast_int"
        if result.__class__ is int:
            return "integer_result"
        if result.__class__ is Fraction:
            return "fraction_result"
        return "float_result"

    raise ValueError(function_name)


def collect_observations() -> list[Observation]:
    inputs = [
        0,
        1,
        2,
        -1,
        0.0,
        1.0,
        2.0,
        0.5,
        1.5,
        1.0 / 3.0,
        math.pi,
        Fraction(0, 1),
        Fraction(1, 1),
        Fraction(2, 1),
        Fraction(1, 2),
        Fraction(3, 2),
        Fraction(7, 3),
    ]
    functions = {
        "validate_power": validate_power,
        "maybe_simple_fraction": maybe_simple_fraction,
        "sanitize_power": sanitize_power,
    }
    observations: list[Observation] = []
    for function_name, fn in functions.items():
        for p in inputs:
            try:
                result = fn(p)
            except Exception:
                continue
            branch = branch_for(function_name, p, result)
            ppt = f"astropy.units.utils.{function_name}.{branch}:::POINT"
            observations.append(Observation(ppt=ppt, values=numeric_features(p, result)))
    return observations


def write_decls(path: Path, ppts: Iterable[str], variables: Iterable[str]) -> None:
    lines = [
        "decl-version 2.0",
        "input-language Python",
        "var-comparability none",
        "",
    ]
    for ppt in sorted(ppts):
        lines.extend([f"ppt {ppt}", "ppt-type point"])
        for name in variables:
            rep_type = "double" if "float_value" in name else "int"
            dec_type = "double" if rep_type == "double" else "int"
            lines.extend(
                [
                    f"variable {name}",
                    "  var-kind variable",
                    f"  dec-type {dec_type}",
                    f"  rep-type {rep_type}",
                    "  comparability -1",
                ]
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_dtrace(path: Path, observations: Iterable[Observation], variables: Iterable[str]) -> None:
    lines: list[str] = []
    for obs in observations:
        lines.extend(["", obs.ppt])
        for name in variables:
            value = obs.values[name]
            if isinstance(value, float):
                value = repr(value)
            lines.extend([name, str(value), "1"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_invariants_by_ppt(daikon_output: str) -> dict[str, list[str]]:
    by_ppt: dict[str, list[str]] = {}
    current_ppt: str | None = None
    for raw in daikon_output.splitlines():
        line = raw.strip()
        if not line or line.startswith("="):
            continue
        if line.endswith(":::POINT"):
            current_ppt = line
            by_ppt[current_ppt] = []
            continue
        if current_ppt is None:
            continue
        if line.startswith(("Daikon version", "Reading ", "(read ", "Processing ", "Exiting ")):
            continue
        by_ppt[current_ppt].append(line)
    return by_ppt


def select_agent_context(by_ppt: dict[str, list[str]]) -> list[dict[str, str]]:
    """Pick invariants that are compact enough to pass to an optimizer agent."""
    selected: list[dict[str, str]] = []
    interesting = (
        "result_is_same_object == 1",
        "is_int == 1",
        "is_fraction == 0",
        "is_float == 1",
        "result_is_fraction == 1",
        "result_is_int",
        "float_value == result_float_value",
        "denominator one of",
    )
    for ppt, invariants in by_ppt.items():
        for invariant in invariants:
            if any(token in invariant for token in interesting):
                selected.append(
                    {
                        "program_point": ppt,
                        "likely_invariant": invariant,
                    }
                )
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--daikon-jar", required=True, type=Path)
    args = parser.parse_args()

    observations = collect_observations()
    variables = list(observations[0].values)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    decls = OUT_DIR / "astropy_16058.decls"
    dtrace = OUT_DIR / "astropy_16058.dtrace"
    raw_output = OUT_DIR / "daikon_output.txt"
    context_json = OUT_DIR / "invariant_context.json"

    write_decls(decls, {obs.ppt for obs in observations}, variables)
    write_dtrace(dtrace, observations, variables)

    proc = subprocess.run(
        ["java", "-cp", str(args.daikon_jar), "daikon.Daikon", str(decls), str(dtrace)],
        check=True,
        text=True,
        capture_output=True,
    )
    raw_output.write_text(proc.stdout, encoding="utf-8")

    by_ppt = parse_invariants_by_ppt(proc.stdout)
    summary = {
        "task_id": TASK_ID,
        "source": "Daikon 5.8.24 over Python adapter traces for real SWE-Perf patch functions",
        "patch_functions": {
            "astropy/units/utils.py": [
                "validate_power",
                "maybe_simple_fraction",
                "sanitize_power",
            ]
        },
        "observations": len(observations),
        "artifacts": {
            "decls": str(decls.relative_to(ROOT)),
            "dtrace": str(dtrace.relative_to(ROOT)),
            "daikon_output": str(raw_output.relative_to(ROOT)),
        },
        "likely_invariants_by_program_point": by_ppt,
        "agent_context_candidates": select_agent_context(by_ppt),
    }
    context_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    STABLE_CONTEXT.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"task: {TASK_ID}")
    print(f"observations: {len(observations)}")
    print(f"decls: {decls}")
    print(f"dtrace: {dtrace}")
    print(f"daikon_output: {raw_output}")
    print(f"invariant_context: {context_json}")
    print(f"stable_context: {STABLE_CONTEXT}")
    print("\nagent context candidates:")
    for item in summary["agent_context_candidates"][:24]:
        print(f"- {item['program_point']}: {item['likely_invariant']}")


if __name__ == "__main__":
    main()
