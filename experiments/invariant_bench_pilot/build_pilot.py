#!/usr/bin/env python3
"""Build a small invariant-focused annotation layer over SWE-Perf cases."""

from __future__ import annotations

import csv
import ast
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "data" / "sweperf_20.jsonl"
OUT_DIR = ROOT / "experiments" / "invariant_bench_pilot"
DRIFT_DIR = ROOT / "experiments" / "swe_perf_pilot" / "results" / "invariant_drift"


ANNOTATIONS: dict[str, dict[str, str]] = {
    "astropy__astropy-16065": {
        "optimization_type": "output-format stabilization",
        "invariant_type": "api_contract",
        "hidden_invariant": "Diff output should be independent of the active Astropy console width/line display configuration.",
        "invariant_source": "patch + changelog",
        "is_invariant_explicit": "partially",
        "semantic_role": "safety",
        "agent_relevance": "An optimizer that removes formatting/config guards could make output depend on ambient terminal settings.",
        "confidence": "medium",
        "notes": "The patch wraps report_diff_values under temporary display settings; this is an API/output contract rather than a numeric invariant.",
    },
    "astropy__astropy-16058": {
        "optimization_type": "split validation from normalization",
        "invariant_type": "validation_normalization",
        "hidden_invariant": "Some power values only need validation and can be returned unchanged; canonical normalization is only required at representation/storage boundaries.",
        "invariant_source": "patch + Daikon trace",
        "is_invariant_explicit": "no",
        "semantic_role": "safety_and_opportunity",
        "agent_relevance": "This invariant can guide an agent from a local fast path toward the higher-value validate_power/sanitize_power split.",
        "confidence": "high",
        "notes": "This is the current showcase case: Daikon observes identity-return paths and the expert patch separates validate_power from sanitize_power.",
    },
    "astropy__astropy-15948": {
        "optimization_type": "masked-array dispatch protocol repair",
        "invariant_type": "representation",
        "hidden_invariant": "Masked array function helpers must preserve the dispatch return protocol: data, mask, and out are represented explicitly and consistently.",
        "invariant_source": "patch",
        "is_invariant_explicit": "partially",
        "semantic_role": "safety",
        "agent_relevance": "Micro-optimizations around mask copying or tuple returns can silently break masked-array representation semantics.",
        "confidence": "medium",
        "notes": "Large performance gain, but many edits are protocol-preserving helper fixes; dynamic drift did not change selected important invariants.",
    },
    "astropy__astropy-15710": {
        "optimization_type": "numpy API compatibility and unit-preserving dispatch",
        "invariant_type": "api_contract",
        "hidden_invariant": "Quantity wrappers around NumPy functions must preserve unit semantics while matching the supported NumPy function signature.",
        "invariant_source": "patch + changed API surface",
        "is_invariant_explicit": "partially",
        "semantic_role": "safety",
        "agent_relevance": "An agent optimizing wrappers must not drop unit conversion, keyword compatibility, or return-unit propagation.",
        "confidence": "medium",
        "notes": "Touches many NumPy helper wrappers, including unwrap period, choose mode, nanmedian kwargs, and cross-like helpers.",
    },
    "astropy__astropy-15228": {
        "optimization_type": "missing function helper dispatch",
        "invariant_type": "shape_and_api_contract",
        "hidden_invariant": "Quantity nanmedian must preserve NumPy nanmedian semantics across array shapes and axis combinations.",
        "invariant_source": "patch + changelog",
        "is_invariant_explicit": "yes",
        "semantic_role": "safety",
        "agent_relevance": "A performance or compatibility patch must route through the helper layer without changing shape/axis behavior.",
        "confidence": "high",
        "notes": "Changelog explicitly states the shape/axis failure mode for NumPy >= 1.25.",
    },
    "astropy__astropy-14590": {
        "optimization_type": "mask reuse and where-aware ufunc handling",
        "invariant_type": "ownership_lifetime",
        "hidden_invariant": "Mask combination must respect where/out semantics and avoid unintended aliasing unless copy=False is explicitly safe.",
        "invariant_source": "patch",
        "is_invariant_explicit": "partially",
        "semantic_role": "safety_and_opportunity",
        "agent_relevance": "Memory reuse or copy-elision optimizations are unsafe unless mask aliasing and where masking are preserved.",
        "confidence": "high",
        "notes": "This is a strong example for ownership/lifetime invariants in array performance code.",
    },
    "astropy__astropy-14413": {
        "optimization_type": "unit-format output contract",
        "invariant_type": "api_contract",
        "hidden_invariant": "Console, LaTeX, and Unicode unit formatters must preserve spacing, superscript, and scale formatting contracts across output backends.",
        "invariant_source": "patch + docs",
        "is_invariant_explicit": "yes",
        "semantic_role": "safety",
        "agent_relevance": "String-format simplifications can be benchmark-neutral but user-visible; output contracts need invariant checks.",
        "confidence": "medium",
        "notes": "This case is more about semantic output compatibility than classic runtime performance.",
    },
    "astropy__astropy-13817": {
        "optimization_type": "mixed cleanup and numerical helper maintenance",
        "invariant_type": "mixed_api_numeric",
        "hidden_invariant": "Import cleanup and numerical helper edits must preserve public API availability and numerical behavior.",
        "invariant_source": "patch",
        "is_invariant_explicit": "no",
        "semantic_role": "safety",
        "agent_relevance": "This case needs further manual triage because the patch mixes lint/import edits with real numerical helper changes.",
        "confidence": "low",
        "notes": "Keep as a low-confidence pilot row; it may be excluded from stricter analysis.",
    },
    "astropy__astropy-13745": {
        "optimization_type": "dtype-preserving boundary check",
        "invariant_type": "numeric_precision",
        "hidden_invariant": "Latitude validation must compare boundary values in the input dtype so float32 pi/2 is accepted correctly.",
        "invariant_source": "patch + changelog",
        "is_invariant_explicit": "yes",
        "semantic_role": "safety",
        "agent_relevance": "An optimizer must preserve dtype-sensitive boundary semantics, not replace them with faster but differently rounded constants.",
        "confidence": "high",
        "notes": "Clear numeric precision invariant from changelog and one-line patch.",
    },
    "astropy__astropy-13734": {
        "optimization_type": "fixed-width table metadata handling",
        "invariant_type": "representation",
        "hidden_invariant": "Fixed-width ASCII readers/writers must preserve configured header rows and per-column metadata through parsing and serialization.",
        "invariant_source": "patch + docs",
        "is_invariant_explicit": "partially",
        "semantic_role": "safety",
        "agent_relevance": "Optimizing table I/O must not assume a single name-only header row or discard metadata-bearing rows.",
        "confidence": "high",
        "notes": "Good representation-invariant case: header_rows controls how column attributes map into fixed-width text.",
    },
    "astropy__astropy-13496": {
        "optimization_type": "memoized physical-type id",
        "invariant_type": "cache_consistency",
        "hidden_invariant": "The cached physical type id must depend only on the decomposed unit bases and powers, and must not be serialized across sessions.",
        "invariant_source": "patch",
        "is_invariant_explicit": "partially",
        "semantic_role": "safety_and_opportunity",
        "agent_relevance": "Caching can speed repeated physical-type lookups, but only if cache invalidation and pickling preserve session-independent identity semantics.",
        "confidence": "high",
        "notes": "Strong cache-consistency case: `_type_id` is memoized but explicitly removed from `__getstate__`.",
    },
    "astropy__astropy-12842": {
        "optimization_type": "time serialization refactor",
        "invariant_type": "serialization_contract",
        "hidden_invariant": "Time and TimeDelta serialization/deserialization must preserve format, scale, and delta metadata across table and ECSV round trips.",
        "invariant_source": "patch + changelog",
        "is_invariant_explicit": "partially",
        "semantic_role": "safety",
        "agent_relevance": "Refactoring shared serialization code can improve maintainability/performance, but an agent must preserve hidden round-trip metadata invariants.",
        "confidence": "medium",
        "notes": "Large refactor around TimeInfoBase, TimeInfo, and TimeDeltaInfo; needs deeper manual validation for exact invariant boundaries.",
    },
    "matplotlib__matplotlib-28104": {
        "optimization_type": "separate hatch color from edge color",
        "invariant_type": "state_consistency",
        "hidden_invariant": "Patch hatch color and edge color are independent artist state fields, with defined rcParam fallback behavior.",
        "invariant_source": "patch + docs",
        "is_invariant_explicit": "yes",
        "semantic_role": "safety",
        "agent_relevance": "Optimizations or simplifications in artist property handling must not couple independently configurable visual states.",
        "confidence": "high",
        "notes": "Good state-consistency/API-contract case with explicit documentation and gallery example.",
    },
    "matplotlib__matplotlib-24250": {
        "optimization_type": "callback connection ordering",
        "invariant_type": "event_ordering",
        "hidden_invariant": "Figure pick callbacks must be connected after shared mouse/key handlers so event processing and pick behavior remain consistent.",
        "invariant_source": "patch",
        "is_invariant_explicit": "no",
        "semantic_role": "safety_and_opportunity",
        "agent_relevance": "Moving callback registration can look like a harmless micro-optimization, but ordering is semantically observable in event dispatch.",
        "confidence": "medium",
        "notes": "Small patch with likely event-ordering invariant; needs issue/PR text for stronger evidence.",
    },
    "matplotlib__matplotlib-23712": {
        "optimization_type": "remove eager garbage collection on figure destruction",
        "invariant_type": "resource_lifetime",
        "hidden_invariant": "Destroying figures must disconnect and clear managers sufficiently; correctness should not depend on forced generation-1 garbage collection after every destroy.",
        "invariant_source": "patch",
        "is_invariant_explicit": "partially",
        "semantic_role": "safety_and_opportunity",
        "agent_relevance": "Removing cleanup work is profitable only if object lifetime and callback cleanup invariants still hold without explicit gc.collect.",
        "confidence": "high",
        "notes": "Clear resource-lifetime/cost tradeoff: performance comes from deleting explicit GC calls.",
    },
    "mwaskom__seaborn-2458": {
        "optimization_type": "use component-transformed data for rugplot",
        "invariant_type": "data_representation",
        "hidden_invariant": "Rugplot must iterate over component-transformed data so datetime and other converted variables reach Matplotlib in plotting-compatible representation.",
        "invariant_source": "patch + changelog",
        "is_invariant_explicit": "yes",
        "semantic_role": "safety",
        "agent_relevance": "An optimization that bypasses data conversion can be faster but unsafe for non-numeric or datetime inputs.",
        "confidence": "high",
        "notes": "One-line but strong representation invariant: `from_comp_data=True` is the semantic requirement.",
    },
    "mwaskom__seaborn-2449": {
        "optimization_type": "color-cycle and artist style refactor",
        "invariant_type": "style_state_consistency",
        "hidden_invariant": "Axes-level plotting functions must preserve Matplotlib color-cycle integration, explicit style kwargs, hue mapping, and artist edge/fill color consistency.",
        "invariant_source": "patch + changelog",
        "is_invariant_explicit": "partially",
        "semantic_role": "safety_and_opportunity",
        "agent_relevance": "Performance/style refactors over plotting helpers must maintain coupled visual-state invariants across relational, categorical, and distribution plots.",
        "confidence": "medium",
        "notes": "Large multi-file patch; useful for taxonomy but should be split into smaller invariant units later.",
    },
    "mwaskom__seaborn-2389": {
        "optimization_type": "color conversion simplification",
        "invariant_type": "data_representation",
        "hidden_invariant": "Cluster color preprocessing must preserve color values, labels, missing-value handling, and alignment for list-like, Series, and DataFrame inputs.",
        "invariant_source": "patch",
        "is_invariant_explicit": "partially",
        "semantic_role": "safety_and_opportunity",
        "agent_relevance": "Removing DataFrame/Series-specific conversion paths can be faster only if upstream preprocessing still preserves index alignment and NA semantics.",
        "confidence": "medium",
        "notes": "Potentially risky representation case because color conversion no longer directly handles pandas objects in `_convert_colors`.",
    },
    "mwaskom__seaborn-2313": {
        "optimization_type": "indexed color alignment check",
        "invariant_type": "index_alignment",
        "hidden_invariant": "Row/column color annotations with pandas indices must align to the data index/columns; unindexed data cannot safely consume indexed colors.",
        "invariant_source": "patch + docstring",
        "is_invariant_explicit": "yes",
        "semantic_role": "safety",
        "agent_relevance": "Optimizing away index checks or reindexing can silently mislabel clustered rows/columns.",
        "confidence": "high",
        "notes": "Clear index-alignment invariant in `_preprocess_colors`.",
    },
    "mwaskom__seaborn-2224": {
        "optimization_type": "distribution plot color-map and multiple-density handling",
        "invariant_type": "visual_encoding",
        "hidden_invariant": "Distribution plot defaults must preserve meaningful color gradients, discrete-variable detection, and multiple-density normalization/stacking semantics.",
        "invariant_source": "patch + examples",
        "is_invariant_explicit": "partially",
        "semantic_role": "safety_and_opportunity",
        "agent_relevance": "Visualization performance changes can appear numerically harmless while changing visual encoding invariants that users rely on.",
        "confidence": "medium",
        "notes": "Includes docs/example changes; exact performance-relevant invariant needs more issue context.",
    },
}


