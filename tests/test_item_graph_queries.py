"""near, path and about over the items' relations and mentions (spec/itemgraph.py, SPEC §5a *Graph queries*), from
the command line and the API."""

from __future__ import annotations

import json
import textwrap
import urllib.error
import urllib.request

import pytest

from ergostat import goodmodel
from ergostat import model as mdl
from ergostat.cli import build, main
from ergostat.spec import itemgraph as ig
from ergostat.spec import items
from ergostat.store import Project
from tests.ports import free_port

MODEL = """
name: graphs
projections:
  epic:
    query: key.startswith('epic/')
    fields:
      state:
        values: [planned, shipped]
  ticket:
    query: key.startswith('ticket/')
    fields:
      state:
        values: [todo, done]
    events:
      ticket-done:
        when: type == 'ticket.done'
        '...': data
        state: set('done')
      other:
        when: true
        '...': data
    relations:
      blocked_by: ticket
      parent: epic
"""


def _repo(tmp_path):
    d = tmp_path / "graphs"
    d.mkdir(exist_ok=True)
    (d / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    return d, Project(mdl.load(d))


def _chain(tmp_path):
    """epic/1 ← ticket/1 → ticket/2 (ticket/1's parent is epic/1; it is blocked by ticket/2)."""
    d, p = _repo(tmp_path)
    p.events.add("epic.opened", item="epic/1")
    p.events.add("ticket.opened", item="ticket/2")
    p.events.add("ticket.opened", item="ticket/1", data={"parent": "epic/1", "blocked_by": "ticket/2"})
    return d, p


def _cli(d, capsys, *args):
    rc = main(["-C", str(d), "item", *args, "--json"])
    out = capsys.readouterr().out
    return rc, json.loads(out) if rc == 0 else None


def test_near_by_depth_both_directions(tmp_path):
    _, p = _chain(tmp_path)
    spec = p.model.spec
    one = ig.near(p.events, spec, "epic/1", "1")
    assert [(x["id"], x["distance"], x["via"]["relation"]) for x in one["items"]] == [("ticket/1", 1, "children")]
    two = ig.near(p.events, spec, "epic/1", "2")
    assert {(x["id"], x["distance"]) for x in two["items"]} == {("ticket/1", 1), ("ticket/2", 2)}
    assert two["items"][1]["via"] == {"from": "ticket/1", "relation": "blocked_by"} and not two["capped"]
    assert {(x["id"], x["via"]["relation"]) for x in ig.near(p.events, spec, "ticket/1")["items"]} == \
        {("epic/1", "parent"), ("ticket/2", "blocked_by")}
    for bad in ("5", "0", "x", "-1", ""):
        with pytest.raises(ig.Bad):
            ig.near(p.events, spec, "epic/1", bad)


def test_path_names_inverse_steps(tmp_path):
    _, p = _chain(tmp_path)
    got = ig.path(p.events, p.model.spec, "ticket/2", "epic/1")
    assert got["found"] and got["says"] == "found" and not got["capped"]
    assert got["steps"] == [{"from": "ticket/2", "relation": "blocks", "to": "ticket/1"},
                            {"from": "ticket/1", "relation": "parent", "to": "epic/1"}]
    with pytest.raises(ig.Bad):
        ig.path(p.events, p.model.spec, "ticket/2", None)


def test_path_is_the_shortest_of_two_routes(tmp_path):
    _, p = _repo(tmp_path)
    for i, by in (("d", None), ("c", "ticket/d"), ("b", "ticket/c"), ("a", ["ticket/b", "ticket/d"])):
        p.events.add("ticket.opened", item=f"ticket/{i}", data={"blocked_by": by} if by else {})
    assert [s["to"] for s in ig.path(p.events, p.model.spec, "ticket/a", "ticket/d")["steps"]] == ["ticket/d"]
    assert [s["to"] for s in ig.path(p.events, p.model.spec, "ticket/d", "ticket/a")["steps"]] == ["ticket/a"]


def test_path_capped_is_not_unconnected(tmp_path, monkeypatch):
    _, p = _repo(tmp_path)
    for i in range(8):
        p.events.add("ticket.opened", item=f"ticket/{i}", data={"blocked_by": f"ticket/{i + 1}"} if i < 7 else {})
    p.events.add("ticket.opened", item="ticket/alone")
    spec = p.model.spec
    assert ig.path(p.events, spec, "ticket/0", "ticket/7")["found"]
    monkeypatch.setattr(ig, "VISIT", 2)
    got = ig.path(p.events, spec, "ticket/0", "ticket/7")
    assert got["capped"] and not got["found"] and got["says"].startswith("none within the cap")
    monkeypatch.setattr(ig, "VISIT", 100)
    got = ig.path(p.events, spec, "ticket/0", "ticket/alone")
    assert not got["found"] and not got["capped"] and got["says"] == "no path"


def test_a_frontier_running_out_exactly_at_the_cap_is_no_path(tmp_path, monkeypatch):
    _, p = _repo(tmp_path)
    p.events.add("ticket.opened", item="ticket/1")
    p.events.add("ticket.opened", item="ticket/0", data={"blocked_by": "ticket/1"})
    p.events.add("ticket.opened", item="ticket/x")
    monkeypatch.setattr(ig, "VISIT", 2)               # ticket/0 and ticket/1: all there is to walk, and the cap
    got = ig.path(p.events, p.model.spec, "ticket/0", "ticket/x")
    assert got["says"] == "no path" and not got["capped"]


def test_near_and_about_report_capped(tmp_path, monkeypatch):
    _, p = _repo(tmp_path)
    p.events.add("epic.opened", item="epic/hub")
    for i in range(5):
        p.events.add("ticket.opened", item=f"ticket/{i}", data={"parent": "epic/hub", "note": "see epic/hub"})
    spec = p.model.spec
    assert not ig.near(p.events, spec, "epic/hub")["capped"] and not ig.about(p.events, spec, "epic/hub")["capped"]
    monkeypatch.setattr(ig, "VISIT", 3)
    near = ig.near(p.events, spec, "epic/hub")
    assert near["capped"] and len(near["items"]) == 2
    for i in range(5, 10):                            # mentions only, no link: about's scan meets the cap
        p.events.add("ticket.opened", item=f"ticket/m{i}", data={"note": "see epic/hub"})
    monkeypatch.setattr(ig, "VISIT", 7)
    assert ig.about(p.events, spec, "epic/hub")["capped"]


def test_about_capped_when_declared_and_inferred_together_pass_the_cap(tmp_path, monkeypatch):
    """Neither the declared links (3) nor the items the text index finds holding the id (3) pass the cap of 4 alone;
    together (6) they do. The declared items' parent lies past a lowered TEXT_MOST, so the index does not find them."""
    monkeypatch.setattr(items, "TEXT_MOST", 20)
    _, p = _repo(tmp_path)
    p.events.add("epic.opened", item="epic/hub")
    for i in range(3):
        p.events.add("ticket.opened", item=f"ticket/d{i}", data={"note": "x" * 40, "parent": "epic/hub"})
        p.events.add("ticket.opened", item=f"ticket/m{i}", data={"note": "see epic/hub"})
    monkeypatch.setattr(ig, "VISIT", 4)
    got = ig.about(p.events, p.model.spec, "epic/hub")
    assert got["capped"] and len(got["items"]) == 4
    monkeypatch.setattr(ig, "VISIT", 6)
    got = ig.about(p.events, p.model.spec, "epic/hub")
    assert not got["capped"] and len(got["items"]) == 6


def test_about_declared_and_inferred_whole_token(tmp_path):
    _, p = _chain(tmp_path)
    p.events.add("ticket.opened", item="ticket/3", data={"title": "split from ticket/2, see the log"})
    p.events.add("ticket.opened", item="ticket/12", data={"title": "nothing to do with ticket/22 or xticket/2"})
    p.events.add("ticket.opened", item="ticket/22", data={"title": "ticket/2/sub is another"})
    got = {x["id"]: x for x in ig.about(p.events, p.model.spec, "ticket/2")["items"]}
    assert got == {"ticket/1": {"id": "ticket/1", "how": "declared", "relation": "blocked_by"},
                   "ticket/3": {"id": "ticket/3", "how": "inferred", "field": "title"}}
    p.events.add("ticket.opened", item="ticket/4", data={"title": "ticket/12 again"})
    assert ig.about(p.events, p.model.spec, "ticket/1")["items"] == []       # ticket/12 is not ticket/1


def test_about_finds_a_mention_after_a_newline_or_tab_or_nested(tmp_path):
    _, p = _chain(tmp_path)
    p.events.add("ticket.opened", item="ticket/5", data={"description": "Blocked on:\nticket/2\nfor now"})
    p.events.add("ticket.opened", item="ticket/6", data={"notes": "see\tticket/2"})
    p.events.add("ticket.opened", item="ticket/7", data={"extra": {"links": ["a", "ticket/2"]}})
    p.events.add("ticket.opened", item="ticket/8", data={"description": "Blocked on:\nticket/22"})
    got = {x["id"]: x.get("field") for x in ig.about(p.events, p.model.spec, "ticket/2")["items"] if x["how"] == "inferred"}
    assert got == {"ticket/5": "description", "ticket/6": "notes", "ticket/7": "extra"}


def _get(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None


QUERIES = [(["ticket/1", "--near", "2"], "near=ticket/1&depth=2"), (["ticket/2", "--path", "epic/1"], "path=ticket/2&to=epic/1"),
           (["ticket/2", "--about"], "about=ticket/2")]


def test_unknown_id_is_an_error(tmp_path, capsys):
    from ergostat.web import serve
    d, p = _chain(tmp_path)
    for args in (["ticket/9", "--near"], ["ticket/9", "--path", "epic/1"], ["ticket/2", "--path", "ticket/9"],
                 ["ticket/9", "--about"]):
        assert main(["-C", str(d), "item", *args, "--json"]) == 2, args
        out, err = capsys.readouterr()
        assert out == "" and "no item 'ticket/9'" in err
    server, url = serve(p, free_port())
    try:
        for q in ("near=ticket/9", "path=ticket/9&to=epic/1", "path=ticket/2&to=ticket/9", "about=ticket/9"):
            assert _get(f"{url}/api/items-query?{q}")[0] == 404, q
        for q in ("near=ticket/1&depth=5", "near=ticket/1&depth=x", "path=ticket/1", "", "near=ticket/1&at=100",
                  "near=ticket/1&about=ticket/2", "path=ticket/2&to=epic/1&about=ticket/2"):
            assert _get(f"{url}/api/items-query?{q}")[0] == 400, q
    finally:
        server.shutdown()
        server.server_close()


def test_the_queries_with_at_or_a_bad_depth_are_refused(tmp_path, capsys):
    d, _ = _chain(tmp_path)
    for args, _q in QUERIES:
        assert main(["-C", str(d), "item", *args, "--at", "1m"]) == 2, args
        assert "never with --at" in capsys.readouterr().err
        assert main(["-C", str(d), "item", *args, "--history"]) == 2, args   # not silently dropped
        assert "or --history" in capsys.readouterr().err
    assert main(["-C", str(d), "item", "ticket/1", "--near", "5"]) == 2
    assert main(["-C", str(d), "item", "ticket/1", "--near", "two"]) == 2
    assert main(["-C", str(d), "item", "ticket/1", "--near", "--about"]) == 2


def test_queries_under_fallback_and_engine(tmp_path, capsys, monkeypatch):
    sub = next(a for a in build()._actions if a.dest == "topic").choices["item"]
    dests = {a.option_strings[0]: a.dest for a in sub._actions if a.option_strings}
    for flag in ("--near", "--path", "--about"):
        assert dests[flag] in goodmodel.READ_FLAGS and dests[flag] not in goodmodel.ACTS and dests[flag] != "about"
    d, p = _chain(tmp_path)
    assert goodmodel.keep(p) is None
    want = {tuple(a): _cli(d, capsys, *a)[1] for a, _q in QUERIES}
    from ergostat.cli import fast
    monkeypatch.setattr(fast, "call", lambda *a, **k: {"item": {"id": "plain"}})    # an engine answering item ID --json
    for a, _q in QUERIES:
        assert _cli(d, capsys, *a)[1] == want[tuple(a)], a
    with open(d / "ergostat.yaml", "a") as f:
        f.write("\nbroken: [\n")
    for a, _q in QUERIES:
        rc = main(["-C", str(d), "item", *a, "--json"])
        out, err = capsys.readouterr()
        assert rc == 0 and json.loads(out) == want[tuple(a)] and "using the last good model" in err, (a, err)


def test_cli_and_api_agree(tmp_path, capsys):
    from ergostat.web import serve
    d, p = _chain(tmp_path)
    p.events.add("ticket.opened", item="ticket/3", data={"title": "after ticket/2"})
    server, url = serve(p, free_port())
    try:
        for args, q in QUERIES:
            rc, cli = _cli(d, capsys, *args)
            st, api = _get(f"{url}/api/items-query?{q}")
            assert rc == 0 and st == 200 and cli == api and cli["items" if "items" in cli else "steps"], (args, cli)
    finally:
        server.shutdown()
        server.server_close()
