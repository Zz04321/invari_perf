---
name: daikon-invariant-mining
description: Mine and use Daikon dynamic invariants as semantic evidence for performance optimization tasks. Use when Codex is asked to optimize code, fix semantic waste, compare cheaper rewrites, find safety preconditions, or improve SWE-Perf-style repository performance and needs runtime invariants, preconditions, or coverage evidence before editing.
---

# Daikon Invariant Mining

Use this skill to treat Daikon as an agent-callable semantic-profiler tool.
The goal is not to prove correctness. The goal is to mine likely runtime
preconditions, connect them to hot-path evidence, and turn them into
performance-relevant rewrite opportunities.

## Workflow

1. Identify the candidate optimization target.
   Prefer target functions, direct helpers, or expensive conversion/allocation
   sites near the proposed edit.

2. Check for existing mined context before running anything expensive. For a
   human-readable report:

   ```bash
   python codex-skills/daikon-invariant-mining/scripts/invariant_tool.py \
     --context experiments/swe_perf_pilot/invariants/<task-id>.real-daikon.json \
     --target <module.or.function>
   ```

   For agent optimization prompts, prefer structured performance guidance:

   ```bash
   python codex-skills/daikon-invariant-mining/scripts/invariant_tool.py \
     --context experiments/swe_perf_pilot/invariants/<task-id>.real-daikon.json \
     --target <module.or.function> \
     --performance-json
   ```

3. If no context exists and the current repository is the SWE-Perf showcase
   project, mine a real execution trace:

   ```bash
   python codex-skills/daikon-invariant-mining/scripts/mine_sweperf_task.py \
     --task <task-id> \
     --target-source patch-functions
   ```

   Use `--target-source patch-modules` only when patch functions have zero
   coverage and you still need evidence from nearby code in the same file.

4. Interpret the report as evidence, not proof.
   Use invariants to propose preconditions and rewrite opportunities such as:
   - input type is stable
   - return value is the same object
   - numeric value is preserved
   - a branch condition is consistently false/true
   - shape/length/size is stable
   - a guarded fast path may be safe
   - validation and normalization may be separable
   - redundant conversion or allocation may be avoidable

5. Edit code only after the evidence is relevant to both safety and cost.
   Do not use global or unrelated invariants as justification for a local
   rewrite. A local invariant can justify safety while still failing to improve
   benchmark time if the guarded path is not the dominant cost.

6. Validate with the repository's correctness and performance tests.
   For SWE-Perf tasks, use official evaluation when available.

## Output Policy

When reporting mined evidence to the user or using it in an agent prompt,
prefer the `--performance-json` schema:

```text
schema_version: daikon-performance-guidance-v1
hot_path: coverage and cost-proxy metadata
evidence: classified invariants
rewrite_opportunities: safe rewrite shapes to consider
agent_instructions: how to use the evidence
warnings: dynamic-observation caveats
```

For a short human-readable report, summarize it as:

```text
Target: <function>
Coverage: <runtime rows>, <unique observed shapes>
Useful invariants:
- ...
Optimization implications:
- ...
Warnings:
- ...
```

Always mention when coverage is zero. A zero-coverage report means "no
evidence", not "no invariant exists".

## Resources

- `scripts/invariant_tool.py`: turn a mined `*.real-daikon.json` file into an
  agent-readable semantic evidence or performance guidance report.
- `scripts/mine_sweperf_task.py`: wrapper for this project's SWE-Perf real
  trace miner.
- `references/interpretation.md`: guidance for deciding whether a mined
  invariant is optimization-relevant.
