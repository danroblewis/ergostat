"""Running a program ergostat does not trust under the OS's sandbox, by allowlist: ``run(argv, Policy(work=...))``
(SPEC §12q, docs/SECURITY.md). macOS: ``seatbelt.py``; Linux: ``bwrap.py``; neither, and it refuses (``Unavailable``).
The only network is ``proxy.py``; git on a work copy goes through ``git.py``, never inside."""

from __future__ import annotations

import functools
import os
import resource
import select
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
from .seatbelt import _signal

NPROC = 256
KEEP = ("HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TZ", "SHELL")


class Unavailable(RuntimeError):
    """No OS sandbox here: the program is not run."""


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
    escaped: list = field(default_factory=list)         # pids still alive after the run was killed: it failed


def backend() -> str | None:
    if sys.platform == "darwin" and shutil.which("sandbox-exec"):
        return "seatbelt"
    if sys.platform.startswith("linux") and shutil.which("bwrap"):
        return "bwrap"
    return None


@functools.lru_cache(maxsize=16)
def _interpreter(python: str) -> tuple[str, ...]:
    """The interpreter's own account of its venv, base prefix, standard library and executable (the caller trusts it)."""
    code = "import sys, sysconfig; print(sys.prefix, sys.base_prefix, sysconfig.get_path('stdlib'), sys.executable, sep='\\n')"
    out = subprocess.run([python, "-I", "-c", code], capture_output=True, text=True, timeout=30, check=True)
    return tuple(out.stdout.splitlines()[:4])


def _links(path: str) -> list[str]:
    """A path and every link it goes through (each must be readable to be followed)."""
    out = []
    while len(out) < 40:
        d = os.path.realpath(os.path.dirname(path))
        path = os.path.join(d, os.path.basename(path))
        out.append(path)
        if not os.path.islink(path):
            break
        path = os.path.join(d, os.readlink(path))
    return out


def toolchain(python: str) -> tuple[list[str], list[str]]:
    """The paths readable inside, and the folders whose top-level shared libraries are: the venv, the standard library,
    the interpreter, the base prefix's certificates and libraries, and the system's. Never a whole prefix."""
    if not os.path.isabs(python):
        raise ValueError(f"the interpreter must be an absolute path: {python}")
    prefix, base, stdlib, exe = _interpreter(python)
    links = [*_links(exe), *_links(python)]
    own = [stdlib, os.path.join(base, "ssl"), *([prefix] if prefix != base else [])]
    system = (["/usr/lib", "/System", "/bin", "/usr/bin", "/usr/share", "/private/var/select",
               "/private/var/db/timezone", "/private/etc/localtime", "/private/etc/ssl"] if sys.platform == "darwin" else
              ["/usr/lib", "/usr/lib64", "/lib", "/lib64", "/bin", "/usr/bin", "/usr/share", "/etc/ld.so.cache",
               "/etc/localtime", "/etc/alternatives", "/etc/ssl"])
    paths = [*links, *(os.path.realpath(p) for p in own + system if os.path.exists(p))]
    libs = [os.path.realpath(os.path.join(base, "lib"))]
    return _whole(dict.fromkeys(paths)), _whole(p for p in libs if p not in paths and os.path.isdir(p))


