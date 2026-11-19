"""The extreme-conditions tests (``extremes.py``) kept and run in the background, so ``check`` stays quick.

Each condition's result is kept in ``<state>/extremes.json``, keyed by the condition and by what it can reach: the
connected part of the model its pushed part belongs to (stocks, flows, auxiliaries, parameters, goals and blocks
joined by what they connect, name or read), each part as plain data (``version._plain``: where it is written and its
words left out). A condition on the whole model is kept per connected part. So a second check runs nothing, and an
edit runs again only the conditions whose part of the model changed. The conditions not kept run in the background,
by one low-priority process per project (``main``), at most ``BOUND`` seconds in all; what is not run by then is said.
Writers merge what they added into the file under its lock."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from ..spec.ir import Spec
from . import version as ver

BOUND = 60.0            # seconds: one model's conditions run at most this long in all; the rest are said, not run
FILE = "extremes.json"
MOST_KEPT = 4000        # results kept on disk, the newest
KEYS = 2                # the keys' version: a change to what a result holds or how it is worked out raises it
SAVE_EVERY = 1.0        # seconds: the results are written at most this often while running
_MEM: dict[str, tuple[float | None, dict]] = {}   # the file → (its modification time as read, its results)
_LOCK = threading.Lock()
_JOBS: dict[tuple, _Job] = {}


def _r(x) -> str:
    return f"{x.kind}.{x.name}"


def components(spec: Spec) -> tuple[dict[str, str], dict[str, str]]:
    """Each part → its connected part's name (its first ref), and each connected part → its content's hash."""
    parts: dict[str, object] = {}
    links: list[tuple[str, str]] = []
    for kind, table in (("stock", spec.stocks), ("flow", spec.flows), ("auxiliary", spec.auxiliaries),
                        ("parameter", spec.parameters), ("goal", spec.goals), ("block", spec.blocks)):
        for n, x in table.items():
            r = f"{kind}.{n}"
            parts[r] = x
            links += [(r, f"stock.{s}") for s in (getattr(x, "source", None), getattr(x, "target", None)) if s]
            links += [(r, _r(d)) for d in getattr(x, "driven_by", None) or []]
            e = getattr(x, "equation", None)
            links += [(r, d) for d in (e.refs if e else [])] + [(r, f"parameter.{d}") for d in (e.parameters if e else [])]
    links += [(f"goal.{n}", _r(g.of)) for n, g in spec.goals.items()]
    links += [(f"block.{n}", _r(t)) for n, b in spec.blocks.items() for t in (*b.reads(), *b.targets())]
    up = {r: r for r in parts}

    def root(r):
        while up[r] != r:
            up[r] = up[up[r]]
            r = up[r]
        return r
    for a, b in links:
        if a in up and b in up:
            up[root(a)] = root(b)
    comp = {r: root(r) for r in parts}
    members: dict[str, list] = {}
    for r in sorted(parts):
        members.setdefault(comp[r], []).append([r, ver._plain(parts[r])])
    return comp, {c: ver._hash(m) for c, m in members.items()}


def _path(spec: Spec) -> Path | None:
    """The file in the project's state directory, when it has one: never made here (a model never run is kept in
    memory only)."""
    from ..store import state_dir
    d = state_dir(spec.name, spec.root, make=False) if spec.root else None
    return d / FILE if d is not None and d.is_dir() else None


@contextlib.contextmanager
def _locked(path: Path, wait: bool = True):
    """The file's lock (``extremes.json.lock``), held across processes: yields whether it was taken."""
    with open(path.with_name(path.name + ".lock"), "a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def _load(path: Path | None) -> dict:
    if path is None:
        return _MEM.setdefault("", (None, {}))[1]
    try:
        m = path.stat().st_mtime
    except OSError:
        m = None
    was = _MEM.get(str(path))
    if was is None or (m is not None and was[0] != m):
        _MEM[str(path)] = was = (m, {**(was[1] if was else {}), **(_read(path) if m is not None else {})})
    return was[1]


def _save(path: Path | None, added: dict) -> None:
    """What this run added, merged into what is on disk under the lock (another process may have written since)."""
    if path is None or not added:
        return
    with _LOCK, _locked(path):
        mine = {**_read(path), **added}
        mine = dict(list(mine.items())[-MOST_KEPT:])
        tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            tmp.write_text(json.dumps(mine))
            os.replace(tmp, path)
            _MEM[str(path)] = (path.stat().st_mtime, mine)
        except OSError:
            pass


def results(spec: Spec, conds: list, params: dict | None, scales: dict | None, budget: float | None = None,
            progress=None) -> list[tuple]:
    """Each condition's failures (``extremes.condition_result``), from what is kept where its part of the model is
    unchanged, else run (within ``budget`` seconds, when given; each condition is itself bounded in steps,
    ``closedloop.MAX_STEPS`` and ``extremes.CONFIRM``). A condition that could not run is not kept: it is tried
    again next time. ``progress(done, of, skipped, so_far)``."""
    from . import extremes as ex
    comp, fp = components(spec)
    path = _path(spec)
    kept = _load(path)
    added: dict = {}
    began, saved, out, skipped = time.monotonic(), time.monotonic(), [], 0
    salt = json.dumps([KEYS, params or {}, scales or {}], sort_keys=True, default=str)
    for i, c in enumerate(conds):
        which = [comp[c.part]] if c.part in comp else sorted(fp)
        what = json.dumps([c.key, c.empty, c.inputs, c.params, c.pools, c.setpoints, salt], sort_keys=True, default=str)
        keys = {w: ver._hash([what, fp[w]]) for w in which}
        if all(k in kept for k in keys.values()):
            got = [x for k in keys.values() for x in kept[k]]
        elif budget is not None and time.monotonic() - began > budget:
            got, skipped = None, skipped + 1
        else:
            got = ex.condition_result(spec, c, params, scales)
            for w, k in (keys.items() if got is not None else ()):     # kept per connected part
                kept[k] = added[k] = [x for x in got if comp.get(x[0], which[0]) == w]
        if got is not None:
            out.append((c, got))
        if added and time.monotonic() - saved > SAVE_EVERY:
            _save(path, added)
            added, saved = {}, time.monotonic()
        if progress:
            progress(i + 1, len(conds), skipped, out)
    _save(path, added)
    return out


def _running(path: Path) -> bool:
    """Whether a runner holds this project's run lock (``extremes.run.lock``)."""
    with _locked(path.with_name("extremes.run"), wait=False) as took:
        return not took


class _Job:
    """One model's conditions, run in the background: by one process per project, at a low priority, where the
    project has a state directory to keep them in (so neither the engine nor the page server waits on them, and
    ``check`` may exit while they finish), else in a thread."""

    def __init__(self, spec: Spec, alone: bool):
        self.status = {"running": True, "done": 0, "of": 0, "skipped": 0}
        self.so_far: list = []
        self.got: dict | None = None
        self.spec, self.path, self.proc = spec, _path(spec), None
        self.alone = bool(alone and self.path is not None and spec.files)
        if self.alone and not _running(self.path):
            self.proc = subprocess.Popen([sys.executable, "-m", "ergostat.numbers.extremes_cache", str(spec.files[0])],
                                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                         start_new_session=True)
        self.thread = threading.Thread(target=self._go, daemon=True, name="extremes")
        self.thread.start()

    def _progress(self, done, of, skipped, so_far):
        self.status.update(done=done, of=of, skipped=skipped)
        self.so_far = list(so_far)

    def _go(self) -> None:
        from . import extremes as ex
        try:
            if self.proc is not None:
                self.proc.wait()
            while self.alone and _running(self.path):     # another's runner (a check, the page), until it is done
                time.sleep(0.25)
            self.got = ex.failures(self.spec, None, None, -1.0 if self.alone else BOUND, self._progress)
        except Exception as e:                            # the tests are a help to the check, never a reason it fails
            self.got, self.status["error"] = {}, f"{type(e).__name__}: {e}"
        finally:
            self.status["running"] = False

    def found(self) -> dict:
        if self.got is not None:
            return self.got
        from . import extremes as ex
        if self.alone:                                    # what the runner has kept so far, and how far it is
            try:
                self.status.update(json.loads(self.path.with_name("extremes.progress").read_text()))
            except (OSError, ValueError):
                pass
            return ex.failures(self.spec, None, None, -1.0)
        return ex.merge(self.spec, self.so_far)


def background(spec: Spec, wait: float | None = None) -> tuple[dict, dict]:
    """The failures found so far and where the run is (``{"running", "done", "of", "skipped"}``), after waiting at
    most ``wait`` seconds (None: until done, in this process) for the conditions running in the background."""
    _, fp = components(spec)
    key = (str(spec.root), spec.name, ver._hash(sorted(fp.values())))
    job = _JOBS.get(key)
    if job is None or (job.status.get("skipped") and not job.thread.is_alive()):   # each asking runs more of what is left
        while len(_JOBS) >= 16:
            _JOBS.pop(next(iter(_JOBS)))
        job = _JOBS[key] = _Job(spec, wait is not None)
    job.thread.join(wait)
    return job.found(), dict(job.status)


def said(status: dict) -> str | None:
    """Where the extreme-conditions tests are, in words, while they are not all run: None when they are."""
    if status.get("running"):
        return f"extremes: running ({status.get('done', 0)} of {status.get('of') or '?'} conditions)"
    if status.get("skipped"):
        return (f"extremes: {status['skipped']} of {status['of']} conditions not run within {BOUND:g} s; each check runs "
                f"more of them")
    return None


def main(path: Path) -> None:
    """The runner a _Job starts (``python -m ergostat.numbers.extremes_cache MODEL``, at a low priority and stopped at
    ``BOUND`` seconds and a little more whatever it is doing: what it finished is kept): one per project, it returns at
    once when another holds the run lock."""
    from ..spec import read
    from .extremes import failures
    model, _ = read(path, extremes=False)
    where, last = _path(model), [0.0]
    if where is None:
        return

    def told(done, of, skipped, _so_far):
        if time.monotonic() - last[0] > SAVE_EVERY or done == of:
            last[0] = time.monotonic()
            try:
                where.with_name("extremes.progress").write_text(json.dumps({"done": done, "of": of}))
            except OSError:
                pass
    with _locked(where.with_name("extremes.run"), wait=False) as took:
        if took:
            failures(model, None, None, BOUND, told)


if __name__ == "__main__":                                # the process alone: a low priority, and stopped at the bound
    if hasattr(os, "nice"):
        os.nice(10)
    if hasattr(signal, "alarm"):
        signal.alarm(int(BOUND) + 5)
    main(Path(sys.argv[1]))
