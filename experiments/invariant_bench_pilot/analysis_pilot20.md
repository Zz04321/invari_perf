# Pilot-20 Analysis

## What This Pilot Shows

This pilot turns the first 20 SWE-Perf instances into an invariant-centered
annotation table. It is not yet a prevalence study. It is a feasibility check
for the paper story:

```text
AI-driven performance optimization should reason about semantic invariants,
not only tests and benchmark speedups.
```

## Current Evidence

- Annotated SWE-Perf cases: 20
- Repositories: Astropy, Matplotlib, Seaborn
- Case review: 10 core, 8 need more evidence, 2 excluded from core claims
- Human-patch invariant drift reports with runtime coverage: 12/20
- Human-patch drift cases: 3/12
- Core-10 human-patch drift coverage: 6/10
- Codex-baseline drift reports with runtime coverage: 3/20
- Codex-baseline drift cases: 0/3

## Interpretation

The important result is not that all performance patches break invariants.
They do not.

The useful result is that real performance patches often have an invariant
shape that can be named and audited:

- validation vs normalization
- cache consistency
- resource lifetime
- event ordering
- representation preservation
- index alignment
- visual encoding contracts

This supports the empirical-study direction: before building a new agent, first
measure where hidden invariants appear, whether they are explicit, and whether
agent or human patches preserve them under dynamic evidence.

## Drift Examples

`astropy__astropy-16058`: the expert patch changes dynamic invariants around
unit power validation/normalization. This is the strongest current showcase
case because it connects the optimization opportunity to a semantic split:
validation can be cheaper than canonical normalization on hot paths.

`astropy__astropy-16065`: the expert patch adds output-stability behavior around
display configuration. The drift is expected and illustrates that invariant
drift is a semantic audit signal, not automatically a bug.

`astropy__astropy-12842`: the expert patch adds invariants around
`TimeInfoBase` after a serialization refactor. The drift report flags exception
and numeric-value invariant changes, which need manual interpretation against
the serialization contract.

`astropy__astropy-13496`: the expert patch memoizes physical-type ids and
removes the memoized value from pickle state. Daikon reports no invariant drift
under a large trace, making this a useful safe-cache contrast case.

## Current Limitations

- The annotation is still manually curated.
- Only 12/20 human patches have drift coverage.
- Matplotlib/Seaborn drift extraction still needs container-level debugging.
- Codex drift evidence currently covers only 3 cases.
- Drift means "dynamic invariant set changed", not "the patch is wrong".

## Next Experimental Step

First make the `A - Core` subset audit-ready. Then run the same drift
extraction on more cases, but in smaller batches:

1. Debug Matplotlib drift extraction separately.
2. Debug Seaborn drift extraction separately.
3. Add Codex-baseline drift for the same covered cases.

The current `A - Core` subset is:

- `astropy__astropy-16058`
- `astropy__astropy-15228`
- `astropy__astropy-14590`
- `astropy__astropy-13745`
- `astropy__astropy-13734`
- `astropy__astropy-13496`
- `matplotlib__matplotlib-28104`
- `matplotlib__matplotlib-23712`
- `mwaskom__seaborn-2458`
- `mwaskom__seaborn-2313`

The target for a stronger study is at least 30-50 validated cases with:

- invariant annotation;
- explicitness label;
- confidence label;
- human-patch drift result;
- agent-patch drift result when available.
