#!/usr/bin/env python3
"""Local showcase server with a real Daikon-tool endpoint."""

from __future__ import annotations

import json
import subprocess
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
TOOL = ROOT / "codex-skills" / "daikon-invariant-mining" / "scripts" / "invariant_tool.py"
CONTEXT = ROOT / "experiments" / "swe_perf_pilot" / "invariants" / "astropy__astropy-16058.real-daikon.json"


class ShowcaseHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DOCS), **kwargs)

    def do_GET(self) -> None:
        if self.path == "/api/daikon":
            self.run_daikon_tool()
            return
        super().do_GET()

    def run_daikon_tool(self) -> None:
        command = [
            sys.executable,
            str(TOOL),
            "--context",
            str(CONTEXT),
            "--target",
            "validate_power",
            "--limit",
            "12",
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )
            payload = {
                "ok": True,
                "command": " ".join(command),
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
            self.write_json(200, payload)
        except Exception as exc:  # noqa: BLE001 - local demo should surface failures.
            payload = {
                "ok": False,
                "command": " ".join(command),
                "error": str(exc),
            }
            self.write_json(500, payload)

    def write_json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    server = ThreadingHTTPServer(("127.0.0.1", port), ShowcaseHandler)
    print(f"Serving showcase at http://127.0.0.1:{port}")
    print("Daikon endpoint: /api/daikon")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
