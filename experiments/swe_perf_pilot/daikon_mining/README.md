# Daikon Invariant Mining Pilot

This directory contains a small adapter that tries Daikon on one real SWE-Perf
task: `astropy__astropy-16058`.

Daikon does not ship a Python/SWE-Perf front end. The adapter therefore:

1. Reconstructs the relevant optimization variables from the real SWE-Perf
   patch metadata.
2. Runs representative Python observations for the patched functions.
3. Exports Daikon `.decls` and `.dtrace` files.
4. Runs Daikon to mine likely invariants.

The goal is not to replace official SWE-Perf evaluation. The goal is to produce
machine-mined invariant context that can later be passed to Codex and evaluated
with SWE-Perf's official correctness/performance metrics.

Run:

```bash
python experiments/swe_perf_pilot/daikon_mining/mine_astropy_16058.py \
  --daikon-jar /tmp/daikon-5.8.24/daikon.jar
```

For the real trace version, run in the same environment used for official
SWE-Perf evaluation:

```bash
conda run -n sweperf python \
  experiments/swe_perf_pilot/daikon_mining/real_trace_astropy_16058.py \
  --daikon-jar /tmp/daikon-5.8.24/daikon.jar
```

This starts the official SWE-Perf Docker image for `astropy__astropy-16058`,
runs the official efficiency test, records runtime calls to the target Astropy
helpers, and mines invariants from that trace with Daikon.

Expected stable output:

```text
experiments/swe_perf_pilot/invariants/astropy__astropy-16058.real-daikon.json
```

The raw runtime trace and Daikon artifacts are written under:

```text
experiments/swe_perf_pilot/results/daikon_real_trace/astropy__astropy-16058/
```
