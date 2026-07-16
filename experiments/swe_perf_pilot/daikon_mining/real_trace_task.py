#!/usr/bin/env python3
"""Generic real-trace Daikon miner for SWE-Perf Python tasks."""

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


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET = ROOT / "data" / "sweperf_small.jsonl"
OFFICIAL_REPO = Path("/tmp/swe-perf-official")


SITE_CUSTOMIZE = r'''
import functools
import importlib.abc
import importlib.machinery
import json
import os
import sys
import threading
import atexit

TRACE_FILE = os.environ.get("DAIKON_TRACE_JSONL", "/tmp/daikon_trace/runtime_trace.jsonl")
TARGETS = json.loads(os.environ.get("DAIKON_TRACE_TARGETS", "{}"))
TRACE_ALL_MODULE_FUNCTIONS = os.environ.get("DAIKON_TRACE_ALL_MODULE_FUNCTIONS", "0") == "1"
_LOCK = threading.Lock()
_PATCHED_MODULES = set()
_PROFILE_TARGETS = {}


def _safe_len(value):
    try:
        return len(value)
    except Exception:
        return -1


def _safe_float(value):
    try:
        return float(value)
    except Exception:
        return 0.0


def _truth(value):
    try:
        return int(bool(value))
    except Exception:
        return -1


def _shape_len(value):
    shape = getattr(value, "shape", None)
    try:
        return len(shape)
    except Exception:
        return -1


def _size(value):
    size = getattr(value, "size", None)
    if size is None:
        return _safe_len(value)
    try:
        return int(size)
    except Exception:
        return -1


def _features(args, kwargs, result=None, exc=None):
    first = args[0] if args else None
    second = args[1] if len(args) > 1 else None
    values = {
        "arg_count": len(args),
        "kwarg_count": len(kwargs),
        "raised": int(exc is not None),
        "arg0_is_none": int(first is None),
        "arg1_is_none": int(second is None),
        "arg0_is_int": int(first.__class__ is int),
        "arg0_is_float": int(first.__class__ is float),
        "arg0_is_bool": int(first.__class__ is bool),
        "arg0_len": _safe_len(first),
        "arg1_len": _safe_len(second),
        "arg0_ndim": int(getattr(first, "ndim", -1) if getattr(first, "ndim", -1) is not None else -1),
        "arg1_ndim": int(getattr(second, "ndim", -1) if getattr(second, "ndim", -1) is not None else -1),
        "arg0_shape_len": _shape_len(first),
        "arg1_shape_len": _shape_len(second),
        "arg0_size": _size(first),
        "arg1_size": _size(second),
        "arg0_truth": _truth(first),
        "arg1_truth": _truth(second),
        "arg0_float": _safe_float(first),
        "arg1_float": _safe_float(second),
        "result_is_none": int(result is None) if exc is None else 0,
        "result_is_same_as_arg0": int(result is first) if exc is None else 0,
        "result_len": _safe_len(result) if exc is None else -1,
        "result_ndim": int(getattr(result, "ndim", -1) if exc is None and getattr(result, "ndim", -1) is not None else -1),
        "result_size": _size(result) if exc is None else -1,
    }
    return values


def _record(target_name, args, kwargs, result=None, exc=None):
    try:
        row = {
            "target": target_name,
            "program_point": "%s.%s:::POINT" % (target_name, "exception" if exc is not None else "return"),
            "values": _features(args, kwargs, result, exc),
            "arg_types": [type(arg).__name__ for arg in args[:4]],
            "result_type": None if exc is not None else type(result).__name__,
        }
        os.makedirs(os.path.dirname(TRACE_FILE), exist_ok=True)
        with _LOCK:
            with open(TRACE_FILE, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
    except Exception:
        pass


def _resolve_owner(module, dotted_name):
    parts = dotted_name.split(".")
    owner = module
    for part in parts[:-1]:
        owner = getattr(owner, part, None)
        if owner is None:
            return None, None
    return owner, parts[-1]


def _wrap(module, module_name, dotted_name):
    owner, attr = _resolve_owner(module, dotted_name)
    if owner is None or attr is None:
        return
    original = getattr(owner, attr, None)
    if original is None or getattr(original, "_daikon_wrapped", False):
        return
    target_name = "%s.%s" % (module_name, dotted_name)

    @functools.wraps(original)
    def wrapper(*args, **kwargs):
        try:
            result = original(*args, **kwargs)
        except Exception as exc:
            _record(target_name, args, kwargs, exc=exc)
            raise
        _record(target_name, args, kwargs, result=result)
        return result

    wrapper._daikon_wrapped = True
    try:
        setattr(owner, attr, wrapper)
    except Exception:
        pass


def _patch(module_name, module):
    if module_name in _PATCHED_MODULES:
        return
    _PATCHED_MODULES.add(module_name)
    for dotted_name in TARGETS.get(module_name, []):
        _wrap(module, module_name, dotted_name)


class _Loader(importlib.abc.Loader):
    def __init__(self, module_name, wrapped):
        self.module_name = module_name
        self.wrapped = wrapped

    def create_module(self, spec):
        if hasattr(self.wrapped, "create_module"):
            return self.wrapped.create_module(spec)
        return None

    def exec_module(self, module):
        self.wrapped.exec_module(module)
        _patch(self.module_name, module)


class _Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname not in TARGETS:
            return None
        for finder in sys.meta_path:
            if finder is self:
                continue
            find_spec = getattr(finder, "find_spec", None)
            if find_spec is None:
                continue
            spec = find_spec(fullname, path, target)
            if spec is not None and spec.loader is not None:
                spec.loader = _Loader(fullname, spec.loader)
                return spec
        return None


for module_name in list(TARGETS):
    module_suffix = module_name.replace(".", "/") + ".py"
    if TRACE_ALL_MODULE_FUNCTIONS:
        _PROFILE_TARGETS[module_suffix] = None
    else:
        _PROFILE_TARGETS[module_suffix] = {
            dotted_name.split(".")[-1] for dotted_name in TARGETS.get(module_name, [])
            if dotted_name.split(".")[-1] != module_name.rsplit(".", 1)[-1]
        }
    if module_name in sys.modules:
        _patch(module_name, sys.modules[module_name])
sys.meta_path.insert(0, _Finder())


def _record_profile(frame, result=None, exc=None):
    try:
        filename = frame.f_code.co_filename.replace("\\", "/")
        func_name = frame.f_code.co_name
        module_suffix = None
        for suffix, names in _PROFILE_TARGETS.items():
            if filename.endswith(suffix) and (names is None or func_name in names):
                module_suffix = suffix
                break
        if module_suffix is None:
            return
        arg_count = frame.f_code.co_argcount + frame.f_code.co_kwonlyargcount
        arg_names = frame.f_code.co_varnames[:arg_count]
        args = tuple(frame.f_locals[name] for name in arg_names if name in frame.f_locals)
        target_name = module_suffix[:-3].replace("/", ".") + "." + func_name
        _record(target_name, args, {}, result=result, exc=exc)
    except Exception:
        pass


def _profile(frame, event, arg):
    if event == "return":
        _record_profile(frame, result=arg)
    elif event == "exception":
        exc = arg[1] if isinstance(arg, tuple) and len(arg) > 1 else None
        _record_profile(frame, exc=exc)
    return _profile


sys.setprofile(_profile)
atexit.register(lambda: sys.setprofile(None))
'''


