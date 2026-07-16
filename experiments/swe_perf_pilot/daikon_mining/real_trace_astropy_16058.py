#!/usr/bin/env python3
"""Collect real SWE-Perf execution traces and mine Daikon invariants.

This runner uses the official SWE-Perf Docker image for astropy__astropy-16058,
executes the task's official efficiency test, records runtime values from the
real Astropy checkout, and passes those observations to Daikon.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import subprocess
import sys
from pathlib import Path
from textwrap import dedent
from typing import Any


TASK_ID = "astropy__astropy-16058"
ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET = ROOT / "data" / "sweperf_small.jsonl"
OUT_DIR = ROOT / "experiments" / "swe_perf_pilot" / "results" / "daikon_real_trace" / TASK_ID
STABLE_CONTEXT = ROOT / "experiments" / "swe_perf_pilot" / "invariants" / f"{TASK_ID}.real-daikon.json"
OFFICIAL_REPO = Path("/tmp/swe-perf-official")


SITE_CUSTOMIZE = r'''
import functools
import importlib.abc
import importlib.machinery
import json
import os
import sys
import threading
from fractions import Fraction

TRACE_FILE = os.environ.get("DAIKON_TRACE_JSONL", "/tmp/daikon_trace/runtime_trace.jsonl")
_LOCK = threading.Lock()
_PATCHED = False


def _num(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _float(value):
    try:
        return float(value)
    except Exception:
        return 0.0


def _features(p, result=None, exc=None):
    denominator = getattr(p, "denominator", 0)
    numerator = getattr(p, "numerator", 0)
    values = {
        "is_int": int(p.__class__ is int),
        "is_fraction": int(p.__class__ is Fraction),
        "is_float": int(p.__class__ is float),
        "is_zero": int(p == 0),
        "denominator": _num(denominator),
        "numerator": _num(numerator),
        "float_value": _float(p),
        "raised": int(exc is not None),
        "result_is_same_object": 0,
        "result_is_int": 0,
        "result_is_fraction": 0,
        "result_is_float": 0,
        "result_float_value": 0.0,
    }
    if exc is None:
        values.update(
            {
                "result_is_same_object": int(result is p),
                "result_is_int": int(result.__class__ is int),
                "result_is_fraction": int(result.__class__ is Fraction),
                "result_is_float": int(result.__class__ is float),
                "result_float_value": _float(result),
            }
        )
    return values


def _branch(function_name, p, result=None, exc=None):
    if exc is not None:
        return "exception"
    if function_name == "validate_power":
        if p.__class__ is int or p.__class__ is Fraction:
            return "fast_exact_type"
        return "float_convertible"
    if function_name == "maybe_simple_fraction":
        if p == 0 or p.__class__ is int or p.__class__ is Fraction:
            return "fast_identity"
        if result.__class__ is Fraction:
            return "fraction_result"
        return "float_result"
    return "observed"


def _record(function_name, p, result=None, exc=None):
    try:
        row = {
            "function": function_name,
            "program_point": "astropy.units.utils.%s.%s:::POINT" % (function_name, _branch(function_name, p, result, exc)),
            "values": _features(p, result, exc),
            "input_type": type(p).__name__,
            "result_type": None if exc is not None else type(result).__name__,
        }
        os.makedirs(os.path.dirname(TRACE_FILE), exist_ok=True)
        with _LOCK:
            with open(TRACE_FILE, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
    except Exception:
        pass


def _wrap(module, function_name):
    original = getattr(module, function_name, None)
    if original is None or getattr(original, "_daikon_wrapped", False):
        return

    @functools.wraps(original)
    def wrapper(p, *args, **kwargs):
        try:
            result = original(p, *args, **kwargs)
        except Exception as exc:
            _record(function_name, p, exc=exc)
            raise
        _record(function_name, p, result=result)
        return result

    wrapper._daikon_wrapped = True
    setattr(module, function_name, wrapper)


def _patch(module):
    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True
    _wrap(module, "validate_power")
    _wrap(module, "maybe_simple_fraction")


class _Loader(importlib.abc.Loader):
    def __init__(self, wrapped):
        self.wrapped = wrapped

    def create_module(self, spec):
        if hasattr(self.wrapped, "create_module"):
            return self.wrapped.create_module(spec)
        return None

    def exec_module(self, module):
        self.wrapped.exec_module(module)
        _patch(module)


class _Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname != "astropy.units.utils":
            return None
        for finder in sys.meta_path:
            if finder is self:
                continue
            if finder is importlib.machinery.PathFinder:
                spec = finder.find_spec(fullname, path, target)
            else:
                find_spec = getattr(finder, "find_spec", None)
                if find_spec is None:
                    continue
                spec = find_spec(fullname, path, target)
            if spec is not None and spec.loader is not None:
                spec.loader = _Loader(spec.loader)
                return spec
        return None


if "astropy.units.utils" in sys.modules:
    _patch(sys.modules["astropy.units.utils"])
else:
    sys.meta_path.insert(0, _Finder())
'''


def load_instance(dataset_path: Path) -> dict[str, Any]:
    for line in dataset_path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["instance_id"] == TASK_ID:
            return row
    raise ValueError(f"{TASK_ID} not found in {dataset_path}")


def load_official_modules() -> None:
    sys.path.insert(0, str(OFFICIAL_REPO / "evaluation"))
    needed = OFFICIAL_REPO / "evaluation" / "test_spec.py"
    if not needed.exists():
        raise FileNotFoundError(f"official SWE-Perf repo not found at {OFFICIAL_REPO}")
    if importlib.util.find_spec("docker") is None:
        raise RuntimeError("Python docker package is not available in this environment")


def setup_logger(log_path: Path) -> logging.Logger:
    logger = logging.getLogger("real-daikon-trace")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    logger.addHandler(stream)
    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


def docker_image_key(instance_id: str) -> str:
    image_name = "sweb.eval.x86_64." + instance_id
    image_name = image_name.replace("__", "_s_")
    return ("docker.io/betty1202/" + image_name).lower()


def run_real_trace(dataset_path: Path, timeout: int) -> Path:
    load_official_modules()
    import docker
    from docker_build import build_container
    from docker_utils import cleanup_container, copy_from_container, copy_to_container, exec_run_with_timeout
    from test_spec import make_test_spec

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    logger = setup_logger(OUT_DIR / "real_trace_run.log")
    instance = load_instance(dataset_path)
    test_spec = make_test_spec(instance, is_eval=True)
    test_spec.instance_image_key = docker_image_key(test_spec.instance_id)

    client = docker.from_env()
    container = None
    run_id = "daikon-real-trace"
    try:
        container = build_container(
            test_spec,
            client,
            run_id,
            logger,
            nocache=False,
            force_rebuild=False,
            is_large=True,
            from_remote=True,
        )
        container.start()
        logger.info("Container started: %s", container.id)

        probe_dir = OUT_DIR / "probe"
        probe_dir.mkdir(parents=True, exist_ok=True)
        sitecustomize = probe_dir / "sitecustomize.py"
        sitecustomize.write_text(SITE_CUSTOMIZE, encoding="utf-8")
        copy_to_container(container, sitecustomize, Path("/tmp/trace_probe/sitecustomize.py"))

        eval_file = OUT_DIR / "eval_with_trace.sh"
        eval_file.write_text(
            dedent(
                f"""\
                export PYTHONPATH=/tmp/trace_probe:${{PYTHONPATH:-}}
                export DAIKON_TRACE_JSONL=/tmp/daikon_trace/runtime_trace.jsonl
                mkdir -p /tmp/daikon_trace
                rm -f /tmp/daikon_trace/runtime_trace.jsonl
                {test_spec.eval_script}
                """
            ),
            encoding="utf-8",
        )
        copy_to_container(container, eval_file, Path("/eval_with_trace.sh"))
        output_path = OUT_DIR / "pytest_output.txt"
        _, timed_out, runtime = exec_run_with_timeout(
            container,
            "/bin/bash /eval_with_trace.sh",
            timeout,
            str(output_path),
        )
        logger.info("Trace pytest runtime: %.2f seconds", runtime)
        if timed_out:
            raise TimeoutError(f"trace run timed out after {timeout} seconds")

        trace_path = OUT_DIR / "runtime_trace.jsonl"
        copy_from_container(container, "/tmp/daikon_trace/runtime_trace.jsonl", trace_path)
        return trace_path
    finally:
        if container is not None:
            cleanup_container(client, container, logger)


def read_trace(path: Path) -> list[dict[str, Any]]:
    rows = []
    seen = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        key = json.dumps(row, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    if not rows:
        raise RuntimeError(f"no trace rows in {path}")
    return rows


def write_decls(path: Path, ppts: list[str], variables: list[str]) -> None:
    lines = ["decl-version 2.0", "input-language Python", "var-comparability none", ""]
    for ppt in sorted(set(ppts)):
        lines.extend([f"ppt {ppt}", "ppt-type point"])
        for name in variables:
            rep_type = "double" if "float_value" in name else "int"
            lines.extend(
                [
                    f"variable {name}",
                    "  var-kind variable",
                    f"  dec-type {rep_type}",
                    f"  rep-type {rep_type}",
                    "  comparability -1",
                ]
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_dtrace(path: Path, rows: list[dict[str, Any]], variables: list[str]) -> None:
    lines = []
    for row in rows:
        lines.extend(["", row["program_point"]])
        values = row["values"]
        for name in variables:
            lines.extend([name, repr(values[name]) if isinstance(values[name], float) else str(values[name]), "1"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_invariants(daikon_output: str) -> dict[str, list[str]]:
    by_ppt: dict[str, list[str]] = {}
    current = None
    for raw in daikon_output.splitlines():
        line = raw.strip()
        if not line or line.startswith("="):
            continue
        if line.endswith(":::POINT"):
            current = line
            by_ppt[current] = []
            continue
        if current is None:
            continue
        if line.startswith(("Daikon version", "Reading ", "(read ", "Processing ", "Exiting ")):
            continue
        by_ppt[current].append(line)
    return by_ppt


def mine_daikon(trace_path: Path, daikon_jar: Path) -> Path:
    rows = read_trace(trace_path)
    variables = list(rows[0]["values"].keys())
    decls = OUT_DIR / "real_trace.decls"
    dtrace = OUT_DIR / "real_trace.dtrace"
    daikon_output = OUT_DIR / "daikon_output.txt"
    context = OUT_DIR / "invariant_context.json"

    write_decls(decls, [row["program_point"] for row in rows], variables)
    write_dtrace(dtrace, rows, variables)

    proc = subprocess.run(
        ["java", "-cp", str(daikon_jar), "daikon.Daikon", str(decls), str(dtrace)],
        check=True,
        text=True,
        capture_output=True,
    )
    daikon_output.write_text(proc.stdout, encoding="utf-8")
    by_ppt = parse_invariants(proc.stdout)
    summary = {
        "task_id": TASK_ID,
        "trace_source": "official SWE-Perf Docker image, base commit, official efficiency test execution",
        "runtime_trace_rows": sum(1 for _ in trace_path.read_text(encoding="utf-8").splitlines() if _.strip()),
        "deduplicated_trace_rows": len(rows),
        "efficiency_test": load_instance(DEFAULT_DATASET)["efficiency_test"],
        "artifacts": {
            "runtime_trace": str(trace_path.relative_to(ROOT)),
            "decls": str(decls.relative_to(ROOT)),
            "dtrace": str(dtrace.relative_to(ROOT)),
            "daikon_output": str(daikon_output.relative_to(ROOT)),
        },
        "likely_invariants_by_program_point": by_ppt,
        "agent_context_candidates": [
            {"program_point": ppt, "likely_invariant": inv}
            for ppt, invs in by_ppt.items()
            for inv in invs
            if any(token in inv for token in ("result_is_same_object", "float_value == result_float_value", "is_int == 1", "is_fraction", "result_is"))
        ],
    }
    context.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    STABLE_CONTEXT.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return context


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--daikon-jar", type=Path, default=Path("/tmp/daikon-5.8.24/daikon.jar"))
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--skip-trace", action="store_true", help="reuse existing runtime_trace.jsonl")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    trace_path = OUT_DIR / "runtime_trace.jsonl"
    if not args.skip_trace:
        trace_path = run_real_trace(args.dataset, args.timeout)
    elif not trace_path.exists():
        raise FileNotFoundError(trace_path)
    context = mine_daikon(trace_path, args.daikon_jar)
    summary = json.loads(context.read_text(encoding="utf-8"))
    print(f"task: {TASK_ID}")
    print(f"runtime_trace_rows: {summary['runtime_trace_rows']}")
    print(f"deduplicated_trace_rows: {summary['deduplicated_trace_rows']}")
    print(f"context: {context}")
    print(f"stable_context: {STABLE_CONTEXT}")
    print("program points:")
    for ppt, invs in summary["likely_invariants_by_program_point"].items():
        print(f"- {ppt}: {len(invs)} invariants")


if __name__ == "__main__":
    main()
