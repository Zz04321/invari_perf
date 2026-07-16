# InvariantBench Pilot

This is a small invariant-focused annotation layer over a 20-case SWE-Perf pilot slice.

## Scope

- Cases: `20`
- Dataset: `data/sweperf_20.jsonl`
- Repository coverage: Astropy, Matplotlib, and Seaborn.

## Taxonomy Counts

- `api_contract`: `3`
- `cache_consistency`: `1`
- `data_representation`: `2`
- `event_ordering`: `1`
- `index_alignment`: `1`
- `mixed_api_numeric`: `1`
- `numeric_precision`: `1`
- `ownership_lifetime`: `1`
- `representation`: `2`
- `resource_lifetime`: `1`
- `serialization_contract`: `1`
- `shape_and_api_contract`: `1`
- `state_consistency`: `1`
- `style_state_consistency`: `1`
- `validation_normalization`: `1`
- `visual_encoding`: `1`

## Explicitness

- `no`: `3`
- `partially`: `11`
- `yes`: `6`

## Confidence

- `high`: `10`
- `low`: `1`
- `medium`: `9`

## Existing Drift Evidence

- Human patch drift reports available: `12/20`
- Human patch drift cases: `3/12`
- Codex baseline drift reports available: `3/20`
- Codex baseline drift cases: `0/3`

## Preliminary Takeaway

The pilot supports the empirical-study direction, but it is not yet a claim about prevalence.
It shows that SWE-Perf patches can be annotated in terms of hidden semantic invariants,
and that invariant drift can be measured for both human and agent patches when runtime traces cover the edited code.

The next step is to add stricter manual validation for whether each invariant is truly hidden, explicit, or only inferred by the annotator, then run drift extraction on the remaining cases.

## Files

- `annotations.csv`: spreadsheet-friendly annotation table.
- `annotations.json`: machine-readable annotation table.
