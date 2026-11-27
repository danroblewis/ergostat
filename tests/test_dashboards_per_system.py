"""Each system's dashboards (SPEC §4f, *Dashboards per system*; docs/roadmap/systems-and-projections.md, step 6): every
dashboard binds ``$system`` (the system whose address it is drawn at); a dashboard is a system's by its file's
``defaults: system:`` or its own ``system:``; saving one edited in place writes it into that system's file (else into
the main file, with ``system:``); a system's Events are those behind what it contains; and the links ergostat writes
are at their canonical addresses."""

from __future__ import annotations

import time

from ergostat import model as mdl
from ergostat.numbers import display
from ergostat.spec import read
from ergostat.spec.routes import events_of, kept_table, link, resolve
from ergostat.store import Project
from ergostat.web import dashboard_api
from tests.test_dashboards import MODEL, project, write

DESK = """\
defaults:
  system: desk
projections:
  bug:
    match:
      key: bug/*
    states: [open, fixed]
    events:
      bug.opened:
        state: set('open')
      bug.fixed:
        state: set('fixed')
    otherwise: rest
"""


def snap() -> dict:
    return {"at": time.time(), "window": 3600.0}


def errors(problems) -> list[str]:
    return [str(p) for p in problems if p.level == "error"]


def test_every_dashboard_binds_system_and_one_may_say_its_system(tmp_path):
    text = MODEL + """\
  desk-view:
    system: desk
    panels:
      - {panel: goals, system: $system, size: full}
      - {panel: events, system: $system}
      - {panel: chart, system: $system}
"""
    spec, problems = read(write(tmp_path, text) / "ergostat.yaml")
    assert not errors(problems)
    d = spec.dashboards["desk.desk-view"]                      # a system's: named SYSTEM.NAME, at /desk/desk-view
    assert d.system == "desk" and [x.params.get("system") for x in d.panels] == ["$system"] * 3
    assert resolve(kept_table(spec), "/desk/desk-view")["name"] == "desk.desk-view"
    _, problems = read(write(tmp_path, text.replace("system: $system, size", "system: nowhere, size")) / "ergostat.yaml")
    assert "'nowhere' is not a system" in " ".join(errors(problems))
    _, problems = read(write(tmp_path, MODEL.replace("refs: [stock.queue, flow.closed]", "refs: []")) / "ergostat.yaml")
    assert errors(problems)                                     # a chart: refs, or a system


def test_system_is_bound_from_the_address_and_scopes_the_panels_answered(tmp_path):
    text = MODEL.replace("goals:\n  short-queue:", "goals:\n  any-tickets: {stock: total, hold: '>= 0'}\n  short-queue:", 1) \
        .replace("stocks:\n", "stocks:\n  total: {sensor: {projection: ticket, state: [open, doing, done]}}\n", 1) + """\
  scoped:
    panels:
      - {panel: goals, system: $system}
      - {panel: chart, system: $system}
"""
    p = project(tmp_path, text)
    got = dashboard_api.answer(None, p, "scoped", {"plain": ["1"], "system": ["desk"]})
    assert [x["system"] for x in got["panels"]] == ["desk", "desk"]
    top = dashboard_api.answer(None, p, "scoped", {"plain": ["1"]})
    assert [x["system"] for x in top["panels"]] == ["", ""]           # drawn at the top level: everything
    from ergostat.web import server as ws
    answered = dashboard_api.answer(ws.Live(p), p, "scoped", {"system": ["desk"]}, wait=True)["panels"]
    assert set(answered[0]["answer"]) == {"short-queue"}               # desk's goals, not the top level's
    names = {s["name"] for s in answered[1]["answer"]["series"]}
    assert names == {"queue", "closed"}                                # desk's stocks and flows
    listed = {d["name"]: d for d in dashboard_api.listing(p)}
    assert listed["ops"]["system"] is None


