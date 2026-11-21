"""A snapshot holds the item sets its own answers link to (snapshot_sets.py): each part's side-panel set and each
process map node's and line's, both as the side panel lists it and as the Items page shows it, keyed as the page's
``snapKey`` keys them, up to a hard maximum."""

import json
import re
import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat.spec.item_sets import BadSet
from ergostat.store import Project

MODEL = """
name: sets
items:
  epic:
    id: epic/*
    states: [planned, underway]
    on: {epic.started: underway}
    show: [title]
  ticket:
    id: ticket/*
    states: [new, awaiting, done]
    on: {ticket.asked: awaiting, ticket.done: done}
    show: [title, area]
    relations: {parent: epic}
stocks:
  awaiting:
    unit: tickets
    sensor: {items: ticket, state: awaiting, where: {area: [flags, billing]}}
  awaiting-too:
    unit: tickets
    sensor: {items: ticket, state: awaiting, where: {area: [flags, billing]}}
flows:
  completed:
    from: awaiting
    sensor: {items: ticket, entering: done, over: 1h}
"""


def sets_project(d):
    """Two epics, one started; six tickets (two about flags, two about billing, two about docs), each under an epic,
    the first two caused by its start, all asked for, two done in the last hour."""
    (d / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    p = Project(mdl.load(d))
    t = time.time() - 1800
    p.events.add("epic.planned", item="epic/e1", data={"title": "first"}, at=t)
    started = p.events.add("epic.started", item="epic/e1", at=t + 10)
    for i in range(1, 7):
        area = ("flags", "billing", "docs")[(i - 1) // 2]
        p.events.add("ticket.opened", item=f"ticket/{i}", data={"title": f"t{i}", "area": area, "parent": "epic/e1"},
                     causedby=started["id"] if i <= 2 else None, at=t + 20 + i)
        p.events.add("ticket.asked", item=f"ticket/{i}", at=t + 100 + i)
    for i in (1, 3):
        p.events.add("ticket.done", item=f"ticket/{i}", at=t + 600 + i)
    return p


def held(p) -> dict:
    from ergostat.web.snapshot import build
    html = build(p)
    return json.loads(re.search(r"window\.SNAPSHOT = (.*?);</script>", html, re.S).group(1))["data"]


def snap_key(params: dict) -> str:
    """The page's ``snapKey`` (util.js), written out: sorted, a list as JavaScript's String says it (a,b)."""
    kept = sorted((k, ",".join(v) if isinstance(v, list) else str(v)) for k, v in params.items())
    return "items?" + "&".join(f"{k}={v}" for k, v in kept)


def live_answer(p, params: dict):
    from ergostat.web.server import Live, api
    q = {"since": ["1h"], **{k: v if isinstance(v, list) else [v] for k, v in params.items()}}
    return json.loads(json.dumps(api(Live(p), "items", q), default=str))


PANEL = {"alone": "1", "n": "10", "shown": "1"}


@pytest.fixture
def p(tmp_path):
    return sets_project(tmp_path)


def test_each_parts_set_is_held_as_the_page_asks(p):
    data = held(p)
    where = {"kind": "ticket", "state": "awaiting", "where": ["area:flags", "area:billing"]}
    panel = "items?alone=1&kind=ticket&n=10&shown=1&state=awaiting&where=area:flags,area:billing"
    page = "items?kind=ticket&state=awaiting&where=area:flags,area:billing"
    assert panel in data and page in data, sorted(k for k in data if k.startswith("items?"))
    assert data[panel] == live_answer(p, {**where, **PANEL}) and data[panel]["total"] == 2     # tickets 2 and 4
    assert data[page] == live_answer(p, where) and data[page]["total"] == 2
    s = data["part/disturbance/completed"]["items"]["set"]       # a flow no valve opens: a disturbance
    a, b = s["moved_since"][0], s["moved_until"][0]
    moved = {"kind": "ticket", "moved": ">done", "moved_since": a, "moved_until": b}
    for k, q in ((f"items?alone=1&kind=ticket&moved=>done&moved_since={a}&moved_until={b}&n=10&shown=1", {**moved, **PANEL}),
                 (f"items?kind=ticket&moved=>done&moved_since={a}&moved_until={b}", moved)):
        assert k in data, k
        assert data[k] == live_answer(p, q) and data[k]["total"] == 2


def test_each_process_map_set_is_held(p):
    data = held(p)
    g = data["graph?view=process"]
    stamp = lambda t: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(t)))   # noqa: E731  as pmStamp
    span = {"by": g["by"], "moved_since": stamp(g["since"]), "moved_until": stamp(g["until"])}
    node = {n["id"]: n for n in g["nodes"]}
    want = [{"kind": n["itemKind"], "through": n["activity"]} for n in g["nodes"] if n["kind"] != "schedule"]
    for e in g["edges"]:
        a, b = node[e["source"]], node[e["target"]]
        want.append({"kind": a["itemKind"], "through": a["activity"]} if e["kind"] == "related" else
                    {"kind": b["itemKind"], "caused": [f"{a['itemKind']}:{a['activity']}>{b['activity']}"]}
                    if e["kind"] == "caused" else {"kind": e["itemKind"], "followed": f"{a['activity']}>{b['activity']}"})
    assert {e["kind"] for e in g["edges"]} == {"follows", "caused", "related"}, g["edges"]
    assert any("caused" in w for w in want) and any("followed" in w for w in want)
    for w in want:
        for q in ({**w, **span}, {**w, **span, **PANEL}):
            k = snap_key(q)
            assert k in data, k
            assert data[k] == live_answer(p, q), k
            assert data[k]["total"] >= 1, k


