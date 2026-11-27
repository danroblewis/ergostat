"""Dashboards edited in place (SPEC §4f, *Editing in place*; §5a, a projection's ``dashboards:``): a projection's own
list and show dashboards, checked like ``dashboards:`` entries, display only, served bound to the projection; Save
writes each edit where it belongs (a projection's in the file the projection is defined in) and accepts it at once;
Reset takes it out again."""

from __future__ import annotations

import time

import pytest

from ergostat import model as mdl
from ergostat.numbers import display
from ergostat.numbers import proposals as pr
from ergostat.spec import read
from ergostat.spec.ir import MODEL_CHANGE
from ergostat.store import Project
from ergostat.web import dashboard_api
from tests.test_dashboards import MODEL, project, write

OWN = MODEL.replace("""    otherwise: rest
""", """    otherwise: rest
    dashboards:
      list:
        title: Tickets, my way
        panels:
          - {panel: projection-now, projection: $projection, size: full}
          - {panel: item-list, projection: $projection, size: full}
      show:
        panels:
          - {panel: item-fields, item: $item, size: full}
          - {panel: projection-model, projection: $projection}
""")
SUB = """\
defaults:
  system: desk
projections:
  bug:
    match:
      key: bug/*
    states: [open, fixed]
    events:
      bug.fixed:
        state: set('fixed')
    otherwise: rest
"""


def snap() -> dict:
    return {"at": time.time(), "window": 3600.0}


def errors(problems) -> list[str]:
    return [str(p) for p in problems if p.level == "error"]


def test_a_projection_s_own_dashboards_are_checked_and_bound_to_it(tmp_path):
    spec, problems = read(write(tmp_path, OWN) / "ergostat.yaml")
    assert not errors(problems)
    ls, sh = spec.dashboards["ticket.list"], spec.dashboards["ticket.show"]
    assert (ls.projection, ls.role, ls.title, ls.nav, ls.page) == ("ticket", "list", "Tickets, my way", None, None)
    assert (sh.projection, sh.role) == ("ticket", "show")
    assert sh.panels[0].params == {"item": "$item"} and sh.panels[1].params == {"projection": "$projection"}
    bad = OWN.replace("item: $item, size: full", "item: $agent, size: full").replace(
        "      list:\n", "      lists:\n      list:\n")
    _, problems = read(write(tmp_path, bad) / "ergostat.yaml")
    said = " ".join(errors(problems))
    assert "'$agent' is taken from no address" in said and "unknown key 'lists'" in said
    wrong = OWN.replace("{panel: projection-now, projection: $projection", "{panel: projection-now, projection: epic")
    _, problems = read(write(tmp_path, wrong) / "ergostat.yaml")
    assert "'epic' is not a projection" in " ".join(errors(problems))


def test_a_projection_s_own_dashboards_are_display_only(tmp_path):
    from ergostat.numbers import version as ver
    from ergostat.numbers.improve import kind_of
    from ergostat.spec.itemindex import kinds_key
    a, _ = read(write(tmp_path) / "ergostat.yaml")
    b, _ = read(write(tmp_path, OWN) / "ergostat.yaml")
    for f in (ver.version, ver.structure, ver.whole, ver.items, ver.control, ver.words, kinds_key):
        assert f(a) == f(b), f
    assert ver.part(a, "items.ticket") == ver.part(b, "items.ticket")
    assert kind_of(a, b, "structure") == "display"
    assert display.beside({str(tmp_path / "ergostat.yaml"): MODEL}) == []        # the file holds OWN now


