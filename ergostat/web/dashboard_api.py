"""``GET /api/dashboards`` and ``GET /api/dashboard/NAME`` (SPEC §4f): a dashboard's every panel in one answer, each
built by the very function its own endpoint calls (``server._answer`` on the same path and parameters), all on one
snapshot, so a panel says exactly what its endpoint would at that moment.

Each panel has its own time limit. One past it answers ``{"pending": true, "moment": N}`` and keeps being worked
out on the dashboard's pool, so a poll naming ``moment=N`` gets it (with the other panels of that moment). The pool
is bounded by hard maxima here (never read from config): ``THREADS`` threads, ``WAITING`` jobs waiting; past that a
panel answers ``{"pending": true, "busy": true}`` and nothing is queued. Python threads cannot be killed: what is
promised is that a job waiting unasked for ``DROP`` seconds is dropped before it starts, and that no more than
``THREADS`` are ever running."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict

from ..spec.dashboards import MOST, names, plain, plain_panel, query
from ..spec.ir import Dashboard, Panel

LIMIT = 0.3           # s: one panel's own running time before it answers pending
BATCH = 0.4           # s: the whole batch's panels, after the snapshot: the rest answer pending
THREADS = 2           # the pool's threads, at most (a hard maximum: lesson 4)
WAITING = 2 * MOST    # jobs waiting, at most: a request's own panels (MOST at most) always fit on a pool
                      # holding one other dashboard's worth or less (an idle one among them): busy is overload
KEPT = 30.0           # s: a finished panel, and its moment's snapshot, kept for a poll naming that moment
DROP = 6.0            # s: a waiting job no poll has asked for in this long is dropped before it starts
MOMENTS = 8           # moments kept at once
JOBS_KEPT = 256       # finished panels kept at once (the oldest go first)
PATHS = {"goals": "loops", "chart": "series", "items": "items", "states": "items-flow", "cycle-time": "items-flow",
         "scope": "loop-scope", "items-graph": "items-graph", "timeline": "items-graph"}


def default(spec) -> Dashboard:
    """The model's own dashboard: each top system's ``show:`` measures (else its goals' measures) and its goals."""
    d = Dashboard("default", "The model's dashboard", "each top system's measures and its goals, as the model declares them")
    if spec is None:
        return d
    for s in spec.subsystems(None):
        goals = sorted(g for g, x in spec.goals.items() if s in spec.chain(x.system))
        refs = [str(r) for r in spec.show.get(s, [])] or list(dict.fromkeys(str(spec.goals[g].of) for g in goals))[:5]
        if refs:
            d.panels.append(Panel("chart", f"{s}: its measures", "m", params={"refs": refs}))
        if goals:
            d.panels.append(Panel("goals", f"{s}: its goals", "m", params={"goals": goals}))
    d.panels = d.panels[:MOST]
    return d


def find(p, name: str | None) -> Dashboard | None:
    spec = getattr(p.model, "spec", None)
    if name == "default":
        return default(spec)
    return (getattr(spec, "dashboards", None) or {}).get(name or "")


def listing(p) -> list[dict]:
    spec = getattr(p.model, "spec", None)
    ds = [default(spec), *(getattr(spec, "dashboards", None) or {}).values()]
    return [{"name": d.name, "title": d.title, "description": d.description, "panels": len(d.panels),
             "window": d.window, "declared": d.name != "default"} for d in ds]


class _Job:
    def __init__(self, run):
        self.run, self.asked, self.started, self.ended = run, time.monotonic(), None, None
        self.done = threading.Event()
        self.answer = self.error = None


class Board:
    """One server's moments and jobs, under one lock: every read-decide-write of them holds it throughout."""

    def __init__(self):
        self.lock = threading.Lock()
        self.moments: OrderedDict = OrderedDict()     # seq → (kept at, snapshot, window, at, model mtime)
        self.jobs: dict = {}                          # (seq, dashboard, index, declaration) → _Job
        self.waiting: list = []                       # keys, in turn
        self.threads = 0

    def moment(self, live, p, window: float, at: float | None, asked: int | None):
        """The snapshot of the moment asked for, while it is kept and the model is the same; else the moment's own."""
        now = time.monotonic()
        with self.lock:
            for k in [k for k, v in self.moments.items() if now - v[0] > KEPT]:
                del self.moments[k]
            ended = sorted((j.ended, k) for k, j in self.jobs.items() if j.ended is not None)
            for _, k in ended[:max(0, len(ended) - JOBS_KEPT)] + [x for x in ended[-JOBS_KEPT:] if now - x[0] > KEPT]:
                self.jobs.pop(k, None)
            got = self.moments.get(asked) if asked is not None else None
            if got is not None and got[2:] == (window, at, live.mtime):
                return got[1], asked
        snap, seq = live.moment(p, window, at)
        with self.lock:
            self.moments[seq] = (now, snap, window, at, live.mtime)
            self.moments.move_to_end(seq)
            while len(self.moments) > MOMENTS:
                self.moments.popitem(last=False)
        return snap, seq

    def submit(self, key, run) -> _Job | None:
        """The job for this key: the one already there (asked again), else a new one; None when the pool is full."""
        with self.lock:
            job = self.jobs.get(key)
            if job is not None:
                job.asked = time.monotonic()
                return job
            if len(self.waiting) >= WAITING:
                return None
            job = self.jobs[key] = _Job(run)
            self.waiting.append(key)
            if self.threads < THREADS:
                self.threads += 1
                threading.Thread(target=self._work, name="dashboard-panel", daemon=True).start()
            return job

    def _work(self) -> None:
        while True:
            with self.lock:
                while self.waiting:
                    key = self.waiting.pop(0)
                    job = self.jobs.get(key)
                    if job is None:
                        continue
                    if time.monotonic() - job.asked > DROP:          # no one asks for it any more: never started
                        del self.jobs[key]
                        job.error, job.ended = "dropped", time.monotonic()
                        job.done.set()
                        continue
                    job.started = time.monotonic()
                    break
                else:
                    self.threads -= 1
                    return
            try:
                job.answer = job.run()
            except Exception as e:                    # one panel that cannot be answered leaves the others
                job.error = f"{type(e).__name__}: {e}"
            finally:
                job.run, job.ended = None, time.monotonic()      # its snapshot let go: only the answer is kept
                job.done.set()


_BOARD_LOCK = threading.Lock()


def _board(live) -> Board:
    with _BOARD_LOCK:
        b = getattr(live, "_dashboards", None)
        if b is None:
            b = live._dashboards = Board()
        return b


def stamp(answer) -> str:
    return hashlib.blake2b(json.dumps(answer, sort_keys=True, default=str).encode(), digest_size=8).hexdigest()


def _run(live, p, panel: Panel, q: dict, snap):
    from .server import _answer
    if panel.panel == "note":
        return {"text": panel.params.get("text", "")}
    got = _answer(live, PATHS[panel.panel], {**q, **query({k: v for k, v in panel.params.items() if k != "goals"})}, p, snap)
    if panel.panel == "goals" and isinstance(got, dict) and panel.params.get("goals"):
        got = {g: got[g] for g in names(panel.params["goals"]) if g in got}
    return got


def answer(live, p, name: str | None, q: dict, wait: bool = False) -> dict | None:
    """The dashboard and each panel's answer, of one moment. ``wait``: every panel worked out here, however long
    (``ergostat snapshot``)."""
    from .server import _window
    d = find(p, name)
    if d is None:
        return None
    one = lambda k: (q.get(k) or [None])[0]       # noqa: E731
    window = _window(q) if one("since") else (d.window or _window({}))
    at = asked = None
    try:
        at = float(one("at")) if one("at") else None
    except ValueError:                             # as every answer reads it: not a time, now
        pass
    try:
        asked = int(one("moment")) if one("moment") else None
    except ValueError:                             # not a moment's number: a new moment
        pass
    board = _board(live)
    snap, seq = board.moment(live, p, window, at, asked)
    base = {"since": [str(window)], **({"at": [str(at)]} if at is not None else {})}
    have = (one("have") or "").split(",")
    began = time.monotonic()
    jobs: list = []
    for i, panel in enumerate(d.panels):
        run = lambda panel=panel: _run(live, p, panel, base, snap)   # noqa: E731
        key = (seq, d.name, i, json.dumps(plain_panel(panel), sort_keys=True, default=str))   # moments are shared
        jobs.append(run if wait else board.submit(key, run))
    out = []
    for i, (panel, job) in enumerate(zip(d.panels, jobs, strict=True)):
        decl = plain_panel(panel)
        if wait:
            try:
                got, err = job(), None
            except Exception as e:
                got, err = None, f"{type(e).__name__}: {e}"
        elif job is None:
            out.append({"panel": decl, "pending": True, "busy": True, "moment": seq})
            continue
        else:
            while not job.done.is_set():
                now = time.monotonic()
                left = min(began + BATCH - now, LIMIT - (now - job.started) if job.started else LIMIT)
                if left <= 0:
                    break
                job.done.wait(min(left, 0.02))
            if not job.done.is_set():
                out.append({"panel": decl, "pending": True, "moment": seq})
                continue
            got, err = job.answer, job.error
        if err is not None:
            out.append({"panel": decl, "error": err})
            continue
        s = stamp(got)
        out.append({"panel": decl, "stamp": s, **({"same": True} if i < len(have) and have[i] == s else {"answer": got})})
    head = plain(d) if d.name != "default" else {**plain(d), "declared": False}
    return {**{k: v for k, v in head.items() if k != "panels"}, "moment": seq, "at": snap.get("at"),
            "window": window, "panels": out}