def test_the_sets_held_stop_at_the_maximum(p, monkeypatch):
    from ergostat.web import snapshot, snapshot_sets
    from ergostat.web.server import api
    monkeypatch.setattr(snapshot_sets, "MOST", 3)
    asked: list[dict] = []

    def counting(live, path, q):
        if path == "items" and q.get("kind"):
            asked.append(q)
        return api(live, path, q)
    monkeypatch.setattr(snapshot, "api", counting)
    data = held(p)
    g = data["graph?view=process"]
    n0 = g["nodes"][0]
    span = {"by": g["by"], "moved_since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(g["since"]))),
            "moved_until": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(g["until"])))}
    s = data["part/disturbance/completed"]["items"]["set"]
    first = [{"kind": "ticket", "state": "awaiting", "where": ["area:flags", "area:billing"]},     # awaiting-too: the same,
             {"kind": "ticket", "moved": ">done", "moved_since": s["moved_since"][0], "moved_until": s["moved_until"][0]},
             {"kind": n0["itemKind"], "through": n0["activity"], **span}]                       # held and counted once
    want = {snap_key(q) for f in first for q in (f, {**f, **PANEL})}
    got = {k for k in data if k.startswith("items?")}
    assert got == want, sorted(got ^ want)
    assert len(asked) == 6, asked


def test_a_set_that_is_not_one_is_left_out_and_any_other_failure_stops_the_snapshot(p, monkeypatch):
    from ergostat.web import snapshot
    from ergostat.web.server import api

    def bad(live, path, q):
        if path == "items" and q.get("moved"):
            raise BadSet("not one")
        return api(live, path, q)
    monkeypatch.setattr(snapshot, "api", bad)
    data = held(p)
    assert not [k for k in data if k.startswith("items?") and "moved=" in k]
    assert "items?kind=ticket&state=awaiting&where=area:flags,area:billing" in data      # the rest held

    def broken(live, path, q):
        if path == "items" and q.get("kind"):
            raise OSError("the index cannot be read")
        return api(live, path, q)
    monkeypatch.setattr(snapshot, "api", broken)
    with pytest.raises(OSError):
        held(p)
