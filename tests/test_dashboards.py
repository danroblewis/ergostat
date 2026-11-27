"""Named dashboards (SPEC §4f): declared under dashboards:, checked like show:, namespaced by a system's file, and
served in one request whose panels say what their own endpoints say of the same snapshot."""

import json
import shutil
import textwrap
import time
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.cli import main
from ergostat.spec import read
from ergostat.store import Project

ROOT = Path(__file__).parent.parent

MODEL = """\
systems:
  desk:
    description: where tickets wait
    show: [stock.queue]
projections:
  ticket:
    match:
      key: ticket/*
    states: [open, doing, done]
    events:
      ticket.started:
        state: set('doing')
      ticket.done:
        state: set('done')
    otherwise: rest
stocks:
  queue:
    system: desk
    sensor:
      projection: ticket
      state: [open, doing]
flows:
  closed:
    system: desk
    from: queue
    sensor:
      projection: ticket
      entering: done
goals:
  short-queue:
    system: desk
    stock: queue
    hold: "< 5"
dashboards:
  ops:
    title: The desk
    description: where tickets wait
    window: 2h
    panels:
      - {panel: goals, size: full}
      - {panel: chart, refs: [stock.queue, flow.closed], size: m}
      - {panel: items, projection: ticket, state: doing, size: m}
      - {panel: states, projection: ticket, note: by state}
      - {panel: cycle-time, projection: ticket, size: s}
      - {panel: scope, goal: short-queue}
      - {panel: timeline, projections: ticket}
      - {panel: note, text: "Tickets are counted from their events."}
"""


def write(tmp_path, text=MODEL, **more) -> Path:
    (tmp_path / "ergostat.yaml").write_text(text)
    for name, body in more.items():
        (tmp_path / f"{name}.yaml").write_text(textwrap.dedent(body))
    return tmp_path


def project(tmp_path, text=MODEL) -> Project:
    p = Project(mdl.load(write(tmp_path, text)))
    t = time.time() - 3000
    for i in range(6):
        p.events.add("ticket.opened", item=f"ticket/{i}", data={"title": f"t{i}"}, at=t + i)
        if i < 4:
            p.events.add("ticket.started", item=f"ticket/{i}", at=t + 600 + i)
        if i < 2:
            p.events.add("ticket.done", item=f"ticket/{i}", at=t + 1200 + i)
    return p


def errors(tmp_path, text):
    _, problems = read(write(tmp_path, text) / "ergostat.yaml")
    return [p for p in problems if p.level == "error"]


# ---- the key: loads, validates, round-trips, and its references are checked

def test_a_dashboard_loads_validates_and_round_trips(tmp_path):
    import yaml
    spec, problems = read(write(tmp_path) / "ergostat.yaml")
    assert not [p for p in problems if p.level == "error"], problems
    d = spec.dashboards["ops"]
    assert (d.title, d.description, d.window, len(d.panels)) == ("The desk", "where tickets wait", 7200.0, 8)
    from ergostat.spec.dashboards import plain
    declared = yaml.safe_load(MODEL)["dashboards"]["ops"]["panels"]
    words = {"title": "", "size": "m", "note": ""}            # what a panel says when it says nothing
    assert plain(d)["panels"] == [{**words, **x} for x in declared]          # what was written, back as written
    import jsonschema
    schema = json.loads((ROOT / "schema/ergostat.schema.json").read_text())
    v = jsonschema.Draft202012Validator(schema)
    only = {"dashboards": yaml.safe_load(MODEL)["dashboards"]}     # (safe_load is YAML 1.1: it reads on: as true)
    assert not list(v.iter_errors(only))
    bad = json.loads(json.dumps(only))
    bad["dashboards"]["ops"]["panels"][1]["colour"] = "red"
    assert list(v.iter_errors(bad))
    bad["dashboards"]["ops"]["panels"][1] = {"panel": "pie", "refs": ["stock.queue"]}
    assert list(v.iter_errors(bad))


def test_a_spec_naming_stock_nope_fails_check_with_unknown_ref_at_its_line(tmp_path, capsys):
    text = MODEL.replace("refs: [stock.queue, flow.closed]", "refs: [stock.queue, stock.nope]")
    write(tmp_path, text)
    line = next(i for i, x in enumerate(text.splitlines(), 1) if "stock.nope" in x)
    assert main(["-C", str(tmp_path), "check", "--json"]) == 1
    found = [x for x in json.loads(capsys.readouterr().out)["found"] if x["level"] == "error"]
    assert [(x["code"], x["about"], Path(x["file"]).name, x["line"]) for x in found] == \
        [("unknown-ref", "stock.nope", "ergostat.yaml", line)], found


