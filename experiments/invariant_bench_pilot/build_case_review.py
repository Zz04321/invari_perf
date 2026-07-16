#!/usr/bin/env python3
"""Build machine-readable review labels for the InvariantBench pilot."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "experiments" / "invariant_bench_pilot"


REVIEW: dict[str, dict[str, str]] = {
    "astropy__astropy-16058": {
        "review_category": "A - Core",
        "paper_role": "main showcase",
        "next_action": "Write a detailed case narrative linking validate_power/sanitize_power to Daikon evidence and expert patch.",
    },
    "astropy__astropy-14590": {
        "review_category": "A - Core",
        "paper_role": "ownership/lifetime invariant",
        "next_action": "Collect issue or test evidence for where/out aliasing behavior.",
    },
    "astropy__astropy-13745": {
        "review_category": "A - Core",
        "paper_role": "numeric precision invariant",
        "next_action": "Keep as a clear safety invariant case; no urgent extra mining needed.",
    },
    "astropy__astropy-13734": {
        "review_category": "A - Core",
        "paper_role": "representation invariant",
        "next_action": "Map header_rows behavior to one concrete test or documentation paragraph.",
    },
    "astropy__astropy-13496": {
        "review_category": "A - Core",
        "paper_role": "cache consistency invariant",
        "next_action": "Run drift extraction and collect pickle/cache evidence from tests or patch text.",
    },
    "matplotlib__matplotlib-28104": {
        "review_category": "A - Core",
        "paper_role": "state consistency invariant",
        "next_action": "Debug drift extraction; collect docs/gallery evidence for hatchcolor fallback.",
    },
    "matplotlib__matplotlib-23712": {
        "review_category": "A - Core",
        "paper_role": "resource lifetime invariant",
        "next_action": "Collect issue/PR or tests showing figure destroy semantics without eager gc.collect.",
    },
    "mwaskom__seaborn-2458": {
        "review_category": "A - Core",
        "paper_role": "data representation invariant",
        "next_action": "Collect changelog/test evidence for datetime converted variables.",
    },
    "mwaskom__seaborn-2313": {
        "review_category": "A - Core",
        "paper_role": "index alignment invariant",
        "next_action": "Collect exact test/docstring showing indexed colors require indexed data.",
    },
    "astropy__astropy-15228": {
        "review_category": "A - Core",
        "paper_role": "shape/API contract invariant",
        "next_action": "Decide whether compatibility-oriented cases remain in the core scope.",
    },
    "astropy__astropy-16065": {
        "review_category": "B - Needs Evidence",
        "paper_role": "output determinism drift example",
        "next_action": "Confirm why the SWE-Perf benchmark covers this output-format patch.",
    },
    "astropy__astropy-15948": {
        "review_category": "B - Needs Evidence",
        "paper_role": "masked-array representation candidate",
        "next_action": "Split broad helper protocol into one or two narrow invariant claims.",
    },
    "astropy__astropy-15710": {
        "review_category": "B - Needs Evidence",
        "paper_role": "unit-preserving NumPy wrapper candidate",
        "next_action": "Select one patched function and one API condition instead of all wrappers.",
    },
    "astropy__astropy-14413": {
        "review_category": "B - Needs Evidence",
        "paper_role": "formatting/API contract candidate",
        "next_action": "Decide whether formatting contracts are in scope for the paper.",
    },
    "astropy__astropy-12842": {
        "review_category": "B - Needs Evidence",
        "paper_role": "serialization drift example",
        "next_action": "Map added TimeInfoBase Daikon invariants back to serialization round-trip behavior.",
    },
    "matplotlib__matplotlib-24250": {
        "review_category": "B - Needs Evidence",
        "paper_role": "event ordering candidate",
        "next_action": "Collect issue/PR text or test proving callback order is semantically observable.",
    },
    "mwaskom__seaborn-2389": {
        "review_category": "B - Needs Evidence",
        "paper_role": "data representation/alignment candidate",
        "next_action": "Split color preprocessing into a narrower pandas index or missing-value invariant.",
    },
    "mwaskom__seaborn-2224": {
        "review_category": "B - Needs Evidence",
        "paper_role": "visual encoding candidate",
        "next_action": "Choose one sub-invariant such as density stacking or discrete detection.",
    },
    "astropy__astropy-13817": {
        "review_category": "C - Exclude From Core",
        "paper_role": "mixed-patch cautionary example",
        "next_action": "Do not use in main quantitative claims unless split into a smaller sub-case.",
    },
    "mwaskom__seaborn-2449": {
        "review_category": "C - Exclude From Core",
        "paper_role": "large-refactor cautionary example",
        "next_action": "Do not use in main quantitative claims unless split into smaller sub-cases.",
    },
}


def main() -> int:
    rows = []
    annotations = list(csv.DictReader((OUT_DIR / "annotations.csv").open(encoding="utf-8")))
    for ann in annotations:
        instance_id = ann["instance_id"]
        review = REVIEW[instance_id]
        rows.append(
            {
                "instance_id": instance_id,
                "repo": ann["repo"],
                "invariant_type": ann["invariant_type"],
                "confidence": ann["confidence"],
                "human_drift_available": ann["human_drift_available"],
                "human_drift": ann["human_drift"],
                **review,
            }
        )

    csv_path = OUT_DIR / "case_review.csv"
    json_path = OUT_DIR / "case_review.json"
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

