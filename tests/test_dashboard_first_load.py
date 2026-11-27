"""Acceptance (dev/records/dashboard-first-load-fast.md): a cold server's first answers to the default Dashboard, on the
factory-size record (``factory_state``), held under a stated budget, every request's and every query's time written
to the output, and the answers the same as before the change.

The page's first load is replayed over HTTP as the page sends it on this record at 1440x900 (``FIRST``, ``REST``: the
default's queries, the panels above the fold first; ``test_the_page_sends_what_the_replay_sends`` holds the page to
them where Playwright is installed) against ``ergostat web`` started cold on the record (no answer kept, no estimate
worked out): the header's status of the hour, the fields, the kinds'
listing, then the first batch beside the header's status of the day (the page asks them at once), then the rest at
the first's ``until``. The server's own start (its plain item index folded, about 11 s here) is before the page and
not in the budget."""

from __future__ import annotations

import base64
import contextlib
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

from tests.conftest import clean_env
from tests.ports import free_port

pytestmark = [pytest.mark.slow, pytest.mark.serial]     # (timed: nothing else runs beside it)

FIRST_BUDGET = 3.0      # s: the panels above the fold answered, from when they are asked (0.8 s measured; 10.4 s before)
LOAD_BUDGET = 6.0       # s: from the page's first request to that answer (2.1 s measured; 11.8 s before)
DAY_BUDGET = 6.0        # s: the header's status of the day, asked beside it (2.6 s measured; 16.7 s before)
WINDOW, POINTS = 86400, 120

GAP = ["new", "leased", "ready", "building", "review", "approved"]
_rate = {"agg": "count", "transform": "rate", "rate_per": "hour"}
_last = {"group_by": "projection", "agg": "last", "transform": "none"}
_p50 = {"agg": "p50", "transform": "none"}


def _arrivals(k):
    return {"source": "moves", "projection": k, "measure": "entries", "first_only": True, "state": ["new"], **_rate}


def _done(k):
    return {"source": "moves", "projection": k, "measure": "entries", "state": ["done", "dropped"], **_rate}


def _count(k, states):
    return {"source": "counts", "projection": k, "state": states, **_last}


def _stay(k, state, **more):
    return {"source": "moves", "projection": k, "measure": "time_in_state", "state": [state], **_p50, **more}


FIRST = [_count("gap", GAP), _done("gap"), _stay("gap", "leased", bucket="whole"), _arrivals("gap"),
         _count("gap", [s for s in GAP if s != "leased"]), _count("gap", ["leased"]), _count("gap", ["parked", "dead"]),
         _stay("gap", "leased"), _stay("gap", "building"), _stay("gap", "approved"),
         {**_count("gap", GAP), "group_by": "state"}, {**_stay("gap", "leased"), "agg": "ohlc"},
         {**_count("gap", ["leased"]), "x": {"type": "query", "query": "q4"}}]
REST = [q for k, states in (("review", ["new", "reading", "judged"]), ("lesson", ["new", "proposed", "applying"]))
        for q in (_arrivals(k), _done(k), _count(k, states), _count(k, ["leased"]), _count(k, ["dead"]),
                  *(_stay(k, s) for s in (["leased", "reading", "judged"] if k == "review" else ["new", "leased", "proposed"])))]


def whole_bucket(since: float, until: float) -> float | None:
    """dashboard.js's dashWholeBucket: one bucket holding the whole window."""
    step = -(-(until - since) // 60) * 60
    while step <= 400 * 86400:
        if since // step == (until + 120) // step:
            return step
        step += 60
    return None


def named(queries, prefix: str = "q") -> list[dict]:
    """Each query with its id, numbered in turn as panels.js numbers a request's queries."""
    return [{**q, "id": f"{prefix}{i}"} for i, q in enumerate(queries)]


def batch(queries, until: float | None, now: float, prefix: str = "q") -> dict:
    end = until if until is not None else now
    out = [{**q, "bucket": whole_bucket(end - WINDOW, end)} if q.get("bucket") == "whole" else q for q in named(queries, prefix)]
    return {"since": WINDOW, "until": until, "points": POINTS, "queries": out}


def enc(d: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")


STARTED: list[float] = []      # how long each cold server took to answer (said, not budgeted)


@contextlib.contextmanager
def cold_server(factory_state):
    """``ergostat web`` on the record, started now; its URL once it answers anything."""
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(factory_state.model), "web", "--port", str(port)],
                            env=clean_env(ERGOSTAT_HOME=str(factory_state.home)), stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)
    url, began = f"http://127.0.0.1:{port}", time.monotonic()
    try:
        for _ in range(1200):                       # (a minute at most: it folds the record's plain index first)
            try:
                urllib.request.urlopen(url + "/api/projects", timeout=2).read()
                break
            except urllib.error.HTTPError:
                break
            except OSError:
                assert proc.poll() is None, "ergostat web stopped"
                time.sleep(0.05)
        else:
            pytest.fail("ergostat web never answered")
        STARTED.append(time.monotonic() - began)
        yield url
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, 15)                 # (its own group: what it started in it stops with it)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, 9)
            proc.wait(timeout=10)


class Timed:
    def __init__(self, url: str):
        self.url, self.rows, self.began = url, [], time.monotonic()

    def get(self, name: str, path: str):
        t = time.monotonic()
        with urllib.request.urlopen(self.url + path, timeout=300) as r:
            assert r.status == 200, (name, r.status)
            got = json.loads(r.read())
        self.rows.append((name, t - self.began, time.monotonic() - t))
        return got