def test_a_systems_events_are_those_behind_what_it_contains(tmp_path):
    write(tmp_path, MODEL.replace("dashboards:", "include: [desk.yaml]\ndashboards:"), desk=DESK)
    p = Project(mdl.load(tmp_path))
    spec = p.model.spec
    globs, _ = events_of(spec, "desk")
    assert set(globs) == {"bug/*", "ticket/*"}                         # its own, and the one its sensors count
    p.events.add("bug.opened", item="bug/1", data={})
    p.events.add("ticket.opened", item="ticket/1", data={})
    p.events.add("other.thing", item="other/1", data={})
    for store_scoped in (events_of(spec, "desk"), events_of(spec, "nowhere")):
        got = [e["item"] for e in p.events.query(n=50, scoped=store_scoped)]
        assert got == (["bug/1", "ticket/1"] if store_scoped[0] else [])
    from ergostat.web import server as ws
    got = ws._answer(ws.Live(p), "events", {"system": ["desk"], "n": ["50"]})          # GET /api/events?system=desk
    assert [e["item"] for e in got] == ["bug/1", "ticket/1"]


def test_save_writes_a_systems_default_into_its_file_and_reset_takes_it_out(tmp_path):
    write(tmp_path, MODEL.replace("dashboards:", "include: [desk.yaml]\ndashboards:"), desk=DESK)
    p = Project(mdl.load(tmp_path))
    main = p.model.path.read_text()
    draft = {"name": "overview", "system": "desk", "title": "Overview",
             "panels": [{"panel": "goals", "system": "$system", "size": "full"}]}
    got = display.save(p, draft, snap())
    assert got["dashboard"] == "desk.overview" and p.model.path.read_text() == main
    sub = (tmp_path / "desk.yaml").read_text()
    assert "dashboards:\n  overview:\n" in sub and "system:" not in sub.split("dashboards:")[1].split("panels")[0]
    p2 = Project(mdl.load(tmp_path))
    assert p2.model.spec.dashboards["desk.overview"].system == "desk"
    assert resolve(kept_table(p2.model.spec), "/desk/overview")["name"] == "desk.overview"   # it replaces the default
    display.reset(p2, {"name": "overview", "system": "desk"}, snap())
    assert (tmp_path / "desk.yaml").read_text().rstrip() == DESK.rstrip()


def test_save_writes_a_system_without_a_file_of_its_own_into_the_main_file_with_system(tmp_path):
    p = project(tmp_path)
    draft = {"name": "goals", "system": "desk", "title": "Goals",
             "panels": [{"panel": "goals", "system": "$system", "size": "full"}]}
    display.save(p, draft, snap())
    text = p.model.path.read_text()
    assert '  goals:\n    system: "desk"\n' in text
    p2 = Project(mdl.load(tmp_path))
    assert p2.model.spec.dashboards["desk.goals"].system == "desk"
    display.save(p2, {**draft, "name": "desk.goals", "panels": [{"panel": "note", "text": "x"}]}, snap())
    p3 = Project(mdl.load(tmp_path))                                   # saved again: in place, still desk's
    assert p3.model.spec.dashboards["desk.goals"].panels[0].panel == "note"
    display.reset(p3, {"name": "goals", "system": "desk"}, snap())
    assert p3.model.path.read_text() == MODEL


def test_the_links_ergostat_writes_are_at_their_canonical_addresses(tmp_path):
    write(tmp_path, MODEL.replace("dashboards:", "include: [desk.yaml]\ndashboards:"), desk=DESK)
    spec = mdl.load(tmp_path).spec
    assert link(spec, "/item/bug/12") == "/desk/bug/12"                # a projection defined in desk
    assert link(spec, "/item/ticket/3") == "/ticket/3"
    assert link(spec, "/item/nobody/3") == "/item/nobody/3"            # no projection sees it
    assert link(spec, "/diagram?view=blocks&around=block/x") == "/diagrams?view=blocks&around=block/x"
    assert link(spec, "/diagram?system=desk&view=blocks") == "/desk/diagrams?view=blocks"
    assert link(spec, "/record?match=x") == "/events?match=x"
    assert link(spec, "https://elsewhere/x") == "https://elsewhere/x"
