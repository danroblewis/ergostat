"""macOS: ``sandbox-exec`` with ``(deny default)`` and explicit allows, and the reaper that finds every process of a
run, wherever it went (a new session, a double fork), by asking the kernel which sandbox it is in."""

from __future__ import annotations

import ctypes
import os
import signal
import subprocess
import tempfile

DEVICES = ("/dev/null", "/dev/zero", "/dev/random", "/dev/urandom", "/dev/tty", "/dev/dtracehelper")


def _q(p: str) -> str:
    return '"' + p.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _any(kind: str, paths) -> str:
    return " ".join(f"({kind} {_q(p)})" for p in paths)


def ancestors(paths) -> list[str]:
    """The folders above each allowed path: their own metadata only (``realpath`` and ``getcwd`` stat them)."""
    out = set()
    for p in paths:
        while p not in ("/", ""):
            p = os.path.dirname(p)
            out.add(p)
    return sorted(out)


def profile(work: str, tmp: str, reads: list[str], port: int | None) -> str:
    readable = [work, tmp, *reads]
    git = os.path.join(work, ".git")
    return "\n".join([
        "(version 1)", "(deny default)",
        "(allow process-fork)", f"(allow process-exec {_any('subpath', readable)})",
        "(allow signal (target same-sandbox))", "(allow sysctl-read)",
        "(allow ipc-posix-sem)",                                   # Python's multiprocessing locks
        f'(allow file-read* (literal "/") (literal "/etc") (literal "/var") {_any("subpath", readable)})',
        f"(allow file-read-metadata {_any('literal', ancestors(readable))})",
        f'(allow file-read* file-write-data file-ioctl {_any("literal", DEVICES)} (subpath "/dev/fd"))',
        f"(allow file-write* {_any('subpath', [work, tmp])})",
        f"(deny file-write* (literal {_q(git)}) (subpath {_q(git)}))",
        *([f'(allow network-outbound (remote ip "localhost:{port}"))'] if port else []),
    ])


def argv(cmd: list[str], work: str, tmp: str, reads: list[str], port: int | None) -> list[str]:
    return ["sandbox-exec", "-p", profile(work, tmp, reads, port), *cmd]


_check = None


def _sandbox_check():
    global _check
    if _check is None:
        f = ctypes.CDLL("/usr/lib/libSystem.dylib").sandbox_check
        f.restype, f.argtypes = ctypes.c_int, [ctypes.c_int, ctypes.c_char_p, ctypes.c_int]   # then one variadic
        _check = f
    return _check


class Canary:
    """A run's fingerprint: its processes may read its temporary folder but not this file. An unsandboxed process
    may read both; another app's sandbox does not allow this run's random folder."""

    def __init__(self, tmp: str, readable: list[str]):
        fd, self.path = tempfile.mkstemp()
        os.close(fd)
        self.tmp = tmp
        if any(self.path.startswith(r.rstrip("/") + "/") for r in readable):
            os.unlink(self.path)
            raise ValueError(f"the temporary folder is readable inside ({self.path}): the run could not be reaped")

    def ours(self, pid: int) -> bool:
        f = _sandbox_check()
        denied = f(pid, b"file-read-data", 1, ctypes.c_char_p(self.path.encode()))
        return denied == 1 and f(pid, b"file-read-data", 1, ctypes.c_char_p(self.tmp.encode())) == 0

    def reap(self, rounds: int = 50) -> int:
        """Kill every process of this user that carries the run's sandbox, until none is left."""
        killed = 0
        try:
            for _ in range(rounds):
                out = subprocess.run(["ps", "-U", str(os.getuid()), "-o", "pid=,stat="], capture_output=True, text=True)
                live = [int(pid) for pid, stat in (r.split() for r in out.stdout.splitlines()) if "Z" not in stat]
                found = [pid for pid in live if pid != os.getpid() and self.ours(pid)]
                if not found:
                    break
                for pid in found:
                    try:
                        os.kill(pid, signal.SIGKILL)
                        killed += 1
                    except OSError:
                        pass
        finally:
            os.unlink(self.path)
        return killed
