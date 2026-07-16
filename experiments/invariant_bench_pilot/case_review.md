# Case Review for Pilot-20

This file reviews whether each annotated SWE-Perf case is strong enough for an
invariant-centered empirical study.

The review goal is not to decide whether the expert patch is correct. The goal
is to decide whether a case is useful evidence for the paper claim:

```text
Performance optimization relies on semantic invariants that tests and
benchmarks do not fully explain.
```

## Review Categories

`A - Core`: use in the main empirical study. The invariant is concrete,
patch-relevant, and has direct evidence.

`B - Needs Evidence`: keep in the pilot, but collect issue/PR text, tests, or
stronger dynamic evidence before using in main statistics.

`C - Exclude From Core`: useful as a cautionary example, but too mixed or broad
for main quantitative claims.

## Summary

- `A - Core`: 10 cases
- `B - Needs Evidence`: 8 cases
- `C - Exclude From Core`: 2 cases

The current pilot is good enough for a showcase and for motivating the study.
It is not yet strong enough for paper-level prevalence numbers.

## A - Core Cases

### `astropy__astropy-16058`

- Invariant type: `validation_normalization`
- Why it matters: the optimization separates cheap validation from more
  expensive canonical normalization.
- Evidence: patch, changelog, Daikon trace, human-patch drift.
- Paper use: main showcase case.
- Review: strong. This is the best current example because the invariant is both
  a safety condition and an optimization opportunity.

### `astropy__astropy-14590`

- Invariant type: `ownership_lifetime`
- Why it matters: mask reuse and copy elision are safe only when `where`, `out`,
  and aliasing behavior are preserved.
- Evidence: patch and targeted functions.
- Paper use: core case for memory/ownership invariants.
- Review: strong, but still needs one paragraph of issue/test evidence before
  final paper use.

### `astropy__astropy-13745`

- Invariant type: `numeric_precision`
- Why it matters: replacing boundary checks or constants can change dtype-aware
  behavior even when tests and benchmarks are narrow.
- Evidence: patch and changelog.
- Paper use: core safety invariant case.
- Review: strong and narrow, though less performance-opportunity oriented than
  `16058`.

### `astropy__astropy-13734`

- Invariant type: `representation`
- Why it matters: table I/O optimizations must preserve multi-row header and
  per-column metadata representation.
- Evidence: patch and docs.
- Paper use: core representation-preservation case.
- Review: strong as an invariant case, but not the cleanest agent optimization
  example.

### `astropy__astropy-13496`

- Invariant type: `cache_consistency`
- Why it matters: caching physical-type ids is profitable only if the cached id
  is derived from stable unit structure and is not serialized across sessions.
- Evidence: patch edits `_get_physical_type_id` and `__getstate__`.
- Paper use: core optimization case.
- Review: strong. This is one of the best examples for "invariant as a safety
  precondition for caching".

### `matplotlib__matplotlib-28104`

- Invariant type: `state_consistency`
- Why it matters: hatch color and edge color are independent visual state fields
  with documented fallback behavior.
- Evidence: patch, docs, gallery example.
- Paper use: core API/state invariant case.
- Review: strong, but drift extraction still needs runtime/debug work.

### `matplotlib__matplotlib-23712`

- Invariant type: `resource_lifetime`
- Why it matters: deleting eager `gc.collect` is only safe if figure destruction
  already disconnects callbacks and clears managers sufficiently.
- Evidence: small patch in figure manager cleanup.
- Paper use: core resource-lifetime optimization case.
- Review: strong conceptually. Needs issue/PR text or tests to confirm the
  lifetime contract.

### `mwaskom__seaborn-2458`

- Invariant type: `data_representation`
- Why it matters: rug plots must use component-transformed data so datetime and
  converted variables reach Matplotlib in a compatible representation.
- Evidence: one-line patch and changelog.
- Paper use: core representation invariant case.
- Review: strong and narrow.

### `mwaskom__seaborn-2313`

- Invariant type: `index_alignment`
- Why it matters: indexed row/column colors must align with data
  index/columns; otherwise clustered rows or columns can be mislabeled.
