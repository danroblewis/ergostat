"""Keep (SPEC §4f): a draft becomes a declared dashboard through one display change the owner made, written only by
Accept; the judge passes a display change without a replay, and a change touching anything but dashboards: is
refused as display."""

from __future__ import annotations

import json
import time

import pytest

from ergostat import model as mdl
from ergostat.cli import main
from ergostat.numbers import display, judge
from ergostat.numbers import improve as im
from ergostat.numbers import proposals as pr
from ergostat.spec.ir import MODEL_CHANGE
from ergostat.store import Project
from ergostat.web import dashboard_api
from tests.test_dashboards import MODEL, project

QUERY = {"id": "a", "source": "counts", "kind": "ticket", "state": ["open", "doing"], "group_by": "kind", "agg": "last",
         "transform": "none", "label": "open"}
DRAFT = {"title": "Desk Watch", "since": "1d", "panels": [
    {"id": "p1", "title": "tickets open", "form": "stacked", "size": "m", "tall": True, "note": "",
     "queries": [QUERY], "display": {"unit": "items", "y": {"min": 0}}, "layout": {"x": 0, "y": 0, "w": 6, "h": 8}}]}


def snap() -> dict:
    return {"at": time.time(), "window": 3600.0}


def test_keep_makes_one_display_change_by_the_owner_and_writes_nothing(tmp_path):
    p = project(tmp_path)
    before = p.model.path.read_text()
    x = display.keep(p, DRAFT)
    assert p.model.path.read_text() == before                       # only Accept writes
    assert (x["kind"], x["made_by"], x["target"]) == ("display", "owner", "dashboard.desk-watch")
    made = p.events.query(n=None, type=f"{MODEL_CHANGE}.made")
    assert [(e["item"], e["source"]) for e in made] == [(pr.item_of(x["id"]), "owner")]
    assert [y["id"] for y in pr.pending(p)] == [x["id"]]


def test_keep_then_accept_declares_a_dashboard_check_passes_and_the_api_lists(tmp_path):
    p = project(tmp_path)
    x = display.keep(p, DRAFT)
    got = pr.accept(p, x["id"], snap(), by="owner")
    assert got["status"] == "accepted" and "desk-watch:" in p.model.path.read_text()
    assert main(["-C", str(tmp_path), "check"]) == 0
    p2 = Project(mdl.load(tmp_path))
    assert "desk-watch" in [d["name"] for d in dashboard_api.listing(p2)]
    d = p2.model.spec.dashboards["desk-watch"]
    assert (d.title, d.window, d.panels[0].panel, d.panels[0].size) == ("Desk Watch", 86400.0, "query", "m-tall")
    assert d.panels[0].params["queries"] == [QUERY] and d.panels[0].params["form"] == "stacked"
    accepted = p2.events.query(n=None, type=f"{MODEL_CHANGE}.accepted")
    assert [e["source"] for e in accepted] == ["owner"]
    again = display.keep(p2, {**DRAFT, "panels": [{**DRAFT["panels"][0], "title": "open now"}]})
    pr.accept(p2, again["id"], snap(), by="owner")                 # kept again under its name: put in its place
    p3 = Project(mdl.load(tmp_path))
    assert p3.model.path.read_text().count("desk-watch:") == 1
    assert p3.model.spec.dashboards["desk-watch"].panels[0].title == "open now"


def test_a_kept_draft_is_refused_when_check_would_fail(tmp_path):
    p = project(tmp_path)
    bad = {**DRAFT, "panels": [{**DRAFT["panels"][0], "queries": [{**QUERY, "kind": "epic"}]}]}
    with pytest.raises(pr.ProposalError, match="epic"):
        display.keep(p, bad)
    with pytest.raises(pr.ProposalError, match="rows"):
        display.keep(p, {**DRAFT, "rows": [{"id": "r", "title": "R"}]})
    assert not pr.pending(p)


def test_a_long_chain_of_shared_references_is_sent_as_the_page_sends_it(tmp_path):
    from ergostat.query.parse import MOST_QUERIES
    from ergostat.spec.dashboards import sent
    chain = [{**QUERY, "id": "q-0"}] + [
        {**QUERY, "id": f"q-{i}", "input": f"q-{i - 1}", "output": f"q-{i - 1}", "x": {"type": "query", "query": f"q-{i - 1}"}}
        for i in range(1, MOST_QUERIES)]
    flat, wanted = sent(chain)
    # one level: each input/output is its neighbour as written (still naming the one before), never the whole chain
    assert len(flat) == MOST_QUERIES and len(json.dumps(flat)) < 600 * MOST_QUERIES
    last = flat[-1]
    assert last["input"] == {k: v for k, v in chain[-2].items() if k not in ("id", "label", "hidden")}
    assert last["x"]["query"] == flat[-2]["id"]                     # an x.query goes by id, a query of its own
    assert [mine for mine, _ in wanted] == [x["id"] for x in chain]
    assert sent([{**QUERY, "x": {"type": "query", "query": "nowhere"}}])[0][0]["x"]["query"] == "unknown:nowhere"
    p = project(tmp_path)
    draft = {**DRAFT, "panels": [{**DRAFT["panels"][0], "queries": chain}]}
    try:                                                            # answered (refused or kept), not hung
        display.keep(p, draft)
    except pr.ProposalError:
        pass
    with pytest.raises(pr.ProposalError, match=f"1 to {MOST_QUERIES} queries"):
        display.keep(p, {**DRAFT, "panels": [{**DRAFT["panels"][0], "queries": chain + [{**QUERY, "id": "more"}]}]})