def load_rows() -> list[dict[str, Any]]:
    return [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]


def changed_files(patch: str) -> list[str]:
    return re.findall(r"^diff --git a/(\S+) b/\S+", patch, flags=re.MULTILINE)


def load_patch_functions(row: dict[str, Any]) -> dict[str, list[str]]:
    raw = row.get("patch_functions", {})
    if isinstance(raw, str):
        return json.loads(raw) if raw else {}
    return raw or {}


def drift_summary(instance_id: str, label: str) -> dict[str, Any]:
    path = DRIFT_DIR / f"{instance_id}.{label}.drift.json"
    if not path.exists():
        return {
            "available": False,
            "before_rows": "",
            "after_rows": "",
            "removed": "",
            "added": "",
            "drift": "",
            "path": "",
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    counts = data.get("counts", {})
    before = data.get("before_coverage", {})
    after = data.get("after_coverage", {})
    removed = int(counts.get("removed", 0) or 0)
    added = int(counts.get("added", 0) or 0)
    return {
        "available": True,
        "before_rows": before.get("runtime_trace_rows", ""),
        "after_rows": after.get("runtime_trace_rows", ""),
        "removed": removed,
        "added": added,
        "drift": bool(removed or added),
        "path": str(path.relative_to(ROOT)),
    }


def build() -> list[dict[str, Any]]:
    out = []
    by_id = {row["instance_id"]: row for row in load_rows()}
    for instance_id, ann in ANNOTATIONS.items():
        row = by_id[instance_id]
        patch_functions = load_patch_functions(row)
        human_drift = drift_summary(instance_id, "human_patch")
        codex_drift = drift_summary(instance_id, "codex_baseline_small")
        out.append(
            {
                "instance_id": instance_id,
                "repo": row["repo"],
                "human_performance": row.get("human_performance", ""),
                "changed_files": ";".join(changed_files(row["patch"])),
                "patch_functions": json.dumps(patch_functions, sort_keys=True),
                "efficiency_test_count": len(ast.literal_eval(row["efficiency_test"])) if isinstance(row.get("efficiency_test"), str) else "",
                "optimization_type": ann["optimization_type"],
                "invariant_type": ann["invariant_type"],
                "hidden_invariant": ann["hidden_invariant"],
                "invariant_source": ann["invariant_source"],
                "is_invariant_explicit": ann["is_invariant_explicit"],
                "semantic_role": ann["semantic_role"],
                "agent_relevance": ann["agent_relevance"],
                "confidence": ann["confidence"],
                "human_drift_available": human_drift["available"],
                "human_drift": human_drift["drift"],
                "human_drift_removed": human_drift["removed"],
                "human_drift_added": human_drift["added"],
                "human_before_rows": human_drift["before_rows"],
                "human_after_rows": human_drift["after_rows"],
                "codex_baseline_drift_available": codex_drift["available"],
                "codex_baseline_drift": codex_drift["drift"],
                "codex_baseline_drift_removed": codex_drift["removed"],
                "codex_baseline_drift_added": codex_drift["added"],
                "codex_before_rows": codex_drift["before_rows"],
                "codex_after_rows": codex_drift["after_rows"],
                "notes": ann["notes"],
            }
        )
    return out


def write_outputs(rows: list[dict[str, Any]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / "annotations.csv"
    json_path = OUT_DIR / "annotations.json"
    summary_path = OUT_DIR / "summary.md"

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    json_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    invariant_counts = Counter(row["invariant_type"] for row in rows)
    explicit_counts = Counter(row["is_invariant_explicit"] for row in rows)
    confidence_counts = Counter(row["confidence"] for row in rows)
    human_available = [row for row in rows if row["human_drift_available"]]
    codex_available = [row for row in rows if row["codex_baseline_drift_available"]]
    lines = [
        "# InvariantBench Pilot",
        "",
        "This is a small invariant-focused annotation layer over a 20-case SWE-Perf pilot slice.",
        "",
        "## Scope",
        "",
        f"- Cases: `{len(rows)}`",
        "- Dataset: `data/sweperf_20.jsonl`",
        "- Repository coverage: Astropy, Matplotlib, and Seaborn.",
        "",
        "## Taxonomy Counts",
        "",
    ]
    lines.extend(f"- `{key}`: `{value}`" for key, value in sorted(invariant_counts.items()))
    lines.extend(["", "## Explicitness", ""])
    lines.extend(f"- `{key}`: `{value}`" for key, value in sorted(explicit_counts.items()))
    lines.extend(["", "## Confidence", ""])
    lines.extend(f"- `{key}`: `{value}`" for key, value in sorted(confidence_counts.items()))
    lines.extend(
        [
            "",
            "## Existing Drift Evidence",
            "",
            f"- Human patch drift reports available: `{len(human_available)}/{len(rows)}`",
            f"- Human patch drift cases: `{sum(bool(row['human_drift']) for row in human_available)}/{len(human_available)}`",
            f"- Codex baseline drift reports available: `{len(codex_available)}/{len(rows)}`",
            f"- Codex baseline drift cases: `{sum(bool(row['codex_baseline_drift']) for row in codex_available)}/{len(codex_available)}`",
            "",
            "## Preliminary Takeaway",
            "",
            "The pilot supports the empirical-study direction, but it is not yet a claim about prevalence.",
            "It shows that SWE-Perf patches can be annotated in terms of hidden semantic invariants,",
            "and that invariant drift can be measured for both human and agent patches when runtime traces cover the edited code.",
            "",
            "The next step is to add stricter manual validation for whether each invariant is truly hidden, explicit, or only inferred by the annotator, then run drift extraction on the remaining cases.",
            "",
            "## Files",
            "",
            "- `annotations.csv`: spreadsheet-friendly annotation table.",
            "- `annotations.json`: machine-readable annotation table.",
        ]
    )
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(csv_path)
    print(json_path)
    print(summary_path)


def main() -> int:
    rows = build()
    write_outputs(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
