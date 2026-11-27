"""A dashboard's address is its name (SPEC §4f): one named as ergostat's own page or as a kind is drawn there (a kind's
binds ``$kind``); ``nav:`` puts it in the header; ``page: agent|item|kind`` draws it for every one, its panels'
``$agent``, ``$item`` or ``$kind`` taken from the address. Checked, listed (/api/routes too), answered bound, and kept
by Keep with them; a kind named as the server's address or one of ergostat's pages is a finding."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.cli import main
from ergostat.numbers import display
from ergostat.numbers import proposals as pr
from ergostat.spec import read
from ergostat.store import Project
from ergostat.web import dashboard_api

ROOT = Path(__file__).resolve().parent.parent

BOARD = """
dashboards:
  crew:
    title: The crew
    nav: true
    panels:
      - {panel: agents, size: full}
  watch:
    title: Watch
    nav: On watch
    panels:
      - {panel: goals, columns: [goal, status, value], size: full}
  goals:
    title: My goals
    panels:
      - {panel: quiet-systems, quiet: true}
      - {panel: goals, columns: all, fit: true}
  one-agent:
    title: One agent
    page: agent
    panels:
      - {panel: agent-what, agent: $agent}
      - {panel: agent-runs, agent: $agent}
  ticket:
    title: Tickets, my way
    panels:
      - {panel: projection-now, projection: $projection}