def said(text: str, capsys) -> None:
    with capsys.disabled():
        print(text, flush=True)


def test_a_cold_servers_first_dashboard_answer_is_within_budget(factory_state, capsys, monkeypatch):
    with cold_server(factory_state) as url:
        page = Timed(url)
        page.get("status, the hour (the header)", "/api/status?since=1h")
        fields = page.get("query/fields", "/api/query/fields")
        page.get("items, the kinds (eta=0)", "/api/items?since=1h&n=1&eta=0")
        now = time.time() // 5 * 5
        first, day = {}, {}
        header = threading.Thread(target=lambda: day.update(page.get("status, the day (the header)", "/api/status?since=1d")))
        header.start()
        asked = time.monotonic()
        first.update(page.get(f"query, the {len(FIRST)} above the fold", "/api/query?q=" + enc(batch(FIRST, None, now))))
        first_took, load_took = time.monotonic() - asked, time.monotonic() - page.began
        until = first["until"]
        rest = page.get(f"query, the other {len(REST)}", "/api/query?q=" + enc(batch(REST, until, now)))
        header.join(300)
        day_took = next(t for n, _, t in page.rows if n.startswith("status, the day"))
        whole = Timed(url).get("all at once", "/api/query?q=" + enc({**batch(FIRST, until, now),
                                                                    "queries": batch(FIRST, until, now)["queries"]
                                                                    + batch(REST, until, now, "r")["queries"]}))
    alone = []                                      # each query by itself afterwards (the index folded, nothing kept)
    monkeypatch.setenv("ERGOSTAT_HOME", str(factory_state.home))
    from ergostat.query import engine
    from ergostat.web.server import Live
    p = factory_state.project()
    for prefix, qs in (("q", FIRST), ("r", REST)):
        for q in batch(qs, until, now, prefix)["queries"]:
            live = Live(p)
            t = time.monotonic()
            engine.answer(live, live.p, enc({"since": WINDOW, "until": until, "points": POINTS,
                                             "queries": [x for x in batch(qs, until, now, prefix)["queries"]
                                                         if x["id"] in (q["id"], (q.get("x") or {}).get("query"))]}))
            alone.append((q["id"], time.monotonic() - t, {k: v for k, v in q.items() if k != "id"}))
    said(f"\nergostat web answered {STARTED[-1]:.2f} s after it was started (not in the budget)"
         "\ncold first load of the default dashboard (factory_state), each request: when asked, how long\n"
         + "\n".join(f"  {at:6.2f} s  {took:6.2f} s  {n}" for n, at, took in page.rows)
         + "\neach query alone afterwards:\n" + "\n".join(f"  {i:>4} {t:6.3f} s  {json.dumps(q)}" for i, t, q in alone), capsys)

    assert fields["sources"]["moves"]["projections"]["gap"]["queue"]
    assert first_took <= FIRST_BUDGET and load_took <= LOAD_BUDGET, (first_took, load_took, page.rows)
    assert day_took <= DAY_BUDGET and day.get("loops"), (day_took, page.rows)
    answered = first["results"] + rest["results"]
    assert len(answered) == len(FIRST) + len(REST) and not [r for r in answered if r.get("error")], answered
    # the same answers as one request of them all at that moment (the page asked them in one before), but for the
    # warning that a request's answers differ in step (G4, query/sampling.py), which compares one request's answers
    def plain(r):
        v = r["meta"]["verdict"]
        kept = [x for x in v["reasons"] if x["code"] != "mixed-windows"]
        return {**{k: x for k, x in r.items() if k != "id"}, "meta": {**r["meta"], "verdict": kept}}
    assert [plain(r) for r in answered] == [plain(r) for r in whole["results"]]


def test_the_queues_the_fields_give_are_the_graphs(factory_state, monkeypatch):
    """The default dashboard read each kind's ``queue`` from ``/api/items-graph``; it reads it from the fields now."""
    monkeypatch.setenv("ERGOSTAT_HOME", str(factory_state.home))
    from ergostat.precedence import Kinds
    from ergostat.query.fields import _read
    from ergostat.spec.itemindex import index_for
    p = factory_state.project()
    spec = p.model.spec
    moves = _read(p)["sources"]["moves"]["projections"]
    graph = Kinds(spec, index_for(p.events, spec, False))
    assert {k: moves[k]["queue"] for k in spec.items} == {k: graph[k]["queue"] for k in spec.items}
    assert any(len(graph[k]["queue"]) > 1 for k in spec.items)          # (one a block takes from beyond its first)


def test_the_listing_with_eta_0_is_the_listing_without_its_estimates(factory_state, monkeypatch):
    """``/api/items?eta=0`` (the default dashboard's) answers what the listing answers, its items' estimates left out,
    and starts no estimate."""
    monkeypatch.setenv("ERGOSTAT_HOME", str(factory_state.home))
    from ergostat.web import eta_api
    from ergostat.web.server import Live, _answer
    live = Live(factory_state.project())
    at = str(time.time())                           # (one moment for both: the snapshot is the same)
    started = []
    monkeypatch.setattr(eta_api, "estimates", lambda *a, **k: started.append(a) or None)
    without = _answer(live, "items", {"since": ["1h"], "n": ["1"], "eta": ["0"], "at": [at]})
    assert started == []
    plain = _answer(live, "items", {"since": ["1h"], "n": ["1"], "at": [at]})
    assert len(started) == 1 and without == plain and without["projections"]