def load_instances(dataset_path: Path) -> dict[str, dict[str, Any]]:
    return {
        row["instance_id"]: row
        for row in (json.loads(line) for line in dataset_path.read_text(encoding="utf-8").splitlines() if line.strip())
    }


def load_prediction_patch(prediction_file: Path | None, instance_id: str, human_patch: str = "") -> str:
    if human_patch:
        return human_patch
    if prediction_file is None:
        return ""
    for line in prediction_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("instance_id") == instance_id:
            return row.get("model_patch", "")
    raise RuntimeError(f"prediction for {instance_id} not found in {prediction_file}")


def trace_targets(instance: dict[str, Any], source: str) -> tuple[dict[str, list[str]], bool]:
    trace_all_module_functions = False
    if source in {"patch-functions", "patch-modules"}:
        raw = instance["patch_functions"]
        trace_all_module_functions = source == "patch-modules"
    elif source == "test-functions":
        raw = instance["test_functions"]
    elif source == "union":
        raw = instance["patch_functions"]
        patch_data = json.loads(raw) if isinstance(raw, str) else raw
        test_raw = instance["test_functions"]
        test_data = json.loads(test_raw) if isinstance(test_raw, str) else test_raw
        merged = {k: list(v) for k, v in patch_data.items()}
        for k, funcs in test_data.items():
            merged.setdefault(k, [])
            for func in funcs:
                if func not in merged[k]:
                    merged[k].append(func)
        raw = merged
    else:
        raise ValueError(source)
    data = json.loads(raw) if isinstance(raw, str) else raw
    targets: dict[str, list[str]] = {}
    for file_path, funcs in data.items():
        if not file_path.endswith(".py"):
            continue
        module = file_path[:-3].replace("/", ".")
        targets[module] = funcs
    return targets, trace_all_module_functions