@pytest.mark.parametrize("old, new, code, about", [
    ("{panel: goals, size: full}", "{panel: pie, size: full}", "bad-dashboard", ""),
    ("{panel: goals, size: full}", "{panel: goals, colour: red}", "unknown-key", ""),
    ("{panel: goals, size: full}", "{panel: goals, goals: [long-queue]}", "unknown-ref", "goal.long-queue"),
    ("{panel: scope, goal: short-queue}", "{panel: scope, goal: nope}", "unknown-ref", "goal.nope"),
    ("{panel: states, projection: ticket, note: by state}", "{panel: states, projection: tickets}", "unknown-ref", "projections.tickets"),
    ("{panel: timeline, projections: ticket}", "{panel: timeline, projections: [ticket, epic]}", "unknown-ref", "projections.epic"),
    ("{panel: items, projection: ticket, state: doing, size: m}", "{panel: items, projection: ticket, state: waiting}", "unknown-ref",
     "projections.ticket"),
    ("{panel: timeline, projections: ticket}", "{panel: timeline, system: floor}", "unknown-ref", "system.floor"),
    ("{panel: chart, refs: [stock.queue, flow.closed], size: m}", "{panel: chart, refs: [auxiliary.x]}", "unknown-ref",
     "auxiliary.x"),
    ("{panel: chart, refs: [stock.queue, flow.closed], size: m}", "{panel: chart, refs: [goal.short-queue]}", "wrong-kind",
     ""),
    ("    window: 2h", "    window: 90d", "bad-dashboard", ""),
    ("    window: 2h", "    window: .nan", "bad-duration", ""),
    ("    title: The desk", "    title: [The, desk]", "bad-dashboard", ""),
    ("{panel: items, projection: ticket, state: doing, size: m}", "{panel: items, projection: ticket, n: 501}", "bad-dashboard", ""),
    ("{panel: cycle-time, projection: ticket, size: s}", "{panel: cycle-time, projection: ticket, size: xl}", "bad-dashboard", ""),
    ("{panel: items, projection: ticket, state: doing, size: m}", "{panel: items, projection: ticket, moved: doing}", "bad-dashboard",
     ""),
    ("    title: The desk", "    owner: me", "unknown-key", ""),
])
def test_unknown_kinds_keys_and_references_are_errors_at_their_line(tmp_path, old, new, code, about):
    text = MODEL.replace(old, new)
    assert text != MODEL
    got = errors(tmp_path, text)
    line = next(i for i, x in enumerate(text.splitlines(), 1) if new.strip() in x)
    assert [(p.code, p.about, p.where.line if p.where else None) for p in got] == [(code, about, line)], got


def test_more_than_24_panels_and_the_name_default_are_refused(tmp_path):
    text = MODEL.replace("      - {panel: goals, size: full}\n", "      - {panel: goals, size: full}\n" * 18)
    assert [p.code for p in errors(tmp_path, text)] == ["bad-dashboard"]
    assert [p.code for p in errors(tmp_path, MODEL.replace("  ops:\n", "  default:\n"))] == ["bad-name"]


def test_a_dashboard_in_a_system_s_file_is_named_by_that_system(tmp_path):
    text = MODEL.replace("dashboards:", "include: [desk.yaml]\ndashboards:")
    write(tmp_path, text, desk="""\
        defaults:
          system: desk
        dashboards:
          ops:
            panels:
              - {panel: chart, refs: stock.queue}
        """)
    spec, problems = read(tmp_path / "ergostat.yaml")
    assert not [p for p in problems if p.level == "error"], problems
    assert set(spec.dashboards) == {"ops", "desk.ops"} and spec.dashboards["desk.ops"].system == "desk"
    assert spec.dashboards["desk.ops"].panels[0].params == {"refs": "stock.queue"}   # as written




def test_a_dashboard_changes_no_version_of_the_model(tmp_path):
    from ergostat.numbers.version import structure, whole
    a, _ = read(write(tmp_path) / "ergostat.yaml")
    b, _ = read(write(tmp_path, MODEL.split("dashboards:")[0]) / "ergostat.yaml")
    assert (structure(a), whole(a)) == (structure(b), whole(b)) and a.dashboards and not b.dashboards


