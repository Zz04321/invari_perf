# Talk Outline

## 1. Motivation

Question:

```text
If all correctness tests pass, can a performance patch still be unsafe or
unconvincing?
```

Answer:

```text
Yes. Performance optimization needs correctness evidence and cost evidence.
For semantic waste, the missing object is often an invariant or precondition.
```

## 2. Correctness Bugs vs Semantic Waste

Correctness bug:

```text
exists x. C(x) != Spec(x)
```

Semantic waste:

```text
forall x in P. C(x) == C'(x)
and Cost(C') < Cost(C)
```

The hard part is discovering and communicating `P`.

## 3. Systems-Code Patterns

Badger-style helper call:

```go
bytes.HasPrefix(ParseKey(key), prefix)
```

can become:

```go
bytes.HasPrefix(key, prefix)
```

only under a layout/precondition such as:

```text
key = userKey || ts8
len(prefix) <= len(userKey)
```

Raft/Bolt-style redundant guard:

```go
if A { return err }
if B { return err }
```

is removable only if a domain invariant makes the second guard unreachable.

## 4. Existing Benchmark: SWE-Perf

SWE-Perf evaluates repository-level performance optimization:

```text
input:  codebase + target functions
output: patch
score:  apply + correctness + performance improvement
```

This gives the right primary metric for our question.

## 5. Experimental Question

Controlled intervention:

```text
Baseline:
  Codex on official SWE-Perf oracle prompts

Treatment:
  same Codex, same tasks, same prompts
  plus invariant/precondition context

Primary evaluation:
  official SWE-Perf metrics
```

Independent variable:

```text
invariant_context: absent vs present
```

## 6. Runnable Showcase

Current runnable status:

```text
real SWE-Perf subset downloaded
3 official Astropy instances selected
official SWE-Perf oracle prompt dataset generated
```

Run preparation:

```bash
conda run -n sweperf python experiments/swe_perf_pilot/codex_baseline/run_codex_sweperf_baseline.py \
  --official-repo /tmp/swe-perf-official \
  --dataset-name-or-path data/sweperf_small.jsonl \
  --work-dir experiments/swe_perf_pilot/results/codex_baseline_small \
  --max-instances 3 \
  --prepare-only
```

Next live step:

```bash
conda run -n sweperf python experiments/swe_perf_pilot/codex_baseline/run_codex_sweperf_baseline.py \
  --official-repo /tmp/swe-perf-official \
  --dataset-name-or-path data/sweperf_small.jsonl \
  --work-dir experiments/swe_perf_pilot/results/codex_baseline_small \
  --max-instances 3 \
  --run-codex
```

## 7. Takeaways

Do not replace SWE-Perf scoring.

Use SWE-Perf as the primary benchmark, and study invariant context as a
controlled intervention.

Semantic evidence should explain improvements; official benchmark metrics
should decide success.
