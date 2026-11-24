"""What a kind and an item touch (SPEC §5a, *What a kind touches*): ``spec/footprint.py``, ``/api/kinds/K`` and an
item's ``path``."""

from __future__ import annotations

import shutil
import textwrap
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import yaml

from ergostat import model as mdl
from ergostat.leases import ENDED, TAKEN
from ergostat.spec import load
from ergostat.spec.footprint import item_path, kind_footprint
from ergostat.store import Project
from ergostat.web.server import Live, api

ROOT = Path(__file__).resolve().parent.parent


def _project(tmp_path, example: str | None = None, text: str | None = None) -> Project:
    if example:
        shutil.copytree(ROOT / "examples" / example, tmp_path, dirs_exist_ok=True)
    else:
        (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    m = mdl.load(tmp_path)
    assert not [x for x in m.problems if x.level == "error"]
    return Project(m)


def test_ticket_factory_ticket_names_every_steps_stock_flow_and_taking_block():
    spec = load(ROOT / "examples" / "ticket-factory" / "ergostat.yaml")
    fp = kind_footprint(spec, "ticket")
    counted = {c["part"] for c in fp["counted_in"]}
    taken = {t["block"]: t for t in fp["taken_by"]}
    steps = sorted((ROOT / "examples" / "ticket-factory" / "steps").glob("*.yaml"))
    assert len(steps) == 12
    for f in steps:
        doc = yaml.safe_load(f.read_text())
        for kind in ("stocks", "flows"):
            for name, part in (doc.get(kind) or {}).items():
                if ((part.get("sensor") or {}).get("items")) == "ticket":
                    assert f"{kind[:-1]}.{name}" in counted, (f.name, name)
        for name, b in (doc.get("blocks") or {}).items():
            if (b.get("takes") or {}).get("kind") == "ticket":
                t = taken[name]
                assert t["pool"] == spec.blocks[name].pool and t["at"] == spec.blocks[name].takes.at, name
                assert set(t["out"]) == {str(r) for r in spec.blocks[name].targets() if r.kind == "flow"} and t["out"]
                assert t["ttl"] and t["attempts"] and t["rung"], name
    assert taken["work"]["attempts"] == 2 and taken["work"]["ttl"] == 1200   # its own lease: over the kind's
    worked = next(s for s in fp["definition"]["states"] if s["state"] == "worked")
    assert not worked["finished"] and fp["definition"]["fold"]["repings"] == "sum"
    assert fp["definition"]["on"]["ticket.work"] == "worked" and fp["definition"]["lease"]["attempts"] == 3
    assert {"leased", "dead"} <= {s["state"] for s in fp["definition"]["states"]}
    assert fp["goals"] and fp["loops"] and "why" not in fp


def _done_ticket(p: Project, id: str = "ticket/1") -> None:
    ev = p.events
    ev.add("ticket.planned", item=id, data={"title": "x"}, at=1000.0)
    ev.add(TAKEN, item=id, data={"run": "r1", "block": "developer", "fence": 1, "ttl": 300, "max": 3, "back": "todo"},
           at=1001.0)
    ev.add("ticket.started", item=id, causedby="r1", at=1002.0)
    ev.add("ticket.submitted", item=id, causedby="r1", at=1003.0)
    ev.add(ENDED, item=id, data={"run": "r1", "fence": 1, "how": "ack"}, at=1004.0)
    ev.add(TAKEN, item=id, data={"run": "r2", "block": "reviewer", "fence": 2, "ttl": 300, "max": 3, "back": "review"},
           at=1005.0)
    ev.add("ticket.approved", item=id, causedby="r2", at=1006.0)
    ev.add(ENDED, item=id, data={"run": "r2", "fence": 2, "how": "ack"}, at=1007.0)


def test_roadmap_kind_names_its_stocks_blocks_pools_goals_and_loops(tmp_path):
    p = _project(tmp_path, "roadmap")
    _done_ticket(p)
    p.events.add("ticket.planned", item="ticket/2", data={"title": "y"}, at=1010.0)
    p.events.add(TAKEN, item="ticket/2", data={"run": "r3", "block": "developer", "fence": 1, "ttl": 300, "max": 3,
                                                "back": "todo"}, at=1011.0)
    p.events.add("ticket.started", item="ticket/2", causedby="r3", at=1012.0)      # held, and moved on to doing
    fp = api(Live(p), "kinds/ticket", {})
    stocks = {c["name"]: c for c in fp["counted_in"] if c["kind"] == "stock"}
    assert {"todo", "in-progress", "in-review"} <= set(stocks) and stocks["in-review"]["states"] == ["review"]
    blocks = {t["block"]: t for t in fp["taken_by"]}
    assert blocks["developer"]["pool"] == 2 and blocks["reviewer"]["pool"] == 1
    assert blocks["developer"]["out"] == ["flow.started", "flow.submitted"] and blocks["reviewer"]["out"] == ["flow.finished"]
    assert blocks["developer"]["taken"] == 1 and blocks["reviewer"]["taken"] == 0     # a holder in any state
    assert blocks["developer"]["only_some"] and "unblocked" in blocks["developer"]["says"]
    goals = {g["goal"]: g for g in fp["goals"]}
    assert {"nothing-ready-waits", "in-review-clear"} <= set(goals) and goals["in-review-clear"]["hold"] == "<= 0"
    assert all("status" in g for g in fp["goals"])
    assert any("block.developer" in lp["through"] and lp["polarity"] for lp in fp["loops"])
    assert fp["now"] == {"done": 1, "doing": 1}
    done = next(s for s in fp["definition"]["states"] if s["state"] == "done")
    assert done["finished"] and fp["definition"]["finished_by"] == "declared"
    assert {"kind": "ticket", "relation": "blocked_by", "inverse": "blocks"} in fp["definition"]["named_by"]
    assert api(Live(p), "kinds/nope", {}) is None and api(Live(p), "kinds/ticket/x", {}) is None


def test_a_done_tickets_path_has_its_states_in_order_with_the_block_that_took_it(tmp_path):
    p = _project(tmp_path, "roadmap")
    _done_ticket(p)
    path = api(Live(p), "items/ticket%2F1", {})["path"]
    assert [s["state"] for s in path] == ["todo", "doing", "review", "done"]          # leased is not a step
    assert [s["block"] for s in path] == ["developer", "developer", "reviewer", "reviewer"]
    assert [s["how"] for s in path] == ["taken from here", "taken while here", "taken from here", "taken while here"]
    assert [s["attempts"] for s in path] == [1, 1, 1, 1] and [s["run"] for s in path] == ["r1", "r1", "r2", "r2"]
    assert [s["stock"] for s in path] == ["todo", "in-progress", "in-review", None]
    assert [s["flow"] for s in path] == ["planned", "started", "submitted", "finished"]
    assert path[0]["goal"] == "nothing-ready-waits" and path[2]["goal"] == "in-review-clear"
    assert path[0]["entered"] == 1000.0 and path[0]["left"] == 1001.0 and path[-1]["left"] is None
    assert "says" not in path[3]                                       # a flow counts it entering done


def test_a_nack_is_a_repeated_step_with_its_attempts(tmp_path):
    p = _project(tmp_path, "roadmap")
    ev = p.events
    ev.add("ticket.planned", item="ticket/1", at=1000.0)
    ev.add(TAKEN, item="ticket/1", data={"run": "r1", "block": "developer", "fence": 1, "ttl": 300, "max": 3}, at=1001.0)
    ev.add(ENDED, item="ticket/1", data={"run": "r1", "fence": 1, "how": "nack", "why": "x"}, at=1002.0)
    ev.add(TAKEN, item="ticket/1", data={"run": "r2", "block": "developer", "fence": 2, "ttl": 300, "max": 3}, at=1003.0)
    ev.add("ticket.started", item="ticket/1", causedby="r2", at=1004.0)
    path = api(Live(p), "items/ticket%2F1", {})["path"]
    assert [(s["state"], s["attempts"], s["run"]) for s in path] == [("todo", 1, "r1"), ("todo", 2, "r2"), ("doing", 2, "r2")]
    assert path[0]["ended"] == "nack" and path[1]["ended"] is None


def test_the_item_pages_where_it_went_joins_each_flow_to_the_block_whose_out_names_it(tmp_path):
    """What pageItem's 'Where it went' reads (pages.js whereView): /api/kinds/K's ``taken_by[].out`` named
    ``flow.X``, joined to a path step's ``flow``; a taken item's lease (holder, block, taken) for its current step."""
    p = _project(tmp_path, "roadmap")
    _done_ticket(p)
    p.events.add("ticket.planned", item="ticket/2", at=2000.0)
    p.events.add(TAKEN, item="ticket/2", data={"run": "r3", "block": "developer", "fence": 1, "ttl": 300, "max": 3,
                                               "back": "todo"}, at=2001.0)
    live = Live(p)
    fp = api(live, "kinds/ticket", {})
    assert "why" not in fp
    mover = {f.removeprefix("flow."): t["block"] for t in fp["taken_by"] for f in t["out"]}
    path = api(live, "items/ticket%2F1", {})["path"]
    assert [mover.get(s["flow"]) for s in path[1:]] == ["developer", "developer", "reviewer"]
    lease = api(live, "items/ticket%2F2", {})["fields"]["lease"]
    assert (lease["holder"], lease["block"], lease["taken"]) == ("r3", "developer", 2001.0)


UNCOUNTED = """
    name: t
    items:
      ticket: {id: ticket/*, states: [todo, done]}
      note: {id: note/*, states: [open, closed]}
    stocks:
      todo:
        sensor: {items: ticket, state: todo, every: 3s}
    flows:
      done:
        from: todo
    blocks:
      w:
        type: program
        run: "true"
        takes: {kind: ticket, at: todo, to: [done], where: {priority: high}}
        out: flow.done
    """


def test_a_kind_nothing_counts_is_empty_and_says_why_and_a_where_takes_only_some(tmp_path):
    p = _project(tmp_path, text=UNCOUNTED)
    spec = p.model.spec
    fp = kind_footprint(spec, "note")
    assert fp["counted_in"] == [] and fp["taken_by"] == [] and fp["goals"] == [] and fp["loops"] == []
    assert "no sensor counts items of kind note" in fp["why"] and fp["uncounted"] == ["open", "closed"]
    [t] = kind_footprint(spec, "ticket")["taken_by"]
    assert t["only_some"] and t["says"] == "takes only the items whose priority is high"
    assert sorted(kind_footprint(spec, "ticket")["uncounted"]) == ["dead", "done", "leased"]
    p.events.add("note.made", item="note/1", at=1000.0)
    [step] = item_path(spec, type("It", (), {"kind": "note", "moves": [{"time": 1.0, "from": None, "to": "open",
                                                                        "type": "note.made"}], "fields": {}})())
    assert step["stock"] is None and step["says"] == "nothing in the model counts note items in open"
    assert kind_footprint(spec, "nope") is None


def test_an_undeclared_kinds_finished_states_are_the_listings_inferred_from_the_record(tmp_path):
    from ergostat.spec import items as its
    p = _project(tmp_path, text=UNCOUNTED)
    assert not any(s["finished"] for s in kind_footprint(p.model.spec, "note")["definition"]["states"])
    p.events.add("note.made", item="note/1", at=1000.0)
    fp = api(Live(p), "kinds/note", {})
    f = its.finishes(p.events, p.model.spec, "note")
    assert fp["definition"]["finished_by"] == f["finished_from"] == "inferred"
    assert [s["state"] for s in fp["definition"]["states"] if s["finished"]] == f["finished"] == ["closed"]


def test_the_footprint_is_kept_per_model_and_each_caller_has_its_own(tmp_path):
    p = _project(tmp_path, text=UNCOUNTED)
    spec = p.model.spec
    a = kind_footprint(spec, "ticket")
    a["taken_by"].clear()
    assert kind_footprint(spec, "ticket")["taken_by"]
    assert ("footprint", "ticket") in spec.lookups().kept


def test_get_api_kinds_answers_and_404s_for_an_unknown_kind(tmp_path):
    from http.server import ThreadingHTTPServer

    from ergostat.web.server import handler
    p = _project(tmp_path, "roadmap")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler(p))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/api/kinds/"
    try:
        with urllib.request.urlopen(url + "ticket", timeout=10) as r:
            assert r.status == 200
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(url + "nope", timeout=10)
        assert e.value.code == 404
    finally:
        srv.shutdown()
        srv.server_close()


@pytest.mark.serial
def test_api_kinds_answers_within_300ms_on_a_few_hundred_tickets(tmp_path):
    p = _project(tmp_path, "roadmap")
    for i in range(300):
        _done_ticket(p, f"ticket/{i}")
    live = Live(p)
    api(live, "kinds/ticket", {})                     # the first: the snapshot and the footprint worked out
    t = time.perf_counter()
    api(live, "kinds/ticket", {})
    assert time.perf_counter() - t < 0.3