# ---- the batched answer

@pytest.fixture
def live(tmp_path, monkeypatch):
    from ergostat.web import server
    monkeypatch.setattr(server, "_estimates", lambda *a, **k: None)    # a background worker's timing, out of both sides
    p = project(tmp_path)
    return server.Live(p)


def _separate(live, panel: dict, at: float):
    """What the panel's own endpoint answers, asked on its own, of the same moment (a past at: the same snapshot)."""
    from ergostat.spec.dashboards import query
    from ergostat.web.dashboard_api import PATHS
    from ergostat.web.server import api
    params = {k: v for k, v in panel.items() if k not in ("panel", "title", "size", "note", "goals")}
    got = api(live, PATHS[panel["panel"]], {"since": ["7200.0"], "at": [str(at)], **query(params)})
    return {g: got[g] for g in panel["goals"]} if panel.get("goals") else got


def test_one_request_answers_every_panel_as_the_separate_endpoints_do(live):
    from ergostat.web.server import api
    at = time.time() - 5

    def another(*a, **k):                                  # every panel on the dashboard's one snapshot: none asks again
        raise AssertionError("a panel asked for a snapshot of its own")
    live.snapshot = another
    got = api(live, "dashboard/ops", {"at": [str(at)]})
    del live.snapshot
    assert got["window"] == 7200.0 and got["declared"] and len(got["panels"]) == 8
    assert all("answer" in x for x in got["panels"]), [x for x in got["panels"] if "answer" not in x]
    for x in got["panels"]:
        if x["panel"]["panel"] == "note":
            assert x["answer"] == {"text": "Tickets are counted from their events."}
            continue
        assert x["answer"] == _separate(live, x["panel"], at), x["panel"]
    assert got["panels"][2]["answer"]["items"] and got["panels"][0]["answer"]          # not two empty answers alike
    listed = api(live, "dashboards", {})
    assert [(d["name"], d["panels"], d["declared"]) for d in listed] == [("default", 2, False), ("ops", 8, True)]
    assert api(live, "dashboard/nope", {}) is None


OTHER = MODEL + """\
  other:
    title: Another desk
    window: 2h
    panels:
      - {panel: timeline}
      - {panel: chart, refs: [stock.queue, flow.closed], size: m}
      - {panel: note, text: other words}
      - {panel: items, projection: ticket}
"""


def test_two_dashboards_of_one_moment_each_answer_their_own_panels(tmp_path, monkeypatch):
    """Panels at one index of two dashboards, with the same parameters, of one moment: each its own endpoint's."""
    from ergostat.web import server
    from ergostat.web.server import api
    monkeypatch.setattr(server, "_estimates", lambda *a, **k: None)
    live = server.Live(project(tmp_path, OTHER))
    at = time.time() - 5
    ops = api(live, "dashboard/ops", {"at": [str(at)]})
    other = api(live, "dashboard/other", {"at": [str(at)]})
    assert ops["moment"] == other["moment"]                # one moment: the window where they could be confused
    assert [x["panel"]["panel"] for x in other["panels"]] == ["timeline", "chart", "note", "items"]
    for got in (ops, other):
        assert all("answer" in x for x in got["panels"]), got["panels"]
        for x in got["panels"]:
            if x["panel"]["panel"] != "note":
                assert x["answer"] == _separate(live, x["panel"], at), x["panel"]
    assert other["panels"][2]["answer"] == {"text": "other words"}
    assert other["panels"][0]["answer"] != ops["panels"][0]["answer"]
    assert other["panels"][3]["answer"] != ops["panels"][3]["answer"]


def test_an_unchanged_panel_is_not_sent_again(live):
    from ergostat.web.server import api
    at = str(time.time() - 5)
    first = api(live, "dashboard/ops", {"at": [at]})
    stamps = [x["stamp"] for x in first["panels"]]
    stamps[1] = "changed"
    again = api(live, "dashboard/ops", {"at": [at], "have": [",".join(stamps)]})
    assert [("answer" in x, x.get("same")) for x in again["panels"]] == \
        [(False, True), (True, None)] + [(False, True)] * 6
    assert again["panels"][1]["answer"] == first["panels"][1]["answer"]


