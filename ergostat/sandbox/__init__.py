"""Running a program ergostat does not trust under the OS's sandbox, by allowlist (SPEC §12q, docs/SECURITY.md).

``run(argv, Policy(work=...))`` starts ``argv`` in the work copy with reads only of the copy, the toolchain and
``Policy.read``; writes only to the copy (never its ``.git``) and a private temporary folder; no network but, when
``Policy.hosts`` lists hosts, a filtering proxy on 127.0.0.1 (``proxy.py``); an environment of ``KEEP`` and what the
caller passes, with no marker that says it is sandboxed or under test; and every process it starts killed when it
ends. macOS: ``sandbox-exec`` (``seatbelt.py``); Linux: ``bwrap`` (``bwrap.py``); neither, and it refuses
(``Unavailable``): it never runs a program unsandboxed. Git on a work copy goes through ``git.py``, never inside."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import bwrap, seatbelt
from .proxy import Proxy

KEEP = ("HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TZ", "SHELL")


class Unavailable(RuntimeError):
    """No OS sandbox here (sandbox-exec or bwrap): the program is not run."""


@dataclass
class Policy:
    """``hosts``: name (or ``name:port``; ports 80 and 443 when none) -> the HTTP methods allowed (None: any).
    ``tls_unchecked``: hosts whose method limit may go unchecked inside a TLS tunnel (else such a host gets no tunnel).
    ``python``: the interpreter whose prefix and venv are readable (default: ergostat's)."""
    work: Path
    read: list = field(default_factory=list)
    hosts: dict = field(default_factory=dict)
    tls_unchecked: list = field(default_factory=list)
    env: dict = field(default_factory=dict)
    python: str = sys.executable


@dataclass
class Result:
    exit: int | None
    stdout: str
    stderr: str
    seconds: float
    timed_out: bool = False
    connections: list = field(default_factory=list)     # the proxy's log: one dict per connection asked for


def backend() -> str | None:
    if sys.platform == "darwin" and shutil.which("sandbox-exec"):
        return "seatbelt"
    if sys.platform.startswith("linux") and shutil.which("bwrap"):
        return "bwrap"
    return None


def toolchain(python: str) -> list[str]:
    """What a program needs to run, resolved: the interpreter's prefixes and the system's libraries and tools."""
    py = Path(python)
    prefixes = {sys.prefix, sys.base_prefix} if py == Path(sys.executable) else set()
    prefixes |= {str(py.parent.parent), str(Path(os.path.realpath(py)).parent.parent)}
    system = (["/usr/lib", "/System", "/bin", "/usr/bin", "/usr/share", "/private/var/select",
               "/private/var/db/timezone", "/private/etc/localtime", "/private/etc/ssl"] if sys.platform == "darwin" else
              ["/usr/lib", "/usr/lib64", "/lib", "/lib64", "/bin", "/usr/bin", "/usr/share", "/etc/ld.so.cache",
               "/etc/localtime", "/etc/alternatives", "/etc/ssl"])
    paths = [os.path.realpath(p) for p in sorted(prefixes) + system if os.path.exists(p)]
    return _whole(dict.fromkeys(paths))


def environment(policy: Policy, tmp: str, port: int | None, python: str) -> dict:
    path = os.pathsep.join(dict.fromkeys([str(Path(python).parent), "/usr/bin", "/bin"]))
    env = {k: os.environ[k] for k in KEEP if k in os.environ} | {"PATH": path, "TMPDIR": tmp}
    if port:
        url = f"http://127.0.0.1:{port}"
        env |= {k: url for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY")}
    return env | {k: str(v) for k, v in policy.env.items()}


def run(argv: list[str], policy: Policy, *, stdin: str = "", timeout: float = 60, cwd: Path | None = None) -> Result:
    """Run ``argv`` sandboxed; raises ``Unavailable`` rather than run it without a sandbox."""
    kind = backend()
    if kind is None:
        raise Unavailable("no OS sandbox here (sandbox-exec on macOS, bwrap on Linux): the program is not run")
    work = os.path.realpath(policy.work)
    reads = [*toolchain(policy.python), *_whole(os.path.realpath(r) for r in policy.read if os.path.exists(r))]
    tmp = os.path.realpath(tempfile.mkdtemp())
    proxy = canary = None
    started, timed_out = time.time(), False
    try:
        if policy.hosts:
            proxy = Proxy(policy.hosts, policy.tls_unchecked, unix=kind == "bwrap")
        port = proxy.port if proxy else None
        if kind == "seatbelt":
            canary = seatbelt.Canary(tmp, [work, *reads])
            args = seatbelt.argv(argv, work, tmp, reads, port)
        else:
            args = bwrap.argv(argv, work, tmp, reads, cwd or work, proxy.unix if proxy else None, port,
                              policy.python)
        p = subprocess.Popen(args, cwd=cwd or work, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, env=environment(policy, tmp, port, policy.python),
                             start_new_session=True)
        pipes = _pipes(p, stdin)
        try:
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
        _killpg(p.pid)
        p.wait()
    finally:
        if canary:
            canary.reap()           # every process of the run, wherever it went
        if proxy:
            proxy.close()
        shutil.rmtree(tmp, ignore_errors=True)
    out, err = (pipes[k].result() for k in ("out", "err"))
    return Result(None if timed_out else p.returncode, out, err, round(time.time() - started, 2), timed_out,
                  proxy.log if proxy else [])


def _whole(paths) -> list[str]:
    """Refuse a path that would open the root or the whole home folder."""
    home, out = os.path.realpath(Path.home()), []
    for r in paths:
        if r == "/" or (home + "/").startswith(r.rstrip("/") + "/"):
            raise ValueError(f"{r} would open the root or the whole home folder to the program")
        out.append(r)
    return out


def _killpg(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except OSError:
        pass


class _Read(threading.Thread):
    def __init__(self, f):
        super().__init__(daemon=True)
        self.f, self.chunks = f, []
        self.start()

    def run(self):
        for chunk in iter(lambda: self.f.read(65536), ""):
            self.chunks.append(chunk)

    def result(self) -> str:
        self.join(5)               # every process that held the pipe is dead by now
        return "".join(self.chunks)


def _pipes(p: subprocess.Popen, stdin: str) -> dict:
    def feed():
        try:
            p.stdin.write(stdin)
            p.stdin.close()
        except OSError:
            pass
    threading.Thread(target=feed, daemon=True).start()
    return {"out": _Read(p.stdout), "err": _Read(p.stderr)}
