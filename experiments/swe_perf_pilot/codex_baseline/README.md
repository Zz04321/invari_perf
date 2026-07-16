# Codex Baseline on Real SWE-Perf

This directory reproduces a small-scale Codex baseline under the official
SWE-Perf oracle protocol.

Baseline definition:

```text
SWE-Perf task
+ official SWE-Perf oracle prompt construction
+ Codex CLI as the generator
+ official SWE-Perf prediction JSONL format
+ official SWE-Perf evaluation/check scripts
```

The invariant experiment should use the same pipeline and change only one
variable: append invariant/precondition context to the prompt.

## Prerequisites

- Docker is available for official SWE-Perf evaluation.
- Codex CLI is logged in.
- Python environment has the official SWE-Perf dependencies installed.
- Official SWE-Perf repo is cloned locally, or the script can clone it.

The official project is:

```text
https://github.com/SWE-Perf/SWE-Perf
```

The official dataset is:

```text
SWE-Perf/SWE-Perf
```

## One-Command Small Baseline

Run only dataset/prompt preparation first:

```bash
python experiments/swe_perf_pilot/codex_baseline/run_codex_sweperf_baseline.py \
  --official-repo /tmp/swe-perf-official \
  --dataset-name-or-path SWE-Perf/SWE-Perf \
  --work-dir experiments/swe_perf_pilot/results/codex_baseline_small \
  --max-instances 3 \
  --prepare-only
```

Run Codex generation:

```bash
python experiments/swe_perf_pilot/codex_baseline/run_codex_sweperf_baseline.py \
  --official-repo /tmp/swe-perf-official \
  --dataset-name-or-path SWE-Perf/SWE-Perf \
  --work-dir experiments/swe_perf_pilot/results/codex_baseline_small \
  --max-instances 3 \
  --run-codex
```

Run official SWE-Perf evaluation for generated patches:

```bash
python experiments/swe_perf_pilot/codex_baseline/run_codex_sweperf_baseline.py \
  --official-repo /tmp/swe-perf-official \
  --dataset-name-or-path SWE-Perf/SWE-Perf \
  --work-dir experiments/swe_perf_pilot/results/codex_baseline_small \
  --max-instances 3 \
  --evaluate
```

For a fixed subset, pass instance ids:

```bash
--instance-ids astropy__astropy-16065 sympy__sympy-25982
```

If Hugging Face is blocked on this machine, download the official dataset on a
machine with access and point the script to the local `save_to_disk` directory:

```bash
--dataset-name-or-path /path/to/local/SWE-Perf
```

The path may also be a `.json` or `.jsonl` export of official SWE-Perf rows.
Do not use synthetic rows for the baseline.

## Outputs

The work directory contains:

- `raw_subset/`: real SWE-Perf subset saved with HuggingFace `save_to_disk`.
- `base_datasets/`: official oracle prompt dataset.
- `codex_outputs/codex__oracle__test.jsonl`: raw Codex outputs.
- `predictions/codex__oracle__test_repair.jsonl`: official evaluation JSONL.
- `evaluation/`: official SWE-Perf logs and CSV output.
- `manifest.json`: exact commands and paths for reproducibility.

## Notes

The official evaluation can be expensive. SWE-Perf uses Docker and repeated
runtime measurements; even a few instances may take a long time.
