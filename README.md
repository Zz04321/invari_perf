# SWE-Perf Codex Baseline Pilot

This repository is a small reproduction harness for running Codex on real
SWE-Perf tasks.

Goal:

```text
Reproduce a small Codex baseline under the official SWE-Perf oracle protocol,
then use the same setup to test whether invariant/precondition context improves
agent performance.
```

## Current Status

Real SWE-Perf data has been downloaded through `hf-mirror`:

```text
data/sweperf_test.parquet
data/sweperf_small.jsonl
```

The small subset contains three official SWE-Perf instances:

```text
astropy__astropy-16065
astropy__astropy-16058
astropy__astropy-15948
```

The official oracle prompt dataset has been generated under:

```text
experiments/swe_perf_pilot/results/codex_baseline_small/base_datasets/raw_subset__efficiency__fs-oracle
```

## Baseline Definition

The baseline is:

```text
official SWE-Perf task
+ official SWE-Perf oracle prompt construction
+ Codex CLI patch generation
+ official SWE-Perf prediction JSONL format
+ official SWE-Perf evaluation scripts
```

The treatment condition should keep everything fixed and only add structured
invariant/precondition context.

## Run

Prepare the real SWE-Perf subset and oracle prompts:

```bash
conda run -n sweperf python experiments/swe_perf_pilot/codex_baseline/run_codex_sweperf_baseline.py \
  --official-repo /tmp/swe-perf-official \
  --dataset-name-or-path data/sweperf_small.jsonl \
  --work-dir experiments/swe_perf_pilot/results/codex_baseline_small \
  --max-instances 3 \
  --prepare-only
```

Run Codex baseline generation:

```bash
conda run -n sweperf python experiments/swe_perf_pilot/codex_baseline/run_codex_sweperf_baseline.py \
  --official-repo /tmp/swe-perf-official \
  --dataset-name-or-path data/sweperf_small.jsonl \
  --work-dir experiments/swe_perf_pilot/results/codex_baseline_small \
  --max-instances 3 \
  --run-codex
```

Run official SWE-Perf evaluation after predictions are generated:

```bash
conda run -n sweperf python experiments/swe_perf_pilot/codex_baseline/run_codex_sweperf_baseline.py \
  --official-repo /tmp/swe-perf-official \
  --dataset-name-or-path data/sweperf_small.jsonl \
  --work-dir experiments/swe_perf_pilot/results/codex_baseline_small \
  --max-instances 3 \
  --evaluate
```

## Layout

- `data/`: real SWE-Perf subset data.
- `experiments/swe_perf_pilot/codex_baseline/`: Codex baseline reproduction.
- `experiments/swe_perf_pilot/config/`: schemas and prompt templates for later
  invariant-context ablation.
- `experiments/swe_perf_pilot/scripts/`: task validation and ablation utilities.