def environment(policy: Policy, tmp: str, port: int | None, python: str) -> dict:
    path = os.pathsep.join(dict.fromkeys([str(Path(python).parent), "/usr/bin", "/bin"]))
    proxy = {k: f"http://127.0.0.1:{port}" for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY") if port}
    return ({k: os.environ[k] for k in KEEP if k in os.environ} | {"PATH": path, "TMPDIR": tmp} | proxy
            | {k: str(v) for k, v in policy.env.items()})


def run(argv: list[str], policy: Policy, *, stdin: str = "", timeout: float = 60, cwd: Path | None = None) -> Result:
    """Run ``argv`` sandboxed; raises ``Unavailable`` rather than run it without a sandbox."""
    kind = backend()
    if kind is None:
        raise Unavailable("no OS sandbox here (sandbox-exec on macOS, bwrap on Linux): the program is not run")
    work = _whole([os.path.realpath(policy.work)])[0]
    reads, libs = toolchain(policy.python)
    reads += _whole(os.path.realpath(r) for r in policy.read if os.path.exists(r))
    tmp = os.path.realpath(tempfile.mkdtemp())
    proxy = canary = None
    started, timed_out, code, escaped = time.time(), False, None, []
    rfd, wfd = os.pipe()            # the supervisor's report (seatbelt); closed here once the run has it
    try:
        if policy.hosts:
            proxy = Proxy(policy.hosts, policy.tls_unchecked, unix=kind == "bwrap")
        port = proxy.port if proxy else None
        if kind == "seatbelt":
            canary = seatbelt.Canary(tmp, [work, *reads, *libs])
            args = seatbelt.argv(argv, work, tmp, reads, libs, port, policy.python, wfd)
        else:
            args = bwrap.argv(argv, work, tmp, reads, libs, cwd or work, proxy.unix if proxy else None, port,
                              policy.python)
        p = subprocess.Popen(args, cwd=cwd or work, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, env=environment(policy, tmp, port, policy.python),
                             start_new_session=True, pass_fds=(wfd,) if canary else (), preexec_fn=_nproc_limit())
        os.close(wfd)
        pipes = _collect(p, stdin)
        if canary:                      # the supervisor inside says the program's exit, then freezes the run
            code, timed_out = _exit_code(p, rfd, timeout)
        else:
            try:
                code = p.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
        _signal(-p.pid, signal.SIGKILL)       # its process group
    finally:
        if canary:
            escaped = canary.reap()     # every process of the run, wherever it went
        if proxy:
            proxy.close()
        os.close(rfd)
        shutil.rmtree(tmp, ignore_errors=True)
    p.wait()
    out, err = pipes()
    if escaped:
        code = None
        err += f"\nergostat: {len(escaped)} process(es) of this run could not be killed: {escaped}\n"
    return Result(code, out, err, round(time.time() - started, 2), timed_out, proxy.log if proxy else [], escaped)


def _exit_code(p: subprocess.Popen, fd: int, timeout: float) -> tuple[int | None, bool]:
    """Read the supervisor's report; past the time limit ask it to stop the program, then give it two seconds."""
    timed_out = not select.select([fd], [], [], max(timeout, 0))[0]
    if timed_out:
        _signal(p.pid, signal.SIGTERM)
    data = os.read(fd, 64) if select.select([fd], [], [], 2)[0] else None
    try:
        return (None if timed_out else int(data)), timed_out
    except (TypeError, ValueError):
        return None, timed_out          # no report: the supervisor was killed from inside


def _nproc_limit():
    """At most ``NPROC`` processes more than the machine has now (RLIMIT_NPROC counts the user's, never more)."""
    now = len(seatbelt.pids()) if sys.platform == "darwin" else sum(d.isdigit() for d in os.listdir("/proc"))
    hard = resource.getrlimit(resource.RLIMIT_NPROC)[1]
    want = now + NPROC if hard == resource.RLIM_INFINITY else min(hard, now + NPROC)
    return lambda: resource.setrlimit(resource.RLIMIT_NPROC, (want, hard))


def _whole(paths) -> list[str]:
    """Refuse a path that would open the root or the whole home folder."""
    home, out = os.path.realpath(Path.home()), []
    for r in paths:
        if r == "/" or (home + "/").startswith(r.rstrip("/") + "/"):
            raise ValueError(f"{r} would open the root or the whole home folder to the program")
        out.append(r)
    return out


def _collect(p: subprocess.Popen, stdin: str):
    """Feed and read the run's pipes in a thread; ``join`` it once every process that held them is dead."""
    box: dict = {}
    t = threading.Thread(target=lambda: box.update(out=p.communicate(stdin)), daemon=True)
    t.start()
    return lambda: (t.join(5), box.get("out") or ("", ""))[1]