projections:
  ticket:
    id: ticket/*
    states: [opened, done]
    on: {ticket.opened: opened, ticket.done: done}
"""


def write(tmp_path: Path, board: str = BOARD) -> Path:
    d = tmp_path / "first-loop"
    shutil.copytree(ROOT / "examples" / "first-loop", d, ignore=shutil.ignore_patterns("run", "__pycache__", "inbox"))
    f = d / "ergostat.yaml"
    f.write_text(f.read_text() + board)
    return d


def errors(tmp_path: Path, board: str):
    _, problems = read(write(tmp_path, board) / "ergostat.yaml")
    return [p for p in problems if p.level == "error"]


def test_nav_and_page_are_checked_kept_and_listed(tmp_path, capsys):
    d = write(tmp_path)
    assert main(["-C", str(d), "check"]) == 0, capsys.readouterr().out
    spec, _ = read(d / "ergostat.yaml")
    ds = spec.dashboards
    assert [(ds[n].nav, ds[n].page) for n in ("crew", "watch", "goals", "one-agent", "ticket")] == [
        ("", None), ("On watch", None), (None, None), (None, "agent"), (None, None)]
    assert ds["watch"].panels[0].params == {"columns": ["goal", "status", "value"]}
    assert ds["goals"].panels[0].params == {"quiet": True}
    assert ds["one-agent"].panels[0].params == {"agent": "$agent"}
    assert ds["ticket"].panels[0].params == {"projection": "$projection"}   # named as a projection: its page, $projection it
    p = Project(mdl.load(d))
    listed = {x["name"]: (x["nav"], x["page"]) for x in dashboard_api.listing(p)}
    assert listed == {"default": (None, None), "crew": ("", None), "watch": ("On watch", None),
                      "goals": (None, None), "one-agent": (None, "agent"), "ticket": (None, None)}
    from ergostat.web import server
    routes = server.api(server.Live(p), "routes", {})
    assert [x for x in routes["projections"] if x["declared"]] == [{"name": "ticket", "id": "ticket/*", "declared": True, "group": None}]
    assert {"name": "session", "id": "session/*", "declared": False, "group": None} in routes["projections"]      # ergostat's own: linked
    assert routes["reserved"] == ["api", "static", "remote"]
    assert "goals" in routes["builtin"] and [x["name"] for x in routes["dashboards"]] == list(listed)


@pytest.mark.parametrize("old, new, code", [
    ("    nav: true\n", "    nav: 3\n", "bad-dashboard"),
    ("    nav: On watch\n", "    nav: " + "x" * 41 + "\n", "bad-dashboard"),
    ("    title: My goals\n", "    title: My goals\n    page: goals\n", "bad-dashboard"),   # named goals instead
    ("    title: My goals\n", "    title: My goals\n    page: [kind]\n", "bad-dashboard"),
    ("    page: agent\n", "    page: agent\n    nav: true\n", "bad-dashboard"),
    ("    nav: true\n", "    page: agent\n", "defined-twice"),           # crew first: one-agent is the second
    ("  crew:\n", "  api:\n", "bad-name"),
    ("      - {panel: projection-now, projection: $projection}", "      - {panel: projection-now, projection: $item}", "bad-dashboard"),
    ("    page: agent\n", "    page: item\n", "bad-dashboard"),        # $agent: not the item page's word
    ("    page: agent\n", "", "bad-dashboard"),                     # $agent taken from no address
    ("columns: [goal, status, value]", "columns: [goal, nope]", "bad-dashboard"),
    ("{panel: quiet-systems, quiet: true}", "{panel: quiet-systems, quiet: maybe}", "bad-dashboard"),
])
def test_a_wrong_nav_page_or_binding_is_an_error(tmp_path, old, new, code):
    board = BOARD.replace(old, new, 1)
    assert board != BOARD
    got = errors(tmp_path, board)
    assert got and {p.code for p in got} == {code}, got


def test_a_dashboard_in_a_pages_place_is_answered_bound_to_the_address(tmp_path, monkeypatch):
    from ergostat.web import server
    monkeypatch.setattr(server, "_estimates", lambda *a, **k: None)
    p = Project(mdl.load(write(tmp_path)))
    now = time.time()
    p.events.add("agent.ran", item="worker", data={"seconds": 1, "note": "5 handled"}, at=now - 60)
    live = server.Live(p)
    plain = server.api(live, "dashboard/one-agent", {"plain": ["1"], "agent": ["worker"]})
    assert (plain["page"], [x["agent"] for x in plain["panels"]]) == ("agent", ["worker", "worker"])
    assert server.api(live, "dashboard/one-agent", {"plain": ["1"]})["panels"][0]["agent"] == "$agent"
    at = str(now - 5)
    got = server.api(live, "dashboard/one-agent", {"agent": ["worker"], "at": [at]})
    worker = server.api(live, "agents/worker", {"since": [str(got["window"])], "at": [at]})
    assert [x["answer"] for x in got["panels"]] == [worker, worker]
    goals = server.api(live, "dashboard/watch", {"at": [at]})["panels"][0]
    assert goals["panel"]["columns"] == ["goal", "status", "value"] and isinstance(goals["answer"], dict)


def test_keep_writes_nav_and_page_and_keeps_them_in_place(tmp_path):
    d = write(tmp_path, "")
    p = Project(mdl.load(d))
    draft = {"title": "Crew Board", "nav": "Crew", "panels": [{"panel": "agents", "size": "full", "fit": True}]}
    x = display.keep(p, draft)
    pr.accept(p, x["id"], {"at": time.time(), "window": 3600.0}, by="owner")
    assert main(["-C", str(d), "check"]) == 0
    spec = Project(mdl.load(d)).model.spec
    assert (spec.dashboards["crew-board"].nav, spec.dashboards["crew-board"].page) == ("Crew", None)
    again = display.keep(Project(mdl.load(d)), {"title": "Crew Board", "name": "crew-board", "page": "agent",
                                                "panels": [{"panel": "agent-runs", "agent": "$agent"}]})
    pr.accept(Project(mdl.load(d)), again["id"], {"at": time.time(), "window": 3600.0}, by="owner")
    spec = Project(mdl.load(d)).model.spec
    assert (spec.dashboards["crew-board"].nav, spec.dashboards["crew-board"].page) == (None, "agent")
    assert (d / "ergostat.yaml").read_text().count("crew-board:") == 1


@pytest.mark.parametrize("kind, code", [("api", "unrouted-projection"), ("record", "projection-takes-page")])
def test_a_kind_named_as_the_servers_address_or_ergostats_page_is_a_finding(tmp_path, kind, code):
    d = write(tmp_path, BOARD.replace("projections:\n", f"projections:\n  {kind}:\n    id: {kind}/*\n    states: [a]\n"))
    _, problems = read(d / "ergostat.yaml")
    assert [(x.level, x.code) for x in problems if x.about == f"projections.{kind}" and "projection" in x.code] == [("finding", code)]
    assert not [x for x in problems if x.level == "error"]


def test_a_projections_group_is_checked_and_listed(tmp_path):
    """`group:` puts a projection in the nav bar's menu of that name (with the others of its group); a bad name is an
    error."""
    p = write(tmp_path)
    f = p / "ergostat.yaml"
    f.write_text(f.read_text().replace("    on: {ticket.opened: opened, ticket.done: done}",
                                       "    on: {ticket.opened: opened, ticket.done: done}\n    group: things"))
    from ergostat.web import server
    routes = server.api(server.Live(Project(mdl.load(p))), "routes", {})
    assert [x["group"] for x in routes["projections"] if x["name"] == "ticket"] == ["things"]
    f.write_text(f.read_text().replace("group: things", "group: Things!"))
    _, problems = read(f)
    assert [x.code for x in problems if x.level == "error"] == ["bad-group"]
