"""The extreme-conditions tests (``extremes.py``) kept and run in the background, so ``check`` stays quick.

Each condition's result is kept in ``<state>/extremes.json``, keyed by the condition and by what it can reach: the
connected part of the model its pushed part belongs to (stocks, flows, auxiliaries, parameters, goals and blocks
joined by what they connect, name or read), each part as plain data (``version._plain``: where it is written and its
words left out). A condition on the whole model is kept per connected part. So a second check runs nothing, and an
edit runs again only the conditions whose part of the model changed. The conditions not kept run in a thread of their
own, at most ``BOUND`` seconds in all; what is not run by then is said."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from ..spec.ir import Spec
from . import version as ver

BOUND = 60.0            # seconds: one model's conditions run at most this long in all; the rest are said, not run
FILE = "extremes.json"
MOST_KEPT = 4000        # results kept on disk, the newest
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
    """The file in the project's state directory, when it has one (a model never run is kept in memory only)."""
    from ..store import state_dir
    d = state_dir(spec.name, spec.root, make=False) if spec.root else None
    return d / FILE if d is not None and d.is_dir() else None


def _load(path: Path | None) -> dict:
    if path is None:
        return _MEM.setdefault("", (None, {}))[1]
    try:
        m = path.stat().st_mtime
    except OSError:
        m = None
    was = _MEM.get(str(path))
    if was is None or (m is not None and was[0] != m):
        try:
            got = json.loads(path.read_text()) if m is not None else {}
        except (OSError, ValueError):
            got = {}
        _MEM[str(path)] = was = (m, {**(was[1] if was else {}), **got})
    return was[1]


def _save(path: Path | None, kept: dict) -> None:
    if path is None:
        return
    with _LOCK:
        mine = dict(list(kept.items())[-MOST_KEPT:])
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
    unchanged, else run (within ``budget`` seconds, when given). ``progress(done, of, skipped, so_far)``."""
    from .extremes import condition_result
    comp, fp = components(spec)
    path = _path(spec)
    kept = _load(path)
    began, saved, out, skipped = time.monotonic(), time.monotonic(), [], 0
    salt = json.dumps([params or {}, scales or {}], sort_keys=True, default=str)
    for i, c in enumerate(conds):
        which = [comp[c.part]] if c.part in comp else sorted(fp)
        what = json.dumps([c.key, c.empty, c.inputs, c.params, c.pools, c.setpoints, salt], sort_keys=True, default=str)
        keys = {w: ver._hash([what, fp[w]]) for w in which}
        if all(k in kept for k in keys.values()):
            got = [x for k in keys.values() for x in kept.pop(k)]
        elif budget is not None and time.monotonic() - began > budget:
            skipped += 1
            got = None
        else:
            got = condition_result(spec, c, params, scales)
        if got is not None:
            for w, k in keys.items():                      # kept per connected part, the newest last
                kept[k] = [x for x in got if comp.get(x[0], which[0]) == w]
            out.append((c, got))
        if path is not None and time.monotonic() - saved > SAVE_EVERY:
            _save(path, kept)
            saved = time.monotonic()
        if progress:
            progress(i + 1, len(conds), skipped, out)
    _save(path, kept)
    return out


class _Job:
    """One model's conditions, run in a thread of their own."""

    def __init__(self, spec: Spec, scales: dict | None):
        self.status = {"running": True, "done": 0, "of": 0, "skipped": 0}
        self.so_far: list = []
        self.got: dict | None = None
        self.spec = spec
        self.thread = threading.Thread(target=self._go, args=(spec, scales), daemon=True, name="extremes")
        self.thread.start()

    def _progress(self, done, of, skipped, so_far):
        self.status.update(done=done, of=of, skipped=skipped)
        self.so_far = list(so_far)

    def _go(self, spec: Spec, scales: dict | None) -> None:
        from . import extremes as ex
        try:
            self.got = ex.failures(spec, None, scales, BOUND, self._progress)
        except Exception as e:                            # the tests are a help to the check, never a reason it fails
            self.got, self.status["error"] = {}, f"{type(e).__name__}: {e}"
        finally:
            self.status["running"] = False

    def found(self) -> dict:
        if self.got is not None:
            return self.got
        from .extremes import merge
        return merge(self.spec, self.so_far)


def background(spec: Spec, scales: dict | None = None, wait: float | None = None) -> tuple[dict, dict]:
    """The failures found so far and where the run is (``{"running", "done", "of", "skipped"}``), after waiting at
    most ``wait`` seconds (None: until done) for the conditions running in the background."""
    _, fp = components(spec)
    key = (str(spec.root), spec.name, ver._hash([sorted(fp.values()), scales or {}]))
    job = _JOBS.get(key)
    if job is None or (job.status.get("skipped") and not job.thread.is_alive()):   # each asking runs more of what is left
        while len(_JOBS) >= 16:
            _JOBS.pop(next(iter(_JOBS)))
        job = _JOBS[key] = _Job(spec, scales)
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