def test_a_slow_panel_answers_pending_while_the_others_answer(live, monkeypatch):
    from ergostat import series
    from ergostat.web import dashboard_api
    from ergostat.web.server import api
    fast, gate, calls = series.items_flow, __import__("threading").Event(), []

    def slow(*a, **k):                                     # the first call (the states panel): held until let go
        calls.append(1)
        if len(calls) == 1:
            gate.wait(10)
        return fast(*a, **k)
    monkeypatch.setattr(series, "items_flow", slow)
    began = time.monotonic()
    got = api(live, "dashboard/ops", {})
    took = time.monotonic() - began
    kinds = {x["panel"]["panel"]: x for x in got["panels"]}
    assert kinds["states"]["pending"] and kinds["states"]["moment"] == got["moment"] and "answer" not in kinds["states"]
    assert all("answer" in kinds[k] for k in ("goals", "chart", "items", "cycle-time", "scope", "timeline", "note")), \
        got["panels"]
    assert took < dashboard_api.BATCH + 0.5, took
    time.sleep(1.6)                                        # past a live snapshot's 1.5 s: a new one is made for others
    gate.set()                                             # worked out for the next poll, of the same moment
    deadline = time.monotonic() + 10
    while True:
        again = api(live, "dashboard/ops", {"moment": [str(got["moment"])]})
        if all("answer" in x for x in again["panels"]) or time.monotonic() > deadline:
            break
        time.sleep(0.05)
    assert again["moment"] == got["moment"] and again["at"] == got["at"]
    assert [x.get("answer") for x in again["panels"] if x["panel"]["panel"] != "states"] == \
        [x.get("answer") for x in got["panels"] if x["panel"]["panel"] != "states"]
    states = next(x for x in again["panels"] if x["panel"]["panel"] == "states")
    snap = dashboard_api._board(live).moments[got["moment"]][1]             # the moment's own snapshot
    assert states["answer"] == fast(live.p, snap, "ticket") and states["answer"]


BIG = MODEL + "  big:\n    window: 2h\n    panels:\n" + "".join(
    f"      - {{panel: {k}, title: p{i}}}\n" for i, k in enumerate(["goals", "timeline", "note, text: n"] * 8))


def test_a_dashboard_of_the_most_panels_answers_every_one_in_one_request(tmp_path, monkeypatch):
    """24 panels (the checker's cap) on an idle server: every one queued, none busy, each its own endpoint's."""
    from ergostat.spec.dashboards import MOST
    from ergostat.web import dashboard_api, server
    from ergostat.web.server import api
    monkeypatch.setattr(server, "_estimates", lambda *a, **k: None)
    monkeypatch.setattr(dashboard_api, "BATCH", 5.0)            # time is not what this test is about: the pool's room
    monkeypatch.setattr(dashboard_api, "LIMIT", 5.0)
    live = server.Live(project(tmp_path, BIG))
    at = time.time() - 5
    got = api(live, "dashboard/big", {"at": [str(at)]})
    assert len(got["panels"]) == MOST
    assert not [x for x in got["panels"] if x.get("busy") or x.get("pending") or "error" in x], got["panels"]
    for x in got["panels"]:
        if x["panel"]["panel"] != "note":
            assert x["answer"] == _separate(live, x["panel"], at), x["panel"]


def test_a_full_pool_answers_busy_and_queues_nothing(live, monkeypatch):
    from ergostat.web import dashboard_api
    from ergostat.web.server import api
    monkeypatch.setattr(dashboard_api, "WAITING", 0)
    got = api(live, "dashboard/ops", {})
    assert [x.get("busy") for x in got["panels"]] == [True] * 8
    assert not dashboard_api._board(live).jobs


def test_a_moment_named_after_the_model_changed_is_answered_as_a_new_one(live):
    from ergostat.web.server import api
    first = api(live, "dashboard/ops", {"at": [str(time.time() - 5)]})
    live.mtime = ("changed", live.mtime)
    again = api(live, "dashboard/ops", {"at": [str(first["at"])], "moment": [str(first["moment"])]})
    assert again["moment"] != first["moment"]
    odd = api(live, "dashboard/ops", {"at": [str(first["at"])], "moment": ["x"]})     # not a number: a new moment,
    assert odd["at"] == first["at"]                                                   # still at the moment asked


