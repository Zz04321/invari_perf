#!/usr/bin/env python3
"""Build a machine-readable Core-10 audit table."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "experiments" / "invariant_bench_pilot"


AUDIT = {
    "astropy__astropy-16058": {
        "optimization": "Split cheap validation from canonical power normalization.",
        "invariant": "Hot-path power validation can return the original value; canonical normalization is required at representation/storage boundaries.",
        "evidence": "Patch introduces sanitize_power, changes validate_power semantics, updates unit power tests, and has Daikon drift.",
        "agent_risk": "A generic agent may only optimize local helper calls and miss the validation/normalization split.",
        "paper_status": "main_showcase",
    },
    "astropy__astropy-15228": {
        "optimization": "Route np.nanmedian through a dedicated Quantity helper.",
        "invariant": "Quantity nanmedian must preserve NumPy shape, axis, and out semantics.",
        "evidence": "Changelog names shape/axis failures; tests parameterize axis and check out identity.",
        "agent_risk": "A generic agent may treat helper dispatch paths as interchangeable.",
        "paper_status": "core_api_contract",
    },
    "astropy__astropy-14590": {
        "optimization": "Use where/out/copy-aware mask combination to avoid unnecessary copies.",
        "invariant": "Mask reuse is safe only when where, out, and aliasing behavior are preserved.",
        "evidence": "Patch adds where/copy parameters and tests selected/unselected output data and masks.",
        "agent_risk": "A generic agent may remove copies without preserving aliasing and where semantics.",
        "paper_status": "core_ownership_lifetime",
    },
    "astropy__astropy-13745": {
        "optimization": "Use dtype-specific latitude boundary constants.",
        "invariant": "Latitude boundary validation must compare values in the input dtype.",
        "evidence": "Patch changes boundary constant type; changelog and tests cover float32 pi/2.",
        "agent_risk": "A generic agent may simplify or hoist constants and change dtype-sensitive behavior.",
        "paper_status": "core_numeric_precision",
    },
    "astropy__astropy-13734": {
        "optimization": "Support multi-row fixed-width table metadata headers.",
        "invariant": "Fixed-width table read/write must preserve configured metadata header rows.",
        "evidence": "Patch introduces header_rows and tests read/write round trips.",
        "agent_risk": "A generic agent may assume a single name header row and drop metadata.",
        "paper_status": "core_representation",
    },
    "astropy__astropy-13496": {
        "optimization": "Memoize UnitBase physical-type id.",
        "invariant": "Cached physical-type id depends only on decomposed bases/powers and must not be serialized.",
        "evidence": "Patch adds lazy _type_id cache and removes it from __getstate__; Daikon drift reports no invariant changes under a large trace.",
        "agent_risk": "A generic agent may add a cache but fail to exclude it from pickle state.",
        "paper_status": "core_cache_consistency",
    },
    "matplotlib__matplotlib-28104": {
        "optimization": "Separate hatch color from edge color in artist state.",
        "invariant": "Hatch color and edge color are independent states with defined rcParam fallback.",
        "evidence": "Docs describe fallback rules; tests check setter ordering and rcParam behavior.",
        "agent_risk": "A generic agent may merge state fields or reorder setters incorrectly.",
        "paper_status": "core_needs_drift",
    },
    "matplotlib__matplotlib-23712": {
        "optimization": "Remove eager gc.collect calls from figure destruction.",
        "invariant": "Figure destruction must clear managers/callbacks without relying on forced generation-1 GC.",
        "evidence": "Patch removes gc import and gc.collect calls; source/test evidence still missing.",
        "agent_risk": "A generic agent may remove cleanup work without proving resource lifetime safety.",
        "paper_status": "core_needs_evidence",
    },
    "mwaskom__seaborn-2458": {
        "optimization": "Use component-transformed data for rugplot.",
        "invariant": "Datetime and converted variables must reach Matplotlib in plotting-compatible representation.",
        "evidence": "Changelog states datetime bug; patch uses from_comp_data=True; test checks Matplotlib date conversion.",
        "agent_risk": "A generic agent may bypass transformation layers for speed.",
        "paper_status": "core_needs_drift",
    },
    "mwaskom__seaborn-2313": {
        "optimization": "Reject indexed color annotations with unindexed matrix data.",
        "invariant": "Indexed row/column colors must align to data index/columns, or be rejected.",
        "evidence": "Patch raises TypeError for mixed index types; docs and tests cover index matching.",
        "agent_risk": "A generic agent may drop alignment checks or convert indexed data too early.",
        "paper_status": "core_needs_drift",
    },
}


def main() -> int:
    review_rows = {
        row["instance_id"]: row
        for row in csv.DictReader((OUT_DIR / "case_review.csv").open(encoding="utf-8"))
    }
    annotation_rows = {
        row["instance_id"]: row
        for row in csv.DictReader((OUT_DIR / "annotations.csv").open(encoding="utf-8"))
    }
    rows = []
    for instance_id, audit in AUDIT.items():
        review = review_rows[instance_id]
        annotation = annotation_rows[instance_id]
        rows.append(
            {
                "instance_id": instance_id,
                "repo": annotation["repo"],
                "invariant_type": annotation["invariant_type"],
                "confidence": annotation["confidence"],
                "human_drift_available": annotation["human_drift_available"],
                "human_drift": annotation["human_drift"],
                "human_drift_removed": annotation["human_drift_removed"],
                "human_drift_added": annotation["human_drift_added"],
                "paper_role": review["paper_role"],
                **audit,
            }
        )

    csv_path = OUT_DIR / "core10_audit.csv"
    json_path = OUT_DIR / "core10_audit.json"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    json_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(csv_path)
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
