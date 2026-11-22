"""One check on every prefix of a batch at once, so bisecting a batch need not be serial: each head in a detached
worktree of its own, run/queue-prefix/<tag>-<i> (named here, removed by that name), its check (fac.suite in the
queue's box: a container of its own, [agents] prefix_cpus of queue_cpuset) in a thread, at most [suites] prefix_most
at a time. Each result is read from its own log: pass, fail, or unknown (a worktree or check that did not start, an
exit of a signal or of docker's own, a check that raised, no log): never pass (lesson-3). Stopped part way (SIGTERM
through fac.stop_on_term, an error), no check starts again, every container is killed by name (fac.stop_suites) and
every worktree it made is removed. Call it under the queue's lock: at its start it removes what a SIGKILLed run left
under run/queue-prefix/, by allowlist (only names of the <tag>-<i> pattern), which no live run can own then.
Named so, never after a stdlib module (queue.py)."""

from __future__ import annotations

import re
import shutil
import threading
from pathlib import Path

import agents
import fac

ROOT = "queue-prefix"                                   # under [paths] run
TAG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}-\d{8}T\d{6}Z$")          # a run's tag (fac.run_tag)
MADE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}-\d{8}T\d{6}Z-\d{1,3}$")  # a worktree this code names: <tag>-<i>
MOST = 8                                                # [suites] prefix_most's ceiling


def prefix_most(cfg: dict) -> int:
    """[suites] prefix_most: the checks run at once (default 4); not a whole number from 1 to MOST, refused."""
    v = cfg.get("suites", {}).get("prefix_most", 4)
    if type(v) is not int or not 1 <= v <= MOST:
        raise ValueError(f"[suites] prefix_most = {v!r}: a whole number from 1 to {MOST} (each is a container)")
    return v


def log_of(logs: Path, tag: str, i: int) -> Path:
    return logs / f"{tag}-{i}.txt"


def suite(cfg: dict, name: str, logs: Path, tag: str, **fmt):
    """The check for run_all: [suites] <name> (rerun with tests=..., or ruff) by fac.suite in the queue's box, on
    the prefix's worktree, its log log_of(logs, tag, i); its exit."""
    return lambda i, work: fac.suite(cfg, name, work, log_of(logs, tag, i), slot=False, box="queue", **fmt)[0]


def remove(repo: Path, root: Path, name: str) -> None:
    """The worktree ``name`` under ``root``, gone: only a name this code makes, never a path that leads out."""
    if not MADE.match(name):
        raise ValueError(f"not a prefix worktree's name: {name!r}")
    wt = root / name
    if wt.is_symlink():                                 # (the link alone, never what it points to)
        wt.unlink()
        return
    fac.git(repo, "worktree", "remove", "--force", str(wt), check=False)
    if wt.exists():
        shutil.rmtree(wt)


def sweep(cfg: dict, repo: Path) -> list[str]:
    """The worktrees a SIGKILLed run left under run/queue-prefix/, removed (under the queue's lock); their names.
    Anything else there is kept."""
    root = fac.run_dir(cfg, ROOT).resolve()
    gone = sorted(p.name for p in root.iterdir() if MADE.match(p.name))
    for name in gone:
        remove(repo, root, name)
    return gone


def read(head: str, rc, log: Path, why: str = "") -> dict:
    text = log.read_text(errors="replace") if log.is_file() else ""
    if why or not text.strip() or type(rc) is not int or rc < 0 or rc in agents.NOT_STARTED:
        result = "unknown"
        why = why or ("no log" if not text.strip() else f"exit {rc!r}: it did not run to its end")
    else:
        result = "pass" if rc == 0 else "fail"
    return {"head": head, "result": result, "rc": rc, "log": str(log), "tail": text[-2000:],
            **({"why": why} if why else {})}


def run_all(cfg: dict, repo: Path, heads: list[str], check, tag: str, logs: Path, most: int | None = None) -> list:
    """check(i, worktree) on each of ``heads`` (head i in run/queue-prefix/<tag>-i), at most ``most`` (default
    [suites] prefix_most; held to 1..MOST here again) at a time; one result per head, in heads' order (read())."""
    if not TAG.match(tag) or len(heads) > 999:
        raise ValueError(f"a prefix run's tag {tag!r} is not a run tag, or {len(heads)} heads are more than 999")
    most = prefix_most(cfg) if most is None else most
    if type(most) is not int or not 1 <= most <= MOST:
        raise ValueError(f"prefix runs at once = {most!r}: a whole number from 1 to {MOST}")
    if cfg.get("suites", {}).get("queue_container", True) is not False:
        agents.prefix_cpus(cfg)                         # (refused before any is made, never one by one)
    root, repo = fac.run_dir(cfg, ROOT).resolve(), Path(repo)
    sweep(cfg, repo)
    made, out, gate, stop = [], [None] * len(heads), threading.Semaphore(most), threading.Event()

    def one(i: int, head: str) -> None:
        with gate:
            if stop.is_set():
                return
            log, wt = log_of(logs, tag, i), root / f"{tag}-{i}"
            log.unlink(missing_ok=True)                 # (never an earlier run's log read as this one's)
            made.append(wt.name)                        # (before it is made: a half-made one is removed too)
            try:
                fac.git(repo, "worktree", "add", "-q", "--detach", str(wt), head)
                rc, why = (None, "stopped") if stop.is_set() else (check(i, wt), "")
            except BaseException as e:                  # (a check that raised: its result unknown, said)
                rc, why = None, f"{type(e).__name__}: {e}"[:400]
            out[i] = read(head, rc, log, "stopped" if stop.is_set() else why)

    ts = [threading.Thread(target=one, args=(i, h), daemon=True) for i, h in enumerate(heads)]
    try:
        for t in ts:
            t.start()
        while any(t.is_alive() for t in ts):
            for t in ts:
                t.join(0.5)
    except BaseException:                               # stopped: no check starts, each running one is killed
        stop.set()
        while any(t.is_alive() for t in ts):
            fac.stop_suites()                       # (again each pass: one started as the stop came)
            for t in ts:
                t.join(0.5)
        raise
    finally:
        for name in list(made):
            remove(repo, root, name)
    return [r or read(heads[i], None, log_of(logs, tag, i), "no result") for i, r in enumerate(out)]
