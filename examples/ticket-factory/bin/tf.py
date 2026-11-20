"""What every script of the ticket factory shares: its settings, where it keeps things, and how it reads
and writes ergostat's record.

Settings come from factory.conf (written by ./setup from factory.conf.example), and each may be overridden
in the environment as TF_<KEY>. Without a factory.conf, or with TF_OFFLINE=1, the factory is OFFLINE: Jira
and GitHub are the fakes in bin/fakes.py, the sample repository is a local one, and the work is the
stand-in's. That is how `scripts/demo_check.py` runs it, and how it runs on a fresh copy.
"""

from __future__ import annotations

import contextvars
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONF = ROOT / "factory.conf"
EXAMPLE = ROOT / "factory.conf.example"


def _read_conf(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = re.sub(r"\s+#.*$", "", line).strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


OFFLINE = os.environ.get("TF_OFFLINE", "") not in ("", "0", "no") or not CONF.exists()   # fixed for a process's life
_conf: dict[str, str] = {}
_read_at: tuple = ()


def _settings() -> dict[str, str]:
    """factory.conf over the example's defaults, read again whenever either file changes: a daemon, which runs for
    days, sees an edited setting at its next reading or run, as a process per run did."""
    global _conf, _read_at
    at = tuple(f.stat().st_mtime if f.exists() else None for f in (EXAMPLE, CONF))
    if at != _read_at:
        got = {**_read_conf(EXAMPLE), **({} if OFFLINE else _read_conf(CONF))}
        if OFFLINE:   # fast, local and free: nothing here reaches a service
            got.update({"AI": "standin", "SCRATCH": str(ROOT / "run"), "REPING_AFTER": "5s", "TEAMMATE_AFTER": "9s",
                        "TEAMMATE": "yes", "JIRA_URL": "https://jira.invalid", "JIRA_EMAIL": "owner@example.invalid",
                        "GITHUB_REPO": "example/sample", "REVIEWERS": "", "POLL_EVERY": "2s", "ACT_WAIT": "8s"})
        _conf, _read_at = got, at
    return _conf


def conf(key: str, default: str = "") -> str:
    return os.environ.get("TF_" + key, _settings().get(key, default))


def seconds(text: str) -> float:
    m = re.fullmatch(r"\s*([\d.]+)\s*(ms|s|m|h|d)?\s*", text or "0")
    if not m:
        raise ValueError(f"not a duration: {text!r}")
    return float(m.group(1)) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600, "d": 86400, None: 1}[m.group(2)]


def yes(key: str) -> bool:
    return conf(key).lower() in ("1", "yes", "true", "on")


SCRATCH = Path(os.path.expanduser(conf("SCRATCH")))
RUN = ROOT / "run"                       # what the example writes in its own folder (ignored by git)
REPO = RUN / "repo"                      # the repository's clone: the workspace pool's (ergostat.yaml)
REPORTS = ROOT / "reports"               # the daily summaries, shown on the Items page
SESSIONS = RUN / "sessions"              # each AI session's answer, linked from its ticket


# --- the run: a process of its own, or one of a daemon's (bin/daemon.py) ---------------------------------

CURRENT: contextvars.ContextVar[dict | None] = contextvars.ContextVar("CURRENT", default=None)   # in a daemon: {run, env}
_out = threading.Lock()
_open: set[str] = set()                  # a daemon's runs under way, not yet done: only their lines are said


def env(key: str) -> str | None:
    """One of the run's ERGOSTAT_* values (ERGOSTAT_ITEM, _LEASE, _RUN, _ACTIONS, _WORKSPACE, ...): in a daemon, from
    the run's own line, never the process's environment (where the next run would find it); in a process, from its
    environment."""
    run = CURRENT.get()
    return (run["env"].get(key) or None) if run is not None else os.environ.get(key)


def say(line: dict) -> None:
    """A line for ergostat on standard output: what a block moved, or an event about an item. In a daemon, tagged
    with the run it belongs to, and dropped once that run has ended."""
    run = CURRENT.get()
    with _out:
        if run is not None:
            if run["run"] not in _open:
                return
            line = {**line, "run": run["run"]}
        print(json.dumps(line), flush=True)


def begin(run: str) -> None:
    """A daemon's run under way."""
    with _out:
        _open.add(run)


def finish(run: str, code: int) -> bool:
    """A daemon's run ended, or was cancelled: {"done": EXIT, "run": ID}, once, and only for a run under way (a cancel
    that crossed its done says nothing). False when it had ended already."""
    with _out:
        if run not in _open:
            return False
        _open.discard(run)
        print(json.dumps({"done": code, "run": run}), flush=True)
        return True


def log(*words) -> None:
    """Anything for a person: to standard error, which ergostat keeps in the block's (or the daemon's) log."""
    print(*words, file=sys.stderr, flush=True)


