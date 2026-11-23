"""A compute worker over a pipe, for the tests: ``Pipe(argv)`` starts it, ``send`` writes one frame (numbered from 1
unless ``seq`` is given), ``read`` takes the next line it says (None past the timeout), ``close`` ends it."""

from __future__ import annotations

import json
import os
import queue
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

WORKER = Path(__file__).resolve().parent.parent / "ergostat" / "compute" / "worker"


def image_python() -> str:
    """The image's own Python (the venv's base interpreter), as a node with no ergostat would have it."""
    return getattr(sys, "_base_executable", None) or shutil.which("python3") or sys.executable


class Pipe:
    def __init__(self, argv: list[str], env: dict | None = None, cwd: str | None = None):
        self.p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  env=env, cwd=cwd, start_new_session=True)
        self.lines: queue.Queue = queue.Queue()
        self.seq = 0
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        for line in self.p.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def send(self, frame: dict | bytes, seq: int | None = None) -> None:
        if isinstance(frame, dict):
            self.seq += 1
            frame = json.dumps({"v": 1, "seq": self.seq if seq is None else seq, **frame}).encode() + b"\n"
        self.p.stdin.write(frame)
        self.p.stdin.flush()

    def read(self, timeout: float = 10.0) -> dict | None:
        try:
            line = self.lines.get(timeout=timeout)
        except queue.Empty:
            return None
        return None if line is None else json.loads(line)

    def until(self, type: str, timeout: float = 10.0) -> list[dict]:
        """Every frame read up to and including the first of ``type`` (beats on the way kept), within ``timeout``."""
        got, end = [], time.monotonic() + timeout
        while (left := end - time.monotonic()) > 0 and (f := self.read(left)) is not None:
            got.append(f)
            if f["type"] == type:
                return got
        raise AssertionError(f"no {type} in {got}; stderr: {self.stderr()}")

    def stderr(self) -> str:
        return self.p.stderr.read().decode(errors="replace") if self.p.poll() is not None else "(still running)"

    def close(self) -> int:
        """Ends it: stdin closed, then its session killed if it has not gone in 10 s."""
        try:
            self.p.stdin.close()
        except OSError:
            pass
        try:
            return self.p.wait(10)
        except subprocess.TimeoutExpired:
            os.killpg(self.p.pid, signal.SIGKILL)
            return self.p.wait(10)