def load_official_modules() -> None:
    sys.path.insert(0, str(OFFICIAL_REPO / "evaluation"))
    if not (OFFICIAL_REPO / "evaluation" / "test_spec.py").exists():
        raise FileNotFoundError(f"official SWE-Perf repo not found at {OFFICIAL_REPO}")
    if importlib.util.find_spec("docker") is None:
        raise RuntimeError("Python docker package is not available")


def setup_logger(log_path: Path) -> logging.Logger:
    logger = logging.getLogger(f"real-daikon-trace-{log_path.parent.name}")
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
    return ("docker.io/betty1202/" + image_name.replace("__", "_s_")).lower()


def run_real_trace(
    instance: dict[str, Any],
    out_dir: Path,
    timeout: int,
    target_source: str,
    model_patch: str = "",
) -> Path:
    load_official_modules()
    import docker
    from docker_build import build_container
    from docker_utils import cleanup_container, copy_from_container, copy_to_container, exec_run_with_timeout
    from test_spec import make_test_spec

    out_dir.mkdir(parents=True, exist_ok=True)
    logger = setup_logger(out_dir / "real_trace_run.log")
    test_spec = make_test_spec(instance, is_eval=True)
    test_spec.instance_image_key = docker_image_key(test_spec.instance_id)

    client = docker.from_env()
    container = None
    try:
        container = build_container(
            test_spec,
            client,
            "daikon-real-trace",
            logger,
            nocache=False,
            force_rebuild=False,
            is_large=True,
            from_remote=True,
        )
        container.start()
        logger.info("Container started: %s", container.id)

        if model_patch.strip():
            patch_file = out_dir / "model.patch"
            patch_file.write_text(model_patch, encoding="utf-8")
            copy_to_container(container, patch_file, Path("/tmp/model.patch"))
            apply_cmd = "/bin/bash -lc 'cd /testbed && git apply --whitespace=nowarn /tmp/model.patch'"
            result = container.exec_run(apply_cmd, user="root")
            if result.exit_code != 0:
                output = result.output.decode("utf-8", errors="replace") if result.output else ""
                raise RuntimeError(f"failed to apply model patch in container:\n{output}")
            logger.info("Applied model patch before trace collection")

        probe_dir = out_dir / "probe"
        probe_dir.mkdir(parents=True, exist_ok=True)
        sitecustomize = probe_dir / "sitecustomize.py"
        sitecustomize.write_text(SITE_CUSTOMIZE, encoding="utf-8")
        copy_to_container(container, sitecustomize, Path("/tmp/trace_probe/sitecustomize.py"))

        targets, trace_all_module_functions = trace_targets(instance, target_source)
        targets_json = json.dumps(targets)
        eval_file = out_dir / "eval_with_trace.sh"
        eval_file.write_text(
            dedent(
                f"""\
                export PYTHONPATH=/tmp/trace_probe:${{PYTHONPATH:-}}
                export DAIKON_TRACE_JSONL=/tmp/daikon_trace/runtime_trace.jsonl
                export DAIKON_TRACE_TARGETS='{targets_json}'
                export DAIKON_TRACE_ALL_MODULE_FUNCTIONS='{"1" if trace_all_module_functions else "0"}'
                mkdir -p /tmp/daikon_trace
                rm -f /tmp/daikon_trace/runtime_trace.jsonl
                {test_spec.eval_script}
                """
            ),
            encoding="utf-8",
        )
        copy_to_container(container, eval_file, Path("/eval_with_trace.sh"))
        _, timed_out, runtime = exec_run_with_timeout(
            container,
            "/bin/bash /eval_with_trace.sh",
            timeout,
            str(out_dir / "pytest_output.txt"),
        )
        logger.info("Trace pytest runtime: %.2f seconds", runtime)
        if timed_out:
            raise TimeoutError(f"trace run timed out after {timeout} seconds")

        trace_path = out_dir / "runtime_trace.jsonl"
        exists = container.exec_run("test -f /tmp/daikon_trace/runtime_trace.jsonl", user="root")
        if exists.exit_code == 0:
            copy_from_container(container, "/tmp/daikon_trace/runtime_trace.jsonl", trace_path)
        else:
            trace_path.write_text("", encoding="utf-8")
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
    return rows


