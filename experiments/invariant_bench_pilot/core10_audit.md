# Core-10 Audit Sheet

This sheet upgrades the `A - Core` cases from labels into auditable evidence
blocks. Each case answers:

- what changed;
- what semantic invariant must hold;
- what evidence supports the invariant;
- why a generic performance agent might miss it;
- whether Daikon drift evidence is currently available.

## `astropy__astropy-16058`

Repository: `astropy/astropy`

Invariant type: `validation_normalization`

Optimization:
The patch splits power handling into cheap validation and explicit
normalization. `validate_power` now checks whether a power is acceptable and can
return the original value, while `sanitize_power` performs canonical conversion
when needed. `CompositeUnit` calls `sanitize_power` only at unit construction
boundaries.

Invariant:
For many hot-path unit powers, validation is sufficient and the original value
can be returned unchanged. Canonical normalization is required only when a power
is stored as part of the unit representation.

Evidence:
The patch changes `validate_power` from "convert a power" into "check that a
power can be converted", adds `sanitize_power`, and updates tests to assert that
integer and fraction powers remain represented as integers or simple
fractions. Daikon drift is available and reports changed invariants.

Agent relevance:
A generic agent may only see local calls to `maybe_simple_fraction` or
`validate_power`. The high-value optimization requires discovering the semantic
split between validation and normalization.

Drift status:
Human patch drift available: yes. Removed: 9. Added: 16.

Use in paper:
Main showcase. This is the strongest case for "invariant as optimization
opportunity".

## `astropy__astropy-15228`

Repository: `astropy/astropy`

Invariant type: `shape_and_api_contract`

Optimization:
The patch routes `np.nanmedian` through a dedicated helper rather than the old
reduction helper set. This is a small dispatch change, but it affects the
runtime path for Quantity arrays under NumPy.

Invariant:
`Quantity` support for `np.nanmedian` must preserve NumPy's shape, axis, and
`out` semantics while retaining Quantity behavior.

Evidence:
The changelog states that `np.nanmedian` raised exceptions for some array
shapes and axis combinations with NumPy >= 1.25. The test patch parameterizes
`axis` and adds an `out` test checking object identity and result equality.
Daikon drift is available and reports no changed invariants under the selected
trace.

Agent relevance:
A performance agent may treat helper dispatch as interchangeable. The invariant
is that dispatch is only valid if the selected helper preserves the NumPy API
surface.

Drift status:
Human patch drift available: yes. Removed: 0. Added: 0.

Use in paper:
Core API-contract case. Mention carefully that this is compatibility/performance
maintenance rather than pure algorithmic speedup.

## `astropy__astropy-14590`

Repository: `astropy/astropy`

Invariant type: `ownership_lifetime`

Optimization:
The patch makes mask combination more precise and cheaper by supporting
`where`, `out`, and `copy=False`. It avoids unnecessary copying when output
storage or selected elements already determine safe reuse.

Invariant:
Mask reuse is safe only when `where`, `out`, and aliasing semantics are
preserved. Elements not selected by `where` must keep their previous output
data and mask state.

Evidence:
The patch extends `_combine_masks` with `where` and `copy` parameters, passes
`copy=False` in selected paths, and uses `np.copyto` / `np.logical_or` with
`where`. Tests construct pre-filled output arrays and verify both selected and
unselected elements. Daikon drift is available and reports no changed
invariants under the selected trace.

Agent relevance:
This is exactly where an optimizer may be tempted to remove copies. The hidden
condition is that copy elision must not leak aliases or overwrite unselected
positions.

Drift status:
Human patch drift available: yes. Removed: 0. Added: 0.

Use in paper:
Core case for ownership, lifetime, and memory-reuse invariants.

## `astropy__astropy-13745`

Repository: `astropy/astropy`

Invariant type: `numeric_precision`

Optimization:
The patch changes a latitude boundary check from a generic floating constant to
a dtype-specific limit.

Invariant:
Latitude validation must compare boundary values using the input dtype. A
float32 value equal to pi/2 in float32 representation must not be rejected
because it is compared against a slightly different float64 value.

Evidence:
The patch changes `limit = 0.5 * np.pi` to `limit =
self.dtype.type(0.5 * np.pi)`. The changelog explicitly describes the float32
pi/2 failure. Tests cover float32 and float64 boundaries and document why
upcasting would create validation side effects. Daikon drift is available and
reports no changed invariants under the selected trace.

Agent relevance:
A generic optimizer might simplify or hoist constants without noticing that the
constant's dtype is semantically observable.

Drift status:
Human patch drift available: yes. Removed: 0. Added: 0.

Use in paper:
Core numeric precision safety case.

## `astropy__astropy-13734`

Repository: `astropy/astropy`

Invariant type: `representation`

Optimization:
The patch generalizes fixed-width ASCII reading/writing to handle multiple
header rows carrying metadata such as dtype, unit, format, description, and
name.

Invariant:
Fixed-width table serialization must preserve configured header rows and
per-column metadata through read/write round trips.

Evidence:
The patch introduces `header_rows`, reads non-name header attributes into
columns, and writes configured metadata rows back out. Tests perform round-trip
checks for `fixed_width` and `fixed_width_two_line`, and reject `header_rows`
for the no-header format. Daikon drift is available and reports no changed
invariants under the selected trace.