def test_a_display_change_is_passed_by_the_judge_without_a_replay(tmp_path, monkeypatch):
    p = project(tmp_path)
    x = display.keep(p, DRAFT)

    def replayed(*a, **k):
        raise AssertionError("a display change was replayed")
    for name in ("compare", "needs", "recorded"):
        monkeypatch.setattr(judge, name, replayed)
    monkeypatch.setattr(judge.tr, "spec_after", replayed)
    out = judge.run(p, at=time.time())
    assert {"id": x["id"], "verdict": "passed"} in [{k: v["id" if k == "id" else "verdict"] for k in ("id", "verdict")}
                                                     for v in out["verdicts"]]
    assert pr.stored(p)[x["id"]]["state"] == "passed"
    assert "desk-watch" not in p.model.path.read_text()            # display is not accept: auto by default


def _raw(p, old: str, new: str, kind: str = "display") -> dict:
    return {"kind": kind, "parts": [], "title": "a dashboard", "edit": {"file": "ergostat.yaml", "replace": old, "with": new},
            "reasons": [{"says": "the owner asks for it again and again", "evidence": "rule:simplest-structure"}]}


def test_a_change_touching_anything_but_dashboards_is_refused_as_display(tmp_path):
    p = project(tmp_path)
    one = "      - {panel: cycle-time, kind: ticket, size: s}"
    more = one + "\n      - {panel: note, text: kept}"
    with pytest.raises(im.ProposeError, match="not a display change: it changes ergostat.yaml: goals"):
        rest = MODEL.split('    hold: "< 5"\n')[1].rstrip("\n")
        im.validate(p, p.model.spec, "tester", _raw(p, '    hold: "< 5"\n' + rest, '    hold: "< 6"\n' + rest.replace(one, more)))
    same = '    hold: "<5"\n' + rest.replace(one, more)                # the same goal, compiled, but written otherwise
    assert im.kind_of(p.model.spec, display.tr.spec_after(p, im.edits(p.model.spec, _raw(p, '    hold: "< 5"\n' + rest, same)["edit"])),
                      "display") == "display"
    with pytest.raises(im.ProposeError, match="not a display change: it changes ergostat.yaml: goals"):
        im.validate(p, p.model.spec, "tester", _raw(p, '    hold: "< 5"\n' + rest, same))
    with pytest.raises(im.ProposeError, match="proposed as kind: display"):
        im.validate(p, p.model.spec, "tester", _raw(p, one, more, kind="structure"))
    assert im.validate(p, p.model.spec, "tester", _raw(p, one, more))["kind"] == "display"
    texts = {str(p.model.path): MODEL.replace("description: where tickets wait\n    show", "description: x\n    show")}
    assert display.beside(texts) == ["ergostat.yaml: systems"]
    assert display.beside({str(p.model.path): MODEL.replace(one, more)}) == []


def test_keep_refuses_an_edit_that_reaches_past_dashboards(tmp_path, monkeypatch):
    p = project(tmp_path)
    made = display._edit

    def wider(p, spec, name, lines):                       # the entry, and a goal's words written otherwise
        e = made(p, spec, name, lines)
        at = next(i for i, x in enumerate(p.model.path.read_text().split("\n"), 1) if 'hold: "< 5"' in x)
        return display.ye.Edit(e.file, [*e.hunks, display.ye.Hunk(at, ['    hold: "< 5"'], ['    hold: "<5"'])])
    monkeypatch.setattr(display, "_edit", wider)
    with pytest.raises(pr.ProposalError, match="not a display change: it changes ergostat.yaml: goals"):
        display.keep(p, DRAFT)
    assert not pr.pending(p)


def test_an_unreadable_file_counts_as_changed(tmp_path):
    p = project(tmp_path)
    assert display.beside({str(p.model.path): "a: [unclosed"}) == ["ergostat.yaml: it cannot be read"]


def test_the_batched_answer_answers_a_query_panel(tmp_path, monkeypatch):
    from ergostat.web import server
    monkeypatch.setattr(server, "_estimates", lambda *a, **k: None)
    p = project(tmp_path)
    pr.accept(p, display.keep(p, DRAFT)["id"], snap(), by="owner")
    live = server.Live(Project(mdl.load(tmp_path)))
    got = dashboard_api.answer(live, live.get(), "desk-watch", {}, wait=True)
    [panel] = got["panels"]
    assert panel["panel"]["queries"] == [QUERY] and "error" not in panel, json.dumps(panel)[:400]
    assert [r["id"] for r in panel["answer"]["results"]] == ["a"]
