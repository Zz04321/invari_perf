#!/usr/bin/env python3
"""Preflight checks for the small SWE-Perf Codex baseline."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def check(label: str, ok: bool, detail: str) -> bool:
    status = "OK" if ok else "FAIL"
    print(f"[{status}] {label}: {detail}")
    return ok


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def run_quiet(cmd: list[str], timeout: int = 20) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout,
        )
    except Exception as exc:
        return False, str(exc)
    return result.returncode == 0, result.stdout.strip()[-500:]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--official-repo", default="/tmp/swe-perf-official")
    parser.add_argument("--dataset-name-or-path", default="SWE-Perf/SWE-Perf")
    args = parser.parse_args()

    failures = 0

    official_repo = Path(args.official_repo)
    failures += not check(
        "official SWE-Perf repo",
        (official_repo / ".git").exists(),
        str(official_repo),
    )
    failures += not check("conda", command_exists("conda"), shutil.which("conda") or "not found")
    failures += not check("codex", command_exists("codex"), shutil.which("codex") or "not found")
    failures += not check("docker", command_exists("docker"), shutil.which("docker") or "not found")

    ok, out = run_quiet(["conda", "run", "-n", "sweperf", "python", "-c", "import datasets, docker; print('ready')"])
    failures += not check("sweperf conda env", ok, out)

    dataset_path = Path(args.dataset_name_or_path)
    if dataset_path.exists():
        ok, out = run_quiet(
            [
                "conda",
                "run",
                "-n",
                "sweperf",
                "python",
                "-c",
                (
                    "from datasets import load_from_disk; "
                    f"d=load_from_disk({str(dataset_path)!r}); "
                    "print(d)"
                ),
            ],
            timeout=60,
        )
        failures += not check("local SWE-Perf dataset", ok, out)
    else:
        ok, out = run_quiet(
            [
                "conda",
                "run",
                "-n",
                "sweperf",
                "python",
                "-c",
                (
                    "from datasets import load_dataset; "
                    f"d=load_dataset({args.dataset_name_or_path!r}, split='test'); "
                    "print(len(d))"
                ),
            ],
            timeout=60,
        )
        failures += not check("remote SWE-Perf dataset", ok, out)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