Agent relevance:
An optimizer that assumes a single name header row may look faster and pass
narrow benchmarks while silently dropping metadata rows.

Drift status:
Human patch drift available: yes. Removed: 0. Added: 0.

Use in paper:
Core representation-preservation case.

## `astropy__astropy-13496`

Repository: `astropy/astropy`

Invariant type: `cache_consistency`

Optimization:
The patch memoizes `UnitBase._get_physical_type_id` by storing `_type_id` after
the first decomposition.

Invariant:
The cached physical-type id must depend only on stable decomposed unit bases and
powers. The cached value must not be serialized across sessions.

Evidence:
The patch adds `_type_id`, computes it lazily from `unit.decompose()`, and
removes `_type_id` in `__getstate__` together with other memoized members.
Daikon drift is available and reports no changed invariants under a large
runtime trace.

Agent relevance:
Caching is a common performance move, but safe caching requires a stable key
and clear invalidation/serialization behavior. A generic agent may add the
cache without removing it from pickle state.

Drift status:
Human patch drift available: yes. Removed: 0. Added: 0.

Use in paper:
Core caching case and strong no-drift contrast for a safe memoization patch.

## `matplotlib__matplotlib-28104`

Repository: `matplotlib/matplotlib`

Invariant type: `state_consistency`

Optimization:
The patch separates hatch color from edge color across artist state,
rcParams, rendering, and documentation.

Invariant:
Patch hatch color and edge color are independent visual state fields. If
`hatchcolor` is unspecified, fallback behavior follows `hatch.color`; the
special value `edge` links to edge color with a defined fallback.

Evidence:
The docs explicitly describe the separated state and fallback rules. Tests
check inheritance logic, explicit setter ordering, rcParam fallback, and
precedence when both edge color and hatch color are set. Drift extraction still
needs runtime debugging for this repository.

Agent relevance:
An optimizer that merges state fields or reorders setter logic can preserve
many visual tests but still violate the intended independent-state contract.

Drift status:
Human patch drift available: no.

Use in paper:
Core state-consistency/API case once runtime drift or stronger source evidence
is attached.

## `matplotlib__matplotlib-23712`

Repository: `matplotlib/matplotlib`

Invariant type: `resource_lifetime`

Optimization:
The patch removes eager `gc.collect(1)` calls from figure destruction paths.

Invariant:
Destroying a figure must already disconnect callbacks and clear managers
sufficiently. Correctness should not depend on forced generation-1 garbage
collection after every destroy.

Evidence:
The patch deletes the `gc` import and removes `gc.collect(1)` from `destroy`
and `destroy_fig`. There is no test patch in the SWE-Perf record, so this case
needs issue/PR or runtime evidence to strengthen the lifetime claim.

Agent relevance:
Removing cleanup work is a common performance optimization, but it is safe only
if resource lifetime and callback cleanup invariants still hold.

Drift status:
Human patch drift available: no.

Use in paper:
Core resource-lifetime case, but currently under-evidenced.

## `mwaskom__seaborn-2458`

Repository: `mwaskom/seaborn`

Invariant type: `data_representation`

Optimization:
The patch changes rug plot iteration to use component-transformed data.

Invariant:
Rug plots must pass datetime and converted variables to Matplotlib in plotting
compatible representation.

Evidence:
The changelog states that `rugplot` previously failed for datetime data. The
code changes `iter_data()` to `iter_data(from_comp_data=True)`. The test checks
that plotted rug coordinates equal Matplotlib date-number conversion of the
input datetime series. Drift extraction is not yet available.

Agent relevance:
A generic agent may bypass transformation layers for speed. The hidden
invariant is that representation conversion is semantically required for
non-numeric inputs.

Drift status:
Human patch drift available: no.

Use in paper:
Core data-representation case.

## `mwaskom__seaborn-2313`

Repository: `mwaskom/seaborn`

Invariant type: `index_alignment`

Optimization:
The patch adds an explicit error when indexed color annotations are supplied
with unindexed matrix data.

Invariant:
Row and column color annotations with pandas indices must be aligned to the
data index or columns. If the data is unindexed, indexed colors cannot be
safely matched and should be rejected.

Evidence:
The patch checks for mixed indexed/unindexed inputs and raises `TypeError`.
Documentation states that DataFrame/Series colors are matched to data by index.
The test creates indexed `row_colors` and `col_colors`, then verifies that
unindexed matrix input raises. Drift extraction is not yet available.

Agent relevance:
An optimizer may remove index checks or convert to NumPy arrays early, which can
silently mislabel clustered rows or columns.

Drift status:
Human patch drift available: no.

Use in paper:
Core index-alignment safety case.

## Core-10 Status

Current split:

- Strong with drift evidence: `16058`, `15228`, `14590`, `13745`, `13734`, `13496`
- Strong but missing drift evidence: `28104`, `23712`, `2458`, `2313`

Immediate next step:

```text
Run or debug human-patch drift extraction for the five missing Core-10 cases.
Then run Codex baseline on the same Core-10 subset.
```
