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
import uuid
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


class Taken:
    """The engine's rule for ``out`` frames (SPEC §12s.3), as the tests keep it: per run and stream the offset taken
    up to; a frame wholly below it is dropped (a resend), one reaching past it has its new bytes taken, and one that
    starts past it is a gap (the assertion fails). So a resend is recorded once."""

    def __init__(self):
        self.at: dict[tuple[str, str], int] = {}
        self.parts: dict[tuple[str, str], list[bytes]] = {}

    def take(self, f: dict) -> bool:
        key, data = (f["run"], f["stream"]), f["text"].encode("utf-8", "surrogateescape")
        at = self.at.get(key, 0)
        assert f["offset"] <= at, f"a gap: {f['offset']} past {at}"
        if f["offset"] + len(data) <= at:
            return False
        self.parts.setdefault(key, []).append(data[at - f["offset"]:])
        self.at[key] = f["offset"] + len(data)
        return True

    def bytes(self, run: str, stream: str) -> bytes:
        return b"".join(self.parts.get((run, stream), []))


def alive(pid: int) -> bool:
    """A process there and not a zombie (a container's PID 1 may never reap what is reparented to it)."""
    if sys.platform.startswith("linux"):
        try:
            return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
        except OSError:
            return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def until(cond, timeout: float = 10.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return cond()


class Node:
    """A worker over a pipe on a root of its own; ``end`` kills every run group and keeper it started. Frames read
    that answer no request (``out``, ``ended``, ``beat``) are kept in ``heard``."""

    def __init__(self, tmp: Path, *more: str):
        self.tmp, self.root = tmp, tmp / "r"
        self.keepers: list[int] = []
        self.n = 0
        self.connect(*more)

    def connect(self, *more: str) -> None:
        """A worker on the same root (a new session), its hello read."""
        self.w = Pipe([image_python(), "-I", str(WORKER), "--stdio", "--root", str(self.root), *more],
                      env={**os.environ, "HOME": str(self.tmp)})
        self.heard: list[dict] = []
        self.hello = self.w.read()
        assert self.hello["type"] == "hello", self.w.stderr()

    def tell(self, type: str, **fields) -> None:
        self.n += 1
        self.w.send({"type": type, "id": self.n, **fields})

    def ask(self, type: str, **fields) -> dict:
        self.tell(type, **fields)
        end = time.monotonic() + 10
        while time.monotonic() < end:
            f = self.w.read(10)
            assert f is not None, self.w.stderr()
            if f.get("id") == self.n:
                return f
            self.heard.append(f)
        raise AssertionError(f"no answer to {type}")

    def hear(self, type: str, timeout: float = 10.0, **match) -> dict:
        """Frames read into ``heard`` up to the first of ``type`` with the fields ``match``, which it returns."""
        end = time.monotonic() + timeout
        while (left := end - time.monotonic()) > 0 and (f := self.w.read(left)) is not None:
            self.heard.append(f)
            if f["type"] == type and all(f.get(k) == v for k, v in match.items()):
                return f
        raise AssertionError(f"no {type} {match}; stderr: {self.w.stderr()}")

    def start(self, command: str, **fields) -> tuple[str, dict]:
        run = uuid.uuid4().hex
        got = self.ask("start", run=run, command=command, block="b", **fields)
        if got["type"] == "started":
            self.keepers.append(got["keeper"])
        return run, got

    def dir(self, run: str) -> Path:
        return self.root / "runs" / run

    def exit(self, run: str, timeout: float = 10.0) -> dict:
        f = self.dir(run) / "exit"
        assert until(f.exists, timeout), (sorted(p.name for p in self.dir(run).iterdir()),
                                          (self.dir(run) / "keeper.log").read_text())
        return json.loads(f.read_text())

    def pgid(self, run: str) -> int:
        f = self.dir(run) / "pgid"
        assert until(f.exists)
        return int(f.read_text())

    def end(self) -> None:
        self.w.close()
        for d in (self.root / "runs").glob("*/pgid"):
            try:
                os.killpg(int(d.read_text()), signal.SIGKILL)
            except (OSError, ValueError):
                pass
        for pid in self.keepers:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
