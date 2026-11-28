"""The unexplained events as a projection (SPEC §12e, *Unexplained events*): each group of the tally an object of the
built-in ``ergostat.unexplained`` (its count, examples and state: unexplained, drafted, held, ignored, explained),
written by the tally's sync only when it moved; the stock lists them as its items; the group's page links its events."""

from __future__ import annotations

import time

from ergostat.numbers import drafter as dr
from ergostat.numbers import judge as jd
from ergostat.numbers import proposals as pr
from ergostat.numbers import unexplained as ux
from ergostat.spec import item_sets
from ergostat.spec import items as its
from ergostat.spec.ir import UNEXPLAINED

from .test_unexplained_events import DEPLOY, MODEL, again, emit, project, stand_in


def objects(p) -> dict:
    got = its.fold_all(p.events, p.model.spec, UNEXPLAINED, None, False)
    return {i.fields.get("type"): i for i in got}


def test_each_group_is_an_object_with_its_count_and_state(tmp_path):
    p = project(tmp_path)
    emit(p)
    ux.sync(p)
    obs = objects(p)
    assert set(obs) == {"deploy.finished", "debug.tick"}
    d = obs["deploy.finished"]
    assert d.state == "unexplained" and d.fields["count"] == 3 and d.fields["source"] == "deployer"
    assert len(d.fields["examples"]) == 3 and d.fields["request"].startswith("ergostat.modelling-request/")
    assert obs["debug.tick"].state == "ignored" and "debug.*" in obs["debug.tick"].fields["why"]


def test_a_second_sync_with_nothing_changed_writes_nothing(tmp_path):
    p = project(tmp_path)
    emit(p)
    ux.sync(p)
    n = p.events.count()
    assert ux.sync(p)["objects"] == {"written": 0, "explained": 0}
    assert p.events.count() == n
    p.events.add("deploy.finished", source="deployer", data={"service": "s9"})   # one more of 3: past a tenth, written
    assert ux.sync(p)["objects"]["written"] == 1
    assert objects(p)["deploy.finished"].fields["count"] == 4


def test_its_draft_goes_judging_waiting_then_explained_when_written(tmp_path, monkeypatch):
    p = project(tmp_path, MODEL.replace("      ai: true\n", "      ai: true\n      review: {when: off}\n"))
    emit(p)
    ux.sync(p)
    monkeypatch.setenv("ERGOSTAT_AI", stand_in(tmp_path, DEPLOY))
    (pid,) = dr.run(p, daily=1.0)["proposed"]
    ux.sync(p)
    d = objects(p)["deploy.finished"]
    assert d.state == "judging" and d.fields["change"] == f"ergostat.model-change/{pid}" and d.fields["drafts"] == ["deploy"]
    assert d.fields["round"] == 1 and d.fields["title"]
    jd.run(p, "judge")
    ux.sync(p)
    d = objects(p)["deploy.finished"]
    assert d.state == "waiting" and "explains 3" in d.fields["latest"], d.fields["latest"]
    pr.accept(p, pid, {"at": time.time(), "window": 600})
    p = again(p)
    assert ux.sync(p)["objects"]["explained"] == 1
    d = objects(p)["deploy.finished"]
    assert d.state == "explained" and d.fields["count"] == 0 and d.fields["change"] == f"ergostat.model-change/{pid}"
    assert [m["to"] for m in d.moves] == ["unexplained", "judging", "waiting", "explained"]   # every step, its history
    assert ux.sync(p)["objects"] == {"written": 0, "explained": 0}


def test_with_the_reviewer_it_goes_reviewing_then_sent_back_with_its_finding(tmp_path, monkeypatch):
    import json

    from ergostat.numbers import reviewer as rv
    from ergostat.stuck import _kind_of
    p = project(tmp_path)
    emit(p)
    ux.sync(p)
    monkeypatch.setenv("ERGOSTAT_AI", stand_in(tmp_path, DEPLOY))
    (pid,) = dr.run(p, daily=1.0)["proposed"]
    jd.run(p, "judge")
    ux.sync(p)
    assert objects(p)["deploy.finished"].state == "reviewing"
    finding = "State done has no exit"

    def call(text, model, timeout=None):
        return {"result": json.dumps({"review": {"verdict": "revise", "findings": [{"check": "chain", "says": finding}]}}),
                "usd": 0.01, "tokens_in": 10, "tokens_out": 5, "seconds": 0.1}
    rv.run(p, call=call)
    ux.sync(p)
    d = objects(p)["deploy.finished"]
    assert d.state == "sent-back" and d.fields["round"] == 1 and d.fields["latest"] == finding, d.fields
    assert _kind_of(p.model.spec, pr.changes(p)[pid][1] | {"state": pr.changes(p)[pid][0]}) == "sent-back"   # as Goals says


def test_the_stock_lists_the_groups_as_its_items(tmp_path):
    p = project(tmp_path)
    st = p.model.spec.stocks["unexplained-events"]
    live = ["unexplained", "judging", "reviewing", "sent-back", "waiting", "held"]
    assert st.items == {"kind": UNEXPLAINED, "state": live}
    got = item_sets.of_part(p.model.spec, "stock", "unexplained-events", 0, time.time(), p.model)
    assert got["set"]["projection"] == [UNEXPLAINED] and got["set"]["state"] == [",".join(live)], got
    assert "modelling events" not in got["how"] and "as declared" in got["how"]


def test_a_stocks_items_must_name_a_projection_and_its_states(tmp_path):
    from ergostat.spec import read
    (tmp_path / "ergostat.yaml").write_text(
        "name: t\nstocks:\n  s:\n    unit: x\n    items: {projection: nothing}\n  t:\n    unit: x\n"
        "    items: {projection: ergostat.modelling-request, state: [nowhere]}\n")
    _, ps = read(tmp_path / "ergostat.yaml")
    said = " ".join(str(x) for x in ps if x.level == "error")
    assert "'nothing' is not a projection" in said and "nowhere not a state" in said
