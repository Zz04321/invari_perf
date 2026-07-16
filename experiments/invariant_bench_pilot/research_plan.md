# Research Plan After Pilot-20

## Current Position

The project is no longer just a demo. It is now an empirical-study-first paper
direction:

```text
Hidden semantic invariants are a missing abstraction in AI-driven performance
optimization.
```

The current pilot establishes that SWE-Perf cases can be converted into an
invariant-centered annotation layer. The next step is to make the evidence
auditable.

## Immediate Next Step

Build an audit-ready `Core-10` subset.

For each core case, write one compact evidence block:

```text
Optimization:
What work does the patch remove, cache, reorder, or bypass?

Invariant:
What semantic condition must remain true?

Evidence:
Where is this condition supported? patch / test / docs / changelog / Daikon.

Agent relevance:
Why might a generic code agent miss this condition?

Drift status:
Did Daikon observe changed invariants under SWE-Perf execution?
```

This should be done before adding more cases.

Current Core-10 audit artifacts:

- `core10_audit.md`
- `core10_audit.csv`
- `core10_audit.json`

The missing drift cases in Core-10 are:

- `matplotlib__matplotlib-28104`
- `matplotlib__matplotlib-23712`
- `mwaskom__seaborn-2458`
- `mwaskom__seaborn-2313`

These should be attempted before running more agent experiments.

## Two-Week Plan

### Week 1: Evidence Hardening

- Finish Core-10 case narratives.
- Add source evidence for each case.
- Separate pure performance cases from compatibility/API cases.
- Re-run drift extraction for missing Core-10 cases where feasible.
- Write down failure reasons when drift extraction cannot cover a case.

Deliverable:

```text
Core-10 audit sheet with invariant, evidence, drift, and agent relevance.
```

### Week 2: Agent Connection

- Run Codex baseline on Core-10 or the covered subset.
- Run invariant-aware Codex on the same subset.
- Compare not only performance score, but also:
  - patch applies;
  - correctness tests pass;
  - performance improves;
  - invariant drift appears or disappears;
  - generated patch mentions or uses the invariant.

Deliverable:

```text
Small agent study connecting invariant evidence to optimization behavior.
```

## Paper RQs

RQ1:

```text
How often do real performance optimization patches rely on semantic invariants?
```

RQ2:

```text
Are these invariants explicit in existing development artifacts, or hidden in
code/domain assumptions?
```

RQ3:

```text
Do human and AI-generated performance patches preserve, remove, or introduce
dynamic invariant evidence?
```

RQ4:

```text
Does providing invariant evidence change an agent's optimization behavior?
```

RQ1-RQ3 are the main empirical study. RQ4 is the bridge to a future framework.

## Contribution Shape

1. Problem framing:
   AI-driven performance optimization is currently test-aware and
   benchmark-aware, but not invariant-aware.

2. Dataset layer:
   InvariantBench-Pilot, an invariant-centered annotation layer over SWE-Perf.

3. Analysis:
   A taxonomy of semantic invariants in real performance optimization patches.

4. Audit method:
   Dynamic invariant drift analysis with Daikon as a semantic evidence signal.

5. Prototype:
   A small invariant-aware agent experiment showing how invariant evidence can
   influence optimization behavior.

## Main Risk

The biggest risk is not the agent. The biggest risk is weak invariant evidence.

If the invariant labels are too broad or too subjective, the paper becomes a
prompting story. If each invariant is grounded in patch/test/docs/dynamic traces,
the paper becomes a credible program-analysis + AI-for-code empirical study.
