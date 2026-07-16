# InvariantBench Pilot

This directory is the first annotation layer for studying hidden semantic
invariants in performance optimization patches.

The goal is not to claim prevalence yet. The goal is to test whether SWE-Perf
cases can be consistently annotated with:

- what optimization was made;
- what semantic invariant the optimization relies on;
- whether the invariant is explicit or hidden;
- whether human and agent patches preserve the mined invariant set.

## Files

- `build_pilot.py`: reproducibly builds the pilot table from `data/sweperf_20.jsonl` plus existing drift reports.
- `annotations.csv`: spreadsheet-friendly annotation table.
- `annotations.json`: machine-readable annotation table.
- `summary.md`: aggregate counts for the current pilot.
- `validation_protocol.md`: manual review rules for deciding whether an
  invariant row is strong enough for empirical-study evidence.
- `case_review.md`: first-author review of which cases are ready for main
  study, need more evidence, or should be excluded from core claims.
- `case_review.csv` / `case_review.json`: machine-readable version of the case
  review labels.
- `research_plan.md`: next-step plan for turning the pilot into a paper-quality
  empirical study.
- `core10_audit.md`: audit-ready evidence sheet for the current core subset.
- `core10_audit.csv` / `core10_audit.json`: machine-readable Core-10 audit
  table for later scripts and website display.

## Annotation Rules

`optimization_type` names the high-level performance or compatibility change,
not the exact code edit.

`invariant_type` should use a small taxonomy. Current pilot labels:

- `api_contract`
- `cache_consistency`
- `data_representation`
- `event_ordering`
- `index_alignment`
- `mixed_api_numeric`
- `numeric_precision`
- `ownership_lifetime`
- `representation`
- `resource_lifetime`
- `serialization_contract`
- `shape_and_api_contract`
- `state_consistency`
- `style_state_consistency`
- `validation_normalization`
- `visual_encoding`

`hidden_invariant` should be written as a semantic condition that must remain
true for the patch to be safe.

`invariant_source` records where the annotator found evidence:

- `patch`
- `patch + changelog`
- `patch + docs`
- `patch + Daikon trace`

`is_invariant_explicit` means:

- `yes`: the invariant or bug condition is clearly stated in changelog/docs/tests.
- `partially`: the patch implies it, but it is not stated as a general rule.
- `no`: the invariant is inferred from code behavior or dynamic evidence.

`semantic_role` means:

- `safety`: needed to avoid changing behavior.
- `opportunity`: suggests a possible optimization.
- `safety_and_opportunity`: does both.

`confidence` is the annotator's confidence that the row captures a real
semantic invariant rather than an incidental implementation detail.

## Current Pilot Interpretation

The current 20-case pilot includes Astropy, Matplotlib, and Seaborn. This is
useful for pipeline validation and early taxonomy design, but not enough for a
paper-level prevalence claim.

The current table supports the next research step:

```text
Build an invariant-focused annotation layer over real performance optimization
benchmarks, then ask whether AI agents fail to preserve or exploit those
invariants.
```