- Evidence: patch and docstring.
- Paper use: core alignment invariant case.
- Review: strong and narrow.

### `astropy__astropy-15228`

- Invariant type: `shape_and_api_contract`
- Why it matters: helper dispatch must preserve NumPy `nanmedian` shape/axis
  semantics.
- Evidence: patch and changelog.
- Paper use: core API-contract case if we keep compatibility fixes in scope.
- Review: strong, but classify carefully because it is more compatibility/API
  behavior than classic performance optimization.

## B - Needs Evidence

### `astropy__astropy-16065`

- Current invariant: diff output should be independent of Astropy display
  configuration.
- Current evidence: patch, changelog, human-patch drift.
- Why not core yet: the invariant is real, but the case is closer to output
  determinism than performance optimization.
- Needed next: confirm why this appears in SWE-Perf and whether the efficiency
  test exercises the patched behavior.

### `astropy__astropy-15948`

- Current invariant: masked-array helpers preserve data/mask/out protocol.
- Current evidence: patch, no human drift.
- Why not core yet: the patch touches many helpers, so the invariant is broad.
- Needed next: split into one or two specific helper-level invariants.

### `astropy__astropy-15710`

- Current invariant: NumPy wrappers preserve unit semantics and function
  signatures.
- Current evidence: patch and changed API surface.
- Why not core yet: many functions are edited, so a single invariant is too
  broad.
- Needed next: choose one function, one API condition, and one test/benchmark.

### `astropy__astropy-14413`

- Current invariant: unit formatter output contracts preserve spacing,
  superscript, and scale formatting.
- Current evidence: patch and docs.
- Why not core yet: useful invariant, but mostly user-visible formatting rather
  than performance optimization.
- Needed next: decide whether formatting/API compatibility belongs in this
  paper's scope.

### `astropy__astropy-12842`

- Current invariant: Time and TimeDelta serialization must preserve round-trip
  metadata.
- Current evidence: patch, changelog, human-patch drift with 14 added
  invariants.
- Why not core yet: drift is real but needs interpretation; added invariants may
  reflect new helper factoring rather than semantic risk.
- Needed next: map the 14 added Daikon invariants back to serialization tests.

### `matplotlib__matplotlib-24250`

- Current invariant: callback connection order preserves pick/event behavior.
- Current evidence: patch only.
- Why not core yet: this is plausible but under-evidenced.
- Needed next: collect issue/PR discussion or tests proving event ordering is
  observable.

### `mwaskom__seaborn-2389`

- Current invariant: color preprocessing preserves values, labels, missing
  values, and pandas alignment.
- Current evidence: patch.
- Why not core yet: combines conversion, missing handling, and alignment.
- Needed next: split into a narrower pandas-index or missing-value invariant.

### `mwaskom__seaborn-2224`

- Current invariant: distribution plot color gradients, discrete detection, and
  multiple-density handling preserve visual encoding.
- Current evidence: patch and examples.
- Why not core yet: the invariant is broad and combines several visual
  semantics.
- Needed next: choose one sub-invariant, preferably `_resolve_multiple` or
  `_default_discrete`.

## C - Exclude From Core

### `astropy__astropy-13817`

- Reason: patch mixes pre-commit config, import cleanup, numerical helper
  maintenance, WCS, modeling, and docs.
- Keep for: cautionary example that some SWE-Perf tasks are too mixed for clean
  invariant annotation.
- Do not use for: prevalence statistics or agent evaluation.

### `mwaskom__seaborn-2449`

- Reason: large style/color refactor across categorical, distribution,
  relational, and utility code.
- Keep for: taxonomy exploration.
- Do not use for: main quantitative claims until split into smaller
  sub-cases.

## Immediate Research Implication

The next paper-quality step is not to add more labels blindly. It is to create
a `Core-10` subset from the `A - Core` cases and make each case audit-ready:

- one invariant sentence;
- one patch-level evidence sentence;
- one test/benchmark evidence sentence;
- optional Daikon drift result;
- one reason a generic agent might miss the invariant.

After `Core-10` is audit-ready, run Codex baseline and invariant-aware Codex on
that same subset. This connects the empirical study to the agent question
without making the agent experiment the whole paper.

