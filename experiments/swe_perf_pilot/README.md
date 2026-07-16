# SWE-Perf Invariant-Context Pilot

This folder is for a real SWE-Perf pilot experiment.

Research question:

```text
Does giving a performance optimization agent explicit invariant / precondition
context improve its SWE-Perf apply, correctness, and performance results?
```

The intervention is simple:

1. Run the same SWE-Perf task with a plain prompt.
2. Run it again with the same prompt plus structured invariant context.
3. Compare both runs with SWE-Perf's primary evaluation.

The semantic evidence score is diagnostic only. It helps explain agent behavior;
it is not the success metric.

## Why SWE-Perf

SWE-Perf is a repository-level performance optimization benchmark. The paper
describes 140 instances from performance-improving pull requests across popular
GitHub repositories. Each instance includes the codebase, target functions,
performance-related tests, expert patch, executable environment, and runtime
metrics.

The official task shape is:

```text
input:  codebase + target functions
output: performance optimization patch
score:  apply + correctness + performance improvement
```

This pilot keeps that scoring intact and only changes the information given to
the agent.

## Files

- `config/swe_perf_task.schema.json`: schema for one real SWE-Perf task config.
- `config/tasks.swe_perf.json`: manifest for imported real SWE-Perf tasks.
- `config/invariant_context.schema.json`: schema for invariant context.
- `config/prompt_templates.json`: plain and invariant prompts.
- `invariants/`: one invariant JSON file per real SWE-Perf task.
- `codex_baseline/`: small-scale Codex baseline reproduction under the
  official SWE-Perf oracle protocol.
- `scripts/validate_real_task.py`: checks that a task config points at a real
  SWE-Perf checkout and matching invariant file.
- `scripts/run_task_ablation.py`: prompt generation, optional Codex run, and
  diagnostic evidence scoring.

## Reproduce Codex Baseline First

Before running the invariant intervention, reproduce a small Codex baseline:

```bash
conda run -n sweperf python experiments/swe_perf_pilot/codex_baseline/run_codex_sweperf_baseline.py \
  --official-repo /tmp/swe-perf-official \
  --dataset-name-or-path data/sweperf_small.jsonl \
  --work-dir experiments/swe_perf_pilot/results/codex_baseline_small \
  --max-instances 3 \
  --prepare-only
```

Then run Codex generation and official evaluation as described in
`codex_baseline/README.md`.

## Required Real Inputs

This directory intentionally does not include a toy SWE-Perf task.

For each pilot task, create a JSON file matching
`config/swe_perf_task.schema.json` with:

- official SWE-Perf instance id;
- repository name and base commit;
- local checkout path for the original SWE-Perf codebase;
- target files and target functions;
- performance-related tests;
- correctness command;
- performance command;
- invariant context path.

The invariant file should match `config/invariant_context.schema.json`. It can
be produced by an existing tool or curated into the same format for the first
pilot.

## Run

After importing one real SWE-Perf task config:

```bash
python experiments/swe_perf_pilot/scripts/validate_real_task.py \
  --task path/to/real_swe_perf_task.json
```

Then generate the two prompts:

```bash
python experiments/swe_perf_pilot/scripts/run_task_ablation.py \
  --task path/to/real_swe_perf_task.json \
  --dry-run
```

To run the local correctness/performance commands recorded in that task config:

```bash
python experiments/swe_perf_pilot/scripts/run_task_ablation.py \
  --task path/to/real_swe_perf_task.json \
  --dry-run \
  --verify-commands
```

To run Codex as the candidate-generation agent:

```bash
python experiments/swe_perf_pilot/scripts/run_task_ablation.py \
  --task path/to/real_swe_perf_task.json \
  --run-codex
```

To score existing agent outputs for semantic evidence only:

```bash
python experiments/swe_perf_pilot/scripts/run_task_ablation.py \
  --task path/to/real_swe_perf_task.json \
  --score-existing
```

Outputs are written under:

```text
experiments/swe_perf_pilot/results/<swe_perf_instance_id>/
```

## Evaluation

Primary metrics follow SWE-Perf:

- `apply`: whether the generated patch applies;
- `correctness`: whether correctness tests pass;
- `performance`: whether runtime improves according to the SWE-Perf evaluator;
- `resolved`: task-level success under the official benchmark rule.

Diagnostic semantic evidence:

- whether the agent names the invariant or precondition;
- whether it identifies unsafe boundary cases;
- whether it explains why a rewrite preserves behavior;
- whether it uses tool-provided invariant evidence.

The paper claim should be about the primary SWE-Perf metrics. The diagnostic
evidence is for mechanism analysis.
