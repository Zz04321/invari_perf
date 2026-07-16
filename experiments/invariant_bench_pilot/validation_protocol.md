# Manual Validation Protocol

This protocol keeps the InvariantBench pilot from becoming an ad-hoc notes
table. Each row should be reviewed with the same questions before it is used as
empirical evidence.

## Goal

For each performance optimization patch, identify whether the patch depends on
a semantic invariant that is not fully captured by ordinary tests and
benchmarks.

The validated object is not "the patch is correct". The validated object is:

```text
This optimization relies on this semantic condition remaining true.
```

## Required Evidence

Each row needs at least one primary evidence source:

- patch diff
- linked issue or pull request text
- changelog or documentation
- added or modified tests
- dynamic invariant trace such as Daikon output

Rows based only on annotator intuition must stay `low` confidence.

## Review Questions

1. What work did the patch remove, cache, reorder, or bypass?
2. What behavior must remain unchanged for that optimization to be safe?
3. Is that behavior stated explicitly in docs, tests, issue text, or comments?
4. Would a generic coding agent know this condition from the local code alone?
5. Could a benchmark pass even if this condition was violated?
6. Is the invariant about safety, optimization opportunity, or both?

## Explicitness Labels

`yes`: The invariant or failure condition is directly stated in documentation,
tests, changelog, issue text, or comments.

`partially`: Evidence exists, but the invariant is implied by the patch or test
shape rather than stated as a general rule.

`no`: The invariant is inferred from code behavior, dynamic traces, or domain
reasoning.

## Confidence Labels

`high`: The invariant is narrow, patch-relevant, and supported by direct
evidence.

`medium`: The invariant is plausible and patch-relevant, but needs more issue,
test, or maintainer evidence.

`low`: The patch mixes several concerns, or the invariant is too broad to use as
strong evidence.

## Drift Check Interpretation

Invariant drift is a warning signal, not an automatic correctness verdict.

Useful drift evidence requires:

- runtime traces cover the edited or semantically relevant functions;
- before and after traces use comparable inputs;
- removed and added invariants are mapped back to patch behavior.

No drift does not prove semantic preservation. It only means the mined invariant
set did not change under the collected traces.

## Paper-Level Acceptance Rule

A case is ready for paper statistics only when:

- the invariant has a concrete source;
- the semantic role is clear;
- confidence is `medium` or `high`;
- low-level patch details and high-level invariant are linked in one sentence;
- drift evidence, if used, has coverage over the relevant functions.