def test_a_projection_s_own_dashboards_are_listed_and_answered_bound(tmp_path):
    p = project(tmp_path, OWN)
    listed = {d["name"]: d for d in dashboard_api.listing(p)}
    assert (listed["ticket.list"]["projection"], listed["ticket.list"]["role"]) == ("ticket", "list")
    got = dashboard_api.answer(None, p, "ticket.show", {"plain": ["1"], "item": ["ticket/1"]})
    assert [x.get("item") or x.get("projection") for x in got["panels"]] == ["ticket/1", "ticket"]
    got = dashboard_api.answer(None, p, "ticket.list", {"plain": ["1"]})
    assert {x["projection"] for x in got["panels"]} == {"ticket"}


LIST = {"projection": "ticket", "role": "list", "panels": [
    {"panel": "projection-now", "projection": "$projection", "size": "full", "fit": True, "id": "now"},
    {"panel": "note", "text": "Mine.", "size": "s", "id": "p2"}]}


def test_save_writes_a_projection_s_list_under_it_and_accepts_it_at_once(tmp_path):
    p = project(tmp_path)
    x = display.save(p, LIST, snap(), by="owner")
    assert x["status"] == "accepted" and x["dashboard"] == "ticket.list"
    text = p.model.path.read_text()
    block = text.split("  ticket:\n")[1].split("stocks:")[0]
    assert "    dashboards:\n      list:\n        panels:\n" in block and '"text": "Mine."' in block
    p2 = Project(mdl.load(tmp_path))
    d = p2.model.spec.dashboards["ticket.list"]
    assert [x.panel for x in d.panels] == ["projection-now", "note"] and d.panels[0].size == "full"
    accepted = p2.events.query(n=None, type=f"{MODEL_CHANGE}.accepted")
    assert [e["source"] for e in accepted] == ["owner"]
    again = display.save(p2, {**LIST, "panels": LIST["panels"][:1]}, snap())       # saved again: in its place
    p3 = Project(mdl.load(tmp_path))
    assert again["status"] == "accepted" and p3.model.path.read_text().count("list:") == 1
    assert len(p3.model.spec.dashboards["ticket.list"].panels) == 1
    show = display.save(p3, {"projection": "ticket", "role": "show",
                              "panels": [{"panel": "item-fields", "item": "$item"}]}, snap())
    p4 = Project(mdl.load(tmp_path))
    assert show["dashboard"] == "ticket.show" and set(p4.model.spec.dashboards) >= {"ticket.list", "ticket.show"}
    display.reset(p4, {"projection": "ticket", "role": "list"}, snap())
    p5 = Project(mdl.load(tmp_path))
    assert "ticket.list" not in p5.model.spec.dashboards and "ticket.show" in p5.model.spec.dashboards
    display.reset(p5, {"name": "ticket.show"}, snap())
    p6 = Project(mdl.load(tmp_path))
    assert "ticket.show" not in p6.model.spec.dashboards
    assert p6.model.path.read_text() == MODEL                                      # back as it was, to the line


def test_save_writes_a_projection_defined_in_a_subsystem_s_file_into_that_file(tmp_path):
    write(tmp_path, MODEL.replace("dashboards:", "include: [desk.yaml]\ndashboards:"), desk=SUB)
    p = Project(mdl.load(tmp_path))
    main_before = p.model.path.read_text()
    display.save(p, {"projection": "bug", "role": "show", "panels": [{"panel": "item-summary", "item": "$item"}]},
                 snap())
    assert p.model.path.read_text() == main_before
    sub = (tmp_path / "desk.yaml").read_text()
    assert "  bug:\n" in sub and "    dashboards:\n      show:\n        panels:\n" in sub
    p2 = Project(mdl.load(tmp_path))
    assert p2.model.spec.dashboards["bug.show"].projection == "bug"
    display.reset(p2, {"projection": "bug", "role": "show"}, snap())
    assert (tmp_path / "desk.yaml").read_text() == SUB


