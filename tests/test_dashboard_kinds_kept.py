"""A dashboard's panels of every kind (SPEC §4f): a diagram panel is declared by its address and checked, and Keep
keeps a draft's panels of any declared kind as they are written, not only its query panels."""

from __future__ import annotations

import time

from ergostat import model as mdl
from ergostat.cli import main
from ergostat.numbers import display
from ergostat.numbers import proposals as pr
from ergostat.store import Project
from ergostat.web import dashboard_api
from tests.test_dashboard_keep import DRAFT
from tests.test_dashboards import project


def snap() -> dict:
    return {"at": time.time(), "window": 3600.0}


def test_a_draft_with_a_diagram_a_note_and_goals_is_kept_as_written_and_checks(tmp_path):
    p = project(tmp_path)
    draft = {"title": "Ops", "panels": [
        {"id": "p1", "panel": "diagram", "title": "The system", "size": "full", "address": "/diagram?view=blocks"},
        {"id": "p2", "panel": "note", "title": "Read me", "text": "What this board is for", "size": "s"},
        {"id": "p3", "panel": "goals", "title": "Goals", "size": "m", "tall": True},
        DRAFT["panels"][0]]}
    x = display.keep(p, draft)
    pr.accept(p, x["id"], snap(), by="owner")
    assert main(["-C", str(tmp_path), "check"]) == 0
    d = Project(mdl.load(tmp_path)).model.spec.dashboards["ops"]
    assert [(q.panel, q.size) for q in d.panels] == [("diagram", "full"), ("note", "s"), ("goals", "m-tall"), ("query", "m-tall")]
    assert d.panels[0].params == {"address": "/diagram?view=blocks"} and d.panels[1].params == {"text": "What this board is for"}
    assert "id" not in d.panels[0].params                          # the page's handle is never written


def test_a_diagram_panel_answers_its_address_and_one_not_a_diagram_address_is_refused(tmp_path):
    p = project(tmp_path)
    x = display.keep(p, {"title": "Pic", "panels": [{"panel": "diagram", "address": "/diagram?view=process"}]})
    pr.accept(p, x["id"], snap(), by="owner")
    p2 = Project(mdl.load(tmp_path))
    from ergostat.web.server import Live
    got = dashboard_api.answer(Live(p2), p2, "pic", {}, wait=True)
    assert got["panels"][0]["answer"] == {"address": "/diagram?view=process"}
    bad = {"title": "Bad", "panels": [{"panel": "diagram", "address": "https://elsewhere.example/"}]}
    try:
        display.keep(p2, bad)
    except pr.ProposalError as e:
        assert "Diagram address" in str(e)
    else:
        raise AssertionError("a diagram panel that is not a Diagram address was kept")
