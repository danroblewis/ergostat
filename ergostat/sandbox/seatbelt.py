"""macOS: ``sandbox-exec`` with ``(deny default)`` and explicit allows, and the reaper that finds every process of a
run, wherever it went (a new session, a double fork), by asking the kernel which sandbox it is in."""

from __future__ import annotations

import ctypes
import functools
import os
import re
import signal
import tempfile
import time

PER = 5
DEVICES = ("/dev/null", "/dev/zero", "/dev/random", "/dev/urandom", "/dev/tty")


def _q(p: str) -> str:
    return '"' + p.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _rules(action: str, kind: str, paths) -> str:
    """One rule per five filters: long filter lists have panicked macOS 15.5's kernel (docs/SECURITY.md)."""
    paths = list(paths)
    return "\n".join(f"({action} " + " ".join(f"({kind} {_q(p)})" for p in paths[i:i + PER]) + ")"
                     for i in range(0, len(paths), PER))


def ancestors(paths) -> list[str]:
    """The folders above each allowed path: their own metadata only (``realpath`` and ``getcwd`` stat them)."""
    out = set()
    for p in paths:
        while p not in ("/", ""):
            p = os.path.dirname(p)
            out.add(p)
    return sorted(out)


def profile(work: str, tmp: str, reads: list[str], libs: list[str], port: int | None) -> str:
    readable = [work, tmp, *reads]
    git = os.path.join(work, ".git")
    return "\n".join([
        "(version 1)", "(deny default)",
        "(allow process-fork)", _rules("allow process-exec", "subpath", readable),
        "(allow signal (target same-sandbox))", "(allow sysctl-read)",
        '(deny sysctl-read (sysctl-name-prefix "kern.proc") (sysctl-name "kern.procargs2") (sysctl-name "kern.procargs"))',
        "(allow ipc-posix-sem)",                                   # Python's multiprocessing locks
        _rules("allow file-read*", "literal", ["/", "/etc", "/var", "/private/etc/localtime"]),
        _rules("allow file-read*", "subpath", readable),
        *(f'(allow file-read* (regex #"^{re.escape(d)}/[^/]+\\.(dylib|so)$"))' for d in libs),
        _rules("allow file-read-metadata", "literal", ancestors([*readable, *libs])),
        _rules("allow file-read* file-write-data", "literal", DEVICES), '(allow file-read* file-write-data (subpath "/dev/fd"))',
        _rules("allow file-write*", "subpath", [work, tmp]),
        f"(deny file-write* (literal {_q(git)}) (subpath {_q(git)}))",
        *([f'(allow network-outbound (remote ip "localhost:{port}"))'] if port else []),
    ])


# The program's parent inside: it reports the exit, then stops the whole run at once (kill -1 reaches this sandbox's
# processes only, itself included), so none can fork away while ergostat, outside, finds and kills them.
SUPERVISE = r"""
import os, signal, subprocess, sys
fd, argv = int(sys.argv[1]), sys.argv[2:]
p = subprocess.Popen(argv)
signal.signal(signal.SIGTERM, lambda *a: p.kill())
os.write(fd, b"%d\n" % p.wait())
os.kill(-1, signal.SIGSTOP)
"""


def argv(cmd: list[str], work: str, tmp: str, reads: list[str], libs: list[str], port: int | None, python: str,
         fd: int) -> list[str]:
    return ["sandbox-exec", "-p", profile(work, tmp, reads, libs, port), python, "-I", "-c", SUPERVISE, str(fd), *cmd]


@functools.cache
def _libs():
    lib = ctypes.CDLL("/usr/lib/libSystem.dylib")
    lib.sandbox_check.restype = ctypes.c_int
    lib.sandbox_check.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int]       # then one variadic
    lib.proc_listallpids.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
    return lib


def pids() -> list[int]:
    buf = (ctypes.c_int * (_libs().proc_listallpids(None, 0) + 512))()
    return list(buf[:max(_libs().proc_listallpids(buf, ctypes.sizeof(buf)), 0)])


def alive(pid: int) -> bool:
    """Not gone and not a zombie (``proc_bsdinfo.pbi_status`` is SZOMB, 5)."""
    info = ctypes.create_string_buffer(136)
    return _libs().proc_pidinfo(pid, 3, 0, info, 136) > 0 and info.raw[4] != 5


class Canary:
    """A run's fingerprint: its processes may read its temporary folder but not this file (an unsandboxed process may
    read both; another app's sandbox, neither)."""

    def __init__(self, tmp: str, readable: list[str]):
        fd, self.path = tempfile.mkstemp()
        os.close(fd)
        self.tmp, self.others = tmp, set()
        if any(self.path.startswith(r.rstrip("/") + "/") for r in readable):
            os.unlink(self.path)
            raise ValueError(f"the temporary folder is readable inside ({self.path}): the run could not be reaped")

    def ours(self, pid: int) -> bool:
        f = _libs().sandbox_check
        denied = f(pid, b"file-read-data", 1, ctypes.c_char_p(self.path.encode()))
        return denied == 1 and f(pid, b"file-read-data", 1, ctypes.c_char_p(self.tmp.encode())) == 0

    def _find(self, skip=()) -> list[int]:     # a process found not to be the run's never becomes one
        found = []
        for p in pids():
            if p in skip or p in self.others or p == os.getpid():
                continue
            if self.ours(p) and alive(p):
                found.append(p)
            else:
                self.others.add(p)
        return found

    def reap(self, rounds: int = 500, quiet: int = 3) -> list[int]:
        """Stop every live process carrying the run's sandbox, round after round until ``quiet`` rounds find none,
        then kill them all. Returns what is still alive after that: the caller fails the run on it."""
        held: set[int] = set()
        try:
            empty = 0
            for _ in range(rounds):
                new = self._find(held)
                for pid in new:
                    _signal(pid, signal.SIGSTOP)
                held.update(new)
                empty = 0 if new else empty + 1
                if empty >= quiet:
                    break
            for _ in range(50):
                for pid in held:
                    _signal(pid, signal.SIGKILL)
                held = set(self._find())
                if not held:
                    return []
                time.sleep(0.01)
            return sorted(held)
        finally:
            os.unlink(self.path)


def _signal(pid: int, sig: int) -> None:
    try:
        os.kill(pid, sig)
    except OSError:
        pass