def test_save_puts_a_page_s_dashboard_in_the_main_file_by_its_name_and_a_new_one_in_the_nav(tmp_path):
    p = project(tmp_path)
    goals = {"name": "goals", "title": "Goals", "panels": [{"panel": "goals", "columns": "all", "size": "full"}]}
    display.save(p, goals, snap())
    p2 = Project(mdl.load(tmp_path))
    assert p2.model.spec.dashboards["goals"].title == "Goals"
    new = {"name": "desk-board", "title": "Desk board", "nav": True, "new": True,
           "panels": [{"panel": "note", "text": "hi"}]}
    display.save(p2, new, snap())
    p3 = Project(mdl.load(tmp_path))
    assert p3.model.spec.dashboards["desk-board"].nav == ""                       # nav: true, its title in the nav
    with pytest.raises(pr.ProposalError, match="in the model already"):
        display.save(p3, new, snap())
    agent = {"name": "agent", "page": "agent", "panels": [{"panel": "agent-what", "agent": "$agent"}]}
    display.save(p3, agent, snap())
    p4 = Project(mdl.load(tmp_path))
    assert p4.model.spec.dashboards["agent"].page == "agent"
    display.reset(p4, {"name": "goals"}, snap())
    p5 = Project(mdl.load(tmp_path))
    assert "goals" not in p5.model.spec.dashboards and "ops" in p5.model.spec.dashboards
    with pytest.raises(pr.ProposalError, match="no dashboard goals is saved"):
        display.reset(p5, {"name": "goals"}, snap())


def test_save_keeps_a_system_file_s_dashboard_under_its_own_name(tmp_path):
    write(tmp_path, MODEL.replace("dashboards:", "include: [desk.yaml]\ndashboards:"), desk="""\
        defaults:
          system: desk
        dashboards:
          board:
            title: Board
            window: 1d
            panels:
              - {panel: chart, refs: stock.queue}
        """)
    p = Project(mdl.load(tmp_path))
    d = p.model.spec.dashboards["desk.board"]
    display.save(p, {"name": "desk.board", "title": "Board", "since": d.window,
                     "panels": [{"panel": "note", "text": "now a note"}]}, snap())
    sub = (tmp_path / "desk.yaml").read_text()
    assert "  board:\n" in sub and "desk.board" not in sub and "window: \"1d\"" in sub
    assert Project(mdl.load(tmp_path)).model.spec.dashboards["desk.board"].panels[0].panel == "note"


def test_save_refuses_what_check_would_refuse_and_writes_nothing(tmp_path):
    p = project(tmp_path)
    before = p.model.path.read_text()
    with pytest.raises(pr.ProposalError, match="does not pass check"):
        display.save(p, {**LIST, "panels": [{"panel": "item-fields", "item": "$item"}]}, snap())   # a list has no $item
    with pytest.raises(pr.ProposalError, match="projection"):
        display.save(p, {**LIST, "projection": "epic"}, snap())
    assert p.model.path.read_text() == before and not pr.pending(p)


def test_the_page_saves_over_http_as_whoever_it_admits(tmp_path):
    import json
    import urllib.request

    from ergostat import web
    p = project(tmp_path)
    server, url = web.serve(p, 0)
    try:
        page = urllib.request.urlopen(url + "/goals").read().decode()
        token = page.split('name="ergostat-token" content="')[1].split('"')[0]
        req = urllib.request.Request(url + "/api/dashboards/save", data=json.dumps(LIST).encode(), method="POST",
                                     headers={"X-Ergostat-Token": token, "Content-Type": "application/json"})
        got = json.loads(urllib.request.urlopen(req).read())
        assert got["status"] == "accepted" and got["by"] == "owner"
        listed = json.loads(urllib.request.urlopen(url + "/api/routes").read())
        assert "ticket.list" in [d["name"] for d in listed["dashboards"]]
        kinds = json.loads(urllib.request.urlopen(url + "/api/panel-kinds").read())
        assert kinds["item-list"]["params"]["finished"] == {"type": "choice", "words": ["hide", "waits", "show"],
                                                             "many": False}
    finally:
        server.shutdown()
        server.server_close()