def write_decls(path: Path, ppts: list[str], variables: list[str]) -> None:
    lines = ["decl-version 2.0", "input-language Python", "var-comparability none", ""]
    for ppt in sorted(set(ppts)):
        lines.extend([f"ppt {ppt}", "ppt-type point"])
        for name in variables:
            rep_type = "double" if name.endswith("_float") else "int"
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
            value = values[name]
            lines.extend([repr(value) if isinstance(value, float) else name, str(value) if not isinstance(value, float) else "1", "1"])
    # Fix accidental variable/value ordering for float branch by writing simply.
    lines = []
    for row in rows:
        lines.extend(["", row["program_point"]])
        values = row["values"]
        for name in variables:
            value = values[name]
            lines.extend([name, repr(value) if isinstance(value, float) else str(value), "1"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_invariants(output: str) -> dict[str, list[str]]:
    by_ppt: dict[str, list[str]] = {}
    current = None
    for raw in output.splitlines():
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


def mine(
    instance: dict[str, Any],
    trace_path: Path,
    out_dir: Path,
    daikon_jar: Path,
    target_source: str,
    prediction_label: str | None = None,
) -> Path:
    rows = read_trace(trace_path)
    decls = out_dir / "real_trace.decls"
    dtrace = out_dir / "real_trace.dtrace"
    daikon_output = out_dir / "daikon_output.txt"
    context = out_dir / "invariant_context.json"
    stable = ROOT / "experiments" / "swe_perf_pilot" / "invariants" / f"{instance['instance_id']}.real-daikon.json"

    by_ppt: dict[str, list[str]] = {}
    if rows:
        variables = list(rows[0]["values"].keys())
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
    else:
        decls.write_text("", encoding="utf-8")
        dtrace.write_text("", encoding="utf-8")
        daikon_output.write_text("No runtime observations for configured patch functions.\n", encoding="utf-8")

    runtime_rows = sum(1 for line in trace_path.read_text(encoding="utf-8").splitlines() if line.strip()) if trace_path.exists() else 0
    summary = {
        "task_id": instance["instance_id"],
        "trace_source": (
            "official SWE-Perf Docker image, patched program, official efficiency test execution"
            if prediction_label
            else "official SWE-Perf Docker image, base commit, official efficiency test execution"
        ),
        "prediction_label": prediction_label,
        "trace_target_source": target_source,
        "trace_targets": trace_targets(instance, target_source)[0],
        "runtime_trace_rows": runtime_rows,
        "deduplicated_trace_rows": len(rows),
        "efficiency_test": instance["efficiency_test"],
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
            if any(token in inv for token in ("==", " one of ", " <= ", " >= "))
        ][:40],
    }
    context.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if prediction_label is None:
        stable.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return context


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--daikon-jar", type=Path, default=Path("/tmp/daikon-5.8.24/daikon.jar"))
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--skip-trace", action="store_true")
    parser.add_argument("--prediction-file", type=Path, default=None)
    parser.add_argument("--prediction-label", default=None)
    parser.add_argument("--use-human-patch", action="store_true")
    parser.add_argument(
        "--target-source",
        choices=["patch-functions", "patch-modules", "test-functions", "union"],
        default="patch-functions",
    )
    args = parser.parse_args()

    instance = load_instances(args.dataset)[args.instance_id]
    prediction_label = args.prediction_label
    human_patch = instance.get("patch", "") if args.use_human_patch else ""
    model_patch = load_prediction_patch(args.prediction_file, args.instance_id, human_patch)
    if args.prediction_file and not prediction_label:
        prediction_label = args.prediction_file.stem
    if args.use_human_patch and not prediction_label:
        prediction_label = "human_patch"

    out_dir = ROOT / "experiments" / "swe_perf_pilot" / "results" / "daikon_real_trace" / args.instance_id
    if prediction_label:
        out_dir = out_dir / prediction_label
    out_dir.mkdir(parents=True, exist_ok=True)
    trace_path = out_dir / "runtime_trace.jsonl"
    if not args.skip_trace:
        trace_path = run_real_trace(instance, out_dir, args.timeout, args.target_source, model_patch)
    elif not trace_path.exists():
        raise FileNotFoundError(trace_path)
    context = mine(instance, trace_path, out_dir, args.daikon_jar, args.target_source, prediction_label)
    summary = json.loads(context.read_text(encoding="utf-8"))
    print(f"task: {args.instance_id}")
    print(f"runtime_trace_rows: {summary['runtime_trace_rows']}")
    print(f"deduplicated_trace_rows: {summary['deduplicated_trace_rows']}")
    print(f"context: {context}")
    for ppt, invs in summary["likely_invariants_by_program_point"].items():
        print(f"- {ppt}: {len(invs)} invariants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