# --- ergostat --------------------------------------------------------------------------------------

def ergostat() -> list[str]:
    """The command that runs ergostat on this project: what ergostat gives every block's run and sensor's command
    (ERGOSTAT_CMD), else `ergostat` on the PATH (run by hand)."""
    cmd = os.environ.get("ERGOSTAT_CMD")
    return shlex.split(cmd) if cmd else ["ergostat", "-C", str(ROOT)]


def engine(op: str, **args) -> dict | None:
    """Ask the running ergostat over its socket (ERGOSTAT_SOCKET, in every run's environment: SPEC 9.5), in
    milliseconds and without loading the model; None when there is none, and the caller runs the command instead.
    One JSON line asked, one answered: the standard library is enough."""
    import socket
    path = os.environ.get("ERGOSTAT_SOCKET")
    if not path:
        return None
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(float(args.pop("_timeout", 120)))
    try:
        s.connect(path)
        s.sendall((json.dumps({"op": op, "root": str(ROOT), **args}) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            got = s.recv(65536)
            if not got:
                break
            buf += got
    except OSError:
        return None
    finally:
        s.close()
    out = json.loads(buf) if buf else None
    if out is None or "elsewhere" in out:
        return None
    if "error" in out:
        raise RuntimeError(f"ergostat {op}: {out['error']}")
    return out


def run_ergostat(*args: str) -> str:
    r = subprocess.run([*ergostat(), *args], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"ergostat {' '.join(args[:3])}: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout


def record(type: str, item: str, data: dict | None = None, by: str = "ticket-factory") -> None:
    """Record an event now (not at the end of the run): what was done outside must never be done twice."""
    if engine("event", events=[{"event": type, "item": item, "data": data or {}}], source=by,
              causedby=env("ERGOSTAT_RUN")) is not None:
        return
    run_ergostat("event", "--add", type, "--item", item, "--data", json.dumps(data or {}), "--as", by)


def items(kind: str, state: str | None = None) -> list[dict]:
    got = engine("items", kind=kind, state=state)          # the running engine's, without a process (its socket),
    if got is not None:                                    # page by page (500 a page), every one of them
        out = got.get("items", [])
        while got.get("items") and len(out) < got.get("total", 0):
            got = engine("items", kind=kind, state=state, offset=len(out)) or {}
            out += got.get("items", [])
        return out
    args = ["item", "--kind", kind, "-n", "2000", "--json"]
    if state:
        args += ["--state", state]
    return json.loads(run_ergostat(*args)).get("items", [])


def item(id: str) -> dict | None:
    try:
        got = engine("item", id=id)
        if got is not None:
            return got["item"]
        return json.loads(run_ergostat("item", id, "--json"))
    except (RuntimeError, json.JSONDecodeError):
        return None


# --- small things ----------------------------------------------------------------------------------

def slug(text: str, n: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:n].strip("-") or "work"


def now() -> float:
    return time.time()


def ticket_id(key: str) -> str:
    return f"ticket/{key}"


def key_of(ticket: dict) -> str:
    return ticket["id"].split("/", 1)[1]


def timeout() -> float:
    """How long a call outside (git, gh) may take before it is given up: GIT_TIMEOUT, 5 minutes. A hung fetch must
    never hold a step, or the lock it took, for ever."""
    return seconds(conf("GIT_TIMEOUT", "5m"))


def git(*args: str, cwd: Path, check: bool = True) -> str:
    who = ["-c", "user.name=ticket-factory", "-c", "user.email=ticket-factory@example.invalid"] if OFFLINE else []
    try:
        r = subprocess.run(["git", *who, "-c", "advice.detachedHead=false", *args], cwd=cwd, capture_output=True,
                           text=True, timeout=timeout())
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"git {' '.join(args[:2])}: no answer in {timeout():g}s (GIT_TIMEOUT)") from None
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:2])}: {r.stderr.strip()}")
    return r.stdout.strip()


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(path)


def throttled(what: str, every: str | None = None) -> bool:
    """True when `what` was looked at less than POLL_EVERY ago (15s; offline never): the teammate, which runs
    every few seconds, looks at each pull request no more often than this."""
    if OFFLINE:
        return False
    path = RUN / "polled.json"
    seen = read_json(path, {})
    if time.time() - seen.get(what, 0) < seconds(every or conf("POLL_EVERY", "15s")):
        return True
    seen[what] = time.time()
    write_json(path, seen)
    return False


def once(key: str, fn):
    """fn(), done once for `key` and its result kept (run/once/): a step that waits (for an approval) after
    the AI agent's work runs again without running the agent again."""
    path = RUN / "once" / (re.sub(r"[^\w.-]+", "_", key)[:150] + ".json")
    if path.exists():
        return json.loads(path.read_text())
    got = fn()
    write_json(path, got)
    return got
